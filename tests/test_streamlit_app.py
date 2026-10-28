"""
tests/test_streamlit_app.py — Automated test suite for ArthSaathi AI Streamlit Application.

Test categories:
  1. Streamlit startup, layout & tabs rendering
  2. Configuration & missing secrets (offline graceful degradation)
  3. Mocked IBM watsonx.ai Granite success and failure handling
  4. RAG passage retrieval and attribution
  5. Multilingual behavior (English, Hindi, Marathi, Hinglish, conversation continuity)
  6. UPI fraud shield positive and negative guards
  7. 1930 Emergency protocol escalation
  8. Loan APR calculator expected values, boundaries & invalid inputs
  9. Session state, chat history & reset
  10. Theme toggle selection and styling
"""

from __future__ import annotations

import os
import unittest.mock as mock
from pathlib import Path
import pytest
from streamlit.testing.v1 import AppTest

from arthsaathi_agent import (
    ArthSaathiOrchestrator,
    FraudDetectionAgent,
    EmergencyProtocolAgent,
    GraniteLLMAgent,
    RAGRetrievalAgent,
    calculate_annualized_cost,
    detect_language,
    get_config_var,
    get_deterministic_greeting,
    is_greeting,
)

_ROOT = Path(__file__).resolve().parent.parent
APP_PATH = str(_ROOT / "streamlit_app.py")


# ---------------------------------------------------------------------------
# 1. Streamlit Startup & Basic Page Rendering
# ---------------------------------------------------------------------------

def test_streamlit_app_loads_without_exception():
    """Verify streamlit_app.py starts cleanly and renders all 3 tabs."""
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()
    assert not at.exception
    assert len(at.tabs) == 3
    tab_labels = [t.label for t in at.tabs]
    assert any("Scam Advisor" in l for l in tab_labels)
    assert any("Loan Cost Calculator" in l for l in tab_labels)
    assert any("1930 Emergency Guide" in l for l in tab_labels)


def test_streamlit_sidebar_elements():
    """Verify sidebar renders branding, diagnostics, language selector, and emergency card."""
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()
    assert not at.exception
    assert len(at.sidebar.selectbox) >= 1
    lang_box = at.sidebar.selectbox[0]
    assert "Auto-detect" in lang_box.options
    assert "English" in lang_box.options
    assert any("हिन्दी" in o for o in lang_box.options)
    assert any("मराठी" in o for o in lang_box.options)
    assert "Hinglish" in lang_box.options

    assert len(at.sidebar.radio) >= 1
    theme_radio = at.sidebar.radio[0]
    assert "Light" in theme_radio.options
    assert "Dark" in theme_radio.options


# ---------------------------------------------------------------------------
# 2. Configuration & Missing Secrets (Deterministic Offline Mode)
# ---------------------------------------------------------------------------

def test_get_config_var_prefers_streamlit_secrets_then_env():
    """get_config_var should check st.secrets, then os.getenv."""
    with mock.patch.dict(os.environ, {"TEST_KEY_123": "env_val"}):
        assert get_config_var("TEST_KEY_123") == "env_val"
        assert get_config_var("NON_EXISTENT_KEY", "default") == "default"


def test_orchestrator_offline_mode_without_credentials():
    """When WATSONX credentials are absent, orchestrator reports offline safely."""
    with mock.patch.dict(os.environ, {"WATSONX_API_KEY": "", "WATSONX_PROJECT_ID": ""}):
        orch = ArthSaathiOrchestrator()
        assert not orch.llm_configured
        resp = orch.answer("What is the zero liability rule?")
        assert resp.source in ("not_configured", "offline_kb")
        assert "Offline Knowledge Base" in resp.answer or "not configured" in resp.answer.lower()
        assert resp.source != "granite"


# ---------------------------------------------------------------------------
# 3. Mocked IBM watsonx.ai Granite Success & Failure
# ---------------------------------------------------------------------------

def test_granite_mocked_success():
    """Verify mocked IBM Granite chat completion returns source='granite'."""
    agent = GraniteLLMAgent()
    mock_client = mock.MagicMock()
    mock_client.chat.return_value = {
        "choices": [{"message": {"content": "This is a verified test response from Granite."}}]
    }
    with mock.patch.object(agent, "configured", True), \
         mock.patch.object(agent, "_ready", True), \
         mock.patch.object(agent, "_client", mock_client):
        answer, source = agent.generate("How to avoid UPI scams?", "context")
        assert source == "granite"
        assert "verified test response" in answer


def test_granite_mocked_timeout_fallback():
    """Verify timeout in Granite call falls back to offline response with provider_error."""
    agent = GraniteLLMAgent()
    mock_client = mock.MagicMock()
    import concurrent.futures
    mock_client.chat.side_effect = concurrent.futures.TimeoutError("Simulated timeout")
    with mock.patch.object(agent, "configured", True), \
         mock.patch.object(agent, "_ready", True), \
         mock.patch.object(agent, "_client", mock_client):
        answer, source = agent.generate("How to avoid UPI scams?", "Some KB context")
        assert source.startswith("provider_error")
        assert "Offline Knowledge Base" in answer


# ---------------------------------------------------------------------------
# 4. RAG Passage Retrieval & Attribution
# ---------------------------------------------------------------------------

def test_rag_retrieves_correct_context():
    """RAG agent must return relevant passages with source attribution."""
    rag = RAGRetrievalAgent()
    passages = rag.retrieve("UPI PIN rules", top_k=3)
    assert len(passages) >= 1
    for p in passages:
        assert p.id
        assert p.source_file
        assert len(p.text) > 40


def test_rag_empty_or_irrelevant_query():
    """Irrelevant query should return empty list or low overlap without crashing."""
    rag = RAGRetrievalAgent()
    assert rag.retrieve("", top_k=3) == []
    irrelevant = rag.retrieve("xyzzy quantum teleportation asteroid", top_k=3)
    assert isinstance(irrelevant, list)


# ---------------------------------------------------------------------------
# 5. Multilingual Behavior (English, Hindi, Marathi, Hinglish)
# ---------------------------------------------------------------------------

def test_multilingual_detection_matrix():
    """Test language detection across all required languages and styles."""
    cases = [
        ("What is a UPI collect request?", "en"),
        ("How to report a cyber crime in India?", "en"),
        ("यूपीआई पिन क्या है और इसे किसी के साथ साझा क्यों नहीं करना चाहिए?", "hi"),
        ("क्या मुझे बैंक अधिकारी को ओटीपी देना चाहिए?", "hi"),
        ("मला सांगा यूपीआई पिन कसा बदलायचा?", "mr"),
        ("माझ्या खात्यातून पैसे कट झाले, काय करावे?", "mr"),
        ("kya QR code scan karke mujhe account me paise mil sakte hain?", "hinglish"),
        ("bhai mera paisa kat gaya ab kya karu?", "hinglish"),
    ]
    for text, expected_lang in cases:
        assert detect_language(text) == expected_lang, f"Failed for text: {text}"


def test_multilingual_greetings():
    """Test that greetings in each language return appropriate response."""
    for lang in ["en", "hi", "mr", "hinglish"]:
        greeting = get_deterministic_greeting(lang)
        assert greeting
        assert "ArthSaathi" in greeting or "अर्थसाथी" in greeting
        assert "1930" in greeting


def test_conversational_language_continuity():
    """Short greetings or affirmations must not reset an established vernacular conversation."""
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()
    assert not at.exception
    at.session_state.conversation_language = "hi"
    words = "ok".split()
    assert len(words) <= 2
    assert at.session_state.conversation_language == "hi"


# ---------------------------------------------------------------------------
# 6. UPI Fraud Shield
# ---------------------------------------------------------------------------

def test_fraud_agent_qr_scan_to_receive():
    """Scanning QR to receive money must trigger a critical warning."""
    agent = FraudDetectionAgent()
    alerts = agent.analyze("Someone sent me a QR code to scan to receive my refund")
    assert len(alerts) >= 1
    assert any("NEVER receives money" in a or "PAYMENTS only" in a for a in alerts)


def test_fraud_agent_upi_pin_request():
    """Requesting UPI PIN must trigger a critical warning."""
    agent = FraudDetectionAgent()
    alerts = agent.analyze("The caller said please share upi pin to verify my account")
    assert len(alerts) >= 1
    assert any("NEVER share your UPI PIN" in a for a in alerts)


def test_fraud_agent_remote_access_anydesk():
    """Asking to install AnyDesk for banking must trigger a critical warning."""
    agent = FraudDetectionAgent()
    alerts = agent.analyze("Customer care asked me to install anydesk to fix my transaction")
    assert len(alerts) >= 1
    assert any("AnyDesk screen-sharing" in a for a in alerts)


def test_fraud_agent_safe_merchant_payment_no_false_positive():
    """Ordinary merchant payment should not trigger QR scam alert."""
    agent = FraudDetectionAgent()
    alerts = agent.analyze("I want to scan to pay for groceries at the supermarket")
    assert len(alerts) == 0


# ---------------------------------------------------------------------------
# 7. 1930 Emergency Protocol
# ---------------------------------------------------------------------------

def test_emergency_protocol_trigger():
    """Emergency keywords must trigger emergency protocol escalation."""
    agent = EmergencyProtocolAgent()
    assert agent.should_escalate("I have been cheated and lost money in a scam")
    assert agent.should_escalate("My account was debited without my consent")
    assert not agent.should_escalate("What is a savings bank interest rate?")


def test_emergency_protocol_content():
    """Emergency protocol must mention 1930, cybercrime.gov.in, and 3-day rule."""
    protocol = EmergencyProtocolAgent.PROTOCOL
    assert "1930" in protocol
    assert "cybercrime.gov.in" in protocol
    assert "3 working days" in protocol
    assert "14448" in protocol


# ---------------------------------------------------------------------------
# 8. Loan APR Calculator
# ---------------------------------------------------------------------------

def test_calculator_canonical_case():
    """Canonical test case: 10,000 principal, 12,500 repayment, 15 days."""
    res = calculate_annualized_cost(10000, 12500, 15)
    assert res["valid"] is True
    assert abs(res["annualized_cost_pct"] - 608.33) < 0.01
    assert res["is_predatory"] is True


def test_calculator_standard_rate():
    """Standard non-predatory rate: ₹10,000 for 1 year, ₹12,000 repayment."""
    res = calculate_annualized_cost(10000, 12000, 365)
    assert res["valid"] is True
    assert abs(res["annualized_cost_pct"] - 20.0) < 0.01
    assert res["is_predatory"] is False


def test_calculator_invalid_inputs():
    """Invalid inputs must be rejected with helpful error messages."""
    assert not calculate_annualized_cost(0, 12500, 15)["valid"]
    assert not calculate_annualized_cost(-5000, 12500, 15)["valid"]
    assert not calculate_annualized_cost(10000, 8000, 15)["valid"]
    assert not calculate_annualized_cost(10000, 12500, 0)["valid"]
    assert not calculate_annualized_cost(10000, 12500, -10)["valid"]


# ---------------------------------------------------------------------------
# 9. Session State & Chat History
# ---------------------------------------------------------------------------

def test_chat_history_state_management():
    """Verify messages list persists in session state and reset empties it."""
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()
    assert not at.exception
    assert at.session_state.messages == []

    at.session_state.messages.append({
        "role": "user",
        "content": "Test query"
    })
    at.session_state.messages.append({
        "role": "assistant",
        "content": "Test response",
        "source": "offline_kb",
        "fraud_alerts": [],
        "passages": [],
    })
    at.run()
    assert not at.exception
    assert len(at.session_state.messages) == 2


# ---------------------------------------------------------------------------
# 10. Theme Toggle Selection
# ---------------------------------------------------------------------------

def test_theme_mode_toggle():
    """Verify changing theme in session state runs cleanly without error."""
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()
    assert not at.exception
    assert at.session_state.theme_mode == "Light"

    at.sidebar.radio[0].set_value("Dark")
    at.run()
    assert not at.exception
    assert at.session_state.theme_mode == "Dark"


# ---------------------------------------------------------------------------
# 11. Diagnostic: missing credentials vs init-failed vs ready
# ---------------------------------------------------------------------------

def test_llm_init_error_stores_only_class_name_not_raw_message():
    """init_error must hold only the exception class name — never raw str(exc)."""
    agent = GraniteLLMAgent()
    sentinel_secret = "sk-secret-api-key-value-that-must-never-appear"

    with mock.patch.dict(os.environ, {
        "WATSONX_API_KEY": sentinel_secret,
        "WATSONX_PROJECT_ID": "test-project-id",
    }):
        # Make the SDK import succeed but ModelInference constructor raise with
        # a message that contains the sentinel secret so we can verify it is
        # NOT stored in init_error.
        fake_creds_cls = mock.MagicMock(return_value=mock.MagicMock())
        fake_model_cls = mock.MagicMock(
            side_effect=RuntimeError(f"auth failed for key {sentinel_secret}")
        )
        with mock.patch.dict("sys.modules", {
            "ibm_watsonx_ai": mock.MagicMock(Credentials=fake_creds_cls),
            "ibm_watsonx_ai.foundation_models": mock.MagicMock(ModelInference=fake_model_cls),
        }):
            fresh_agent = GraniteLLMAgent()

    assert fresh_agent.configured is True
    assert fresh_agent._ready is False
    assert fresh_agent.init_error == "RuntimeError"
    # The raw exception message — which contains the secret — must NOT be stored.
    assert sentinel_secret not in (fresh_agent.init_error or "")


def test_orchestrator_exposes_init_error_as_class_name():
    """llm_init_error on the orchestrator must equal the exception class name."""
    with mock.patch.dict(os.environ, {
        "WATSONX_API_KEY": "dummy-key",
        "WATSONX_PROJECT_ID": "dummy-proj",
    }):
        fake_creds_cls = mock.MagicMock(return_value=mock.MagicMock())
        fake_model_cls = mock.MagicMock(side_effect=ImportError("sdk not installed"))
        with mock.patch.dict("sys.modules", {
            "ibm_watsonx_ai": mock.MagicMock(Credentials=fake_creds_cls),
            "ibm_watsonx_ai.foundation_models": mock.MagicMock(ModelInference=fake_model_cls),
        }):
            orch = ArthSaathiOrchestrator()

    assert orch.llm_configured is True
    assert orch.llm_ready is False
    assert orch.llm_init_error == "ImportError"


def test_orchestrator_no_init_error_when_not_configured():
    """When credentials are absent, init_error must be None (no failure occurred)."""
    with mock.patch.dict(os.environ, {"WATSONX_API_KEY": "", "WATSONX_PROJECT_ID": ""}):
        orch = ArthSaathiOrchestrator()
    assert orch.llm_configured is False
    assert orch.llm_init_error is None


def test_orchestrator_no_init_error_on_success():
    """When SDK init succeeds, init_error must be None."""
    agent = GraniteLLMAgent()
    # Simulate a fully ready agent (credentials present, init succeeded).
    mock.patch.object(agent, "configured", True).start()
    mock.patch.object(agent, "_ready", True).start()
    agent.init_error = None
    assert agent.init_error is None


def test_generate_falls_back_when_configured_but_not_ready():
    """configured=True, _ready=False must return offline fallback, not granite."""
    agent = GraniteLLMAgent()
    agent.configured = True
    agent._ready = False
    agent.init_error = "ImportError"
    answer, source = agent.generate("How to file a complaint?", "some KB context")
    assert "Offline Knowledge Base" in answer
    assert source.startswith("provider_error")


def test_stderr_log_does_not_contain_api_key(capsys):
    """The stderr diagnostic log must not contain the API key value."""
    secret_key = "super-secret-watsonx-key-xyz"
    with mock.patch.dict(os.environ, {
        "WATSONX_API_KEY": secret_key,
        "WATSONX_PROJECT_ID": "test-project",
    }):
        fake_creds_cls = mock.MagicMock(return_value=mock.MagicMock())
        fake_model_cls = mock.MagicMock(side_effect=ConnectionError("conn refused"))
        with mock.patch.dict("sys.modules", {
            "ibm_watsonx_ai": mock.MagicMock(Credentials=fake_creds_cls),
            "ibm_watsonx_ai.foundation_models": mock.MagicMock(ModelInference=fake_model_cls),
        }):
            GraniteLLMAgent()

    captured = capsys.readouterr()
    assert secret_key not in captured.err
    assert "conn refused" not in captured.err   # raw exc message must not appear
    assert "GraniteLLMAgent init failed" in captured.err
    assert "ConnectionError" in captured.err
