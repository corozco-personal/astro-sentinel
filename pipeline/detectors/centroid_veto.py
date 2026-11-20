"""
Pixel-level PRF Centroid Shift detector.
Rejects background eclipsing binaries or variables within the 21" TESS aperture.
"""
from typing import Dict, Any
import numpy as np
import lightkurve as lk

class CentroidVetoFilter:
    def __init__(self, max_allowed_shift_arcsec: float = 4.0):
        self.max_allowed_shift = max_allowed_shift_arcsec

    def evaluate(self, lc: lk.LightCurve) -> Dict[str, Any]:
        """
        Computes the correlation between brightness variations and stellar centroid displacement.
        If the centroid position shifts at the same time brightness changes, the event originates
        from a background contaminating star, not the central target.
        """
        # Check if the SPOC lightcurve contains centroid moments (mom_centr1, mom_centr2)
        has_centroids = hasattr(lc, "centroid_col") and hasattr(lc, "centroid_row")
        if not has_centroids or lc.centroid_col is None or lc.centroid_row is None:
            return {
                "has_centroid_data": False,
                "is_blended_background_artifact": False,
                "centroid_shift_arcsec": 0.0,
                "reason": "No centroid columns in lightcurve product"
            }

        col = np.ascontiguousarray(lc.centroid_col.value, dtype=float)
        row = np.ascontiguousarray(lc.centroid_row.value, dtype=float)
        flux = np.ascontiguousarray(lc.flux.value, dtype=float)

        valid = np.isfinite(col) & np.isfinite(row) & np.isfinite(flux)
        col, row, flux = col[valid], row[valid], flux[valid]

        if len(col) < 100:
            return {"has_centroid_data": False, "is_blended_background_artifact": False}

        # Centroid standard deviation in TESS pixels (1 pixel = 21 arcseconds)
        col_med = np.median(col)
        row_med = np.median(row)
        dist_px = np.sqrt((col - col_med)**2 + (row - row_med)**2)

        # 95th percentile displacement converted to arcsec
        shift_95_arcsec = float(np.percentile(dist_px, 95) * 21.0)

        # Correlation between flux and distance to center
        corr = float(np.corrcoef(flux, dist_px)[0, 1])
        if np.isnan(corr):
            corr = 0.0

        # If displacement during anomalies exceeds threshold and correlates with flux:
        is_blended = (shift_95_arcsec > self.max_allowed_shift and abs(corr) > 0.45)

        return {
            "has_centroid_data": True,
            "is_blended_background_artifact": bool(is_blended),
            "centroid_shift_arcsec": float(shift_95_arcsec),
            "flux_centroid_correlation": float(corr)
        }
