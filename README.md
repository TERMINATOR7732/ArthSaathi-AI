# ArthSaathi AI

**Digital Financial Literacy and UPI Fraud Awareness — IBM SkillsBuild AICTE 2026 (Problem Statement No. 7)**

ArthSaathi AI is a professional web application that helps Indian citizens understand UPI safety rules, identify predatory lending practices, and respond to financial cyber-fraud. It is grounded in official RBI guidelines, NPCI UPI rules, and Government of India schemes.

---

## Features

- **AI Scam Advisor** — Answers financial literacy and fraud-detection questions, grounded in curated RBI/NPCI knowledge base passages.
- **Loan Cost Calculator** — Calculates the simplified annualized borrowing cost (not a legally defined APR) for any principal, total repayment, and tenure in days.
- **Emergency Guidance** — Clear, actionable steps for reporting financial cyber-fraud via the National Cybercrime Helpline (1930).
- **IBM watsonx.ai Integration** — Uses IBM Granite inference when credentials are configured; falls back to offline knowledge-base retrieval with a clear notice when not configured.
- **Multilingual** — Designed to handle English, Hindi, Hinglish, and Marathi queries via the Granite multilingual model.

---

## Local setup

### Prerequisites

- Python 3.10+
- `pip`
- An IBM Cloud account with a Watson Machine Learning service instance (optional — offline mode works without it)

### Install dependencies

```bash
pip install -r requirements.txt
```

### Configure environment

```bash
cp .env.example .env
# Edit .env and add your real IBM Cloud credentials
```

**Never commit `.env` to version control.**

Credentials to obtain:
- `WATSONX_API_KEY` — [IBM Cloud IAM API Keys](https://cloud.ibm.com/iam/apikeys)
- `WATSONX_PROJECT_ID` — [watsonx.ai project settings](https://dataplatform.cloud.ibm.com) → Project → Manage → General
- `WATSONX_URL` — your region endpoint, e.g. `https://us-south.ml.cloud.ibm.com`
- `WATSONX_MODEL_ID` — e.g. `ibm/granite-3-8b-instruct` (verify in Prompt Lab)

### Run locally

```bash
python app.py
```

Open [http://localhost:5000](http://localhost:5000) in your browser.

### Run tests

```bash
python -m pytest tests/ -v
```

---

## Project structure

```
ArthSaathi-AI/
├── app.py                  Flask backend and API routes
├── arthsaathi_agent.py     Agent orchestration logic
├── requirements.txt
├── .env.example            Placeholder configuration (safe to commit)
├── .gitignore
├── knowledge_base/
│   ├── rbi_npci_financial_literacy_kb.txt
│   └── rbi_whitelist_and_cyber_stats.txt
├── templates/
│   └── index.html          Application UI
├── static/
│   ├── css/styles.css
│   └── js/app.js
└── tests/
    └── test_app.py
```

---

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Serves the web application |
| `GET` | `/api/health` | Reports application health (no credentials exposed) |
| `POST` | `/api/chat` | Answers a financial literacy or fraud query |
| `POST` | `/api/apr` | Calculates simplified annualized borrowing cost |

### POST /api/chat

Request:
```json
{ "query": "What is a UPI collect request?" }
```

Response (configured):
```json
{
  "status": "ok",
  "answer": "...",
  "source": "granite",
  "fraud_alerts": [],
  "emergency": false,
  "passages": [{"id": "literacy/3", "text": "..."}]
}
```

Response (not configured):
```json
{
  "status": "not_configured",
  "answer": "...",
  "source": "offline_kb",
  "passages": [{"id": "literacy/3", "text": "..."}]
}
```

### POST /api/apr

Request:
```json
{ "principal": 10000, "repayment": 12500, "days": 15 }
```

Response:
```json
{
  "status": "ok",
  "annualized_cost_pct": 608.33,
  "label": "Simplified annualized borrowing cost (estimate only)",
  "is_predatory": true,
  "threshold_pct": 36.0
}
```

---

## Disclaimer

This application is for educational and awareness purposes only. It does not provide legal or financial advice. Always verify information with official RBI, NPCI, and government sources. For immediate fraud assistance, call **1930** (National Cybercrime Helpline, 24×7).

---

## License

MIT License — see [LICENSE](LICENSE) for details.

---

*IBM SkillsBuild AICTE Internship 2026 · Problem Statement No. 7 · Financial Literacy and UPI Fraud Prevention*
