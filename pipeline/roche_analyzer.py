"""
Roche Equipotential Solver and Roche Lobe Filling Factor (Eggleton 1983).
Determines whether the visible star overflows its Roche lobe, transferring mass to the black hole.
"""
import math
from typing import Dict, Any

class RocheLobeAnalyzer:
    def __init__(self):
        pass

    def calculate_roche_geometry(self, m_primary: float, m_bh: float, period_days: float, r_star_rsun: float) -> Dict[str, Any]:
        """
        Calculate effective Roche radius using the Eggleton (1983) analytical formula:
        r_L / a = 0.49 q^(2/3) / [0.6 q^(2/3) + ln(1 + q^(1/3))]
        where q = M_primary / M_bh
        """
        q = max(0.01, float(m_primary) / max(0.1, float(m_bh)))

        # Kepler's 3rd Law: Semi-major axis 'a' in solar radii (R_sun)
        m_tot = m_primary + m_bh
        a_au = (m_tot * ((period_days / 365.25) ** 2)) ** (1.0 / 3.0)
        a_rsun = a_au * 215.032

        # Eggleton formula
        q_23 = q ** (2.0 / 3.0)
        q_13 = q ** (1.0 / 3.0)
        r_roche_fraction = (0.49 * q_23) / (0.6 * q_23 + math.log(1.0 + q_13))
        r_roche_rsun = r_roche_fraction * a_rsun

        # Roche filling factor: f = R_star / R_Roche
        filling_factor = float(r_star_rsun) / max(0.1, r_roche_rsun)
        is_overflowing = filling_factor >= 1.0
        is_detached = filling_factor < 0.8

        classification = "Roche-Lobe Overflow (Active Accretion)" if is_overflowing else (
            "Near-Contact Binary" if filling_factor >= 0.8 else "Detached Binary"
        )

        return {
            "semi_major_axis_rsun": float(round(a_rsun, 2)),
            "roche_lobe_radius_rsun": float(round(r_roche_rsun, 2)),
            "filling_factor": float(round(filling_factor, 3)),
            "binary_state": classification,
            "is_overflowing": bool(is_overflowing)
        }
