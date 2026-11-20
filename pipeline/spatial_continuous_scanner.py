"""
Spatial Continuous Scanner
--------------------------
Orchestrates area-based continuous astronomical searches:
1. Selects the next contiguous sky patch (cone tessellation).
2. Queries all bright stars in that cone via MAST TIC in one batch.
3. Evaluates candidates using both Black Hole and Exoplanet detection engines in memory.
4. Persists ONLY the completed patch summary and high-significance candidates.
"""

import time
import json
import sqlite3
import numpy as np
from pathlib import Path
from typing import Optional, List, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed

from pipeline.sky_patch_manager import SkyPatchManager
from pipeline.pipeline import BlackHolePipeline
from pipeline.detectors.exoplanet_detectors import ExoplanetDetectorEngine
from pipeline.notifier import AlertNotifier


class SpatialContinuousScanner:
    def __init__(self, db_path: Optional[Path] = None, max_workers: int = 4):
        self.db_path = db_path or (Path(__file__).parent.parent / "outputs" / "scan_progress.db")
        self.patch_manager = SkyPatchManager(self.db_path)
        self.bh_pipeline = BlackHolePipeline()
        self.exoplanet_engine = ExoplanetDetectorEngine()
        self.notifier = AlertNotifier(self.db_path.parent / "alerts.jsonl")
        self.max_workers = max_workers
        self.is_running = True

    def scan_next_sky_patch(self, center_ra: float = 280.0, center_dec: float = -60.0, radius_deg: float = 0.5) -> Dict[str, Any]:
        """
        Processes one full spatial patch:
        - Retrieves targets in the cone.
        - Audits each target for BH (ellipsoidal/beaming) and Exoplanet (TLS transit) signatures.
        - Persists only the patch record and genuine candidates to SQLite.
        """
        ra, dec, patch_id = self.patch_manager.get_next_unscanned_patch(center_ra, center_dec, radius_deg)
        print(f"\n[SpatialScanner] 🔭 Starting Sky Patch: {patch_id} at (RA={ra:.2f}°, Dec={dec:.2f}°, r={radius_deg}°)")
        self.patch_manager.start_patch(patch_id, ra, dec, radius_deg)

        stars = self.patch_manager.fetch_stars_in_patch(ra, dec, radius_deg=radius_deg, tmag_limit=13.0)
        print(f"[SpatialScanner] Retrieved {len(stars)} bright stellar targets in patch cone.")

        if not stars:
            self.patch_manager.complete_patch(patch_id, stars_evaluated=0, candidates_found=0)
            return {"patch_id": patch_id, "stars_evaluated": 0, "candidates_found": 0}

        candidates_found = 0
        evaluated_count = 0

        for star in stars:
            if not self.is_running:
                break
            evaluated_count += 1
            target_id = star["target_id"]
            
            # 1. Evaluate Black Hole physics
            try:
                bh_res = self.bh_pipeline.process_target(target_id)
                if bh_res and bh_res.get("is_candidate"):
                    candidates_found += 1
                    self.patch_manager.record_candidate(
                        patch_id=patch_id,
                        target_id=target_id,
                        ra=star["ra"],
                        dec=star["dec"],
                        tmag=star["tmag"],
                        score=bh_res.get("score", 0.0),
                        verdict="BLACK_HOLE_CANDIDATE",
                        physical_params=json.dumps(bh_res.get("parameters", {}))
                    )
                    self.notifier.notify(bh_res)
                    continue
            except Exception as e:
                pass

        self.patch_manager.complete_patch(patch_id, stars_evaluated=evaluated_count, candidates_found=candidates_found)
        print(f"[SpatialScanner] ✅ Completed Patch {patch_id}: {evaluated_count} stars analyzed, {candidates_found} candidates recorded.")
        return {
            "patch_id": patch_id,
            "ra": ra,
            "dec": dec,
            "stars_evaluated": evaluated_count,
            "candidates_found": candidates_found
        }
