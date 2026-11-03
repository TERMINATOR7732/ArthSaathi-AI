"""
ui/styles.py — CSS injection and responsive styling system for ArthSaathi AI.

Applies a light-first, institutional design without modifying the protected
static/css/styles.css file. Uses clean component classes, accessibility focus rings,
tabular numerals for financial calculations, and mobile-responsive layouts.
"""

from __future__ import annotations

import streamlit as st
from ui.theme import ColorPalette, ThemeMode, get_palette


def get_custom_css(theme: str | ThemeMode = ThemeMode.LIGHT) -> str:
    """Generate scoped CSS string using theme tokens."""
    c = get_palette(theme)

    return f"""
    <style>
    /* ==========================================================================
       ArthSaathi AI — Core Design System & Typography
       ========================================================================== */
    html, body, [class*="css"] {{
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
        color: {c.text_primary};
    }}

    /* Tabular figures for financial calculations and currency */
    .tabular-nums, .stNumberInput input, .metric-value {{
        font-variant-numeric: tabular-nums;
        font-feature-settings: "tnum";
    }}

    /* Global focus-visible indicator for accessibility */
    *:focus-visible {{
        outline: 2px solid {c.focus_ring} !important;
        outline-offset: 2px !important;
    }}

    /* App Brand Header */
    .as-header-card {{
        background-color: {c.bg_card};
        border: 1px solid {c.border};
        border-radius: 8px;
        padding: 1.25rem 1.5rem;
        margin-bottom: 1.25rem;
        box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04);
    }}
    .as-badge-pill {{
        display: inline-block;
        font-size: 0.72rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        color: {c.primary_blue};
        background-color: {c.primary_blue_light};
        padding: 0.2rem 0.6rem;
        border-radius: 4px;
        margin-bottom: 0.4rem;
    }}
    .as-title {{
        font-size: 1.65rem;
        font-weight: 800;
        letter-spacing: -0.025em;
        color: {c.navy if c.text_primary != "#F8FAFC" else c.text_primary};
        margin: 0;
        line-height: 1.2;
    }}
    .as-tagline {{
        font-size: 1rem;
        font-weight: 600;
        color: {c.primary_blue};
        margin: 0.25rem 0 0.4rem 0;
    }}
    .as-support-text {{
        font-size: 0.92rem;
        color: {c.text_secondary};
        line-height: 1.45;
        margin: 0 0 0.5rem 0;
    }}
    .as-disclaimer {{
        font-size: 0.78rem;
        color: {c.text_secondary};
        border-top: 1px solid {c.border};
        padding-top: 0.5rem;
        margin-top: 0.5rem;
        line-height: 1.35;
    }}

    /* 1930 Emergency Assistance Banner */
    .as-emergency-banner {{
        background-color: {c.emergency_red_bg};
        border: 1px solid {c.emergency_red_border};
        border-left: 6px solid {c.emergency_red};
        border-radius: 6px;
        padding: 1rem 1.25rem;
        margin-bottom: 1.25rem;
    }}
    .as-emergency-title {{
        color: {c.emergency_red};
        font-size: 0.95rem;
        font-weight: 800;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        display: flex;
        align-items: center;
        gap: 0.4rem;
        margin-bottom: 0.3rem;
    }}
    .as-emergency-call-btn {{
        display: inline-flex;
        align-items: center;
        background-color: {c.emergency_red};
        color: #FFFFFF !important;
        font-weight: 700;
        font-size: 1.05rem;
        padding: 0.45rem 1.15rem;
        border-radius: 4px;
        text-decoration: none !important;
        margin: 0.35rem 0;
        transition: background-color 0.15s ease-in-out;
    }}
    .as-emergency-call-btn:hover {{
        background-color: {c.emergency_red_hover};
    }}
    .as-emergency-text {{
        font-size: 0.85rem;
        color: {c.text_primary};
        margin: 0.2rem 0;
        line-height: 1.4;
    }}

    /* Icon styling */
    .as-icon {{
        display: inline-block;
        vertical-align: -0.15em;
        flex-shrink: 0;
    }}

    /* Trust / Reference Informational Cards */
    .as-trust-row {{
        display: grid;
        grid-template-columns: repeat(3, 1fr);
        gap: 0.75rem;
        margin-bottom: 1.25rem;
    }}
    .as-trust-card {{
        background-color: {c.bg_card};
        border: 1px solid {c.border};
        border-radius: 6px;
        padding: 0.75rem 0.9rem;
        box-shadow: 0 1px 2px rgba(15, 23, 42, 0.02);
    }}
    .as-trust-title {{
        font-size: 0.82rem;
        font-weight: 700;
        color: {c.text_primary};
        margin-bottom: 0.2rem;
        display: flex;
        align-items: center;
        gap: 0.35rem;
    }}
    .as-trust-desc {{
        font-size: 0.76rem;
        color: {c.text_secondary};
        line-height: 1.35;
    }}

    /* Action Entry Cards */
    .as-action-card {{
        background-color: {c.bg_card};
        border: 1px solid {c.border};
        border-radius: 6px;
        padding: 1rem 1.15rem;
        height: 100%;
        box-shadow: 0 1px 2px rgba(15, 23, 42, 0.03);
        display: flex;
        flex-direction: column;
        justify-content: space-between;
    }}
    .as-action-title {{
        font-size: 0.95rem;
        font-weight: 700;
        color: {c.text_primary};
        margin-bottom: 0.25rem;
        display: flex;
        align-items: center;
        gap: 0.4rem;
    }}
    .as-action-desc {{
        font-size: 0.82rem;
        color: {c.text_secondary};
        line-height: 1.4;
        margin-bottom: 0.75rem;
    }}

    /* Provenance & Source Badges */
    .as-source-badge {{
        display: inline-block;
        font-size: 0.72rem;
        font-weight: 700;
        padding: 0.15rem 0.55rem;
        border-radius: 4px;
        margin-bottom: 0.45rem;
        letter-spacing: 0.02em;
    }}
    .as-badge-granite {{
        background-color: {c.primary_blue_light};
        color: {c.primary_blue};
        border: 1px solid {c.border_strong if c.text_primary == "#F8FAFC" else "#C9DEFF"};
    }}
    .as-badge-offline {{
        background-color: {c.bg_subtle};
        color: {c.text_secondary};
        border: 1px solid {c.border};
    }}
    .as-badge-warning {{
        background-color: {c.warning_amber_bg};
        color: {c.warning_amber};
        border: 1px solid {c.warning_amber_border};
    }}

    /* Fraud Alert Box */
    .as-fraud-box {{
        background-color: {c.emergency_red_bg};
        border: 1px solid {c.emergency_red_border};
        border-left: 4px solid {c.emergency_red};
        color: {c.emergency_red};
        padding: 0.75rem 1rem;
        border-radius: 6px;
        margin-bottom: 0.65rem;
        font-size: 0.88rem;
        font-weight: 500;
        line-height: 1.4;
    }}

    /* Financial Stat Metric Card */
    .as-metric-card {{
        background-color: {c.bg_card};
        border: 1px solid {c.border};
        border-radius: 6px;
        padding: 0.9rem 1rem;
        text-align: center;
        box-shadow: 0 1px 2px rgba(0, 0, 0, 0.03);
    }}
    .as-metric-label {{
        font-size: 0.75rem;
        font-weight: 600;
        text-transform: uppercase;
        color: {c.text_secondary};
        letter-spacing: 0.04em;
        margin-bottom: 0.2rem;
    }}
    .as-metric-val {{
        font-size: 1.35rem;
        font-weight: 800;
        color: {c.text_primary};
        font-variant-numeric: tabular-nums;
    }}

    /* Step sequence container for 1930 Emergency */
    .as-step-item {{
        background-color: {c.bg_card};
        border: 1px solid {c.border};
        border-left: 4px solid {c.primary_blue};
        border-radius: 6px;
        padding: 0.85rem 1.15rem;
        margin-bottom: 0.75rem;
    }}
    .as-step-header {{
        font-size: 0.92rem;
        font-weight: 700;
        color: {c.text_primary};
        margin-bottom: 0.2rem;
    }}
    .as-step-body {{
        font-size: 0.85rem;
        color: {c.text_secondary};
        line-height: 1.4;
    }}

    /* Responsive Mobile Breakpoints */
    @media (max-width: 768px) {{
        .as-header-card {{
            padding: 1rem 1.15rem;
        }}
        .as-title {{
            font-size: 1.35rem;
        }}
        .as-emergency-call-btn {{
            width: 100%;
            justify-content: center;
            font-size: 1rem;
        }}
        .as-trust-row {{
            grid-template-columns: 1fr;
        }}
        .as-action-card {{
            margin-bottom: 0.6rem;
        }}
    }}
    </style>
    """


def inject_ui_styles(theme: str | ThemeMode = ThemeMode.LIGHT) -> None:
    """Inject custom scoped CSS into Streamlit document."""
    st.markdown(get_custom_css(theme), unsafe_allow_html=True)
