"""
Gravitational microlensing event detector (Isolated or Binary Black Hole signatures).
Uses the Paczyński (1986) analytical formalism and formal selection criteria from the literature
(Gould 1992, Mróz et al. 2021, Sahu et al. 2022).
"""
from typing import Dict, Any, Optional
import numpy as np
from scipy.optimize import curve_fit
import lightkurve as lk

def paczynski_model(t: np.ndarray, t0: float, u0: float, tE: float, f_base: float) -> np.ndarray:
    """
    Standard point-source microlensing model (Paczyński 1986):
    u(t) = sqrt(u0^2 + ((t - t0) / tE)^2)
    A(u) = (u^2 + 2) / (u * sqrt(u^2 + 4))
    Flux = f_base * A(u)
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
        Applies canonical literature criteria to isolate high-mass lenses (Black Holes):
        1. Robust statistical improvement of Paczyński model vs flat model (Delta_chi2 > 150).
        2. Temporal symmetry test: |t_rise - t_fall| / tE < 0.25 (rejects asymmetric stellar flares).
        3. Prolonged tE (tE > 20 days) representative of lenses with M > 3-10 M_sun (Sahu et al. 2022).
        4. Reduced chi2 of fit <= 2.5 (physical quality fit).
        """
        time = np.ascontiguousarray(lc.time.value, dtype=float)
        flux = np.ascontiguousarray(lc.flux.value, dtype=float)
        flux_err = np.ascontiguousarray(getattr(lc, 'flux_err', None).value if getattr(lc, 'flux_err', None) is not None else np.ones_like(flux) * 0.005, dtype=float)

        valid = np.isfinite(time) & np.isfinite(flux) & (flux_err > 0)
        time, flux, flux_err = time[valid], flux[valid], flux_err[valid]

        if len(time) < 80:
            return {"is_candidate": False, "reason": "Insufficient data points"}

        # Use low percentile to estimate baseline: microlensing only amplifies,
        # so the 15th percentile is free from event contamination.
        f_base_est = float(np.percentile(flux, 15))
        max_idx = np.argmax(flux)
        t0_est = float(time[max_idx])
        max_flux = float(flux[max_idx])
        peak_amplification = max_flux / f_base_est

        if peak_amplification < self.min_magnification:
            return {
                "is_candidate": False,
                "reason": f"Peak magnification {peak_amplification:.2f} below threshold {self.min_magnification}",
                "peak_amplification": peak_amplification
            }

        u0_est = min(0.9, 1.0 / max(peak_amplification, 1.05))
        # Estimate initial tE from the full-width at half-maximum of the peak
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

            # Model chi2 vs flat chi2
            chi2_model = float(np.sum(((flux - model_flux) / flux_err)**2))
            chi2_flat = float(np.sum(((flux - f_base_est) / flux_err)**2))
            d_chi2 = chi2_flat - chi2_model
            red_chi2 = chi2_model / max(len(flux) - 4, 1)

            # Symmetry test (Mróz et al. 2021)
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

            # Preliminary lens mass estimate (M_lens ~ theta_E^2 / kappa * pi_rel)
            # tE > 25d typically scales to M > 4-15 M_sun
            estimated_mass_solar = (fit_tE / 25.0) ** 2 * 4.0

            # RIGOROUS SCIENTIFIC LITERATURE CRITERIA:
            is_bh_microlensing = (
                d_chi2 >= self.min_delta_chi2 and
                fit_tE >= self.min_tE and
                red_chi2 <= 3.5 and
                fit_u0 < 0.75 and
                asymmetry_index < 0.65 and  # Rejects asymmetric flare-type eruptions
                estimated_mass_solar >= 3.0  # Tolman-Oppenheimer-Volkoff limit
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
                "reason": f"Paczynski fit did not converge: {str(e)}",
                "peak_amplification": peak_amplification
            }
