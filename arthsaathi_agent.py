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

import concurrent.futures
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

try:
    from dotenv import load_dotenv
    _dotenv_path = _HERE / ".env"
    if _dotenv_path.is_file():
        load_dotenv(dotenv_path=_dotenv_path)
except Exception:
    pass

_KB_FILES = [
    "rbi_npci_financial_literacy_kb.txt",
    "rbi_whitelist_and_cyber_stats.txt",
]


from core.config import (
    DEFAULT_WATSONX_MODEL_ID,
    DEFAULT_WATSONX_URL,
    WATSONX_CONFIG_KEYS as _WATSONX_CONFIG_KEYS,
    UUID_RE as _UUID_RE,
    WatsonxConfig,
    get_config_var,
    get_config_var_with_source,
    get_st_secrets_root_keys as _get_st_secrets_root_keys,
    has_enclosing_quotes as _has_enclosing_quotes,
    normalize_watsonx_url,
)
from ibm.exceptions import (
    CATEGORY_AUTH_INVALID_CREDENTIALS,
    CATEGORY_AUTH_NETWORK_ERROR,
    CATEGORY_CONFIG_MALFORMED,
    CATEGORY_WATSONX_TIMEOUT,
    WatsonxError,
    categorize_ibm_exception,
)
from ibm.watsonx_client import WatsonxClient


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
    source: str                          # "granite" | "offline_kb" | "not_configured" | "rule_based" | "provider_error"
    fraud_alerts: list[str] = field(default_factory=list)
    emergency: bool = False
    passages: list[Passage] = field(default_factory=list)
    provider_error: Optional[str] = None
    latency_ms: dict[str, float] = field(default_factory=dict)
    model_id: Optional[str] = None
    status: str = "success"
    error_category: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "answer": self.answer,
            "source": self.source,
            "fraud_alerts": self.fraud_alerts,
            "emergency": self.emergency,
            "passages": [{"id": p.id, "text": p.text[:400]} for p in self.passages],
            "provider_error": self.provider_error,
            "latency_ms": self.latency_ms,
            "model_id": self.model_id,
            "status": self.status,
            "error_category": self.error_category,
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
        "## Immediate Fraud Response Steps\n\n"
        "**Step 1 — Call 1930 immediately (National Cybercrime Helpline / Cyber Financial Fraud Helpline).**  \n"
        "Available 24×7. Prompt reporting enables the Citizen Financial Cyber Fraud Reporting & Management System (CFCFRMS) "
        "to alert concerned banks and authorities to take timely action. "
        "*Note: A fund freeze, recovery, or refund is not guaranteed; decisions rest with concerned banks and investigating authorities.*  \n\n"
        "**Step 2 — File an official complaint online.**  \n"
        "Visit https://cybercrime.gov.in and submit transaction IDs (UTR), debit SMS screenshots, and scam details. "
        "Preserve the formal acknowledgement number.  \n\n"
        "**Step 3 — Block your compromised cards and UPI access immediately.**  \n"
        "Use your bank's mobile application, official net banking, or call the emergency number on the back of your card.  \n\n"
        "**Step 4 — Notify your bank immediately in writing.**  \n"
        "Under the RBI customer liability framework (Circular DBR.No.Leg.BC.78/09.07.005/2017-18):\n"
        "- **Bank Negligence/Deficiency:** Zero customer liability where the deficiency lies with the bank, regardless of when reported.\n"
        "- **Third-Party Breach:** Zero customer liability if reported within 3 working days of receiving bank communication. If reported within 4 to 7 working days, liability is limited according to RBI transaction slabs. Beyond 7 working days, the bank's board-approved policy applies.\n"
        "- **Customer Negligence:** Where loss occurs due to sharing credentials (such as OTP or UPI PIN), the customer bears the entire loss until reported to the bank; unauthorized transactions occurring after reporting are borne by the bank.\n"
        "*Always report immediately — do not delay. Refunds are not automatically guaranteed.*\n\n"
        "**RBI Ombudsman:** https://cms.rbi.org.in | Toll-free: **14448**\n\n"
        "> Do not delete fraudulent messages, transaction SMS records, call logs, or payment screenshots — these are critical investigation evidence."
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


def _categorize_init_error(exc: Exception) -> str:
    """Classify an initialization exception into a generic failure category without logging sensitive data."""
    exc_name = type(exc).__name__.lower()
    if "credential" in exc_name or "auth" in exc_name or "permission" in exc_name:
        return "auth_invalid_credentials"
    if "connect" in exc_name or "timeout" in exc_name or "network" in exc_name:
        return "network_connection_error"
    try:
        msg = str(exc).lower()
        if "bxnim0415e" in msg or "invalid credentials" in msg or "401" in msg or "403" in msg:
            return "auth_invalid_credentials"
        if "connection" in msg or "timed out" in msg:
            return "network_connection_error"
    except Exception:
        pass
    if isinstance(exc, (ValueError, KeyError)):
        return "configuration_error"
    return "initialization_error"


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

    client: Optional[WatsonxClient] = None
    configured: bool = False
    _ready: bool = False
    init_error: Optional[str] = None
    error_category: Optional[str] = None
    last_model_id: Optional[str] = None
    last_error_category: Optional[str] = None
    _client: Any = None

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

    def __init__(self, config: Optional[WatsonxConfig] = None) -> None:
        self.config = config or WatsonxConfig.from_sources()
        self.client = None
        self.configured = False
        self._ready = False
        self.init_error = None
        self.error_category = None
        self.last_model_id = None
        self.last_error_category = None
        self._client = None

        api_key, api_key_src = get_config_var_with_source("WATSONX_API_KEY", "")
        project_id, proj_id_src = get_config_var_with_source("WATSONX_PROJECT_ID", "")
        url, url_src = get_config_var_with_source("WATSONX_URL", "https://us-south.ml.cloud.ibm.com")
        model_id, model_src = get_config_var_with_source("WATSONX_MODEL_ID", "ibm/granite-4-h-small")

        if not api_key or not project_id:
            return  # not configured; graceful degradation

        self.configured = True

        api_key_has_quotes = _has_enclosing_quotes(api_key)
        api_key_is_uuid = bool(_UUID_RE.match(api_key))
        proj_id_is_uuid = bool(_UUID_RE.match(project_id))

        if api_key_has_quotes or api_key_is_uuid:
            import sys
            suspicious = []
            if api_key_has_quotes:
                suspicious.append("api_key has enclosing quotes (possible TOML formatting issue)")
            if api_key_is_uuid:
                suspicious.append("api_key matches UUID structure (possible configuration mismatch / swapped with project_id)")
            print(
                f"[ArthSaathi] WARNING: Suspicious credential structure detected — {'; '.join(suspicious)}. "
                f"sources: api_key={api_key_src}, project_id={proj_id_src}",
                file=sys.stderr,
            )

        self.client = WatsonxClient(self.config)
        self._ready = self.client.is_ready
        self.init_error = self.client.init_error
        self.error_category = self.client.error_category
        self._client = self.client._model_inference

        if self.configured and not self._ready:
            exc_class = self.init_error or "InitializationError"
            failure_cat = self.error_category or _categorize_init_error(Exception(exc_class))
            root_secrets = _get_st_secrets_root_keys()
            root_keys_str = ",".join(root_secrets) if root_secrets else "none"

            if "//" in url:
                url_host = url.split("//")[1].split("/")[0]
            elif "/" in url:
                url_host = url.split("/")[0]
            else:
                url_host = url or "unknown"

            import sys
            print(
                f"[ArthSaathi] GraniteLLMAgent init failed: {exc_class} [{failure_cat}] — "
                "credentials were present but SDK initialization did not complete. "
                f"sources: api_key={api_key_src}, project_id={proj_id_src}, url={url_src}, model={model_src}; "
                f"present: api_key={bool(api_key)}, project_id={bool(project_id)}; "
                f"structure: api_key_has_quotes={api_key_has_quotes}, api_key_is_uuid={api_key_is_uuid}, "
                f"proj_id_is_uuid={proj_id_is_uuid}; "
                f"root_secrets_found=[{root_keys_str}]; "
                f"model_id={model_id!r} url_host={url_host}",
                file=sys.stderr,
            )

    def generate(self, query: str, context: str, target_lang: Optional[str] = None) -> tuple[str, str]:
        """
        Returns (answer_text, source_label).
        source_label: "granite" | "not_configured" | "provider_error:<err>"
        """
        if not getattr(self, "configured", False):
            self.last_model_id = None
            self.last_error_category = "config_missing"
            return self._offline_answer(context, query=query, target_lang=target_lang), "not_configured"

        ready = getattr(self, "_ready", False)
        client_inference = getattr(self, "_client", None)
        client_obj = getattr(self, "client", None)
        client_is_ready = bool(client_obj and client_obj.is_ready)

        if not ready or (client_inference is None and not client_is_ready):
            err = getattr(self, "init_error", None) or "SDK initialization failed"
            self.last_model_id = None
            self.last_error_category = getattr(self, "error_category", None) or "initialization_error"
            return self._offline_answer(context, query=query, target_lang=target_lang), f"provider_error:{err}"

        if target_lang and target_lang != "auto":
            lang = target_lang
        else:
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

        # Ensure WatsonxClient wrapper exists
        if not hasattr(self, "client") or self.client is None:
            self.client = WatsonxClient(getattr(self, "config", None))

        # Synchronize _client if overridden or mocked on agent
        if self._client is not None:
            self.client._model_inference = self._client
            self.client._ready = True
            self.client.configured = True

        try:
            content, meta = self.client.chat_with_metadata(
                messages=messages,
                params={"max_tokens": 512, "temperature": 0.3},
                timeout=50.0,
            )
            self.last_model_id = meta.get("model_id") or getattr(self.config, "model_id", "ibm/granite-4-h-small")
            self.last_error_category = None
            return content, "granite"
        except concurrent.futures.TimeoutError:
            self.last_model_id = None
            self.last_error_category = CATEGORY_WATSONX_TIMEOUT
            return (
                self._offline_answer(context, query=query, target_lang=target_lang),
                "provider_error:IBM watsonx.ai request timed out after 50 seconds",
            )
        except WatsonxError as exc:
            self.last_model_id = None
            self.last_error_category = exc.category
            err_msg = getattr(exc, "message", str(exc))
            return (
                self._offline_answer(context, query=query, target_lang=target_lang),
                f"provider_error:{err_msg}",
            )
        except Exception as exc:
            self.last_model_id = None
            self.last_error_category = _categorize_init_error(exc)
            return (
                self._offline_answer(context, query=query, target_lang=target_lang),
                f"provider_error:{exc}",
            )

    @staticmethod
    def _offline_answer(context: str, query: str = "", target_lang: Optional[str] = None) -> str:
        """Return best-available KB content with a clear offline notice, or a friendly greeting."""
        if query and is_greeting(query)[0]:
            lang = target_lang if (target_lang and target_lang != "auto") else detect_language(query)
            return get_deterministic_greeting(lang)

        if context.strip():
            snippet = context[:1200].strip()
            return (
                "**[Offline Knowledge Base — IBM Granite not configured or unavailable]**\n\n"
                + snippet
                + "\n\n---\n"
                "*Configure WATSONX_API_KEY and WATSONX_PROJECT_ID in your .env file or Streamlit secrets "
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
    upfront_fees: float = 0.0,
) -> dict:
    """
    Compute objective borrowing figures and simplified annualized borrowing cost estimate.

    Formula: ((total_repayment - principal) / principal) × (365 / tenure_days) × 100

    This is an educational estimate, NOT a legally defined APR under the RBI Digital
    Lending Guidelines (DOR.CRE.REC.66/21.07.001/2022-23). Does not apply an arbitrary
    universal 36% ceiling. Returns objective monetary values, net disbursement,
    and factual risk screening indicators.
    """
    errors = []
    if principal <= 0:
        errors.append("Principal must be greater than zero.")
    if tenure_days <= 0:
        errors.append("Tenure must be at least 1 day.")
    if upfront_fees < 0:
        errors.append("Upfront deductions cannot be negative.")
    if upfront_fees >= principal and principal > 0:
        errors.append("Upfront deductions cannot equal or exceed principal.")
    if not errors and total_repayment < principal:
        errors.append("Total repayment cannot be less than principal.")
    if principal > 100_000_000:
        errors.append("Principal exceeds maximum allowed value (₹10 crore).")
    if tenure_days > 36500:
        errors.append("Tenure exceeds maximum allowed value (100 years).")

    if errors:
        return {"valid": False, "errors": errors}

    net_disbursed = round(principal - upfront_fees, 2)
    total_borrowing_cost = round((total_repayment - principal) + upfront_fees, 2)
    cost = ((total_repayment - principal) / principal) * (365.0 / tenure_days) * 100
    cost = round(cost, 2)

    risk_indicators = [
        "Undisclosed or unexplained upfront deductions / processing charges.",
        "Absence of a standardized Key Fact Statement (KFS) provided prior to loan agreement.",
        "Lender not identifiable as an RBI-regulated bank or registered NBFC.",
        "Repayment demands directed to personal accounts or unverified UPI IDs.",
        "Excessive or coercive collection practices or invasive mobile permissions.",
    ]

    cost_explanation = (
        f"Your estimated annualized borrowing cost is {cost:.2f}%. "
        "Review the Key Fact Statement (KFS), total charges, repayment obligations, "
        "and lender identity on the RBI Sachet portal before accepting this loan."
    )

    return {
        "valid": True,
        "gross_principal": principal,
        "net_disbursed": net_disbursed,
        "upfront_fees": upfront_fees,
        "total_repayment": total_repayment,
        "total_borrowing_cost": total_borrowing_cost,
        "tenure_days": tenure_days,
        "annualized_cost_pct": cost,
        "label": "Estimated annualized borrowing cost (simplified estimate; not a legal APR)",
        "cost_explanation": cost_explanation,
        "risk_indicators": risk_indicators,
        "errors": [],
    }


# Canonical alias for compatibility
calculate_effective_apr = calculate_annualized_cost


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
        # Mirror the LLM diagnostic state as instance attributes so they survive
        # @st.cache_resource across Streamlit hot-reloads (the cached instance
        # retains its own __dict__ even when the class is redefined by a new
        # module load; class-level @property lookups would fail in that scenario).
        self.llm_init_error: Optional[str] = self.llm.init_error

    def answer(self, query: str, target_lang: Optional[str] = None) -> OrchestratorResponse:
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
        answer_text, source = self.llm.generate(query, context, target_lang=target_lang)
        provider_ms = (time.perf_counter() - t_llm0) * 1000.0

        # Prepend emergency protocol if triggered
        if is_emergency:
            answer_text = self.emergency.PROTOCOL + "\n\n---\n\n" + answer_text

        provider_error: Optional[str] = None
        if source.startswith("provider_error:"):
            provider_error = source[len("provider_error:"):]
            source = "provider_error"

        # Determine status, model_id, and error_category
        status: str
        model_id: Optional[str] = None
        error_category: Optional[str] = None

        if source == "granite":
            status = "success"
            model_id = getattr(self.llm, "last_model_id", None) or getattr(getattr(self.llm, "config", None), "model_id", "ibm/granite-4-h-small")
            error_category = None
        elif source == "not_configured":
            status = "fallback"
            model_id = None
            error_category = getattr(self.llm, "last_error_category", None) or "config_missing"
        elif source == "provider_error":
            status = "fallback"
            model_id = None
            error_category = getattr(self.llm, "last_error_category", None) or "watsonx_service_error"
        elif source == "rule_based":
            status = "blocked" if is_emergency else "success"
            model_id = None
            error_category = None
        else:
            status = "fallback"
            model_id = None
            error_category = None

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
            model_id=model_id,
            status=status,
            error_category=error_category,
        )

    @property
    def llm_configured(self) -> bool:
        return self.llm.configured

    @property
    def llm_ready(self) -> bool:
        return self.llm._ready

    def get_diagnostics(self) -> dict[str, Any]:
        """Return safe, leak-free system diagnostics for UI and health reporting."""
        if hasattr(self.llm, "client") and self.llm.client:
            diag = self.llm.client.get_safe_diagnostics()
        else:
            from core.config import WatsonxConfig
            cfg = getattr(self.llm, "config", None) or WatsonxConfig.from_sources()
            diag = cfg.get_safe_diagnostics()
            diag.update({
                "llm_ready": self.llm_ready,
                "llm_init_error": self.llm_init_error,
                "error_category": getattr(self.llm, "error_category", None),
            })
        diag.update({
            "llm_configured": self.llm_configured,
            "llm_ready": self.llm_ready,
            "llm_init_error": self.llm_init_error,
            "kb_passages_loaded": len(self.rag.passages),
        })
        return diag

    # NOTE: llm_init_error is intentionally set as an instance attribute in
    # __init__ (above) rather than as a @property.  This ensures the attribute
    # exists in the instance __dict__ and is accessible even when Streamlit's
    # @st.cache_resource returns a cached instance whose __class__ references
    # an older version of ArthSaathiOrchestrator (e.g. after a hot-reload
    # within the same worker process).  A @property only exists on the class
    # object; an instance attribute exists on the instance regardless of which
    # class version created it.
