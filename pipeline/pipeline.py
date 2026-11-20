"""
Integrator Pipeline — coordinates TESS download, physics-based detection,
cross-match against SIMBAD/official catalogs, and report generation.
"""
from pathlib import Path
from typing import Dict, Any, Optional
from config import PipelineConfig, OUTPUT_DIR
from pipeline.tess_client import TESSClient
from pipeline.detectors.microlensing import MicrolensingDetector
from pipeline.detectors.ellipsoidal import EllipsoidalDetector
from pipeline.detectors.self_lensing import SelfLensingDetector
from pipeline.detectors.doppler_beaming import DopplerBeamingDetector
from pipeline.detectors.accretion_flickering import AccretionFlickeringDetector
from pipeline.detectors.bls_detector import BoxLeastSquaresDetector
from pipeline.detectors.centroid_veto import CentroidVetoFilter
from pipeline.detectors.eccentric_harmonics import EccentricHarmonicsAndPhaseFilter
from pipeline.statistical_corrector import StatisticalQualityCorrector
from pipeline.bayesian_mcmc import BayesianMCMCAnalyzer
from pipeline.multi_sector_stitcher import MultiSectorStitcher
from pipeline.gaia_spectral import GaiaSpectralInspector
from pipeline.roche_analyzer import RocheLobeAnalyzer
from pipeline.finder_chart import FinderChartGenerator
from pipeline.kinematic_kick import KinematicKickAnalyzer
from pipeline.cross_match import CatalogCrossMatcher
from pipeline.auto_verifier import AutoVerifier
from pipeline.report_generator import ReportGenerator
from pipeline.proposal_generator import ProposalGenerator
import numpy as np
from pipeline.safe_logger import safe_print as print

class BlackHolePipeline:
    def __init__(self, config: Optional[PipelineConfig] = None):
        self.config = config or PipelineConfig()
        self.tess_client = TESSClient()
        self.microlensing_detector = MicrolensingDetector(
            min_magnification=self.config.microlensing.min_magnification,
            min_tE=self.config.microlensing.min_tE_days,
            max_tE=self.config.microlensing.max_tE_days
        )
        self.ellipsoidal_detector = EllipsoidalDetector(
            min_period=self.config.ellipsoidal.min_period_days,
            max_period=self.config.ellipsoidal.max_period_days,
            min_snr=self.config.ellipsoidal.min_power_snr
        )
        self.self_lensing_detector = SelfLensingDetector()
        self.doppler_detector = DopplerBeamingDetector()
        self.flickering_detector = AccretionFlickeringDetector()
        self.bls_detector = BoxLeastSquaresDetector()
        self.centroid_filter = CentroidVetoFilter()
        self.eccentric_filter = EccentricHarmonicsAndPhaseFilter()
        self.stat_corrector = StatisticalQualityCorrector()
        self.mcmc_analyzer = BayesianMCMCAnalyzer()
        self.multi_sector_stitcher = MultiSectorStitcher()
        self.spectral_inspector = GaiaSpectralInspector()
        self.roche_analyzer = RocheLobeAnalyzer()
        self.finder_chart_gen = FinderChartGenerator(OUTPUT_DIR)
        self.kinematic_analyzer = KinematicKickAnalyzer()
        self.cross_matcher = CatalogCrossMatcher()
        self.auto_verifier = AutoVerifier()
        self.report_gen = ReportGenerator(OUTPUT_DIR)
        self.proposal_gen = ProposalGenerator(OUTPUT_DIR)

    def analyze_target(self, target_id: str, sector: Optional[int] = None) -> Dict[str, Any]:
        """
        Run full analysis cycle on an astronomical target in TESS.
        """
        print(f"\n=======================================================")
        print(f"[Pipeline] Analyzing target: {target_id}")
        print(f"=======================================================")

        # 1. Fetch TESS data
        try:
            lc = self.tess_client.fetch_lightcurve(target_id, sector=sector)
        except Exception as e:
            return {"target_id": target_id, "status": "ERROR", "reason": f"Error downloading TESS data: {str(e)}"}

        if lc is None:
            return {"target_id": target_id, "status": "NO_DATA", "reason": "No TESS lightcurve found in MAST archive"}

        # 2. Microlensing analysis (Paczyński 1986 / Sahu et al. 2022)
        print("[Pipeline] Evaluating Gravitational Microlensing model...")
        micro_res = self.microlensing_detector.evaluate(lc)

        # 3. Fetch stellar metadata from TIC
        cross_match = self.cross_matcher.check_simbad_and_mast(target_id)
        tic_info = cross_match.get("tic_info", {})
        star_mass = tic_info.get("mass") or 1.0
        star_rad = tic_info.get("rad") or 1.5

        # 4. Ellipsoidal Modulation (Morris 1985 / Gomel et al. 2021)
        print("[Pipeline] Evaluating ellipsoidal modulation and Morris model...")
        ellip_res = self.ellipsoidal_detector.evaluate(lc, star_mass=star_mass, star_rad=star_rad)

        # 5. Self-Lensing in Binary (Agol 2002 / Kruse & Agol 2014)
        print("[Pipeline] Evaluating Self-Lensing magnification pulses...")
        self_lens_res = self.self_lensing_detector.evaluate(lc, orbital_period_days=ellip_res.get("orbital_period_days"))

        # 6. Relativistic Doppler Beaming (Mazeh & Faigler 2010)
        print("[Pipeline] Evaluating relativistic Doppler Beaming...")
        doppler_res = self.doppler_detector.evaluate(lc, orbital_period_days=ellip_res.get("orbital_period_days"), star_mass=star_mass)

        # 7. Accretion and RMS–Flux Relation (Uttley et al. 2005)
        print("[Pipeline] Evaluating aperiodic variability and RMS–Flux relation...")
        flicker_res = self.flickering_detector.evaluate(lc)

        # 8. Box Least Squares (BLS) for Circumstellar Disk Eclipses
        print("[Pipeline] Evaluating BLS for disk eclipses...")
        bls_res = self.bls_detector.evaluate(lc)

        # 9. Centroid Veto Filter (Pixel Centroid Shift)
        print("[Pipeline] Verifying TESS PRF centroid stability...")
        centroid_res = self.centroid_filter.evaluate(lc)

        # 10. Phase Persistence and Eccentricity Harmonics Filter (3f, 4f)
        print("[Pipeline] Evaluating phase coherence and eccentric harmonics (anti-starspot)...")
        ecc_res = self.eccentric_filter.evaluate(lc, orbital_period_days=ellip_res.get("orbital_period_days"))

        # 11. Roche Lobe Geometry (Eggleton 1983)
        roche_res = self.roche_analyzer.calculate_roche_geometry(
            m_primary=star_mass,
            m_bh=ellip_res.get("estimated_compact_mass_msun", 6.0),
            period_days=ellip_res.get("orbital_period_days", 4.0),
            r_star_rsun=star_rad
        )

        # Select best physical model detected
        candidates_list = [d for d in [micro_res, self_lens_res, ellip_res, doppler_res, flicker_res, bls_res] if d.get("is_candidate")]
        best_detection = candidates_list[0] if candidates_list else ellip_res

        # VETO 1: Centroid shift (background contaminating star)
        if centroid_res.get("is_blended_background_artifact"):
            print(f"[Pipeline] Centroid veto triggered: variation attributable to background contaminant ({centroid_res.get('centroid_shift_arcsec', 0):.1f} arcsec)")
            best_detection = {
                "is_candidate": False,
                "type": "Rejected by Centroid Shift",
                "reason": f"False positive from background blended binary (centroid shift {centroid_res.get('centroid_shift_arcsec', 0):.1f}\")"
            }

        # VETO 2: Phase drift from rotating starspots
        if ecc_res.get("is_stellar_spot_artifact") and best_detection.get("is_candidate"):
            print(f"[Pipeline] Starspot veto triggered: temporal phase incoherence ({ecc_res.get('phase_coherence', 0):.2f})")
            best_detection = {
                "is_candidate": False,
                "type": "Rejected by Starspot Variability",
                "reason": f"Orbital phase incoherence ({ecc_res.get('phase_coherence', 0):.2f}): consistent with active starspot evolution."
            }

        # Novelty assessment (undocumented candidate check)
        assessment = self.cross_matcher.assess_undocumented_bh_potential(cross_match, best_detection)

        # Multi-observatory auto-verification (strict veto filter)
        auto_verification = None
        if assessment.get("undocumented_candidate"):
            print(f"[Pipeline] Running Multi-Observatory Auto-Verification (Gaia / Chandra / OV Limit)...")
            auto_verification = self.auto_verifier.run_auto_verification(
                target_id=target_id,
                detection=best_detection,
                tic_info=cross_match.get("tic_info")
            )
            v_score = auto_verification.get("final_score", 0)
            v_status = auto_verification.get("status", "")
            print(f"[Pipeline] Auto-Verification Result: Score {v_score}/100 [{v_status}]")
            print(f"[Pipeline]    {auto_verification.get('verdict')}")

            # Strict filter: if verification concludes common stellar binary or inconclusive (<60%), revoke candidate status.
            if v_score < 60 or v_status == "INCONCLUSIVE_OR_STELLAR":
                assessment["undocumented_candidate"] = False
                assessment["confidence"] = "Low"
                assessment["verdict"] = f"DISCARDED BY MULTI-OBSERVATORY VETO: Score {v_score}% - Compatible with standard stellar binary/blended artifact."
            else:
                assessment["auto_verification"] = auto_verification
                assessment["verdict"] = f"{assessment['verdict']} | {auto_verification.get('verdict')}"

                # Bayesian MCMC inference for strong confirmed candidates
                print(f"[Pipeline] Running Bayesian MCMC (emcee) for mass posterior estimation...")
                try:
                    time_v = np.ascontiguousarray(lc.time.value, dtype=float)
                    flux_v = np.ascontiguousarray(lc.flux.value, dtype=float)
                    flux_err_v = getattr(lc, 'flux_err', None)
                    err_v = np.ascontiguousarray(flux_err_v.value, dtype=float) if flux_err_v is not None else np.full_like(flux_v, 0.005)
                    valid_m = np.isfinite(time_v) & np.isfinite(flux_v) & np.isfinite(err_v)
                    mcmc_res = self.mcmc_analyzer.fit_bh_posterior(
                        time_v[valid_m], flux_v[valid_m], err_v[valid_m],
                        initial_period=best_detection.get("orbital_period_days", 5.0),
                        initial_mass=best_detection.get("estimated_compact_mass_msun", 6.0)
                    )
                    assessment["mcmc_posteriors"] = mcmc_res
                    print(f"[Pipeline] 📊 MCMC Posterior: M_BH = {mcmc_res['bh_mass_msun_median']} +{mcmc_res['bh_mass_msun_err_plus']}/-{mcmc_res['bh_mass_msun_err_minus']} M_☉")
                except Exception as e_mcmc:
                    print(f"[Pipeline] MCMC notice: {e_mcmc}")

                # Gaia DR3 spectral inspection (XP/RP)
                t_ra = cross_match.get("tic_info", {}).get("ra")
                t_dec = cross_match.get("tic_info", {}).get("dec")
                if t_ra is not None and t_dec is not None:
                    spec_res = self.spectral_inspector.inspect_spectrum(t_ra, t_dec)
                    assessment["gaia_spectrum"] = spec_res

        # Generate structured report and ToO proposal PDF if candidate
        report_file = self.report_gen.generate_candidate_report(
            target_id=target_id,
            lc=lc,
            detection=best_detection,
            cross_match=cross_match,
            assessment=assessment
        )

        proposal_pdf = None
        if assessment.get("undocumented_candidate"):
            try:
                candidate_summary = {
                    "target_id": target_id,
                    "ra": cross_match.get("tic_info", {}).get("ra"),
                    "dec": cross_match.get("tic_info", {}).get("dec"),
                    "detection_details": best_detection,
                    "assessment": assessment,
                    "simbad_info": cross_match,
                    "criteria_list": [
                        f"Astronomical signature: {best_detection.get('type')}",
                        f"Verdict: {assessment.get('verdict')}",
                        "No prior catalogation in SIMBAD as confirmed black hole or exoplanet.",
                        "Multi-Observatory Auto-Verification completed successfully."
                    ]
                }
                proposal_pdf = self.proposal_gen.generate_pdf_proposal(candidate_summary)
            except Exception as e:
                print(f"[Pipeline] Error generating PDF proposal: {e}")

        # Extract sampled photometry for interactive visualization (Plotly in dashboard)
        times_sample = lc.time.value
        flux_sample = lc.flux.value
        # Downsample to ~400 points for fast web transfer
        if len(times_sample) > 400:
            step = len(times_sample) // 400
            times_sample = times_sample[::step]
            flux_sample = flux_sample[::step]

        result = {
            "target_id": target_id,
            "status": "SUCCESS",
            "is_candidate": best_detection.get("is_candidate", False),
            "detection_details": best_detection,
            "simbad_info": cross_match,
            "assessment": assessment,
            "auto_verification": auto_verification,
            "proposal_pdf": proposal_pdf,
            "raw_lightcurve": lc,
            "lightcurve_sample": {
                "time": [round(float(t), 4) for t in times_sample],
                "flux": [round(float(f), 4) for f in flux_sample]
            },
            "report_path": report_file
        }

        print(f"[Pipeline] Verdict: {assessment.get('verdict')}")
        print(f"[Pipeline] Undocumented Black Hole Candidate?: {assessment.get('undocumented_candidate')}")
        return result
