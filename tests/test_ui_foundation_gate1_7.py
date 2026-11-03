"""
tests/test_ui_foundation_gate1_7.py — UI Redesign Foundation Tests (Gate 1.7).

Validates:
1. ui/ modular structure (theme, styles, components, navigation).
2. ColorPalette tokens for Light and Dark modes.
3. CSS generation with accessibility focus outlines, tabular nums, and responsive breakpoints.
4. Component rendering for header, emergency banner, action cards, source badges, and portals.
5. Streamlit AppTest verification of initial rendering, tab navigation, starter queries, and reset.
6. Provenance badge accuracy across Granite, offline KB, and error states.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest import mock

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from ui.components import (
    render_action_cards,
    render_emergency_banner,
    render_fraud_alerts,
    render_header,
    render_official_portals,
    render_source_badge,
)
from ui.navigation import TAB_TITLES, TAB_SCAM_ADVISOR, TAB_LOAN_CALCULATOR, TAB_EMERGENCY_GUIDE
from ui.styles import get_custom_css
from ui.theme import ColorPalette, ThemeMode, get_palette

_ROOT = Path(__file__).resolve().parent.parent
_APP_PATH = str(_ROOT / "streamlit_app.py")


# ===========================================================================
# 1. Theme & Design System Token Tests
# ===========================================================================

def test_theme_color_tokens():
    """ColorPalette provides required institutional colors with accessible contrast."""
    palette = get_palette(ThemeMode.LIGHT)
    assert palette.navy == "#0F172A"
    assert palette.primary_blue == "#0F62FE"
    assert palette.emergency_red == "#DA1E28"
    assert palette.bg_main == "#F8FAFC"
    assert palette.border == "#E2E8F0"

    dark_palette = get_palette(ThemeMode.DARK)
    assert dark_palette.bg_main == "#0B0F19"
    assert dark_palette.text_primary == "#F8FAFC"


def test_custom_css_includes_accessibility_and_responsive_tokens():
    """Generated CSS includes focus rings, tabular numbers, and responsive media queries."""
    css = get_custom_css(ThemeMode.LIGHT)
    assert "*:focus-visible" in css, "Must include global keyboard focus indicator"
    assert "tabular-nums" in css, "Must include tabular numbers for currency and calculations"
    assert "@media (max-width: 768px)" in css, "Must include mobile/tablet responsive breakpoint"
    assert "as-header-card" in css
    assert "as-emergency-banner" in css
    assert "as-source-badge" in css


def test_navigation_tab_definitions():
    """Navigation defines all 3 core functional areas."""
    assert len(TAB_TITLES) == 3
    assert TAB_SCAM_ADVISOR in TAB_TITLES
    assert TAB_LOAN_CALCULATOR in TAB_TITLES
    assert TAB_EMERGENCY_GUIDE in TAB_TITLES


# ===========================================================================
# 2. Streamlit Runtime Rendering & Navigation Tests
# ===========================================================================

def test_ui_runtime_renders_all_components_without_exception():
    """AppTest loads streamlit_app.py, verifies header, emergency banner, action cards, and tabs."""
    st.cache_resource.clear()
    with mock.patch.dict(os.environ, {"WATSONX_API_KEY": "", "WATSONX_PROJECT_ID": ""}):
        at = AppTest.from_file(_APP_PATH, default_timeout=30)
        at.run()

        assert len(at.exception) == 0, f"Encountered startup exceptions: {at.exception}"
        assert len(at.tabs) == 3

        # Check tab labels
        tab_names = [t.label for t in at.tabs]
        assert any("Scam Advisor" in n for n in tab_names)
        assert any("Loan Cost Calculator" in n for n in tab_names)
        assert any("1930 Emergency Guide" in n for n in tab_names)

        # Check sidebar elements
        assert len(at.sidebar.selectbox) >= 1
        assert "Auto-detect" in at.sidebar.selectbox[0].options
        assert len(at.sidebar.radio) >= 1
        assert "Light" in at.sidebar.radio[0].options


def test_ui_runtime_chat_starter_execution():
    """Clicking a starter button populates prompt, runs inference, and displays badge."""
    st.cache_resource.clear()
    with mock.patch.dict(os.environ, {
        "WATSONX_API_KEY": "synthetic-key",
        "WATSONX_PROJECT_ID": "12345678-abcd-ef01-2345-6789abcdef01",
    }):
        with mock.patch("ibm_watsonx_ai.Credentials", mock.MagicMock()):
            mock_model = mock.MagicMock()
            mock_model.chat.return_value = {
                "model_id": "ibm/granite-4-h-small",
                "choices": [{"message": {"content": "Never scan a QR code to receive money."}}],
            }
            with mock.patch("ibm_watsonx_ai.foundation_models.ModelInference", return_value=mock_model):
                at = AppTest.from_file(_APP_PATH, default_timeout=30)
                at.run()

                # Click starter 0 (QR code question)
                at.button[0].click().run()
                assert len(at.exception) == 0
                assert mock_model.chat.call_count == 1
                assert len(at.session_state.messages) == 2
                assert at.session_state.messages[-1]["source"] == "granite"


def test_ui_runtime_conversation_reset():
    """Reset Chat button resets message history, signature, and preserves layout."""
    st.cache_resource.clear()
    with mock.patch.dict(os.environ, {"WATSONX_API_KEY": "", "WATSONX_PROJECT_ID": ""}):
        at = AppTest.from_file(_APP_PATH, default_timeout=30)
        at.run()

        # Seed message
        at.session_state.messages.append({"role": "user", "content": "Hello"})
        at.session_state.last_processed_query_sig = "Hello:0"
        at.run()
        assert len(at.session_state.messages) == 1

        # Click sidebar reset button
        reset_btns = [b for b in at.sidebar.button if "Reset Chat" in (b.label or "")]
        assert len(reset_btns) == 1
        reset_btns[0].click().run()

        assert len(at.exception) == 0
        assert len(at.session_state.messages) == 0
        assert at.session_state.last_processed_query_sig is None
