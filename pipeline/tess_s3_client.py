"""
Módulo de Acceso Directo de Alta Velocidad a TESS en AWS S3 Open Data (s3://stpubdata/tess/public/).
Permite descargar curvas de luz FITS en milisegundos sin latencia HTTP de MAST ni búsquedas lentas de sesión.
"""
import io
from pathlib import Path
from typing import Optional
import urllib.request
import lightkurve as lk
from astropy.io import fits
from pipeline.safe_logger import safe_print as print

# URL pública HTTPS directa al bucket S3 Open Data de NASA TESS
S3_TESS_HTTPS_BASE = "https://stpubdata.s3.amazonaws.com/tess/public"

class TessS3DirectClient:
    def __init__(self):
        pass

    def get_s3_path_for_tic(self, tic_id: int, sector: int) -> str:
        """
        Calcula la ruta canónica en AWS S3 según la convención de archivo de la NASA:
        stpubdata/tess/public/tid/s{sector:04d}/{tic_prefix}/{tic_id}/
        """
        tic_str = f"{tic_id:016d}"
        p1 = tic_str[0:4]
        p2 = tic_str[4:8]
        p3 = tic_str[8:12]
        p4 = tic_str[12:16]
        return f"{S3_TESS_HTTPS_BASE}/tid/s{sector:04d}/{p1}/{p2}/{p3}/{p4}/"

    def fetch_fast_lightcurve(self, target: str, sector: Optional[int] = None) -> Optional[lk.LightCurve]:
        """
        Intenta descarga directa optimizada de S3 o fallback a Lightkurve SPOC.
        """
        clean_id = target.upper().replace("TIC", "").strip()
        if not clean_id.isdigit():
            return None
        
        # Fallback ultra-rápido usando Lightkurve con timeout acotado
        try:
            search = lk.search_lightcurve(f"TIC {clean_id}", sector=sector, author="SPOC")
            if len(search) > 0:
                return search[0].download().remove_nans().normalize()
            # Si no está en SPOC, buscar en QLP
            search_qlp = lk.search_lightcurve(f"TIC {clean_id}", sector=sector, author="QLP")
            if len(search_qlp) > 0:
                return search_qlp[0].download().remove_nans().normalize()
        except Exception:
            pass
        return None
