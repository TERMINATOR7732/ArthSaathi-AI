"""
app.py — ArthSaathi AI Flask application.

Routes:
  GET  /             Serves the web application.
  GET  /api/health   Reports application health (no credentials exposed).
  POST /api/chat     Answers a financial literacy or fraud query.
  POST /api/apr      Calculates simplified annualized borrowing cost.
"""

from __future__ import annotations

import os
import logging
from flask import Flask, jsonify, render_template, request, Response

from arthsaathi_agent import ArthSaathiOrchestrator, calculate_annualized_cost
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("arthsaathi")

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "change-this-in-production")

# Single orchestrator instance — initialised once at startup
_orchestrator = ArthSaathiOrchestrator()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_QUERY_LEN = 1000   # characters
MAX_PRINCIPAL = 100_000_000   # ₹10 crore
MAX_TENURE_DAYS = 36500       # 100 years


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _error(message: str, status: int = 400) -> tuple[Response, int]:
    return jsonify({"status": "error", "message": message}), status


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/")
def index() -> str:
    """Serve the single-page web application."""
    return render_template("index.html")


@app.get("/api/health")
def health() -> tuple[Response, int]:
    """
    Return application health without exposing any credential values.
    """
    return jsonify({
        "status": "ok",
        "service": "ArthSaathi AI",
        "kb_passages_loaded": len(_orchestrator.rag.passages),
        "llm_configured": _orchestrator.llm_configured,
        "llm_ready": _orchestrator.llm_ready,
        # Intentionally omit: API keys, project IDs, URLs containing tokens
    }), 200


@app.post("/api/chat")
def chat() -> tuple[Response, int]:
    """
    Process a financial literacy or fraud-awareness query.

    Request body (JSON):
      { "query": "<user question>" }

    Response:
      {
        "status": "ok" | "not_configured" | "provider_error",
        "answer": "...",
        "source": "granite" | "offline_kb" | "not_configured" | "provider_error",
        "fraud_alerts": [...],
        "emergency": true | false,
        "passages": [{"id": "...", "text": "..."}],
        "provider_error": null | "..."
      }
    """
    data = request.get_json(silent=True)
    if not data or not isinstance(data, dict):
        return _error("Request body must be JSON with a 'query' field.")

    query = data.get("query", "")
    if not isinstance(query, str) or not query.strip():
        return _error("'query' must be a non-empty string.")
    if len(query) > MAX_QUERY_LEN:
        return _error(f"'query' exceeds maximum length of {MAX_QUERY_LEN} characters.")

    # Do NOT log the query content — user financial questions are private
    logger.info("POST /api/chat — query length=%d", len(query))

    response = _orchestrator.answer(query)
    result = response.to_dict()

    # Map internal source to API-level status
    if response.source in ("granite",):
        result["status"] = "ok"
    elif response.source == "not_configured":
        result["status"] = "not_configured"
    else:
        result["status"] = "provider_error"

    # Sanitize provider_error before sending to client: IBM API error bodies may
    # contain trace UUIDs and other internal identifiers that must not be
    # forwarded. Replace with a generic message; details are logged server-side.
    if result.get("provider_error"):
        logger.warning("Provider error (details suppressed from response): %s",
                       result["provider_error"])
        result["provider_error"] = "IBM watsonx.ai request failed. Serving offline response."

    return jsonify(result), 200


@app.post("/api/apr")
def apr() -> tuple[Response, int]:
    """
    Calculate simplified annualized borrowing cost.

    Request body (JSON):
      { "principal": 10000, "repayment": 12500, "days": 15 }

    Response:
      {
        "status": "ok" | "error",
        "annualized_cost_pct": 608.33,
        "label": "Simplified annualized borrowing cost (estimate only; not a legally defined APR)",
        "is_predatory": true,
        "threshold_pct": 36.0
      }
    """
    data = request.get_json(silent=True)
    if not data or not isinstance(data, dict):
        return _error("Request body must be JSON with 'principal', 'repayment', 'days' fields.")

    # Validate field presence and types
    for field_name in ("principal", "repayment", "days"):
        if field_name not in data:
            return _error(f"Missing required field: '{field_name}'.")
        if not isinstance(data[field_name], (int, float)):
            return _error(f"'{field_name}' must be a number.")

    principal = float(data["principal"])
    repayment = float(data["repayment"])
    days = data["days"]

    if not isinstance(days, int) or isinstance(days, bool):
        # Accept floats that are whole numbers
        if isinstance(days, float) and days == int(days):
            days = int(days)
        else:
            return _error("'days' must be a positive integer.")

    result = calculate_annualized_cost(
        principal=principal,
        total_repayment=repayment,
        tenure_days=days,
    )

    if not result["valid"]:
        return jsonify({"status": "error", "errors": result["errors"]}), 400

    return jsonify({
        "status": "ok",
        "annualized_cost_pct": result["annualized_cost_pct"],
        "label": result["label"],
        "is_predatory": result["is_predatory"],
        "threshold_pct": result["threshold_pct"],
    }), 200


# ---------------------------------------------------------------------------
# Error handlers — never expose internal stack traces to the browser
# ---------------------------------------------------------------------------

@app.errorhandler(404)
def not_found(exc) -> tuple[Response, int]:
    return jsonify({"status": "error", "message": "Not found."}), 404


@app.errorhandler(405)
def method_not_allowed(exc) -> tuple[Response, int]:
    return jsonify({"status": "error", "message": "Method not allowed."}), 405


@app.errorhandler(500)
def internal_error(exc) -> tuple[Response, int]:
    logger.exception("Unhandled server error")
    return jsonify({"status": "error", "message": "Internal server error."}), 500


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    app.run(host="0.0.0.0", port=5000, debug=debug)
