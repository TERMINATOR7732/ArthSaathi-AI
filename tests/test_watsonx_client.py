"""
tests/test_watsonx_client.py — Tests for ibm/watsonx_client.py wrapper.

Covers:
- Unconfigured graceful degradation state.
- ModelInference construction with canonical credentials.
- Handling of authentication, project, model, and timeout errors.
- Mocked chat inference execution.
- Safe diagnostic output.
"""

import concurrent.futures
import unittest.mock as mock
import pytest

from core.config import WatsonxConfig
from ibm.exceptions import (
    CATEGORY_AUTH_INVALID_CREDENTIALS,
    CATEGORY_AUTH_TIMEOUT,
    CATEGORY_CONFIG_MISSING,
    CATEGORY_WATSONX_MODEL_ERROR,
    CATEGORY_WATSONX_SERVICE_ERROR,
    CATEGORY_WATSONX_TIMEOUT,
    WatsonxError,
)
from ibm.watsonx_client import WatsonxClient


# ===========================================================================
# 1. State & Lifecycle Tests
# ===========================================================================

def test_watsonx_client_unconfigured_when_empty():
    cfg = WatsonxConfig(api_key="", project_id="")
    client = WatsonxClient(cfg)
    assert client.configured is False
    assert client.is_ready is False
    assert client.error_category == CATEGORY_CONFIG_MISSING


def test_watsonx_client_initialization_success():
    cfg = WatsonxConfig(
        api_key="valid-synthetic-key",
        project_id="12345678-abcd-ef01-2345-6789abcdef01",
        url="https://us-south.ml.cloud.ibm.com",
    )
    fake_creds_cls = mock.MagicMock(return_value=mock.MagicMock())
    fake_model_cls = mock.MagicMock(return_value=mock.MagicMock())

    with mock.patch("ibm_watsonx_ai.Credentials", fake_creds_cls):
        with mock.patch("ibm_watsonx_ai.foundation_models.ModelInference", fake_model_cls):
            client = WatsonxClient(cfg)

    assert client.configured is True
    assert client.is_ready is True
    assert client.init_error is None
    assert client.error_category is None


def test_watsonx_client_initialization_failure():
    cfg = WatsonxConfig(
        api_key="bad-synthetic-key",
        project_id="12345678-abcd-ef01-2345-6789abcdef01",
        url="https://us-south.ml.cloud.ibm.com",
    )
    fake_creds_cls = mock.MagicMock(return_value=mock.MagicMock())
    fake_model_cls = mock.MagicMock(
        side_effect=RuntimeError("BXNIM0415E: Provided API key could not be found.")
    )

    with mock.patch("ibm_watsonx_ai.Credentials", fake_creds_cls):
        with mock.patch("ibm_watsonx_ai.foundation_models.ModelInference", fake_model_cls):
            client = WatsonxClient(cfg)

    assert client.configured is True
    assert client.is_ready is False
    assert client.init_error == "RuntimeError"
    assert client.error_category == CATEGORY_AUTH_INVALID_CREDENTIALS


# ===========================================================================
# 2. Inference & Error Separation Tests
# ===========================================================================

def test_watsonx_client_chat_not_ready_raises():
    cfg = WatsonxConfig(api_key="", project_id="")
    client = WatsonxClient(cfg)
    with pytest.raises(WatsonxError) as exc_info:
        client.chat([{"role": "user", "content": "hello"}])
    assert "not ready" in str(exc_info.value)


def test_watsonx_client_chat_success():
    cfg = WatsonxConfig(
        api_key="valid-key",
        project_id="12345678-abcd-ef01-2345-6789abcdef01",
    )
    mock_inference = mock.MagicMock()
    mock_inference.chat.return_value = {
        "choices": [{"message": {"content": "ArthSaathi financial safety answer."}}]
    }

    with mock.patch("ibm_watsonx_ai.Credentials", mock.MagicMock()):
        with mock.patch("ibm_watsonx_ai.foundation_models.ModelInference", return_value=mock_inference):
            client = WatsonxClient(cfg)
            response = client.chat([{"role": "user", "content": "What is UPI?"}])

    assert response == "ArthSaathi financial safety answer."


def test_watsonx_client_chat_timeout_handling():
    cfg = WatsonxConfig(
        api_key="valid-key",
        project_id="12345678-abcd-ef01-2345-6789abcdef01",
    )
    mock_inference = mock.MagicMock()
    # Simulate timeout in chat
    mock_inference.chat.side_effect = concurrent.futures.TimeoutError()

    with mock.patch("ibm_watsonx_ai.Credentials", mock.MagicMock()):
        with mock.patch("ibm_watsonx_ai.foundation_models.ModelInference", return_value=mock_inference):
            client = WatsonxClient(cfg)
            with pytest.raises(WatsonxError) as exc_info:
                client.chat([{"role": "user", "content": "What is UPI?"}], timeout=0.1)

    assert exc_info.value.category == CATEGORY_WATSONX_TIMEOUT
    assert "timed out" in str(exc_info.value)


def test_watsonx_client_chat_malformed_response():
    cfg = WatsonxConfig(
        api_key="valid-key",
        project_id="12345678-abcd-ef01-2345-6789abcdef01",
    )
    mock_inference = mock.MagicMock()
    # Missing 'choices' in response
    mock_inference.chat.return_value = {"status": "ok"}

    with mock.patch("ibm_watsonx_ai.Credentials", mock.MagicMock()):
        with mock.patch("ibm_watsonx_ai.foundation_models.ModelInference", return_value=mock_inference):
            client = WatsonxClient(cfg)
            with pytest.raises(WatsonxError) as exc_info:
                client.chat([{"role": "user", "content": "What is UPI?"}])

    assert exc_info.value.category == CATEGORY_WATSONX_MODEL_ERROR
    assert "Malformed model response" in str(exc_info.value)


# ===========================================================================
# 3. Diagnostic Reporting Tests
# ===========================================================================

def test_watsonx_client_safe_diagnostics():
    sentinel_key = "MY-SECRET-KEY-ABC-123"
    cfg = WatsonxConfig(
        api_key=sentinel_key,
        project_id="12345678-abcd-ef01-2345-6789abcdef01",
        url="https://us-south.ml.cloud.ibm.com/",
    )
    with mock.patch("ibm_watsonx_ai.Credentials", mock.MagicMock()):
        with mock.patch("ibm_watsonx_ai.foundation_models.ModelInference", mock.MagicMock()):
            client = WatsonxClient(cfg)
            diag = client.get_safe_diagnostics()

    assert sentinel_key not in str(diag)
    assert diag["configured"] is True
    assert diag["llm_ready"] is True
    assert diag["endpoint_host"] == "us-south.ml.cloud.ibm.com"
    assert diag["endpoint_normalized"] is True
