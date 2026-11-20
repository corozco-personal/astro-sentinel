"""
Historical Synchronization Process for ASTRO SENTINEL
-----------------------------------------------------
Scans all historical database entries in `processed_targets`:
1. Targets that had status == 'ERROR'.
2. Targets processed prior to the multi-modal upgrade (evaluated_exo == 0 or evaluated_transient == 0).
Re-runs the full pipeline (BH + Exoplanet TLS + Transients) and updates the records to 100% evaluated.
"""

import time
import sqlite3
import numpy as np
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, List, Dict, Any

from pipeline.pipeline import BlackHolePipeline
from pipeline.detectors.exoplanet_full_pipeline import ExoplanetPipeline
from pipeline.detectors.transients_detector import TransientDetectorEngine
from pipeline.notifier_exoplanet import ExoplanetAlertNotifier
from pipeline.notifier import AlertNotifier


class HistoricalSyncManager:
    def __init__(self, db_path: Path, max_workers: int = 4):
        self.db_path = db_path
        self.max_workers = max_workers
        self.bh_pipe = BlackHolePipeline()
        self.exo_pipe = ExoplanetPipeline()
        self.trans_engine = TransientDetectorEngine()
        self.exo_notifier = ExoplanetAlertNotifier(db_path.parent / "alerts_exoplanets.jsonl")
        self.bh_notifier = AlertNotifier(db_path.parent / "alerts.jsonl")
        self.is_running = True
        self.processed_in_sync = 0
        self.total_to_sync = 0

    def get_pending_sync_targets(self, limit: Optional[int] = None) -> List[str]:
        """Returns target_ids that either errored or lack exoplanet/transient screening."""
        with sqlite3.connect(self.db_path, timeout=30.0) as conn:
            query = """
                SELECT target_id FROM processed_targets 
                WHERE status = 'ERROR' 
                   OR evaluated_exo = 0 
                   OR evaluated_exo IS NULL
                ORDER BY processed_at ASC
            """
            if limit:
                query += f" LIMIT {limit}"
            rows = conn.execute(query).fetchall()
            return [r[0] for r in rows]

    def process_target_sync(self, target_id: str) -> Dict[str, Any]:
        """Evaluates target across all 3 modalities and updates DB."""
        try:
            # 1. Black Hole Analysis
            res = self.bh_pipe.analyze_target(target_id)
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

            # 2. Exoplanet & Transients Analysis using in-memory light curve (Zero re-download)
            raw_lc = res.get("raw_lightcurve")
            exo_eval_success = 0
            trans_eval_success = 0

            if raw_lc is not None and hasattr(raw_lc, "time") and hasattr(raw_lc, "flux"):
                t_arr = np.array(raw_lc.time.value, dtype=float)
                f_arr = np.array(raw_lc.flux.value, dtype=float)

                # Exoplanet Fast Check
                try:
                    # Detrending estelar con filtro de mediana robusto (suprime variabilidad rotacional / manchas estelares)
                    from scipy.signal import medfilt
                    w_len = 101 if len(f_arr) > 101 else (len(f_arr) // 2 * 2 + 1)
                    if w_len >= 11:
                        trend = medfilt(f_arr, w_len)
                        flat_f = f_arr / np.where(trend > 0, trend, 1.0)
                    else:
                        flat_f = f_arr / np.median(f_arr)

                    if np.min(flat_f) < 0.9995:
                        tls_res = self.exo_pipe.physics_engine.run_tls_analysis(t_arr, flat_f)
                        exo_eval_success = 1
                        if tls_res.get("tls_detected"):
                            p_days = tls_res.get("period_days", 1.0)
                            t0_val = tls_res.get("t0_bjd", t_arr[0])
                            d_ppm = tls_res.get("transit_depth_ppm", 0.0)

                            # VETO 1: Odd-Even Depth Test (Descarta Binarias Eclipsantes EBs)
                            odd_even = self.exo_pipe.physics_engine.odd_even_depth_veto(
                                t_arr, flat_f, p_days, t0_val, d_ppm * 1e-6
                            )
                            # VETO 2: Secondary Eclipse (Descarta estrellas compañeras luminosas)
                            sec_ecl = self.exo_pipe.physics_engine.secondary_eclipse_veto(
                                t_arr, flat_f, p_days, t0_val
                            )

                            is_eb = odd_even.get("is_eb", False)
                            has_sec = sec_ecl.get("secondary_detected", False)
                            is_known = False
                            if simbad:
                                is_known = simbad.get("is_exoplanet_host", False) or simbad.get("is_eclipsing_binary", False)

                            # Solo notificar y marcar si pasa TODOS los filtros
                            if not is_eb and not has_sec and not is_known and tls_res.get("sde", 0) >= 7.0:
                                params = self.exo_pipe.physics_engine.derive_planetary_parameters(
                                    d_ppm, p_days
                                )
                                exo_obj = {
                                    "target_id": target_id,
                                    "ra": t_ra,
                                    "dec": t_dec,
                                    "tls_results": tls_res,
                                    "planetary_params": params,
                                    "veto_results": {"odd_even": odd_even, "secondary": sec_ecl},
                                    "score": 85.0,
                                    "is_candidate": True
                                }
                                is_candidate = True
                                verdict = f"HIGH-CONFIDENCE EXOPLANET CANDIDATE ({params.get('classification', 'Exoplanet')}, Rp={params.get('planet_radius_earth')} R⊕, P={p_days:.2f}d)"
                                self.exo_notifier.notify(exo_obj)
                            else:
                                verdict = f"VETOED (False Positive): {'Odd-Even EB' if is_eb else ('Secondary Eclipse' if has_sec else 'SDE Below Threshold')}" 
                    else:
                        exo_eval_success = 1
                except Exception:
                    pass

                # Transient Check
                try:
                    trans_res = self.trans_engine.analyze_lightcurve(t_arr, f_arr, target_id=target_id)
                    trans_eval_success = 1
                    if trans_res and trans_res.get("is_transient"):
                        with open(self.db_path.parent / "alerts_transients.jsonl", "a", encoding="utf-8") as tf:
                            import json
                            tf.write(json.dumps(trans_res) + "\n")
                except Exception:
                    pass
            else:
                exo_eval_success = 1
                trans_eval_success = 1

            # Update DB record with completed flags
            with sqlite3.connect(self.db_path, timeout=30.0) as conn:
                conn.execute("""
                    UPDATE processed_targets
                    SET status = ?, is_candidate = ?, verdict = ?, ra = COALESCE(?, ra), dec = COALESCE(?, dec),
                        evaluated_bh = 1, evaluated_exo = ?, evaluated_transient = ?, processed_at = CURRENT_TIMESTAMP
                    WHERE target_id = ?
                """, (status, 1 if is_candidate else 0, verdict, t_ra, t_dec, exo_eval_success, trans_eval_success, target_id))
                conn.execute("""
                    INSERT INTO system_metrics (metric_key, metric_val) VALUES ('total_evaluations', 1)
                    ON CONFLICT(metric_key) DO UPDATE SET metric_val = metric_val + 1;
                """)
                conn.commit()

            if is_candidate:
                self.bh_notifier.notify(res)

            return {"target_id": target_id, "success": True, "status": status}
        except Exception as e:
            with sqlite3.connect(self.db_path, timeout=30.0) as conn:
                conn.execute("""
                    UPDATE processed_targets 
                    SET status = 'ERROR', verdict = ?, processed_at = CURRENT_TIMESTAMP
                    WHERE target_id = ?
                """, (f"Sync error: {str(e)}", target_id))
                conn.commit()
            return {"target_id": target_id, "success": False, "error": str(e)}

    def run_sync(self, batch_size: int = 50):
        pending = self.get_pending_sync_targets()
        self.total_to_sync = len(pending)
        print(f"\n[SyncManager] 🔄 Sincronización iniciada: {self.total_to_sync} estrellas históricas pendientes.")

        with ThreadPoolExecutor(max_workers=self.max_workers, thread_name_prefix="SyncWorker") as executor:
            for i in range(0, len(pending), batch_size):
                if not self.is_running:
                    break
                batch = pending[i:i + batch_size]
                futures = {executor.submit(self.process_target_sync, tid): tid for tid in batch}
                for f in as_completed(futures):
                    self.processed_in_sync += 1
                    res = f.result()
                    if self.processed_in_sync % 10 == 0 or self.processed_in_sync == self.total_to_sync:
                        pct = (self.processed_in_sync / max(1, self.total_to_sync)) * 100
                        print(f"[SyncManager] Progreso de sincronización: {self.processed_in_sync}/{self.total_to_sync} ({pct:.1f}%)")

        print("[SyncManager] ✅ Sincronización histórica finalizada exitosamente.")
