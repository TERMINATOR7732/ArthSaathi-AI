"""
streamlit_app.py — ArthSaathi AI Streamlit Application.

Digital Financial Literacy and UPI Fraud Awareness for Indian citizens.
IBM SkillsBuild AICTE Internship 2026 · Problem Statement No. 7.

Architecture & Components:
  - Mission Control: Digital public safety hero, emergency banner, action entry points.
  - AI Scam Advisor: RAG-grounded chat with live IBM Granite / offline fallback.
  - Loan Cost Calculator: Objective annualized borrowing cost estimation and risk indicators.
  - 1930 Emergency Guide: Actionable 5-step cyber-fraud response protocol and RBI liability framework.
"""

from __future__ import annotations

import html
import time
from typing import Optional

import streamlit as st

from arthsaathi_agent import (
    ArthSaathiOrchestrator,
    calculate_annualized_cost,
    detect_language,
    get_config_var,
    get_deterministic_greeting,
    is_greeting,
)
from ui import (
    TAB_EMERGENCY_GUIDE,
    TAB_LOAN_CALCULATOR,
    TAB_SCAM_ADVISOR,
    TAB_TITLES,
    VIEW_EMERGENCY_GUIDE,
    VIEW_LOAN_CALCULATOR,
    VIEW_MAP,
    VIEW_SCAM_ADVISOR,
    get_svg_icon,
    inject_ui_styles,
    render_action_cards,
    render_emergency_banner,
    render_fraud_alerts,
    render_header,
    render_official_portals,
    render_sidebar_diagnostics,
    render_source_badge,
)

# ---------------------------------------------------------------------------
# Page configuration
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="ArthSaathi AI — Financial Literacy & UPI Fraud Shield",
    page_icon="₹",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Singleton orchestrator initialization
# ---------------------------------------------------------------------------

@st.cache_resource(show_spinner=False)
def get_orchestrator() -> ArthSaathiOrchestrator:
    """Initialize and cache the single ArthSaathiOrchestrator instance."""
    return ArthSaathiOrchestrator()

orchestrator = get_orchestrator()

# ---------------------------------------------------------------------------
# Session state initialization
# ---------------------------------------------------------------------------

if "messages" not in st.session_state:
    st.session_state.messages = []
if "is_processing" not in st.session_state:
    st.session_state.is_processing = False
if "theme_mode" not in st.session_state:
    st.session_state.theme_mode = "Light"
if "language_preference" not in st.session_state:
    st.session_state.language_preference = "Auto-detect"
if "conversation_language" not in st.session_state:
    st.session_state.conversation_language = "en"
if "last_processed_query_sig" not in st.session_state:
    st.session_state.last_processed_query_sig = None
if "active_view" not in st.session_state:
    st.session_state.active_view = VIEW_SCAM_ADVISOR

# ---------------------------------------------------------------------------
# Modern UI Styling & Theme Injection (via modular ui/ package)
# ---------------------------------------------------------------------------

inject_ui_styles(st.session_state.theme_mode)

# ---------------------------------------------------------------------------
# Sidebar: Brand, System Diagnostics, Controls & Safe Links
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown(
        """
        <div style="display:flex; align-items:center; gap:0.6rem; margin-bottom:0.4rem;">
            <div style="font-size:1.8rem; font-weight:800; color:#0F62FE; line-height:1;">₹</div>
            <div>
                <h2 style="font-size:1.45rem; font-weight:800; margin:0; line-height:1.2; letter-spacing:-0.02em;">ArthSaathi AI</h2>
                <div style="font-size:0.82rem; color:#64748B; margin:0;">Understand · Verify · Protect</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("---")

    # Diagnostics & Status Badge
    st.subheader("System Status")
    _llm_configured = orchestrator.llm_configured
    _llm_ready = orchestrator.llm_ready
    _llm_init_error: Optional[str] = getattr(orchestrator, "llm_init_error", None)

    if _llm_configured and _llm_ready:
        st.markdown(
            '<span class="as-source-badge as-badge-granite">● IBM Client Initialized</span>',
            unsafe_allow_html=True,
        )
        st.caption("Model: `ibm/granite-4-h-small` · US South (Dallas) · Inference on-demand")
    elif _llm_configured and not _llm_ready:
        st.markdown(
            '<span class="as-source-badge as-badge-warning">⚠ Init Failed · Offline Fallback</span>',
            unsafe_allow_html=True,
        )
        if _llm_init_error:
            st.caption(f"SDK init note: `{_llm_init_error}`. Safe offline mode active.")
        else:
            st.caption("SDK initialization in offline fallback mode.")
    else:
        st.markdown(
            '<span class="as-source-badge as-badge-offline">○ Credentials Not Configured</span>',
            unsafe_allow_html=True,
        )
        st.caption("Operating in offline mode with local financial reference content.")

    kb_count = len(orchestrator.rag.passages)
    st.caption(f"Local Financial Reference Content: **{kb_count} passages** active.")

    # Expandable Safe Diagnostics
    render_sidebar_diagnostics(orchestrator)

    st.markdown("---")

    # Multilingual selection
    st.subheader("Language Setting")
    lang_options = [
        "Auto-detect",
        "English",
        "हिन्दी (Hindi)",
        "मराठी (Marathi)",
        "Hinglish",
    ]
    current_lang_idx = (
        lang_options.index(st.session_state.language_preference)
        if st.session_state.language_preference in lang_options
        else 0
    )
    selected_lang = st.selectbox(
        "Response Language",
        options=lang_options,
        index=current_lang_idx,
        help="Select your preferred language or leave on Auto-detect.",
    )
    if selected_lang != st.session_state.language_preference:
        st.session_state.language_preference = selected_lang
        st.rerun()

    # Theme toggle
    st.subheader("Theme & Display")
    theme_choice = st.radio(
        "Interface Theme",
        options=["Light", "Dark"],
        index=0 if st.session_state.theme_mode == "Light" else 1,
        horizontal=True,
    )
    if theme_choice != st.session_state.theme_mode:
        st.session_state.theme_mode = theme_choice
        st.rerun()

    st.markdown("---")

    # 24x7 Emergency Contact Box in Sidebar
    phone_icon = get_svg_icon("phone_call", size=15, color="#DA1E28")
    st.markdown(
        f"""
        <div class="as-emergency-banner" style="padding:0.75rem 0.9rem; margin-bottom:1rem;">
            <strong style="color:#DA1E28; font-size:0.8rem; text-transform:uppercase; letter-spacing:0.04em;">
                {phone_icon} 24×7 Cybercrime Helpline
            </strong>
            <div style="margin: 0.3rem 0;">
                <a href="tel:1930" class="as-emergency-call-btn" style="padding:0.35rem 0.8rem; font-size:0.95rem;">Call 1930</a>
            </div>
            <p style="font-size:0.78rem; margin:0; line-height:1.35; color:#1E293B;">
                Report immediately. Prompt reporting helps authorities take timely action. Fund freeze or refund is not guaranteed.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Official verification portals
    render_official_portals()

    # Chat reset button
    if st.button("Reset Conversation", use_container_width=True):
        st.session_state.messages = []
        st.session_state.conversation_language = "en"
        st.session_state.last_processed_query_sig = None
        st.rerun()


# ---------------------------------------------------------------------------
# SCREEN 1: Mission Control Hero & Immediate Escalation
# ---------------------------------------------------------------------------

render_header(st.session_state.conversation_language)
render_emergency_banner()
render_action_cards()

st.markdown("<div style='margin-top: 1.25rem;'></div>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# State-Driven Navigation
# ---------------------------------------------------------------------------

current_nav_label = VIEW_MAP.get(st.session_state.active_view, TAB_SCAM_ADVISOR)
selected_nav_label = st.radio(
    "Navigation Views",
    options=TAB_TITLES,
    index=TAB_TITLES.index(current_nav_label) if current_nav_label in TAB_TITLES else 0,
    horizontal=True,
    label_visibility="collapsed",
    key="main_navigation_selector",
)

# Synchronize active_view if user directly toggles the radio control
for v_key, v_title in VIEW_MAP.items():
    if v_title == selected_nav_label and st.session_state.active_view != v_key:
        st.session_state.active_view = v_key
        st.rerun()

st.markdown("<div style='margin-top: 0.8rem;'></div>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# SCREEN 2: AI Scam Advisor
# ---------------------------------------------------------------------------

if st.session_state.active_view == VIEW_SCAM_ADVISOR:
    st.markdown(
        """
        <div style="margin-bottom: 0.8rem;">
            <h2 style="margin:0; font-size:1.35rem; font-weight:700;">Digital Financial Literacy & Scam Advisor</h2>
            <p style="color:#64748B; font-size:0.9rem; margin:0.2rem 0 0.8rem 0;">
                Grounded in official RBI and NPCI guidelines. Check suspicious UPI payments, verify loan offers, or learn your consumer rights.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Offline banner if LLM not configured
    if not (orchestrator.llm_configured and orchestrator.llm_ready):
        st.info(
            "**Offline Mode**: IBM Granite credentials are not configured or connecting. "
            "ArthSaathi is serving verified answers directly from local financial reference content."
        )

    # Display Chat History or Empty State Starter Questions
    if not st.session_state.messages:
        # Seed welcome message
        st.markdown(
            """
            <div class="as-header-card" style="margin-bottom: 0.8rem; border-left: 4px solid #0F62FE;">
                <h4 style="margin:0 0 0.3rem 0; font-size:1.05rem; font-weight:700;">Namaste! I am ArthSaathi, your digital financial safety assistant.</h4>
                <p style="margin:0 0 0.4rem 0; font-size:0.9rem; color:#475569;">
                    Ask me about UPI security rules, suspicious payment requests, digital loan apps, or banking consumer rights.
                </p>
                <em style="font-size:0.85rem; color:#64748B;">You can communicate in English, Hindi (हिन्दी), Marathi (मराठी), or Hinglish.</em>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown("**Suggested questions to get started:**")
        col1, col2 = st.columns(2)
        starters = [
            ("Someone asked me to scan a QR code to receive money.", "The #1 marketplace payment scam explained."),
            ("How do I identify a UPI collect request scam?", "Recognize fake collect requests and phishing."),
            ("I received a suspicious part-time job offer.", "Identify task scams and illegal account mule traps."),
            ("How do I report unauthorized UPI transactions?", "Step-by-step CFCFRMS protocol and 1930 helpline."),
        ]

        for idx, (q, desc) in enumerate(starters):
            target_col = col1 if idx % 2 == 0 else col2
            with target_col:
                if st.button(q, key=f"starter_{idx}", use_container_width=True):
                    st.session_state.pending_prompt = q
                    st.rerun()

    # Render conversation
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            if msg["role"] == "assistant" and "source" in msg:
                render_source_badge(msg["source"], msg.get("model_id"))

            if msg.get("fraud_alerts"):
                render_fraud_alerts(msg["fraud_alerts"])

            st.markdown(msg["content"])

            if msg.get("passages"):
                with st.expander("Reference Material Citations", expanded=False):
                    for p in msg["passages"]:
                        st.markdown(f"**Passage:** `{p['id']}`")
                        st.caption(p["text"])

            if msg.get("latency_ms"):
                st.caption(
                    f"Latency — Retrieval: {msg['latency_ms'].get('retrieval', 0.0)}ms | "
                    f"Provider: {msg['latency_ms'].get('provider', 0.0)}ms | "
                    f"Total: {msg['latency_ms'].get('total', 0.0)}ms"
                )

    # Handle pending starter prompt if clicked
    prompt_to_process = None
    if "pending_prompt" in st.session_state and st.session_state.pending_prompt:
        prompt_to_process = st.session_state.pending_prompt
        st.session_state.pending_prompt = None

    # Chat input widget
    user_input = st.chat_input(
        "Ask about UPI security, suspicious payment requests, or loan offers...",
        disabled=st.session_state.is_processing,
    )

    active_prompt = prompt_to_process or user_input

    if active_prompt and not st.session_state.is_processing:
        clean_query = active_prompt.strip()
        query_sig = f"{clean_query}:{len(st.session_state.messages)}"

        if query_sig != st.session_state.last_processed_query_sig:
            st.session_state.is_processing = True
            st.session_state.last_processed_query_sig = query_sig

            st.session_state.messages.append({
                "role": "user",
                "content": clean_query,
            })

            with st.chat_message("user"):
                st.markdown(clean_query)

            try:
                # Multilingual detection & routing
                pref = st.session_state.language_preference
                if pref == "English":
                    target_lang = "en"
                elif pref == "हिन्दी (Hindi)":
                    target_lang = "hi"
                elif pref == "मराठी (Marathi)":
                    target_lang = "mr"
                elif pref == "Hinglish":
                    target_lang = "hinglish"
                else:
                    detected = detect_language(clean_query)
                    greeting_flag, _ = is_greeting(clean_query)
                    words = clean_query.split()
                    if len(words) <= 2 and greeting_flag and st.session_state.conversation_language != "en":
                        target_lang = st.session_state.conversation_language
                    else:
                        target_lang = detected
                        st.session_state.conversation_language = detected

                with st.chat_message("assistant"):
                    with st.spinner("Analyzing with financial reference content & IBM Granite..."):
                        response = orchestrator.answer(clean_query, target_lang=target_lang)

                    render_source_badge(response.source, response.model_id)
                    render_fraud_alerts(response.fraud_alerts)
                    st.markdown(response.answer)

                    passage_data = [{"id": p.id, "text": p.text[:400]} for p in response.passages]
                    if passage_data:
                        with st.expander("Reference Material Citations", expanded=False):
                            for p in passage_data:
                                st.markdown(f"**Passage:** `{p['id']}`")
                                st.caption(p["text"])

                    if response.latency_ms:
                        st.caption(
                            f"Latency — Retrieval: {response.latency_ms.get('retrieval', 0.0)}ms | "
                            f"Provider: {response.latency_ms.get('provider', 0.0)}ms | "
                            f"Total: {response.latency_ms.get('total', 0.0)}ms"
                        )

                st.session_state.messages.append({
                    "role": "assistant",
                    "content": response.answer,
                    "source": response.source,
                    "model_id": response.model_id,
                    "status": response.status,
                    "error_category": response.error_category,
                    "fraud_alerts": response.fraud_alerts,
                    "emergency": response.emergency,
                    "passages": passage_data,
                    "latency_ms": response.latency_ms,
                })
            finally:
                st.session_state.is_processing = False
            st.rerun()


# ---------------------------------------------------------------------------
# SCREEN 3: Loan Cost Calculator
# ---------------------------------------------------------------------------

elif st.session_state.active_view == VIEW_LOAN_CALCULATOR:
    st.markdown(
        """
        <div style="margin-bottom: 0.8rem;">
            <h2 style="margin:0; font-size:1.35rem; font-weight:700;">Objective Loan Cost & Annualized Rate Calculator</h2>
            <p style="color:#64748B; font-size:0.9rem; margin:0.2rem 0 0.8rem 0;">
                Compute the true borrowing cost, net disbursement, and effective annualized rate to evaluate digital credit offers objectively.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col_in, col_out = st.columns([1, 1], gap="large")

    with col_in:
        with st.form("loan_calculator_form"):
            st.markdown("**Loan Parameters**")
            principal = st.number_input(
                "Sanctioned Loan Amount (Principal ₹)",
                min_value=1.0,
                max_value=100000000.0,
                value=10000.0,
                step=500.0,
                help="The gross loan amount sanctioned by the lender in the loan agreement.",
            )
            upfront_fees = st.number_input(
                "Upfront Processing Fees & Deductions (₹)",
                min_value=0.0,
                max_value=99999999.0,
                value=500.0,
                step=100.0,
                help="Fees, charges, or insurance deducted upfront before disbursing funds to your account.",
            )
            repayment = st.number_input(
                "Total Amount to Repay (₹)",
                min_value=1.0,
                max_value=100000000.0,
                value=12500.0,
                step=500.0,
                help="Total amount due across all scheduled repayments, including interest and fees.",
            )
            tenure_days = st.number_input(
                "Loan Tenure (Days)",
                min_value=1,
                max_value=36500,
                value=15,
                step=1,
                help="Total repayment duration in calendar days.",
            )

            calc_submitted = st.form_submit_button("Calculate Annualized Cost", use_container_width=True)

    with col_out:
        calc_result = calculate_annualized_cost(
            principal=principal,
            total_repayment=repayment,
            tenure_days=int(tenure_days),
            upfront_fees=upfront_fees,
        )

        if not calc_result["valid"]:
            for err in calc_result["errors"]:
                st.error(f"⚠️ {err}")
        else:
            annual_cost = calc_result["annualized_cost_pct"]
            net_disbursed = calc_result["net_disbursed"]
            total_borrowing_cost = calc_result["total_borrowing_cost"]

            st.markdown("### Calculation Summary")
            m_c1, m_c2 = st.columns(2)
            with m_c1:
                st.metric(
                    label="Gross Sanctioned",
                    value=f"₹{principal:,.2f}",
                )
            with m_c2:
                st.metric(
                    label="Net Disbursed to You",
                    value=f"₹{net_disbursed:,.2f}",
                    delta=f"-₹{upfront_fees:,.2f} upfront fee" if upfront_fees > 0 else "No upfront fee",
                    delta_color="off",
                )

            m_c3, m_c4 = st.columns(2)
            with m_c3:
                st.metric(
                    label="Total Repayment",
                    value=f"₹{repayment:,.2f}",
                )
            with m_c4:
                st.metric(
                    label="Estimated Annualized Cost",
                    value=f"{annual_cost:,.2f}%",
                    help="Simplified annualized rate based on effective borrowing period.",
                )

            st.info(f"**Borrowing Cost Assessment:** {calc_result['cost_explanation']}")

            with st.expander("RBI Digital Lending Due Diligence Checklist", expanded=True):
                st.markdown("**Verify these screening indicators before accepting any digital loan:**")
                for indicator in calc_result["risk_indicators"]:
                    st.markdown(f"- {indicator}")
                st.markdown(
                    "Always demand a **Key Fact Statement (KFS)** and verify the lending entity on the official "
                    "[RBI Sachet Portal (sachet.rbi.org.in)](https://sachet.rbi.org.in)."
                )

            st.markdown(
                """
                <div style="font-size:0.8rem; color:#64748B; margin-top:1rem; border-top:1px solid #E2E8F0; padding-top:0.6rem;">
                    <strong>Calculation formula:</strong> <code>((Repayment − Principal) / Principal) × (365 / Days) × 100</code><br>
                    <em>Disclaimer: This calculation provides a simplified annualized borrowing cost estimate for educational comparison. It does not replace the legally defined APR required in the standardized Key Fact Statement (KFS) under RBI Digital Lending Guidelines (DOR.CRE.REC.66/21.07.001/2022-23). The Reserve Bank of India does not set an arbitrary universal 36% APR legal ceiling; lenders must provide transparent upfront disclosure of all fees and charges.</em>
                </div>
                """,
                unsafe_allow_html=True,
            )


# ---------------------------------------------------------------------------
# SCREEN 4: 1930 Emergency Guide
# ---------------------------------------------------------------------------

elif st.session_state.active_view == VIEW_EMERGENCY_GUIDE:
    st.markdown(
        """
        <div style="margin-bottom: 0.8rem;">
            <h2 style="margin:0; font-size:1.35rem; font-weight:700;">Immediate Financial Fraud Escalation Protocol</h2>
            <p style="color:#64748B; font-size:0.9rem; margin:0.2rem 0 0.8rem 0;">
                If you have been scammed or noticed unauthorized transactions, take these steps immediately. Prompt reporting is critical.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    steps = [
        ("Step 1 — Call 1930 Immediately (National Cyber Financial Fraud Helpline)",
         "The **National Cyber Financial Fraud Helpline (1930)** operates 24×7 under the Ministry of Home Affairs / I4C. Calling promptly enables the Citizen Financial Cyber Fraud Reporting & Management System (CFCFRMS) to alert concerned banks and authorities to take timely action. *Note: I4C does not itself freeze accounts; fund freezing and recovery decisions rest with concerned financial institutions and investigating authorities under applicable law. A fund freeze, recovery, or refund is not guaranteed.*"),
        ("Step 2 — File a Complaint Online at cybercrime.gov.in",
         "Visit the official [National Cyber Crime Reporting Portal](https://cybercrime.gov.in). Submit transaction reference IDs (UTR), SMS debit alerts, beneficiary account/UPI details, and payment screenshots. Retain the formal acknowledgement number for reference."),
        ("Step 3 — Block Compromised Cards and UPI Access Immediately",
         "Use your bank's mobile application, net banking portal, or call the 24×7 customer care number on the back of your card to freeze compromised accounts, block payment cards, and disable UPI access."),
        ("Step 4 — Notify Your Bank Immediately in Writing",
         "Under the RBI Customer Liability Framework (Circular DBR.No.Leg.BC.78/09.07.005/2017-18):\n\n"
         "- **Bank Negligence or Deficiency:** Zero customer liability where the deficiency lies with the bank, regardless of when reported.\n"
         "- **Third-Party Breach:** Zero customer liability if reported within 3 working days of receiving bank communication. If reported within 4 to 7 working days, liability is limited according to RBI transaction slabs. Beyond 7 working days, the bank's board-approved policy governs.\n"
         "- **Customer Negligence:** If loss occurred due to sharing payment credentials (such as OTP, UPI PIN, or passwords), the customer bears the entire loss until reported to the bank; unauthorized transactions occurring after reporting are borne by the bank.\n\n"
         "*Always report immediately — do not delay. Refunds are not automatically guaranteed.*"),
        ("Step 5 — Preserve All Digital & Transaction Evidence",
         "Do not delete fraudulent SMS alerts, call logs, WhatsApp messages, APK files, or payment receipts. Investigating agencies and bank dispute resolution desks require these digital records for formal verification."),
    ]

    for title, desc in steps:
        st.markdown(
            f"""
            <div class="as-step-item">
                <div class="as-step-header">{html.escape(title)}</div>
                <div class="as-step-body">{desc}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("### Official Redressal Directory")
    contact_data = {
        "Agency / Portal": [
            "National Cyber Financial Fraud Helpline",
            "National Cybercrime Reporting Portal",
            "RBI Integrated Banking Ombudsman",
            "RBI Ombudsman Helpline",
            "NPCI UPI Dispute Resolution",
            "RBI Sachet (NBFC / App Verifier)",
        ],
        "Contact / Access Route": [
            "1930 (Toll-Free, 24×7)",
            "cybercrime.gov.in",
            "cms.rbi.org.in",
            "14448 (Toll-Free)",
            "npci.org.in/what-we-do/upi/dispute-redressal-mechanism",
            "sachet.rbi.org.in",
        ],
        "Purpose": [
            "Immediate alert to banks & intermediaries via CFCFRMS",
            "Official cybercrime complaint & evidence filing",
            "Bank grievance escalation (if unresolved > 30 days)",
            "Guidance on banking consumer rights",
            "UPI transaction dispute redressal",
            "Verify registered NBFCs and report illegal lending apps",
        ],
    }
    st.table(contact_data)

    st.caption(
        "Disclaimer: ArthSaathi AI provides educational guidance based on official RBI, NPCI, and Ministry of Home Affairs guidelines. "
        "It does not constitute formal legal counsel. For ongoing criminal investigations, always coordinate directly with local law enforcement."
    )
