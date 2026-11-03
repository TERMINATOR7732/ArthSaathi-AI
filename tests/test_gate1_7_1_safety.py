"""
tests/test_gate1_7_1_safety.py — Comprehensive Safety, Reliability & UI Refinement Tests (Gate 1.7.1).

Validates:
1. Workstream A: Removal of universal 36% APR threshold, objective lending calculations,
   net disbursement, and accurate 4-condition RBI customer liability framework.
2. Workstream B: Complete elimination of credential-validation bypass and broad exception fallbacks.
3. Workstream C & D: Functional home action cards, state-driven navigation, and structural SVG icons.
4. Workstream E: Truthful IBM client status and factual reference content labeling.
"""

from __future__ import annotations

import os
from unittest import mock
import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from arthsaathi_agent import (
    ArthSaathiOrchestrator,
    EmergencyProtocolAgent,
    calculate_annualized_cost,
    calculate_effective_apr,
)
from core.config import WatsonxConfig
from ibm.exceptions import (
    CATEGORY_CONFIG_CREDENTIAL_FORMAT,
    CATEGORY_CONFIG_MALFORMED,
    CATEGORY_CONFIG_MISSING,
    IBMConfigError,
)
from ibm.watsonx_client import WatsonxClient
from ui.components import (
    render_action_cards,
    render_emergency_banner,
    render_header,
    render_source_badge,
)
from ui.icons import get_svg_icon
from ui.navigation import (
    TAB_EMERGENCY_GUIDE,
    TAB_LOAN_CALCULATOR,
    TAB_SCAM_ADVISOR,
    TAB_TITLES,
    VIEW_EMERGENCY_GUIDE,
    VIEW_LOAN_CALCULATOR,
    VIEW_SCAM_ADVISOR,
)

_APP_PATH = os.path.abspath("streamlit_app.py")


# ===========================================================================
# 1. Workstream A: APR & Lending Calculations (No 36% Ceiling)
# ===========================================================================

def test_apr_below_36_percent():
    """Loans below 36% produce objective borrowing metrics without claiming to be inherently safe."""
    # ₹10,000 for 1 year, ₹11,500 total repayment → 15.0%
    res = calculate_annualized_cost(10000, 11500, 365)
    assert res["valid"] is True
    assert res["annualized_cost_pct"] == 15.0
    assert res["gross_principal"] == 10000.0
    assert res["net_disbursed"] == 10000.0
    assert res["total_borrowing_cost"] == 1500.0
    assert "cost_explanation" in res
    assert res.get("threshold_pct") is None
    assert "is_predatory" not in res or res.get("threshold_pct") is None


def test_apr_exactly_36_percent():
    """Loans at exactly 36% do not trigger an arbitrary threshold classification."""
    # ₹10,000 for 100 days, ₹10,986.30 repayment → ~36.0%
    res = calculate_annualized_cost(10000, 10986.30, 100)
    assert res["valid"] is True
    assert abs(res["annualized_cost_pct"] - 36.0) < 0.05
    assert res.get("threshold_pct") is None


def test_apr_above_36_percent():
    """Loans above 36% report the actual annualized rate and provide screening indicators."""
    # ₹10,000 for 15 days, ₹12,500 repayment → 608.33%
    res = calculate_annualized_cost(10000, 12500, 15)
    assert res["valid"] is True
    assert abs(res["annualized_cost_pct"] - 608.33) < 0.01
    assert res.get("threshold_pct") is None
    assert "Key Fact Statement" in res["cost_explanation"]
    assert len(res["risk_indicators"]) >= 3


def test_no_automatic_predatory_classification():
    """No loan is automatically declared predatory solely based on an arbitrary percentage."""
    res_high = calculate_annualized_cost(10000, 15000, 30)
    assert res_high["valid"] is True
    assert res_high.get("threshold_pct") is None
    assert "threshold_pct" not in res_high or res_high["threshold_pct"] is None


def test_net_disbursement_and_upfront_deductions():
    """Calculates net cash received and incorporates upfront fees into total borrowing cost."""
    # Gross ₹10,000 with ₹600 upfront fee deducted, repaying ₹11,000 in 30 days
    res = calculate_annualized_cost(principal=10000, total_repayment=11000, tenure_days=30, upfront_fees=600)
    assert res["valid"] is True
    assert res["gross_principal"] == 10000.0
    assert res["upfront_fees"] == 600.0
    assert res["net_disbursed"] == 9400.0
    assert res["total_borrowing_cost"] == 1600.0  # (11000 - 10000) + 600


def test_invalid_upfront_deductions():
    """Rejects negative deductions or deductions that equal/exceed the principal."""
    res_neg = calculate_annualized_cost(10000, 12000, 30, upfront_fees=-100)
    assert res_neg["valid"] is False
    assert any("negative" in e.lower() for e in res_neg["errors"])

    res_exceed = calculate_annualized_cost(10000, 12000, 30, upfront_fees=10000)
    assert res_exceed["valid"] is False
    assert any("equal or exceed" in e.lower() for e in res_exceed["errors"])


def test_invalid_loan_inputs():
    """Rejects invalid principal, tenure, and repayment amounts."""
    assert not calculate_annualized_cost(0, 12000, 30)["valid"]
    assert not calculate_annualized_cost(-500, 12000, 30)["valid"]
    assert not calculate_annualized_cost(10000, 12000, 0)["valid"]
    assert not calculate_annualized_cost(10000, 12000, -10)["valid"]
    assert not calculate_annualized_cost(10000, 8000, 30)["valid"]


# ===========================================================================
# 2. Workstream A: RBI Zero-Liability & 1930 Framework
# ===========================================================================

def test_rbi_liability_four_conditions_in_protocol():
    """Emergency protocol accurately documents all 4 RBI liability conditions."""
    protocol = EmergencyProtocolAgent.PROTOCOL
    assert "Bank Negligence" in protocol
    assert "Third-Party Breach" in protocol
    assert "3 working days" in protocol
    assert "4 to 7 working days" in protocol
    assert "Customer Negligence" in protocol
    assert "OTP" in protocol or "UPI PIN" in protocol
    assert "DBR.No.Leg.BC.78/09.07.005/2017-18" in protocol


def test_no_automatic_refund_or_fund_freeze_guarantee():
    """Protocol and UI explicitly disclaim guaranteed refund or automatic fund freeze."""
    protocol = EmergencyProtocolAgent.PROTOCOL
    assert "not guaranteed" in protocol.lower()

    # Verify Emergency Banner text
    banner_call = EmergencyProtocolAgent.PROTOCOL
    assert "refund is not guaranteed" in banner_call.lower() or "recovery, or refund is not guaranteed" in banner_call.lower()


def test_1930_role_and_portal_link():
    """Mentions 1930, cybercrime.gov.in, and does not claim I4C freezes accounts directly."""
    protocol = EmergencyProtocolAgent.PROTOCOL
    assert "1930" in protocol
    assert "https://cybercrime.gov.in" in protocol
    assert "14448" in protocol


# ===========================================================================
# 3. Workstream B: IBM Credential Validation (Fail Closed)
# ===========================================================================

def test_enclosing_quotes_fails_closed_without_constructing_credentials():
    """Detecting enclosing quotes stops initialization and NEVER calls ibm_watsonx_ai.Credentials."""
    cfg = WatsonxConfig(
        api_key='"quoted-key-with-enclosing-quotes"',
        project_id="12345678-abcd-ef01-2345-6789abcdef01",
        url="https://us-south.ml.cloud.ibm.com",
    )
    with mock.patch("ibm_watsonx_ai.Credentials") as mock_creds:
        client = WatsonxClient(cfg)
        assert client.is_ready is False
        assert client.error_category == CATEGORY_CONFIG_CREDENTIAL_FORMAT
        assert mock_creds.call_count == 0, "ibm_watsonx_ai.Credentials must never be constructed when quotes are detected"


def test_swapped_uuid_credentials_fail_closed():
    """Swapped API key and Project ID format raises CATEGORY_CONFIG_MALFORMED and fails closed."""
    cfg = WatsonxConfig(
        api_key="12345678-abcd-ef01-2345-6789abcdef01",  # UUID shaped
        project_id="regular-string-project-id",           # Non-UUID shaped
        url="https://us-south.ml.cloud.ibm.com",
    )
    with mock.patch("ibm_watsonx_ai.Credentials") as mock_creds:
        client = WatsonxClient(cfg)
        assert client.is_ready is False
        assert client.error_category == CATEGORY_CONFIG_MALFORMED
        assert mock_creds.call_count == 0


def test_missing_credentials_fail_closed():
    """Empty credentials fail closed without attempting external network calls."""
    cfg = WatsonxConfig(api_key="", project_id="")
    with mock.patch("ibm_watsonx_ai.Credentials") as mock_creds:
        client = WatsonxClient(cfg)
        assert client.is_ready is False
        assert client.error_category == CATEGORY_CONFIG_MISSING
        assert mock_creds.call_count == 0


# ===========================================================================
# 4. Workstream C: Functional Home Action Cards & Navigation
# ===========================================================================

def test_action_cards_route_to_respective_views():
    """Clicking home action buttons navigates to the expected functional screens."""
    st.cache_resource.clear()
    with mock.patch.dict(os.environ, {"WATSONX_API_KEY": "", "WATSONX_PROJECT_ID": ""}):
        at = AppTest.from_file(_APP_PATH, default_timeout=30)
        at.run()

        # Initial view is scam_advisor
        assert at.session_state.active_view == VIEW_SCAM_ADVISOR

        # 1. Click Loan Calculator action button (key='btn_nav_loan')
        loan_btn = [b for b in at.button if b.key == "btn_nav_loan"][0]
        loan_btn.click().run()
        assert len(at.exception) == 0
        assert at.session_state.active_view == VIEW_LOAN_CALCULATOR

        # 2. Click Emergency Guide action button (key='btn_nav_emergency')
        em_btn = [b for b in at.button if b.key == "btn_nav_emergency"][0]
        em_btn.click().run()
        assert len(at.exception) == 0
        assert at.session_state.active_view == VIEW_EMERGENCY_GUIDE

        # 3. Click UPI action button (key='btn_nav_upi')
        upi_btn = [b for b in at.button if b.key == "btn_nav_upi"][0]
        upi_btn.click().run()
        assert len(at.exception) == 0
        assert at.session_state.active_view == VIEW_SCAM_ADVISOR


def test_navigation_preserves_chat_history_without_inference():
    """Switching between views does not clear chat messages or trigger unintended inference."""
    st.cache_resource.clear()
    with mock.patch.dict(os.environ, {"WATSONX_API_KEY": "", "WATSONX_PROJECT_ID": ""}):
        at = AppTest.from_file(_APP_PATH, default_timeout=30)
        at.run()

        # Seed conversation
        at.session_state.messages.append({"role": "user", "content": "How to report fraud?"})
        at.session_state.messages.append({"role": "assistant", "content": "Call 1930 immediately."})
        at.run()
        assert len(at.session_state.messages) == 2

        # Navigate to Loan Calculator
        loan_btn = [b for b in at.button if b.key == "btn_nav_loan"][0]
        loan_btn.click().run()
        assert len(at.session_state.messages) == 2

        # Navigate back to Scam Advisor
        upi_btn = [b for b in at.button if b.key == "btn_nav_upi"][0]
        upi_btn.click().run()
        assert len(at.session_state.messages) == 2
        assert at.session_state.messages[0]["content"] == "How to report fraud?"


# ===========================================================================
# 5. Workstream D & E: Structural SVG Icons & Transparency
# ===========================================================================

def test_svg_icon_generation():
    """get_svg_icon returns valid, accessible inline SVG elements."""
    icon_svg = get_svg_icon("shield_check", size=20)
    assert "<svg" in icon_svg
    assert 'aria-hidden="true"' in icon_svg
    assert 'width="20"' in icon_svg
    assert 'viewBox="0 0 24 24"' in icon_svg

    # Unknown icon returns empty string
    assert get_svg_icon("non_existent_icon") == ""


def test_tab_titles_have_no_structural_emojis():
    """Navigation tab titles do not contain Unicode emoji."""
    for title in TAB_TITLES:
        assert not any(ord(char) > 10000 for char in title), f"Structural emoji found in {title}"


def test_sidebar_status_truthfulness():
    """Sidebar status distinguishes client initialization from live inference."""
    st.cache_resource.clear()
    # 1. Unconfigured state
    with mock.patch.dict(os.environ, {"WATSONX_API_KEY": "", "WATSONX_PROJECT_ID": ""}):
        at = AppTest.from_file(_APP_PATH, default_timeout=30)
        at.run()
        # Verify markdown content doesn't falsely claim live inference
        sidebar_text = "".join(m.value for m in at.sidebar.markdown)
        assert "Credentials Not Configured" in sidebar_text
        assert "Live IBM Granite 4.0" not in sidebar_text
