import pytest
import requests
from sdd.judges.verification_judges import ArchitectureIntegrityJudge

BASE_URL = "http://localhost:5055"

def test_api_status_satisfies_sdd_integrity():
    try:
        r = requests.get(f"{BASE_URL}/api/status", timeout=5)
        assert r.status_code == 200, "Server /api/status did not return HTTP 200"
        data = r.json()
        
        # Pass payload through Architecture Integrity Judge
        judgment = ArchitectureIntegrityJudge.judge_status_response(data)
        assert judgment["passed"] is True, f"SDD Architecture Violations: {judgment['violations']}"
        
        # Verify per-category independent numbers
        cat = data.get("category_metrics", {})
        assert "bh" in cat and "exo" in cat and "transient" in cat
        assert cat["bh"]["candidates"] >= 0
        assert cat["exo"]["candidates"] >= 0
        assert cat["transient"]["candidates"] >= 0
    except requests.exceptions.ConnectionError:
        pytest.skip("Server is not currently running for E2E check.")
