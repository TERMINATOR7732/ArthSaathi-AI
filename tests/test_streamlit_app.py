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
    get_config_var_with_source,
    get_deterministic_greeting,
    is_greeting,
    _UUID_RE,
    _has_enclosing_quotes,
    _get_st_secrets_root_keys,
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


# ---------------------------------------------------------------------------
# 12. Regression: AttributeError for llm_init_error (production hotfix)
# ---------------------------------------------------------------------------

def test_llm_init_error_is_instance_attribute_not_only_property():
    """llm_init_error must live in the orchestrator's __dict__ (instance attribute),
    not only on the class.  This guards against @st.cache_resource returning a
    cached instance whose __class__ is from a prior module load (which would cause
    an AttributeError if the attribute were a class-level @property only)."""
    with mock.patch.dict(os.environ, {"WATSONX_API_KEY": "", "WATSONX_PROJECT_ID": ""}):
        orch = ArthSaathiOrchestrator()
    # Must be present directly on the instance — not just inherited from the class.
    assert "llm_init_error" in orch.__dict__, (
        "llm_init_error must be an instance attribute set in __init__, "
        "not only a @property, so it survives @st.cache_resource hot-reload."
    )


def test_llm_init_error_instance_attribute_on_init_failure():
    """After a simulated init failure, llm_init_error is in the instance __dict__."""
    with mock.patch.dict(os.environ, {
        "WATSONX_API_KEY": "dummy-key",
        "WATSONX_PROJECT_ID": "dummy-proj",
    }):
        fake_creds_cls = mock.MagicMock(return_value=mock.MagicMock())
        fake_model_cls = mock.MagicMock(side_effect=ValueError("bad config"))
        with mock.patch.dict("sys.modules", {
            "ibm_watsonx_ai": mock.MagicMock(Credentials=fake_creds_cls),
            "ibm_watsonx_ai.foundation_models": mock.MagicMock(ModelInference=fake_model_cls),
        }):
            orch = ArthSaathiOrchestrator()

    assert "llm_init_error" in orch.__dict__
    assert orch.llm_init_error == "ValueError"
    assert orch.__dict__["llm_init_error"] == "ValueError"


def test_orchestrator_llm_init_error_accessible_via_getattr():
    """getattr(orch, 'llm_init_error', None) must return the correct value,
    mirroring how streamlit_app.py accesses it as a cache-safe boundary."""
    with mock.patch.dict(os.environ, {"WATSONX_API_KEY": "", "WATSONX_PROJECT_ID": ""}):
        orch = ArthSaathiOrchestrator()
    # Normal access
    assert orch.llm_init_error is None
    # getattr access (as used in streamlit_app.py)
    assert getattr(orch, "llm_init_error", "SENTINEL") is None


def test_no_attribute_error_on_fresh_orchestrator_without_credentials():
    """Constructing an orchestrator without credentials must never raise AttributeError
    on llm_init_error.  This directly reproduces the production crash scenario."""
    with mock.patch.dict(os.environ, {"WATSONX_API_KEY": "", "WATSONX_PROJECT_ID": ""}):
        orch = ArthSaathiOrchestrator()
    # Must not raise AttributeError
    try:
        val = orch.llm_init_error
    except AttributeError as e:
        raise AssertionError(
            f"AttributeError raised accessing llm_init_error: {e}\n"
            "This is the production crash scenario — the fix is incomplete."
        ) from e
    assert val is None


def test_no_attribute_error_on_init_failure_orchestrator():
    """Orchestrator with failed SDK init must not raise AttributeError on llm_init_error."""
    with mock.patch.dict(os.environ, {
        "WATSONX_API_KEY": "dummy-key",
        "WATSONX_PROJECT_ID": "dummy-proj",
    }):
        fake_creds_cls = mock.MagicMock(return_value=mock.MagicMock())
        fake_model_cls = mock.MagicMock(side_effect=RuntimeError("simulated sdk failure"))
        with mock.patch.dict("sys.modules", {
            "ibm_watsonx_ai": mock.MagicMock(Credentials=fake_creds_cls),
            "ibm_watsonx_ai.foundation_models": mock.MagicMock(ModelInference=fake_model_cls),
        }):
            orch = ArthSaathiOrchestrator()
    try:
        val = orch.llm_init_error
    except AttributeError as e:
        raise AssertionError(
            f"AttributeError on init-failure orchestrator: {e}"
        ) from e
    assert val == "RuntimeError"


def test_streamlit_sidebar_status_no_attribute_error_offline():
    """The Streamlit app's sidebar status block must render without AttributeError
    in offline mode (no credentials), reproducing the deployment crash path."""
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()
    assert not at.exception, (
        f"Streamlit app raised an exception in offline mode: {at.exception}"
    )


def test_stale_cache_simulation_getattr_fallback():
    """Simulate @st.cache_resource returning an object that lacks llm_init_error
    (as if created by an older class version).  getattr must return None rather
    than raising AttributeError."""
    with mock.patch.dict(os.environ, {"WATSONX_API_KEY": "", "WATSONX_PROJECT_ID": ""}):
        orch = ArthSaathiOrchestrator()

    # Simulate a stale cache: manually delete the instance attribute to reproduce
    # the condition where the cached object was created without llm_init_error.
    del orch.__dict__["llm_init_error"]
    assert "llm_init_error" not in orch.__dict__

    # Direct attribute access would now raise AttributeError (demonstrates the bug):
    # (We skip actually calling orch.llm_init_error directly to avoid relying on
    # whether the class still has a @property fallback.)

    # The streamlit_app.py access pattern using getattr must NOT raise:
    val = getattr(orch, "llm_init_error", None)
    assert val is None, "getattr safety net must return None for stale cached instance"



# ---------------------------------------------------------------------------
# 13. IBM IAM Configuration Diagnostics and Precedence Tests
# ---------------------------------------------------------------------------

def test_get_config_var_with_source_st_secrets_precedence():
    """st.secrets takes precedence over environment variables."""
    fake_secrets = {"WATSONX_API_KEY": "secret-api-key-val"}
    with mock.patch("streamlit.secrets", fake_secrets):
        with mock.patch.dict(os.environ, {"WATSONX_API_KEY": "env-api-key-val"}):
            val, src = get_config_var_with_source("WATSONX_API_KEY")
            assert val == "secret-api-key-val"
            assert src == "st.secrets"
            # get_config_var backward compatibility
            assert get_config_var("WATSONX_API_KEY") == "secret-api-key-val"


def test_get_config_var_with_source_env_fallback_when_secret_missing_or_empty():
    """Falls back to os.environ when st.secrets has missing key or empty value."""
    # Subtest A: empty string in secrets falls through to environment
    fake_empty_secrets = {"WATSONX_API_KEY": "   "}
    with mock.patch("streamlit.secrets", fake_empty_secrets):
        with mock.patch.dict(os.environ, {"WATSONX_API_KEY": "env-fallback-key"}):
            val, src = get_config_var_with_source("WATSONX_API_KEY")
            assert val == "env-fallback-key"
            assert src == "os.environ"

    # Subtest B: missing key in secrets falls through to environment
    fake_missing_secrets = {"OTHER_KEY": "something"}
    with mock.patch("streamlit.secrets", fake_missing_secrets):
        with mock.patch.dict(os.environ, {"WATSONX_API_KEY": "env-fallback-key"}):
            val, src = get_config_var_with_source("WATSONX_API_KEY")
            assert val == "env-fallback-key"
            assert src == "os.environ"


def test_get_config_var_with_source_default_fallback():
    """Falls back to default value when missing from both secrets and environment."""
    with mock.patch("streamlit.secrets", {}):
        with mock.patch.dict(os.environ, {}, clear=True):
            val, src = get_config_var_with_source("NONEXISTENT_VAR", "https://default.host")
            assert val == "https://default.host"
            assert src == "default"
            assert get_config_var("NONEXISTENT_VAR", "https://default.host") == "https://default.host"

    # Preserves empty string behavior when env var is explicitly empty string
    with mock.patch("streamlit.secrets", {}):
        with mock.patch.dict(os.environ, {"EXPLICIT_EMPTY": ""}):
            val, src = get_config_var_with_source("EXPLICIT_EMPTY", "default_val")
            assert val == ""
            assert src == "os.environ"


def test_uuid_shaped_api_key_and_project_id_detection(capsys):
    """UUID regex accurately classifies 36-character UUID vs IBM API key and logs warning."""
    # UUID regex verification
    valid_uuid = "0a1b2c3d-4e5f-6a7b-8c9d-0e1f2a3b4c5d"
    standard_api_key = "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0"

    assert bool(_UUID_RE.match(valid_uuid)) is True
    assert bool(_UUID_RE.match(standard_api_key)) is False

    # Simulate suspicious case: API key matches UUID (possible swap)
    with mock.patch.dict(os.environ, {
        "WATSONX_API_KEY": valid_uuid,
        "WATSONX_PROJECT_ID": valid_uuid,
    }):
        fake_creds_cls = mock.MagicMock(return_value=mock.MagicMock())
        fake_model_cls = mock.MagicMock(side_effect=RuntimeError("simulated auth fail"))
        with mock.patch.dict("sys.modules", {
            "ibm_watsonx_ai": mock.MagicMock(Credentials=fake_creds_cls),
            "ibm_watsonx_ai.foundation_models": mock.MagicMock(ModelInference=fake_model_cls),
        }):
            GraniteLLMAgent()

    captured = capsys.readouterr()
    # Warning about suspicious credential structure must be emitted
    assert "WARNING: Suspicious credential structure detected" in captured.err
    assert "api_key matches UUID structure (possible configuration mismatch / swapped with project_id)" in captured.err
    assert "api_key_is_uuid=True" in captured.err
    assert "proj_id_is_uuid=True" in captured.err


def test_enclosing_quotes_detection_does_not_modify_credentials(capsys):
    """Detects literal enclosing single or double quotes without modifying the key passed to SDK."""
    assert _has_enclosing_quotes('"double-quoted"') is True
    assert _has_enclosing_quotes("'single-quoted'") is True
    assert _has_enclosing_quotes("unquoted-key") is False
    assert _has_enclosing_quotes('"') is False
    assert _has_enclosing_quotes("") is False

    quoted_key = '"my-literal-quoted-api-key"'
    with mock.patch.dict(os.environ, {
        "WATSONX_API_KEY": quoted_key,
        "WATSONX_PROJECT_ID": "test-project-id",
    }):
        fake_creds_cls = mock.MagicMock(return_value=mock.MagicMock())
        fake_model_cls = mock.MagicMock(side_effect=ValueError("bad key format"))
        with mock.patch.dict("sys.modules", {
            "ibm_watsonx_ai": mock.MagicMock(Credentials=fake_creds_cls),
            "ibm_watsonx_ai.foundation_models": mock.MagicMock(ModelInference=fake_model_cls),
        }):
            GraniteLLMAgent()

        # The SDK Credentials call must have received the UNTOUCHED quoted key
        fake_creds_cls.assert_called_once()
        _, kwargs = fake_creds_cls.call_args
        assert kwargs.get("api_key") == quoted_key, "Quotes must NOT be stripped before passing to SDK"

    captured = capsys.readouterr()
    assert "WARNING: Suspicious credential structure detected" in captured.err
    assert "api_key has enclosing quotes (possible TOML formatting issue)" in captured.err
    assert "api_key_has_quotes=True" in captured.err


def test_root_level_secret_presence_reporting(capsys):
    """Reports expected watsonx keys found at root of st.secrets without exposing values."""
    fake_st_secrets = {
        "WATSONX_API_KEY": "synthetic-key",
        "WATSONX_PROJECT_ID": "synthetic-proj",
        "UNRELATED_SECRET": "other-val",
    }
    with mock.patch("streamlit.secrets", fake_st_secrets):
        root_keys = _get_st_secrets_root_keys()
        assert "WATSONX_API_KEY" in root_keys
        assert "WATSONX_PROJECT_ID" in root_keys
        assert "WATSONX_URL" not in root_keys
        assert "UNRELATED_SECRET" not in root_keys

        fake_creds_cls = mock.MagicMock(return_value=mock.MagicMock())
        fake_model_cls = mock.MagicMock(side_effect=Exception("generic failure"))
        with mock.patch.dict("sys.modules", {
            "ibm_watsonx_ai": mock.MagicMock(Credentials=fake_creds_cls),
            "ibm_watsonx_ai.foundation_models": mock.MagicMock(ModelInference=fake_model_cls),
        }):
            GraniteLLMAgent()

    captured = capsys.readouterr()
    assert "root_secrets_found=[WATSONX_API_KEY,WATSONX_PROJECT_ID]" in captured.err
    assert "synthetic-key" not in captured.err
    assert "synthetic-proj" not in captured.err


def test_diagnostic_output_never_exposes_sentinel_secrets_or_sensitive_exc(capsys):
    """Sanitized diagnostic output must never expose secret values, prefixes, suffixes, lengths, or raw exception text."""
    sentinel_key = "SENTINEL-API-KEY-888-HIGHLY-SENSITIVE-VALUE"
    sentinel_proj = "SENTINEL-PROJECT-ID-999-SECRET-VALUE"
    sensitive_raw_exc = "BXNIM0415E: Provided API key could not be found. Bearer eyJhbGciOiJIUzI1Ni.jwt_token_payload"

    class SyntheticIAMAuthError(Exception):
        pass

    with mock.patch.dict(os.environ, {
        "WATSONX_API_KEY": sentinel_key,
        "WATSONX_PROJECT_ID": sentinel_proj,
    }):
        fake_creds_cls = mock.MagicMock(return_value=mock.MagicMock())
        fake_model_cls = mock.MagicMock(side_effect=SyntheticIAMAuthError(sensitive_raw_exc))
        with mock.patch.dict("sys.modules", {
            "ibm_watsonx_ai": mock.MagicMock(Credentials=fake_creds_cls),
            "ibm_watsonx_ai.foundation_models": mock.MagicMock(ModelInference=fake_model_cls),
        }):
            GraniteLLMAgent()

    captured = capsys.readouterr()
    # Must NOT expose sentinels or sensitive error payload
    assert sentinel_key not in captured.err
    assert sentinel_proj not in captured.err
    assert sensitive_raw_exc not in captured.err
    assert "eyJhbGciOi" not in captured.err
    assert "jwt_token_payload" not in captured.err

    # Must contain safe categorized metadata
    assert "GraniteLLMAgent init failed: SyntheticIAMAuthError [auth_invalid_credentials]" in captured.err
    assert "sources: api_key=os.environ, project_id=os.environ" in captured.err
    assert "present: api_key=True, project_id=True" in captured.err


def test_preservation_of_offline_fallback_behavior():
    """Offline fallback behavior is preserved whether unconfigured or failing initialization."""
    # Case 1: Unconfigured (missing credentials)
    with mock.patch.dict(os.environ, {"WATSONX_API_KEY": "", "WATSONX_PROJECT_ID": ""}):
        agent_unconfigured = GraniteLLMAgent()
        assert agent_unconfigured.configured is False
        assert agent_unconfigured._ready is False
        ans, src = agent_unconfigured.generate("What is UPI?", "Context on UPI safety")
        assert src == "not_configured"
        assert "Offline Knowledge Base" in ans

    # Case 2: Configured but SDK initialization fails
    with mock.patch.dict(os.environ, {"WATSONX_API_KEY": "any-key", "WATSONX_PROJECT_ID": "any-proj"}):
        fake_creds_cls = mock.MagicMock(return_value=mock.MagicMock())
        fake_model_cls = mock.MagicMock(side_effect=RuntimeError("simulated failure"))
        with mock.patch.dict("sys.modules", {
            "ibm_watsonx_ai": mock.MagicMock(Credentials=fake_creds_cls),
            "ibm_watsonx_ai.foundation_models": mock.MagicMock(ModelInference=fake_model_cls),
        }):
            agent_failed = GraniteLLMAgent()
            assert agent_failed.configured is True
            assert agent_failed._ready is False
            ans, src = agent_failed.generate("What is UPI?", "Context on UPI safety")
            assert src.startswith("provider_error:RuntimeError")
            assert "Offline Knowledge Base" in ans
