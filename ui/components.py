"""
ui/components.py — Reusable, accessible UI components for ArthSaathi AI.

Renders modern public-service interface elements:
- Brand identity header, mission disclaimer, and factual reference trust cards.
- 1930 National Cyber Financial Fraud emergency banner with accurate authority explanations.
- Genuinely functional action cards routing to core application workflows.
- Provenance & source badges for AI responses.
- Fraud alert callouts with accessible SVG icons.
- Official verification portal expander.
- Leak-free sidebar diagnostics.
"""

from __future__ import annotations

import html
from typing import Any, Sequence

import streamlit as st
from ui.icons import get_svg_icon
from ui.navigation import (
    TAB_EMERGENCY_GUIDE,
    TAB_LOAN_CALCULATOR,
    TAB_SCAM_ADVISOR,
    VIEW_EMERGENCY_GUIDE,
    VIEW_LOAN_CALCULATOR,
    VIEW_SCAM_ADVISOR,
)


def render_header(lang: str = "en") -> None:
    """Render the primary Mission Control / Brand Identity header card and factual trust cards."""
    shield_icon = get_svg_icon("shield_check", size=14, color="#0F62FE")
    book_icon = get_svg_icon("book_open", size=14, color="#0F62FE")
    status_icon = get_svg_icon("circle_check", size=14, color="#0F62FE")

    st.markdown(
        f"""
        <div class="as-header-card">
            <span class="as-badge-pill">{shield_icon} Digital Public Literacy Initiative</span>
            <h1 class="as-title">ArthSaathi AI</h1>
            <div class="as-tagline">Understand. Verify. Protect.</div>
            <p class="as-support-text">
                Your digital financial safety companion for understanding UPI scams,
                evaluating loan offers, and accessing trusted financial consumer guidance.
            </p>
            <div class="as-disclaimer">
                <strong>Educational Assistant Notice:</strong> ArthSaathi AI is an educational digital literacy
                platform. It does not provide legal advice, process financial transactions, or act as an official
                banking portal. For unauthorized cyber fraud, call <strong>1930</strong> immediately.
            </div>
        </div>

        <div class="as-trust-row">
            <div class="as-trust-card">
                <div class="as-trust-title">
                    {shield_icon} Session-Based Conversation
                </div>
                <div class="as-trust-desc">
                    Conversation messages are maintained in the active application session. Do not enter OTPs, UPI PINs, passwords or sensitive credentials.
                </div>
            </div>
            <div class="as-trust-card">
                <div class="as-trust-title">
                    {book_icon} Local Financial Reference Content
                </div>
                <div class="as-trust-desc">
                    Educational financial safety references based on publicly available RBI and NPCI advisories.
                </div>
            </div>
            <div class="as-trust-card">
                <div class="as-trust-title">
                    {status_icon} IBM Granite Foundation
                </div>
                <div class="as-trust-desc">
                    Configured with IBM Granite foundation models via ibm-watsonx-ai SDK.
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_emergency_banner() -> None:
    """
    Render the high-visibility, restrained 1930 Emergency Assistance panel.
    Accurately explains the role of 1930 and CFCFRMS without claiming automatic fund freeze.
    """
    phone_icon = get_svg_icon("phone_call", size=16, color="#DA1E28")
    phone_btn_icon = get_svg_icon("phone_call", size=18, color="#FFFFFF")
    ext_icon = get_svg_icon("external_link", size=14)

    st.markdown(
        f"""
        <div class="as-emergency-banner">
            <div class="as-emergency-title">
                {phone_icon} 24×7 National Cyber Financial Fraud Helpline
            </div>
            <div style="margin: 0.35rem 0;">
                <a href="tel:1930" class="as-emergency-call-btn">{phone_btn_icon} Call 1930 Immediately</a>
            </div>
            <p class="as-emergency-text">
                Report financial cyber fraud immediately through <strong>1930</strong> or the National Cyber Crime Reporting Portal.
                Prompt reporting helps the concerned investigating authorities and financial institutions take timely action.
                <em>A fund freeze, recovery or refund is not guaranteed.</em>
            </p>
            <div class="as-emergency-text" style="font-size:0.8rem; margin-top:0.4rem;">
                Official Reporting Portal: <a href="https://cybercrime.gov.in" target="_blank" rel="noopener noreferrer"><strong>cybercrime.gov.in</strong> {ext_icon}</a> ·
                RBI Ombudsman: <a href="tel:14448"><strong>14448</strong></a> (Toll-free)
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_action_cards() -> None:
    """
    Render primary feature entry point cards for Mission Control.
    Uses native Streamlit buttons for genuine accessibility and state-driven navigation.
    """
    shield_icon = get_svg_icon("shield_check", size=16, color="#0F62FE")
    calc_icon = get_svg_icon("calculator", size=16, color="#0F62FE")
    phone_icon = get_svg_icon("phone_call", size=16, color="#0F62FE")

    c1, c2, c3 = st.columns(3)

    with c1:
        st.markdown(
            f"""
            <div class="as-action-card">
                <div>
                    <div class="as-action-title">{shield_icon} UPI & Payment Safety</div>
                    <div class="as-action-desc">
                        Verify suspicious QR codes, check unexpected collect requests, and protect your UPI PIN.
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("Analyze UPI Request", key="btn_nav_upi", use_container_width=True):
            st.session_state.active_view = VIEW_SCAM_ADVISOR
            st.session_state.main_navigation_selector = TAB_SCAM_ADVISOR
            st.rerun()

    with c2:
        st.markdown(
            f"""
            <div class="as-action-card">
                <div>
                    <div class="as-action-title">{calc_icon} Loan Cost Calculator</div>
                    <div class="as-action-desc">
                        Compute annualized borrowing costs (APR) and evaluate digital lending terms objectively.
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("Check Loan Offer", key="btn_nav_loan", use_container_width=True):
            st.session_state.active_view = VIEW_LOAN_CALCULATOR
            st.session_state.main_navigation_selector = TAB_LOAN_CALCULATOR
            st.rerun()

    with c3:
        st.markdown(
            f"""
            <div class="as-action-card">
                <div>
                    <div class="as-action-title">{phone_icon} 1930 Emergency Guide</div>
                    <div class="as-action-desc">
                        Immediate golden-hour reporting steps, bank notification, and evidence preservation checklist.
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("Get Emergency Guidance", key="btn_nav_emergency", use_container_width=True):
            st.session_state.active_view = VIEW_EMERGENCY_GUIDE
            st.session_state.main_navigation_selector = TAB_EMERGENCY_GUIDE
            st.rerun()


def render_source_badge(source: str, model_id: str | None = None) -> None:
    """Render accurate response-source provenance badges."""
    clean_src = (source or "").strip()

    if clean_src == "granite":
        label = "Live IBM Granite"
        if model_id:
            label += f" · {model_id.replace('ibm/', '')}"
        css_cls = "as-badge-granite"
    elif clean_src == "offline_kb":
        label = "Offline Knowledge Base"
        css_cls = "as-badge-offline"
    elif clean_src == "not_configured":
        label = "Offline Knowledge Base · Credentials Not Configured"
        css_cls = "as-badge-warning"
    elif clean_src.startswith("provider_error:") or clean_src == "provider_error":
        label = "Offline Knowledge Base · IBM Unavailable"
        css_cls = "as-badge-warning"
    elif clean_src == "rule_based":
        label = "Rule-based Guidance"
        css_cls = "as-badge-offline"
    else:
        label = html.escape(clean_src)
        css_cls = "as-badge-offline"

    st.markdown(
        f'<span class="as-source-badge {css_cls}">{html.escape(label)}</span>',
        unsafe_allow_html=True,
    )


def render_fraud_alerts(alerts: Sequence[str]) -> None:
    """Render high-priority intercepted fraud warnings."""
    if not alerts:
        return
    alert_icon = get_svg_icon("shield_alert", size=16, color="#DA1E28")
    for alert in alerts:
        st.markdown(
            f'<div class="as-fraud-box">{alert_icon} <strong>Warning:</strong> {html.escape(alert)}</div>',
            unsafe_allow_html=True,
        )


def render_official_portals() -> None:
    """Render official verification portal links expander."""
    portal_icon = get_svg_icon("external_link", size=14)
    with st.expander("Official Verification & Redressal Portals", expanded=False):
        st.markdown(
            f"""
            - **[cybercrime.gov.in](https://cybercrime.gov.in)** — National Cyber Crime Reporting Portal (MHA) {portal_icon}
            - **[sachet.rbi.org.in](https://sachet.rbi.org.in)** — RBI portal to verify registered NBFCs and report illegal lending apps {portal_icon}
            - **[cms.rbi.org.in](https://cms.rbi.org.in)** — RBI Complaint Management System (Banking Ombudsman) {portal_icon}
            - **[npci.org.in](https://www.npci.org.in)** — National Payments Corporation of India official UPI safety guidelines {portal_icon}
            - **[ceir.gov.in](https://ceir.gov.in)** — Central Equipment Identity Register to block stolen mobile devices {portal_icon}
            """
        )


def render_sidebar_diagnostics(orchestrator: Any) -> None:
    """Render safe, leak-free system status in sidebar."""
    with st.expander("System Status & Diagnostics", expanded=False):
        try:
            diag = orchestrator.get_safe_diagnostics()
            st.markdown(f"**Local Reference Passages:** `{len(orchestrator.rag.passages)}`")
            st.markdown(f"**Credentials Configured:** `{diag.get('configured', False)}`")
            st.markdown(f"**Foundation Model Client Initialized:** `{diag.get('llm_ready', False)}`")
            st.markdown(f"**Endpoint Host:** `{diag.get('endpoint_host', 'none')}`")
            st.markdown(f"**Model Identifier:** `{diag.get('model_id', 'ibm/granite-4-h-small')}`")
            if diag.get("llm_init_error"):
                st.markdown(f"**Status Notice:** `{diag.get('llm_init_error')}`")
            if diag.get("error_category"):
                st.markdown(f"**Category:** `{diag.get('error_category')}`")
        except Exception:
            st.caption("Diagnostics offline.")
