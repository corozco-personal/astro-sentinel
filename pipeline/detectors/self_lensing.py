"""
Gravitational Self-Lensing detector in compact binaries (Agol 2002, Kruse & Agol 2014).
When a stellar-mass black hole transits in front of its companion star,
the gravitational lens of the black hole deflects and focuses the star's light rays,
producing an ultra-rapid magnification pulse instead of a traditional shadow eclipse.
"""
from typing import Dict, Any, Optional
import numpy as np
import lightkurve as lk

class SelfLensingDetector:
    def __init__(self, min_pulse_snr: float = 7.0, max_pulse_duration_hours: float = 12.0):
        self.min_pulse_snr = min_pulse_snr
        self.max_pulse_duration_hours = max_pulse_duration_hours

    def evaluate(self, lc: lk.LightCurve, orbital_period_days: Optional[float] = None) -> Dict[str, Any]:
        """
        Searches for periodic magnification pulses (Self-Lensing pulses) characteristic
        of a black hole or neutron star passing in front of the stellar disk.
        """
        time = np.ascontiguousarray(lc.time.value, dtype=float)
        flux = np.ascontiguousarray(lc.flux.value, dtype=float)

        valid = np.isfinite(time) & np.isfinite(flux)
        time, flux = time[valid], flux[valid]

        if len(time) < 150:
            return {"is_candidate": False, "reason": "Insufficient data points"}

        # Local moving baseline (median in 1.5-day window)
        dt = np.median(np.diff(time))
        window_size = max(15, int(1.5 / dt))
        if window_size % 2 == 0:
            window_size += 1

        from scipy.signal import medfilt
        smooth_base = medfilt(flux, kernel_size=min(window_size, len(flux) if len(flux)%2!=0 else len(flux)-1))
        residual = flux - smooth_base
        std_noise = np.std(residual) + 1e-9

        # Search for narrow anomalous positive peaks (Self-lensing pulses)
        pulse_mask = residual > (self.min_pulse_snr * std_noise)
        peak_indices = np.where(pulse_mask)[0]

        if len(peak_indices) == 0:
            return {
                "is_candidate": False,
                "reason": "No focal magnification pulses detected",
                "max_snr": float(np.max(residual) / std_noise)
            }

        # Group contiguous points into individual events
        events = []
        current_event = [peak_indices[0]]
        for idx in peak_indices[1:]:
            if idx - current_event[-1] <= 3:
                current_event.append(idx)
            else:
                events.append(current_event)
                current_event = [idx]
        events.append(current_event)

        # Filter by physical duration (a self-lensing pulse lasts a few hours)
        valid_pulses = []
        for ev in events:
            ev_times = time[ev]
            duration_hours = (ev_times[-1] - ev_times[0]) * 24.0
            max_pulse_flux = np.max(residual[ev])
            pulse_snr = max_pulse_flux / std_noise
            if duration_hours <= self.max_pulse_duration_hours and pulse_snr >= self.min_pulse_snr:
                valid_pulses.append({
                    "time_bjd": float(time[ev[np.argmax(residual[ev])]]),
                    "duration_hours": float(duration_hours),
                    "snr": float(pulse_snr),
                    "magnification_amplitude": float(max_pulse_flux)
                })

        is_self_lensing = len(valid_pulses) >= 1

        return {
            "is_candidate": bool(is_self_lensing),
            "type": "Gravitational Self-Lensing Pulse (Agol 2002)",
            "pulse_count": len(valid_pulses),
            "pulses": valid_pulses,
            "max_snr": float(np.max([p["snr"] for p in valid_pulses])) if valid_pulses else 0.0,
            "reason": f"Detected focal gravitational magnification pulse (Self-Lensing) with SNR {valid_pulses[0]['snr']:.1f}" if is_self_lensing else "No valid pulses"
        }
