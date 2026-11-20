"""
Sky Patch Manager
-----------------
Partitions the sky into discrete spatial patches (tessellations) and manages
area-based surveys, retrieving all target stars within a specific cone,
evaluating them in batch, and only persisting the patch record and genuine candidates.
"""

import math
import sqlite3
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
import astropy.units as u
from astropy.coordinates import SkyCoord
from astroquery.mast import Catalogs


class SkyPatchManager:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_patch_tables()

    def _init_patch_tables(self):
        """Initializes tables for spatial patch tracking and candidate associations."""
        with sqlite3.connect(self.db_path, timeout=30.0) as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS surveyed_sky_patches (
                    patch_id TEXT PRIMARY KEY,
                    ra_center REAL NOT NULL,
                    dec_center REAL NOT NULL,
                    radius_deg REAL NOT NULL,
                    stars_evaluated INTEGER DEFAULT 0,
                    candidates_found INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'IN_PROGRESS',
                    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS spatial_candidates (
                    target_id TEXT PRIMARY KEY,
                    patch_id TEXT,
                    ra REAL,
                    dec REAL,
                    tmag REAL,
                    score REAL,
                    verdict TEXT,
                    physical_params TEXT,
                    detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(patch_id) REFERENCES surveyed_sky_patches(patch_id)
                )
            """)
            conn.commit()

    @staticmethod
    def generate_patch_id(ra: float, dec: float, radius: float) -> str:
        sign = "+" if dec >= 0 else "-"
        return f"PATCH_RA{ra:05.1f}_DEC{sign}{abs(dec):04.1f}_R{int(radius*60):03d}m"

    def is_patch_completed(self, patch_id: str) -> bool:
        with sqlite3.connect(self.db_path, timeout=30.0) as conn:
            cur = conn.cursor()
            cur.execute("SELECT 1 FROM surveyed_sky_patches WHERE patch_id = ? AND status IN ('COMPLETED', 'IN_PROGRESS')", (patch_id,))
            return cur.fetchone() is not None

    def get_next_unscanned_patch(self, sector_center_ra: float = 280.0, sector_center_dec: float = -60.0, radius_deg: float = 0.5) -> Tuple[float, float, str]:
        """
        Generates an Archimedean spiral of sky patches around the sector center or galactic plane.
        """
        # Search radially outwards
        ring = 0
        while ring < 50:
            if ring == 0:
                p_id = self.generate_patch_id(sector_center_ra, sector_center_dec, radius_deg)
                if not self.is_patch_completed(p_id):
                    return sector_center_ra, sector_center_dec, p_id
                ring += 1
                continue

            r_offset = ring * radius_deg * 1.5
            n_patches_in_ring = max(6, int(2 * math.pi * ring))
            for i in range(n_patches_in_ring):
                angle = (2 * math.pi * i) / n_patches_in_ring
                ra = (sector_center_ra + (r_offset * math.cos(angle)) / max(0.01, math.cos(math.radians(sector_center_dec)))) % 360.0
                dec = max(-90.0, min(90.0, sector_center_dec + (r_offset * math.sin(angle))))
                p_id = self.generate_patch_id(ra, dec, radius_deg)
                if not self.is_patch_completed(p_id):
                    return ra, dec, p_id
            ring += 1

        return sector_center_ra, sector_center_dec, self.generate_patch_id(sector_center_ra, sector_center_dec, radius_deg)

    def fetch_stars_in_patch(self, ra: float, dec: float, radius_deg: float = 0.5, tmag_limit: float = 13.0) -> List[Dict[str, Any]]:
        """
        Queries all bright stellar targets inside the spatial cone in a single network call.
        """
        coord = SkyCoord(ra=ra, dec=dec, unit=(u.deg, u.deg))
        try:
            results = Catalogs.query_criteria(
                catalog='TIC',
                coordinates=coord,
                radius=radius_deg * u.deg,
                Tmag=[0, tmag_limit]
            )
            stars = []
            for row in results:
                tic_id = str(row['ID']).strip()
                stars.append({
                    "target_id": f"TIC {tic_id}",
                    "tic_id": tic_id,
                    "ra": float(row['ra']),
                    "dec": float(row['dec']),
                    "tmag": float(row['Tmag']) if row['Tmag'] is not None else 12.0,
                    "teff": float(row['Teff']) if 'Teff' in row.colnames and row['Teff'] is not None else 5778.0
                })
            return stars
        except Exception as e:
            print(f"[SkyPatchManager] Error querying TIC cone for ({ra}, {dec}): {e}")
            return []

    def start_patch(self, patch_id: str, ra: float, dec: float, radius_deg: float):
        with sqlite3.connect(self.db_path, timeout=30.0) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO surveyed_sky_patches (patch_id, ra_center, dec_center, radius_deg, status, started_at)
                VALUES (?, ?, ?, ?, 'IN_PROGRESS', CURRENT_TIMESTAMP)
            """, (patch_id, ra, dec, radius_deg))
            conn.commit()

    def record_candidate(self, patch_id: str, target_id: str, ra: float, dec: float, tmag: float, score: float, verdict: str, physical_params: str):
        with sqlite3.connect(self.db_path, timeout=30.0) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO spatial_candidates (target_id, patch_id, ra, dec, tmag, score, verdict, physical_params)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (target_id, patch_id, ra, dec, tmag, score, verdict, physical_params))
            conn.commit()

    def complete_patch(self, patch_id: str, stars_evaluated: int, candidates_found: int):
        with sqlite3.connect(self.db_path, timeout=30.0) as conn:
            conn.execute("""
                UPDATE surveyed_sky_patches 
                SET stars_evaluated = ?, candidates_found = ?, status = 'COMPLETED', completed_at = CURRENT_TIMESTAMP
                WHERE patch_id = ?
            """, (stars_evaluated, candidates_found, patch_id))
            conn.commit()

    def get_surveyed_patches(self) -> List[Dict[str, Any]]:
        with sqlite3.connect(self.db_path, timeout=30.0) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("""
                SELECT patch_id, ra_center, dec_center, radius_deg, stars_evaluated, candidates_found, status, started_at, completed_at
                FROM surveyed_sky_patches
                ORDER BY started_at DESC LIMIT 100
            """)
            return [dict(r) for r in cur.fetchall()]
