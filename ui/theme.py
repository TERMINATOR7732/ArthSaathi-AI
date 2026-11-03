"""
ui/theme.py — Theme tokens, typography, and color palette definitions.

Adopts a modern financial-safety and digital-public-service design language
purpose-built for Indian citizens. Adheres to strict accessibility contrast
guidelines with a clean, light-first visual hierarchy.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ThemeMode(str, Enum):
    LIGHT = "Light"
    DARK = "Dark"


@dataclass(frozen=True)
class ColorPalette:
    """Color tokens for the ArthSaathi AI financial safety platform."""

    # Brand & Surface tokens
    navy: str = "#0F172A"
    primary_blue: str = "#0F62FE"
    primary_blue_hover: str = "#0043CE"
    primary_blue_light: str = "#EDF5FF"

    bg_main: str = "#F8FAFC"
    bg_card: str = "#FFFFFF"
    bg_subtle: str = "#F1F5F9"

    text_primary: str = "#1E293B"
    text_secondary: str = "#64748B"
    text_inverse: str = "#FFFFFF"

    border: str = "#E2E8F0"
    border_strong: str = "#CBD5E1"

    # Status & Emergency tokens
    emergency_red: str = "#DA1E28"
    emergency_red_hover: str = "#BA1B23"
    emergency_red_bg: str = "#FFF1F1"
    emergency_red_border: str = "#FFD7D9"

    success_green: str = "#198038"
    success_green_bg: str = "#DEFBE6"
    success_green_border: str = "#A7F0BA"

    warning_amber: str = "#D97706"
    warning_amber_bg: str = "#FEF3C7"
    warning_amber_border: str = "#FCD34D"

    # Focus indicator
    focus_ring: str = "#0F62FE"


# Dark theme palette overrides
DARK_PALETTE = ColorPalette(
    navy="#0F172A",
    primary_blue="#4589FF",
    primary_blue_hover="#78A9FF",
    primary_blue_light="#1E293B",
    bg_main="#0B0F19",
    bg_card="#151D2A",
    bg_subtle="#1E293B",
    text_primary="#F8FAFC",
    text_secondary="#94A3B8",
    text_inverse="#0F172A",
    border="#27354A",
    border_strong="#3E4F69",
    emergency_red="#FA4D56",
    emergency_red_hover="#FF8389",
    emergency_red_bg="#341113",
    emergency_red_border="#750E13",
    success_green="#42BE65",
    success_green_bg="#0E2D16",
    success_green_border="#198038",
    warning_amber="#F59E0B",
    warning_amber_bg="#302008",
    warning_amber_border="#8A5B0B",
    focus_ring="#4589FF",
)

LIGHT_PALETTE = ColorPalette()


def get_palette(theme: str | ThemeMode) -> ColorPalette:
    """Return the active color palette based on selected theme mode."""
    mode = ThemeMode(theme) if isinstance(theme, str) else theme
    if mode == ThemeMode.DARK:
        return DARK_PALETTE
    return LIGHT_PALETTE
