"""
tests/test_ibm_auth.py — IBM Cloud IAM authentication adapter and SDK routing tests.

Verifies:
- SDK HrefDefinitions IAM URL resolution defect with trailing slash.
- SDK resolution to production IAM with normalized endpoint.
- IBMCloudIAMClient credential construction and validation.
- Deterministic exception categorization.
- Zero credential leakage during auth failures.
"""

import unittest.mock as mock
import pytest

from core.config import WatsonxConfig, normalize_watsonx_url
from ibm.auth import IBMCloudIAMClient, PRODUCTION_IAM_TOKEN_URL
from ibm.exceptions import (
    CATEGORY_AUTH_ENDPOINT_MISCONFIGURED,
    CATEGORY_AUTH_INVALID_CREDENTIALS,
    CATEGORY_AUTH_NETWORK_ERROR,
    CATEGORY_AUTH_TIMEOUT,
    CATEGORY_CONFIG_CREDENTIAL_FORMAT,
    CATEGORY_CONFIG_MALFORMED,
    CATEGORY_CONFIG_MISSING,
    CATEGORY_WATSONX_MODEL_ERROR,
    CATEGORY_WATSONX_PROJECT_ERROR,
    CATEGORY_WATSONX_UNAUTHORIZED,
    IBMAuthError,
    IBMConfigError,
    WatsonxError,
    categorize_ibm_exception,
)


# ===========================================================================
# 1. SDK Routing & Trailing Slash Tests (Reproduced & Verified)
# ===========================================================================

def test_sdk_href_definitions_trailing_slash_selects_staging_endpoint():
    """
    Directly exercises installed ibm_watsonx_ai.href_definitions.HrefDefinitions.
    Proves that an unnormalized URL with trailing slash selects test/staging IAM.
    """
    from ibm_watsonx_ai.href_definitions import HrefDefinitions

    unnormalized = "https://us-south.ml.cloud.ibm.com/"
    hd = HrefDefinitions(
        url=unnormalized,
        instance_id="",
        version=None,
        bedrock_url=None,
        cloud_platform_spaces=False,
        cp4d_platform_spaces=False,
        platform_url="",
        project_type="project",
        auth_url=None,
    )
    # The installed SDK bug routes unnormalized URL to iam.test.cloud.ibm.com
    assert hd.get_iam_token_url() == "https://iam.test.cloud.ibm.com/identity/token"


def test_sdk_href_definitions_normalized_selects_production_endpoint():
    """
    Proves that normalize_watsonx_url cures the SDK defect and selects production IAM.
    """
    from ibm_watsonx_ai.href_definitions import HrefDefinitions

    raw_url = "https://us-south.ml.cloud.ibm.com/"
    normalized = normalize_watsonx_url(raw_url)

    hd = HrefDefinitions(
        url=normalized,
        instance_id="",
        version=None,
        bedrock_url=None,
        cloud_platform_spaces=False,
        cp4d_platform_spaces=False,
        platform_url="",
        project_type="project",
        auth_url=None,
    )
    # Normalized URL resolves to production IAM
    assert hd.get_iam_token_url() == "https://iam.cloud.ibm.com/identity/token"


def test_sdk_href_definitions_all_global_regions_normalized():
    """
    Verifies that all supported global IBM Cloud watsonx.ai regions resolve to
    production IAM after normalization.
    """
    from ibm_watsonx_ai.href_definitions import HrefDefinitions

    regions = [
        "https://us-south.ml.cloud.ibm.com/",
        "https://eu-gb.ml.cloud.ibm.com/",
        "https://eu-de.ml.cloud.ibm.com/",
        "https://jp-tok.ml.cloud.ibm.com/",
        "https://ca-tor.ml.cloud.ibm.com/",
        "https://au-syd.ml.cloud.ibm.com/",
    ]
    for raw in regions:
        normalized = normalize_watsonx_url(raw)
        hd = HrefDefinitions(
            url=normalized,
            instance_id="",
            version=None,
            bedrock_url=None,
            cloud_platform_spaces=False,
            cp4d_platform_spaces=False,
            platform_url="",
            project_type="project",
            auth_url=None,
        )
        assert hd.get_iam_token_url() == "https://iam.cloud.ibm.com/identity/token"


def test_sdk_aws_endpoint_protocol_divergence():
    """
    Proves that AWS watsonx.ai endpoints route to SaaS IAM (account-iam.platform.saas.ibm.com)
    via get_aws_token_url rather than standard IBM Cloud IAM (iam.cloud.ibm.com),
    justifying why AWS endpoints cannot share the IBM Cloud Lite adapter.
    """
    from ibm_watsonx_ai.href_definitions import HrefDefinitions

    hd = HrefDefinitions(
        url="https://ap-south-1.aws.wxai.ibm.com",
        instance_id="",
        version=None,
        bedrock_url=None,
        cloud_platform_spaces=False,
        cp4d_platform_spaces=False,
        platform_url="",
        project_type="project",
        auth_url=None,
    )
    assert hd.get_aws_token_url() == "https://account-iam.platform.saas.ibm.com/api/2.0/apikeys/token"


# ===========================================================================
# 2. IBMCloudIAMClient Adapter Tests
# ===========================================================================

def test_iam_client_creates_credentials_with_production_auth_url():
    """
    Verifies that IBMCloudIAMClient attaches the canonical URL and explicit production auth_url.
    """
    cfg = WatsonxConfig(
        api_key="valid-synthetic-api-key",
        project_id="12345678-abcd-ef01-2345-6789abcdef01",
        url="https://us-south.ml.cloud.ibm.com/",
    )
    client = IBMCloudIAMClient(cfg)

    fake_creds_cls = mock.MagicMock(return_value=mock.MagicMock())
    with mock.patch("ibm_watsonx_ai.Credentials", fake_creds_cls):
        creds = client.create_credentials()

    fake_creds_cls.assert_called_once_with(
        url="https://us-south.ml.cloud.ibm.com",
        api_key="valid-synthetic-api-key",
        auth_url=PRODUCTION_IAM_TOKEN_URL,
    )


def test_iam_client_validation_missing_key():
    cfg = WatsonxConfig(api_key="", project_id="12345678-abcd-ef01-2345-6789abcdef01")
    client = IBMCloudIAMClient(cfg)
    with pytest.raises(IBMConfigError) as exc_info:
        client.create_credentials()
    assert exc_info.value.category == CATEGORY_CONFIG_MISSING


def test_iam_client_validation_quoted_key():
    cfg = WatsonxConfig(
        api_key='"literal-quoted-key"',
        project_id="12345678-abcd-ef01-2345-6789abcdef01",
    )
    client = IBMCloudIAMClient(cfg)
    with pytest.raises(IBMConfigError) as exc_info:
        client.create_credentials()
    assert exc_info.value.category == CATEGORY_CONFIG_CREDENTIAL_FORMAT


def test_iam_client_safe_status_no_secrets():
    sentinel = "SECRET-KEY-TO-NOT-LEAK-XYZ"
    cfg = WatsonxConfig(
        api_key=sentinel,
        project_id="12345678-abcd-ef01-2345-6789abcdef01",
    )
    client = IBMCloudIAMClient(cfg)
    status = client.get_safe_status()
    assert sentinel not in str(status)
    assert status["production_iam_enforced"] is True


# ===========================================================================
# 3. Deterministic Error Categorization Tests
# ===========================================================================

def test_categorize_bxnim0415e():
    raw_error = Exception('{"errorCode":"BXNIM0415E","errorMessage":"Provided API key could not be found."}')
    cat, user_msg = categorize_ibm_exception(raw_error)
    assert cat == CATEGORY_AUTH_INVALID_CREDENTIALS
    assert "BXNIM0415E" not in user_msg  # sanitized user-facing message


def test_categorize_timeout():
    cat, _ = categorize_ibm_exception(TimeoutError("request timed out"))
    assert cat == CATEGORY_AUTH_TIMEOUT


def test_categorize_network_connection():
    cat, _ = categorize_ibm_exception(ConnectionError("Failed to establish a connection"))
    assert cat == CATEGORY_AUTH_NETWORK_ERROR


def test_categorize_403_unauthorized():
    cat, _ = categorize_ibm_exception(Exception("403 Forbidden: Insufficient permissions for project"))
    assert cat == CATEGORY_WATSONX_UNAUTHORIZED


def test_categorize_404_project_not_found():
    cat, _ = categorize_ibm_exception(Exception("404: Watson Machine Learning project not found"))
    assert cat == CATEGORY_WATSONX_PROJECT_ERROR


def test_categorize_model_unavailable():
    cat, _ = categorize_ibm_exception(Exception("Model ibm/granite-4-h-small is not supported in region"))
    assert cat == CATEGORY_WATSONX_MODEL_ERROR


def test_categorize_endpoint_misconfigured():
    cat, _ = categorize_ibm_exception(Exception("invalid_auth_url: cannot connect to staging auth"))
    assert cat == CATEGORY_AUTH_ENDPOINT_MISCONFIGURED


# ===========================================================================
# 4. Credential Leakage Protection Tests
# ===========================================================================

def test_categorize_does_not_leak_bearer_or_api_key():
    sentinel_key = "MY-SECRET-API-KEY-777"
    raw_sensitive_error = Exception(f"Failed auth for key {sentinel_key} with Bearer eyJhbGciOiJIUzI1Ni.abc.def")

    cat, user_msg = categorize_ibm_exception(raw_sensitive_error)
    assert cat == CATEGORY_AUTH_INVALID_CREDENTIALS
    assert sentinel_key not in user_msg
    assert "eyJhbGciOi" not in user_msg
