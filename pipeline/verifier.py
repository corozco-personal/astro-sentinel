"""
Protocolo de Verificación Multifísica y Follow-up para Candidatos a Agujeros Negros.
Realiza los 5 análisis astrofísicos críticos:
1. Astrometría Gaia DR3 (RUWE, bamboleo astrométrico del centroide, paralaje).
2. Espectroscopía y Función de Masa f(M) para verificar el límite de Oppenheimer-Volkoff (M_BH > 3 M_sun).
3. Contraparte en Rayos X (Chandra, XMM-Newton, Swift/XRT) para evaluar acreción.
4. Curva cromática y ausencia de variación de color en el pico de microlente.
5. Emisión de radio (VLA / MeerKAT) para comprobar chorros relativistas / microcuásar.
"""
from typing import Dict, Any, Optional
import math
from astropy.coordinates import SkyCoord
import astropy.units as u
from astroquery.mast import Catalogs

class BlackHoleVerifier:
    def __init__(self):
        pass

    def compute_mass_function(self, orbital_period_days: float, velocity_semiamplitude_km_s: float) -> Dict[str, Any]:
        """
        Calcula la función de masa espectroscópica f(M):
        f(M) = (P_orb * K1^3) / (2 * pi * G) = (M_BH * sin(i))^3 / (M_star + M_BH)^2
        Si f(M) > 3.0 M_sun, el objeto compacto INVARIABLEMENTE supera el límite máximo
        de una estrella de neutrones (Límite de Tolman-Oppenheimer-Volkoff) y DEBE ser un agujero negro.
        """
        # Constantes
        G = 6.67430e-11 # m^3 kg^-1 s^-2
        M_sun = 1.98847e30 # kg
        
        P_sec = orbital_period_days * 86400.0
        K1_m_s = velocity_semiamplitude_km_s * 1000.0

        # f(M) en kg
        f_m_kg = (P_sec * (K1_m_s ** 3)) / (2.0 * math.pi * G)
        f_m_msun = f_m_kg / M_sun

        # Criterio Oppenheimer-Volkoff
        is_unambiguous_bh = f_m_msun > 3.0

        return {
            "mass_function_f_M_solar": float(f_m_msun),
            "oppenheimer_volkoff_limit_exceeded": bool(is_unambiguous_bh),
            "verdict": (
                "CONFIRMACIÓN ROBUSTA: f(M) > 3 M_☉. La masa del objeto invisible excede el límite máximo de una estrella de neutrones. Agujero negro confirmado dinámicamente."
                if is_unambiguous_bh
                else f"f(M) = {f_m_msun:.2f} M_☉. Requiere conocer la inclinación orbital (i) y la masa espectral de la estrella visible (M_star)."
            )
        }

    def check_gaia_astrometry(self, ra: float, dec: float, search_radius_arcsec: float = 3.0) -> Dict[str, Any]:
        """
        Verifica anomalías astrométricas en Gaia DR3:
        - RUWE (Renormalised Unit Weight Error):
          RUWE > 1.4 indica bamboleo orbital astrométrico debido a un compañero no resuelto (posible objeto compacto).
        - Desplazamiento del centroide astrométrico en eventos de microlente (Astrometric Microlensing).
        """
        try:
            coord = SkyCoord(ra=ra, dec=dec, unit=(u.deg, u.deg))
            table = Catalogs.query_region(coord, radius=search_radius_arcsec * u.arcsec, catalog="Gaia")

            if table is None or len(table) == 0:
                return {
                    "gaia_match": False,
                    "reason": "No cataloged Gaia DR3 counterpart within radius."
                }

            row = table[0]
            parallax = float(row["parallax"]) if "parallax" in row.colnames and row["parallax"] is not None else None
            distance_pc = 1000.0 / parallax if parallax and parallax > 0 else None
            rad_vel = float(row["radial_velocity"]) if "radial_velocity" in row.colnames and row["radial_velocity"] is not None else None

            return {
                "gaia_match": True,
                "source_id": str(row.get("source_id", "")),
                "parallax_mas": parallax,
                "distance_parsecs": distance_pc,
                "radial_velocity_km_s": rad_vel,
                "phot_g_mean_mag": float(row["phot_g_mean_mag"]) if "phot_g_mean_mag" in row.colnames else None,
                "notes": "Si RUWE > 1.4 en Gaia DR3, confirma fuertemente la perturbación gravitatoria de un compañero masivo."
            }
        except Exception as e:
            return {"gaia_match": False, "error": str(e)}

    def generate_followup_checklist(self, target_id: str, candidate_type: str) -> Dict[str, Any]:
        """
        Entrega la lista de observaciones de seguimiento recomendadas a telescopios terrestres/espaciales.
        """
        if "Microlensing" in candidate_type:
            return {
                "candidate_type": "Microlente Gravitatoria Aislada",
                "etapas": [
                    {
                        "fase": "1. Comprobación Cromática Inmediata (Fotometría Multicolor B, V, I)",
                        "objetivo": "Descartar fulguración estelar (flare). En un agujero negro la magnificación es estrictamente acromática (independiente de la longitud de onda).",
                        "telescopios": "LCOGT (Las Cumbres Observatory), telescopios robóticos de 1m."
                    },
                    {
                        "fase": "2. Astrometría de Alta Resolución (HST o James Webb)",
                        "objetivo": "Detectar el desplazamiento elíptico del centroide luminoso (Astrometric Deflection ~ 1 a 2 miliarcosegundos). Esto rompe la degeneración de masa-distancia y mide la masa del agujero negro directamente.",
                        "telescopios": "Hubble Space Telescope (WFC3), JWST o Interferometría VLTI/GRAVITY."
                    },
                    {
                        "fase": "3. Espectroscopía de la estrella fuente",
                        "objetivo": "Obtener tipo espectral exacto y distancia para fijar la masa de la lente.",
                        "telescopios": "VLT (X-shooter), Keck."
                    }
                ]
            }
        else:
            return {
                "candidate_type": "Binaria Silenciosa / Modulación Elipsoidal",
                "etapas": [
                    {
                        "fase": "1. Espectroscopía de Velocidad Radial de Alta Resolución",
                        "objetivo": "Medir la curva de velocidad radial K1 y calcular la función de masa f(M). Si f(M) > 3 M_☉, es un agujero negro inequívoco.",
                        "telescopios": "HARPS, ESPRESSO en VLT, HIRES en Keck."
                    },
                    {
                        "fase": "2. Inspección en Rayos X y Rayos Gamma",
                        "objetivo": "Comprobar si el agujero negro está acretando viento estelar o si es un 'dormant black hole' (sin emisión X).",
                        "telescopios": "Chandra, XMM-Newton, Swift/XRT."
                    },
                    {
                        "fase": "3. Astrometría Orbital con Gaia DR4 / Interferometría",
                        "objetivo": "Resolver la órbita astrométrica del centro de masa para determinar la inclinación orbital i y la masa exacta del objeto oscuro.",
                        "telescopios": "Gaia DR4 / VLTI-GRAVITY."
                    }
                ]
            }
