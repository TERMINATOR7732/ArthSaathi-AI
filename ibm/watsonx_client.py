"""
ibm/watsonx_client.py — IBM watsonx.ai client wrapper for ArthSaathi AI.

Coordinates IAM authentication, foundation model client construction, and
inference execution with deterministic error handling and zero credential exposure.
"""

from __future__ import annotations

from typing import Any, Optional

import httpx

from core.config import WatsonxConfig
from ibm.auth import IBMCloudIAMClient
from ibm.exceptions import (
    CATEGORY_AUTH_NETWORK_ERROR,
    CATEGORY_AUTH_TIMEOUT,
    CATEGORY_CONFIG_CREDENTIAL_FORMAT,
    CATEGORY_CONFIG_MISSING,
    CATEGORY_UNKNOWN_IBM_ERROR,
    CATEGORY_WATSONX_MODEL_ERROR,
    CATEGORY_WATSONX_NETWORK_ERROR,
    CATEGORY_WATSONX_SERVICE_ERROR,
    CATEGORY_WATSONX_TIMEOUT,
    IBMAuthError,
    IBMBaseError,
    IBMConfigError,
    WatsonxError,
    categorize_ibm_exception,
)


class WatsonxClient:
    """
    Clean client wrapper for IBM watsonx.ai foundation models.
    Separates IAM authentication from project validation and Granite inference.
    Executes inference synchronously on caller thread with explicit HTTP transport
    timeouts, eliminating abandoned worker threads and uncontrolled socket leaks.
    """

    DEFAULT_CONNECT_TIMEOUT: float = 10.0
    DEFAULT_READ_TIMEOUT: float = 50.0
    DEFAULT_WRITE_TIMEOUT: float = 10.0
    DEFAULT_POOL_TIMEOUT: float = 10.0

    def __init__(self, config: Optional[WatsonxConfig] = None) -> None:
        self.config = config or WatsonxConfig.from_sources()
        self.auth_client = IBMCloudIAMClient(self.config)

        self._model_inference: Any = None
        self._ready: bool = False
        self.init_error: Optional[str] = None
        self.error_category: Optional[str] = None

        if not self.config.api_key or not self.config.project_id:
            # Unconfigured state (graceful offline degradation)
            self.configured = False
            self.error_category = CATEGORY_CONFIG_MISSING
            return

        self.configured = True
        self._initialize_sdk()

    def _initialize_sdk(self) -> None:
        """
        Construct SDK Credentials and ModelInference client.
        Enforces strict credential validation and native HttpClientConfig.
        Fails closed on configuration errors with zero bypass fallbacks.
        """
        try:
            # 1. Validate configuration and obtain credentials strictly through IAM adapter
            creds = self.auth_client.create_credentials()

            # 2. Construct ModelInference client with native HttpClientConfig and disabled retries
            from ibm_watsonx_ai.foundation_models import ModelInference
            from ibm_watsonx_ai.utils.utils import HttpClientConfig

            self.http_config = HttpClientConfig(
                timeout=httpx.Timeout(
                    connect=self.DEFAULT_CONNECT_TIMEOUT,
                    read=self.DEFAULT_READ_TIMEOUT,
                    write=self.DEFAULT_WRITE_TIMEOUT,
                    pool=self.DEFAULT_POOL_TIMEOUT,
                ),
                limits=httpx.Limits(
                    max_connections=5,
                    max_keepalive_connections=2,
                    keepalive_expiry=5.0,
                ),
            )

            try:
                self._model_inference = ModelInference(
                    model_id=self.config.model_id,
                    credentials=creds,
                    project_id=self.config.project_id,
                    http_client=self.http_config,
                    validate=False,
                    max_retries=0,
                    retry_status_codes=[],
                )
            except TypeError:
                self._model_inference = ModelInference(
                    model_id=self.config.model_id,
                    credentials=creds,
                    project_id=self.config.project_id,
                    validate=False,
                    max_retries=0,
                    retry_status_codes=[],
                )

            # Propagate timeouts to both synchronous and asynchronous clients
            if hasattr(self._model_inference, "_client") and self._model_inference._client is not None:
                client_obj = self._model_inference._client
                if hasattr(client_obj, "httpx_client") and client_obj.httpx_client is not None:
                    client_obj.httpx_client.timeout = self.http_config.timeout
                if hasattr(client_obj, "async_httpx_client") and client_obj.async_httpx_client is not None:
                    client_obj.async_httpx_client.timeout = self.http_config.timeout

            self._ready = True
            self.init_error = None
            self.error_category = None
        except Exception as exc:
            self._ready = False
            self.init_error = type(exc).__name__
            cat, _ = categorize_ibm_exception(exc)
            self.error_category = cat

    @property
    def is_ready(self) -> bool:
        """Return True if credentials and ModelInference client are initialized."""
        return self.configured and self._ready and self._model_inference is not None

    def chat(
        self,
        messages: list[dict[str, str]],
        params: Optional[dict[str, Any]] = None,
        timeout: float = 50.0,
    ) -> str:
        """
        Execute chat inference on IBM Granite model with timeout protection.

        Raises:
            WatsonxError: On inference failure or timeout.
        """
        content, _ = self.chat_with_metadata(messages=messages, params=params, timeout=timeout)
        return content

    def chat_with_metadata(
        self,
        messages: list[dict[str, str]],
        params: Optional[dict[str, Any]] = None,
        timeout: float = 50.0,
    ) -> tuple[str, dict[str, Any]]:
        """
        Execute chat inference on IBM Granite model and return content with metadata.

        Raises:
            WatsonxError: On inference failure or timeout.
        """
        if not self.is_ready:
            raise WatsonxError(
                message=f"Client is not ready: {self.init_error or 'uninitialized'}",
                category=self.error_category or CATEGORY_WATSONX_SERVICE_ERROR,
            )

        chat_params = params or {"max_tokens": 512, "temperature": 0.3}

        # 1. Update HTTP client timeout if dynamic override is passed
        if timeout != self.DEFAULT_READ_TIMEOUT:
            if hasattr(self._model_inference, "_client"):
                client_obj = self._model_inference._client
                if hasattr(client_obj, "httpx_client"):
                    client_obj.httpx_client.timeout = httpx.Timeout(
                        connect=min(self.DEFAULT_CONNECT_TIMEOUT, timeout),
                        read=timeout,
                        write=min(self.DEFAULT_WRITE_TIMEOUT, timeout),
                        pool=self.DEFAULT_POOL_TIMEOUT,
                    )

        # 2. Synchronous execution on caller thread (zero background worker threads, zero abandoned workers)
        try:
            result = self._model_inference.chat(
                messages=messages,
                params=chat_params,
            )
        except (httpx.TimeoutException, TimeoutError) as exc:
            raise WatsonxError(
                message=f"IBM watsonx.ai request timed out after {int(timeout)} seconds.",
                category=CATEGORY_WATSONX_TIMEOUT,
                user_message="IBM watsonx.ai foundation model request timed out. Please try again later.",
            ) from exc
        except (httpx.ConnectError, httpx.NetworkError) as exc:
            raise WatsonxError(
                message=f"Failed to connect to IBM watsonx.ai: {exc}",
                category=CATEGORY_WATSONX_NETWORK_ERROR,
                user_message="Failed to establish a network connection to IBM watsonx.ai.",
            ) from exc
        except IBMBaseError:
            raise
        except Exception as exc:
            cat, user_msg = categorize_ibm_exception(exc)
            if cat == CATEGORY_AUTH_TIMEOUT:
                cat = CATEGORY_WATSONX_TIMEOUT
                user_msg = "IBM watsonx.ai foundation model request timed out. Please try again later."
            raise WatsonxError(
                message=str(exc),
                category=cat,
                user_message=user_msg,
            ) from exc

        # Extract content from response
        choices = result.get("choices", [])
        if not choices:
            raise WatsonxError(
                message="Malformed model response: missing 'choices'.",
                category=CATEGORY_WATSONX_MODEL_ERROR,
            )
        content = choices[0].get("message", {}).get("content", "")
        if not isinstance(content, str) or not content.strip():
            raise WatsonxError(
                message="Model returned empty content.",
                category=CATEGORY_WATSONX_MODEL_ERROR,
            )
        metadata = {
            "model_id": result.get("model_id", self.config.model_id),
            "usage": result.get("usage", {}),
        }
        return content.strip(), metadata

    def get_safe_diagnostics(self) -> dict[str, Any]:
        """Return leak-free diagnostics for system status and monitoring."""
        diag = self.auth_client.get_safe_status()
        diag.update({
            "llm_ready": self._ready,
            "llm_init_error": self.init_error,
            "error_category": self.error_category,
        })
        return diag
