"""
Multi-Sector Co-registration (Multi-Sector Lightcurve Stitching).
Concatenates multiple TESS sectors to extend the temporal baseline from weeks to months/years,
enabling discovery of intermediate and long-period dormant black holes (Gaia BH1, Gaia BH2).
"""
from typing import Optional, List
import numpy as np
import lightkurve as lk

class MultiSectorStitcher:
    def __init__(self):
        pass

    def stitch_sectors(self, target: str, max_sectors: int = 5) -> Optional[lk.LightCurve]:
        """
        Download all available sectors for a target and concatenate them,
        aligning relative medians to remove instrumental jumps between sectors.
        """
        try:
            search = lk.search_lightcurve(target, author="SPOC")
            if len(search) == 0:
                search = lk.search_lightcurve(target)
            if len(search) == 0:
                return None

            if len(search) == 1:
                return search[0].download().remove_nans().normalize()

            selected_products = search[:max_sectors]
            lc_collection = selected_products.download_all()
            if not lc_collection or len(lc_collection) == 0:
                return None

            # Normalize each sector independently before stitching
            normalized_lcs = []
            for lc in lc_collection:
                clean = lc.remove_nans()
                if len(clean) > 50:
                    normalized_lcs.append(clean.normalize())

            if len(normalized_lcs) == 0:
                return None

            stitched = normalized_lcs[0]
            for next_lc in normalized_lcs[1:]:
                stitched = stitched.append(next_lc)

            return stitched
        except Exception:
            return None
