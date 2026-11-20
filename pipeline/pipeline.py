"""
Módulo del Pipeline Integrador.
Coordina la descarga de TESS, evaluación con detectores físicos,
descarte cruzado con SIMBAD/catálogos oficiales y generación de reportes.
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
        Ejecuta el ciclo completo de análisis sobre un objetivo astronómico en TESS.
        """
        print(f"\n=======================================================")
        print(f"[Pipeline] Analizando objetivo: {target_id}")
        print(f"=======================================================")

        # 1. Obtener datos de TESS
        try:
            lc = self.tess_client.fetch_lightcurve(target_id, sector=sector)
        except Exception as e:
            return {"target_id": target_id, "status": "ERROR", "reason": f"Error downloading TESS data: {str(e)}"}

        if lc is None:
            return {"target_id": target_id, "status": "NO_DATA", "reason": "No TESS lightcurve found in MAST archive"}

        # 2. Análisis de Microlente (Paczyński 1986 / Sahu et al. 2022)
        print("[Pipeline] Evaluando modelo de Microlente Gravitatoria...")
        micro_res = self.microlensing_detector.evaluate(lc)

        # 3. Consulta de metadatos estelares previos en TIC
        cross_match = self.cross_matcher.check_simbad_and_mast(target_id)
        tic_info = cross_match.get("tic_info", {})
        star_mass = tic_info.get("mass") or 1.0
        star_rad = tic_info.get("rad") or 1.5

        # 4. Análisis de Modulación Elipsoidal (Morris 1985 / Gomel et al. 2021)
        print("[Pipeline] Evaluando modulación elipsoidal y modelo de Morris...")
        ellip_res = self.ellipsoidal_detector.evaluate(lc, star_mass=star_mass, star_rad=star_rad)

        # 5. Análisis de Self-Lensing en Binaria (Agol 2002 / Kruse & Agol 2014)
        print("[Pipeline] Evaluando pulsos de magnificación Self-Lensing...")
        self_lens_res = self.self_lensing_detector.evaluate(lc, orbital_period_days=ellip_res.get("orbital_period_days"))

        # 6. Análisis de Doppler Beaming Relativista (Mazeh & Faigler 2010)
        print("[Pipeline] Evaluando efecto Doppler Beaming relativista...")
        doppler_res = self.doppler_detector.evaluate(lc, orbital_period_days=ellip_res.get("orbital_period_days"), star_mass=star_mass)

        # 7. Análisis de Acreción y Relación RMS-Flujo (Uttley et al. 2005)
        print("[Pipeline] Evaluando variabilidad aperiódica y relación RMS-Flujo...")
        flicker_res = self.flickering_detector.evaluate(lc)

        # 8. Análisis Box Least Squares (BLS) para Eclipses de Disco Circunestelar
        print("[Pipeline] Evaluando algoritmo Box Least Squares (BLS) para eclipses de disco...")
        bls_res = self.bls_detector.evaluate(lc)

        # 9. Filtro de Veto de Centroide (Pixel Centroid Shift Veto)
        print("[Pipeline] Verificando estabilidad de centroide PRF de TESS...")
        centroid_res = self.centroid_filter.evaluate(lc)

        # 10. Filtro de Persistencia de Fase y Armónicos de Excentricidad (3f, 4f)
        print("[Pipeline] Evaluando coherencia de fase y armónicos excéntricos (anti-manchas solares)...")
        ecc_res = self.eccentric_filter.evaluate(lc, orbital_period_days=ellip_res.get("orbital_period_days"))

        # 11. Geometría de Lóbulos de Roche (Eggleton 1983)
        roche_res = self.roche_analyzer.calculate_roche_geometry(
            m_primary=star_mass,
            m_bh=ellip_res.get("estimated_compact_mass_msun", 6.0),
            period_days=ellip_res.get("orbital_period_days", 4.0),
            r_star_rsun=star_rad
        )

        # Jerarquía de selección del mejor modelo físico detectado
        candidates_list = [d for d in [micro_res, self_lens_res, ellip_res, doppler_res, flicker_res, bls_res] if d.get("is_candidate")]
        best_detection = candidates_list[0] if candidates_list else ellip_res

        # VETO 1: Desplazamiento de centroide estelar (estrella contaminante de fondo)
        if centroid_res.get("is_blended_background_artifact"):
            print(f"[Pipeline] ⚠️ Veto de centroide activado: variación atribuible a estrella de fondo contaminante ({centroid_res.get('centroid_shift_arcsec', 0):.1f} arcsec)")
            best_detection = {
                "is_candidate": False,
                "type": "Descartado por Desplazamiento de Centroide",
                "reason": f"Falso positivo por binaria contaminante de fondo (desplazamiento de centroide {centroid_res.get('centroid_shift_arcsec', 0):.1f}\")"
            }

        # VETO 2: Deriva de fase de manchas estelares en rotación
        if ecc_res.get("is_stellar_spot_artifact") and best_detection.get("is_candidate"):
            print(f"[Pipeline] ⚠️ Veto de manchas solares activado: falta de coherencia de fase temporal ({ecc_res.get('phase_coherence', 0):.2f})")
            best_detection = {
                "is_candidate": False,
                "type": "Descartado por Variabilidad de Manchas Solares",
                "reason": f"Incoherencia de fase orbital ({ecc_res.get('phase_coherence', 0):.2f}): compatible con evolución de manchas estelares activas."
            }

        # 10. Evaluación de novedad (No documentado)
        assessment = self.cross_matcher.assess_undocumented_bh_potential(cross_match, best_detection)

        # 6. VERIFICACIÓN MULTIOBSERVATORIO AUTOMÁTICA EN TIEMPO REAL (FILTRO ESTRICTO DE VETO)
        auto_verification = None
        if assessment.get("undocumented_candidate"):
            print(f"[Pipeline] 🔬 Ejecutando Verificación Automática Multi-Observatorio (Gaia / Chandra / Límite OV)...")
            auto_verification = self.auto_verifier.run_auto_verification(
                target_id=target_id,
                detection=best_detection,
                tic_info=cross_match.get("tic_info")
            )
            v_score = auto_verification.get("final_score", 0)
            v_status = auto_verification.get("status", "")
            print(f"[Pipeline] 🛡️  Resultado Verificación Automática: Score {v_score}/100 [{v_status}]")
            print(f"[Pipeline]    {auto_verification.get('verdict')}")

            # FILTRO ESTRICTO: Si la verificación concluye que es una binaria estelar común o señal no concluyente (<60%),
            # se ANULA la designación de candidato inmediatamente.
            if v_score < 60 or v_status == "INCONCLUSIVE_OR_STELLAR":
                assessment["undocumented_candidate"] = False
                assessment["confidence"] = "Low"
                assessment["verdict"] = f"DISCARDED BY MULTI-OBSERVATORY VETO: Score {v_score}% - Compatible with standard stellar binary/blended artifact."
            else:
                assessment["auto_verification"] = auto_verification
                assessment["verdict"] = f"{assessment['verdict']} | {auto_verification.get('verdict')}"

                # INFERENCIA BAYESIANA MCMC FORMAL CUANDO SE CONFIRMA CANDIDATO FUERTE
                print(f"[Pipeline] ⚛️  Ejecutando Inferencia Bayesiana MCMC (emcee) para estimar distribución de masa...")
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

                # INSPECCIÓN ESPECTRAL GAIA DR3 (XP/RP)
                t_ra = cross_match.get("tic_info", {}).get("ra")
                t_dec = cross_match.get("tic_info", {}).get("dec")
                if t_ra is not None and t_dec is not None:
                    spec_res = self.spectral_inspector.inspect_spectrum(t_ra, t_dec)
                    assessment["gaia_spectrum"] = spec_res

        # 8. Generar reporte estructurado y Propuesta ToO en PDF si es candidato
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
                        f"Firma astronómica: {best_detection.get('type')}",
                        f"Veredicto: {assessment.get('verdict')}",
                        "Sin catalogación previa en SIMBAD como agujero negro o exoplaneta confirmado.",
                        "Auto-Verificación Multi-Observatorio completada exitosamente."
                    ]
                }
                proposal_pdf = self.proposal_gen.generate_pdf_proposal(candidate_summary)
            except Exception as e:
                print(f"[Pipeline] Error al generar propuesta PDF: {e}")

        # Extraer fotometría muestreada para visualización interactiva (Plotly en monitor)
        times_sample = lc.time.value
        flux_sample = lc.flux.value
        # Si tiene muchos puntos, remuestrear a ~400 puntos para transferencia web rápida
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

        print(f"[Pipeline] Veredicto: {assessment.get('verdict')}")
        print(f"[Pipeline] ¿Candidato a Agujero Negro sin documentar?: {assessment.get('undocumented_candidate')}")
        return result
