"""
streamlit_app.py — ArthSaathi AI Streamlit Application.

Digital Financial Literacy and UPI Fraud Awareness for Indian citizens.
IBM SkillsBuild AICTE Internship 2026 · Problem Statement No. 7.

Components:
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

# ---------------------------------------------------------------------------
# Styling and Theme Injection
# ---------------------------------------------------------------------------

def apply_custom_styles(theme: str) -> None:
    """Inject editorial finance styles adapted for Light or Dark theme."""
    if theme == "Dark":
        bg_card = "#161E2E"
        bg_card_alt = "#1F2937"
        text_primary = "#F3F4F6"
        text_secondary = "#9CA3AF"
        border_color = "#374151"
        banner_bg = "#1E293B"
        badge_bg = "#2A374A"
    else:  # Light
        bg_card = "#FFFFFF"
        bg_card_alt = "#F8FAFC"
        text_primary = "#0F172A"
        text_secondary = "#475569"
        border_color = "#E2E8F0"
        banner_bg = "#F1F5F9"
        badge_bg = "#E2E8F0"

    custom_css = f"""
    <style>
    /* Editorial header & card styling */
    .app-brand-title {{
        font-size: 1.65rem;
        font-weight: 700;
        letter-spacing: -0.02em;
        margin: 0;
        padding-bottom: 0.15rem;
    }}
    .app-brand-subtitle {{
        font-size: 0.9rem;
        color: {text_secondary};
        margin: 0;
        padding-bottom: 0.8rem;
    }}
    .editorial-card {{
        background-color: {bg_card};
        border: 1px solid {border_color};
        border-radius: 8px;
        padding: 1.15rem 1.25rem;
        margin-bottom: 1rem;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
    }}
    .emergency-card-critical {{
        background-color: {banner_bg};
        border-left: 5px solid #DC2626;
        border-radius: 6px;
        padding: 1rem 1.25rem;
        margin-bottom: 1.2rem;
    }}
    .status-pill {{
        display: inline-block;
        font-size: 0.75rem;
        font-weight: 600;
        padding: 0.2rem 0.55rem;
        border-radius: 9999px;
        text-transform: uppercase;
        letter-spacing: 0.04em;
    }}
    .status-live {{
        background-color: #DCFCE7;
        color: #166534;
        border: 1px solid #86EFAC;
    }}
    .status-offline {{
        background-color: #FEF3C7;
        color: #92400E;
        border: 1px solid #FCD34D;
    }}
    .fraud-alert-box {{
        background-color: #FEF2F2;
        border: 1px solid #FCA5A5;
        border-left: 4px solid #DC2626;
        color: #991B1B;
        padding: 0.75rem 1rem;
        border-radius: 6px;
        margin-bottom: 0.6rem;
        font-size: 0.9rem;
    }}
    .source-badge {{
        font-size: 0.75rem;
        font-weight: 600;
        padding: 0.15rem 0.5rem;
        border-radius: 4px;
        background-color: {badge_bg};
        color: {text_primary};
        display: inline-block;
        margin-bottom: 0.4rem;
    }}
    .call-btn-link {{
        display: inline-block;
        background-color: #DC2626;
        color: white !important;
        font-weight: 700;
        font-size: 1.1rem;
        padding: 0.5rem 1.2rem;
        border-radius: 6px;
        text-decoration: none;
        margin: 0.4rem 0;
    }}
    .call-btn-link:hover {{
        background-color: #B91C1C;
        text-decoration: none;
    }}
    </style>
    """
    st.markdown(custom_css, unsafe_allow_html=True)

apply_custom_styles(st.session_state.theme_mode)

# ---------------------------------------------------------------------------
# Sidebar: System Diagnostics, Controls & Safe Links
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown(
        """
        <div style="display:flex; align-items:center; gap:0.6rem; margin-bottom:0.4rem;">
            <div style="font-size:1.8rem; font-weight:800; color:#1B365D; line-height:1;">₹</div>
            <div>
                <h2 class="app-brand-title">ArthSaathi AI</h2>
                <div class="app-brand-subtitle">Financial Literacy & Fraud Shield</div>
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
    _llm_init_error = orchestrator.llm_init_error  # exception class name only; never contains secrets

    if _llm_configured and _llm_ready:
        # Credentials present and SDK initialized successfully.
        st.markdown(
            '<span class="status-pill status-live">● IBM Granite Live</span>',
            unsafe_allow_html=True,
        )
        st.caption("Model: `ibm/granite-4-h-small` | 24×7 Active")
    elif _llm_configured and not _llm_ready:
        # Credentials were present but SDK initialization failed.
        st.markdown(
            '<span class="status-pill status-offline">⚠ Init Failed — Offline Fallback</span>',
            unsafe_allow_html=True,
        )
        if _llm_init_error:
            # _llm_init_error holds only the exception class name (e.g. "ImportError"),
            # never raw exception text, auth headers, or tokens.
            st.caption(f"SDK init error: `{_llm_init_error}`. Check Streamlit logs for details.")
        else:
            st.caption("SDK initialization did not complete. Check Streamlit logs.")
    else:
        # Credentials not configured at all.
        st.markdown(
            '<span class="status-pill status-offline">○ Offline Knowledge Base</span>',
            unsafe_allow_html=True,
        )
        st.caption("Operating in offline RAG mode with curated RBI/NPCI guidelines.")

    kb_count = len(orchestrator.rag.passages)
    st.caption(f"Knowledge Base: **{kb_count} passages** loaded and indexed.")

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
    current_lang_idx = lang_options.index(st.session_state.language_preference) if st.session_state.language_preference in lang_options else 0
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

    # 24x7 Emergency Contact Box
    st.markdown(
        """
        <div class="emergency-card-critical">
            <strong style="color:#DC2626; font-size:0.85rem; text-transform:uppercase; letter-spacing:0.05em;">🚨 24×7 Cybercrime Helpline</strong>
            <div style="margin: 0.4rem 0;">
                <a href="tel:1930" class="call-btn-link">📞 Call 1930</a>
            </div>
            <p style="font-size:0.82rem; margin:0; line-height:1.4;">
                Triggers automated fund freezing across 400+ banks via CFCFRMS.
            </p>
            <div style="font-size:0.82rem; margin-top:0.4rem;">
                RBI Ombudsman: <a href="tel:14448"><strong>14448</strong></a> (Toll-free)
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Official verification portals
    with st.expander("Official Verification Portals", expanded=False):
        st.markdown(
            """
            - [cybercrime.gov.in](https://cybercrime.gov.in) — National Cybercrime Reporting Portal
            - [sachet.rbi.org.in](https://sachet.rbi.org.in) — Verify RBI-registered lenders
            - [cms.rbi.org.in](https://cms.rbi.org.in) — RBI Ombudsman complaint filing
            - [npci.org.in](https://www.npci.org.in) — Official NPCI UPI guidelines
            """
        )

    # Chat reset button
    if st.button("🗑️ Reset Chat Conversation", use_container_width=True):
        st.session_state.messages = []
        st.session_state.conversation_language = "en"
        st.rerun()


# ---------------------------------------------------------------------------
# Navigation Tabs
# ---------------------------------------------------------------------------

tab_chat, tab_calc, tab_emergency = st.tabs([
    "💬 AI Scam Advisor",
    "📊 Loan Cost Calculator",
    "🚨 1930 Emergency Guide",
])

# ---------------------------------------------------------------------------
# TAB 1: AI Scam Advisor
# ---------------------------------------------------------------------------

with tab_chat:
    st.markdown(
        """
        <div style="margin-bottom: 0.8rem;">
            <h2 style="margin:0; font-size:1.4rem; font-weight:700;">Digital Financial Literacy & Scam Advisor</h2>
            <p style="color:#64748B; font-size:0.92rem; margin:0.2rem 0 0.8rem 0;">
                Grounded in official RBI and NPCI guidelines. Check suspicious UPI payments, verify loan offers, or learn your rights.
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

    # Display Chat History
    if not st.session_state.messages:
        # Seed message
        st.markdown(
            """
            <div class="editorial-card">
                <strong>Namaste! I am ArthSaathi, your digital financial safety assistant.</strong><br>
                Ask me about UPI safety rules, suspicious payment requests, loan apps, or banking consumer rights.
                <em>You can communicate in English, Hindi (हिन्दी), Marathi (मराठी), or Hinglish.</em>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown("**Suggested questions to get started:**")
        col1, col2 = st.columns(2)
        starters = [
            ("How can I identify a UPI payment scam?", "Recognize fake collect requests and phishing."),
            ("Can someone send me money by asking me to scan a QR code?", "The #1 marketplace scam explained."),
            ("Is this loan offer suspicious?", "Identify predatory interest rates and fake NBFCs."),
            ("How do I report a financial cybercrime?", "Step-by-step CFCFRMS protocol and 1930 helpline."),
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
            # Display source tag if assistant
            if msg["role"] == "assistant" and "source" in msg:
                src = msg["source"]
                if src == "granite":
                    st.markdown('<span class="source-badge">Live IBM Granite</span>', unsafe_allow_html=True)
                elif src == "offline_kb":
                    st.markdown('<span class="source-badge">Offline Knowledge Base</span>', unsafe_allow_html=True)
                elif src == "not_configured":
                    st.markdown('<span class="source-badge">Offline Knowledge Base (Credentials not set)</span>', unsafe_allow_html=True)
                else:
                    st.markdown(f'<span class="source-badge">{html.escape(src)}</span>', unsafe_allow_html=True)

            # Display any fraud alerts
            if msg.get("fraud_alerts"):
                for alert in msg["fraud_alerts"]:
                    st.markdown(f'<div class="fraud-alert-box">{html.escape(alert)}</div>', unsafe_allow_html=True)

            # Display answer content
            st.markdown(msg["content"])

            # Collapsible passages
            if msg.get("passages"):
                with st.expander("📚 Knowledge Base Citations", expanded=False):
                    for p in msg["passages"]:
                        st.markdown(f"**Passage:** `{p['id']}`")
                        st.caption(p["text"])

            # Latency footer
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
        st.session_state.is_processing = True

        # Append user message
        st.session_state.messages.append({
            "role": "user",
            "content": clean_query,
        })

        # Resolve language target from selector or conversational context
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
            # If short greeting or short 1-2 word query without clear script shift, preserve conversation language
            if len(words) <= 2 and greeting_flag and st.session_state.conversation_language != "en":
                target_lang = st.session_state.conversation_language
            else:
                target_lang = detected
                st.session_state.conversation_language = detected

        # Generate response
        with st.chat_message("assistant"):
            with st.spinner("Analyzing with RBI/NPCI knowledge base & IBM Granite..."):
                response = orchestrator.answer(clean_query, target_lang=target_lang)

            # Source badge
            if response.source == "granite":
                st.markdown('<span class="source-badge">Live IBM Granite</span>', unsafe_allow_html=True)
            else:
                st.markdown('<span class="source-badge">Offline Knowledge Base</span>', unsafe_allow_html=True)

            # Fraud alerts
            if response.fraud_alerts:
                for alert in response.fraud_alerts:
                    st.markdown(f'<div class="fraud-alert-box">{html.escape(alert)}</div>', unsafe_allow_html=True)

            # Answer
            st.markdown(response.answer)

            # Citations
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

        # Store in history
        st.session_state.messages.append({
            "role": "assistant",
            "content": response.answer,
            "source": response.source,
            "fraud_alerts": response.fraud_alerts,
            "emergency": response.emergency,
            "passages": passage_data,
            "latency_ms": response.latency_ms,
        })

        st.session_state.is_processing = False
        st.rerun()


# ---------------------------------------------------------------------------
# TAB 2: Loan Cost Calculator
# ---------------------------------------------------------------------------

with tab_calc:
    st.markdown(
        """
        <div style="margin-bottom: 0.8rem;">
            <h2 style="margin:0; font-size:1.4rem; font-weight:700;">Simplified Loan Cost Calculator</h2>
            <p style="color:#64748B; font-size:0.92rem; margin:0.2rem 0 0.8rem 0;">
                Compute the annualized cost rate of short-term lending offers to detect predatory terms.
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
                "Loan Amount (Principal ₹)",
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

            st.markdown("### Calculation Result")
            st.metric(
                label="Annualized Borrowing Cost (Estimate)",
                value=f"{annual_cost:,.2f}%",
                delta=f"+{annual_cost - 36.0:.1f}% vs 36% limit" if annual_cost > 36.0 else "Within standard range",
                delta_color="inverse" if annual_cost > 36.0 else "normal",
            )

            if is_predatory:
                st.markdown(
                    f"""
                    <div style="background-color:#FEF2F2; border-left:4px solid #DC2626; padding:0.9rem 1.1rem; border-radius:6px; margin:0.8rem 0;">
                        <strong style="color:#991B1B;">⚠️ WARNING: Potential Predatory Lending Rate ({annual_cost:.1f}%)</strong>
                        <p style="color:#7F1D1D; font-size:0.88rem; margin:0.4rem 0 0 0;">
                            The Reserve Bank of India considers annual rates exceeding <strong>36%</strong> an indicator of exploitative and predatory lending for regulated NBFCs.
                        </p>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                st.warning(
                    "Before accepting this loan, verify whether the lending app and NBFC partner are registered on the official RBI Sachet Portal: "
                    "[sachet.rbi.org.in](https://sachet.rbi.org.in)."
                )
            else:
                st.success(
                    f"✅ The annualized cost rate ({annual_cost:.1f}%) is within standard commercial lending benchmarks (<= 36%)."
                )

            st.markdown(
                """
                <div style="font-size:0.82rem; color:#64748B; margin-top:1rem; border-top:1px solid #E2E8F0; padding-top:0.6rem;">
                    <strong>Calculation formula:</strong> <code>((Repayment − Principal) / Principal) × (365 / Days) × 100</code><br>
                    <em>Disclaimer: This calculation provides a simplified annualized estimate and does not replace the legally defined APR required in loan sanction letters under the RBI Fair Practices Code (DOR.STR.REC.68/21.04.048/2023-24). Always request a Key Fact Statement (KFS) before borrowing.</em>
                </div>
                """,
                unsafe_allow_html=True,
            )


# ---------------------------------------------------------------------------
# TAB 3: 1930 Emergency Guide
# ---------------------------------------------------------------------------

with tab_emergency:
    st.markdown(
        """
        <div style="margin-bottom: 0.8rem;">
            <h2 style="margin:0; font-size:1.4rem; font-weight:700;">Immediate Financial Fraud Escalation Protocol</h2>
            <p style="color:#64748B; font-size:0.92rem; margin:0.2rem 0 0.8rem 0;">
                If you have been scammed or noticed unauthorized transactions, take these steps immediately. The first hour is critical.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    steps = [
        ("Step 1 — Call 1930 immediately",
         "The **National Cybercrime Helpline (1930)** operates 24×7. Calling immediately triggers an automated fund-freeze across 400+ participating banks via the Citizen Financial Cyber Fraud Reporting and Management System (CFCFRMS).",
         True),
        ("Step 2 — File a complaint online at cybercrime.gov.in",
         "Visit the official [National Cybercrime Reporting Portal](https://cybercrime.gov.in). Submit transaction IDs, SMS alerts, UPI reference numbers, and screenshots as evidence.",
         False),
        ("Step 3 — Block your card and UPI services immediately",
         "Use your mobile banking app, net banking, or call your bank's toll-free emergency number to disable your UPI ID and block your debit/credit cards.",
         False),
        ("Step 4 — Notify your bank branch in writing within 3 working days",
         "Under RBI's Zero-Liability Circular (DBR.No.Leg.BC.78/09.07.005/2017-18), notifying your bank within 3 working days protects you from bearing financial liability for third-party breaches.",
         False),
        ("Step 5 — Preserve all digital evidence",
         "Do not delete fraudulent SMS, call recordings, WhatsApp messages, or transaction receipts. Law enforcement requires these records for criminal investigation.",
         False),
    ]

    for title, desc, is_crit in steps:
        border_col = "#DC2626" if is_crit else "#CBD5E1"
        bg_col = "#FEF2F2" if is_crit else "#F8FAFC"
        st.markdown(
            f"""
            <div style="background-color:{bg_col}; border-left:4px solid {border_col}; border-radius:6px; padding:0.9rem 1.1rem; margin-bottom:0.75rem;">
                <h4 style="margin:0 0 0.3rem 0; font-size:1.02rem; font-weight:700;">{title}</h4>
                <p style="margin:0; font-size:0.9rem; line-height:1.45;">{desc}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("### Official Directory")
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
