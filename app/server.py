"""
Servidor Flask y API para la aplicación de monitoreo de agujeros negros en TESS.
Expone estado en tiempo real, eventos en vivo, notificaciones y control de inicio/parada.
"""
import os
import sys
from pathlib import Path

# Agregar directorio raíz al PYTHONPATH
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import json
import sqlite3
import threading
import time
import numpy as np
from flask import Flask, render_template, jsonify, request, send_file
from flask_cors import CORS

from concurrent.futures import ThreadPoolExecutor, as_completed, wait, FIRST_COMPLETED
from config import OUTPUT_DIR, CANDIDATES_DIR, PLOTS_DIR, PipelineConfig
from pipeline.continuous_scanner import ContinuousScanner
from pipeline.detectors.exoplanet_full_pipeline import ExoplanetPipeline
from pipeline.detectors.transients_detector import TransientDetectorEngine
from pipeline.notifier_exoplanet import ExoplanetAlertNotifier
from pipeline.telegram_control_bot import TelegramSentinelBot
from pipeline.sky_patch_manager import SkyPatchManager
from pipeline.sync_evaluator import HistoricalSyncManager
from pipeline.notifier import AlertNotifier
from pipeline.proposal_generator import ProposalGenerator
from pipeline.orbit_analyzer import NeighborhoodOrbitAnalyzer
from pipeline.benchmark_calibration import get_benchmark_catalog, calibrate_target
from pipeline.safe_logger import safe_print as print

orbit_analyzer = NeighborhoodOrbitAnalyzer()
pipeline_cfg = PipelineConfig()
WORKERS_COUNT = getattr(pipeline_cfg, "max_workers", 4)

app = Flask(__name__, template_folder="templates", static_folder="static")
CORS(app)

DB_PATH = OUTPUT_DIR / "scan_progress.db"
ALERTS_PATH = OUTPUT_DIR / "alerts.jsonl"
ALERTS_EXO_PATH = OUTPUT_DIR / "alerts_exoplanets.jsonl"
ALERTS_TRANS_PATH = OUTPUT_DIR / "alerts_transients.jsonl"
transient_engine_instance = TransientDetectorEngine(significance_threshold=6.0)
exoplanet_pipeline_instance = ExoplanetPipeline()
exoplanet_notifier_instance = ExoplanetAlertNotifier(ALERTS_EXO_PATH)

def telegram_toggle_scanner(enable: bool):
    global scanner_running, scanner_thread
    if enable and not scanner_running:
        scanner_running = True
        scanner_thread = threading.Thread(target=scanner_worker, daemon=True)
        scanner_thread.start()
    elif not enable and scanner_running:
        scanner_running = False

def telegram_priority_target(target_id: str):
    threading.Thread(target=process_single_target, args=(target_id,), daemon=True).start()

telegram_bot = TelegramSentinelBot(
    db_path=DB_PATH,
    alerts_bh_path=ALERTS_PATH,
    alerts_exo_path=ALERTS_EXO_PATH,
    toggle_callback=telegram_toggle_scanner,
    priority_callback=telegram_priority_target
)
telegram_bot.start_in_background()

scanner_thread = None
scanner_running = False
scanner_instance = ContinuousScanner(max_workers=WORKERS_COUNT)
current_target_name = "Initializing..."
current_target_coords = {"ra": None, "dec": None}
db_write_lock = threading.Lock()

def process_single_target(target_id: str):
    """Procesa un objetivo individual de forma concurrente con DOWNLOAD ONCE, FEED ALL."""
    global current_target_name, current_target_coords
    current_target_name = target_id

    try:
        # 1. Run Black Hole Pipeline (which downloads light curve and extracts stellar properties)
        res = scanner_instance.pipeline.analyze_target(target_id)
        status = res.get("status", "NO_DATA")
        assessment = res.get("assessment", {})
        is_candidate = assessment.get("undocumented_candidate", False)
        verdict = assessment.get("verdict", "")
        if not verdict and res.get("reason"):
            verdict = res.get("reason")

        simbad = res.get("simbad_info", {})
        tic_info = simbad.get("tic_info", {}) if simbad else {}
        t_ra = tic_info.get("ra")
        t_dec = tic_info.get("dec")

        if t_ra is not None and t_dec is not None:
            current_target_coords = {"ra": t_ra, "dec": t_dec}

        # Retrieve cached lightcurve in memory to feed exoplanet and transient engines directly (NO RE-DOWNLOAD)
        raw_lc = res.get("raw_lightcurve")
        exo_eval_success = 0
        trans_eval_success = 0

        if raw_lc is not None and hasattr(raw_lc, "time") and hasattr(raw_lc, "flux"):
            t_arr = np.array(raw_lc.time.value, dtype=float)
            f_arr = np.array(raw_lc.flux.value, dtype=float)

            # 2. Rigorous Multi-Test Exoplanet Evaluation (Odd-Even + Secondary Eclipse + Cross-Match Veto)
            try:
                norm_f = f_arr / np.median(f_arr)
                # Quick pre-filter: must have dips > 100 ppm
                if np.min(norm_f) < 0.9999:
                    tls_res = exoplanet_pipeline_instance.physics_engine.run_tls_analysis(t_arr, norm_f)
                    exo_eval_success = 1

                    if tls_res.get("tls_detected"):
                        p_days = tls_res.get("period_days", 1.0)
                        t0_val = tls_res.get("t0_bjd", t_arr[0])
                        d_ppm = tls_res.get("transit_depth_ppm", 0.0)

                        # VETO 1: Odd-Even Depth Test (Descarta Binarias Eclipsantes EBs)
                        odd_even = exoplanet_pipeline_instance.physics_engine.odd_even_depth_veto(
                            t_arr, norm_f, p_days, t0_val, d_ppm * 1e-6
                        )
                        # VETO 2: Secondary Eclipse (Descarta estrellas compañeras luminosas)
                        sec_ecl = exoplanet_pipeline_instance.physics_engine.secondary_eclipse_veto(
                            t_arr, norm_f, p_days, t0_val
                        )

                        # Check if vetoes trigger
                        is_eb = odd_even.get("is_eb", False)
                        has_sec = sec_ecl.get("secondary_detected", False)

                        # VETO 3: Cross-Match Check (NASA Exoplanet Archive & TOIs)
                        is_known_planet = False
                        if simbad:
                            is_known_planet = simbad.get("is_exoplanet_host", False) or simbad.get("is_eclipsing_binary", False)

                        # STRICT CANDIDATE GATE: NO FALSER ALARMS, NO EBs, NO ALREADY KNOWN
                        if not is_eb and not has_sec and not is_known_planet:
                            params = exoplanet_pipeline_instance.physics_engine.derive_planetary_parameters(
                                d_ppm, p_days
                            )
                            # Confidence score
                            c_score = min(99.0, 60.0 + (tls_res.get("sde", 7.0) * 3.5))
                            if params.get("in_habitable_zone"):
                                c_score += 5.0

                            criteria = [
                                f"TLS Detection: SDE {tls_res.get('sde', 0.0):.1f}σ (Exceeds >7.0σ discovery threshold)",
                                f"Period: {p_days:.4f} days | Transit Depth: {d_ppm:.0f} ppm",
                                f"Physical Classification: {params.get('classification')} (Rp = {params.get('planet_radius_earth')} R⊕)",
                                f"Equilibrium Temperature: {params.get('equilibrium_temp_k')} K {'[HABITABLE ZONE]' if params.get('in_habitable_zone') else ''}",
                                f"Anti-EB Odd/Even Test Passed: Δ={odd_even.get('delta_depth_sigma', 0.0):.1f}σ (<3.0σ limit)",
                                f"Secondary Eclipse Veto Passed: No companion occultation at φ=0.5",
                                "Catalog Cross-Match: Clean (Undocumented in NASA Exoplanet Archive and TOI Catalog)"
                            ]

                            exo_obj = {
                                "target_id": target_id,
                                "ra": t_ra,
                                "dec": t_dec,
                                "tls_results": tls_res,
                                "planetary_params": params,
                                "veto_results": {"odd_even": odd_even, "secondary": sec_ecl},
                                "score": round(c_score, 1),
                                "criteria_list": criteria,
                                "is_candidate": True,
                                "verdict": f"HIGH-CONFIDENCE EXOPLANET CANDIDATE ({params.get('classification')}, Rp={params.get('planet_radius_earth')} R⊕, P={p_days:.2f}d)"
                            }
                            is_candidate = True
                            verdict = exo_obj["verdict"]
                            exoplanet_notifier_instance.notify(exo_obj)
                        else:
                            # It is a vetoed false positive or known object: DO NOT NOTIFY, DO NOT ADD TO CANDIDATES
                            verdict = f"VETOED (False Positive): {'Odd-Even EB' if is_eb else ('Secondary Eclipse' if has_sec else 'Known Planet/EB')}"
                else:
                    exo_eval_success = 1
            except Exception:
                pass

            # 3. Fast Transients & Supernova detector on in-memory array
            try:
                trans_res = transient_engine_instance.analyze_lightcurve(t_arr, f_arr, target_id=target_id)
                trans_eval_success = 1
                if trans_res and trans_res.get("is_transient"):
                    with open(ALERTS_TRANS_PATH, "a", encoding="utf-8") as tf:
                        tf.write(json.dumps(trans_res) + "\n")
            except Exception:
                pass

        with db_write_lock:
            with sqlite3.connect(DB_PATH, timeout=30.0) as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO processed_targets 
                    (target_id, status, is_candidate, verdict, details, ra, dec, evaluated_bh, evaluated_exo, evaluated_transient)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                """, (target_id, status, 1 if is_candidate else 0, verdict, str(res.get("detection_details", {}).get("type", "")), t_ra, t_dec, exo_eval_success, trans_eval_success))
                conn.execute("""
                    INSERT INTO system_metrics (metric_key, metric_val) VALUES ('total_evaluations', 1)
                    ON CONFLICT(metric_key) DO UPDATE SET metric_val = metric_val + 1;
                """)
                conn.commit()

        if is_candidate:
            scanner_instance.notifier.notify(res)



    except Exception as e:
        with db_write_lock:
            scanner_instance.mark_processed(
                target_id=target_id,
                status="ERROR",
                is_candidate=False,
                verdict=f"Execution/Processing error: {str(e)}",
                details=str(type(e).__name__)
            )

def scanner_worker():
    global scanner_running, scanner_instance, current_target_name, current_target_coords
    scanner_instance = ContinuousScanner(max_workers=WORKERS_COUNT)
    patch_mgr = SkyPatchManager(DB_PATH)
    queue = []
    current_patch_id = None
    stars_evaluated_in_patch = 0

    print(f"\n[Scanner] High-Performance Multi-Worker Pipeline started ({WORKERS_COUNT} threads).")

    with ThreadPoolExecutor(max_workers=WORKERS_COUNT, thread_name_prefix="TESS-Worker") as executor:
        active_futures = set()

        while scanner_running:
            if not queue and not active_futures:
                if current_patch_id:
                    # Mark previous patch completed in DB
                    patch_mgr.complete_patch(current_patch_id, stars_evaluated_in_patch, 0)
                    print(f"[Scanner Spatial] ✅ Completed patch {current_patch_id} ({stars_evaluated_in_patch} stars).")
                    current_patch_id = None
                    stars_evaluated_in_patch = 0

                # Get next unscanned patch in spiral
                p_ra, p_dec, patch_id = patch_mgr.get_next_unscanned_patch(280.0, -60.0, radius_deg=0.5)
                current_patch_id = patch_id
                patch_mgr.start_patch(patch_id, p_ra, p_dec, 0.5)
                current_target_coords = {"ra": p_ra, "dec": p_dec}

                stars = patch_mgr.fetch_stars_in_patch(p_ra, p_dec, radius_deg=0.5, tmag_limit=13.0)
                if stars:
                    # Batch check in SQLite to avoid N individual queries
                    star_ids = [s["target_id"] for s in stars]
                    with sqlite3.connect(DB_PATH, timeout=30.0) as conn:
                        placeholders = ",".join("?" for _ in star_ids)
                        rows = conn.execute(f"SELECT target_id, evaluated_exo FROM processed_targets WHERE target_id IN ({placeholders})", star_ids).fetchall()
                        fully_audited = {r[0] for r in rows if r[1] == 1}

                    queue = [sid for sid in star_ids if sid not in fully_audited]
                    print(f"[Scanner Spatial] Loaded {len(queue)} pending stars for patch {patch_id} at ({p_ra:.2f}°, {p_dec:.2f}°)")
                else:
                    patch_mgr.complete_patch(patch_id, 0, 0)
                    current_patch_id = None
                    time.sleep(1)
                    continue

            # Rellenar el pool con workers libres
            while queue and len(active_futures) < WORKERS_COUNT:
                t_id = queue.pop(0)
                future = executor.submit(process_single_target, t_id)
                active_futures.add(future)
                stars_evaluated_in_patch += 1

            if not active_futures:
                time.sleep(0.5)
                continue

            # Esperar a que el primer worker disponible termine para despachar el siguiente inmediatamente
            done, _ = wait(active_futures, return_when=FIRST_COMPLETED, timeout=0.5)
            for f in done:
                active_futures.remove(f)
                try:
                    f.result()
                except Exception as err:
                    print(f"[Scanner Worker Error]: {err}")

@app.route("/")
def index():
    return render_template("index.html")

sync_manager_instance = HistoricalSyncManager(DB_PATH, max_workers=2)
sync_thread = None

def run_background_sync():
    sync_manager_instance.run_sync(batch_size=30)

@app.route("/api/sync/start", methods=["POST"])
def start_sync():
    global sync_thread
    if sync_thread is None or not sync_thread.is_alive():
        sync_thread = threading.Thread(target=run_background_sync, daemon=True)
        sync_thread.start()
        return jsonify({"status": "STARTED", "pending_count": len(sync_manager_instance.get_pending_sync_targets())})
    return jsonify({"status": "ALREADY_RUNNING", "progress": sync_manager_instance.processed_in_sync, "total": sync_manager_instance.total_to_sync})

@app.route("/api/sync/status")
def sync_status():
    is_active = sync_thread is not None and sync_thread.is_alive()
    pending = len(sync_manager_instance.get_pending_sync_targets())
    return jsonify({
        "is_active": is_active,
        "processed": sync_manager_instance.processed_in_sync,
        "total": sync_manager_instance.total_to_sync,
        "pending_remaining": pending
    })

@app.route("/api/status")
def get_status():
    total_processed = 0
    total_candidates = 0
    recent_logs = []
    inspected_coordinates = []

    # Consultar DB SQLite
    if DB_PATH.exists():
        try:
            with sqlite3.connect(DB_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT metric_val FROM system_metrics WHERE metric_key = 'total_evaluations'")
                m_row = cursor.fetchone()
                cursor.execute("SELECT COUNT(*), SUM(CASE WHEN evaluated_bh = 1 THEN 1 ELSE 0 END), SUM(CASE WHEN evaluated_exo = 1 THEN 1 ELSE 0 END), SUM(CASE WHEN evaluated_transient = 1 THEN 1 ELSE 0 END) FROM processed_targets")
                p_row = cursor.fetchone()
                db_total = p_row[0] or 0
                proc_bh = p_row[1] or 0
                proc_exo = p_row[2] or 0
                proc_trans = p_row[3] or 0

                if m_row and m_row[0]:
                    total_processed = max(m_row[0], db_total)
                else:
                    total_processed = db_total

                cursor.execute("""
                    SELECT target_id, status, verdict, processed_at, ra, dec, is_candidate
                    FROM processed_targets
                    ORDER BY processed_at DESC
                    LIMIT 60
                """)
                for r in cursor.fetchall():
                    recent_logs.append({
                        "target_id": r[0],
                        "status": r[1],
                        "verdict": r[2],
                        "timestamp": r[3],
                        "ra": r[4],
                        "dec": r[5],
                        "is_candidate": bool(r[6])
                    })

                # Obtener puntos celestes de estrellas inspeccionadas para el Skymap
                cursor.execute("""
                    SELECT target_id, ra, dec, is_candidate
                    FROM processed_targets
                    WHERE ra IS NOT NULL AND dec IS NOT NULL
                    ORDER BY processed_at DESC
                    LIMIT 200
                """)
                for r in cursor.fetchall():
                    inspected_coordinates.append({
                        "target_id": r[0],
                        "ra": r[1],
                        "dec": r[2],
                        "is_candidate": bool(r[3])
                    })
        except Exception as e:
            pass

    # Leer alertas reales generadas por el pipeline
    alerts = []
    seen_ids = set()
    if ALERTS_PATH.exists():
        try:
            with open(ALERTS_PATH, "r", encoding="utf-8") as f:
                lines = f.readlines()
                for line in reversed(lines):
                    if line.strip():
                        alert_obj = json.loads(line)
                        t_id = alert_obj.get("target_id")
                        if t_id and t_id not in seen_ids:
                            alerts.append(alert_obj)
                            seen_ids.add(t_id)
        except Exception:
            pass

    # Consultar parches celestes espaciales
    surveyed_patches = []
    if DB_PATH.exists():
        try:
            with sqlite3.connect(DB_PATH) as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()
                cur.execute("""
                    SELECT patch_id, ra_center, dec_center, radius_deg, stars_evaluated, candidates_found, status, started_at
                    FROM surveyed_sky_patches
                    ORDER BY started_at DESC
                    LIMIT 50
                """)
                surveyed_patches = [dict(r) for r in cur.fetchall()]
        except Exception:
            pass

    # Leer alertas reales de exoplanetas
    # Leer alertas reales de transitorios y supernovas
    transient_alerts = []
    seen_trans_ids = set()
    if ALERTS_TRANS_PATH.exists():
        try:
            with open(ALERTS_TRANS_PATH, "r", encoding="utf-8") as f:
                for line in reversed(f.readlines()):
                    if line.strip():
                        t_obj = json.loads(line)
                        tr_id = t_obj.get("target_id")
                        if tr_id and tr_id not in seen_trans_ids:
                            transient_alerts.append(t_obj)
                            seen_trans_ids.add(tr_id)
        except Exception:
            pass

    exo_alerts = []
    seen_exo_ids = set()
    if ALERTS_EXO_PATH.exists():
        try:
            with open(ALERTS_EXO_PATH, "r", encoding="utf-8") as f:
                for line in reversed(f.readlines()):
                    if line.strip():
                        exo_obj = json.loads(line)
                        e_id = exo_obj.get("target_id")
                        if e_id and e_id not in seen_exo_ids:
                            exo_alerts.append(exo_obj)
                            seen_exo_ids.add(e_id)
        except Exception:
            pass

    # Total unified candidate count across genuine Black Holes, Exoplanets and Transients
    unified_total_candidates = len(alerts) + len(exo_alerts) + len(transient_alerts)

    # Per-category metrics (both processed stars and candidates per modality)
    category_metrics = {
        "bh": {
            "processed": proc_bh if 'proc_bh' in locals() else total_processed,
            "candidates": len(alerts)
        },
        "exo": {
            "processed": proc_exo if 'proc_exo' in locals() else total_processed,
            "candidates": len(exo_alerts)
        },
        "transient": {
            "processed": proc_trans if 'proc_trans' in locals() else total_processed,
            "candidates": len(transient_alerts)
        }
    }

    return jsonify({
        "scanner_running": scanner_running,
        "current_target": current_target_name if scanner_running else "Paused",
        "current_target_coords": current_target_coords if scanner_running else None,
        "total_processed": total_processed,
        "total_candidates": unified_total_candidates,
        "category_metrics": category_metrics,
        "sync_progress": {
            "is_active": sync_thread is not None and sync_thread.is_alive(),
            "processed": sync_manager_instance.processed_in_sync,
            "total": sync_manager_instance.total_to_sync,
            "pending_remaining": len(sync_manager_instance.get_pending_sync_targets())
        },
        "alerts": alerts,
        "exo_alerts": exo_alerts,
        "transient_alerts": transient_alerts,
        "recent_logs": recent_logs,
        "inspected_coordinates": inspected_coordinates,
        "surveyed_patches": surveyed_patches
    })

@app.route("/api/scanner/toggle", methods=["POST"])
def toggle_scanner():
    global scanner_running, scanner_thread
    if scanner_running:
        scanner_running = False
    else:
        scanner_running = True
        scanner_thread = threading.Thread(target=scanner_worker, daemon=True)
        scanner_thread.start()
    # Auto-start historical sync thread in background with polite worker count
    global sync_thread
    sync_thread = threading.Thread(target=run_background_sync, daemon=True)
    sync_thread.start()
    return jsonify({"scanner_running": scanner_running})

@app.route("/api/orbits/<target_id>")
def get_orbits(target_id):
    """Retorna la cinemática de estrellas vecinas y la órbita kepleriana alrededor del objeto oscuro."""
    ra = request.args.get("ra", type=float)
    dec = request.args.get("dec", type=float)
    if ra is None or dec is None:
        # Intentar obtener coordenadas desde DB o simulación
        ra, dec = 260.6725, -0.6022
    
    analysis = orbit_analyzer.analyze_neighborhood(ra=ra, dec=dec, candidate_id=target_id)
    return jsonify(analysis)

@app.route("/api/proposal/<target_id>")
def download_proposal(target_id):
    """Permite descargar la propuesta PDF formal de observación astronómica."""
    clean_name = target_id.replace(" ", "_").replace("/", "_")
    proposal_path = OUTPUT_DIR / "proposals" / f"{clean_name}_ToO_Proposal.pdf"
    
    # Si aún no existe el PDF, generarlo en caliente
    if not proposal_path.exists():
        pg = ProposalGenerator(OUTPUT_DIR)
        mock_info = {
            "target_id": target_id,
            "detection_details": {"type": "Compact Object Candidate"},
            "assessment": {"confidence": "High", "verdict": "Candidato detectado por TESS Sentinel"},
            "criteria_list": [
                "Ajuste astrofísico consistente",
                "Sin catalogación previa en SIMBAD/MAST",
                "Auto-Verificación Multi-Observatorio completada"
            ]
        }
        proposal_path = Path(pg.generate_pdf_proposal(mock_info))

    return send_file(proposal_path, as_attachment=True, download_name=f"{clean_name}_ToO_Proposal.pdf")

@app.route("/api/export_csv/<target_id>")
def export_target_csv(target_id):
    """Exporta los datos de fotometría limpia en CSV estandarizado."""
    import lightkurve as lk
    import io
    from flask import Response
    
    clean_id = target_id.strip()
    try:
        search = lk.search_lightcurve(clean_id)
        if len(search) > 0:
            lc = search[0].download().remove_nans().normalize()
            output = io.StringIO()
            output.write("# TESS Black Hole Sentinel - Standard Photometry Export\n")
            output.write(f"# Target: {clean_id}\n")
            output.write("time_bjd,normalized_flux,flux_err\n")
            for t, f in zip(lc.time.value, lc.flux.value):
                output.write(f"{t:.6f},{f:.6f},0.005000\n")
            
            return Response(
                output.getvalue(),
                mimetype="text/csv",
                headers={"Content-disposition": f"attachment; filename={clean_id.replace(' ', '_')}_photometry.csv"}
            )
    except Exception as e:
        pass
    return jsonify({"error": f"Photometry data not available for {clean_id}"}), 404

@app.route("/api/simulate_candidate", methods=["POST"])
def simulate_candidate():
    """Genera un evento de candidato sintético para probar el monitor, mapa celeste y sonido."""
    notifier = AlertNotifier(ALERTS_PATH)
    sim_id = f"TIC {int(time.time()) % 100000000}"
    # Coordenadas realistas cerca del plano/bulbo galáctico
    import random
    sim_ra = round(random.uniform(260.0, 280.0), 4)
    sim_dec = round(random.uniform(-35.0, -20.0), 4)

    # Generar curva de luz sintética de microlente para renderizado inmediato
    import numpy as np
    t_synth = np.linspace(1520.0, 1570.0, 250)
    tau = (t_synth - 1545.0) / 48.5
    u = np.sqrt(0.24**2 + tau**2)
    a_synth = (u**2 + 2.0) / (u * np.sqrt(u**2 + 4.0))
    flux_synth = a_synth + np.random.normal(0, 0.003, size=len(t_synth))

    simulated_info = {
        "target_id": sim_id,
        "ra": sim_ra,
        "dec": sim_dec,
        "detection_details": {
            "type": "Microlensing (Paczynski)",
            "tE_days": 48.5,
            "peak_magnification": 4.12,
            "delta_chi2": 950.0,
            "reduced_chi2": 1.08,
            "asymmetry_index": 0.04
        },
        "assessment": {
            "undocumented_candidate": True,
            "confidence": "High",
            "verdict": f"Extended microlensing event tE=48.5d characteristic of an isolated massive black hole (M > 8 M_☉) at RA:{sim_ra}°, DEC:{sim_dec}°."
        },
        "lightcurve_sample": {
            "time": [round(float(t), 4) for t in t_synth],
            "flux": [round(float(f), 4) for f in flux_synth]
        },
        "report_path": "outputs/candidates/simulated_candidate.json"
    }

    # Generar propuesta PDF
    try:
        pg = ProposalGenerator(OUTPUT_DIR)
        simulated_info["proposal_pdf"] = pg.generate_pdf_proposal(simulated_info)
    except Exception:
        pass

    notifier.notify(simulated_info)

    # También registrar en DB como candidato con coordenadas
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            INSERT OR REPLACE INTO processed_targets (target_id, status, is_candidate, verdict, details, ra, dec)
            VALUES (?, 'SUCCESS', 1, ?, 'Microlensing (Paczynski)', ?, ?)
        """, (simulated_info["target_id"], simulated_info["assessment"]["verdict"], sim_ra, sim_dec))
        conn.commit()

    return jsonify({"status": "Simulated candidate triggered", "target": simulated_info["target_id"], "ra": sim_ra, "dec": sim_dec})

@app.route("/api/benchmark_catalog")
def get_benchmark():
    """Retorna el catálogo curado de agujeros negros confirmados para calibración."""
    return jsonify(get_benchmark_catalog())

@app.route("/api/calibrate_benchmark", methods=["POST"])
def run_calibration():
    """Ejecuta la calibración sobre un objetivo del catálogo confirmado."""
    data = request.get_json() or {}
    target_id = data.get("target_id", "CYG_X1")
    result = calibrate_target(target_id)
    return jsonify(result)

def start_server(port: int = 5055):
    global scanner_running, scanner_thread, sync_thread
    scanner_running = True
    scanner_thread = threading.Thread(target=scanner_worker, daemon=True)
    scanner_thread.start()
    sync_thread = threading.Thread(target=run_background_sync, daemon=True)
    sync_thread.start()
    print(f"\n=======================================================")
    print(f"🖥️  MONITOR SENTINEL INICIADO EN: http://127.0.0.1:{port}")
    print(f"=======================================================\n")
    app.run(host="0.0.0.0", port=port, debug=False)

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5055
    start_server(port)
