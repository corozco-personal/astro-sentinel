"""
Filtro Cinemático 3D de Velocidad Peculiar y Empujón Natal de Supernova (Gaia DR3 Astrometry).
Evalúa si el sistema presenta una velocidad espacial anómala propia de un agujero negro con 'natal kick'.
"""
from typing import Dict, Any, Optional
import numpy as np

class KinematicKickAnalyzer:
    def __init__(self, runaway_velocity_threshold_km_s: float = 65.0):
        self.threshold = runaway_velocity_threshold_km_s

    def evaluate_kinematics(self, pmra: Optional[float], pmdec: Optional[float], parallax_mas: Optional[float], radial_velocity_km_s: Optional[float] = None) -> Dict[str, Any]:
        """
        Calcula la velocidad tangencial v_tan = 4.74 * (pm / parallax) en km/s:
        Si v_tan > 65-100 km/s, el objeto es una estrella fugitiva (runaway) con un fuerte impulso natal
        de supernova asimétrica que expulsó al agujero negro a gran velocidad por el disco galáctico.
        """
        if pmra is None or pmdec is None or parallax_mas is None or parallax_mas <= 0.05:
            return {"kinematics_available": False, "reason": "Insufficient parallax or proper motion in Gaia DR3"}

        pm_total = np.sqrt(pmra**2 + pmdec**2)
        # Distancia en parsecs d = 1000 / parallax
        dist_pc = 1000.0 / parallax_mas
        # Velocidad tangencial en km/s (fórmula canónica de astrometría 4.74 * mu * d)
        v_tan_km_s = 4.74047 * pm_total / parallax_mas

        is_runaway = v_tan_km_s >= self.threshold

        return {
            "kinematics_available": True,
            "distance_pc": float(round(dist_pc, 1)),
            "total_proper_motion_mas_yr": float(round(pm_total, 2)),
            "tangential_velocity_km_s": float(round(v_tan_km_s, 1)),
            "is_runaway_natal_kick": bool(is_runaway),
            "supernova_kick_classification": "High-Velocity Runaway Compact Object" if is_runaway else "Standard Galactic Disk Kinematics"
        }
