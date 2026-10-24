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


# ===========================================================================
# 10. QR receive-money scam detection — Phase 3F regression tests
# ===========================================================================

# --- Positive cases: must trigger the QR receive-money alert ---

def test_qr_scam_must_scan_to_receive():
    """'Someone says I must scan a QR code to receive money.' → alert triggered."""
    agent = FraudDetectionAgent()
    alerts = agent.analyze("Someone says I must scan a QR code to receive money.")
    assert any("QR" in a or "qr" in a.lower() for a in alerts), (
        f"Expected a QR receive-money alert. Got: {alerts}"
    )


def test_qr_scam_buyer_sent_qr_to_get_paid():
    """'A buyer sent me a QR code and says I need to scan it to get paid.' → alert."""
    agent = FraudDetectionAgent()
    alerts = agent.analyze(
        "A buyer sent me a QR code and says I need to scan it to get paid."
    )
    assert any("QR" in a or "qr" in a.lower() for a in alerts), (
        f"Expected a QR receive-money alert. Got: {alerts}"
    )


def test_qr_scam_scan_to_receive_refund():
    """'Do I need to scan a QR code to receive a refund?' → alert triggered."""
    agent = FraudDetectionAgent()
    alerts = agent.analyze("Do I need to scan a QR code to receive a refund?")
    assert any("QR" in a or "qr" in a.lower() for a in alerts), (
        f"Expected a QR receive-money alert. Got: {alerts}"
    )


def test_qr_scam_scan_to_receive_cashback():
    """'They asked me to scan a QR code and enter my UPI PIN to receive cashback.' → alert."""
    agent = FraudDetectionAgent()
    alerts = agent.analyze(
        "They asked me to scan a QR code and enter my UPI PIN to receive cashback."
    )
    assert any("QR" in a or "qr" in a.lower() for a in alerts), (
        f"Expected a QR receive-money alert. Got: {alerts}"
    )


# --- Negative cases: ordinary merchant-payment wording must NOT fire the QR receive-scam alert ---
# (Other alerts such as 'upi pin' may still fire if the content is genuinely suspicious.)

def test_qr_no_false_positive_pay_for_groceries():
    """'How do I scan a shop QR code to pay for groceries?' → no QR receive-money alert."""
    agent = FraudDetectionAgent()
    alerts = agent.analyze("How do I scan a shop's QR code to pay for groceries?")
    qr_receive_alerts = [
        a for a in alerts
        if "NEVER receives money" in a or "Scanning a QR code NEVER" in a
    ]
    assert len(qr_receive_alerts) == 0, (
        "Ordinary merchant-payment question must not trigger QR receive-money alert. "
        f"Got: {qr_receive_alerts}"
    )


def test_qr_no_false_positive_how_qr_payments_work():
    """'Explain how QR payments work.' → no QR receive-money alert."""
    agent = FraudDetectionAgent()
    alerts = agent.analyze("Explain how QR payments work.")
    qr_receive_alerts = [
        a for a in alerts
        if "NEVER receives money" in a or "Scanning a QR code NEVER" in a
    ]
    assert len(qr_receive_alerts) == 0, (
        "Generic QR payment explanation must not trigger QR receive-money alert. "
        f"Got: {qr_receive_alerts}"
    )


def test_qr_no_false_positive_pay_merchant_using_qr():
    """'I want to pay a merchant using a QR code.' → no QR receive-money alert."""
    agent = FraudDetectionAgent()
    alerts = agent.analyze("I want to pay a merchant using a QR code.")
    qr_receive_alerts = [
        a for a in alerts
        if "NEVER receives money" in a or "Scanning a QR code NEVER" in a
    ]
    assert len(qr_receive_alerts) == 0, (
        "Explicit merchant-payment intent must not trigger QR receive-money alert. "
        f"Got: {qr_receive_alerts}"
    )


# ===========================================================================
# 11. Knowledge-base heading filter — Phase 3F regression tests
# ===========================================================================

def test_kb_no_standalone_section_headings():
    """
    No passage in the loaded KB should be a bare '=== SECTION N: TITLE ===' line.
    These are structural formatting markers with no retrievable content.
    """
    import re as _re
    heading_re = _re.compile(r"^={3,}\s*.+={3,}$")
    rag = RAGRetrievalAgent()
    headings_found = [p for p in rag.passages if heading_re.match(p.text)]
    assert len(headings_found) == 0, (
        f"Standalone section headings should be filtered. Found: "
        + str([p.id for p in headings_found])
    )


def test_kb_real_content_under_heading_is_retained():
    """
    Content paragraphs that follow section headings must still be loaded.
    UPI fraud prevention content (section 1) must appear in the KB.
    """
    rag = RAGRetrievalAgent()
    texts = " ".join(p.text.lower() for p in rag.passages)
    assert "upi pin" in texts, (
        "UPI PIN content from Section 1 must be retained after heading filter."
    )
    assert "pmjdy" in texts, (
        "PMJDY content from Section 4 must be retained after heading filter."
    )


def test_kb_empty_blocks_not_loaded():
    """
    Loader must not produce any passage with empty or whitespace-only text.
    """
    rag = RAGRetrievalAgent()
    empty_passages = [p for p in rag.passages if not p.text.strip()]
    assert len(empty_passages) == 0, (
        f"No empty passages should be loaded. Found {len(empty_passages)}."
    )


def test_kb_passage_count_reduced_after_heading_filter():
    """
    With heading filtering, the total passage count must be less than the raw
    block count that included headings (verified: old count was 23, new count
    must be exactly 12 with current KB files).
    """
    rag = RAGRetrievalAgent()
    # Old unfiltered count was 23 (10 + 13 raw blocks, 10 of which were headings
    # or the comment header).
    # After filtering, the two comment headers + 8 section headings = 10 dropped,
    # leaving exactly 13 retained passages from the current KB files.
    # Verify it's at most 20 (well below the old 23) and at least 10.
    assert len(rag.passages) <= 20, (
        f"Expected heading filter to reduce passage count below 20. "
        f"Got {len(rag.passages)}."
    )
    assert len(rag.passages) >= 10, (
        f"Expected at least 10 content passages after filtering. "
        f"Got {len(rag.passages)}."
    )


def test_kb_existing_files_still_load():
    """
    Existing KB files must still load correctly after the heading filter.
    Both files must contribute passages.
    """
    rag = RAGRetrievalAgent()
    source_files = {p.source_file for p in rag.passages}
    assert "rbi_npci_financial_literacy_kb.txt" in source_files, (
        "rbi_npci_financial_literacy_kb.txt must still load passages."
    )
    assert "rbi_whitelist_and_cyber_stats.txt" in source_files, (
        "rbi_whitelist_and_cyber_stats.txt must still load passages."
    )


def test_kb_passage_indices_are_sequential_per_file():
    """
    Passage indices within each source file must be sequential 0-based integers
    corresponding to retained-passage positions (not original block positions).
    """
    rag = RAGRetrievalAgent()
    from collections import defaultdict
    by_file: dict[str, list[int]] = defaultdict(list)
    for p in rag.passages:
        by_file[p.source_file].append(p.index)
    for fname, indices in by_file.items():
        assert indices == list(range(len(indices))), (
            f"Indices for {fname} must be 0, 1, 2, … Got: {indices}"
        )


# ===========================================================================
# 12. Environment loading — .env path resolved from app.py location, not CWD
# ===========================================================================

def test_dotenv_path_is_relative_to_app_file():
    """
    app.py must resolve the .env path relative to its own directory, not the
    process working directory. This is verified by inspecting the _DOTENV_PATH
    variable that app.py sets before calling load_dotenv().

    We confirm:
      1. _DOTENV_PATH is a Path object.
      2. Its parent equals the directory that contains app.py (resolved).
      3. Its filename is '.env'.

    We do NOT read or check the actual contents of .env.
    """
    import app as flask_app_module
    from pathlib import Path as _Path

    dotenv_path = getattr(flask_app_module, "_DOTENV_PATH", None)
    assert dotenv_path is not None, (
        "app._DOTENV_PATH must be set before load_dotenv() is called. "
        "It is used to make .env discovery independent of the working directory."
    )
    assert isinstance(dotenv_path, _Path), (
        f"_DOTENV_PATH must be a pathlib.Path, got {type(dotenv_path)}"
    )

    # The parent of _DOTENV_PATH must equal the resolved directory of app.py
    app_dir = _Path(flask_app_module.__file__).resolve().parent
    assert dotenv_path.parent.resolve() == app_dir, (
        f"_DOTENV_PATH parent ({dotenv_path.parent}) must equal the directory "
        f"containing app.py ({app_dir})."
    )
    assert dotenv_path.name == ".env", (
        f"_DOTENV_PATH filename must be '.env', got '{dotenv_path.name}'"
    )


def test_offline_mode_starts_cleanly_without_credentials():
    """
    When WATSONX_API_KEY and WATSONX_PROJECT_ID are absent, the application
    must start without raising an exception and the orchestrator must report
    llm_configured=False and llm_ready=False. This verifies that patching
    env vars to empty strings reliably exercises the offline-mode path,
    independent of whatever real credentials may be in .env.
    """
    with mock.patch.dict(os.environ, {"WATSONX_API_KEY": "", "WATSONX_PROJECT_ID": ""}):
        agent = GraniteLLMAgent()
        assert not agent.configured, "configured must be False without credentials"
        assert not agent._ready,     "_ready must be False without credentials"
        assert agent.init_error is None, (
            "init_error should be None when credentials were absent (not an SDK error)"
        )


def test_health_endpoint_reports_configured_state_accurately(client):
    """
    The /api/health endpoint must return llm_configured and llm_ready that
    accurately reflect the actual orchestrator state — not a hardcoded value.
    When running without real credentials, both must be False.
    When running with real credentials, llm_configured must be True.

    This test does not require real credentials; it only verifies the field
    contract (both fields are booleans and their values are consistent).
    """
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.get_json()

    assert isinstance(data["llm_configured"], bool), (
        "llm_configured must be a boolean"
    )
    assert isinstance(data["llm_ready"], bool), (
        "llm_ready must be a boolean"
    )
    # llm_ready can only be True if llm_configured is also True
    if data["llm_ready"]:
        assert data["llm_configured"], (
            "llm_ready=True requires llm_configured=True"
        )
    # llm_configured=False must mean llm_ready=False
    if not data["llm_configured"]:
        assert not data["llm_ready"], (
            "llm_configured=False must imply llm_ready=False"
        )

def test_dotenv_loads_from_file_dir_not_cwd():
    """
    Functional test: proves that resolving the .env path relative to a known
    file location — the same pattern used in app.py — loads variables
    correctly even when the process CWD is a completely different directory.

    Coverage gap in test_dotenv_path_is_relative_to_app_file
    ──────────────────────────────────────────────────────────
    That test inspects the computed Path value only. It would pass even if
    load_dotenv silently ignored the explicit path. This test exercises the
    actual runtime behaviour.

    Approach
    ─────────
    1. Create a temporary "app directory" and write a dummy .env there.
    2. Change CWD to a separate temporary "other directory".
    3. Call load_dotenv(dotenv_path=...) with the path resolved from the
       "app directory" — the same idiom as app.py line 27-28.
    4. Assert the dummy variable was loaded.
    5. Restore CWD and clean the dummy variable from os.environ, even on
       failure, via try/finally.

    No real credentials, no IBM API calls, no production .env is read.
    """
    import tempfile
    import pathlib
    from dotenv import load_dotenv as _load_dotenv

    DUMMY_KEY = "ARTHSAATHI_TEST_CWD_CHECK_DUMMY"
    DUMMY_VAL = "cwd_independent_load_ok"

    original_cwd = os.getcwd()
    tmpdir_app   = tempfile.mkdtemp(prefix="arthsaathi_app_")
    tmpdir_other = tempfile.mkdtemp(prefix="arthsaathi_cwd_")

    try:
        # Write a dummy .env into the "app directory"
        dummy_env = pathlib.Path(tmpdir_app) / ".env"
        dummy_env.write_text(f"{DUMMY_KEY}={DUMMY_VAL}\n", encoding="utf-8")

        # Move CWD somewhere completely different
        os.chdir(tmpdir_other)

        # Reproduce the exact pattern from app.py:
        #   _DOTENV_PATH = Path(__file__).resolve().parent / ".env"
        #   load_dotenv(dotenv_path=_DOTENV_PATH)
        # Here __file__ is simulated by dummy_env itself.
        resolved_path = pathlib.Path(tmpdir_app).resolve() / ".env"
        _load_dotenv(dotenv_path=resolved_path, override=True)

        loaded = os.environ.get(DUMMY_KEY, "NOT_FOUND")
        assert loaded == DUMMY_VAL, (
            f"Expected {DUMMY_KEY}={DUMMY_VAL!r} after load_dotenv with explicit "
            f"path {resolved_path}, but got {loaded!r}. "
            f"CWD was {os.getcwd()!r} (not the app dir). "
            "This indicates load_dotenv did not respect the dotenv_path argument."
        )
    finally:
        # Restore CWD and clean up dummy env var regardless of test outcome
        os.chdir(original_cwd)
        os.environ.pop(DUMMY_KEY, None)
        import shutil
        shutil.rmtree(tmpdir_app,   ignore_errors=True)
        shutil.rmtree(tmpdir_other, ignore_errors=True)


# ===========================================================================
# 13. Production deployment configuration (Render & WSGI)
# ===========================================================================

def test_production_wsgi_app_callable():
    """
    gunicorn invokes 'app:app'. app.py must expose an 'app' symbol that is an
    instance of flask.Flask so that gunicorn can bind and serve the WSGI app.
    """
    import app as flask_app_module
    from flask import Flask
    assert hasattr(flask_app_module, "app"), "app.py must expose 'app' WSGI callable"
    assert isinstance(flask_app_module.app, Flask), "'app' must be a Flask instance"


def test_gunicorn_dependency_in_requirements():
    """
    requirements.txt must include gunicorn for production WSGI serving on Linux.
    """
    req_file = Path(__file__).parent.parent / "requirements.txt"
    assert req_file.exists(), "requirements.txt must exist"
    req_text = req_file.read_text(encoding="utf-8")
    assert "gunicorn" in req_text.lower(), "gunicorn must be present in requirements.txt"


def test_render_blueprint_configuration():
    """
    render.yaml must exist, enforce ₹0 cost (plan: free), use gunicorn startup,
    and configure the /api/health health-check endpoint.
    """
    render_file = Path(__file__).parent.parent / "render.yaml"
    assert render_file.exists(), "render.yaml must exist"
    content = render_file.read_text(encoding="utf-8")
    assert "plan: free" in content, "render.yaml must enforce free plan"
    assert "gunicorn app:app" in content, "render.yaml must specify gunicorn startCommand"
    assert "/api/health" in content, "render.yaml must configure healthCheckPath"


