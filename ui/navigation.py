"""
ui/navigation.py — Navigation tabs and active view management.

Defines the primary functional sections of the ArthSaathi AI platform:
- AI Scam Advisor (Chat & RAG Q&A)
- Loan Cost Calculator (Objective APR & loan charge evaluation)
- 1930 Emergency Guide (Immediate 5-step response protocol)
"""

from __future__ import annotations

# Clean titles without structural emoji
TAB_SCAM_ADVISOR = "AI Scam Advisor"
TAB_LOAN_CALCULATOR = "Loan Cost Calculator"
TAB_EMERGENCY_GUIDE = "1930 Emergency Guide"

TAB_TITLES = [
    TAB_SCAM_ADVISOR,
    TAB_LOAN_CALCULATOR,
    TAB_EMERGENCY_GUIDE,
]

VIEW_SCAM_ADVISOR = "scam_advisor"
VIEW_LOAN_CALCULATOR = "loan_calculator"
VIEW_EMERGENCY_GUIDE = "emergency_guide"

VIEW_MAP = {
    VIEW_SCAM_ADVISOR: TAB_SCAM_ADVISOR,
    VIEW_LOAN_CALCULATOR: TAB_LOAN_CALCULATOR,
    VIEW_EMERGENCY_GUIDE: TAB_EMERGENCY_GUIDE,
}

REVERSE_VIEW_MAP = {v: k for k, v in VIEW_MAP.items()}
