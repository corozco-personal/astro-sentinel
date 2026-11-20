"""
Doppler Beaming / Relativistic Boosting detector (Mazeh & Faigler 2010, Loeb & Gaudi 2003).
Detects relativistic modulation at orbital frequency 1f phase-shifted 90 degrees from
the ellipsoidal modulation at 2f, allowing estimation of radial velocity semi-amplitude K
and minimum compact companion mass.
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
        Computes relativistic beaming amplitude A_beam ~ (3 - alpha) * (v_r / c):
        A_beam(t) ~ alpha_beam * (K_star / c) * sin(2*pi * t / P_orb)
        """
        time = np.ascontiguousarray(lc.time.value, dtype=float)
        flux = np.ascontiguousarray(lc.flux.value, dtype=float)

        valid = np.isfinite(time) & np.isfinite(flux)
        time, flux = time[valid], flux[valid]

        if len(time) < 150:
            return {"is_candidate": False, "reason": "Insufficient points for Doppler beaming"}

        # If we have a prior estimated orbital period (e.g. from ellipsoidal modulation)
        if orbital_period_days and orbital_period_days > 0.2:
            target_freq = 1.0 / orbital_period_days
            ls = LombScargle(time, flux)
            powers = ls.autopower(minimum_frequency=0.03, maximum_frequency=2.0, samples_per_peak=10)
            median_pow = float(np.median(powers[1]))
            std_pow = float(np.std(powers[1]))

            p_at_f = float(ls.power(target_freq))
            snr_1f = (p_at_f - median_pow) / (std_pow + 1e-9)

            # Orbital phase amplitude fit
            phase = (time / orbital_period_days) % 1.0
            sin_phase = np.sin(2.0 * np.pi * phase)
            cos_phase = np.cos(2.0 * np.pi * phase)

            # Simple linear regression to decompose 1f components
            M = np.column_stack([sin_phase, cos_phase, np.ones_like(phase)])
            try:
                coeffs, _, _, _ = np.linalg.lstsq(M, flux - 1.0, rcond=None)
                amplitude_beaming = np.sqrt(coeffs[0]**2 + coeffs[1]**2)
                # Radial velocity estimate in km/s (alpha_eff ~ 1.5 in TESS band)
                # A_beam ~ 1.5 * (K / c) -> K ~ (A_beam / 1.5) * 300,000 km/s
                k_km_s = (amplitude_beaming / 1.5) * 299792.458
            except Exception:
                amplitude_beaming = 0.0
                k_km_s = 0.0

            # Relativistic velocity criterion for massive compact companion:
            # In short-period BH binaries, K_star typically > 60-150 km/s
            is_candidate = (snr_1f >= self.min_snr and 50.0 <= k_km_s <= self.max_velocity_km_s)

            # Binary mass function estimate f(M) = P * K^3 / (2*pi*G)
            # f(M) in M_sun ~ 1.036e-7 * (1 - e^2)^(3/2) * (K_km_s)^3 * P_days
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
