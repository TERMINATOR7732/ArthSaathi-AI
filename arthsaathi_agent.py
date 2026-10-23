"""
arthsaathi_agent.py — ArthSaathi AI agent orchestration logic.

Components:
  RAGRetrievalAgent     — keyword-based passage retrieval from local knowledge base.
  FraudDetectionAgent   — rule-based UPI/loan scam pattern detection.
  EmergencyProtocolAgent — escalation trigger for immediate cyber-fraud situations.
  GraniteLLMAgent       — IBM watsonx.ai Granite inference (optional; gracefully degrades).
  ArthSaathiOrchestrator — coordinates all agents and returns a structured response dict.

This module does NOT import Flask. It is independently testable.
Credentials are read from environment variables only — never hardcoded here.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Knowledge-base paths
# ---------------------------------------------------------------------------

_HERE = Path(__file__).parent
KB_DIR = _HERE / "knowledge_base"

_KB_FILES = [
    "rbi_npci_financial_literacy_kb.txt",
    "rbi_whitelist_and_cyber_stats.txt",
]


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class Passage:
    """A single retrievable passage from the knowledge base."""
    source_file: str
    index: int          # 0-based index within the source file
    text: str

    @property
    def id(self) -> str:
        stem = Path(self.source_file).stem
        return f"{stem}/{self.index}"


@dataclass
class OrchestratorResponse:
    """Structured response returned by ArthSaathiOrchestrator.answer()."""
    answer: str
    source: str                          # "granite" | "offline_kb" | "not_configured"
    fraud_alerts: list[str] = field(default_factory=list)
    emergency: bool = False
    passages: list[Passage] = field(default_factory=list)
    provider_error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "answer": self.answer,
            "source": self.source,
            "fraud_alerts": self.fraud_alerts,
            "emergency": self.emergency,
            "passages": [{"id": p.id, "text": p.text[:400]} for p in self.passages],
            "provider_error": self.provider_error,
        }


# ---------------------------------------------------------------------------
# Agent 1 — RAG Retrieval (keyword-based; explicitly NOT semantic/vector search)
# ---------------------------------------------------------------------------

class RAGRetrievalAgent:
    """
    Loads local knowledge-base files and retrieves passages by keyword overlap.

    This is a simplified keyword-frequency retrieval baseline.
    It is NOT semantic search and NOT vector-based RAG.
    Source file and passage index are returned for attribution.
    """

    def __init__(self, kb_dir: Path = KB_DIR) -> None:
        self.passages: list[Passage] = []
        for filename in _KB_FILES:
            path = kb_dir / filename
            self._load(path)

    def _load(self, path: Path) -> None:
        try:
            text = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return
        # Split on blank lines; keep only passages with meaningful length
        raw_chunks = [c.strip() for c in text.split("\n\n") if len(c.strip()) > 40]
        for i, chunk in enumerate(raw_chunks):
            self.passages.append(Passage(source_file=path.name, index=i, text=chunk))

    def retrieve(self, query: str, top_k: int = 5) -> list[Passage]:
        """Return up to top_k passages with highest keyword overlap with query."""
        query_words = set(re.findall(r"\w+", query.lower()))
        if not query_words:
            return []

        scored: list[tuple[float, Passage]] = []
        for passage in self.passages:
            passage_words = set(re.findall(r"\w+", passage.text.lower()))
            overlap = len(query_words & passage_words)
            if overlap > 0:
                score = overlap / max(len(query_words), 1)
                scored.append((score, passage))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [p for _, p in scored[:top_k]]


# ---------------------------------------------------------------------------
# Agent 2 — Fraud Detection (rule-based keyword patterns)
# ---------------------------------------------------------------------------

class FraudDetectionAgent:
    """
    Detects high-risk UPI/loan scam patterns in user queries.
    Returns a list of human-readable alert strings.
    """

    # Mapping: trigger phrase (lowercase) → alert message
    _RULES: list[tuple[str, str]] = [
        ("upi collect request",
         "⚠️ ALERT: A UPI Collect Request SENDS money out of your account. "
         "Never approve requests from unknown senders."),
        ("qr code receive",
         "⚠️ ALERT: QR codes are for PAYMENTS only. "
         "Scanning a QR code cannot receive money — this is always a scam."),
        ("share upi pin",
         "🚨 CRITICAL: NEVER share your UPI PIN with anyone — not bank staff, "
         "not NPCI, not payment app support."),
        ("upi pin",
         "⚠️ REMINDER: Your UPI PIN is strictly private. "
         "No legitimate party will ever ask for it."),
        ("anydesk",
         "🚨 CRITICAL: AnyDesk screen-sharing for banking is a remote-access fraud. "
         "Disconnect immediately and call 1930."),
        ("teamviewer",
         "🚨 CRITICAL: TeamViewer screen-sharing for banking is a remote-access fraud. "
         "Disconnect immediately and call 1930."),
        ("kyc update",
         "⚠️ ALERT: Fake KYC update SMS/WhatsApp messages are phishing scams. "
         "Visit your bank branch directly — do not click any link."),
        ("loan app",
         "⚠️ ALERT: Verify the lending app is RBI-registered before borrowing. "
         "Check: https://sachet.rbi.org.in"),
        ("lottery",
         "⚠️ ALERT: Unsolicited lottery or prize notifications are scams. "
         "No legitimate prize requires a fee or your banking details."),
        ("share otp",
         "🚨 CRITICAL: NEVER share an OTP. "
         "Banks will never ask for your OTP — sharing it gives immediate account access."),
        ("activation fee",
         "🚨 SCAM: UPI accounts have no 'activation fee'. "
         "This is a known fraud script — do not pay."),
    ]

    def analyze(self, query: str) -> list[str]:
        q = query.lower()
        return [msg for trigger, msg in self._RULES if trigger in q]


# ---------------------------------------------------------------------------
# Agent 3 — Emergency Protocol
# ---------------------------------------------------------------------------

class EmergencyProtocolAgent:
    """
    Detects emergency signals in user queries and provides the 1930 protocol.
    """

    _TRIGGERS = frozenset([
        "fraud", "scam", "hacked", "lost money", "stolen", "phishing",
        "cheated", "unauthorized", "debited", "blocked account", "help me",
        "emergency", "1930", "cybercrime", "complaint", "debit", "stolen money",
    ])

    # Static guidance — sourced from public RBI/MHA materials
    PROTOCOL = (
        "## 🚨 Immediate Fraud Response Steps\n\n"
        "**Step 1 — Call 1930 immediately.**  \n"
        "National Cybercrime Helpline, 24×7. Triggers automated fund-freeze across 400+ banks "
        "(CFCFRMS network).\n\n"
        "**Step 2 — File a complaint online.**  \n"
        "https://cybercrime.gov.in — submit transaction IDs and debit SMS screenshots.\n\n"
        "**Step 3 — Block your card/UPI.**  \n"
        "Use your bank app, IVR helpline, or the number on the back of your debit card.\n\n"
        "**Step 4 — Notify your bank within 3 working days.**  \n"
        "RBI Zero-Liability Rule (Circular DBR.No.Leg.BC.78/09.07.005/2017-18): "
        "reporting within 3 working days of an unauthorized transaction protects your "
        "entitlement to reimbursement. Note: outcomes depend on individual bank policies "
        "and the specific circumstances; consult your bank for confirmation.\n\n"
        "**RBI Ombudsman:** https://cms.rbi.org.in | Toll-free: **14448**\n\n"
        "> ⚠️ Do not delete any messages, transaction records, or screenshots — "
        "these are evidence."
    )

    def should_escalate(self, query: str) -> bool:
        q = query.lower()
        return any(t in q for t in self._TRIGGERS)


# ---------------------------------------------------------------------------
# Agent 4 — IBM Granite LLM
# ---------------------------------------------------------------------------

class GraniteLLMAgent:
    """
    Generates grounded responses via IBM watsonx.ai Granite model.

    Reads configuration from environment variables:
      WATSONX_API_KEY, WATSONX_PROJECT_ID, WATSONX_URL, WATSONX_MODEL_ID

    States:
      configured=True, _ready=True  → credentials present, SDK initialised
      configured=False               → missing credentials; returns not_configured
      configured=True, _ready=False  → credentials present but SDK init failed
    """

    _SYSTEM_PROMPT = (
        "You are ArthSaathi, a trusted AI financial literacy advisor for Indian citizens. "
        "You are grounded in RBI Master Directions, NPCI UPI guidelines, and Government "
        "of India financial inclusion schemes. "
        "Always give accurate, actionable advice based only on the provided context. "
        "Flag potential fraud clearly. Use ₹ for currency. "
        "Respond in clear English; you may include Hindi or Hinglish phrases where helpful. "
        "Never give personalized investment advice. "
        "Always direct users to official government portals for authoritative information. "
        "If the context does not contain a relevant answer, say so explicitly."
    )

    def __init__(self) -> None:
        self._client = None
        self._ready = False
        self.configured = False
        self.init_error: Optional[str] = None

        api_key = os.getenv("WATSONX_API_KEY", "").strip()
        project_id = os.getenv("WATSONX_PROJECT_ID", "").strip()
        url = os.getenv("WATSONX_URL", "https://us-south.ml.cloud.ibm.com").strip()
        model_id = os.getenv("WATSONX_MODEL_ID", "ibm/granite-4-h-small").strip()

        if not api_key or not project_id:
            return  # not configured; graceful degradation

        self.configured = True
        try:
            from ibm_watsonx_ai import Credentials
            from ibm_watsonx_ai.foundation_models import ModelInference

            creds = Credentials(url=url, api_key=api_key)
            self._client = ModelInference(
                model_id=model_id,
                credentials=creds,
                project_id=project_id,
            )
            self._ready = True
        except Exception as exc:
            self.init_error = str(exc)
            self._ready = False

    def generate(self, query: str, context: str) -> tuple[str, str]:
        """
        Returns (answer_text, source_label).
        source_label: "granite" | "not_configured" | "provider_error"
        """
        if not self.configured:
            return self._offline_answer(context), "not_configured"

        if not self._ready or self._client is None:
            err = self.init_error or "SDK initialization failed"
            return self._offline_answer(context), f"provider_error:{err}"

        messages = [
            {
                "role": "system",
                "content": (
                    f"{self._SYSTEM_PROMPT}\n\n"
                    f"### Knowledge Base Context:\n{context}"
                ),
            },
            {"role": "user", "content": query},
        ]
        try:
            result = self._client.chat(
                messages=messages,
                params={"max_tokens": 512, "temperature": 0.3},
            )
            answer = result["choices"][0]["message"]["content"].strip()
            return answer, "granite"
        except Exception as exc:
            return self._offline_answer(context), f"provider_error:{exc}"

    @staticmethod
    def _offline_answer(context: str) -> str:
        """Return best-available KB content with a clear offline notice."""
        if context.strip():
            snippet = context[:1200].strip()
            return (
                "**[Offline Knowledge Base — IBM Granite not configured or unavailable]**\n\n"
                + snippet
                + "\n\n---\n"
                "*Configure WATSONX_API_KEY and WATSONX_PROJECT_ID in your .env file "
                "to enable live IBM Granite responses.*"
            )
        return (
            "I could not find specific information for that query in the offline knowledge base. "
            "Please try rephrasing your question, or call **1930** for immediate assistance."
        )


# ---------------------------------------------------------------------------
# Financial calculator (pure function, no dependencies)
# ---------------------------------------------------------------------------

def calculate_annualized_cost(
    principal: float,
    total_repayment: float,
    tenure_days: int,
) -> dict:
    """
    Compute simplified annualized borrowing cost.

    Formula: ((total_repayment - principal) / principal) × (365 / tenure_days) × 100

    This is a simplified estimate, NOT a legally defined APR.
    Returns a dict with result and validation state.
    """
    errors = []
    if principal <= 0:
        errors.append("Principal must be greater than zero.")
    if tenure_days <= 0:
        errors.append("Tenure must be at least 1 day.")
    if not errors and total_repayment < principal:
        errors.append("Total repayment cannot be less than principal.")
    if principal > 100_000_000:
        errors.append("Principal exceeds maximum allowed value (₹10 crore).")
    if tenure_days > 36500:
        errors.append("Tenure exceeds maximum allowed value (100 years).")

    if errors:
        return {"valid": False, "errors": errors}

    cost = ((total_repayment - principal) / principal) * (365.0 / tenure_days) * 100
    cost = round(cost, 2)
    predatory_threshold = 36.0

    return {
        "valid": True,
        "annualized_cost_pct": cost,
        "label": "Simplified annualized borrowing cost (estimate only; not a legally defined APR)",
        "is_predatory": cost > predatory_threshold,
        "threshold_pct": predatory_threshold,
        "errors": [],
    }


# ---------------------------------------------------------------------------
# Orchestrator — coordinates all agents
# ---------------------------------------------------------------------------

class ArthSaathiOrchestrator:
    """
    Coordinates RAG retrieval, fraud detection, emergency escalation,
    and IBM Granite inference into a single structured response.
    """

    def __init__(self) -> None:
        self.rag = RAGRetrievalAgent()
        self.fraud = FraudDetectionAgent()
        self.emergency = EmergencyProtocolAgent()
        self.llm = GraniteLLMAgent()

    def answer(self, query: str) -> OrchestratorResponse:
        """Process a user query and return a structured OrchestratorResponse."""
        query = query.strip()

        # Agent 2: fraud alerts
        fraud_alerts = self.fraud.analyze(query)

        # Agent 3: emergency escalation flag
        is_emergency = self.emergency.should_escalate(query)

        # Agent 1: retrieve relevant passages
        passages = self.rag.retrieve(query, top_k=5)
        context = "\n\n".join(p.text for p in passages)

        # Agent 4: generate answer
        answer_text, source = self.llm.generate(query, context)

        # Prepend emergency protocol if triggered
        if is_emergency:
            answer_text = self.emergency.PROTOCOL + "\n\n---\n\n" + answer_text

        provider_error: Optional[str] = None
        if source.startswith("provider_error:"):
            provider_error = source[len("provider_error:"):]
            source = "provider_error"

        return OrchestratorResponse(
            answer=answer_text,
            source=source,
            fraud_alerts=fraud_alerts,
            emergency=is_emergency,
            passages=passages,
            provider_error=provider_error,
        )

    @property
    def llm_configured(self) -> bool:
        return self.llm.configured

    @property
    def llm_ready(self) -> bool:
        return self.llm._ready
