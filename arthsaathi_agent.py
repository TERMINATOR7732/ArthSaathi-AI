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
import time
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
    latency_ms: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "answer": self.answer,
            "source": self.source,
            "fraud_alerts": self.fraud_alerts,
            "emergency": self.emergency,
            "passages": [{"id": p.id, "text": p.text[:400]} for p in self.passages],
            "provider_error": self.provider_error,
            "latency_ms": self.latency_ms,
        }


# ---------------------------------------------------------------------------
# Agent 1 — RAG Retrieval (keyword-based; explicitly NOT semantic/vector search)
# ---------------------------------------------------------------------------

# Regex that matches standalone KB section-heading lines of the form:
#   === SECTION N: TITLE ===
# These lines are purely structural formatting and carry no retrievable content.
_HEADING_RE = re.compile(r"^={3,}\s*.+={3,}$")


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
        # Split on blank lines; keep only content passages.
        # Excluded:
        #   - Empty / whitespace-only blocks.
        #   - Blocks with 40 chars or fewer (too short to be useful).
        #   - Standalone section-heading lines (=== SECTION N: TITLE ===).
        retained_index = 0
        for chunk in text.split("\n\n"):
            chunk = chunk.strip()
            if not chunk:
                continue
            if len(chunk) <= 40:
                continue
            if _HEADING_RE.match(chunk):
                continue
            self.passages.append(
                Passage(source_file=path.name, index=retained_index, text=chunk)
            )
            retained_index += 1

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

# ---------------------------------------------------------------------------
# QR receive-money scam detection — contextual pattern matching
#
# A scammer claims the victim must *scan* a QR code to *receive* money/refund.
# In reality, scanning and authorising any QR payment SENDS money to the scammer.
#
# Detection logic (all three must match the full query string):
#   1. Query mentions "qr" or "qr code".
#   2. Query mentions scanning ("scan" or "scanning").
#   3. Query mentions a receive-money context word.
#
# Negative guard: queries that clearly describe outgoing merchant payments
#   ("pay for groceries", "pay a merchant", "how QR payments work") are excluded
#   to prevent false positives on ordinary payment questions.
# ---------------------------------------------------------------------------
_QR_KEYWORD_RE = re.compile(r"\bqr\b", re.IGNORECASE)
_QR_SCAN_RE = re.compile(r"\b(?:scan|scanning)\b", re.IGNORECASE)
_QR_RECEIVE_CONTEXT_RE = re.compile(
    r"\b(?:receive|receiving|refund|cashback|get paid|get money|"
    r"credit|credited|earn|payment received|paid back)\b",
    re.IGNORECASE,
)

# Safe-context phrases that indicate the user is paying a merchant — not a scam.
_QR_SAFE_PAYMENT_RE = re.compile(
    r"\b(?:pay for|pay a merchant|pay at|pay the merchant|paying for|paying at|"
    r"how qr payments work|how do qr|explain.*qr payment|pay using qr|"
    r"scan.*to pay|want to pay)\b",
    re.IGNORECASE,
)


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
        # NOTE: QR receive-money scam is detected via _analyze_qr() (contextual
        # regex) rather than a plain substring, to avoid false positives on
        # ordinary merchant-payment questions.
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

    _QR_RECEIVE_ALERT = (
        "⚠️ ALERT: Scanning a QR code NEVER receives money — QR codes are for "
        "PAYMENTS only. Anyone who claims you must scan a QR code to receive "
        "money, a refund, or cashback is running a known scam: you will be "
        "PAYING them, not receiving funds. Do not scan, do not enter your UPI "
        "PIN. Report this to 1930 immediately."
    )

    def analyze(self, query: str) -> list[str]:
        alerts = [msg for trigger, msg in self._RULES if trigger in query.lower()]
        # QR receive-money scam: require all three signals present anywhere in the
        # query (order-independent), then exclude safe merchant-payment context.
        if (
            _QR_KEYWORD_RE.search(query)
            and _QR_SCAN_RE.search(query)
            and _QR_RECEIVE_CONTEXT_RE.search(query)
            and not _QR_SAFE_PAYMENT_RE.search(query)
        ):
            alerts.append(self._QR_RECEIVE_ALERT)
        return alerts


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
# Language detection and greeting policy
# ---------------------------------------------------------------------------

_GREETING_PATTERNS = [
    re.compile(r"^(hi|hello|hey|hiya|howdy|greetings)[\s!.]*$", re.IGNORECASE),
    re.compile(r"^(good\s+(morning|afternoon|evening|day))[\s!.]*$", re.IGNORECASE),
    re.compile(r"^(namaste|namaskar|pranam)[\s!.]*$", re.IGNORECASE),
    re.compile(r"^(नमस्ते|नमस्कार|प्रणाम|हेलो|हाय)[\s।!.]*$", re.IGNORECASE),
]

_DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]")

# Characteristic Marathi tokens (words/morphemes distinct from standard Hindi)
_MARATHI_SPECIFIC_TOKENS = {
    "आहे", "नाही", "सांगा", "माहिती", "कसे", "कशी", "काय", "झाले", "माझे",
    "माझ्या", "मिळाले", "करावे", "करावी", "होते", "आहोत", "तक्रार", "नमस्कार",
    "बदलायचा", "ठेवावे", "कसा"
}

# Characteristic Hindi tokens (words/morphemes distinct from Marathi)
_HINDI_SPECIFIC_TOKENS = {
    "है", "नहीं", "बताएं", "बताओ", "जानकारी", "कैसे", "क्या", "हुआ", "मेरा",
    "मेरी", "मेरे", "मुझे", "करें", "करो", "नमस्ते", "प्रणाम", "बारे", "खाते", "खाता"
}

# Characteristic Hinglish tokens (Latin-script transliterated Hindi)
_HINGLISH_TOKENS = {
    "kya", "kaise", "mera", "meri", "mere", "paise", "paisa", "bheja",
    "aaya", "kata", "kat", "karo", "karna", "nahi", "nahin", "batao",
    "chahiye", "hoga", "hogi", "bhai", "aap", "apna", "apni", "wala",
    "wali", "wale", "dekh", "raha", "rahi", "thik", "theek", "khata",
    "dhokhadhadi", "madad"
}


def detect_language(text: str) -> str:
    """
    Classify input query language into one of: 'en', 'hi', 'hinglish', 'mr'.
    Defaults to 'en' (English).
    """
    clean = text.strip()
    if not clean:
        return "en"

    # Check for Devanagari script
    if _DEVANAGARI_RE.search(clean):
        words = set(re.findall(r"[\u0900-\u097F]+", clean))
        marathi_hits = len(words.intersection(_MARATHI_SPECIFIC_TOKENS))
        hindi_hits = len(words.intersection(_HINDI_SPECIFIC_TOKENS))
        if marathi_hits > hindi_hits:
            return "mr"
        return "hi"

    # Latin script: tokenize alphabetic words
    tokens = [t.lower() for t in re.findall(r"\b[a-zA-Z]+\b", clean)]
    if not tokens:
        return "en"

    # Single-word or pure English greetings MUST be English
    if len(tokens) <= 2 and any(p.match(clean) for p in _GREETING_PATTERNS[:2]):
        return "en"

    hinglish_matches = [t for t in tokens if t in _HINGLISH_TOKENS]
    # If 2 or more Hinglish tokens, or >= 25% of tokens match
    if len(hinglish_matches) >= 2 or (tokens and len(hinglish_matches) / len(tokens) >= 0.25):
        return "hinglish"

    return "en"


def is_greeting(query: str) -> tuple[bool, str]:
    """
    Determine if the query is a greeting.
    Returns (is_greeting_bool, detected_language).
    """
    clean = query.strip()
    for pattern in _GREETING_PATTERNS:
        if pattern.match(clean):
            lang = detect_language(clean)
            return True, lang
    return False, detect_language(clean)


def get_deterministic_greeting(lang: str) -> str:
    """Return an authoritative, warm greeting tailored to the detected language."""
    if lang == "mr":
        return (
            "नमस्कार! मी **अर्थसाथी** आहे, तुमचा डिजिटल आर्थिक साक्षरता आणि यूपीआई फसवणूक "
            "प्रतिबंधक सहाय्यक.\n\n"
            "मी तुम्हाला यूपीआई सुरक्षा नियम, संशयास्पद कर्ज अ‍ॅप्स ओळखणे आणि आर्थिक फसवणूक झाल्यास "
            "काय करावे याबाबत मार्गदर्शन करू शकतो.\n\n"
            "मला तुमचा प्रश्न विचारा — त्वरित सायबर फसवणूक मदतीसाठी **1930** वर कॉल करा."
        )
    elif lang in ("hi", "hinglish"):
        if lang == "hinglish":
            return (
                "Namaste! Main hoon **ArthSaathi**, aapka digital financial literacy aur UPI fraud shield.\n\n"
                "Aap mujhse UPI safety rules, suspicious loan apps, fraud SMS, ya cybercrime reporting "
                "ke baare mein pooch sakte hain.\n\n"
                "Apna sawaal neeche type karein — kisi bhi emergency ke liye turant **1930** par call karein."
            )
        return (
            "नमस्ते! मैं **अर्थसाथी** हूँ, आपका डिजिटल वित्तीय साक्षरता और यूपीआई धोखाधड़ी सुरक्षा सहायक।\n\n"
            "मैं आपको यूपीआई सुरक्षा नियम समझने, संदिग्ध लोन ऐप्स पहचानने और धोखाधड़ी की स्थिति में "
            "उचित कदम उठाने में मदद कर सकता हूँ।\n\n"
            "कृपया अपना प्रश्न नीचे पूछें — किसी भी वित्तीय धोखाधड़ी की तुरंत शिकायत के लिए **1930** पर कॉल करें।"
        )
    # Default: English
    return (
        "Hello! I am **ArthSaathi**, your digital financial literacy and UPI fraud-prevention assistant.\n\n"
        "I can help you understand UPI safety rules, recognize payment scams, verify loan terms, "
        "and guide you on reporting cyber fraud.\n\n"
        "How can I assist your financial safety today? (For immediate cyber-fraud reporting, call **1930** 24×7)."
    )


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
        "Respond in clear, accessible language adhering strictly to the user's language. "
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
            return self._offline_answer(context, query=query), "not_configured"

        if not self._ready or self._client is None:
            err = self.init_error or "SDK initialization failed"
            return self._offline_answer(context, query=query), f"provider_error:{err}"

        lang = detect_language(query)
        greeting_flag, _ = is_greeting(query)

        if lang == "hi":
            lang_directive = (
                "LANGUAGE DIRECTIVE: The user communicated in Hindi. "
                "You MUST respond in clear, accessible Hindi using Devanagari script."
            )
        elif lang == "mr":
            lang_directive = (
                "LANGUAGE DIRECTIVE: The user communicated in Marathi. "
                "You MUST respond in clear, accessible Marathi using Devanagari script."
            )
        elif lang == "hinglish":
            lang_directive = (
                "LANGUAGE DIRECTIVE: The user communicated in Hinglish. "
                "Respond in natural, conversational Hinglish using Latin script."
            )
        else:  # Default: 'en'
            lang_directive = (
                "LANGUAGE DIRECTIVE: The user communicated in English. "
                "You MUST respond STRICTLY in English. "
                "Do NOT switch to Hindi, do NOT use Devanagari script, and do NOT include Hindi greetings or translations."
            )

        if greeting_flag:
            lang_directive += (
                f" The user sent a greeting ('{query}'). Greet them warmly as ArthSaathi (AI financial literacy "
                "and UPI fraud shield) in the specified language, explain what financial safety guidance "
                "you provide, and invite their question."
            )

        messages = [
            {
                "role": "system",
                "content": (
                    f"{self._SYSTEM_PROMPT}\n\n"
                    f"{lang_directive}\n\n"
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
            return self._offline_answer(context, query=query), f"provider_error:{exc}"

    @staticmethod
    def _offline_answer(context: str, query: str = "") -> str:
        """Return best-available KB content with a clear offline notice, or a friendly greeting."""
        if query and is_greeting(query)[0]:
            lang = detect_language(query)
            return get_deterministic_greeting(lang)

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
        t0 = time.perf_counter()
        query = query.strip()

        # Agent 2: fraud alerts
        fraud_alerts = self.fraud.analyze(query)

        # Agent 3: emergency escalation flag
        is_emergency = self.emergency.should_escalate(query)

        # Agent 1: retrieve relevant passages
        t_rag0 = time.perf_counter()
        passages = self.rag.retrieve(query, top_k=5)
        retrieval_ms = (time.perf_counter() - t_rag0) * 1000.0
        context = "\n\n".join(p.text for p in passages)

        # Agent 4: generate answer
        t_llm0 = time.perf_counter()
        answer_text, source = self.llm.generate(query, context)
        provider_ms = (time.perf_counter() - t_llm0) * 1000.0

        # Prepend emergency protocol if triggered
        if is_emergency:
            answer_text = self.emergency.PROTOCOL + "\n\n---\n\n" + answer_text

        provider_error: Optional[str] = None
        if source.startswith("provider_error:"):
            provider_error = source[len("provider_error:"):]
            source = "provider_error"

        total_ms = (time.perf_counter() - t0) * 1000.0
        latency_ms = {
            "retrieval": round(retrieval_ms, 1),
            "provider": round(provider_ms, 1),
            "total": round(total_ms, 1),
        }

        return OrchestratorResponse(
            answer=answer_text,
            source=source,
            fraud_alerts=fraud_alerts,
            emergency=is_emergency,
            passages=passages,
            provider_error=provider_error,
            latency_ms=latency_ms,
        )

    @property
    def llm_configured(self) -> bool:
        return self.llm.configured

    @property
    def llm_ready(self) -> bool:
        return self.llm._ready
