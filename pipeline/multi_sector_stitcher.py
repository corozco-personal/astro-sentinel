"""
Módulo de Co-registro Multi-Sector (Multi-Sector Lightcurve Stitching).
Concatena múltiples sectores TESS para extender la línea base temporal de semanas a meses/años,
permitiendo descubrir agujeros negros durmientes de período intermedio y largo (Gaia BH1, Gaia BH2).
"""
from typing import Optional, List
import numpy as np
import lightkurve as lk

class MultiSectorStitcher:
    def __init__(self):
        pass

    def stitch_sectors(self, target: str, max_sectors: int = 5) -> Optional[lk.LightCurve]:
        """
        Descarga todos los sectores disponibles para un objetivo y los concatena
        alineando medianas relativas para eliminar saltos instrumentales entre sectores.
        """
        try:
            search = lk.search_lightcurve(target, author="SPOC")
            if len(search) == 0:
                search = lk.search_lightcurve(target)
            if len(search) == 0:
                return None

            # Si solo hay 1 sector, descargar directamente
            if len(search) == 1:
                return search[0].download().remove_nans().normalize()

            # Descargar hasta max_sectors
            selected_products = search[:max_sectors]
            lc_collection = selected_products.download_all()
            if not lc_collection or len(lc_collection) == 0:
                return None

            # Normalizar cada sector independientemente antes de coser
            normalized_lcs = []
            for lc in lc_collection:
                clean = lc.remove_nans()
                if len(clean) > 50:
                    normalized_lcs.append(clean.normalize())

            if len(normalized_lcs) == 0:
                return None

            # Concatenar en una sola curva continua
            stitched = normalized_lcs[0]
            for next_lc in normalized_lcs[1:]:
                stitched = stitched.append(next_lc)

            return stitched
        except Exception:
            return None
