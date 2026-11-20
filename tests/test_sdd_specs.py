"""
ASTRO SENTINEL - Automated SDD Regression Test Suite
Executes the Judges on core observatory contracts, veto gates, per-category metrics, and UI specs.
"""
import pytest
from sdd.contracts.candidate_contracts import (
    ExoplanetCandidateContract,
    ExoplanetTLSResults,
    ExoplanetPlanetaryParams,
    ExoplanetVetoAudit,
    BlackHoleCandidateContract
)
from sdd.judges.verification_judges import (
    CandidateQualityJudge,
    NotificationPolicyJudge,
    ArchitectureIntegrityJudge
)


class TestSDDCandidateGates:
    """Tests the strict veto gates ensuring no false alarms leak into Telegram or candidates list."""

    def test_genuine_exoplanet_passes_judge(self):
        payload = {
            "target_id": "TIC 355707036",
            "ra": 1.3685,
            "dec": -61.2258,
            "tls_results": {
                "tls_detected": True,
                "sde": 9.2,
                "period_days": 0.635,
                "t0_bjd": 1325.68,
                "transit_depth_ppm": 318.5,
                "duration_hours": 0.76
            },
            "planetary_params": {
                "planet_radius_earth": 1.95,
                "semi_major_axis_au": 0.0145,
                "equilibrium_temp_k": 2119.0,
                "classification": "Super-Earth",
                "in_habitable_zone": False
            },
            "veto_results": {
                "odd_even": {"is_eb": False, "delta_depth_sigma": 0.8},
                "secondary": {"secondary_detected": False}
            },
            "is_candidate": True,
            "verdict": "HIGH-CONFIDENCE EXOPLANET CANDIDATE (Super-Earth, Rp=1.95 R⊕, P=0.64d)"
        }

        judgment = CandidateQualityJudge.judge_exoplanet(payload)
        assert judgment["passed"] is True
        assert judgment["verdict"] == "APPROVED_CANDIDATE"
        assert NotificationPolicyJudge.can_notify_telegram("exoplanet", payload) is True

    def test_eclipsing_binary_veto_rejects_candidate(self):
        payload = {
            "target_id": "TIC 999999999",
            "tls_results": {"sde": 12.0},
            "veto_results": {
                "odd_even": {"is_eb": True, "delta_depth_sigma": 5.4},
                "secondary": {"secondary_detected": False}
            },
            "is_candidate": True,
            "verdict": "VETOED (False Positive): Odd-Even EB"
        }

        judgment = CandidateQualityJudge.judge_exoplanet(payload)
        assert judgment["passed"] is False
        assert judgment["verdict"] == "REJECTED_FALSE_POSITIVE"
        assert NotificationPolicyJudge.can_notify_telegram("exoplanet", payload) is False

    def test_secondary_eclipse_veto_rejects_candidate(self):
        payload = {
            "target_id": "TIC 888888888",
            "tls_results": {"sde": 10.5},
            "veto_results": {
                "odd_even": {"is_eb": False},
                "secondary": {"secondary_detected": True}
            },
            "is_candidate": True,
            "verdict": "VETOED (False Positive): Secondary Eclipse"
        }

        judgment = CandidateQualityJudge.judge_exoplanet(payload)
        assert judgment["passed"] is False
        assert NotificationPolicyJudge.can_notify_telegram("exoplanet", payload) is False

    def test_low_sde_threshold_rejects_candidate(self):
        payload = {
            "target_id": "TIC 777777777",
            "tls_results": {"sde": 5.8},  # Below 7.0σ requirement
            "is_candidate": True,
            "verdict": "Weak signal"
        }

        judgment = CandidateQualityJudge.judge_exoplanet(payload)
        assert judgment["passed"] is False
        assert any("TLS SDE" in v for v in judgment["violations"])


class TestSDDArchitectureIntegrity:
    """Tests the architecture integrity guaranteeing multi-modal metric isolation."""

    def test_category_metrics_isolation_passes_judge(self):
        status_payload = {
            "total_processed": 3000,
            "total_candidates": 20,
            "category_metrics": {
                "bh": {"processed": 3000, "candidates": 0},
                "exo": {"processed": 1300, "candidates": 20},
                "transient": {"processed": 1300, "candidates": 0}
            }
        }

        judgment = ArchitectureIntegrityJudge.judge_status_response(status_payload)
        assert judgment["passed"] is True

    def test_inconsistent_candidate_sum_fails_judge(self):
        status_payload = {
            "total_processed": 3000,
            "total_candidates": 50,  # Contradicts sum (0 + 20 + 0 = 20)
            "category_metrics": {
                "bh": {"processed": 3000, "candidates": 0},
                "exo": {"processed": 1300, "candidates": 20},
                "transient": {"processed": 1300, "candidates": 0}
            }
        }

        judgment = ArchitectureIntegrityJudge.judge_status_response(status_payload)
        assert judgment["passed"] is False
        assert any("Inconsistent candidate count" in v for v in judgment["violations"])
