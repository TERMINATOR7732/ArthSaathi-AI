"""
ui/components.py — Reusable, accessible UI components for ArthSaathi AI.

Renders modern public-service interface elements:
- Brand identity header and mission disclaimer.
- 1930 National Cyber Financial Fraud emergency banner.
- Action cards for quick entry points.
- Provenance & source badges for AI responses.
- Fraud alert callouts.
- Official verification portal expander.
- Leak-free sidebar diagnostics.
"""

from __future__ import annotations

import html
from typing import Any, Sequence

import streamlit as st


def render_header(lang: str = "en") -> None:
    """Render the primary Mission Control / Brand Identity header card."""
    st.markdown(
        """
        <div class="as-header-card">
            <span class="as-badge-pill">Digital Public Literacy Initiative</span>
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
        """,
        unsafe_allow_html=True,
    )


def render_emergency_banner() -> None:
    """Render the high-visibility, restrained 1930 Emergency Assistance panel."""
    st.markdown(
        """
        <div class="as-emergency-banner">
            <div class="as-emergency-title">
                🚨 24×7 National Cyber Financial Fraud Helpline
            </div>
            <div style="margin: 0.35rem 0;">
                <a href="tel:1930" class="as-emergency-call-btn">📞 Call 1930 Immediately</a>
            </div>
            <p class="as-emergency-text">
                <strong>Automatic Fund Freeze:</strong> Calling 1930 triggers the Citizen Financial Cyber Fraud
                Reporting & Management System (CFCFRMS), coordinating freeze protocols across 400+ connected banks.
            </p>
            <div class="as-emergency-text" style="font-size:0.8rem; margin-top:0.4rem;">
                Official Reporting Portal: <a href="https://cybercrime.gov.in" target="_blank" rel="noopener noreferrer"><strong>cybercrime.gov.in</strong></a> ·
                RBI Ombudsman: <a href="tel:14448"><strong>14448</strong></a> (Toll-free)
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_action_cards() -> None:
    """Render primary feature entry point cards for Mission Control."""
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(
            """
            <div class="as-action-card">
                <div class="as-action-title">🛡️ UPI & Payment Safety</div>
                <div class="as-action-desc">
                    Verify suspicious QR codes, check unexpected collect requests, and protect your UPI PIN.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            """
            <div class="as-action-card">
                <div class="as-action-title">📊 Loan Cost Calculator</div>
                <div class="as-action-desc">
                    Calculate annualized borrowing costs (APR) and identify predatory digital lending traps.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with c3:
        st.markdown(
            """
            <div class="as-action-card">
                <div class="as-action-title">🚨 1930 Emergency Guide</div>
                <div class="as-action-desc">
                    Actionable 5-step response sequence and RBI Zero-Liability 3-day reporting rule.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


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
    for alert in alerts:
        st.markdown(
            f'<div class="as-fraud-box">⚠️ {html.escape(alert)}</div>',
            unsafe_allow_html=True,
        )


def render_official_portals() -> None:
    """Render official verification portal links expander."""
    with st.expander("🏛️ Official Verification & Redressal Portals", expanded=False):
        st.markdown(
            """
            - **[cybercrime.gov.in](https://cybercrime.gov.in)** — National Cyber Crime Reporting Portal (MHA)
            - **[sachet.rbi.org.in](https://sachet.rbi.org.in)** — RBI portal to verify registered NBFCs and report illegal lending apps
            - **[cms.rbi.org.in](https://cms.rbi.org.in)** — RBI Complaint Management System (Banking Ombudsman)
            - **[npci.org.in](https://www.npci.org.in)** — National Payments Corporation of India official UPI safety guidelines
            - **[ceir.gov.in](https://ceir.gov.in)** — Central Equipment Identity Register to block stolen mobile devices
            """
        )


def render_sidebar_diagnostics(orchestrator: Any) -> None:
    """Render safe, leak-free system status in sidebar."""
    with st.expander("⚙️ System Status & Diagnostics", expanded=False):
        try:
            diag = orchestrator.get_safe_diagnostics()
            st.markdown(f"**Knowledge Base Passages:** `{len(orchestrator.rag.passages)}`")
            st.markdown(f"**Credentials Configured:** `{diag.get('configured', False)}`")
            st.markdown(f"**Foundation Model Ready:** `{diag.get('llm_ready', False)}`")
            st.markdown(f"**Endpoint Host:** `{diag.get('endpoint_host', 'none')}`")
            st.markdown(f"**Model Identifier:** `{diag.get('model_id', 'ibm/granite-4-h-small')}`")
            if diag.get("llm_init_error"):
                st.markdown(f"**Status Notice:** `{diag.get('llm_init_error')}`")
            if diag.get("error_category"):
                st.markdown(f"**Category:** `{diag.get('error_category')}`")
        except Exception:
            st.caption("Diagnostics offline.")
