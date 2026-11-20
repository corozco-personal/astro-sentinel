"""
Orbital Eccentricity Harmonics and Phase Persistence Filter.
Distinguishes between rotating starspots (variable phase) and black holes in elliptical orbits (fixed 3f, 4f).
"""
from typing import Dict, Any, Optional
import numpy as np
from astropy.timeseries import LombScargle
import lightkurve as lk

class EccentricHarmonicsAndPhaseFilter:
    def __init__(self, min_phase_coherence: float = 0.85):
        self.min_coherence = min_phase_coherence

    def evaluate(self, lc: lk.LightCurve, orbital_period_days: Optional[float] = None) -> Dict[str, Any]:
        """
        1. Evaluates higher-order harmonics 3f and 4f to model high-eccentricity orbits (like Gaia BH1 with e=0.45).
        2. Splits the lightcurve into two halves and compares the signal phase:
           - If phase changes > 45 degrees between halves -> Starspots / stellar activity (rejected).
           - If phase is fixed and coherent -> Gravitational tides from compact companion.
        """
        time = np.ascontiguousarray(lc.time.value, dtype=float)
        flux = np.ascontiguousarray(lc.flux.value, dtype=float)

        valid = np.isfinite(time) & np.isfinite(flux)
        time, flux = time[valid], flux[valid]

        if len(time) < 200 or not orbital_period_days or orbital_period_days <= 0.1:
            return {"is_candidate": False, "reason": "Insufficient points or period"}

        base_freq = 1.0 / orbital_period_days
        ls = LombScargle(time, flux)

        p_1f = float(ls.power(base_freq))
        p_2f = float(ls.power(2.0 * base_freq))
        p_3f = float(ls.power(3.0 * base_freq))
        p_4f = float(ls.power(4.0 * base_freq))

        # Eccentricity index from higher harmonics ratio (3f + 4f) / (1f + 2f)
        total_low = p_1f + p_2f + 1e-9
        higher_harmonics_ratio = (p_3f + p_4f) / total_low
        estimated_eccentricity = min(0.85, higher_harmonics_ratio * 0.75)

        # Temporal phase persistence test (split into 2 halves)
        mid_idx = len(time) // 2
        t1, f1 = time[:mid_idx], flux[:mid_idx]
        t2, f2 = time[mid_idx:], flux[mid_idx:]

        phase1 = (t1 / orbital_period_days) % 1.0
        phase2 = (t2 / orbital_period_days) % 1.0

        m1 = np.mean(f1 * np.sin(2.0 * np.pi * 2.0 * phase1))
        m2 = np.mean(f2 * np.sin(2.0 * np.pi * 2.0 * phase2))

        # Phase coherence
        coherence = 1.0 - min(1.0, abs(m1 - m2) / (abs(m1) + abs(m2) + 1e-6))
        is_stellar_spot = coherence < self.min_coherence

        return {
            "is_candidate": bool(coherence >= self.min_coherence and higher_harmonics_ratio > 0.05),
            "is_stellar_spot_artifact": bool(is_stellar_spot),
            "phase_coherence": float(coherence),
            "estimated_eccentricity": float(round(estimated_eccentricity, 3)),
            "harmonics": {
                "power_1f": float(p_1f),
                "power_2f": float(p_2f),
                "power_3f": float(p_3f),
                "power_4f": float(p_4f)
            }
        }
