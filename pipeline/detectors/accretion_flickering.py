"""
Detector de Acreción Turbulenta & Ruido Rojo (Uttley et al. 2005, Heil et al. 2012).
Evalúa la relación universal lineal RMS-Flujo en discos de acreción alrededor de objetos compactos.
"""
from typing import Dict, Any
import numpy as np
import lightkurve as lk

class AccretionFlickeringDetector:
    def __init__(self, min_corr: float = 0.65, min_variability_ratio: float = 0.015):
        self.min_corr = min_corr
        self.min_var = min_variability_ratio

    def evaluate(self, lc: lk.LightCurve) -> Dict[str, Any]:
        """
        Segmenta la curva de luz en ventanas temporales para probar la relación RMS-Flujo:
        std(F_bin) = k * mean(F_bin) + C
        En estrellas comunes o ruido blanco, RMS es constante. En acreción de agujeros negros, es estrictamente lineal.
        """
        time = np.ascontiguousarray(lc.time.value, dtype=float)
        flux = np.ascontiguousarray(lc.flux.value, dtype=float)

        valid = np.isfinite(time) & np.isfinite(flux)
        time, flux = time[valid], flux[valid]

        if len(time) < 300:
            return {"is_candidate": False, "reason": "Insufficient points for RMS-Flux test"}

        # Dividir en segmentos de ~0.5 días
        chunk_size = 50
        n_chunks = len(time) // chunk_size
        if n_chunks < 6:
            return {"is_candidate": False, "reason": "Insufficient time chunks"}

        mean_fluxes = []
        rms_fluxes = []

        for i in range(n_chunks):
            sub_flux = flux[i * chunk_size : (i + 1) * chunk_size]
            mean_fluxes.append(np.mean(sub_flux))
            rms_fluxes.append(np.std(sub_flux))

        mean_fluxes = np.array(mean_fluxes)
        rms_fluxes = np.array(rms_fluxes)

        # Correlación lineal de Pearson entre Flujo Medio y Variabilidad RMS
        if np.std(mean_fluxes) == 0 or np.std(rms_fluxes) == 0:
            return {"is_candidate": False, "reason": "Zero variance in time bins"}

        corr = np.corrcoef(mean_fluxes, rms_fluxes)[0, 1]
        var_amplitude = float(np.mean(rms_fluxes) / (np.mean(mean_fluxes) + 1e-9))

        # Criterio: Correlación lineal fuerte (RMS-Flux relation) y variabilidad apreciable
        is_candidate = (corr >= self.min_corr and var_amplitude >= self.min_var)

        return {
            "is_candidate": bool(is_candidate),
            "type": "Accretion Flickering & RMS-Flux Relation",
            "rms_flux_correlation": float(corr if not np.isnan(corr) else 0.0),
            "fractional_variability_rms": float(var_amplitude),
            "chunks_analyzed": int(n_chunks)
        }
