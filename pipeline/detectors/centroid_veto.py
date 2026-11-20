"""
Detector de Desplazamiento de Centroide a Nivel de Píxel (PRF Centroid Shift).
Descarta binarias eclipsantes o variables de fondo dentro de la apertura de 21" de TESS.
"""
from typing import Dict, Any
import numpy as np
import lightkurve as lk

class CentroidVetoFilter:
    def __init__(self, max_allowed_shift_arcsec: float = 4.0):
        self.max_allowed_shift = max_allowed_shift_arcsec

    def evaluate(self, lc: lk.LightCurve) -> Dict[str, Any]:
        """
        Calcula la correlación entre las variaciones de brillo y el desplazamiento del centroide estelar.
        Si la posición del centroide se desplaza al mismo tiempo que el brillo cambia, el evento proviene
        de una estrella de fondo contaminante, no del objetivo central.
        """
        # Comprobar si la curva de luz SPOC contiene momentos de centroide (mom_centr1, mom_centr2)
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

        # Desviación típica del centroide en píxeles TESS (1 píxel = 21 segundos de arco)
        col_med = np.median(col)
        row_med = np.median(row)
        dist_px = np.sqrt((col - col_med)**2 + (row - row_med)**2)
        
        # Desplazamiento en el 95 percentil convertido a arcsec
        shift_95_arcsec = float(np.percentile(dist_px, 95) * 21.0)

        # Correlación entre flujo y distancia al centro
        corr = float(np.corrcoef(flux, dist_px)[0, 1])
        if np.isnan(corr):
            corr = 0.0

        # Si el desplazamiento durante las anomalías excede el umbral y correlaciona con el flujo:
        is_blended = (shift_95_arcsec > self.max_allowed_shift and abs(corr) > 0.45)

        return {
            "has_centroid_data": True,
            "is_blended_background_artifact": bool(is_blended),
            "centroid_shift_arcsec": float(shift_95_arcsec),
            "flux_centroid_correlation": float(corr)
        }
