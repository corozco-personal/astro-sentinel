"""
ASTRO SENTINEL - SDD Judges & Verification Oracles
Judges act as automated arbiters evaluating system behavior, candidate validity, 
and preventing regression of previously established specifications.
"""
from typing import Dict, Any, List, Optional
from sdd.specs.observatory_rules import RuleAuditor, SDDRule


class CandidateQualityJudge:
    """
    Arbitrates whether an alert dispatch or candidate persistence is mathematically,
    astrophysically, and contractually valid according to SDD specifications.
    """

    @classmethod
    def judge_exoplanet(cls, payload: Dict[str, Any]) -> Dict[str, Any]:
        valid, violations = RuleAuditor.audit_exoplanet_candidate(payload)
        return {
            "passed": valid,
            "violations": violations,
            "judge": cls.__name__,
            "verdict": "APPROVED_CANDIDATE" if valid else "REJECTED_FALSE_POSITIVE"
        }

    @classmethod
    def judge_black_hole(cls, payload: Dict[str, Any]) -> Dict[str, Any]:
        valid, violations = RuleAuditor.audit_black_hole_candidate(payload)
        return {
            "passed": valid,
            "violations": violations,
            "judge": cls.__name__,
            "verdict": "APPROVED_CANDIDATE" if valid else "REJECTED_FALSE_POSITIVE"
        }


class NotificationPolicyJudge:
    """
    Ensures that no dispatch mechanism communicates non-confirmed events.
    """

    @classmethod
    def can_notify_telegram(cls, modality: str, candidate_data: Dict[str, Any]) -> bool:
        if modality == "exoplanet":
            res = CandidateQualityJudge.judge_exoplanet(candidate_data)
            return res["passed"]
        elif modality == "black_hole":
            res = CandidateQualityJudge.judge_black_hole(candidate_data)
            return res["passed"]
        return False


class ArchitectureIntegrityJudge:
    """
    Validates state metrics and API responses to guarantee non-regression:
    - Verifies category metrics independence.
    - Verifies unified candidate counts match true category sums.
    """

    @classmethod
    def judge_status_response(cls, api_status: Dict[str, Any]) -> Dict[str, Any]:
        violations = []
        
        # Check presence of category_metrics
        cat_metrics = api_status.get("category_metrics")
        if not cat_metrics:
            violations.append("Missing 'category_metrics' in /api/status response.")
        else:
            for cat in ["bh", "exo", "transient"]:
                if cat not in cat_metrics:
                    violations.append(f"Missing '{cat}' sub-metrics in category_metrics.")
                else:
                    if "processed" not in cat_metrics[cat] or "candidates" not in cat_metrics[cat]:
                        violations.append(f"Category '{cat}' missing 'processed' or 'candidates' counts.")

        # Check total candidates equality
        if cat_metrics:
            sum_cands = (
                cat_metrics.get("bh", {}).get("candidates", 0) +
                cat_metrics.get("exo", {}).get("candidates", 0) +
                cat_metrics.get("transient", {}).get("candidates", 0)
            )
            reported_total = api_status.get("total_candidates", 0)
            if sum_cands != reported_total:
                violations.append(f"Inconsistent candidate count: sum of categories ({sum_cands}) != total_candidates ({reported_total})")

        return {
            "passed": len(violations) == 0,
            "violations": violations,
            "judge": cls.__name__
        }
