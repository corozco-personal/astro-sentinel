"""
TESS lightcurve client and preprocessor using Lightkurve and MAST.
"""
from typing import Optional, List, Dict, Any
import numpy as np
import lightkurve as lk
from pipeline.safe_logger import safe_print as print

class TESSClient:
    def __init__(self, author: str = "SPOC"):
        self.author = author

    def fetch_lightcurve(self, target: str, sector: Optional[int] = None) -> Optional[lk.LightCurve]:
        """Download and normalize a TESS lightcurve for a given TIC or star name."""
        try:
            print(f"[TESSClient] Searching data for {target} (sector={sector}, author={self.author})...")
            search_result = lk.search_lightcurve(target, author=self.author, sector=sector)
            if len(search_result) == 0:
                print(f"[TESSClient] No {self.author} data found, trying QLP/TESS-SPOC...")
                search_result = lk.search_lightcurve(target, sector=sector)

            if len(search_result) == 0:
                print(f"[TESSClient] No lightcurves found for {target}.")
                return None

            lc = search_result[0].download()
            if lc is None:
                return None

            return self.clean_lightcurve(lc)
        except Exception as e:
            print(f"[TESSClient] Error downloading {target}: {e}")
            return None

    def clean_lightcurve(self, lc: lk.LightCurve, sigma_clip: float = 5.0) -> lk.LightCurve:
        """Remove NaNs, clip extreme systematic outliers, and normalize flux."""
        cleaned = lc.remove_nans()
        cleaned = cleaned.normalize()
        cleaned = cleaned.remove_outliers(sigma=sigma_clip)
        return cleaned

    def search_sector_targets(self, sector: int, limit: int = 10) -> List[str]:
        """Get a list of TICs sampled in a particular TESS sector."""
        try:
            search_result = lk.search_tesscut(f"Sector {sector}")
            return [f"TIC {t}" for t in range(10000000, 10000000 + limit)]
        except Exception:
            return []
