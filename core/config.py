"""
core/config.py — Centralized configuration management for ArthSaathi AI.

Handles loading, validating, and normalizing IBM watsonx.ai configuration
from Streamlit secrets and environment variables with deterministic precedence.
Ensures zero credential leakage in logs and diagnostics.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_WATSONX_URL = "https://us-south.ml.cloud.ibm.com"
DEFAULT_WATSONX_MODEL_ID = "ibm/granite-4-h-small"

WATSONX_CONFIG_KEYS = (
    "WATSONX_API_KEY",
    "WATSONX_PROJECT_ID",
    "WATSONX_URL",
    "WATSONX_MODEL_ID",
)

# Standard UUIDv4 pattern (36 chars: 8-4-4-4-12)
UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)

# Recognized IBM Cloud / watsonx.ai production domain suffixes and canonical hosts
RECOGNIZED_IBM_DOMAINS = (
    ".ml.cloud.ibm.com",
    ".mybluemix.net",
    ".bluemix.net",
)

# Known canonical hosts from ibm_watsonx_ai.href_definitions.PROD_SVT_URL
CANONICAL_PROD_HOSTS = frozenset([
    "us-south.ml.cloud.ibm.com",
    "eu-gb.ml.cloud.ibm.com",
    "eu-de.ml.cloud.ibm.com",
    "jp-tok.ml.cloud.ibm.com",
    "ca-tor.ml.cloud.ibm.com",
    "au-syd.ml.cloud.ibm.com",
    "ibm-watson-ml.mybluemix.net",
    "ibm-watson-ml.eu-gb.bluemix.net",
    "private.us-south.ml.cloud.ibm.com",
    "private.eu-gb.ml.cloud.ibm.com",
    "private.eu-de.ml.cloud.ibm.com",
    "private.jp-tok.ml.cloud.ibm.com",
    "private.au-syd.ml.cloud.ibm.com",
    "private.ca-tor.ml.cloud.ibm.com",
    "yp-qa.ml.cloud.ibm.com",
    "private.yp-qa.ml.cloud.ibm.com",
    "yp-cr.ml.cloud.ibm.com",
    "private.yp-cr.ml.cloud.ibm.com",
    "wxai-qa.ml.cloud.ibm.com",
    "private.wxai-qa.ml.cloud.ibm.com",
])


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def has_enclosing_quotes(val: str) -> bool:
    """Return True if string has literal enclosing single or double quotes."""
    if len(val) >= 2:
        return (val[0] == '"' and val[-1] == '"') or (val[0] == "'" and val[-1] == "'")
    return False


def is_valid_uuid(val: str) -> bool:
    """Return True if string matches standard UUID structure."""
    return bool(UUID_RE.match(val.strip()))


def normalize_watsonx_url(raw_url: str) -> str:
    """
    Safely normalize an IBM watsonx.ai endpoint URL.

    - Resolves leading and trailing whitespace.
    - Strips trailing slashes to prevent the SDK staging fallback bug.
    - Validates HTTPS scheme strictly (rejects http, ftp, file, etc.).
    - Rejects embedded credentials (username:password@host).
    - Rejects query strings and fragments.
    - Rejects unsupported deep URL paths (e.g. /v1, /ml/v1).
    - Verifies that the host is a recognized IBM watsonx.ai production host.

    Raises:
        ValueError: If the URL is empty, malformed, non-HTTPS, or not a recognized IBM host.
    """
    if not isinstance(raw_url, str) or not raw_url.strip():
        raise ValueError("watsonx URL cannot be empty or non-string.")

    clean_url = raw_url.strip()
    parsed = urlparse(clean_url)

    # 1. Scheme check
    if parsed.scheme.lower() != "https":
        raise ValueError(
            f"watsonx URL must strictly use HTTPS scheme; got '{parsed.scheme or 'none'}'."
        )

    # 2. Host presence and credential check
    if not parsed.netloc:
        raise ValueError("watsonx URL must specify a valid hostname.")

    if "@" in parsed.netloc or parsed.username or parsed.password:
        raise ValueError("watsonx URL must not contain embedded user credentials.")

    # 3. Query string & fragment check
    if parsed.query:
        raise ValueError("watsonx URL must not contain query parameters.")
    if parsed.fragment:
        raise ValueError("watsonx URL must not contain URL fragments.")

    # 4. Path validation (must be empty or just "/")
    path = parsed.path.strip()
    if path and path != "/":
        raise ValueError(
            f"watsonx URL must be a base service endpoint without path components; got '{path}'."
        )

    # 5. Host domain verification & family check
    host = parsed.netloc.split(":")[0].lower()  # ignore port if present

    # Explicit rejection of AWS-hosted SaaS endpoints
    if ".aws.wxai.ibm.com" in host or host.endswith(".aws.wxai.ibm.com") or "aws.wxai" in host:
        raise ValueError(
            f"AWS-hosted watsonx.ai endpoint '{host}' is unsupported. "
            "ArthSaathi AI operates on IBM Cloud Lite IAM; please configure a standard "
            "IBM Cloud endpoint such as 'https://us-south.ml.cloud.ibm.com'."
        )

    # Explicit rejection of IBM GovCloud endpoints
    if "ibmforusgov.com" in host or host.endswith(".ibmforusgov.com"):
        raise ValueError(
            f"IBM GovCloud watsonx.ai endpoint '{host}' is unsupported. "
            "ArthSaathi AI operates on IBM Cloud Lite IAM; please configure a standard "
            "IBM Cloud endpoint such as 'https://us-south.ml.cloud.ibm.com'."
        )

    is_recognized = (
        host in CANONICAL_PROD_HOSTS
        or any(host.endswith(suffix) for suffix in RECOGNIZED_IBM_DOMAINS)
    )
    if not is_recognized:
        raise ValueError(
            f"watsonx URL host '{host}' is not a recognized IBM Cloud or watsonx.ai endpoint."
        )

    # Reconstruct canonical endpoint without trailing slash
    return f"https://{host}"


def get_st_secrets_root_keys() -> list[str]:
    """Return names of expected watsonx keys found at the root of st.secrets."""
    try:
        import streamlit as st
        if hasattr(st, "secrets") and st.secrets is not None:
            return [k for k in WATSONX_CONFIG_KEYS if k in st.secrets]
    except Exception:
        pass
    return []


def get_config_var_with_source(key: str, default: str = "") -> tuple[str, str]:
    """
    Retrieve configuration value and its source ('st.secrets', 'os.environ', or 'default').
    Checks st.secrets first (for Streamlit Community Cloud), then os.environ, then default.
    Preserves exact whitespace handling and empty variable semantics.
    """
    try:
        import streamlit as st
        if hasattr(st, "secrets") and st.secrets is not None and key in st.secrets:
            val = str(st.secrets[key]).strip()
            if val:
                return val, "st.secrets"
    except Exception:
        pass

    if key in os.environ:
        return os.environ[key].strip(), "os.environ"

    return default.strip(), "default"


def get_config_var(key: str, default: str = "") -> str:
    """Retrieve configuration value from Streamlit secrets or environment variables."""
    return get_config_var_with_source(key, default)[0]


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

@dataclass
class ConfigValidationResult:
    """Result of configuration validation."""
    is_valid: bool
    error_category: Optional[str] = None
    error_message: Optional[str] = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class WatsonxConfig:
    """
    Strongly typed, validated configuration for IBM watsonx.ai services.
    Never exposes raw secrets in __repr__ or __str__.
    """
    api_key: str
    project_id: str
    url: str = DEFAULT_WATSONX_URL
    model_id: str = DEFAULT_WATSONX_MODEL_ID
    source_map: dict[str, str] = field(default_factory=dict)
    endpoint_normalized: bool = False
    validation_result: Optional[ConfigValidationResult] = None

    def __post_init__(self) -> None:
        """Ensure URL is always canonically normalized upon instantiation."""
        if self.url:
            try:
                norm = normalize_watsonx_url(self.url)
                if norm != self.url:
                    self.endpoint_normalized = True
                self.url = norm
            except Exception:
                pass

    def __repr__(self) -> str:
        # Prevent any accidental leakage in logging/debugging
        return (
            f"WatsonxConfig(url={self.url!r}, model_id={self.model_id!r}, "
            f"project_id_valid={is_valid_uuid(self.project_id)}, "
            f"has_api_key={bool(self.api_key)}, sources={self.source_map})"
        )

    @classmethod
    def from_sources(cls) -> WatsonxConfig:
        """
        Load configuration deterministically from st.secrets and os.environ.
        Enforces atomic credential bundle resolution: if either WATSONX_API_KEY
        or WATSONX_PROJECT_ID is present in st.secrets, credentials must originate
        exclusively from st.secrets to prevent cross-tier credential splicing.
        """
        source_map: dict[str, str] = {}

        # Safely inspect streamlit secrets
        secrets_dict: dict[str, Any] = {}
        try:
            import streamlit as st
            if hasattr(st, "secrets") and st.secrets is not None:
                secrets_dict = {k: st.secrets[k] for k in WATSONX_CONFIG_KEYS if k in st.secrets}
        except Exception:
            secrets_dict = {}

        # Determine credential provider tier atomically
        has_secrets_creds = ("WATSONX_API_KEY" in secrets_dict) or ("WATSONX_PROJECT_ID" in secrets_dict)

        if has_secrets_creds:
            if "WATSONX_API_KEY" in secrets_dict and str(secrets_dict["WATSONX_API_KEY"]).strip():
                raw_api_key = str(secrets_dict["WATSONX_API_KEY"]).strip()
                source_map["api_key"] = "st.secrets"
            else:
                raw_api_key = ""
                source_map["api_key"] = "st.secrets (missing)"

            if "WATSONX_PROJECT_ID" in secrets_dict and str(secrets_dict["WATSONX_PROJECT_ID"]).strip():
                raw_project_id = str(secrets_dict["WATSONX_PROJECT_ID"]).strip()
                source_map["project_id"] = "st.secrets"
            else:
                raw_project_id = ""
                source_map["project_id"] = "st.secrets (missing)"
        else:
            # Fall back to os.environ for credential bundle
            if "WATSONX_API_KEY" in os.environ and os.environ["WATSONX_API_KEY"].strip():
                raw_api_key = os.environ["WATSONX_API_KEY"].strip()
                source_map["api_key"] = "os.environ"
            else:
                raw_api_key = ""
                source_map["api_key"] = "missing"

            if "WATSONX_PROJECT_ID" in os.environ and os.environ["WATSONX_PROJECT_ID"].strip():
                raw_project_id = os.environ["WATSONX_PROJECT_ID"].strip()
                source_map["project_id"] = "os.environ"
            else:
                raw_project_id = ""
                source_map["project_id"] = "missing"

        # Non-credential config: URL and Model ID can be specified in secrets, then env, then default
        raw_url, url_src = get_config_var_with_source("WATSONX_URL", DEFAULT_WATSONX_URL)
        source_map["url"] = url_src

        raw_model_id, model_src = get_config_var_with_source("WATSONX_MODEL_ID", DEFAULT_WATSONX_MODEL_ID)
        source_map["model_id"] = model_src

        # Attempt URL normalization
        endpoint_normalized = False
        normalized_url = raw_url
        try:
            if raw_url:
                normalized_url = normalize_watsonx_url(raw_url)
                endpoint_normalized = (normalized_url != raw_url)
        except Exception:
            normalized_url = raw_url

        cfg = cls(
            api_key=raw_api_key,
            project_id=raw_project_id,
            url=normalized_url,
            model_id=raw_model_id,
            source_map=source_map,
            endpoint_normalized=endpoint_normalized,
        )
        cfg.validation_result = cfg.validate()
        return cfg

    def validate(self) -> ConfigValidationResult:
        """
        Perform comprehensive validation on the configuration.
        Distinguishes missing config, malformed config, and credential format errors.
        """
        details: dict[str, Any] = {
            "has_api_key": bool(self.api_key),
            "has_project_id": bool(self.project_id),
            "endpoint_normalized": self.endpoint_normalized,
            "sources": self.source_map,
        }

        # 1. Missing credentials check
        if not self.api_key or not self.project_id:
            missing = []
            if not self.api_key:
                missing.append("WATSONX_API_KEY")
            if not self.project_id:
                missing.append("WATSONX_PROJECT_ID")
            return ConfigValidationResult(
                is_valid=False,
                error_category="config_missing",
                error_message=f"Missing required configuration: {', '.join(missing)}.",
                details=details,
            )

        # 2. Check for literal enclosing quotes in API key (do NOT strip)
        if has_enclosing_quotes(self.api_key):
            details["api_key_has_quotes"] = True
            return ConfigValidationResult(
                is_valid=False,
                error_category="config_credential_format",
                error_message=(
                    "WATSONX_API_KEY contains literal enclosing quotation marks. "
                    "Check Streamlit secrets or .env file and remove extraneous quotes."
                ),
                details=details,
            )

        # 3. Check for UUID inversion (API key looks like UUID)
        api_key_is_uuid = is_valid_uuid(self.api_key)
        proj_id_is_uuid = is_valid_uuid(self.project_id)
        details["api_key_is_uuid"] = api_key_is_uuid
        details["proj_id_is_uuid"] = proj_id_is_uuid

        if api_key_is_uuid and not proj_id_is_uuid:
            return ConfigValidationResult(
                is_valid=False,
                error_category="config_malformed",
                error_message=(
                    "WATSONX_API_KEY matches UUID format while WATSONX_PROJECT_ID does not. "
                    "It is possible that API key and Project ID values were swapped."
                ),
                details=details,
            )

        # 4. Project ID UUID check
        if not proj_id_is_uuid:
            return ConfigValidationResult(
                is_valid=False,
                error_category="config_malformed",
                error_message="WATSONX_PROJECT_ID is not a valid 36-character UUID.",
                details=details,
            )

        # 5. Endpoint validation
        try:
            normalize_watsonx_url(self.url)
        except ValueError as exc:
            return ConfigValidationResult(
                is_valid=False,
                error_category="config_malformed",
                error_message=f"Invalid watsonx URL: {exc}",
                details=details,
            )

        return ConfigValidationResult(
            is_valid=True,
            error_category=None,
            error_message=None,
            details=details,
        )

    def get_safe_diagnostics(self) -> dict[str, Any]:
        """Generate safe, leak-free diagnostic information for UI and logging."""
        val = self.validation_result or self.validate()

        host = "unknown"
        if "//" in self.url:
            host = self.url.split("//")[1].split("/")[0]
        elif "/" in self.url:
            host = self.url.split("/")[0]

        root_keys = get_st_secrets_root_keys()

        return {
            "configured": bool(self.api_key and self.project_id),
            "valid": val.is_valid,
            "error_category": val.error_category,
            "config_sources": self.source_map,
            "endpoint_host": host,
            "endpoint_normalized": self.endpoint_normalized,
            "project_id_format_valid": is_valid_uuid(self.project_id) if self.project_id else False,
            "root_secrets_found": root_keys,
            "model_id": self.model_id,
        }
