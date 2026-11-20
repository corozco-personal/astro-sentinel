"""
Solucionador de Equipotenciales de Roche y Factor de Llenado de Lóbulo de Roche (Eggleton 1983).
Determina si la estrella visible roza el lóbulo de Roche transfiriendo masa hacia el agujero negro.
"""
import math
from typing import Dict, Any

class RocheLobeAnalyzer:
    def __init__(self):
        pass

    def calculate_roche_geometry(self, m_primary: float, m_bh: float, period_days: float, r_star_rsun: float) -> Dict[str, Any]:
        """
        Calcula el radio efectivo de Roche mediante la fórmula analítica de Eggleton (1983):
        r_L / a = 0.49 q^(2/3) / [0.6 q^(2/3) + ln(1 + q^(1/3))]
        donde q = M_primary / M_bh
        """
        q = max(0.01, float(m_primary) / max(0.1, float(m_bh)))
        
        # 3ra Ley de Kepler: Semieje mayor 'a' en radios solares (R_sun)
        # a (AU) = [(M_tot) * (P/365.25)^2]^(1/3) -> convertir a R_sun (1 AU = 215 R_sun)
        m_tot = m_primary + m_bh
        a_au = (m_tot * ((period_days / 365.25) ** 2)) ** (1.0 / 3.0)
        a_rsun = a_au * 215.032

        # Fórmula de Eggleton
        q_23 = q ** (2.0 / 3.0)
        q_13 = q ** (1.0 / 3.0)
        r_roche_fraction = (0.49 * q_23) / (0.6 * q_23 + math.log(1.0 + q_13))
        r_roche_rsun = r_roche_fraction * a_rsun

        # Factor de llenado de Roche: f = R_star / R_Roche
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
