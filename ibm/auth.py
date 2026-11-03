"""
ibm/auth.py — IBM Cloud IAM Authentication Adapter for ArthSaathi AI.

Provides deterministic credential creation and IAM authentication management
via the official ibm-watsonx-ai SDK. Enforces production IAM routing and protects
sensitive secrets from being exposed.
"""

from __future__ import annotations

import sys
from typing import Any, Optional

from core.config import WatsonxConfig, has_enclosing_quotes, is_valid_uuid
from ibm.exceptions import (
    CATEGORY_AUTH_ENDPOINT_MISCONFIGURED,
    CATEGORY_AUTH_INVALID_CREDENTIALS,
    CATEGORY_CONFIG_CREDENTIAL_FORMAT,
    CATEGORY_CONFIG_MALFORMED,
    CATEGORY_CONFIG_MISSING,
    IBMAuthError,
    IBMConfigError,
    categorize_ibm_exception,
)

# Canonical production IAM endpoint
PRODUCTION_IAM_TOKEN_URL = "https://iam.cloud.ibm.com/identity/token"


class IBMCloudIAMClient:
    """
    Dedicated IBM Cloud IAM authentication adapter.
    Encapsulates SDK credential construction, validation, and safe diagnostics.
    """

    def __init__(self, config: WatsonxConfig) -> None:
        self.config = config
        self._credentials: Any = None
        self._auth_status: str = "not_tested"
        self._error_category: Optional[str] = None
        self._error_message: Optional[str] = None

    def validate_configuration(self) -> None:
        """
        Validate the configuration before attempting SDK instantiation.
        Raises IBMConfigError on failure.
        """
        if not self.config.api_key:
            self._auth_status = "config_error"
            self._error_category = CATEGORY_CONFIG_MISSING
            self._error_message = "Missing required configuration: WATSONX_API_KEY."
            raise IBMConfigError(
                message=self._error_message,
                category=CATEGORY_CONFIG_MISSING,
            )

        if has_enclosing_quotes(self.config.api_key):
            self._auth_status = "config_error"
            self._error_category = CATEGORY_CONFIG_CREDENTIAL_FORMAT
            self._error_message = (
                "WATSONX_API_KEY contains literal enclosing quotation marks. "
                "Check Streamlit secrets or .env file and remove extraneous quotes."
            )
            raise IBMConfigError(
                message=self._error_message,
                category=CATEGORY_CONFIG_CREDENTIAL_FORMAT,
            )

        if is_valid_uuid(self.config.api_key) and self.config.project_id and not is_valid_uuid(self.config.project_id):
            self._auth_status = "config_error"
            self._error_category = CATEGORY_CONFIG_MALFORMED
            self._error_message = (
                "WATSONX_API_KEY matches UUID format while WATSONX_PROJECT_ID does not. "
                "It is possible that API key and Project ID values were swapped."
            )
            raise IBMConfigError(
                message=self._error_message,
                category=CATEGORY_CONFIG_MALFORMED,
            )

    def create_credentials(self) -> Any:
        """
        Construct and return official ibm_watsonx_ai.Credentials object.
        Guarantees that canonical endpoint is used and explicit production auth_url
        is attached to prevent accidental staging fallback.
        """
        self.validate_configuration()

        try:
            from ibm_watsonx_ai import Credentials

            # Pass the canonical normalized URL and explicit production IAM auth_url
            self._credentials = Credentials(
                url=self.config.url,
                api_key=self.config.api_key,
                auth_url=PRODUCTION_IAM_TOKEN_URL,
            )
            return self._credentials
        except ImportError as exc:
            self._auth_status = "sdk_missing"
            self._error_category = CATEGORY_CONFIG_MALFORMED
            raise IBMConfigError(
                message=f"ibm-watsonx-ai SDK is not installed: {exc}",
                category=CATEGORY_CONFIG_MALFORMED,
            )
        except Exception as exc:
            cat, user_msg = categorize_ibm_exception(exc)
            self._auth_status = "failed"
            self._error_category = cat
            self._error_message = user_msg
            raise IBMAuthError(
                message=str(exc),
                category=cat,
                user_message=user_msg,
            )

    def get_safe_status(self) -> dict[str, Any]:
        """
        Return safe diagnostic status without credentials.
        """
        diag = self.config.get_safe_diagnostics()
        diag.update({
            "auth_status": self._auth_status,
            "auth_error_category": self._error_category,
            "production_iam_enforced": True,
        })
        return diag
