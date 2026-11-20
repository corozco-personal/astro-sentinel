"""
Detector Box Least Squares (BLS) para Eclipses Gravitatorios de Discos y Tránsitos (Kovács et al. 2002).
Detecta tránsitos periódicos de perfil cuadrado producidos por discos de acreción circunestelares.
"""
from typing import Dict, Any, Optional
import numpy as np
from astropy.timeseries import BoxLeastSquares
import lightkurve as lk

class BoxLeastSquaresDetector:
    def __init__(self, min_period_days: float = 0.5, max_period_days: float = 30.0, min_snr: float = 12.0):
        self.min_period = min_period_days
        self.max_period = max_period_days
        self.min_snr = min_snr

    def evaluate(self, lc: lk.LightCurve) -> Dict[str, Any]:
        time = np.ascontiguousarray(lc.time.value, dtype=float)
        flux = np.ascontiguousarray(lc.flux.value, dtype=float)

        valid = np.isfinite(time) & np.isfinite(flux)
        time, flux = time[valid], flux[valid]

        if len(time) < 250:
            return {"is_candidate": False, "reason": "Insufficient points for BLS"}

        # Submuestreo para optimizar tiempo de cómputo
        if len(time) > 1200:
            step = len(time) // 1200
            time, flux = time[::step], flux[::step]

        bls = BoxLeastSquares(time, flux)
        durations = np.linspace(0.05, 0.4, 8)
        periods = np.linspace(self.min_period, self.max_period, 400)

        periodogram = bls.power(periods, durations)

        best_idx = np.argmax(periodogram.power)
        best_period = float(periodogram.period[best_idx])
        best_power = float(periodogram.power[best_idx])
        best_duration = float(periodogram.duration[best_idx])
        best_depth = float(periodogram.depth[best_idx])

        median_power = float(np.median(periodogram.power))
        std_power = float(np.std(periodogram.power))
        snr = (best_power - median_power) / (std_power + 1e-9)

        # Criterio para eclipse profundo de disco compacto:
        # Profundidad > 0.03 (3%) y SNR > umbral
        is_candidate = (snr >= self.min_snr and 0.02 <= best_depth <= 0.40)

        return {
            "is_candidate": bool(is_candidate),
            "type": "Box Least Squares (Accretion Disk Eclipse)",
            "snr": float(round(snr, 2)),
            "detected_period_days": float(round(best_period, 4)),
            "transit_duration_days": float(round(best_duration, 3)),
            "eclipse_depth_fraction": float(round(best_depth, 4))
        }
