"""
Report and diagnostic plot generator for light curves and black hole candidates.
"""
from pathlib import Path
from typing import Dict, Any, Optional
import json
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import lightkurve as lk

class ReportGenerator:
    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.plots_dir = output_dir / "plots"
        self.candidates_dir = output_dir / "candidates"
        self.plots_dir.mkdir(parents=True, exist_ok=True)
        self.candidates_dir.mkdir(parents=True, exist_ok=True)

    def generate_candidate_report(self, target_id: str, lc: lk.LightCurve, detection: Dict[str, Any], cross_match: Dict[str, Any], assessment: Dict[str, Any]) -> str:
        """
        Generate JSON file and diagnostic plot for the candidate.
        """
        clean_name = target_id.replace(" ", "_").replace("/", "_")

        # 1. Save structured summary as JSON
        report_data = {
            "target_id": target_id,
            "detection": {k: v for k, v in detection.items() if k != "model_flux"},
            "cross_match": cross_match,
            "assessment": assessment
        }
        json_path = self.candidates_dir / f"{clean_name}_report.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False)

        # 2. Generate diagnostic plot
        fig_path = self.plots_dir / f"{clean_name}_diagnostic.png"
        self._plot_diagnostic(clean_name, lc, detection, assessment, fig_path)

        return str(json_path)

    def _plot_diagnostic(self, title: str, lc: lk.LightCurve, detection: Dict[str, Any], assessment: Dict[str, Any], out_path: Path):
        fig, ax = plt.subplots(figsize=(10, 5), dpi=150)
        
        time = lc.time.value
        flux = lc.flux.value
        ax.scatter(time, flux, s=2, color="#1f77b4", alpha=0.6, label="TESS Normalized Flux")

        # If microlensing model fit is available
        if "model_flux" in detection and detection["model_flux"] is not None:
            ax.plot(time, detection["model_flux"], color="#d62728", lw=2, label="Paczyński Microlensing Fit")

        ax.set_title(f"Target: {title} | Verdict: {assessment.get('verdict')}", fontsize=11, fontweight="bold")
        ax.set_xlabel("Time (BJD - 2457000)", fontsize=10)
        ax.set_ylabel("Normalized Relative Flux", fontsize=10)
        ax.grid(True, linestyle="--", alpha=0.4)
        ax.legend(loc="upper right")

        plt.tight_layout()
        plt.savefig(out_path)
        plt.close(fig)
