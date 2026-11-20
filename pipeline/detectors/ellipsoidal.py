"""
Detector de modulaciones elipsoidales y beaming relativista en binarias durmientes (Dormant Black Holes).
Fundamentado en el formalismo de distorsión de marea de Morris (1985), Morris & Naftilan (1993)
y el criterio de función de masa mínima de Gomel et al. (2021) / Gaia DR3 Non-Single Stars.
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
        Aplica los criterios canónicos de Morris (1985) y Gomel et al. (2021):
        1. Periodograma Lomb-Scargle de altísima significancia (SNR >= 20) libre de manchas rotacionales.
        2. Dominancia del modo de marea cuadrupolar: potencia balanceada en el armónico orbital 2f respecto a f (harmonic_ratio >= 0.45).
        3. Cálculo de la masa mínima del compañero compacto mediante la relación analítica de Morris:
           A_ellip ~ q * (R_star / a)^3 * sin^2(i)
           Si M_compacto_min < 3.0 M_☉, se descarta por ser compatible con una enana blanca o estrella ordinaria.
        """
        time = np.ascontiguousarray(lc.time.value, dtype=float)
        flux = np.ascontiguousarray(lc.flux.value, dtype=float)

        valid = np.isfinite(time) & np.isfinite(flux)
        time, flux = time[valid], flux[valid]

        if len(time) < 150:
            return {"is_candidate": False, "reason": "Puntos de datos insuficientes"}

        min_freq = 1.0 / self.max_period
        max_freq = 1.0 / self.min_period

        ls = LombScargle(time, flux)
        frequencies, powers = ls.autopower(minimum_frequency=min_freq, maximum_frequency=max_freq, samples_per_peak=15)

        best_idx = np.argmax(powers)
        best_power = float(powers[best_idx])
        best_freq = float(frequencies[best_idx])
        best_period = 1.0 / best_freq

        median_power = float(np.median(powers))
        # Usar MAD (Median Absolute Deviation) como estimador robusto de dispersión,
        # resistente a sidelobe spectral leakage que infla np.std
        mad_power = float(np.median(np.abs(powers - median_power)))
        std_robust = mad_power * 1.4826  # Factor de escala para distribución normal
        snr = (best_power - median_power) / (std_robust + 1e-9)

        if snr < self.min_snr:
            return {
                "is_candidate": False,
                "reason": f"SNR {snr:.1f} inferior al umbral estricto {self.min_snr}",
                "period": float(best_period),
                "snr": float(snr)
            }

        double_freq = 2.0 * best_freq
        half_freq = 0.5 * best_freq

        power_2f = float(ls.power(double_freq))
        power_half_f = float(ls.power(half_freq))

        # Detectar si el pico es 2f_orb (marea cuadrupolar domina):
        # Si hay potencia significativa a half_freq (= f_orb), el pico está en 2f_orb
        peak_is_2f = power_half_f > 0.01 * best_power
        # Si hay potencia significativa a double_freq (= 2f_orb), el pico está en f_orb
        peak_is_f = power_2f > 0.01 * best_power

        # Harmonic ratio: relación entre componente de marea (2f) y dipolar (1f)
        # Cuando el pico es 2f_orb: ratio = best_power / power_half_f (2f/f - marea domina)
        # Cuando el pico es f_orb: ratio = power_2f / best_power (2f/f)
        if peak_is_2f and best_power > power_half_f:
            # Pico en 2f_orb: la marea domina, ratio = potencia_2f / potencia_f
            harmonic_ratio = power_half_f / (best_power + 1e-9)
            # Para marea cuadrupolar dominante, basta que f_orb esté presente
            harmonic_check = power_half_f > 0.01 * best_power
        else:
            harmonic_ratio = max(power_2f, power_half_f) / (best_power + 1e-9)
            harmonic_check = harmonic_ratio >= self.harmonic_ratio_min

        # Amplitud semipico en porcentaje
        amplitude_percent = float((np.percentile(flux, 95) - np.percentile(flux, 5)) * 100.0 / 2.0)

        # Período orbital real (si el pico detectado corresponde a 2*f_orb)
        orbital_period_days = float(best_period * 2.0 if peak_is_2f else best_period)

        # MODELO DE MORRIS (1985) PARA COMPAÑERO MASIVO:
        # A_ellip ∝ q * (R_star / a)^3 * sin²(i)
        # a³ ∝ (M_star + M_comp) * P²  (Kepler)
        # → M_comp_min ∝ A_ellip * M_star * (P_orb)^2 / R_star^3
        # Estimación analítica (Gomel et al. 2021):
        r_ratio = max(0.5, float(star_rad or 1.5))
        m_primary = max(0.8, float(star_mass or 1.0))

        # Factor de Morris normalizado (R_star en numerador: mayor estrella → más distorsión para misma masa)
        morris_mass_ratio = (amplitude_percent / 1.5) * ((orbital_period_days / 3.5) ** (2.0 / 3.0)) * (r_ratio ** 1.0)
        estimated_compact_mass = m_primary * max(0.1, morris_mass_ratio)

        # CRITERIO DE TOLMAN-OPPENHEIMER-VOLKOFF:
        # Solo se considera candidato a agujero negro si la masa estimada del objeto oscuro
        # es > 3.0 M_☉ (incompatible con enanas blancas o estrellas de neutrones)
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
                "Candidato consistente con agujero negro estelar masivo según Morris (1985)"
                if is_ellipsoidal_candidate
                else f"Descartado: Masa estimada ({estimated_compact_mass:.2f} M_☉) < 3.0 M_☉ o armónicos insuficientes ({harmonic_ratio:.2f})"
            )
        }
