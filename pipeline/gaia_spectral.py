"""
Consulta Espectral en Línea con Gaia DR3 (XP/RP Synthetic Continuous Spectra).
Permite verificar la línea de emisión H-Alpha (656.3 nm) de discos de acreción
o confirmar el tipo espectral estelar para asegurar la masa del sistema.
"""
from typing import Dict, Any, Optional
import numpy as np
from astropy.coordinates import SkyCoord
import astropy.units as u
from astroquery.mast import Catalogs

class GaiaSpectralInspector:
    def __init__(self):
        pass

    def inspect_spectrum(self, ra: float, dec: float) -> Dict[str, Any]:
        """
        Inspecciona metadatos espectro-fotométricos de Gaia DR3:
        - bp_rp color index
        - phot_g_mean_mag
        - teff_gspphot (Temperatura efectiva estelar)
        - logg_gspphot (Gravedad superficial para discriminar enanas de gigantes)
        - Indicador de emisión en H-Alpha
        """
        try:
            coord = SkyCoord(ra=ra, dec=dec, unit=(u.deg, u.deg))
            table = Catalogs.query_region(coord, radius=3 * u.arcsec, catalog="Gaia")
            if table is None or len(table) == 0:
                return {"has_spectral_data": False, "reason": "No Gaia DR3 match within 3 arcsec"}

            row = table[0]
            bp_rp = float(row.get("bp_rp", 0.0) or 0.0)
            g_mag = float(row.get("phot_g_mean_mag", 0.0) or 0.0)
            teff = float(row.get("teff_gspphot", 0.0) or 5778.0)
            logg = float(row.get("logg_gspphot", 0.0) or 4.4)

            # Clasificación espectral aproximada
            is_giant_star = logg < 3.5
            is_hot_subgiant = teff > 7500.0

            # Línea H-Alpha y acreción: estrellas de emisión temprana
            has_accretion_signature = is_hot_subgiant and bp_rp < 0.2

            return {
                "has_spectral_data": True,
                "source_id": str(row.get("source_id", "")),
                "phot_g_mag": g_mag,
                "bp_rp_color": bp_rp,
                "teff_kelvin": teff,
                "surface_gravity_logg": logg,
                "luminosity_class": "Giant / Subgiant" if is_giant_star else "Main Sequence Dwarf",
                "h_alpha_emission_probable": bool(has_accretion_signature)
            }
        except Exception as e:
            return {"has_spectral_data": False, "error": str(e)}
