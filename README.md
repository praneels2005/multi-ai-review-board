# Multiple AI Review Board

A full-stack multi-agent prototype where users submit startup ideas and receive structured, domain-specific feedback from a bespoke board of AI specialists. Specialists assess ideas independently, challenge one another's reasoning in a bounded debate round, and submit their findings to a coordinator agent that synthesizes priorities, exposes disagreements, evaluates evidence sufficiency, and recommends validation experiments.

Built with **FastAPI**, **React 19**, **TypeScript**, and an extensible **Shared Connector Interface** supporting deterministic offline simulation, OpenAI, and Google Gemini.

---

## Architecture & System Design

```
+-----------------------------------------------------------------------------------+
|                              Frontend (React 19 + Vite)                           |
|  - Idea & Evidence Input (E1, E2...)       - Walkthrough Presets (DevPulse, Glow) |
|  - Panel Inspector & Provider Switcher     - Budget & Failure Simulation Controls |
|  - Multi-Stage Execution Tracker           - Saved Reviews Reopening & Rerun      |
+-----------------------------------------------------------------------------------+
                                        | (REST API)
+-----------------------------------------------------------------------------------+
|                           Backend (FastAPI Orchestrator)                          |
+-----------------------------------------------------------------------------------+
  |
  +--> [1. Panel Generator]
  |      Inspects problem, customer, solution & evidence.
  |      Dynamically generates 3-5 domain-specific specialist agents with mandates.
  |
  +--> [2. Shared Connector Interface & Adapters]
  |      - Deterministic Mock Adapter (Zero API keys required, latency & token simulation)
  |      - OpenAI Adapter (AsyncOpenAI, GPT-4o-mini, GPT-4o)
  |      - Google Gemini Adapter (google-genai SDK, Gemini-1.5-Flash, Gemini-2.0-Flash)
  |      - Unified structured response contract across providers
  |      - Server-side key protection & prompt injection data containment
  |
  +--> [3. Phase 1: Independent Specialist Reviews]
  |      - Specialists evaluate in isolation (no seeing peer reviews)
  |      - Strengths, risks, missing assumptions, probing questions, experiments
  |      - Cites verified evidence IDs; validates & flags fabricated citations
  |      - Per-agent timeout enforcement & max 1 retry on transient failure
  |      - Failure isolation: failing agents do not crash the board
  |
  +--> [4. Phase 2: Bounded Challenge & Response Debate]
  |      - Exactly 1 bounded cross-examination round
  |      - Specialists challenge contested assumptions; targets defend or adjust logic
  |
  +--> [5. Phase 3: Coordinator Synthesis]
  |      - Aggregates findings into decision-support report
  |      - Top strategic priorities & key specialist disagreements
  |      - Ranked concrete validation experiments
  |      - Objective Evidence Sufficiency rating ("sufficient", "thin", "insufficient")
  |      - Specialist Failure Impact Analysis (if any agent timed out or failed)
  |      - Mandatory disclaimer: Decision support only; consensus != proof of demand
  |
  +--> [6. Persistence & Session Store]
         - Saves sessions to disk (`data/saved_reviews/`)
         - Reopen any historical review or rerun with 1 click
```

---

## Walkthrough & Demo Scenarios

The application includes 3 built-in curated presets accessible directly from the UI or API:

### 1. Contrasting Idea A: DevPulse (Developer Tool / Infrastructure)
- **Concept:** Kernel-level eBPF continuous distributed tracing & APM for Kubernetes with sub-1.5% CPU overhead and zero code instrumentation.
- **Evidence:** 
  - `[E1]` Synthetic 50-node benchmark recording 1.18% CPU overhead under 25,000 req/sec load.
  - `[E2]` 12 customer discovery interviews with platform engineering leads confirming Datadog cost fatigue.
- **Generated Panel:** Developer Experience Specialist, Cloud Infrastructure & Kernel Systems Architect, DevSecOps & Enterprise Compliance Auditor, Open-Core GTM Strategist.
- **Debate Focus:** Tension between 1-click CLI developer experience vs root/CAP_BPF host privileges required by enterprise security.

### 2. Contrasting Idea B: GlowGreen (Consumer D2C / Sustainability)
- **Concept:** Closed-loop refillable skincare subscription in weighted aluminum bottles with prepaid return mailers for industrial cleaning and reuse.
- **Evidence:**
  - `[E1]` Meta/TikTok paid ad test acquiring 540 waitlist emails at $2.22 blended CPA.
  - `[E2]` 50-person Austin pilot showing a 42% physical container return rate over 60 days.
- **Generated Panel:** Sustainable Supply Chain & Reverse Logistics Specialist, D2C Retention & Customer Lifecycle Strategist, Cosmetic Formulation & FDA Regulatory Compliance Officer, Unit Economics Analyst.
- **Debate Focus:** Reverse logistics freight and cleaning costs vs unit margin, and batch-return loops vs single-bottle returns.

### 3. Thin-Evidence Case: QuantumSleep (Consumer Hardware / Neurotech)
- **Concept:** Acoustic bone-conduction sleep pillow claiming to cure chronic insomnia using binaural delta-wave entrainment.
- **Evidence:**
  - `[E1]` Founder personal diary reporting falling asleep in 12 minutes rather than 45 minutes across 14 nights (n=1 anecdote).
- **Behavior:** The Review Board identifies severe lack of empirical proof. The Coordinator explicitly marks Evidence Sufficiency as **"thin"**, labels heavy unverified assumptions, and mandates randomized sham-controlled polysomnography trials before commercial claims.

### 4. Provider Failure & Resilience Demo
- In the Panel Inspector, select **"Simulate Timeout"** or **"Simulate Connection Error"** on any specialist.
- **Result:** The review board isolates the error, marks the specialist as `failed` or `timed_out` with an explicit red alert banner, and proceeds with the remaining agents.
- The **Coordinator** prominently includes a **Failure Impact Analysis**, explaining how the absence of that perspective degrades confidence in that specific technical domain.

### 5. Reopening & Rerunning Saved Reviews
- Open the **"Saved Reviews"** drawer to inspect past runs. Click any run to restore its idea, panel configuration, discussion, and coordinator synthesis. Click **"Rerun Review"** to re-evaluate with current settings.

---

## Usability, Reliability & Security Controls

1. **Zero-API-Key Operation:** Fully functional out-of-the-box using the deterministic mock adapter with realistic latency and token generation. Live OpenAI and Gemini adapters can be toggled without code modifications.
2. **Provider Separation:** Specialist domain roles are strictly decoupled from underlying AI models.
3. **Structured Response Contract:** Every provider response is validated and normalized into consistent Pydantic models.
4. **Timeouts & Retry Bounds:** Every LLM call is bound by a configurable timeout (`asyncio.wait_for`) with at most **one retry** on transient failure.
5. **Budget Stops:** Configurable hard call cap and token cap halts execution immediately if limits are reached.
6. **Citation Verification:** Extracted evidence citations are checked against supplied evidence IDs. Any hallucinated citation (e.g. `E99`) is separated and flagged under `invalid_citations`.
7. **Prompt Injection Protection:** User input text is treated strictly as passive evaluation data, wrapped in `<user_startup_data>` XML delimiters with explicit instructions forbidding instruction override.
8. **Server-Side Key Hygiene:** API keys are never exposed to the frontend or written to logs.

---

## Technical & Research Sources

1. **Multi-Agent Debate for Reasoning & Hallucination Reduction**  
   *Du, Y., Li, S., Torralba, A., Tenenbaum, J. B., & Mordatch, I. (2023). "Improving Factuality and Reasoning in Language Models through Multi-Agent Debate." arXiv:2305.14325.*  
   *Application in Project:* Demonstrates that independent generation followed by bounded debate rounds significantly reduces single-model cognitive bias, blind spots, and hallucinations compared to single-agent reflection. Our Phase 1 (independent evaluation) and Phase 2 (bounded challenge round) directly mirror this finding.

2. **Persona-Conditioned Evaluation & Agent Specialization**  
   *Park, J. S., O'Brien, J. C., Cai, C. J., Morris, M. R., Liang, P., & Bernstein, M. S. (2023). "Generative Agents: Interactive Simulacra of Human Behavior." arXiv:2304.03442.*  
   *Application in Project:* Informs how domain-specific persona conditioning, explicit mandates, and separate coordinator synthesis prevent agents from collapsing into uniform generic consensus, ensuring contrasting startup ideas yield genuinely tailored perspectives.

---

## Trade-offs & Design Decisions

- **Independent Coordinator vs. Consensus Voting:** Rather than averaging agent opinions, we use an independent coordinator. Consensus among LLMs is often sycophantic; an independent coordinator explicitly records unresolved disagreements and insists that consensus is not proof of market demand.
- **Bounded Debate (1 Round):** We restrict cross-examination to exactly one bounded round. Multi-round open-ended debates create token explosion and circular arguments with diminishing informational returns.
- **Deterministic Mock Adapter:** Implemented a zero-dependency deterministic mock provider that produces domain-accurate responses for contrasting ideas, allowing complete CI/CD testing and offline demos without API quotas.
- **Client-Side Editing of Panels:** Allowing users to inspect and adjust the panel before running gives human operators oversight over AI agent composition.

---

## Limitations

- **Simulated vs. Real User Behavior:** AI review boards provide structured decision support and uncover blind spots, but they do not replace direct customer interviews or willingness-to-pay transaction tests.
- **Textual Evidence Only:** Current evidence ingestion supports structured text, metrics, and interview quotes; direct multimodal verification of CAD designs or binary traces is not yet integrated.

---

## AI Coding Assistance

AI coding assistance was utilized during development for scaffold code generation, typing definitions, mock test data authoring, and test fixture assembly. All agent orchestration logic, citation validation algorithms, prompt defense wrappers, and test suites were verified and reviewed.

---

## Installation & How to Run

### 1. Prerequisites
- Python 3.12+
- Node.js 20+ and npm

### 2. Backend Setup
```bash
# From repository root
cd startup-validator

# Activate Python virtual environment
source venv/bin/activate  # or: python3 -m venv venv && source venv/bin/activate

# Install dependencies (already satisfied if using existing venv)
pip install -r requirements.txt

# Start FastAPI backend server
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```
- API Documentation (Swagger UI): `http://127.0.0.1:8000/docs`
- Health check: `http://127.0.0.1:8000/health`

### 3. Frontend Setup
```bash
# In a separate terminal
cd startup-validator/frontend

# Run development server
npm run dev
```
Open `http://localhost:5173` in your browser.

---

## Running Automated Tests

Run the full automated test suite covering all 6 core evaluation areas:
```bash
cd startup-validator
PYTHONPATH=. ./venv/bin/pytest tests/ -v
```

### Test Suite Coverage:
1. `tests/test_panel_structure.py`: Validates 3-5 specialists, required fields, and meaningful panel divergence across contrasting ideas.
2. `tests/test_provider_normalization.py`: Validates unified connector interface, cost calculators, API key sanitation, and prompt defense tags.
3. `tests/test_malformed_output.py`: Validates schema validation and error isolation on malformed JSON outputs.
4. `tests/test_invalid_citations.py`: Validates valid evidence ID recognition and flagging of hallucinated/unsupplied citations.
5. `tests/test_timeouts_and_retries.py`: Validates timeout limits and bounding to at most one retry.
6. `tests/test_budget_stops.py`: Validates call cap and token cap execution halts.
7. `tests/test_failure_isolation.py`: Validates board resilience when a specialist fails and coordinator impact reporting.
8. `tests/test_review_api.py`: Validates FastAPI review board endpoints (presets, panel generation, running, persistence, reopening, rerunning).
