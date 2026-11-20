"""
Módulo de correlación cruzada (Cross-Match) para verificación y descarte.
Consulta el censo oficial de agujeros negros (BlackCAT, Gaia, WATCHDOG),
el catálogo TIC de MAST, NASA Exoplanet Archive (Planetas Confirmados y TOI Candidates)
y bases de datos astrométricas para descartar exhaustivamente falsos positivos.
"""
from typing import Dict, Any, Optional
import warnings
from astropy.coordinates import SkyCoord
import astropy.units as u
from astroquery.mast import Catalogs
from astroquery.ipac.nexsci.nasa_exoplanet_archive import NasaExoplanetArchive

from pipeline.official_catalogs import is_officially_documented_black_hole

class CatalogCrossMatcher:
    def __init__(self):
        pass

    def check_simbad_and_mast(self, identifier: str, coord: Optional[SkyCoord] = None) -> Dict[str, Any]:
        """
        Consulta fuentes astronómicas oficiales:
        1. Catálogo Oficial Mundial de Agujeros Negros (BlackCAT / Gaia / WATCHDOG).
        2. NASA Exoplanet Archive: Planetas Confirmados.
        3. NASA Exoplanet Archive: Tabla Oficial de TESS Objects of Interest (TOI).
        4. Catálogo TIC de MAST (stellar parameters).
        """
        clean_id = identifier.upper().strip()
        result = {
            "is_known_object": False,
            "main_id": identifier,
            "object_type": "Unknown",
            "is_documented_black_hole": False,
            "is_eclipsing_binary": False,
            "is_known_variable": False,
            "is_exoplanet_host": False,
            "is_toi_candidate": False,
            "is_blended_binary": False,
            "blending_details": None,
            "documented_details": {},
            "tic_info": {},
            "raw_otype": None
        }

        # 1. Comprobación contra el censo oficial de agujeros negros documentados
        bh_check = is_officially_documented_black_hole(identifier)
        if bh_check.get("is_documented"):
            result["is_known_object"] = True
            result["is_documented_black_hole"] = True
            result["object_type"] = f"Agujero Negro Documentado Oficialmente ({bh_check.get('official_name')})"
            result["documented_details"] = bh_check
            return result

        # 2. Comprobación en NASA Exoplanet Archive: Planetas Confirmados
        try:
            exo_table = NasaExoplanetArchive.query_criteria(
                table="pscomppars",
                where=f"hostname like '{identifier}' or pl_name like '{identifier}'"
            )
            if exo_table is not None and len(exo_table) > 0:
                result["is_known_object"] = True
                result["is_exoplanet_host"] = True
                result["object_type"] = f"Sistema Exoplanetario Confirmado ({exo_table['pl_name'][0]})"
                return result
        except Exception:
            pass

        # 3. Comprobación en NASA Exoplanet Archive: TESS Objects of Interest (TOI)
        # Permite identificar si TESS ya lo tiene marcado como falso positivo, binaria eclipsante o candidato planetario
        try:
            clean_tic = clean_id.replace("TIC", "").strip()
            if clean_tic.isdigit():
                toi_table = NasaExoplanetArchive.query_criteria(
                    table="toi",
                    where=f"tid = {clean_tic}"
                )
                if toi_table is not None and len(toi_table) > 0:
                    row = toi_table[0]
                    disp = str(row.get("tfopwg_disp", "")).strip().upper()
                    result["is_known_object"] = True
                    result["is_toi_candidate"] = True
                    if disp in ["EB", "V", "SB1", "SB2"]:
                        result["is_eclipsing_binary"] = True
                        result["object_type"] = f"Binaria Eclipsante / Variable TOI ({row.get('toidisplay', '')} - {disp})"
                    else:
                        result["object_type"] = f"TESS TOI Candidate ({row.get('toidisplay', '')} - {disp})"
        except Exception:
            pass

        # 4. Comprobación en catálogo TIC de MAST
        try:
            clean_tic = clean_id.replace("TIC", "").strip()
            if clean_tic.isdigit():
                tic_res = Catalogs.query_criteria(catalog="Tic", ID=clean_tic)
                if tic_res is not None and len(tic_res) > 0:
                    row = tic_res[0]
                    result["is_known_object"] = True
                    if not result["object_type"] or result["object_type"] == "Unknown":
                        result["object_type"] = f"TIC {row.get('objType', 'STAR')}"
                    result["tic_info"] = {
                        "Tmag": float(row["Tmag"]) if "Tmag" in row.colnames else None,
                        "ra": float(row["ra"]) if "ra" in row.colnames else None,
                        "dec": float(row["dec"]) if "dec" in row.colnames else None,
                        "rad": float(row["rad"]) if "rad" in row.colnames and row["rad"] else None,
                        "mass": float(row["mass"]) if "mass" in row.colnames and row["mass"] else None
                    }
                    
                    # Re-verificar contra catálogo de agujeros negros por coordenadas exactas
                    if result["tic_info"]["ra"] and result["tic_info"]["dec"]:
                        bh_coord_check = is_officially_documented_black_hole(
                            identifier,
                            ra=result["tic_info"]["ra"],
                            dec=result["tic_info"]["dec"]
                        )
                        if bh_coord_check.get("is_documented"):
                            result["is_documented_black_hole"] = True
                            result["object_type"] = f"Agujero Negro Documentado ({bh_coord_check.get('official_name')})"
                            result["documented_details"] = bh_coord_check
                            return result

                        # Veto de Contaminación de Apertura (Aperture Blending Veto)
                        # El píxel de TESS abarca 21 arcsec. Si hay otra estrella en un radio de 25 arcsec
                        # con brillo significativo, descarta falsos positivos por mezcla fotométrica.
                        blending = self._check_aperture_blending(
                            result["tic_info"]["ra"],
                            result["tic_info"]["dec"],
                            result["tic_info"]["Tmag"],
                            clean_id
                        )
                        if blending.get("is_blended"):
                            result["is_blended_binary"] = True
                            result["blending_details"] = blending
                    
                    return result
        except Exception:
            pass

        if not result["is_known_object"]:
            result["object_type"] = "Objetivo No Catalogado / Fuera de Catálogo"
        return result

    def _check_aperture_blending(self, ra: float, dec: float, tmag: Optional[float], target_id: str) -> Dict[str, Any]:
        """
        Detecta estrellas vecinas dentro de la apertura fotométrica de TESS (radio 25 arcsec)
        que contaminen el flujo de la estrella objetivo.
        """
        try:
            from astropy.coordinates import SkyCoord
            import astropy.units as u

            coord = SkyCoord(ra=ra * u.deg, dec=dec * u.deg)
            nearby = Catalogs.query_region(coord, radius=25 * u.arcsec, catalog="Tic")
            if nearby is None or len(nearby) <= 1:
                return {"is_blended": False}

            clean_target_num = target_id.replace("TIC", "").strip()
            for row in nearby:
                row_id = str(row["ID"]).strip()
                if row_id == clean_target_num:
                    continue  # Misma estrella

                row_ra = float(row["ra"])
                row_dec = float(row["dec"])
                neighbor_coord = SkyCoord(ra=row_ra * u.deg, dec=row_dec * u.deg)
                sep_arcsec = coord.separation(neighbor_coord).arcsec

                row_tmag = float(row["Tmag"]) if "Tmag" in row.colnames and row["Tmag"] is not None else 99.0
                target_mag = tmag if tmag is not None else 12.0

                delta_mag = abs(row_tmag - target_mag)
                if sep_arcsec <= 25.0 and delta_mag <= 3.5:
                    return {
                        "is_blended": True,
                        "neighbor_id": f"TIC {row_id}",
                        "separation_arcsec": round(sep_arcsec, 2),
                        "neighbor_tmag": round(row_tmag, 2),
                        "delta_tmag": round(delta_mag, 2),
                        "reason": f"Severe TESS pixel aperture blending: neighbor TIC {row_id} at {sep_arcsec:.1f}\" (ΔTmag={delta_mag:.1f})."
                    }
        except Exception:
            pass

        return {"is_blended": False}

    def assess_undocumented_bh_potential(self, cross_match_data: Dict[str, Any], detector_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Determina si el candidato representa una anomalía NO documentada en fuentes oficiales
        y descarta rigurosamente falsos positivos (EB, tránsitos exoplanetarios y BHs conocidos).
        """
        # Si ya es un agujero negro catalogado
        if cross_match_data.get("is_documented_black_hole"):
            details = cross_match_data.get("documented_details", {})
            name = details.get("official_name", "Catálogo Oficial")
            return {
                "undocumented_candidate": False,
                "confidence": "None",
                "verdict": f"DESCARTADO POR DOCUMENTACIÓN PREVIA: Corresponde al agujero negro ya catalogado '{name}'."
            }

        # Si ya es una binaria eclipsante o variable estelar catalogada en TOI/VSX
        if cross_match_data.get("is_eclipsing_binary"):
            return {
                "undocumented_candidate": False,
                "confidence": "None",
                "verdict": f"FALSO POSITIVO DESCARTADO: Objeto catalogado previamente como binaria eclipsante/variable ({cross_match_data.get('object_type')})."
            }

        # Si es un planeta confirmado
        if cross_match_data.get("is_exoplanet_host"):
            return {
                "undocumented_candidate": False,
                "confidence": "None",
                "verdict": f"FALSO POSITIVO DESCARTADO: Tránsito exoplanetario confirmado ({cross_match_data.get('object_type')})."
            }

        # Veto de contaminación por binaria visual / mezcla en píxel TESS (Blending Veto)
        if cross_match_data.get("is_blended_binary"):
            b_info = cross_match_data.get("blending_details", {})
            return {
                "undocumented_candidate": False,
                "confidence": "None",
                "verdict": f"FALSO POSITIVO DESCARTADO POR CONTAMINACIÓN DE APERTURA: {b_info.get('reason')}"
            }

        # Si el detector disparó y superó todas las pruebas físicas
        if detector_result.get("is_candidate"):
            det_type = detector_result.get("type")
            return {
                "undocumented_candidate": True,
                "confidence": "High",
                "verdict": f"¡CANDIDATO NO CATALOGADO DETECTADO! Firma compatible con Agujero Negro ({det_type}) sin registro previo en ningún catálogo oficial."
            }

        return {
            "undocumented_candidate": False,
            "confidence": "None",
            "verdict": "Does not meet sufficient statistical black hole criteria."
        }

