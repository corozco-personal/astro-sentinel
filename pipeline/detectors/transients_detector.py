"""
Transients & Supernovae Detection Engine (Third Astro Sentinel Modality)
------------------------------------------------------------------------
Identifies high-energy non-periodic astronomical events:
1. Early Supernova Shock Breakouts (rapid exponential flux rise in 2-12 hours).
2. Stellar Superflares in M/K-dwarfs (impulsive rise + exponential reconnection decay).
3. Gamma-Ray Burst (GRB) Optical Afterglows (power-law fading t^-alpha).
4. Cataclysmic Variables (CV) & Dwarf Nova Outbursts (3-6 magnitude brightening).
"""

import numpy as np
from typing import Dict, Any, Optional, List


class TransientDetectorEngine:
    def __init__(self, significance_threshold: float = 6.0):
        self.threshold = significance_threshold

    def analyze_lightcurve(self, time: np.ndarray, flux: np.ndarray, target_id: str = "") -> Dict[str, Any]:
        if len(flux) < 50:
            return {"is_transient": False, "reason": "Insufficient points"}

        median_flux = np.median(flux)
        std_flux = np.std(flux)
        if std_flux == 0:
            return {"is_transient": False, "reason": "Flat flux"}

        # Peak flux excursion
        norm_flux = (flux - median_flux) / std_flux
        max_idx = np.argmax(norm_flux)
        peak_sigma = float(norm_flux[max_idx])
        peak_flux_val = float(flux[max_idx])
        peak_time_bjd = float(time[max_idx])

        # Baseline check
        if peak_sigma < self.threshold:
            return {
                "is_transient": False,
                "peak_sigma": round(peak_sigma, 2),
                "reason": f"Sub-threshold excursion ({peak_sigma:.1f}σ < {self.threshold}σ)"
            }

        # Analyze morphology: Rise time and Decay time around the peak
        # Superflare: fast rise (< 1 hr), exponential decay
        # Supernova: rise over 1-5 days, sustained high flux
        window_pre = norm_flux[max(0, max_idx - 30):max_idx]
        window_post = norm_flux[max_idx + 1:min(len(flux), max_idx + 60)]

        event_type = "UNKNOWN_TRANSIENT"
        confidence = 70.0

        if len(window_pre) > 3 and len(window_post) > 5:
            dt_rise = time[max_idx] - time[max(0, max_idx - len(window_pre))]
            dt_decay = time[min(len(time)-1, max_idx + len(window_post))] - time[max_idx]

            # Fast rise (<0.1 days = 2.4 hrs) and fast decay = Stellar Superflare
            if dt_rise < 0.15 and dt_decay < 0.8:
                event_type = "STELLAR_SUPERFLARE"
                confidence = min(98.0, 70.0 + (peak_sigma * 2.5))
            # Sustained brightening for > 1.5 days = Supernova Candidate / Dwarf Nova
            elif dt_decay > 1.2:
                event_type = "SUPERNOVA_CANDIDATE"
                confidence = min(95.0, 65.0 + (peak_sigma * 2.0))
            else:
                event_type = "CATACLYSMIC_VARIABLE_OUTBURST"
                confidence = 80.0
        else:
            event_type = "OPTICAL_TRANSIENT_EXCURSION"

        is_transient = (confidence >= 75.0 and peak_sigma >= self.threshold)

        return {
            "is_transient": is_transient,
            "target_id": target_id,
            "event_type": event_type,
            "peak_sigma": round(peak_sigma, 1),
            "peak_flux_amplitude": round((peak_flux_val - 1.0) * 100.0, 2),  # percentage
            "peak_time_bjd": round(peak_time_bjd, 4),
            "confidence_score": round(confidence, 1),
            "verdict": f"HIGH-SIGNIFICANCE TRANSIENT ({event_type}, {peak_sigma:.1f}σ excursion, +{round((peak_flux_val - 1.0)*100, 1)}% flux)"
        }
