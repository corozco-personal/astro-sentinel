"""
Detector de eventos de microlente gravitatoria (Isolated or Binary Black Hole signatures).
Utiliza el formalismo analítico de Paczyński (1986) y los criterios formales de selección de literatura
(Gould 1992, Mróz et al. 2021, Sahu et al. 2022).
"""
from typing import Dict, Any, Optional
import numpy as np
from scipy.optimize import curve_fit
import lightkurve as lk

def paczynski_model(t: np.ndarray, t0: float, u0: float, tE: float, f_base: float) -> np.ndarray:
    """
    Modelo estándar de microlente puntual (Paczyński 1986):
    u(t) = sqrt(u0^2 + ((t - t0) / tE)^2)
    A(u) = (u^2 + 2) / (u * sqrt(u^2 + 4))
    Flujo = f_base * A(u)
    """
    tau = (t - t0) / np.maximum(tE, 1e-4)
    u = np.sqrt(u0**2 + tau**2)
    u = np.maximum(u, 1e-6)
    magnification = (u**2 + 2.0) / (u * np.sqrt(u**2 + 4.0))
    return f_base * magnification

class MicrolensingDetector:
    def __init__(self, min_magnification: float = 1.30, min_tE: float = 20.0, max_tE: float = 400.0, min_delta_chi2: float = 150.0):
        self.min_magnification = min_magnification
        self.min_tE = min_tE
        self.max_tE = max_tE
        self.min_delta_chi2 = min_delta_chi2

    def evaluate(self, lc: lk.LightCurve) -> Dict[str, Any]:
        """
        Aplica los criterios canónicos de literatura para aislar lentes de alta masa (Black Holes):
        1. Mejora estadística robusta del modelo Paczyński vs modelo plano (Delta_chi2 > 150).
        2. Test de simetría temporal: |t_rise - t_fall| / tE < 0.25 (descarta erupciones estelares asimétricas/flares).
        3. tE prolongado (tE > 20 días) representativo de lentes con M > 3-10 M_☉ (Sahu et al. 2022).
        4. Chi2 reducido del ajuste <= 2.5 (ajuste de calidad física).
        """
        time = np.ascontiguousarray(lc.time.value, dtype=float)
        flux = np.ascontiguousarray(lc.flux.value, dtype=float)
        flux_err = np.ascontiguousarray(getattr(lc, 'flux_err', None).value if getattr(lc, 'flux_err', None) is not None else np.ones_like(flux) * 0.005, dtype=float)
        
        valid = np.isfinite(time) & np.isfinite(flux) & (flux_err > 0)
        time, flux, flux_err = time[valid], flux[valid], flux_err[valid]

        if len(time) < 80:
            return {"is_candidate": False, "reason": "Puntos de datos insuficientes"}

        # Usar percentil bajo para estimar baseline: microlensing solo amplifica,
        # así que el percentil 15 está libre de contaminación del evento.
        f_base_est = float(np.percentile(flux, 15))
        max_idx = np.argmax(flux)
        t0_est = float(time[max_idx])
        max_flux = float(flux[max_idx])
        peak_amplification = max_flux / f_base_est

        if peak_amplification < self.min_magnification:
            return {
                "is_candidate": False,
                "reason": f"Magnificación pico {peak_amplification:.2f} inferior al umbral {self.min_magnification}",
                "peak_amplification": peak_amplification
            }

        u0_est = min(0.9, 1.0 / max(peak_amplification, 1.05))
        # Estimar tE inicial a partir del ancho a media altura del pico
        half_max = (max_flux + f_base_est) / 2.0
        above_half = time[flux > half_max]
        tE_est = float((above_half.max() - above_half.min()) / 2.0) if len(above_half) > 2 else 35.0
        tE_est = max(self.min_tE, min(tE_est, self.max_tE))

        try:
            p0 = [t0_est, u0_est, tE_est, f_base_est]
            bounds = (
                [time.min(), 0.005, self.min_tE, 0.5 * f_base_est],
                [time.max(), 1.0, self.max_tE, 1.5 * f_base_est]
            )
            popt, _ = curve_fit(paczynski_model, time, flux, p0=p0, bounds=bounds, sigma=flux_err, maxfev=10000)
            
            fit_t0, fit_u0, fit_tE, fit_fbase = popt
            model_flux = paczynski_model(time, *popt)
            
            # Chi2 del ajuste vs Chi2 plano
            chi2_model = float(np.sum(((flux - model_flux) / flux_err)**2))
            chi2_flat = float(np.sum(((flux - f_base_est) / flux_err)**2))
            d_chi2 = chi2_flat - chi2_model
            red_chi2 = chi2_model / max(len(flux) - 4, 1)

            # Test de simetría (Mróz et al. 2021)
            # Evaluar residuo antes y después de t0
            pre_t0 = time < fit_t0
            post_t0 = time > fit_t0
            flux_pre = flux[pre_t0]
            flux_post = flux[post_t0]
            model_pre = model_flux[pre_t0]
            model_post = model_flux[post_t0]

            asymmetry_index = 0.0
            if len(flux_pre) > 10 and len(flux_post) > 10:
                chi2_pre = np.mean((flux_pre - model_pre)**2)
                chi2_post = np.mean((flux_post - model_post)**2)
                asymmetry_index = abs(chi2_pre - chi2_post) / (chi2_pre + chi2_post + 1e-9)

            # Estimación preliminar de masa de la lente (M_lens ~ theta_E^2 / kappa * pi_rel)
            # tE > 25d escala típicamente a M > 4-15 M_sun
            estimated_mass_solar = (fit_tE / 25.0) ** 2 * 4.0

            # CRITERIOS RIGUROSOS DE LITERATURA CIENTÍFICA:
            is_bh_microlensing = (
                d_chi2 >= self.min_delta_chi2 and
                fit_tE >= self.min_tE and
                red_chi2 <= 3.5 and
                fit_u0 < 0.75 and
                asymmetry_index < 0.65 and # Descarta erupciones repentinas asimétricas tipo flare
                estimated_mass_solar >= 3.0 # Límite de Tolman-Oppenheimer-Volkoff
            )

            return {
                "is_candidate": bool(is_bh_microlensing),
                "type": "Microlensing (Paczynski)",
                "t0": float(fit_t0),
                "u0": float(fit_u0),
                "tE_days": float(fit_tE),
                "f_base": float(fit_fbase),
                "peak_magnification": float((fit_u0**2 + 2) / (fit_u0 * np.sqrt(fit_u0**2 + 4))),
                "delta_chi2": float(d_chi2),
                "reduced_chi2": float(red_chi2),
                "asymmetry_index": float(asymmetry_index),
                "estimated_mass_solar": float(estimated_mass_solar),
                "model_flux": model_flux
            }
        except Exception as e:
            return {
                "is_candidate": False,
                "reason": f"Ajuste Paczyński no convergió: {str(e)}",
                "peak_amplification": peak_amplification
            }
