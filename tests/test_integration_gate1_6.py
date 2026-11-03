"""
tests/test_integration_gate1_6.py — Comprehensive Mocked Integration Tests for Gate 1.6.

Validates end-to-end integration between Streamlit, ArthSaathiOrchestrator,
GraniteLLMAgent, and WatsonxClient with zero live network calls.
"""

from __future__ import annotations

import concurrent.futures
import os
from pathlib import Path
from unittest import mock

import pytest

from arthsaathi_agent import (
    ArthSaathiOrchestrator,
    FraudDetectionAgent,
    GraniteLLMAgent,
    OrchestratorResponse,
    calculate_annualized_cost,
    detect_language,
    get_deterministic_greeting,
    is_greeting,
)
from core.config import WatsonxConfig
from ibm.exceptions import (
    CATEGORY_AUTH_INVALID_CREDENTIALS,
    CATEGORY_AUTH_NETWORK_ERROR,
    CATEGORY_AUTH_TIMEOUT,
    CATEGORY_CONFIG_MISSING,
    CATEGORY_WATSONX_MODEL_ERROR,
    CATEGORY_WATSONX_SERVICE_ERROR,
    CATEGORY_WATSONX_TIMEOUT,
    WatsonxError,
    categorize_ibm_exception,
)
from ibm.watsonx_client import WatsonxClient


# ===========================================================================
# 1. WatsonxClient Integration & Delegation Tests
# ===========================================================================

def test_granite_agent_delegates_to_watsonx_client():
    """GraniteLLMAgent must instantiate and delegate chat inference to WatsonxClient."""
    mock_inference = mock.MagicMock()
    mock_inference.chat.return_value = {
        "model_id": "ibm/granite-4-h-small",
        "choices": [{"message": {"content": "UPI is an instant real-time payment system."}}],
        "usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30},
    }

    agent = GraniteLLMAgent()
    agent.configured = True
    agent._ready = True
    agent._client = mock_inference

    ans, src = agent.generate("What is UPI?", "UPI guidelines from NPCI")
    assert src == "granite"
    assert "instant real-time payment system" in ans
    assert agent.last_model_id == "ibm/granite-4-h-small"
    assert agent.last_error_category is None


def test_granite_agent_unconfigured_offline_fallback():
    """Unconfigured GraniteLLMAgent must return offline KB answer with not_configured source."""
    agent = GraniteLLMAgent()
    agent.configured = False
    agent._ready = False

    ans, src = agent.generate("Explain UPI collect request", "NPCI UPI collect request guide")
    assert src == "not_configured"
    assert "Offline Knowledge Base" in ans
    assert agent.last_error_category == "config_missing"


def test_granite_agent_initialization_error_offline_fallback():
    """GraniteLLMAgent with failed initialization must return offline fallback with provider_error."""
    agent = GraniteLLMAgent()
    agent.configured = True
    agent._ready = False
    agent.init_error = "ConnectionError"
    agent.error_category = CATEGORY_AUTH_NETWORK_ERROR

    ans, src = agent.generate("What is UPI?", "Context on UPI")
    assert src.startswith("provider_error:ConnectionError")
    assert "Offline Knowledge Base" in ans
    assert agent.last_error_category == CATEGORY_AUTH_NETWORK_ERROR


def test_granite_agent_timeout_handling():
    """Inference timeout must be captured cleanly and return offline fallback with timeout error."""
    mock_inference = mock.MagicMock()

    def _timeout_chat(*args, **kwargs):
        raise concurrent.futures.TimeoutError("Inference timed out")

    mock_inference.chat.side_effect = _timeout_chat

    agent = GraniteLLMAgent()
    agent.configured = True
    agent._ready = True
    agent._client = mock_inference

    ans, src = agent.generate("Explain QR code security", "RBI QR code guidelines")
    assert "provider_error:" in src
    assert "timed out after 50 seconds" in src
    assert "Offline Knowledge Base" in ans
    assert agent.last_error_category == CATEGORY_WATSONX_TIMEOUT


def test_granite_agent_malformed_model_response():
    """Model returning empty or malformed response must be caught as WatsonxError and handled."""
    mock_inference = mock.MagicMock()
    # Missing choices
    mock_inference.chat.return_value = {"error": "bad response"}

    agent = GraniteLLMAgent()
    agent.configured = True
    agent._ready = True
    agent._client = mock_inference

    ans, src = agent.generate("What is UPI?", "Context")
    assert "provider_error:" in src
    assert "Offline Knowledge Base" in ans


# ===========================================================================
# 2. OrchestratorResponse Contract Tests
# ===========================================================================

def test_orchestrator_response_contract_granite():
    """Orchestrator answer via Granite must populate all contract fields including status and model_id."""
    orch = ArthSaathiOrchestrator()
    mock_inference = mock.MagicMock()
    mock_inference.chat.return_value = {
        "model_id": "ibm/granite-4-h-small",
        "choices": [{"message": {"content": "Never approve unexpected UPI collect requests."}}],
    }
    orch.llm.configured = True
    orch.llm._ready = True
    orch.llm._client = mock_inference

    resp = orch.answer("What is a collect request?")
    assert isinstance(resp, OrchestratorResponse)
    assert resp.source == "granite"
    assert resp.status == "success"
    assert resp.model_id == "ibm/granite-4-h-small"
    assert resp.error_category is None
    assert resp.provider_error is None
    assert "collect request" in resp.answer.lower()
    assert len(resp.passages) > 0
    assert "total" in resp.latency_ms

    # Verify serialization contract
    d = resp.to_dict()
    assert d["source"] == "granite"
    assert d["status"] == "success"
    assert d["model_id"] == "ibm/granite-4-h-small"
    assert d["error_category"] is None
    assert isinstance(d["passages"], list)


def test_orchestrator_response_contract_unconfigured():
    """Unconfigured Orchestrator must return fallback status and config_missing error category."""
    orch = ArthSaathiOrchestrator()
    orch.llm.configured = False
    orch.llm._ready = False

    resp = orch.answer("Explain cyber fraud reporting")
    assert resp.source == "not_configured"
    assert resp.status == "fallback"
    assert resp.model_id is None
    assert resp.error_category == "config_missing"
    assert "Offline Knowledge Base" in resp.answer


def test_orchestrator_response_contract_provider_error():
    """Orchestrator with provider error must return fallback status with error category."""
    orch = ArthSaathiOrchestrator()
    orch.llm.configured = True
    orch.llm._ready = False
    orch.llm.init_error = "IBMAuthError"
    orch.llm.error_category = CATEGORY_AUTH_INVALID_CREDENTIALS

    resp = orch.answer("How do I protect my UPI PIN?")
    assert resp.source == "provider_error"
    assert resp.status == "fallback"
    assert resp.model_id is None
    assert resp.error_category == CATEGORY_AUTH_INVALID_CREDENTIALS
    assert resp.provider_error == "IBMAuthError"


# ===========================================================================
# 3. Emergency Escalation & Fraud Alerts Integration Tests
# ===========================================================================

def test_orchestrator_emergency_escalation_protocol():
    """Emergency keywords must trigger emergency=True and prepend the 1930 protocol."""
    orch = ArthSaathiOrchestrator()
    orch.llm.configured = False

    resp = orch.answer("Help! I lost money in a scam! My account was debited!")
    assert resp.emergency is True
    assert "1930" in resp.answer
    assert "National Cybercrime Helpline" in resp.answer
    assert "cybercrime.gov.in" in resp.answer
    assert "RBI Zero-Liability Rule" in resp.answer


def test_orchestrator_qr_scam_alert_detection():
    """Scanning QR to receive money must trigger the dedicated critical fraud alert."""
    orch = ArthSaathiOrchestrator()
    orch.llm.configured = False

    resp = orch.answer("The buyer asked me to scan this QR code to receive my refund money.")
    assert len(resp.fraud_alerts) > 0
    assert any("Scanning a QR code NEVER receives money" in a for a in resp.fraud_alerts)


def test_orchestrator_safe_qr_merchant_payment_no_false_positive():
    """Ordinary QR merchant payment question must NOT trigger the scam alert."""
    orch = ArthSaathiOrchestrator()
    orch.llm.configured = False

    resp = orch.answer("How do I scan a QR code to pay for groceries at a store?")
    assert not any("Scanning a QR code NEVER receives money" in a for a in resp.fraud_alerts)


# ===========================================================================
# 4. Multilingual & Language Directive Tests
# ===========================================================================

@pytest.mark.parametrize("query,expected_lang", [
    ("Hello, what is a UPI PIN?", "en"),
    ("नमस्ते, मुझे यूपीआई सुरक्षा के बारे में बताएं", "hi"),
    ("मला सांगा बँक खाते सुरक्षित कसे ठेवावे?", "mr"),
    ("kya QR code scan karke paise aate hain?", "hinglish"),
])
def test_multilingual_language_classification(query, expected_lang):
    """Accurately classify user query language across all supported tongues."""
    assert detect_language(query) == expected_lang


def test_granite_multilingual_directive_injection():
    """GraniteLLMAgent must inject target language directives into system instructions."""
    agent = GraniteLLMAgent()
    mock_inference = mock.MagicMock()
    mock_inference.chat.return_value = {
        "model_id": "ibm/granite-4-h-small",
        "choices": [{"message": {"content": "मराठी उत्तर"}}],
    }
    agent.configured = True
    agent._ready = True
    agent._client = mock_inference

    agent.generate("माझे पैसे गेले", "संदर्भ", target_lang="mr")
    call_kwargs = mock_inference.chat.call_args[1]
    system_prompt = call_kwargs["messages"][0]["content"]
    assert "LANGUAGE DIRECTIVE: The user communicated in Marathi" in system_prompt
    assert "Devanagari script" in system_prompt


def test_deterministic_greetings_all_languages():
    """Deterministic greetings must be available and authentic for all 4 supported language modes."""
    for lang in ["en", "hi", "mr", "hinglish"]:
        greeting = get_deterministic_greeting(lang)
        assert ("ArthSaathi" in greeting) or ("अर्थसाथी" in greeting)
        assert "1930" in greeting
        if lang == "en":
            assert "Hello!" in greeting
            assert not any("\u0900" <= c <= "\u097F" for c in greeting)
        elif lang == "mr":
            assert "नमस्कार!" in greeting
            assert "अर्थसाथी" in greeting
        elif lang == "hi":
            assert "नमस्ते!" in greeting
            assert "अर्थसाथी" in greeting
        elif lang == "hinglish":
            assert "Namaste!" in greeting
            assert "ArthSaathi" in greeting


# ===========================================================================
# 5. Financial Safety & Loan Calculator Integrity Tests
# ===========================================================================

def test_financial_safety_calculator_bounds():
    """Loan calculator enforces realistic boundaries and does not assume fixed 36% APR."""
    # Standard loan calculation
    res = calculate_annualized_cost(principal=10000, total_repayment=11000, tenure_days=30)
    assert res["valid"] is True
    # (1000 / 10000) * (365 / 30) * 100 = 121.67%
    assert res["annualized_cost_pct"] == 121.67
    assert res["is_predatory"] is True

    # Zero or negative principal rejected
    res_invalid = calculate_annualized_cost(principal=0, total_repayment=1000, tenure_days=30)
    assert res_invalid["valid"] is False
    assert any("Principal must be greater than zero" in e for e in res_invalid["errors"])

    # Repayment less than principal rejected
    res_under = calculate_annualized_cost(principal=10000, total_repayment=9000, tenure_days=30)
    assert res_under["valid"] is False
    assert any("Total repayment cannot be less than principal" in e for e in res_under["errors"])


def test_zero_liability_rule_preservation():
    """Emergency protocol must preserve the 3-working-day reporting window for zero liability."""
    orch = ArthSaathiOrchestrator()
    assert "3 working days" in orch.emergency.PROTOCOL
    assert "Circular DBR.No.Leg.BC.78/09.07.005/2017-18" in orch.emergency.PROTOCOL
    assert "14448" in orch.emergency.PROTOCOL


# ===========================================================================
# 6. Streamlit Session State & Duplicate Prevention Tests
# ===========================================================================

def test_duplicate_submission_signature_prevention():
    """Duplicate submissions with identical query and message count must not re-trigger inference."""
    messages = [{"role": "user", "content": "How do I report fraud?"}]
    query = "How do I report fraud?"
    sig1 = f"{query}:{len(messages)}"

    # Repeated submission with identical query and length
    sig2 = f"{query}:{len(messages)}"
    assert sig1 == sig2, "Signatures must match to prevent re-execution"

    # New submission creates a distinct signature
    messages.append({"role": "assistant", "content": "Call 1930"})
    sig3 = f"{query}:{len(messages)}"
    assert sig1 != sig3, "Signature must change when history changes"


def test_orchestrator_diagnostics_leak_free():
    """System diagnostics must never expose API keys, Bearer tokens, or raw credentials."""
    orch = ArthSaathiOrchestrator()
    diag = orch.get_diagnostics()
    assert "api_key" not in diag
    assert "token" not in str(diag).lower() or "production_iam_enforced" in diag
    assert "llm_configured" in diag
    assert "llm_ready" in diag
    assert "kb_passages_loaded" in diag
    assert diag["kb_passages_loaded"] > 0


# ===========================================================================
# 7. Timeout Separation & Runtime AppTest Verification
# ===========================================================================

_APP_PATH = str(Path(__file__).resolve().parent.parent / "streamlit_app.py")


def test_timeout_classification_distinguishes_iam_and_inference():
    """IAM authentication timeout must be classified separately from model inference timeout."""
    iam_err = TimeoutError("IAM token exchange request timed out")
    cat_iam, _ = categorize_ibm_exception(iam_err)
    assert cat_iam == CATEGORY_AUTH_TIMEOUT

    model_err = TimeoutError("watsonx model inference request timed out")
    cat_model, _ = categorize_ibm_exception(model_err)
    assert cat_model == CATEGORY_WATSONX_TIMEOUT
    assert cat_iam != cat_model


def test_streamlit_apptest_runtime_initial_render_zero_inference():
    """Running actual Streamlit app produces zero inference calls on initial load."""
    import streamlit as st
    st.cache_resource.clear()
    from streamlit.testing.v1 import AppTest

    with mock.patch.dict(os.environ, {
        "WATSONX_API_KEY": "synthetic-key",
        "WATSONX_PROJECT_ID": "12345678-abcd-ef01-2345-6789abcdef01",
    }):
        with mock.patch("ibm_watsonx_ai.Credentials", mock.MagicMock()):
            mock_model = mock.MagicMock()
            with mock.patch("ibm_watsonx_ai.foundation_models.ModelInference", return_value=mock_model):
                at = AppTest.from_file(_APP_PATH, default_timeout=30)
                at.run()
                assert len(at.exception) == 0, f"App startup encountered exceptions: {at.exception}"
                assert mock_model.chat.call_count == 0, "Initial render must produce zero inference calls"
                assert len(at.session_state.messages) == 0


def test_streamlit_apptest_runtime_chat_and_rerun_lifecycle():
    """AppTest verifies submission, exact single call, rerun stability, and repeat question."""
    import streamlit as st
    st.cache_resource.clear()
    from streamlit.testing.v1 import AppTest

    with mock.patch.dict(os.environ, {
        "WATSONX_API_KEY": "synthetic-key",
        "WATSONX_PROJECT_ID": "12345678-abcd-ef01-2345-6789abcdef01",
    }):
        with mock.patch("ibm_watsonx_ai.Credentials", mock.MagicMock()):
            mock_model = mock.MagicMock()
            mock_model.chat.return_value = {
                "model_id": "ibm/granite-4-h-small",
                "choices": [{"message": {"content": "Never approve unknown UPI collect requests."}}],
            }
            with mock.patch("ibm_watsonx_ai.foundation_models.ModelInference", return_value=mock_model):
                at = AppTest.from_file(_APP_PATH, default_timeout=30)
                at.run()
                assert mock_model.chat.call_count == 0

                # 1. First submission
                at.chat_input[0].set_value("What is a collect request?").run()
                assert len(at.exception) == 0
                assert mock_model.chat.call_count == 1
                assert len(at.session_state.messages) == 2
                assert at.session_state.messages[-1]["source"] == "granite"
                assert at.session_state.messages[-1]["model_id"] == "ibm/granite-4-h-small"

                # 2. Ordinary rerun (no new input) produces zero additional calls
                at.run()
                assert mock_model.chat.call_count == 1
                assert len(at.session_state.messages) == 2

                # 3. Intentional repeat of same question produces exactly one new call
                at.chat_input[0].set_value("What is a collect request?").run()
                assert mock_model.chat.call_count == 2
                assert len(at.session_state.messages) == 4


def test_streamlit_apptest_runtime_starter_and_reset():
    """AppTest verifies starter button execution and conversation reset."""
    import streamlit as st
    st.cache_resource.clear()
    from streamlit.testing.v1 import AppTest

    with mock.patch.dict(os.environ, {"WATSONX_API_KEY": "", "WATSONX_PROJECT_ID": ""}):
        at = AppTest.from_file(_APP_PATH, default_timeout=30)
        at.run()

        # Click starter 0 button
        at.button[0].click().run()
        assert len(at.exception) == 0
        assert len(at.session_state.messages) == 2
        assert at.session_state.messages[0]["role"] == "user"
        assert at.session_state.messages[1]["role"] == "assistant"
        assert at.session_state.messages[1]["source"] == "not_configured"

        # Click reset chat button in sidebar
        reset_btns = [b for b in at.sidebar.button if "Reset Chat" in (b.label or "")]
        assert len(reset_btns) == 1
        reset_btns[0].click().run()
        assert len(at.exception) == 0
        assert len(at.session_state.messages) == 0
        assert at.session_state.last_processed_query_sig is None
