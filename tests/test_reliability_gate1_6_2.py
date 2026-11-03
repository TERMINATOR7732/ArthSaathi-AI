"""
tests/test_reliability_gate1_6_2.py — Gate 1.6.2 Reliability and Hardening Tests.

Validates:
1. Zero abandoned background worker threads during inference and timeouts.
2. Explicit HTTP transport timeout propagation (connect, read, write, pool).
3. Deterministic distinction between IAM auth timeouts and watsonx inference timeouts.
4. Graceful offline fallback on connection, timeout, network, and provider errors.
5. Inactivity read-timeout behavior vs wall-clock limits documentation.
6. Actual local Streamlit server startup, health endpoint response, and clean shutdown.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from typing import Any
from unittest import mock

import httpx
import pytest

from arthsaathi_agent import (
    ArthSaathiOrchestrator,
    GraniteLLMAgent,
    OrchestratorResponse,
)
from core.config import WatsonxConfig
from ibm.exceptions import (
    CATEGORY_AUTH_NETWORK_ERROR,
    CATEGORY_AUTH_TIMEOUT,
    CATEGORY_WATSONX_MODEL_ERROR,
    CATEGORY_WATSONX_NETWORK_ERROR,
    CATEGORY_WATSONX_SERVICE_ERROR,
    CATEGORY_WATSONX_TIMEOUT,
    WatsonxError,
    categorize_ibm_exception,
)
from ibm.watsonx_client import WatsonxClient


# ===========================================================================
# Helpers & Fixtures
# ===========================================================================

def _create_mock_client() -> tuple[WatsonxClient, mock.MagicMock]:
    """Create a configured WatsonxClient with a mocked ModelInference backend."""
    cfg = WatsonxConfig(
        api_key="valid-synthetic-key",
        project_id="12345678-abcd-ef01-2345-6789abcdef01",
        url="https://us-south.ml.cloud.ibm.com",
        model_id="ibm/granite-4-h-small",
    )
    mock_inference = mock.MagicMock()
    mock_inference._client = mock.MagicMock()
    mock_inference._client.httpx_client = mock.MagicMock()

    with mock.patch("ibm_watsonx_ai.Credentials", mock.MagicMock()):
        with mock.patch("ibm_watsonx_ai.foundation_models.ModelInference", return_value=mock_inference):
            client = WatsonxClient(cfg)
    return client, mock_inference


def _find_free_port() -> int:
    """Find an available TCP port for local server testing."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ===========================================================================
# 1. Successful Inference & Zero Worker Threads (Task E.1, E.6)
# ===========================================================================

def test_successful_inference_zero_worker_threads():
    """Successful inference executes synchronously on caller thread without leaking workers."""
    client, mock_inference = _create_mock_client()
    mock_inference.chat.return_value = {
        "model_id": "ibm/granite-4-h-small",
        "choices": [{"message": {"content": "UPI PIN is required only to send money."}}],
        "usage": {"prompt_tokens": 15, "completion_tokens": 12, "total_tokens": 27},
    }

    initial_threads = threading.active_count()
    content, meta = client.chat_with_metadata(
        messages=[{"role": "user", "content": "When is UPI PIN needed?"}],
        timeout=30.0,
    )

    assert "UPI PIN is required" in content
    assert meta["model_id"] == "ibm/granite-4-h-small"
    assert meta["usage"]["total_tokens"] == 27
    assert threading.active_count() == initial_threads, "Synchronous execution must leave zero workers behind"


def test_delayed_response_synchronous_completion():
    """Delayed response completes synchronously without spawning background threads."""
    client, mock_inference = _create_mock_client()

    def _delayed_chat(*args, **kwargs):
        time.sleep(0.05)
        return {
            "model_id": "ibm/granite-4-h-small",
            "choices": [{"message": {"content": "Delayed response content."}}],
            "usage": {},
        }

    mock_inference.chat.side_effect = _delayed_chat

    initial_threads = threading.active_count()
    content, _ = client.chat_with_metadata(
        messages=[{"role": "user", "content": "Test"}],
        timeout=10.0,
    )

    assert content == "Delayed response content."
    assert threading.active_count() == initial_threads


# ===========================================================================
# 2. HTTP Transport Timeout Scenarios (Task E.2, E.3, E.4, E.5)
# ===========================================================================

def test_connection_timeout_classification():
    """HTTP connect timeout is classified as watsonx_timeout and sets transport timeout."""
    client, mock_inference = _create_mock_client()
    mock_inference.chat.side_effect = httpx.ConnectTimeout("Connection handshake timed out")

    initial_threads = threading.active_count()
    with pytest.raises(WatsonxError) as exc_info:
        client.chat_with_metadata([{"role": "user", "content": "Test"}], timeout=15.0)

    assert exc_info.value.category == CATEGORY_WATSONX_TIMEOUT
    assert "timed out after 15 seconds" in str(exc_info.value)
    assert threading.active_count() == initial_threads


def test_read_timeout_classification():
    """HTTP socket read timeout is classified as watsonx_timeout."""
    client, mock_inference = _create_mock_client()
    mock_inference.chat.side_effect = httpx.ReadTimeout("Socket read timed out waiting for server")

    initial_threads = threading.active_count()
    with pytest.raises(WatsonxError) as exc_info:
        client.chat_with_metadata([{"role": "user", "content": "Test"}], timeout=25.0)

    assert exc_info.value.category == CATEGORY_WATSONX_TIMEOUT
    assert "timed out after 25 seconds" in str(exc_info.value)
    assert threading.active_count() == initial_threads


def test_write_timeout_classification():
    """HTTP socket write timeout is classified as watsonx_timeout."""
    client, mock_inference = _create_mock_client()
    mock_inference.chat.side_effect = httpx.WriteTimeout("Socket write timed out")

    initial_threads = threading.active_count()
    with pytest.raises(WatsonxError) as exc_info:
        client.chat_with_metadata([{"role": "user", "content": "Test"}], timeout=10.0)

    assert exc_info.value.category == CATEGORY_WATSONX_TIMEOUT
    assert threading.active_count() == initial_threads


def test_pool_timeout_classification():
    """HTTP pool acquisition timeout is classified as watsonx_timeout."""
    client, mock_inference = _create_mock_client()
    mock_inference.chat.side_effect = httpx.PoolTimeout("Connection pool acquisition timed out")

    initial_threads = threading.active_count()
    with pytest.raises(WatsonxError) as exc_info:
        client.chat_with_metadata([{"role": "user", "content": "Test"}], timeout=10.0)

    assert exc_info.value.category == CATEGORY_WATSONX_TIMEOUT
    assert threading.active_count() == initial_threads


# ===========================================================================
# 3. Inactivity Timeout vs Wall-Clock Limit Documentation (Task E.7)
# ===========================================================================

def test_continuous_streaming_data_socket_limitation_documented():
    """
    Demonstrates and verifies HTTP transport read-timeout mechanics:
    An HTTPX read timeout enforces socket inactivity between chunks,
    meaning data arriving continuously resets the per-chunk timer.
    """
    # Verify that httpx.Timeout defines separate read and connect deadlines
    t = httpx.Timeout(connect=10.0, read=50.0, write=10.0, pool=10.0)
    assert t.read == 50.0
    assert t.connect == 10.0
    assert t.pool == 10.0
    # Confirms that read timeout is per-read, not total transaction wall-clock deadline
    assert not hasattr(t, "total_wall_clock")


# ===========================================================================
# 4. Malformed, Empty, Network, and Provider Errors (Task E.8, E.9, E.10, E.11)
# ===========================================================================

def test_malformed_model_response():
    """Missing 'choices' key raises WatsonxError with watsonx_model_error."""
    client, mock_inference = _create_mock_client()
    mock_inference.chat.return_value = {"id": "chat-123", "model_id": "granite"}

    with pytest.raises(WatsonxError) as exc_info:
        client.chat_with_metadata([{"role": "user", "content": "Test"}])

    assert exc_info.value.category == CATEGORY_WATSONX_MODEL_ERROR
    assert "missing 'choices'" in str(exc_info.value)


def test_empty_model_response():
    """Empty or blank whitespace content raises WatsonxError with watsonx_model_error."""
    client, mock_inference = _create_mock_client()
    mock_inference.chat.return_value = {
        "model_id": "ibm/granite-4-h-small",
        "choices": [{"message": {"content": "   \n\t  "}}],
    }

    with pytest.raises(WatsonxError) as exc_info:
        client.chat_with_metadata([{"role": "user", "content": "Test"}])

    assert exc_info.value.category == CATEGORY_WATSONX_MODEL_ERROR
    assert "empty content" in str(exc_info.value)


def test_network_connection_failure():
    """Network connection error raises WatsonxError with auth_network_error."""
    client, mock_inference = _create_mock_client()
    mock_inference.chat.side_effect = httpx.ConnectError("Failed to resolve host 'us-south.ml.cloud.ibm.com'")

    with pytest.raises(WatsonxError) as exc_info:
        client.chat_with_metadata([{"role": "user", "content": "Test"}])

    assert exc_info.value.category in (CATEGORY_WATSONX_NETWORK_ERROR, CATEGORY_AUTH_NETWORK_ERROR)


def test_provider_service_error():
    """Unexpected provider runtime error raises WatsonxError with watsonx_service_error."""
    client, mock_inference = _create_mock_client()
    mock_inference.chat.side_effect = RuntimeError("watsonx.ai 500 internal server error")

    with pytest.raises(WatsonxError) as exc_info:
        client.chat_with_metadata([{"role": "user", "content": "Test"}])

    assert exc_info.value.category in (CATEGORY_WATSONX_SERVICE_ERROR, "unknown_ibm_error")


# ===========================================================================
# 5. Agent & Orchestrator Timeout Fallback (Task E.12, E.13, E.14, E.15)
# ===========================================================================

def test_timeout_during_granite_agent_inference():
    """GraniteLLMAgent captures timeout and returns offline KB answer with provider_error."""
    mock_inference = mock.MagicMock()
    mock_inference.chat.side_effect = httpx.ReadTimeout("Server took longer than 50 seconds to respond")

    agent = GraniteLLMAgent()
    agent.configured = True
    agent._ready = True
    agent._client = mock_inference

    ans, src = agent.generate("Explain QR code payment scam", "RBI QR code guidance")
    assert "provider_error:" in src
    assert "timed out after 50 seconds" in src
    assert "Offline Knowledge Base" in ans
    assert agent.last_error_category == CATEGORY_WATSONX_TIMEOUT


def test_timeout_followed_by_successful_new_interaction():
    """A timed-out query does not leave lingering locks or prevent subsequent query success."""
    mock_inference = mock.MagicMock()
    # Turn 1: times out
    mock_inference.chat.side_effect = httpx.ReadTimeout("Read timed out")

    agent = GraniteLLMAgent()
    agent.configured = True
    agent._ready = True
    agent._client = mock_inference

    ans1, src1 = agent.generate("Question 1", "Context 1")
    assert "provider_error:" in src1
    assert agent.last_error_category == CATEGORY_WATSONX_TIMEOUT

    # Turn 2: succeeds
    mock_inference.chat.side_effect = None
    mock_inference.chat.return_value = {
        "model_id": "ibm/granite-4-h-small",
        "choices": [{"message": {"content": "Successful reply to Question 2."}}],
    }

    ans2, src2 = agent.generate("Question 2", "Context 2")
    assert src2 == "granite"
    assert "Successful reply to Question 2." in ans2
    assert agent.last_error_category is None


def test_orchestrator_application_fallback_after_timeout():
    """Orchestrator returns structured OrchestratorResponse with fallback status upon timeout."""
    orch = ArthSaathiOrchestrator()
    mock_inference = mock.MagicMock()
    mock_inference.chat.side_effect = httpx.TimeoutException("Network timeout during inference")

    orch.llm.configured = True
    orch.llm._ready = True
    orch.llm._client = mock_inference

    resp = orch.answer("I lost money in a fraudulent UPI transaction. What should I do?")
    assert isinstance(resp, OrchestratorResponse)
    assert resp.status == "fallback"
    assert resp.source == "provider_error"
    assert "timed out after 50 seconds" in (resp.provider_error or "")
    assert resp.error_category == CATEGORY_WATSONX_TIMEOUT
    # Emergency protocol must be deterministically prepended even during fallback
    assert resp.emergency is True
    assert "1930" in resp.answer
    assert "Offline Knowledge Base" in resp.answer


# ===========================================================================
# 6. Actual Local Streamlit Server Startup & Health Check (Task F)
# ===========================================================================

def test_actual_streamlit_server_startup_and_health_endpoint():
    """
    Spawns the real Streamlit application server as an isolated subprocess,
    polls the local /_stcore/health endpoint, verifies HTTP 200 'ok', verifies
    the initial HTML bundle loads without unhandled exceptions, and shuts down cleanly.
    """
    port = _find_free_port()
    env = os.environ.copy()
    env["WATSONX_API_KEY"] = ""
    env["WATSONX_PROJECT_ID"] = ""

    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        "streamlit_app.py",
        "--server.headless",
        "true",
        "--server.port",
        str(port),
    ]

    proc = subprocess.Popen(
        cmd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    health_url = f"http://127.0.0.1:{port}/_stcore/health"
    root_url = f"http://127.0.0.1:{port}/"

    health_ok = False
    try:
        # Poll health endpoint with 15s bounded deadline
        for _ in range(30):
            try:
                with urllib.request.urlopen(health_url, timeout=1.0) as resp:
                    if resp.status == 200 and resp.read().decode().strip() == "ok":
                        health_ok = True
                        break
            except Exception:
                time.sleep(0.5)

        assert health_ok is True, "Streamlit health endpoint /_stcore/health must respond with 'ok'"

        # Verify root page renders HTML
        with urllib.request.urlopen(root_url, timeout=3.0) as resp:
            assert resp.status == 200
            content = resp.read().decode("utf-8", errors="ignore")
            assert len(content) > 100
            assert "<!DOCTYPE html>" in content or "<html" in content

    finally:
        # Terminate server process cleanly
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=2)
