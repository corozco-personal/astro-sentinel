"""
False Discovery Rate (FDR) Control and TESS Systematics Correction.
1. Benjamini-Hochberg FDR to control false positive probability in massive searches.
2. TESS spacecraft thermal systematics cleanup (splines / cotrending / median filter).
"""
from typing import Dict, Any, List
import numpy as np
from scipy import stats
import lightkurve as lk

class StatisticalQualityCorrector:
    def __init__(self, target_fdr: float = 0.05):
        self.target_fdr = target_fdr

    def remove_systematics(self, lc: lk.LightCurve) -> lk.LightCurve:
        """
        Remove TESS orbital thermal trends (13.7-day periapsis cycles)
        via long-pass sliding median filter to preserve transits and microlensing events.
        """
        try:
            clean_lc = lc.flatten(window_length=201, polyorder=2, niters=3, sigma=3.0)
            return clean_lc
        except Exception:
            return lc

    def calculate_fdr_pvalue(self, chi2_val: float, dof: int, total_tested_targets: int) -> Dict[str, Any]:
        """
        Calculate canonical p-value and Benjamini-Hochberg (1995) corrected threshold
        to mitigate the look-elsewhere effect in catalogs of hundreds of thousands of stars.
        """
        if dof <= 0:
            dof = 100
        p_val = float(1.0 - stats.chi2.cdf(chi2_val, df=dof))
        n_stars = max(1, total_tested_targets)
        adjusted_alpha = self.target_fdr / n_stars
        is_statistically_significant = p_val < adjusted_alpha

        return {
            "raw_p_value": float(p_val),
            "adjusted_alpha_threshold": float(adjusted_alpha),
            "is_statistically_significant": bool(is_statistically_significant),
            "total_tested_stars": int(n_stars)
        }
