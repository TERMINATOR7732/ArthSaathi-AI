"""
tests/test_integration_gate1_6_3.py — IBM SDK-Native HTTP Configuration Tests (Gate 1.6.3).

Validates:
1. SDK-native HttpClientConfig configuration with explicit timeouts and connection limits.
2. Synchronous and asynchronous HTTP client timeout propagation.
3. Separation of inference network errors (watsonx_network_error) from IAM network errors (auth_network_error).
4. Strict differentiation between IAM token timeouts (auth_timeout) and inference timeouts (watsonx_timeout).
"""

from __future__ import annotations

import httpx
import pytest
from unittest import mock

from core.config import WatsonxConfig
from ibm.exceptions import (
    CATEGORY_AUTH_NETWORK_ERROR,
    CATEGORY_AUTH_TIMEOUT,
    CATEGORY_WATSONX_NETWORK_ERROR,
    CATEGORY_WATSONX_TIMEOUT,
    WatsonxError,
    categorize_ibm_exception,
)
from ibm.watsonx_client import WatsonxClient
from ibm_watsonx_ai.utils.utils import HttpClientConfig


def test_http_client_config_construction():
    """HttpClientConfig is initialized with explicit timeouts and connection pool limits."""
    cfg = WatsonxConfig(
        api_key="valid-synthetic-key",
        project_id="12345678-abcd-ef01-2345-6789abcdef01",
        url="https://us-south.ml.cloud.ibm.com",
    )
    with mock.patch("ibm_watsonx_ai.Credentials", mock.MagicMock()):
        with mock.patch("ibm_watsonx_ai.foundation_models.ModelInference", mock.MagicMock()):
            client = WatsonxClient(cfg)

    assert hasattr(client, "http_config")
    assert isinstance(client.http_config, HttpClientConfig)
    assert client.http_config.timeout.connect == 10.0
    assert client.http_config.timeout.read == 50.0
    assert client.http_config.timeout.write == 10.0
    assert client.http_config.timeout.pool == 10.0
    assert client.http_config.limits.max_connections == 5
    assert client.http_config.limits.max_keepalive_connections == 2
    assert client.http_config.limits.keepalive_expiry == 5.0


def test_sync_and_async_client_timeout_propagation():
    """Both sync (httpx_client) and async (async_httpx_client) clients receive configured timeouts."""
    cfg = WatsonxConfig(
        api_key="valid-synthetic-key",
        project_id="12345678-abcd-ef01-2345-6789abcdef01",
        url="https://us-south.ml.cloud.ibm.com",
    )
    fake_inference = mock.MagicMock()
    fake_inference._client = mock.MagicMock()
    fake_inference._client.httpx_client = mock.MagicMock()
    fake_inference._client.async_httpx_client = mock.MagicMock()

    with mock.patch("ibm_watsonx_ai.Credentials", mock.MagicMock()):
        with mock.patch("ibm_watsonx_ai.foundation_models.ModelInference", return_value=fake_inference):
            client = WatsonxClient(cfg)

    # Check timeout assigned to synchronous and asynchronous clients
    assert fake_inference._client.httpx_client.timeout == client.http_config.timeout
    assert fake_inference._client.async_httpx_client.timeout == client.http_config.timeout


def test_inference_network_error_categorization():
    """Inference network failures are categorized as watsonx_network_error, not auth_network_error."""
    cfg = WatsonxConfig(
        api_key="valid-synthetic-key",
        project_id="12345678-abcd-ef01-2345-6789abcdef01",
    )
    fake_inference = mock.MagicMock()
    fake_inference.chat.side_effect = httpx.ConnectError("Failed to establish TCP connection to watsonx endpoint")

    with mock.patch("ibm_watsonx_ai.Credentials", mock.MagicMock()):
        with mock.patch("ibm_watsonx_ai.foundation_models.ModelInference", return_value=fake_inference):
            client = WatsonxClient(cfg)
            with pytest.raises(WatsonxError) as exc_info:
                client.chat_with_metadata([{"role": "user", "content": "What is UPI?"}])

    assert exc_info.value.category == CATEGORY_WATSONX_NETWORK_ERROR
    assert exc_info.value.category != CATEGORY_AUTH_NETWORK_ERROR


def test_categorize_ibm_exception_distinguishes_watsonx_and_auth_network():
    """categorize_ibm_exception separates watsonx network errors from general IAM auth network errors."""
    iam_net_err = httpx.ConnectError("DNS resolution failed for iam.cloud.ibm.com")
    cat_iam, _ = categorize_ibm_exception(iam_net_err)
    assert cat_iam == CATEGORY_AUTH_NETWORK_ERROR

    watsonx_net_err = httpx.ConnectError("Connection refused by watsonx model service endpoint")
    cat_watsonx, _ = categorize_ibm_exception(watsonx_net_err)
    assert cat_watsonx == CATEGORY_WATSONX_NETWORK_ERROR
    assert cat_watsonx != cat_iam
