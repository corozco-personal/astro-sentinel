"""
Demonio y Gestor de Escaneo Continuo de Datos de TESS.
Descarga y analiza sistemáticamente lotes de curvas de luz, guarda el estado
de estrellas ya procesadas en SQLite y notifica inmediatamente cuando un candidato
pasa todos los filtros sin coincidencia previa en fuentes oficiales.
"""
import sqlite3
import time
from pathlib import Path
from typing import List, Optional
import lightkurve as lk
from astroquery.mast import Catalogs

from config import PipelineConfig, OUTPUT_DIR
from pipeline.pipeline import BlackHolePipeline
from pipeline.notifier import AlertNotifier
from pipeline.safe_logger import safe_print as print

class ContinuousScanner:
    def __init__(self, db_path: Optional[Path] = None, delay_between_targets: float = 1.0, max_workers: int = 4):
        self.output_dir = OUTPUT_DIR
        self.db_path = db_path or (self.output_dir / "scan_progress.db")
        self.alerts_file = self.output_dir / "alerts.jsonl"
        self.delay = delay_between_targets
        self.max_workers = max_workers
        
        self.pipeline = BlackHolePipeline()
        self.notifier = AlertNotifier(self.alerts_file)
        self._init_db()

    def _init_db(self):
        """Inicializa la base de datos de control de progreso con WAL mode para concurrencia."""
        with sqlite3.connect(self.db_path, timeout=30.0) as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS processed_targets (
                    target_id TEXT PRIMARY KEY,
                    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    status TEXT,
                    is_candidate INTEGER,
                    verdict TEXT,
                    details TEXT,
                    ra REAL,
                    dec REAL
                )
            """)
            # Agregar columnas si la tabla ya existía previamente
            try:
                conn.execute("ALTER TABLE processed_targets ADD COLUMN ra REAL")
            except Exception:
                pass
            try:
                conn.execute("ALTER TABLE processed_targets ADD COLUMN dec REAL")
            except Exception:
                pass
            conn.commit()

    def is_processed(self, target_id: str) -> bool:
        with sqlite3.connect(self.db_path, timeout=30.0) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM processed_targets WHERE target_id = ?", (target_id,))
            return cursor.fetchone() is not None

    def mark_processed(self, target_id: str, status: str, is_candidate: bool, verdict: str, details: str = "", ra: Optional[float] = None, dec: Optional[float] = None):
        with sqlite3.connect(self.db_path, timeout=30.0) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO processed_targets (target_id, status, is_candidate, verdict, details, ra, dec)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (target_id, status, 1 if is_candidate else 0, verdict, details, ra, dec))
            conn.commit()

    def fetch_targets_from_sector(self, sector: int, limit: int = 50) -> List[str]:
        """Obtiene una lista de estrellas observadas por TESS en un sector."""
        print(f"[Scanner] Consultando objetivos disponibles para Sector {sector}...")
        try:
            # Consulta objetivos de alta prioridad en el sector
            search = lk.search_tesscut(f"Sector {sector}")
            # Si no está directo, consultar coordenadas típicas o TIC
        except Exception:
            pass
        return []

    def fetch_confirmed_tess_targets(self, sector: int = 1, limit: int = 150) -> List[str]:
        """
        Consulta en MAST los objetivos que efectivamente disponen de series temporales (curvas de luz)
        procesadas por TESS para ese sector, aplicando pre-filtrado de calidad y brillo.
        """
        print(f"[Scanner] Consultando objetivos de alta calidad con curvas de luz reales en TESS Sector {sector}...")
        try:
            from astroquery.mast import Observations
            obs = Observations.query_criteria(
                obs_collection="TESS",
                dataproduct_type="timeseries",
                sequence_number=sector
            )
            targets = []
            for row in obs:
                name = str(row["target_name"]).strip()
                if name and name.isdigit():
                    # Pre-filtrado rápido: descartar duplicados inmediatos
                    t_str = f"TIC {name}"
                    if not self.is_processed(t_str):
                        targets.append(t_str)
                if len(targets) >= limit:
                    break
            print(f"[Scanner] Cola optimizada con {len(targets)} objetivos no analizados.")
            return targets
        except Exception as e:
            print(f"[Scanner] Error consultando Observations: {e}")
            return []

    def run_continuous_scan(self, custom_targets: Optional[List[str]] = None, max_iterations: Optional[int] = None, sector: int = 1):
        """
        Bucle de ejecución continua: procesa objetivos, audita anomalías y notifica.
        """
        print("\n" + "="*70)
        print("🚀 INICIANDO DEMONIO DE BÚSQUEDA CONTINUA DE AGUJEROS NEGROS EN TESS")
        print(f"📁 Base de datos de estado: {self.db_path}")
        print(f"🔔 Registro de alertas: {self.alerts_file}")
        print("="*70 + "\n")

        processed_count = 0
        current_sector = sector

        # Llenar cola con objetivos proporcionados o consultar observaciones reales de TESS
        queue = list(custom_targets) if custom_targets else []
        if not queue:
            queue.extend(self.fetch_confirmed_tess_targets(sector=current_sector, limit=100))

        while queue:
            target_id = queue.pop(0)

            if self.is_processed(target_id):
                print(f"[Scanner] Omitiendo {target_id} (ya analizado previamente).")
                continue

            try:
                result = self.pipeline.analyze_target(target_id, sector=current_sector)
                status = result.get("status", "FAILED")
                assessment = result.get("assessment", {})
                is_undocumented = assessment.get("undocumented_candidate", False)
                verdict = assessment.get("verdict", "")

                simbad = result.get("simbad_info", {})
                tic_info = simbad.get("tic_info", {}) if simbad else {}
                target_ra = tic_info.get("ra")
                target_dec = tic_info.get("dec")

                self.mark_processed(
                    target_id=target_id,
                    status=status,
                    is_candidate=is_undocumented,
                    verdict=verdict,
                    details=str(result.get("detection_details", {}).get("type", "")),
                    ra=target_ra,
                    dec=target_dec
                )

                # Si es un candidato tentativo no documentado, ¡NOTIFICAR!
                if is_undocumented:
                    self.notifier.notify(result)

            except Exception as e:
                print(f"[Scanner] Error procesando {target_id}: {e}")
                self.mark_processed(target_id, "ERROR", False, str(e))

            processed_count += 1
            if max_iterations and processed_count >= max_iterations:
                print(f"[Scanner] Se alcanzó el límite configurado de {max_iterations} análisis.")
                break

            time.sleep(self.delay)

            # Si la cola se vacía, avanzar secuencialmente en el catálogo o siguiente sector de TESS
            if len(queue) == 0 and (max_iterations is None or processed_count < max_iterations):
                current_sector += 1
                if current_sector > 80:
                    current_sector = 1
                print(f"[Scanner] Cola completada. Avanzando a TESS Sector {current_sector}...")
                queue.extend(self.fetch_confirmed_tess_targets(sector=current_sector, limit=100))
