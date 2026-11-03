"""
ui package — ArthSaathi AI UI Foundation.

Provides modern financial-safety and digital-public-service styling,
accessible components, responsive layout definitions, and theme management.
"""

from ui.components import (
    render_action_cards,
    render_emergency_banner,
    render_fraud_alerts,
    render_header,
    render_official_portals,
    render_sidebar_diagnostics,
    render_source_badge,
)
from ui.navigation import TAB_TITLES
from ui.styles import get_custom_css, inject_ui_styles
from ui.theme import ColorPalette, ThemeMode

__all__ = [
    "ColorPalette",
    "ThemeMode",
    "get_custom_css",
    "inject_ui_styles",
    "render_action_cards",
    "render_emergency_banner",
    "render_fraud_alerts",
    "render_header",
    "render_official_portals",
    "render_sidebar_diagnostics",
    "render_source_badge",
    "TAB_TITLES",
]
