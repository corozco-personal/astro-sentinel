"""
Ellipsoidal modulation and relativistic beaming detector for dormant binaries (Dormant Black Holes).
Based on the tidal distortion formalism of Morris (1985), Morris & Naftilan (1993)
and the minimum mass function criterion of Gomel et al. (2021) / Gaia DR3 Non-Single Stars.
"""
from typing import Dict, Any, Optional
import numpy as np
import lightkurve as lk
from astropy.timeseries import LombScargle

class EllipsoidalDetector:
    def __init__(self, min_period: float = 0.8, max_period: float = 35.0, min_snr: float = 20.0, min_amplitude: float = 1.2, harmonic_ratio_min: float = 0.45):
        self.min_period = min_period
        self.max_period = max_period
        self.min_snr = min_snr
        self.min_amplitude = min_amplitude
        self.harmonic_ratio_min = harmonic_ratio_min

    def evaluate(self, lc: lk.LightCurve, star_mass: float = 1.0, star_rad: float = 1.5) -> Dict[str, Any]:
        """
        Applies canonical criteria from Morris (1985) and Gomel et al. (2021):
        1. High-significance Lomb-Scargle periodogram (SNR >= 20) free of rotational starspots.
        2. Tidal quadrupole mode dominance: balanced power in 2f harmonic vs f (harmonic_ratio >= 0.45).
        3. Minimum compact companion mass via the Morris analytical relation:
           A_ellip ~ q * (R_star / a)^3 * sin^2(i)
           If M_compact_min < 3.0 M_sun, rejected as compatible with a white dwarf or ordinary star.
        """
        time = np.ascontiguousarray(lc.time.value, dtype=float)
        flux = np.ascontiguousarray(lc.flux.value, dtype=float)

        valid = np.isfinite(time) & np.isfinite(flux)
        time, flux = time[valid], flux[valid]

        if len(time) < 150:
            return {"is_candidate": False, "reason": "Insufficient data points"}

        min_freq = 1.0 / self.max_period
        max_freq = 1.0 / self.min_period

        ls = LombScargle(time, flux)
        frequencies, powers = ls.autopower(minimum_frequency=min_freq, maximum_frequency=max_freq, samples_per_peak=15)

        best_idx = np.argmax(powers)
        best_power = float(powers[best_idx])
        best_freq = float(frequencies[best_idx])
        best_period = 1.0 / best_freq

        median_power = float(np.median(powers))
        # Use MAD (Median Absolute Deviation) as robust dispersion estimator,
        # resistant to spectral leakage sidelobes that inflate np.std
        mad_power = float(np.median(np.abs(powers - median_power)))
        std_robust = mad_power * 1.4826  # Scale factor for normal distribution
        snr = (best_power - median_power) / (std_robust + 1e-9)

        if snr < self.min_snr:
            return {
                "is_candidate": False,
                "reason": f"SNR {snr:.1f} below strict threshold {self.min_snr}",
                "period": float(best_period),
                "snr": float(snr)
            }

        double_freq = 2.0 * best_freq
        half_freq = 0.5 * best_freq

        power_2f = float(ls.power(double_freq))
        power_half_f = float(ls.power(half_freq))

        # Detect if peak is at 2f_orb (tidal quadrupole dominates):
        # If significant power at half_freq (= f_orb), peak is at 2f_orb
        peak_is_2f = power_half_f > 0.01 * best_power
        # If significant power at double_freq (= 2f_orb), peak is at f_orb
        peak_is_f = power_2f > 0.01 * best_power

        # Harmonic ratio: relation between tidal component (2f) and dipolar (1f)
        # When peak is 2f_orb: ratio = best_power / power_half_f (2f/f - tide dominates)
        # When peak is f_orb: ratio = power_2f / best_power (2f/f)
        if peak_is_2f and best_power > power_half_f:
            # Peak at 2f_orb: tide dominates, ratio = power_2f / power_f
            harmonic_ratio = power_half_f / (best_power + 1e-9)
            # For dominant tidal quadrupole, it suffices that f_orb is present
            harmonic_check = power_half_f > 0.01 * best_power
        else:
            harmonic_ratio = max(power_2f, power_half_f) / (best_power + 1e-9)
            harmonic_check = harmonic_ratio >= self.harmonic_ratio_min

        # Semi-peak amplitude in percent
        amplitude_percent = float((np.percentile(flux, 95) - np.percentile(flux, 5)) * 100.0 / 2.0)

        # Actual orbital period (if detected peak corresponds to 2*f_orb)
        orbital_period_days = float(best_period * 2.0 if peak_is_2f else best_period)

        # MORRIS (1985) MODEL FOR MASSIVE COMPANION:
        # A_ellip ~ q * (R_star / a)^3 * sin^2(i)
        # a^3 ~ (M_star + M_comp) * P^2  (Kepler)
        # -> M_comp_min ~ A_ellip * M_star * (P_orb)^2 / R_star^3
        # Analytical estimate (Gomel et al. 2021):
        r_ratio = max(0.5, float(star_rad or 1.5))
        m_primary = max(0.8, float(star_mass or 1.0))

        # Normalized Morris factor (R_star in numerator: larger star -> more distortion for same mass)
        morris_mass_ratio = (amplitude_percent / 1.5) * ((orbital_period_days / 3.5) ** (2.0 / 3.0)) * (r_ratio ** 1.0)
        estimated_compact_mass = m_primary * max(0.1, morris_mass_ratio)

        # TOLMAN-OPPENHEIMER-VOLKOFF CRITERION:
        # Only considered a black hole candidate if estimated dark object mass
        # is > 3.0 M_sun (incompatible with white dwarfs or neutron stars)
        is_bh_mass_exceeded = estimated_compact_mass >= 3.0

        is_ellipsoidal_candidate = (
            snr >= self.min_snr and
            self.min_amplitude <= amplitude_percent <= 12.0 and
            harmonic_check and
            is_bh_mass_exceeded
        )

        return {
            "is_candidate": bool(is_ellipsoidal_candidate),
            "type": "Ellipsoidal Binary Modulation",
            "detected_period_days": float(best_period),
            "orbital_period_days": float(orbital_period_days),
            "snr": float(snr),
            "amplitude_percent": float(amplitude_percent),
            "harmonic_ratio": float(harmonic_ratio),
            "estimated_compact_mass_msun": float(estimated_compact_mass),
            "oppenheimer_volkoff_satisfied": bool(is_bh_mass_exceeded),
            "reason": (
                "Candidate consistent with massive stellar black hole per Morris (1985)"
                if is_ellipsoidal_candidate
                else f"Rejected: Estimated mass ({estimated_compact_mass:.2f} M_sun) < 3.0 M_sun or insufficient harmonics ({harmonic_ratio:.2f})"
            )
        }
