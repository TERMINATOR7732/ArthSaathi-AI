"""
tests/test_config.py — Comprehensive tests for core/config.py.

Covers:
- URL normalization (trailing slash, whitespace, schemes, paths, queries, fragments).
- Enclosing quote detection and credential format rules.
- UUID validation for watsonx project IDs.
- Deterministic configuration source precedence (st.secrets vs os.environ vs defaults).
- Validation error categorization (missing, malformed, credential format).
- Zero credential leakage in diagnostics and repr.
"""

import os
import unittest.mock as mock
import pytest

from core.config import (
    DEFAULT_WATSONX_MODEL_ID,
    DEFAULT_WATSONX_URL,
    WatsonxConfig,
    get_config_var,
    get_config_var_with_source,
    get_st_secrets_root_keys,
    has_enclosing_quotes,
    is_valid_uuid,
    normalize_watsonx_url,
)


# ===========================================================================
# 1. URL Normalization Tests
# ===========================================================================

def test_normalize_url_canonical_unchanged():
    url = "https://us-south.ml.cloud.ibm.com"
    assert normalize_watsonx_url(url) == "https://us-south.ml.cloud.ibm.com"


def test_normalize_url_strips_trailing_slash():
    url = "https://us-south.ml.cloud.ibm.com/"
    assert normalize_watsonx_url(url) == "https://us-south.ml.cloud.ibm.com"


def test_normalize_url_strips_surrounding_whitespace():
    url = "  https://us-south.ml.cloud.ibm.com/  "
    assert normalize_watsonx_url(url) == "https://us-south.ml.cloud.ibm.com"


def test_normalize_url_multi_regions():
    regions = [
        "https://us-south.ml.cloud.ibm.com",
        "https://eu-gb.ml.cloud.ibm.com",
        "https://eu-de.ml.cloud.ibm.com/",
        "https://jp-tok.ml.cloud.ibm.com/",
        "https://ca-tor.ml.cloud.ibm.com",
        "https://au-syd.ml.cloud.ibm.com/",
    ]
    for r in regions:
        normalized = normalize_watsonx_url(r)
        assert not normalized.endswith("/")
        assert normalized.startswith("https://")


def test_normalize_url_rejects_aws_endpoints():
    with pytest.raises(ValueError, match="AWS-hosted watsonx.ai endpoint.*is unsupported"):
        normalize_watsonx_url("https://ap-south-1.aws.wxai.ibm.com")
    with pytest.raises(ValueError, match="AWS-hosted watsonx.ai endpoint.*is unsupported"):
        normalize_watsonx_url("https://us-east-1.aws.wxai.ibm.com/")


def test_normalize_url_rejects_govcloud_endpoints():
    with pytest.raises(ValueError, match="IBM GovCloud watsonx.ai endpoint.*is unsupported"):
        normalize_watsonx_url("https://wxai.ibmforusgov.com")
    with pytest.raises(ValueError, match="IBM GovCloud watsonx.ai endpoint.*is unsupported"):
        normalize_watsonx_url("https://private.internal.wxai.ibmforusgov.com/")


def test_normalize_url_rejects_http_scheme():
    with pytest.raises(ValueError, match="must strictly use HTTPS"):
        normalize_watsonx_url("http://us-south.ml.cloud.ibm.com")


def test_normalize_url_rejects_empty_or_whitespace():
    with pytest.raises(ValueError, match="cannot be empty"):
        normalize_watsonx_url("")
    with pytest.raises(ValueError, match="cannot be empty"):
        normalize_watsonx_url("   ")


def test_normalize_url_rejects_embedded_credentials():
    with pytest.raises(ValueError, match="embedded user credentials"):
        normalize_watsonx_url("https://user:pass@us-south.ml.cloud.ibm.com")


def test_normalize_url_rejects_query_parameters():
    with pytest.raises(ValueError, match="must not contain query parameters"):
        normalize_watsonx_url("https://us-south.ml.cloud.ibm.com?version=2023-05-29")


def test_normalize_url_rejects_fragments():
    with pytest.raises(ValueError, match="must not contain URL fragments"):
        normalize_watsonx_url("https://us-south.ml.cloud.ibm.com#section")


def test_normalize_url_rejects_unsupported_path():
    with pytest.raises(ValueError, match="must be a base service endpoint"):
        normalize_watsonx_url("https://us-south.ml.cloud.ibm.com/ml/v1/foundation_models")


def test_normalize_url_rejects_unrecognized_domain():
    with pytest.raises(ValueError, match="not a recognized IBM Cloud or watsonx.ai endpoint"):
        normalize_watsonx_url("https://untrusted-external-site.com")


# ===========================================================================
# 2. Credential Formatting & Enclosing Quotes
# ===========================================================================

def test_has_enclosing_quotes():
    assert has_enclosing_quotes('"double-quoted"') is True
    assert has_enclosing_quotes("'single-quoted'") is True
    assert has_enclosing_quotes("unquoted-key") is False
    assert has_enclosing_quotes('"') is False
    assert has_enclosing_quotes("'") is False
    assert has_enclosing_quotes("") is False


def test_is_valid_uuid():
    # UUID v4
    assert is_valid_uuid("12345678-abcd-ef01-2345-6789abcdef01") is True
    # UUID v1
    assert is_valid_uuid("6ba7b810-9dad-11d1-80b4-00c04fd430c8") is True
    # Uppercase hex UUID
    assert is_valid_uuid("12345678-ABCD-EF01-2345-6789ABCDEF01") is True
    # Nil UUID
    assert is_valid_uuid("00000000-0000-0000-0000-000000000000") is True
    # Leading/trailing whitespace
    assert is_valid_uuid("  12345678-abcd-ef01-2345-6789abcdef01  ") is True
    # Invalid strings
    assert is_valid_uuid("not-a-uuid") is False
    assert is_valid_uuid("12345678-abcd-ef01-2345-6789abcdef0") is False  # 35 chars
    assert is_valid_uuid("12345678-abcd-ef01-2345-6789abcdef012") is False  # 37 chars
    assert is_valid_uuid("") is False


# ===========================================================================
# 3. Configuration Precedence & Resolution
# ===========================================================================

def test_get_config_var_precedence():
    fake_secrets = {"WATSONX_API_KEY": "secret-key"}
    with mock.patch("streamlit.secrets", fake_secrets):
        with mock.patch.dict(os.environ, {"WATSONX_API_KEY": "env-key"}):
            val, src = get_config_var_with_source("WATSONX_API_KEY")
            assert val == "secret-key"
            assert src == "st.secrets"


def test_get_config_var_env_fallback():
    fake_secrets = {}
    with mock.patch("streamlit.secrets", fake_secrets):
        with mock.patch.dict(os.environ, {"WATSONX_API_KEY": "env-key"}):
            val, src = get_config_var_with_source("WATSONX_API_KEY")
            assert val == "env-key"
            assert src == "os.environ"


def test_get_config_var_empty_secret_falls_back():
    fake_secrets = {"WATSONX_API_KEY": "   "}
    with mock.patch("streamlit.secrets", fake_secrets):
        with mock.patch.dict(os.environ, {"WATSONX_API_KEY": "env-key"}):
            val, src = get_config_var_with_source("WATSONX_API_KEY")
            assert val == "env-key"
            assert src == "os.environ"


def test_get_config_var_default():
    fake_secrets = {}
    with mock.patch("streamlit.secrets", fake_secrets):
        with mock.patch.dict(os.environ, {}, clear=True):
            val, src = get_config_var_with_source("WATSONX_URL", DEFAULT_WATSONX_URL)
            assert val == DEFAULT_WATSONX_URL
            assert src == "default"


# ===========================================================================
# 4. WatsonxConfig Validation
# ===========================================================================

def test_config_validation_missing_key():
    cfg = WatsonxConfig(api_key="", project_id="12345678-abcd-ef01-2345-6789abcdef01")
    res = cfg.validate()
    assert res.is_valid is False
    assert res.error_category == "config_missing"


def test_config_validation_missing_project_id():
    cfg = WatsonxConfig(api_key="valid-key", project_id="")
    res = cfg.validate()
    assert res.is_valid is False
    assert res.error_category == "config_missing"


def test_config_validation_literal_quotes_error():
    cfg = WatsonxConfig(
        api_key='"enclosed-quoted-key"',
        project_id="12345678-abcd-ef01-2345-6789abcdef01",
    )
    res = cfg.validate()
    assert res.is_valid is False
    assert res.error_category == "config_credential_format"
    assert "enclosing quotation marks" in res.error_message


def test_config_validation_malformed_project_id():
    cfg = WatsonxConfig(api_key="valid-key", project_id="not-a-valid-uuid")
    res = cfg.validate()
    assert res.is_valid is False
    assert res.error_category == "config_malformed"
    assert "36-character UUID" in res.error_message


def test_config_validation_swapped_key_and_project():
    uuid_str = "12345678-abcd-ef01-2345-6789abcdef01"
    cfg = WatsonxConfig(api_key=uuid_str, project_id="non-uuid-api-key")
    res = cfg.validate()
    assert res.is_valid is False
    assert res.error_category == "config_malformed"
    assert "swapped" in res.error_message


def test_config_validation_valid():
    cfg = WatsonxConfig(
        api_key="valid-ibm-cloud-api-key",
        project_id="12345678-abcd-ef01-2345-6789abcdef01",
        url="https://us-south.ml.cloud.ibm.com",
    )
    res = cfg.validate()
    assert res.is_valid is True
    assert res.error_category is None


# ===========================================================================
# 5. Zero Credential Leakage in Diagnostics & Repr
# ===========================================================================

def test_safe_diagnostics_no_secret_leak():
    sentinel_key = "SENTINEL-SUPER-SECRET-API-KEY-VALUE-999"
    sentinel_proj = "12345678-abcd-ef01-2345-6789abcdef01"
    cfg = WatsonxConfig(
        api_key=sentinel_key,
        project_id=sentinel_proj,
        url="https://us-south.ml.cloud.ibm.com/",
    )
    diag = cfg.get_safe_diagnostics()

    assert sentinel_key not in str(diag)
    assert repr(cfg).find(sentinel_key) == -1
    assert diag["configured"] is True
    assert diag["endpoint_host"] == "us-south.ml.cloud.ibm.com"
    assert diag["project_id_format_valid"] is True


# ===========================================================================
# 6. Atomic Credential Bundling in from_sources()
# ===========================================================================

def test_from_sources_secrets_atomic_bundle_prevents_env_splicing_missing_proj():
    """
    If st.secrets defines WATSONX_API_KEY but omits WATSONX_PROJECT_ID,
    from_sources() must NOT silently borrow WATSONX_PROJECT_ID from os.environ.
    """
    fake_secrets = {"WATSONX_API_KEY": "secret-api-key"}
    with mock.patch("streamlit.secrets", fake_secrets):
        with mock.patch.dict(os.environ, {"WATSONX_PROJECT_ID": "12345678-abcd-ef01-2345-6789abcdef01"}):
            cfg = WatsonxConfig.from_sources()
            assert cfg.api_key == "secret-api-key"
            assert cfg.project_id == ""  # Did NOT splice from os.environ
            assert cfg.source_map["api_key"] == "st.secrets"
            assert "st.secrets" in cfg.source_map["project_id"]
            val = cfg.validate()
            assert val.is_valid is False
            assert val.error_category == "config_missing"
            assert "WATSONX_PROJECT_ID" in val.error_message


def test_from_sources_secrets_atomic_bundle_prevents_env_splicing_missing_key():
    """
    If st.secrets defines WATSONX_PROJECT_ID but omits WATSONX_API_KEY,
    from_sources() must NOT silently borrow WATSONX_API_KEY from os.environ.
    """
    fake_secrets = {"WATSONX_PROJECT_ID": "12345678-abcd-ef01-2345-6789abcdef01"}
    with mock.patch("streamlit.secrets", fake_secrets):
        with mock.patch.dict(os.environ, {"WATSONX_API_KEY": "env-api-key"}):
            cfg = WatsonxConfig.from_sources()
            assert cfg.api_key == ""  # Did NOT splice from os.environ
            assert cfg.project_id == "12345678-abcd-ef01-2345-6789abcdef01"
            assert "st.secrets" in cfg.source_map["api_key"]
            assert cfg.source_map["project_id"] == "st.secrets"
            val = cfg.validate()
            assert val.is_valid is False
            assert val.error_category == "config_missing"
            assert "WATSONX_API_KEY" in val.error_message


def test_from_sources_complete_secrets_override_env():
    """When both credentials exist in st.secrets, they completely supersede os.environ."""
    fake_secrets = {
        "WATSONX_API_KEY": "secret-key",
        "WATSONX_PROJECT_ID": "11111111-1111-1111-1111-111111111111",
    }
    with mock.patch("streamlit.secrets", fake_secrets):
        with mock.patch.dict(
            os.environ,
            {
                "WATSONX_API_KEY": "env-key",
                "WATSONX_PROJECT_ID": "22222222-2222-2222-2222-222222222222",
            },
        ):
            cfg = WatsonxConfig.from_sources()
            assert cfg.api_key == "secret-key"
            assert cfg.project_id == "11111111-1111-1111-1111-111111111111"
            assert cfg.source_map["api_key"] == "st.secrets"
            assert cfg.source_map["project_id"] == "st.secrets"
            assert cfg.validate().is_valid is True


def test_from_sources_fallback_to_environ():
    """When st.secrets has no watsonx keys, falls back safely to os.environ."""
    fake_secrets = {}
    with mock.patch("streamlit.secrets", fake_secrets):
        with mock.patch.dict(
            os.environ,
            {
                "WATSONX_API_KEY": "env-key",
                "WATSONX_PROJECT_ID": "12345678-abcd-ef01-2345-6789abcdef01",
            },
        ):
            cfg = WatsonxConfig.from_sources()
            assert cfg.api_key == "env-key"
            assert cfg.project_id == "12345678-abcd-ef01-2345-6789abcdef01"
            assert cfg.source_map["api_key"] == "os.environ"
            assert cfg.source_map["project_id"] == "os.environ"
            assert cfg.validate().is_valid is True
