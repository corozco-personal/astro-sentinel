"""
3D Kinematic Peculiar Velocity and Supernova Natal Kick Filter (Gaia DR3 Astrometry).
Evaluates whether the system has an anomalous space velocity characteristic of a black hole with natal kick.
"""
from typing import Dict, Any, Optional
import numpy as np

class KinematicKickAnalyzer:
    def __init__(self, runaway_velocity_threshold_km_s: float = 65.0):
        self.threshold = runaway_velocity_threshold_km_s

    def evaluate_kinematics(self, pmra: Optional[float], pmdec: Optional[float], parallax_mas: Optional[float], radial_velocity_km_s: Optional[float] = None) -> Dict[str, Any]:
        """
        Calculate tangential velocity v_tan = 4.74 * (pm / parallax) in km/s:
        If v_tan > 65-100 km/s, the object is a runaway star with a strong natal kick
        from an asymmetric supernova that ejected the black hole at high velocity through the galactic disk.
        """
        if pmra is None or pmdec is None or parallax_mas is None or parallax_mas <= 0.05:
            return {"kinematics_available": False, "reason": "Insufficient parallax or proper motion in Gaia DR3"}

        pm_total = np.sqrt(pmra**2 + pmdec**2)
        dist_pc = 1000.0 / parallax_mas
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
