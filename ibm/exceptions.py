"""
ibm/exceptions.py — Structured exceptions and deterministic error categorization
for IBM Cloud IAM and watsonx.ai services.

Guarantees zero credential leakage by preventing raw exception strings, auth headers,
and Bearer tokens from appearing in user-facing responses or unvetted logs.
"""

from __future__ import annotations

from typing import Optional

# ---------------------------------------------------------------------------
# Error Categories (Section 11 Specification)
# ---------------------------------------------------------------------------

CATEGORY_CONFIG_MISSING = "config_missing"
CATEGORY_CONFIG_MALFORMED = "config_malformed"
CATEGORY_CONFIG_CREDENTIAL_FORMAT = "config_credential_format"
CATEGORY_AUTH_INVALID_CREDENTIALS = "auth_invalid_credentials"
CATEGORY_AUTH_ENDPOINT_MISCONFIGURED = "auth_endpoint_misconfigured"
CATEGORY_AUTH_NETWORK_ERROR = "auth_network_error"
CATEGORY_AUTH_TIMEOUT = "auth_timeout"
CATEGORY_WATSONX_NETWORK_ERROR = "watsonx_network_error"
CATEGORY_WATSONX_TIMEOUT = "watsonx_timeout"
CATEGORY_WATSONX_UNAUTHORIZED = "watsonx_unauthorized"
CATEGORY_WATSONX_PROJECT_ERROR = "watsonx_project_error"
CATEGORY_WATSONX_SERVICE_ERROR = "watsonx_service_error"
CATEGORY_WATSONX_MODEL_ERROR = "watsonx_model_error"
CATEGORY_UNKNOWN_IBM_ERROR = "unknown_ibm_error"

ALL_CATEGORIES = frozenset([
    CATEGORY_CONFIG_MISSING,
    CATEGORY_CONFIG_MALFORMED,
    CATEGORY_CONFIG_CREDENTIAL_FORMAT,
    CATEGORY_AUTH_INVALID_CREDENTIALS,
    CATEGORY_AUTH_ENDPOINT_MISCONFIGURED,
    CATEGORY_AUTH_NETWORK_ERROR,
    CATEGORY_AUTH_TIMEOUT,
    CATEGORY_WATSONX_NETWORK_ERROR,
    CATEGORY_WATSONX_TIMEOUT,
    CATEGORY_WATSONX_UNAUTHORIZED,
    CATEGORY_WATSONX_PROJECT_ERROR,
    CATEGORY_WATSONX_SERVICE_ERROR,
    CATEGORY_WATSONX_MODEL_ERROR,
    CATEGORY_UNKNOWN_IBM_ERROR,
])


# ---------------------------------------------------------------------------
# Exception Hierarchy
# ---------------------------------------------------------------------------

class IBMBaseError(Exception):
    """Base exception for all IBM integration errors."""
    def __init__(
        self,
        message: str,
        category: str = CATEGORY_UNKNOWN_IBM_ERROR,
        status_code: Optional[int] = None,
        ibm_code: Optional[str] = None,
        user_message: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.category = category
        self.status_code = status_code
        self.ibm_code = ibm_code
        self.user_message = user_message or "An IBM service error occurred."


class IBMConfigError(IBMBaseError):
    """Raised when IBM configuration is missing, malformed, or has invalid format."""
    def __init__(
        self,
        message: str,
        category: str = CATEGORY_CONFIG_MALFORMED,
        user_message: Optional[str] = None,
    ) -> None:
        super().__init__(
            message=message,
            category=category,
            user_message=user_message or "IBM Cloud configuration is incomplete or invalid.",
        )


class IBMAuthError(IBMBaseError):
    """Raised when IAM token acquisition or authentication fails."""
    def __init__(
        self,
        message: str,
        category: str = CATEGORY_AUTH_INVALID_CREDENTIALS,
        status_code: Optional[int] = None,
        ibm_code: Optional[str] = None,
        user_message: Optional[str] = None,
    ) -> None:
        super().__init__(
            message=message,
            category=category,
            status_code=status_code,
            ibm_code=ibm_code,
            user_message=user_message or "IBM Cloud IAM authentication failed. Please verify credentials.",
        )


class WatsonxError(IBMBaseError):
    """Raised when watsonx.ai authorization, project lookup, or model inference fails."""
    def __init__(
        self,
        message: str,
        category: str = CATEGORY_WATSONX_SERVICE_ERROR,
        status_code: Optional[int] = None,
        ibm_code: Optional[str] = None,
        user_message: Optional[str] = None,
    ) -> None:
        super().__init__(
            message=message,
            category=category,
            status_code=status_code,
            ibm_code=ibm_code,
            user_message=user_message or "watsonx.ai foundation model service encountered an error.",
        )


# ---------------------------------------------------------------------------
# Exception Classifier
# ---------------------------------------------------------------------------

def categorize_ibm_exception(exc: Exception) -> tuple[str, str]:
    """
    Classify any arbitrary exception from the IBM SDK or network layer into
    a standardized error category and a sanitized user-facing message.

    Returns:
        tuple[str, str]: (error_category, user_friendly_message)
    """
    if isinstance(exc, IBMBaseError):
        return exc.category, exc.user_message

    exc_class_name = type(exc).__name__.lower()
    msg = ""
    try:
        msg = str(exc).lower()
    except Exception:
        pass

    # 1. IAM authentication / credentials failure
    if (
        "bxnim0415e" in msg
        or "invalidcredentials" in exc_class_name
        or "invalid credentials" in msg
        or "provided api key could not be found" in msg
        or "401" in msg
        or "unauthorized" in msg
        or "failed auth" in msg
        or "authentication failed" in msg
        or "auth failed" in msg
    ):
        return (
            CATEGORY_AUTH_INVALID_CREDENTIALS,
            "IBM Cloud IAM rejected the provided API key. Verify that the key is active in your IBM Cloud account.",
        )

    # 2. Timeout errors
    if "timeout" in exc_class_name or "timed out" in msg:
        if "model" in msg or "watsonx" in msg or "granite" in msg or "inference" in msg:
            return (
                CATEGORY_WATSONX_TIMEOUT,
                "IBM watsonx.ai foundation model request timed out. Please try again later.",
            )
        return (
            CATEGORY_AUTH_TIMEOUT,
            "Connection to IBM Cloud services timed out. Please check your network connection.",
        )

    # 3. Network / Connection errors
    if (
        "connect" in exc_class_name
        or "network" in exc_class_name
        or "dns" in msg
        or "gaierror" in exc_class_name
        or "connection error" in msg
        or "connection refused" in msg
    ):
        if "model" in msg or "watsonx" in msg or "granite" in msg or "inference" in msg:
            return (
                CATEGORY_WATSONX_NETWORK_ERROR,
                "Failed to establish a network connection to IBM watsonx.ai foundation model endpoint.",
            )
        return (
            CATEGORY_AUTH_NETWORK_ERROR,
            "Failed to establish a network connection to IBM Cloud endpoints.",
        )

    # 4. Permissions / Authorization (403 Forbidden)
    if "403" in msg or "forbidden" in msg or "permission" in msg or "not authorized" in msg:
        return (
            CATEGORY_WATSONX_UNAUTHORIZED,
            "IBM IAM authenticated successfully, but the identity lacks sufficient access to the watsonx.ai project.",
        )

    # 5. Project lookup errors (404 / project missing)
    if "project" in msg and ("not found" in msg or "404" in msg or "invalid" in msg):
        return (
            CATEGORY_WATSONX_PROJECT_ERROR,
            "The configured watsonx.ai project ID could not be found or is not accessible.",
        )

    # 6. Model unavailable or unsupported
    if "model" in msg and ("not supported" in msg or "unavailable" in msg or "not found" in msg):
        return (
            CATEGORY_WATSONX_MODEL_ERROR,
            "The requested IBM Granite foundation model is unsupported or unavailable in this region.",
        )

    # 7. Endpoint misconfigured
    if "staging" in msg or "invalid_auth_url" in msg or "endpoint" in msg:
        return (
            CATEGORY_AUTH_ENDPOINT_MISCONFIGURED,
            "The watsonx.ai service or IAM endpoint URL is misconfigured.",
        )

    # 8. Configuration errors
    if isinstance(exc, (ValueError, KeyError)) or "config" in msg:
        return (
            CATEGORY_CONFIG_MALFORMED,
            "IBM configuration format is invalid.",
        )

    # Default fallback
    return (
        CATEGORY_UNKNOWN_IBM_ERROR,
        "An unexpected error occurred while communicating with IBM Cloud services.",
    )
