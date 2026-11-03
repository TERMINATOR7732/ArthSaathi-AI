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
from ui.icons import get_svg_icon
from ui.navigation import (
    TAB_EMERGENCY_GUIDE,
    TAB_LOAN_CALCULATOR,
    TAB_SCAM_ADVISOR,
    TAB_TITLES,
    VIEW_EMERGENCY_GUIDE,
    VIEW_LOAN_CALCULATOR,
    VIEW_MAP,
    VIEW_SCAM_ADVISOR,
)
from ui.styles import get_custom_css, inject_ui_styles
from ui.theme import ColorPalette, ThemeMode

__all__ = [
    "ColorPalette",
    "ThemeMode",
    "get_custom_css",
    "get_svg_icon",
    "inject_ui_styles",
    "render_action_cards",
    "render_emergency_banner",
    "render_fraud_alerts",
    "render_header",
    "render_official_portals",
    "render_sidebar_diagnostics",
    "render_source_badge",
    "TAB_EMERGENCY_GUIDE",
    "TAB_LOAN_CALCULATOR",
    "TAB_SCAM_ADVISOR",
    "TAB_TITLES",
    "VIEW_EMERGENCY_GUIDE",
    "VIEW_LOAN_CALCULATOR",
    "VIEW_MAP",
    "VIEW_SCAM_ADVISOR",
]
