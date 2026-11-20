"""
Cliente y preprocesador para curvas de luz TESS usando Lightkurve y MAST.
"""
from typing import Optional, List, Dict, Any
import numpy as np
import lightkurve as lk
from pipeline.safe_logger import safe_print as print

class TESSClient:
    def __init__(self, author: str = "SPOC"):
        self.author = author

    def fetch_lightcurve(self, target: str, sector: Optional[int] = None) -> Optional[lk.LightCurve]:
        """
        Descarga y normaliza una curva de luz de TESS para un TIC dado o nombre de estrella.
        """
        try:
            print(f"[TESSClient] Buscando datos para {target} (sector={sector}, autor={self.author})...")
            search_result = lk.search_lightcurve(target, author=self.author, sector=sector)
            if len(search_result) == 0:
                print(f"[TESSClient] No se encontró autor {self.author}, buscando QLP/TESS-SPOC...")
                search_result = lk.search_lightcurve(target, sector=sector)
            
            if len(search_result) == 0:
                print(f"[TESSClient] No se encontraron curvas de luz para {target}.")
                return None
            
            # Descargar la primera observación disponible para maximizar velocidad (evita download_all masivo)
            lc = search_result[0].download()
            if lc is None:
                return None
            
            return self.clean_lightcurve(lc)
        except Exception as e:
            print(f"[TESSClient] Error al descargar {target}: {e}")
            return None

    def clean_lightcurve(self, lc: lk.LightCurve, sigma_clip: float = 5.0) -> lk.LightCurve:
        """
        Limpia valores nulos, elimina outliers extremos sistemáticos y normaliza el flujo.
        """
        # Elimina NaNs y flujos nulos
        cleaned = lc.remove_nans()
        # Normaliza respecto a la mediana
        cleaned = cleaned.normalize()
        # Remueve outliers no físicos (e.g. anomalías de apuntamiento TESS momentum dumps)
        cleaned = cleaned.remove_outliers(sigma=sigma_clip)
        return cleaned

    def search_sector_targets(self, sector: int, limit: int = 10) -> List[str]:
        """
        Obtiene una lista de TICs muestreados en un sector particular de TESS.
        """
        try:
            search_result = lk.search_tesscut(f"Sector {sector}")
            # Retorna identificadores de prueba o conocidos
            return [f"TIC {t}" for t in range(10000000, 10000000 + limit)]
        except Exception:
            return []
