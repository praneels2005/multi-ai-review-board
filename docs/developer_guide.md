# Startup Idea Validator — Developer Guide
---

 Overview
AI-powered FastAPI app that validates startup ideas using an LLM (Groq/OpenAI).
Returns a score, strengths, risks, competitors, and market notes.

---

 Setup

# 1. Clone the repo

git clone https://github.com/TechX-Resources/startup-validator
cd startup-validator


# 2. Create virtual environment

python -m venv venv
venv\Scripts\activate        # Windows
source venv/bin/activate     # Mac/Linux


# 3. Install dependencies

pip install -r requirements.txt
pip install slowapi pydantic-settings


# 4. Set up environment variables

cp .env.example .env

Add your API key to `.env`:

GROQ_API_KEY=your_groq_key_here
OPENAI_API_KEY=
VECTOR_DB_PATH=./data/embeddings


# 5. Run the app
uvicorn app.main:app


# 6. Open API docs

http://localhost:8000/docs


---

 API Endpoints

# GET /health
Returns service status and version.

Response:
json
{"status": "ok", "service": "startup-idea-validator-agent", "version": "0.3.0"}


# POST /validate-idea
Validates a startup idea using LLM analysis.

Request:
json
{"idea": "Your startup idea here (10-1000 characters)"}


Response:
json
{
  "score": 7.5,
  "summary": "Strong idea with clear use case",
  "strengths": ["Clear pain point", "Scalable"],
  "risks": ["Crowded market", "Monetization unclear"],
  "competitors": ["LinkedIn", "Handshake"],
  "market_notes": "EdTech growing 12% CAGR"
}


---

 Security Features (Task 2)
- Input sanitization — strips dangerous characters (`<>{}`) from all inputs
- Length validation — rejects ideas under 10 or over 1000 characters
- Rate limiting — max 10 requests per minute per IP (via slowapi)
- CORS middleware — enabled for frontend access

---

 Input Validation (app/utils/validators.py)
python
sanitize_idea(idea)         # removes dangerous characters, strips whitespace
validate_idea_length(idea)  # enforces 10-1000 character limit


---

 Running Tests (Tasks 3 & 4)
C:\Users\quest\OneDrive\Desktop\TechX\startup-validator
python -m pytest tests/test_api.py -v


11 tests covering:
- Health endpoint (3 tests)
- Input validation — empty, short, too long, missing field, valid (5 tests)
- Security — XSS input, special characters, invalid endpoint (3 tests)

---

 Project Structure

app/
  main.py              - FastAPI entry point, rate limiting, CORS
  models/llm_client.py - LLM client 
  services/            - Validation pipeline
  schemas/             - Request/response models
  utils/validators.py  - Input sanitization and length validation
  utils/logger.py      - Shared logger
  config/settings.py   - Environment settings
tests/
  test_api.py          - 11 API tests (Quest Bokwe)
docs/
  developer_guide.md   - This file

### Live evidence sufficiency

The coordinator receives the policy in `app/prompts/evidence_rubric.py` in its system
prompt and a reminder in its user request. Ratings apply to an explicitly named
founder decision, defaulting to an initial customer pilot when no decision is stated.

- **Insufficient:** no relevant empirical support; pitches, planned tests, and
  hypothetical examples do not count as observations.
- **Thin:** relevant observations exist, but at least one sufficiency gate fails.
- **Sufficient:** at least two distinct qualified empirical reports jointly cover
  every decision-critical assumption, with appropriate methods and coverage,
  explicit limitations, and no unresolved material blocker. Repeated summaries or
  multiple metrics from one study count as one report. Evidence type labels alone
  do not establish quality or independence.

A qualified report documents its source, setting, method, sample or observation
coverage, outcome, and limitations. Required detail depends on the inference and
stakes; the policy deliberately avoids a universal sample-size cutoff. A missing
specialist blocks sufficiency when its decision-critical perspective is otherwise
uncovered. Negative results may be sufficient to justify stopping or pivoting.

The existing `evidence_sufficiency` JSON object is unchanged: `status` holds the
rating; `analysis` names the decision, cites decisive supplied evidence, and explains
the passing gates or the blocking gap and smallest next evidence step. Sufficiency
for a bounded pilot does not establish readiness to scale or investment merit.

This is a prompt-level decision policy, not independent evidence verification or
a deterministic enforcement mechanism. The schema validates structure and enum
values, not the truth of a model's assessment. The retained mock provider continues
to use its separate bounded documentation rubric. Prompt-delivery tests exercise
all stages without paid provider calls; live calibration is still needed to measure
how consistently each model applies the policy.
