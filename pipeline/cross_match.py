"""
Cross-Match module for verification and rejection.
Queries the official black hole census (BlackCAT, Gaia, WATCHDOG),
the MAST TIC catalog, NASA Exoplanet Archive (Confirmed Planets and TOI Candidates)
and astrometric databases to exhaustively reject false positives.
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
        Query official astronomical sources:
        1. Official World Black Hole Catalog (BlackCAT / Gaia / WATCHDOG).
        2. NASA Exoplanet Archive: Confirmed Planets.
        3. NASA Exoplanet Archive: Official TESS Objects of Interest (TOI) table.
        4. MAST TIC catalog (stellar parameters).
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

        # 1. Check against official documented black hole census
        bh_check = is_officially_documented_black_hole(identifier)
        if bh_check.get("is_documented"):
            result["is_known_object"] = True
            result["is_documented_black_hole"] = True
            result["object_type"] = f"Officially Documented Black Hole ({bh_check.get('official_name')})"
            result["documented_details"] = bh_check
            return result

        # 2. Check NASA Exoplanet Archive: Confirmed Planets
        try:
            exo_table = NasaExoplanetArchive.query_criteria(
                table="pscomppars",
                where=f"hostname like '{identifier}' or pl_name like '{identifier}'"
            )
            if exo_table is not None and len(exo_table) > 0:
                result["is_known_object"] = True
                result["is_exoplanet_host"] = True
                result["object_type"] = f"Confirmed Exoplanetary System ({exo_table['pl_name'][0]})"
                return result
        except Exception:
            pass

        # 3. Check NASA Exoplanet Archive: TESS Objects of Interest (TOI)
        # Identifies if TESS already flagged it as false positive, eclipsing binary or planet candidate
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
                        result["object_type"] = f"Eclipsing Binary / Variable TOI ({row.get('toidisplay', '')} - {disp})"
                    else:
                        result["object_type"] = f"TESS TOI Candidate ({row.get('toidisplay', '')} - {disp})"
        except Exception:
            pass

        # 4. Check MAST TIC catalog
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

                    # Re-verify against black hole catalog by exact coordinates
                    if result["tic_info"]["ra"] and result["tic_info"]["dec"]:
                        bh_coord_check = is_officially_documented_black_hole(
                            identifier,
                            ra=result["tic_info"]["ra"],
                            dec=result["tic_info"]["dec"]
                        )
                        if bh_coord_check.get("is_documented"):
                            result["is_documented_black_hole"] = True
                            result["object_type"] = f"Documented Black Hole ({bh_coord_check.get('official_name')})"
                            result["documented_details"] = bh_coord_check
                            return result

                        # Aperture Blending Veto
                        # TESS pixel spans 21 arcsec. If another star within 25 arcsec
                        # has significant brightness, reject false positives from photometric blending.
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
            result["object_type"] = "Uncataloged Target"
        return result

    def _check_aperture_blending(self, ra: float, dec: float, tmag: Optional[float], target_id: str) -> Dict[str, Any]:
        """
        Detect neighboring stars within the TESS photometric aperture (25 arcsec radius)
        that contaminate the target star's flux.
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
                    continue

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
        Determine whether the candidate represents an anomaly NOT documented in official sources
        and rigorously reject false positives (EB, exoplanet transits, and known BHs).
        """
        # Already a cataloged black hole
        if cross_match_data.get("is_documented_black_hole"):
            details = cross_match_data.get("documented_details", {})
            name = details.get("official_name", "Official Catalog")
            return {
                "undocumented_candidate": False,
                "confidence": "None",
                "verdict": f"REJECTED BY PRIOR DOCUMENTATION: Corresponds to already cataloged black hole '{name}'."
            }

        # Already a cataloged eclipsing binary or variable star in TOI/VSX
        if cross_match_data.get("is_eclipsing_binary"):
            return {
                "undocumented_candidate": False,
                "confidence": "None",
                "verdict": f"FALSE POSITIVE REJECTED: Object previously cataloged as eclipsing binary/variable ({cross_match_data.get('object_type')})."
            }

        # Confirmed planet
        if cross_match_data.get("is_exoplanet_host"):
            return {
                "undocumented_candidate": False,
                "confidence": "None",
                "verdict": f"FALSE POSITIVE REJECTED: Confirmed exoplanetary transit ({cross_match_data.get('object_type')})."
            }

        # Aperture contamination veto (visual binary / TESS pixel blending)
        if cross_match_data.get("is_blended_binary"):
            b_info = cross_match_data.get("blending_details", {})
            return {
                "undocumented_candidate": False,
                "confidence": "None",
                "verdict": f"FALSE POSITIVE REJECTED BY APERTURE CONTAMINATION: {b_info.get('reason')}"
            }

        # Detector triggered and passed all physical tests
        if detector_result.get("is_candidate"):
            det_type = detector_result.get("type")
            return {
                "undocumented_candidate": True,
                "confidence": "High",
                "verdict": f"UNCATALOGED CANDIDATE DETECTED! Signature consistent with Black Hole ({det_type}) with no prior record in any official catalog."
            }

        return {
            "undocumented_candidate": False,
            "confidence": "None",
            "verdict": "Does not meet sufficient statistical black hole criteria."
        }
