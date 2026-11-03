"""
ui/icons.py — Professional, accessible inline SVG iconography for ArthSaathi AI.

Provides standard Lucide-style SVG icons:
- shield_check (Security & Verification)
- shield_alert (Fraud Alert & Risk Warning)
- wallet (Financial Literacy & Payment)
- calculator (Loan Cost & APR Calculation)
- phone_call (1930 Emergency Helpline)
- book_open (Financial Reference Content)
- layout_dashboard (Mission Control / System Status)
- file_text (Key Fact Statement / Legal Documents)
- external_link (Official Regulatory Portals)
- circle_check (System Operational Status)
- alert_triangle (Caution & Disclaimers)
- trash (Reset Conversation History)

Eliminates structural Unicode emoji from headings, action cards, emergency banners,
and navigation controls while maintaining full accessibility with aria-hidden="true".
"""

from __future__ import annotations

import html
from typing import Optional


# SVG path definitions with 24x24 viewBox, stroke-width="2", fill="none", stroke="currentColor"
_ICON_PATHS: dict[str, str] = {
    "shield_check": (
        '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>'
        '<path d="m9 12 2 2 4-4"/>'
    ),
    "shield_alert": (
        '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>'
        '<line x1="12" y1="8" x2="12" y2="12"/>'
        '<line x1="12" y1="16" x2="12.01" y2="16"/>'
    ),
    "wallet": (
        '<path d="M19 7V4a1 1 0 0 0-1-1H5a2 2 0 0 0 0 4h15a1 1 0 0 1 1 1v4h-3a2 2 0 0 0 0 4h3a1 1 0 0 0 1-1v-2a1 1 0 0 0-1-1"/>'
        '<path d="M3 5v14a2 2 0 0 0 2 2h15a1 1 0 0 0 1-1v-4"/>'
    ),
    "calculator": (
        '<rect width="16" height="20" x="4" y="2" rx="2"/>'
        '<line x1="8" x2="16" y1="6" y2="6"/>'
        '<line x1="16" x2="16" y1="14"/>'
        '<path d="M16 10h.01"/>'
        '<path d="M12 10h.01"/>'
        '<path d="M8 10h.01"/>'
        '<path d="M12 14h.01"/>'
        '<path d="M8 14h.01"/>'
        '<path d="M12 18h.01"/>'
        '<path d="M8 18h.01"/>'
    ),
    "phone_call": (
        '<path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"/>'
        '<path d="M14.05 2a9 9 0 0 1 8 7.94"/>'
        '<path d="M14.05 6A5 5 0 0 1 18 10"/>'
    ),
    "book_open": (
        '<path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/>'
        '<path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>'
    ),
    "layout_dashboard": (
        '<rect width="7" height="9" x="3" y="3" rx="1"/>'
        '<rect width="7" height="5" x="14" y="3" rx="1"/>'
        '<rect width="7" height="9" x="14" y="12" rx="1"/>'
        '<rect width="7" height="5" x="3" y="16" rx="1"/>'
    ),
    "file_text": (
        '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/>'
        '<path d="M14 2v4a2 2 0 0 0 2 2h4"/>'
        '<path d="M10 9H8"/>'
        '<path d="M16 13H8"/>'
        '<path d="M16 17H8"/>'
    ),
    "external_link": (
        '<path d="M15 3h6v6"/>'
        '<path d="M10 14 21 3"/>'
        '<path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>'
    ),
    "circle_check": (
        '<circle cx="12" cy="12" r="10"/>'
        '<path d="m9 12 2 2 4-4"/>'
    ),
    "alert_triangle": (
        '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/>'
        '<line x1="12" y1="9" x2="12" y2="13"/>'
        '<line x1="12" y1="17" x2="12.01" y2="17"/>'
    ),
    "trash": (
        '<path d="M3 6h18"/>'
        '<path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/>'
        '<path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/>'
    ),
}


def get_svg_icon(
    name: str,
    size: int = 18,
    color: Optional[str] = None,
    extra_class: str = "",
) -> str:
    """
    Generate an inline SVG element for the given icon name.

    Parameters:
        name: Icon identifier from _ICON_PATHS.
        size: Viewport width and height in pixels (default: 18).
        color: Optional CSS stroke color (default: 'currentColor').
        extra_class: Optional additional CSS class for styling.

    Returns:
        Safe HTML string containing the rendered <svg> element.
    """
    path_content = _ICON_PATHS.get(name)
    if not path_content:
        return ""

    color_attr = f' stroke="{html.escape(color)}"' if color else ' stroke="currentColor"'
    class_attr = f' class="as-icon {html.escape(extra_class)}"' if extra_class else ' class="as-icon"'
    style_attr = ' style="vertical-align: -0.15em; display: inline-block;"'

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 24 24" fill="none"{color_attr} stroke-width="2" '
        f'stroke-linecap="round" stroke-linejoin="round"{class_attr}{style_attr} '
        f'aria-hidden="true">{path_content}</svg>'
    )
