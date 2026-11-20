"""
ASTRO SENTINEL - SDD Architectural Rule Engine
Declares and enforces the non-negotiable invariant rules of the observatory.
"""
from enum import Enum
from typing import Dict, Any, List, Tuple


class SDDRuleSeverity(str, Enum):
    BLOCKER = "BLOCKER"
    CRITICAL = "CRITICAL"
    WARNING = "WARNING"


class SDDRule(Enum):
    # Rule 1: No False Positives in Notifications
    RULE_NO_FALSE_POSITIVE_NOTIFICATION = (
        "SDD-R01",
        "Never notify, store as candidate, or display as candidate any target that failed a veto or lacks confirmed candidate status.",
        SDDRuleSeverity.BLOCKER
    )

    # Rule 2: Multi-Modal Metric Independence
    RULE_INDEPENDENT_CATEGORY_METRICS = (
        "SDD-R02",
        "Each observatory modality (Black Holes, Exoplanets, Transients) must report independent, isolated processed counts and candidate counts.",
        SDDRuleSeverity.BLOCKER
    )

    # Rule 3: Category-Isolated Sky Map Rendering
    RULE_CATEGORY_ISOLATED_SKYMAP = (
        "SDD-R03",
        "Aladin Lite sky map must render ONLY markers belonging to the currently active observatory category.",
        SDDRuleSeverity.CRITICAL
    )

    # Rule 4: Inline Detail Rendering (No intrusive modals)
    RULE_INLINE_CARD_DIAGNOSTICS = (
        "SDD-R04",
        "Transit fits, light curves, and diagnostics must be displayed directly inside expandable accordion cards rather than general blocking modals.",
        SDDRuleSeverity.CRITICAL
    )

    # Rule 5: Pure Telegram Notification Channel (Zero SMS/Direct Tel)
    RULE_TELEGRAM_ONLY_ALERTS = (
        "SDD-R05",
        "All candidate alerts must go exclusively through Telegram Bot (@tess_bh_sentinel_bot); zero SMS or direct phone text dispatches.",
        SDDRuleSeverity.BLOCKER
    )

    # Rule 6: Global Privacy Controls
    RULE_GLOBAL_BLUR_PRIVACY = (
        "SDD-R06",
        "Blur Info toggle must be positioned in the global header controls and blur across all categories simultaneously.",
        SDDRuleSeverity.WARNING
    )

    def __init__(self, code: str, description: str, severity: SDDRuleSeverity):
        self.code = code
        self.description = description
        self.severity = severity


class RuleAuditor:
    """Evaluates arbitrary candidate payloads or system states against SDD rules."""

    @staticmethod
    def audit_exoplanet_candidate(data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        violations = []
        is_candidate = data.get("is_candidate") is True
        verdict = str(data.get("verdict", "")).upper()

        # Check for contradictory false positive verdicts
        if not is_candidate:
            violations.append(f"{SDDRule.RULE_NO_FALSE_POSITIVE_NOTIFICATION.code}: is_candidate must be True.")
        for bad_word in ["VETOED", "FALSE POSITIVE", "DISCARDED", "DOES NOT MEET", "ERROR", "NO DATA"]:
            if bad_word in verdict:
                violations.append(f"{SDDRule.RULE_NO_FALSE_POSITIVE_NOTIFICATION.code}: Contradictory verdict containing '{bad_word}'.")

        # Check TLS SDE threshold
        tls = data.get("tls_results", {})
        if tls.get("sde", 0.0) < 7.0:
            violations.append(f"{SDDRule.RULE_NO_FALSE_POSITIVE_NOTIFICATION.code}: TLS SDE ({tls.get('sde')}) is below 7.0σ.")

        # VETO AUDIT REQUIREMENT: Must have explicit passing veto tests
        vetoes = data.get("veto_results") or data.get("veto_audit")
        if not vetoes:
            violations.append(f"{SDDRule.RULE_NO_FALSE_POSITIVE_NOTIFICATION.code}: Missing mandatory veto audit results (Odd-Even and Secondary Eclipse tests required).")
        else:
            if isinstance(vetoes, dict):
                # Format 1: dict of dicts {'odd_even': {'is_eb': False}, 'secondary': {'secondary_detected': False}}
                odd_eb = vetoes.get("odd_even", {}).get("is_eb")
                if odd_eb is True:
                    violations.append(f"{SDDRule.RULE_NO_FALSE_POSITIVE_NOTIFICATION.code}: Odd-Even EB veto was triggered.")
                elif odd_eb is None and not vetoes.get("odd_even_eb_veto"):
                    violations.append(f"{SDDRule.RULE_NO_FALSE_POSITIVE_NOTIFICATION.code}: Incomplete Odd-Even EB veto evaluation.")

                sec_det = vetoes.get("secondary", {}).get("secondary_detected")
                if sec_det is True:
                    violations.append(f"{SDDRule.RULE_NO_FALSE_POSITIVE_NOTIFICATION.code}: Secondary occultation was detected.")
                elif sec_det is None and not vetoes.get("secondary_eclipse_veto"):
                    violations.append(f"{SDDRule.RULE_NO_FALSE_POSITIVE_NOTIFICATION.code}: Incomplete Secondary Eclipse veto evaluation.")

        return (len(violations) == 0, violations)

    @staticmethod
    def audit_black_hole_candidate(data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        violations = []
        assessment = data.get("assessment", {})
        is_candidate = data.get("is_candidate") is True or assessment.get("undocumented_candidate") is True
        verdict = str(assessment.get("verdict", "") or data.get("verdict", "")).upper()

        if not is_candidate:
            violations.append(f"{SDDRule.RULE_NO_FALSE_POSITIVE_NOTIFICATION.code}: is_candidate is False.")
        for bad_word in ["FALSO POSITIVO", "DISCARDED", "DOES NOT MEET", "ERROR", "NO DATA"]:
            if bad_word in verdict:
                violations.append(f"{SDDRule.RULE_NO_FALSE_POSITIVE_NOTIFICATION.code}: Vetoed text '{bad_word}' in verdict.")

        # Auto-verification gate
        auto_ver = data.get("auto_verification") or assessment.get("auto_verification")
        if auto_ver:
            score = auto_ver.get("final_score", 0)
            if score < 60:
                violations.append(f"{SDDRule.RULE_NO_FALSE_POSITIVE_NOTIFICATION.code}: Multi-observatory auto-verification score ({score}) below 60%.")
            if auto_ver.get("status") == "INCONCLUSIVE_OR_STELLAR":
                violations.append(f"{SDDRule.RULE_NO_FALSE_POSITIVE_NOTIFICATION.code}: Auto-verification concluded INCONCLUSIVE_OR_STELLAR.")

        return (len(violations) == 0, violations)
