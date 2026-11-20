"""
Detector de Doppler Beaming / Relativistic Boosting (Mazeh & Faigler 2010, Loeb & Gaudi 2003).
Detecta modulación relativista a frecuencia orbital 1f desfasada 90° de la modulación elipsoidal 2f,
permitiendo estimar la velocidad radial semiamplitud K y la masa mínima del compañero compacto.
"""
from typing import Dict, Any, Optional
import numpy as np
from astropy.timeseries import LombScargle
import lightkurve as lk

class DopplerBeamingDetector:
    def __init__(self, min_snr: float = 4.0, max_velocity_km_s: float = 600.0):
        self.min_snr = min_snr
        self.max_velocity_km_s = max_velocity_km_s

    def evaluate(self, lc: lk.LightCurve, orbital_period_days: Optional[float] = None, star_mass: float = 1.0) -> Dict[str, Any]:
        """
        Calcula la amplitud de beaming relativista A_beam ~ (3 - alpha) * (v_r / c):
        A_beam(t) ~ alpha_beam * (K_star / c) * sin(2*pi * t / P_orb)
        """
        time = np.ascontiguousarray(lc.time.value, dtype=float)
        flux = np.ascontiguousarray(lc.flux.value, dtype=float)

        valid = np.isfinite(time) & np.isfinite(flux)
        time, flux = time[valid], flux[valid]

        if len(time) < 150:
            return {"is_candidate": False, "reason": "Insufficient points for Doppler beaming"}

        # Si tenemos un período orbital previo estimado (e.g. de modulación elipsoidal)
        if orbital_period_days and orbital_period_days > 0.2:
            target_freq = 1.0 / orbital_period_days
            ls = LombScargle(time, flux)
            powers = ls.autopower(minimum_frequency=0.03, maximum_frequency=2.0, samples_per_peak=10)
            median_pow = float(np.median(powers[1]))
            std_pow = float(np.std(powers[1]))
            
            p_at_f = float(ls.power(target_freq))
            snr_1f = (p_at_f - median_pow) / (std_pow + 1e-9)

            # Ajuste de amplitud en fase orbital
            phase = (time / orbital_period_days) % 1.0
            sin_phase = np.sin(2.0 * np.pi * phase)
            cos_phase = np.cos(2.0 * np.pi * phase)
            
            # Regresión lineal simple para descomponer componentes 1f
            M = np.column_stack([sin_phase, cos_phase, np.ones_like(phase)])
            try:
                coeffs, _, _, _ = np.linalg.lstsq(M, flux - 1.0, rcond=None)
                amplitude_beaming = np.sqrt(coeffs[0]**2 + coeffs[1]**2)
                # Estimación de velocidad radial en km/s (alpha_eff ~ 1.5 en banda TESS)
                # A_beam ~ 1.5 * (K / c) -> K ~ (A_beam / 1.5) * 300,000 km/s
                k_km_s = (amplitude_beaming / 1.5) * 299792.458
            except Exception:
                amplitude_beaming = 0.0
                k_km_s = 0.0

            # Criterio de velocidad relativista para compañero compacto masivo:
            # En binarias BH de corto período, K_star típicamente > 60-150 km/s
            is_candidate = (snr_1f >= self.min_snr and 50.0 <= k_km_s <= self.max_velocity_km_s)
            
            # Estimación de función de masa binaria f(M) = P * K^3 / (2*pi*G)
            # f(M) en M_sun ~ 1.036e-7 * (1 - e^2)^(3/2) * (K_km_s)^3 * P_days
            mass_func = 1.036e-7 * (k_km_s ** 3) * orbital_period_days

            return {
                "is_candidate": is_candidate,
                "type": "Doppler Beaming (Relativistic Boosting)",
                "snr": float(snr_1f),
                "beaming_amplitude_ppm": float(amplitude_beaming * 1e6),
                "estimated_radial_velocity_km_s": float(k_km_s),
                "binary_mass_function_msun": float(mass_func),
                "orbital_period_days": float(orbital_period_days)
            }

        return {"is_candidate": False, "reason": "No orbital period constraint provided"}
