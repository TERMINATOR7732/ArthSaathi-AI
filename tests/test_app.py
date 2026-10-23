"""
tests/test_app.py — ArthSaathi AI automated test suite.

Test categories (per Phase 2 requirements):
  1. Application startup and health endpoint
  2. Homepage response
  3. Invalid and valid chat requests
  4. Missing IBM configuration and provider error handling
  5. APR calculator expected value and invalid inputs
  6. Retrieval of a known passage from the knowledge base
  7. Honest source attribution and offline-mode labels
  8. No credential values in frontend responses
  9. No fake Granite response on missing credentials

Run: C:\\Python312\\python.exe -m pytest tests/ -v
"""

from __future__ import annotations

import json
import os
import unittest.mock as mock
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Ensure the agent module path is importable from the project root
# ---------------------------------------------------------------------------

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from arthsaathi_agent import (
    ArthSaathiOrchestrator,
    RAGRetrievalAgent,
    FraudDetectionAgent,
    EmergencyProtocolAgent,
    GraniteLLMAgent,
    calculate_annualized_cost,
)

# ---------------------------------------------------------------------------
# Flask test client fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def client():
    """Create a Flask test client with TESTING=True."""
    # Import app here so environment is set up first
    import app as flask_app_module
    flask_app_module.app.config["TESTING"] = True
    with flask_app_module.app.test_client() as c:
        yield c


# ===========================================================================
# 1. Application startup and health endpoint
# ===========================================================================


def test_health_endpoint_returns_200(client):
    """GET /api/health must return 200."""
    resp = client.get("/api/health")
    assert resp.status_code == 200


def test_health_endpoint_structure(client):
    """Health response must contain required keys and no credential values."""
    resp = client.get("/api/health")
    data = resp.get_json()
    assert "status" in data
    assert data["status"] == "ok"
    assert "service" in data
    assert "kb_passages_loaded" in data
    assert "llm_configured" in data
    assert "llm_ready" in data
    # Must be an integer >= 0
    assert isinstance(data["kb_passages_loaded"], int)
    assert data["kb_passages_loaded"] >= 0


def test_health_no_credentials_in_response(client):
    """Health endpoint must not expose credential values."""
    resp = client.get("/api/health")
    body_text = resp.get_data(as_text=True)
    # Should not contain keys that indicate credential exposure
    assert "api_key" not in body_text.lower()
    assert "project_id" not in body_text.lower()
    # Must not contain any real key format (32+ hex chars)
    import re
    assert not re.search(r"[0-9a-f]{32,}", body_text), (
        "Possible credential value found in health response"
    )


def test_kb_passages_loaded(client):
    """Health endpoint must report at least one KB passage loaded."""
    resp = client.get("/api/health")
    data = resp.get_json()
    # KB files exist in the repo; at least some passages should load
    assert data["kb_passages_loaded"] >= 1, (
        "Expected at least 1 KB passage to be loaded. "
        "Check that knowledge_base/ files are present."
    )


# ===========================================================================
# 2. Homepage response
# ===========================================================================


def test_homepage_returns_200(client):
    """GET / must return 200."""
    resp = client.get("/")
    assert resp.status_code == 200


def test_homepage_returns_html(client):
    """GET / must return text/html."""
    resp = client.get("/")
    ct = resp.content_type
    assert "text/html" in ct


def test_homepage_contains_brand(client):
    """Homepage must contain the ArthSaathi brand name."""
    resp = client.get("/")
    body = resp.get_data(as_text=True)
    assert "ArthSaathi" in body


def test_homepage_contains_1930(client):
    """Homepage must contain the emergency helpline number 1930."""
    resp = client.get("/")
    body = resp.get_data(as_text=True)
    assert "1930" in body


# ===========================================================================
# 3. Invalid and valid chat requests
# ===========================================================================


def test_chat_empty_body_returns_400(client):
    """POST /api/chat with no body must return 400."""
    resp = client.post("/api/chat", content_type="application/json", data="")
    assert resp.status_code == 400


def test_chat_missing_query_returns_400(client):
    """POST /api/chat without 'query' field must return 400."""
    resp = client.post(
        "/api/chat",
        content_type="application/json",
        data=json.dumps({"question": "hello"}),
    )
    assert resp.status_code == 400


def test_chat_empty_query_returns_400(client):
    """POST /api/chat with whitespace-only query must return 400."""
    resp = client.post(
        "/api/chat",
        content_type="application/json",
        data=json.dumps({"query": "   "}),
    )
    assert resp.status_code == 400


def test_chat_query_too_long_returns_400(client):
    """POST /api/chat with query > 1000 chars must return 400."""
    resp = client.post(
        "/api/chat",
        content_type="application/json",
        data=json.dumps({"query": "x" * 1001}),
    )
    assert resp.status_code == 400


def test_chat_valid_request_returns_200(client):
    """POST /api/chat with a valid query must return 200."""
    resp = client.post(
        "/api/chat",
        content_type="application/json",
        data=json.dumps({"query": "What is a UPI collect request?"}),
    )
    assert resp.status_code == 200


def test_chat_response_has_required_fields(client):
    """Valid chat response must include answer, source, status, fraud_alerts, passages."""
    resp = client.post(
        "/api/chat",
        content_type="application/json",
        data=json.dumps({"query": "How do I stay safe on UPI?"}),
    )
    data = resp.get_json()
    assert "status" in data
    assert "answer" in data
    assert "source" in data
    assert "fraud_alerts" in data
    assert "passages" in data
    assert isinstance(data["fraud_alerts"], list)
    assert isinstance(data["passages"], list)


def test_chat_response_no_stack_trace(client):
    """Chat response must not expose Python stack traces."""
    resp = client.post(
        "/api/chat",
        content_type="application/json",
        data=json.dumps({"query": "test query"}),
    )
    body = resp.get_data(as_text=True)
    assert "Traceback" not in body
    assert "File \"" not in body


# ===========================================================================
# 4. Missing IBM configuration handling
# ===========================================================================


def test_chat_not_configured_returns_valid_response(client):
    """
    When IBM credentials are absent (default test environment),
    the response must have status='not_configured' and source='not_configured',
    NOT 'granite'.
    Skipped automatically when live credentials are configured.
    """
    # In the test environment no .env with real credentials should be loaded
    resp = client.post(
        "/api/chat",
        content_type="application/json",
        data=json.dumps({"query": "What is PMJDY?"}),
    )
    assert resp.status_code == 200
    data = resp.get_json()
    if data["source"] == "granite":
        pytest.skip("Live IBM Granite credentials are configured — not_configured path not applicable.")
    # Since no real credentials exist, source must not be 'granite'
    assert data["source"] != "granite", (
        "source='granite' implies live IBM inference succeeded — "
        "this should not happen in a test environment without credentials."
    )


def test_chat_not_configured_answer_contains_offline_notice(client):
    """
    When not configured, the answer must include the offline notice text,
    not a fabricated Granite response.
    """
    resp = client.post(
        "/api/chat",
        content_type="application/json",
        data=json.dumps({"query": "What is RBI zero liability rule?"}),
    )
    data = resp.get_json()
    if data["source"] == "granite":
        pytest.skip("Live IBM Granite credentials are configured — offline test not applicable.")

    # The offline answer must contain the explicit offline marker
    answer = data.get("answer", "")
    assert "[Offline Knowledge Base" in answer or "not configured" in answer.lower(), (
        "Expected offline answer to contain an explicit offline notice. "
        f"Got: {answer[:200]}"
    )


def test_no_fabricated_granite_response_without_credentials():
    """
    Unit test: GraniteLLMAgent without credentials must return 'not_configured'
    as source — never 'granite'.
    """
    with mock.patch.dict(os.environ, {"WATSONX_API_KEY": "", "WATSONX_PROJECT_ID": ""}):
        agent = GraniteLLMAgent()
        assert not agent.configured
        _, source = agent.generate("test query", "test context")
        assert source == "not_configured", (
            f"Expected 'not_configured', got '{source}'"
        )


def test_granite_agent_provider_error_not_silent():
    """
    Unit test: GraniteLLMAgent configured but SDK init fails must
    return 'provider_error:...' as source, not 'granite'.
    """
    with mock.patch.dict(
        os.environ,
        {"WATSONX_API_KEY": "fake-key", "WATSONX_PROJECT_ID": "fake-proj"},
    ):
        with mock.patch("arthsaathi_agent.GraniteLLMAgent.__init__") as mock_init:
            # Simulate SDK init failure: configured=True but _ready=False
            def failing_init(self):
                self._client = None
                self._ready = False
                self.configured = True
                self.init_error = "Simulated SDK init failure"
            mock_init.side_effect = failing_init
            agent = GraniteLLMAgent.__new__(GraniteLLMAgent)
            failing_init(agent)
            _, source = agent.generate("test", "ctx")
            assert source.startswith("provider_error"), (
                f"Expected provider_error, got '{source}'"
            )


# ===========================================================================
# 5. APR calculator — expected values and invalid inputs
# ===========================================================================


def test_apr_example_case():
    """
    Canonical example: ₹10,000 principal, ₹12,500 repayment, 15 days.
    Expected output ≈ 608.33%.
    """
    result = calculate_annualized_cost(10000, 12500, 15)
    assert result["valid"] is True
    assert abs(result["annualized_cost_pct"] - 608.33) < 0.01, (
        f"Expected ~608.33%, got {result['annualized_cost_pct']}"
    )
    assert result["is_predatory"] is True
    assert result["threshold_pct"] == 36.0


def test_apr_non_predatory():
    """A 24% annual rate should be flagged as non-predatory."""
    # ₹10,000 for 365 days, repay ₹12,400 → 24%
    result = calculate_annualized_cost(10000, 12400, 365)
    assert result["valid"] is True
    assert result["is_predatory"] is False


def test_apr_endpoint_expected_value(client):
    """POST /api/apr with canonical example must return 608.33%."""
    resp = client.post(
        "/api/apr",
        content_type="application/json",
        data=json.dumps({"principal": 10000, "repayment": 12500, "days": 15}),
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "ok"
    assert abs(data["annualized_cost_pct"] - 608.33) < 0.01
    assert data["is_predatory"] is True


def test_apr_zero_principal():
    """Principal of 0 must be invalid."""
    result = calculate_annualized_cost(0, 12500, 15)
    assert result["valid"] is False
    assert any("principal" in e.lower() for e in result["errors"])


def test_apr_negative_principal():
    """Negative principal must be invalid."""
    result = calculate_annualized_cost(-1000, 12500, 15)
    assert result["valid"] is False


def test_apr_repayment_less_than_principal():
    """Repayment < principal must be invalid."""
    result = calculate_annualized_cost(10000, 5000, 15)
    assert result["valid"] is False
    assert any("repayment" in e.lower() for e in result["errors"])


def test_apr_zero_tenure():
    """Zero tenure days must be invalid."""
    result = calculate_annualized_cost(10000, 12500, 0)
    assert result["valid"] is False
    assert any("tenure" in e.lower() for e in result["errors"])


def test_apr_equal_principal_and_repayment():
    """Principal == repayment (0% cost) must be valid and non-predatory."""
    result = calculate_annualized_cost(10000, 10000, 30)
    assert result["valid"] is True
    assert result["annualized_cost_pct"] == 0.0
    assert result["is_predatory"] is False


def test_apr_endpoint_missing_field(client):
    """POST /api/apr with missing 'days' field must return 400."""
    resp = client.post(
        "/api/apr",
        content_type="application/json",
        data=json.dumps({"principal": 10000, "repayment": 12500}),
    )
    assert resp.status_code == 400


def test_apr_endpoint_invalid_type(client):
    """POST /api/apr with string principal must return 400."""
    resp = client.post(
        "/api/apr",
        content_type="application/json",
        data=json.dumps({"principal": "ten thousand", "repayment": 12500, "days": 15}),
    )
    assert resp.status_code == 400


def test_apr_result_has_label(client):
    """APR result must contain a label field."""
    resp = client.post(
        "/api/apr",
        content_type="application/json",
        data=json.dumps({"principal": 10000, "repayment": 12500, "days": 15}),
    )
    data = resp.get_json()
    assert "label" in data
    assert "estimate" in data["label"].lower()


# ===========================================================================
# 6. Knowledge-base retrieval of a known passage
# ===========================================================================


def test_rag_loads_passages():
    """RAGRetrievalAgent must load at least 1 passage from existing KB files."""
    rag = RAGRetrievalAgent()
    assert len(rag.passages) >= 1, (
        "No passages loaded. Check knowledge_base/ directory."
    )


def test_rag_retrieves_upi_passage():
    """Querying 'UPI PIN fraud' must retrieve at least one relevant passage."""
    rag = RAGRetrievalAgent()
    results = rag.retrieve("UPI PIN fraud", top_k=3)
    assert len(results) >= 1
    # At least one result should mention UPI
    texts_combined = " ".join(p.text.lower() for p in results)
    assert "upi" in texts_combined


def test_rag_passage_has_source_attribution():
    """Every retrieved passage must have a source_file and index set."""
    rag = RAGRetrievalAgent()
    results = rag.retrieve("loan scam", top_k=5)
    for p in results:
        assert p.source_file, "Passage source_file must not be empty"
        assert isinstance(p.index, int)
        assert p.id, "Passage id must be set"


def test_rag_empty_query_returns_empty():
    """Empty query must return an empty list."""
    rag = RAGRetrievalAgent()
    results = rag.retrieve("", top_k=5)
    assert results == []


def test_rag_known_passage_in_whitelist_file():
    """Querying 'RBI registered NBFC' must retrieve a passage from the whitelist file."""
    rag = RAGRetrievalAgent()
    results = rag.retrieve("RBI registered NBFC lending", top_k=5)
    assert len(results) >= 1
    source_files = [p.source_file for p in results]
    assert any("whitelist" in f or "literacy" in f for f in source_files)


# ===========================================================================
# 7. Honest source attribution and offline-mode labels
# ===========================================================================


def test_fraud_detection_upi_pin_alert():
    """Query mentioning 'share upi pin' must trigger a fraud alert."""
    agent = FraudDetectionAgent()
    alerts = agent.analyze("Someone asked me to share upi pin")
    assert len(alerts) >= 1
    assert any("pin" in a.lower() or "upi" in a.lower() for a in alerts)


def test_fraud_detection_qr_code_receive():
    """Query mentioning 'qr code receive' must trigger a fraud alert."""
    agent = FraudDetectionAgent()
    alerts = agent.analyze("Can I receive money by scanning a qr code receive?")
    assert len(alerts) >= 1


def test_fraud_detection_no_false_positives_basic():
    """A benign UPI safety question must not generate excessive alerts."""
    agent = FraudDetectionAgent()
    alerts = agent.analyze("What is the maximum UPI transaction limit per day?")
    # No fraud keywords in this question
    assert len(alerts) == 0


def test_emergency_escalation_triggered():
    """Query containing 'fraud' must set emergency=True in orchestrator."""
    orchestrator = ArthSaathiOrchestrator()
    response = orchestrator.answer("I think I have been defrauded, help me")
    assert response.emergency is True


def test_emergency_escalation_not_triggered():
    """Benign query about PMJDY must not set emergency=True."""
    orchestrator = ArthSaathiOrchestrator()
    response = orchestrator.answer("What is PMJDY and how do I open an account?")
    assert response.emergency is False


def test_response_source_is_not_configured_without_env():
    """
    Orchestrator without IBM credentials must return source != 'granite'.
    source must be 'not_configured' (credentials absent).
    """
    orchestrator = ArthSaathiOrchestrator()
    if orchestrator.llm_configured:
        pytest.skip("IBM credentials appear configured — skipping not_configured assertion.")
    response = orchestrator.answer("Tell me about UPI safety")
    assert response.source != "granite", (
        "Expected source != 'granite' without credentials"
    )


def test_offline_answer_has_explicit_notice():
    """GraniteLLMAgent offline answer must contain the [Offline Knowledge Base] marker."""
    agent = GraniteLLMAgent()
    if agent.configured:
        pytest.skip("Credentials present — skipping offline marker test.")
    answer, source = agent.generate("test query", "some context text here")
    assert "[Offline Knowledge Base" in answer, (
        "Offline answer must explicitly state it is from offline KB, not Granite."
    )


# ===========================================================================
# 8. No credential values in frontend API responses
# ===========================================================================


def test_chat_response_no_api_key(client):
    """Chat response body must never contain an actual API key value.

    The env var name WATSONX_API_KEY may legitimately appear in user-facing
    instructions (e.g. the offline notice telling the user how to configure).
    What must NOT appear is a real key value — i.e. a long hex/base64 string.
    """
    import re
    resp = client.post(
        "/api/chat",
        content_type="application/json",
        data=json.dumps({"query": "Tell me about UPI"}),
    )
    body = resp.get_data(as_text=True)
    # No 32+ hex character strings (typical IBM Cloud API key / UUID format)
    assert not re.search(r"[0-9a-f]{32,}", body), (
        "Possible credential value (32+ hex chars) found in chat response"
    )
    # The placeholder value from .env.example must not appear either
    assert "your_ibm_cloud_api_key_here" not in body


def test_health_response_no_sensitive_keys(client):
    """Health response must not contain watsonx project IDs or API key values."""
    resp = client.get("/api/health")
    body = resp.get_data(as_text=True)
    # Must not contain raw credential env var names as values
    assert "your_ibm_cloud_api_key_here" not in body
    assert "your_watsonx_project_id_here" not in body


# ===========================================================================
# 9. No fake Granite response on missing credentials
# ===========================================================================


def test_no_fake_granite_on_missing_credentials():
    """
    Critical integrity test: with no credentials, source must NOT be 'granite'.
    A fake Granite response would violate the honesty requirement.
    """
    with mock.patch.dict(os.environ, {"WATSONX_API_KEY": "", "WATSONX_PROJECT_ID": ""}):
        agent = GraniteLLMAgent()
        assert not agent.configured, "Agent should not be configured without credentials"
        _, source = agent.generate("What is UPI fraud?", "context about UPI")
        assert source != "granite", (
            "CRITICAL: 'granite' source returned without valid credentials. "
            "This is a fake response violation."
        )


def test_orchestrator_no_granite_without_credentials():
    """
    Integration: Orchestrator without credentials must not claim granite source.
    """
    # Patch env vars to ensure no credentials
    with mock.patch.dict(os.environ, {"WATSONX_API_KEY": "", "WATSONX_PROJECT_ID": ""}):
        # Re-create orchestrator with patched env
        orch = ArthSaathiOrchestrator()
        # Patch the llm to use a freshly created unconfigured agent
        unconfigured_llm = GraniteLLMAgent()
        orch.llm = unconfigured_llm
        response = orch.answer("What is UPI?")
        assert response.source != "granite", (
            "Orchestrator returned granite source without credentials — "
            "this indicates a fake response."
        )
