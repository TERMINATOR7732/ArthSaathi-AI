"""
streamlit_app.py — ArthSaathi AI Streamlit Application.

Digital Financial Literacy and UPI Fraud Awareness for Indian citizens.
IBM SkillsBuild AICTE Internship 2026 · Problem Statement No. 7.

Architecture & Components:
  - 🛡️ Mission Control: Digital public safety hero, emergency banner, action entry points.
  - 💬 AI Scam Advisor: RAG-grounded chat with live IBM Granite / offline fallback.
  - 📊 Loan Cost Calculator: Annualized borrowing cost estimation with predatory warnings.
  - 🚨 1930 Emergency Guide: Actionable 5-step cyber-fraud response protocol.
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
    TAB_TITLES,
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
            '<span class="as-source-badge as-badge-granite">● Live IBM Granite 4.0</span>',
            unsafe_allow_html=True,
        )
        st.caption("Model: `ibm/granite-4-h-small` · US South (Dallas)")
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
            '<span class="as-source-badge as-badge-offline">○ Offline Knowledge Base</span>',
            unsafe_allow_html=True,
        )
        st.caption("Operating in offline RAG mode with curated RBI/NPCI guidelines.")

    kb_count = len(orchestrator.rag.passages)
    st.caption(f"Verified Knowledge Base: **{kb_count} passages** active.")

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
    st.markdown(
        """
        <div class="as-emergency-banner" style="padding:0.75rem 0.9rem; margin-bottom:1rem;">
            <strong style="color:#DA1E28; font-size:0.8rem; text-transform:uppercase; letter-spacing:0.04em;">🚨 24×7 Cybercrime Helpline</strong>
            <div style="margin: 0.3rem 0;">
                <a href="tel:1930" class="as-emergency-call-btn" style="padding:0.35rem 0.8rem; font-size:0.95rem;">📞 Call 1930</a>
            </div>
            <p style="font-size:0.78rem; margin:0; line-height:1.35; color:#1E293B;">
                Automated fund-freeze across 400+ banks via CFCFRMS.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Official verification portals
    render_official_portals()

    # Chat reset button
    if st.button("🗑️ Reset Chat Conversation", use_container_width=True):
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
# Navigation Tabs
# ---------------------------------------------------------------------------

tab_chat, tab_calc, tab_emergency = st.tabs(TAB_TITLES)

# ---------------------------------------------------------------------------
# SCREEN 2 / TAB 1: AI Scam Advisor
# ---------------------------------------------------------------------------

with tab_chat:
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
            "ℹ️ **Offline Mode**: IBM Granite credentials are not configured or connecting. "
            "ArthSaathi is serving verified answers directly from the local RBI/NPCI knowledge base."
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
                if st.button(f"🔍 {q}", key=f"starter_{idx}", use_container_width=True):
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
                with st.expander("📚 Knowledge Base Citations", expanded=False):
                    for p in msg["passages"]:
                        st.markdown(f"**Passage:** `{p['id']}`")
                        st.caption(p["text"])

            if msg.get("latency_ms"):
                lat = msg["latency_ms"]
                st.caption(
                    f"⏱️ Retrieval: {lat.get('retrieval', 0.0)}ms | Provider: {lat.get('provider', 0.0)}ms | Total: {lat.get('total', 0.0)}ms"
                )

    # Check for pending prompt from starter button
    user_query = None
    if "pending_prompt" in st.session_state and st.session_state.pending_prompt:
        user_query = st.session_state.pending_prompt
        del st.session_state.pending_prompt
    else:
        user_query = st.chat_input(
            "Ask about UPI safety, suspicious SMS, loan apps, or government schemes…",
            max_chars=1000,
            disabled=st.session_state.is_processing,
        )

    # Process query
    if user_query and user_query.strip():
        clean_query = user_query.strip()
        query_sig = f"{clean_query}:{len(st.session_state.messages)}"
        if st.session_state.get("last_processed_query_sig") != query_sig:
            st.session_state.last_processed_query_sig = query_sig
            st.session_state.is_processing = True
            try:
                st.session_state.messages.append({
                    "role": "user",
                    "content": clean_query,
                })

                lang_pref_map = {
                    "Auto-detect": "auto",
                    "English": "en",
                    "हिन्दी (Hindi)": "hi",
                    "मराठी (Marathi)": "mr",
                    "Hinglish": "hinglish",
                }
                manual_lang = lang_pref_map.get(st.session_state.language_preference, "auto")
                if manual_lang != "auto":
                    target_lang = manual_lang
                    st.session_state.conversation_language = manual_lang
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
                    with st.spinner("Analyzing with RBI/NPCI knowledge base & IBM Granite..."):
                        response = orchestrator.answer(clean_query, target_lang=target_lang)

                    render_source_badge(response.source, response.model_id)
                    render_fraud_alerts(response.fraud_alerts)
                    st.markdown(response.answer)

                    passage_data = [{"id": p.id, "text": p.text[:400]} for p in response.passages]
                    if passage_data:
                        with st.expander("📚 Knowledge Base Citations", expanded=False):
                            for p in passage_data:
                                st.markdown(f"**Passage:** `{p['id']}`")
                                st.caption(p["text"])

                    if response.latency_ms:
                        st.caption(
                            f"⏱️ Retrieval: {response.latency_ms.get('retrieval', 0.0)}ms | "
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
# SCREEN 3 / TAB 2: Loan Cost Calculator
# ---------------------------------------------------------------------------

with tab_calc:
    st.markdown(
        """
        <div style="margin-bottom: 0.8rem;">
            <h2 style="margin:0; font-size:1.35rem; font-weight:700;">Simplified Loan Cost & APR Calculator</h2>
            <p style="color:#64748B; font-size:0.9rem; margin:0.2rem 0 0.8rem 0;">
                Compute the annualized borrowing cost of short-term lending offers to detect predatory terms.
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
                "Loan Amount Disbursed (Principal ₹)",
                min_value=1.0,
                max_value=100000000.0,
                value=10000.0,
                step=500.0,
                help="The exact amount of cash disbursed to you.",
            )
            repayment = st.number_input(
                "Total Amount to Repay (₹)",
                min_value=1.0,
                max_value=100000000.0,
                value=12500.0,
                step=500.0,
                help="Total amount due, including processing fees, charges, and interest.",
            )
            tenure_days = st.number_input(
                "Loan Tenure (Days)",
                min_value=1,
                max_value=36500,
                value=15,
                step=1,
                help="Number of days until the full amount must be repaid.",
            )

            calc_submitted = st.form_submit_button("Calculate Annualized Cost", use_container_width=True)

    with col_out:
        calc_result = calculate_annualized_cost(
            principal=principal,
            total_repayment=repayment,
            tenure_days=int(tenure_days),
        )

        if not calc_result["valid"]:
            for err in calc_result["errors"]:
                st.error(f"⚠️ {err}")
        else:
            annual_cost = calc_result["annualized_cost_pct"]
            is_predatory = calc_result["is_predatory"]
            net_borrowing_cost = repayment - principal

            st.markdown("### Calculation Summary")
            m_c1, m_c2 = st.columns(2)
            with m_c1:
                st.metric(
                    label="Estimated Annualized Cost (APR)",
                    value=f"{annual_cost:,.2f}%",
                    delta=f"+{annual_cost - 36.0:.1f}% vs 36% indicator benchmark" if annual_cost > 36.0 else "Within commercial lending benchmarks",
                    delta_color="inverse" if annual_cost > 36.0 else "normal",
                )
            with m_c2:
                st.metric(
                    label="Total Borrowing Cost",
                    value=f"₹{net_borrowing_cost:,.2f}",
                    delta=f"{(net_borrowing_cost/principal)*100:.1f}% total fee",
                    delta_color="off",
                )

            if is_predatory:
                st.markdown(
                    f"""
                    <div class="as-fraud-box" style="margin-top:0.8rem;">
                        <strong>⚠️ WARNING: Potential Predatory Lending Term ({annual_cost:.1f}% Annualized)</strong>
                        <p style="margin:0.3rem 0 0 0; font-size:0.85rem; line-height:1.4;">
                            Under RBI Fair Practices Code principles, annual borrowing costs exceeding <strong>36%</strong>
                            frequently indicate predatory short-tenure lending. Many unauthorized digital lending apps disburse 7-day
                            loans with massive hidden fees.
                        </p>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                st.warning(
                    "Before accepting this loan, verify whether the lending entity is registered on the official RBI Sachet Portal: "
                    "[sachet.rbi.org.in](https://sachet.rbi.org.in)."
                )
            else:
                st.success(
                    f"✅ The annualized borrowing cost ({annual_cost:.1f}%) is within standard commercial lending benchmarks (≤ 36%)."
                )

            st.markdown(
                """
                <div style="font-size:0.8rem; color:#64748B; margin-top:1rem; border-top:1px solid #E2E8F0; padding-top:0.6rem;">
                    <strong>Calculation formula:</strong> <code>((Repayment − Principal) / Principal) × (365 / Days) × 100</code><br>
                    <em>Disclaimer: This calculation provides an annualized estimate and does not replace the legally defined APR required in loan sanction letters under the RBI Fair Practices Code (DOR.STR.REC.68/21.04.048/2023-24). Always demand a Key Fact Statement (KFS) before borrowing.</em>
                </div>
                """,
                unsafe_allow_html=True,
            )


# ---------------------------------------------------------------------------
# SCREEN 4 / TAB 3: 1930 Emergency Guide
# ---------------------------------------------------------------------------

with tab_emergency:
    st.markdown(
        """
        <div style="margin-bottom: 0.8rem;">
            <h2 style="margin:0; font-size:1.35rem; font-weight:700;">Immediate Financial Fraud Escalation Protocol</h2>
            <p style="color:#64748B; font-size:0.9rem; margin:0.2rem 0 0.8rem 0;">
                If you have been scammed or noticed unauthorized transactions, take these steps immediately. The golden hour is critical.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    steps = [
        ("Step 1 — Call 1930 Immediately (National Cybercrime Helpline)",
         "The **National Cybercrime Helpline (1930)** operates 24×7. Calling immediately triggers the Citizen Financial Cyber Fraud Reporting & Management System (CFCFRMS), coordinating freeze protocols across 400+ connected banks before funds are withdrawn."),
        ("Step 2 — File a Complaint Online at cybercrime.gov.in",
         "Visit the official [National Cyber Crime Reporting Portal](https://cybercrime.gov.in). Submit transaction IDs, SMS alerts, UPI reference numbers (UTR), and screenshots as evidence."),
        ("Step 3 — Block Your Cards and UPI Accounts Immediately",
         "Use your mobile banking app, net banking, or call your bank's toll-free emergency number to disable your UPI ID and block your debit/credit cards."),
        ("Step 4 — Notify Your Bank in Writing Within 3 Working Days",
         "Under the RBI Zero-Liability Circular (DBR.No.Leg.BC.78/09.07.005/2017-18), notifying your bank within 3 working days of an unauthorized transaction protects your entitlement to reimbursement. Note: outcomes depend on individual bank policies and specific circumstances; obtain a formal written acknowledgement."),
        ("Step 5 — Preserve All Digital & Transaction Evidence",
         "Do not delete fraudulent SMS alerts, call recordings, WhatsApp messages, or payment receipts. Law enforcement and cybercrime units require these records for formal investigation."),
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
            "National Cybercrime Helpline",
            "National Cybercrime Portal",
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
            "Emergency fund freeze on 400+ banks",
            "Official police FIR & cyber complaint",
            "Bank grievance escalation (if unresolved > 30 days)",
            "Guidance on banking consumer rights",
            "UPI transaction dispute redressal",
            "Check if lending apps have legal RBI licenses",
        ],
    }
    st.table(contact_data)

    st.caption(
        "Disclaimer: ArthSaathi AI provides educational guidance based on official RBI, NPCI, and Ministry of Home Affairs rules. "
        "It does not constitute formal legal counsel. For ongoing criminal investigations, always coordinate directly with local law enforcement."
    )
