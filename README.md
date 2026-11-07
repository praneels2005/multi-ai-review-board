# Multiple AI Review Board

A full-stack multi-agent prototype for structured startup feedback. Users submit an idea and evidence, inspect a bespoke panel, and run independent specialist reviews, a bounded challenge-and-response debate, and coordinator synthesis. The report records priorities, unresolved concerns, evidence limitations, and proposed validation experiments.

Built with **FastAPI**, **React 19**, **TypeScript**, and a shared provider interface supporting a deterministic offline mock, OpenAI, and Google Gemini. AI recommendations are decision support, not validated market or clinical findings.

## Architecture & System Design

```text
React + Vite
  Idea / evidence / presets -> editable specialist panel / providers / budget
                                |
                            FastAPI API
                                |
  Panel generation (separate from the review-run budget)
                                |
  Identified run -> independent specialist reviews
                                |
                   bounded challenge / response
                                |
                   coordinator synthesis (mock)
                                |
                   atomic JSON session checkpoints
                                |
  Saved Reviews / GET snapshots / sequenced SSE -> browser recovery
```

- **Panel generation:** generates 3–5 specialists with roles, expertise, mandates, and rationales; users can inspect and edit the panel before execution.
- **Independent reviews:** each specialist sees the idea and supplied evidence, without peer reviews. Outputs include strengths, risks, missing assumptions, questions, evidence citations, assumptions/unknowns, and a validation experiment with a hypothesis, test design, and success metric.
- **Bounded debate:** one challenge-and-response round, with up to two exchanges for four or five successfully completed specialist reviews, one for two or three, and none for fewer than two. Failures and budget limits can reduce or prevent exchanges. Challenges use actual findings; complementary risks are not automatically disagreements or consensus.
- **Coordinator synthesis:** combines available reviews and exchanges into priorities, disagreements, experiments, evidence sufficiency, and failure impact when applicable. The current coordinator always uses the **mock adapter**, including when specialists use live providers. Output provenance identifies this.
- **Persistence:** saved sessions retain findings, exchanges, synthesis, configuration, lineage, and execution accounting under `data/saved_reviews/`.

Implementation: [orchestrator](app/services/review_orchestrator.py), [response contracts](app/schemas/review_board_schema.py), [run ownership](app/services/review_runs.py), and [session storage](app/services/session_store.py).

## Offline Specialist Panel Selection

The deterministic mock uses a shared [library of 18 specialist archetypes](app/models/connectors/mock_archetypes.py), each with explicit trigger terms, a role, expertise, a mandate template, and a review perspective covering risks, assumptions, questions, and validation experiments. The library includes the original developer-tool, refill-commerce, and sleep-hardware perspectives plus financial controls, learning outcomes, carbon-credit integrity, dental operations, agriculture, privacy, and document retrieval.

Panel selection uses structured idea fields and case-insensitive **whole-word matching** (`\bterm\b`), including bounded phrases. For example, `capital` and `rapid` do not match `api`, and `healthy` does not match `health`. Explicit variants are listed in the library; there is no stemming or semantic classification.

| Idea field | Weight per distinct matching trigger in that field |
| --- | ---: |
| Title | 4 |
| Proposed solution | 4 |
| Idea description | 2 |
| Problem | 2 |
| Target customer | 1 |

An archetype must match **at least two distinct trigger terms**, including **at least one domain anchor**, to qualify. The anchor gate prevents supporting terms such as `practice` and `claims` from selecting a dental specialist for a legal-service idea. Repeating one term cannot satisfy the two-term threshold or inflate its score within a field. Supplied evidence does not select panel archetypes or alter these field weights.

Up to five highest-scoring qualifying archetypes are selected, with deterministic ties and canonical presentation order. If fewer than three qualify, generic customer-discovery, delivery-feasibility, and commercial-viability roles pad the panel to three as needed. Their rationales carry **`[EXPLICIT MOCK FALLBACK]`**; qualifying roles show **`[MOCK KEYWORD MATCH: …]`** with matched terms and scores. These labels describe bounded lexical matching, not calibrated confidence or independently established expertise.

Specialist feedback uses the same whole-word matcher. Mandate matches take priority over role and expertise, so a substantive mandate edit can change the risks, questions, and experiment. Non-preset regressions cover fintech, edtech, carbon credits, dental SaaS, and agriculture, including substantively different assessments. Unknown domains receive explicit generic fallbacks rather than fabricated specialist knowledge.

## Provider Abstraction & Evidence Handling

The shared connector interface uses explicit task identifiers for panel generation, specialist review, challenge generation, challenge response, and coordinator synthesis. User-entered keywords cannot select an operation. Responses undergo JSON parsing and task-specific schema validation; malformed or incomplete output is recorded as failure rather than filled with fabricated assessments. Panel generation has an explicit fallback panel; coordinator failure produces explicitly marked fallback guidance.

| Provider key | UI/default model name | Behavior |
| --- | --- | --- |
| `mock` | `mock-deterministic` | Deterministic, bounded offline reasoning and simulated usage; no API key required. |
| `openai` | `gpt-4o-mini` | Asynchronous OpenAI adapter; requires a backend key. |
| `gemini` | `gemini-1.5-flash` | Native asynchronous Google GenAI adapter; requires a backend key. |

These are names configured in the source, **not verified statements of current live model availability**. Specialist model names are editable; provider switching updates provider and model together. Gemini's settings fallback is `gemini-3.5-flash-lite` when no explicit model is supplied; normal UI selection supplies its own model. Cost estimates use a local pricing table and are not authoritative billing quotes. The UI labels dollar amounts as **Est. cost**. Run totals expose reported, estimated, and simulated token counts when available; older saved sessions without the breakdown show that the usage source is unavailable. Specialist cards label mock tokens as simulated and live-provider tokens as reported/estimated because that per-card contract does not preserve exact usage provenance.

Mock specialist feedback uses role, expertise, mandate, startup context, and actual supplied evidence text. Bounded rules distinguish domain risks and experiments and respond to supported evidence mutations, such as an unfavorable CPU-overhead measurement. This is not a general-purpose semantic inference engine.

Evidence citations reference supplied IDs such as `E1`, `E2`, or arbitrary IDs. IDs are normalized for matching; unsupplied citations are flagged in `invalid_citations`. **Matching an ID does not independently verify its underlying claim.** Evidence items are supplied reports, not proof of validation. Missing evidence produces explicit uncertainty; experiments are proposals, not completed results.

The schema allows evidence sufficiency `sufficient`, `thin`, or `insufficient`. The current mock conservatively returns `thin` for supplied reports and `insufficient` when none are supplied; item counts or source labels do not earn a `sufficient` rating.

## Walkthrough & Demo Scenarios

Select a Walkthrough Preset, choose **Deterministic Mock** for panel generation, generate the panel, confirm every specialist uses `mock` / `mock-deterministic`, and run the review. Use a budget sufficient for the whole workflow: **20 calls and 50,000 tokens** are used by the offline verifier. Panel generation is outside that run budget.

### DevPulse — Developer Tool / Infrastructure

- **Concept:** eBPF tracing/APM for Kubernetes, claiming low overhead and zero application instrumentation.
- **Supplied reports:** `[E1]` a synthetic 50-node benchmark reporting 1.18% CPU overhead at 25,000 requests/second; `[E2]` 12 discovery interviews reporting observability cost concerns. These reports are not independently verified.
- **Panel:** developer experience, cloud infrastructure/kernel systems, DevSecOps/compliance, and open-core GTM.
- **Review focus:** onboarding friction, kernel compatibility/runtime overhead, telemetry security, and budget-holder commitment. Debate compares these actual findings; it does not invent opposing positions. A supplied benchmark does not establish production safety or willingness to pay.

### GlowGreen — Consumer D2C / Sustainability

- **Concept:** refillable skincare subscriptions using returnable aluminum packaging.
- **Supplied reports:** `[E1]` an ad test reporting 540 waitlist emails at $2.22 blended acquisition cost; `[E2]` an Austin pilot reporting a 42% container return rate among 50 participants over 60 days.
- **Panel:** reverse logistics, customer retention, cosmetic safety/compliance, and unit economics.
- **Review focus:** return friction, paid renewals, microbial safety, and contribution margin after freight/cleaning. Waitlist acquisition does not prove repeat purchase, and a reported return rate does not establish profitable reuse.

### QuantumSleep — Thin Evidence / Neurotech Hardware

- **Concept:** an acoustic sleep pillow making insomnia-treatment claims.
- **Supplied report:** `[E1]` a founder's 14-night diary reporting sleep onset of 12 rather than 45 minutes: an uncontrolled, single-person anecdote.
- **Panel:** sleep medicine, hardware/ergonomics, and health-claims regulation.
- **Review focus:** confounding and clinical evidence gaps, comfort/durability, and therapeutic claims outrunning evidence. The mock labels supplied evidence `thin` and explicitly insufficient to establish clinical efficacy. Controlled studies are proposed, not claimed to have occurred.

### Failure Simulation & Saved Reviews

The Panel Inspector offers **Simulate Timeout** and **Simulate Connection Error**. Affected reviews record failure or timeout while available results remain usable. Failure impact is conditional; successful specialists alone do not trigger a failure warning. Budget exhaustion can also stop later phases.

Open **Saved Reviews** to inspect a stored session. **Rerun Review** explicitly creates a new child run from the saved parent with recorded lineage; it does not restart the parent's identifier. See the [manual demo runbook](docs/LOCAL_DEMO_RUNBOOK.md) for exact controls and expected pass/fail behavior.

## Execution Reliability & Recovery

These guarantees apply to cooperating processes in the existing **file-based, single-node POSIX execution model**, while identifiers and saved files are retained. They do not establish exactly-once remote execution or billing.

### Idempotent Execution

Clients use a stable `session_id` or `Idempotency-Key`; if both are supplied they must match. The backend computes a SHA-256 fingerprint of the normalized idea, ordered panel, budget configuration, and rerun parent. Repeating an identifier with matching parameters attaches to the existing run. Different parameters return HTTP **409 Conflict**.

Nonblocking POSIX `flock` execution claims prevent cooperating workers sharing the session directory from dispatching the same run concurrently. The initial checkpoint is saved before provider work is scheduled, and the execution owner retains the lock. Completed or interrupted identifiers are not implicitly restarted: request a new identifier for a new run or explicitly rerun into a new child session.

### Stream Recovery

| Endpoint | Purpose |
| --- | --- |
| `POST /api/review-board/runs` | Start or attach to an identified run; returns HTTP 202 and session state. |
| `GET /api/review-board/sessions/{id}` | Retrieve saved state without provider execution. |
| `GET /api/review-board/sessions/{id}/events` | Subscribe to sequenced SSE snapshots without starting execution; supports `after` and `Last-Event-ID` cursors. |
| `POST /api/review-board/sessions/{id}/rerun` | Explicitly create or attach to an identified child rerun. |

Compatibility routes `/api/review-board/run` and `/api/review-board/run-stream` remain available.

Execution is owned by a server task, so browser refreshes and disconnected HTTP streams do not cancel it. The frontend remembers the active identifier and recovers existing state through GET requests. Broken streams fall back to snapshot polling rather than another provider workflow. If full network loss also breaks polling, the observer may stop with an error; restore connectivity and refresh/reopen the session. Automatic resubscription on a browser Online event is not implemented.

Local browser checks on November 7, 2026 passed for all three presets, saved reopening, explicit reruns, simulated failures, budget stops, active-run refresh, and two-tab recovery. A recorded follow-up also verified stream-only blocking with snapshot polling and an offline interval followed by saved-review reopening. Abrupt backend restart was attempted but blocked by the execution sandbox; see the [runbook worksheet](docs/LOCAL_DEMO_RUNBOOK.md#acceptance-worksheet). Default preset initialization is skipped when a remembered run is being recovered, so a late preset response does not clear restored state. Regression tests exercise both preset/recovery response orders through the application hook harness; browser refresh passed in the recorded controlled-timeout scenario.

### Persistence & Interrupted Runs

Session checkpoints are written to temporary files in the session directory, flushed, `fsync`ed, and atomically replaced with `os.replace`. They preserve completed specialist findings, debate exchanges, coordinator output when available, and the last durable budget ledger. Accounting is checkpointed before provider dispatch.

If an in-progress session no longer has an execution owner, retrieval conservatively represents it as `partial_failure` when findings exist, otherwise `failed`, with interruption metadata. GET recovery can project this state without rewriting the raw JSON. Outstanding usage remains uncertain rather than being erased. No interrupted remote provider operation is automatically resumed. Atomic replacement applies per file; rerun lineage updates are not a multi-file transaction.

### Budgets, Retries, Timeouts & Partial Results

- An `asyncio.Lock` synchronizes reservation and settlement of call/token budgets. Settled usage plus in-flight reservations prevents application-level oversubscription before dispatch.
- Input estimates and configured output allowances reserve capacity. Actual usage can exceed estimates; overruns are reported accurately, not silently capped, and block subsequent dispatch. Usage is labeled reported, estimated, or simulated; unknown failed-call usage retains conservative accounting.
- Each specialist has at most one retry, subject to configuration, remaining budget, and explicit retryability. Timeouts and ambiguous remote completion are not automatically retried. SDK retries are disabled/bounded so attempts remain visible to application accounting.
- Local await deadlines request cancellation but cannot prove a remote provider stopped or refunded a request. Pending SDK work is guarded against overlapping reuse. The timeout implementation is not a blanket `asyncio.wait_for` guarantee.
- Failed specialists do not erase completed reviews. Debate participation and synthesis depend on available findings and budget. Coordinator failures are explicitly marked; fallback guidance is not represented as successful provider reasoning.

## Security & Design Trade-offs

Structured input delimiters such as `<user_startup_data>` and explicit role/mandate framing treat startup text as evaluation data. These are prompt-injection mitigations, not immunity. Live keys are configured on the backend; adapters redact configured keys from error details. This is not a guarantee that arbitrary sensitive input cannot appear in output or logs.

Independent reviews reduce immediate peer influence; bounded debate controls execution cost and avoids unbounded loops. Coordinator synthesis preserves complementary concerns and recognized disagreements rather than treating agent agreement as proof. The deterministic mock makes offline regressions reproducible but relies on bounded rules. Editable panels allow human oversight. File checkpoints keep local operation simple, at the cost of distributed execution and database transaction guarantees.

## Installation & Usage

### Prerequisites

- Python **3.12+**; the reported verification used **3.14.2**. Backend requirements are unpinned, so fresh dependency resolution can differ from the tested environment.
- Node.js **20.19+ within 20.x, or 22.12+**, matching the installed Vite engine range; tested with Node **22.22.0** and npm **10.9.4**.
- A POSIX environment supporting `fcntl.flock`, such as macOS or Linux.

### Backend — From Repository Root

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

API: `http://localhost:8000`; interactive docs: `http://localhost:8000/docs`; health: `http://localhost:8000/health`.

### Frontend — Separate Terminal, Starting at Repository Root

```bash
cd frontend && npm ci
npm run dev
```

Open `http://localhost:5173`. Keep the same frontend origin across tabs so active-run browser storage is shared. The frontend calls `http://localhost:8000`.

### Deterministic Mock & Optional Live Providers

No paid keys are needed for the review-board mock. Choose **Deterministic Mock** for panel generation and each specialist; use `mock-deterministic` and disable failure simulation for baseline runs. Do not set the legacy `LLM_PROVIDER=mock`: that separate legacy setting does not accept `mock`.

For optional live specialists, set backend environment variables privately before starting the backend, then select the corresponding provider/model in the UI:

```bash
# Placeholders only: supply your own values privately.

export OPENAI_API_KEY='<your-openai-key>'
export GEMINI_API_KEY='<your-gemini-key>'
python -m uvicorn app.main:app --reload
```

Backend settings also load `.env`; keep secrets out of version control and frontend variables. Real provider execution and current model availability have not been established by the offline checks. Coordinator synthesis remains mock.

The [local demo runbook](docs/LOCAL_DEMO_RUNBOOK.md) uses additional precautions for controlled interruption testing: explicitly blank keys, avoid `--reload`, record the process PID, and keep ports/origins stable. Follow it for refresh, stream interruption, two tabs, reruns, failure simulation, budget exhaustion, and interrupted-run inspection.

## Testing & Verification

**Reported automated results — November 7, 2026**, application commit `b7ed1e8f1cd96b8737596c892541460418825301`. The backend count comes from a fresh `python -m pytest -q` run: **335 passed, 2 warnings in 84.41 seconds**.

| Check | Reported result (2026-11-07, `b7ed1e8`) |
| --- | --- |
| Backend pytest suite | **335 passed**; two existing third-party deprecation warnings. |
| Frontend regression tests | **11 passed**. |
| Deterministic offline demo behavioral checks | **53/53 passed** across DevPulse, GlowGreen, and QuantumSleep. |
| TypeScript check | Passed. |
| Vite production build | Passed. |

The backend suite includes **38 archetype regressions** covering substring collisions, five non-preset domains, weighted scoring, distinct-term thresholds, domain anchors, explicit generic padding, mandate sensitivity, and deterministic output. Frontend tests include both preset/recovery response orders, fresh default initialization, visible usage/cost labels, provider/model pairing, and stream recovery. Verification used the existing installed environment without paid provider calls; a fresh dependency installation was not tested.

Reproduce from the repository root with the virtual environment activated:

```bash
# Empty keys also prevent legacy test routes from selecting a paid client.

env OPENAI_API_KEY= GEMINI_API_KEY= ANTHROPIC_API_KEY= GROQ_API_KEY= XAI_API_KEY= SERPER_API_KEY= SERPAPI_API_KEY= \
  python -m pytest -q
env OPENAI_API_KEY= GEMINI_API_KEY= ANTHROPIC_API_KEY= GROQ_API_KEY= XAI_API_KEY= SERPER_API_KEY= SERPAPI_API_KEY= \
  python scripts/verify_offline_demo.py
```

The verifier creates a fresh artifact directory under `data/saved_reviews/demo-verification/` and does not require running frontend/backend servers. In a separate terminal from the repository root, after `npm ci`:

```bash
cd frontend
node --test tests/*.test.cjs
npx tsc --noEmit
npm run build
```

**Browser acceptance is partially verified as of November 7, 2026: 12 worksheet scenarios were observed passing (including the documented offline/reopen variant), and abrupt backend restart was blocked; final acceptance still requires reviewer confirmation.** See the [runbook acceptance worksheet](docs/LOCAL_DEMO_RUNBOOK.md#acceptance-worksheet) for session IDs and remaining checks. Frontend regression tests use a helper harness, not a real browser acceptance run. These results do not establish paid-provider execution/billing, scientific validity, clinical efficacy, or unrestricted semantic correctness.

## Limitations

- File-based storage and POSIX locking assume cooperating processes on reliable local storage. There is no distributed/multi-host execution guarantee.
- Interrupted provider operations are not resumed automatically. Remote completion/cancellation may be unknown; there is no exactly-once remote execution or billing guarantee.
- Sessions use an existing unauthenticated, application-wide namespace intended for **trusted local use**.
- Evidence is text supplied by the user; there is no independent external evidence verification. A valid citation or agreement between specialists is not proof.
- Mock behavior is deterministic and bounded. Its 18 archetypes require explicit whole-word triggers and a domain anchor; absent vocabulary, negation, or ambiguous context can still produce incomplete or inappropriate matches. Generic fallbacks disclose insufficient domain coverage. Role/evidence handling does not provide general semantic understanding. Recommendations and proposed experiments are decision support, not validated market or clinical findings.
- Live provider/model availability and fresh dependency installations were not validated by the reported offline tests. Browser checks and remaining acceptance gaps are recorded in the runbook; automated checks alone do not establish final manual acceptance.

## Technical & Research Sources

- Du, Y., Li, S., Torralba, A., Tenenbaum, J. B., & Mordatch, I. (2023). [Improving Factuality and Reasoning in Language Models through Multiagent Debate](https://arxiv.org/abs/2305.14325). Background for independent generation and bounded debate.
- Park, J. S., O'Brien, J. C., Cai, C. J., Morris, M. R., Liang, P., & Bernstein, M. S. (2023). [Generative Agents: Interactive Simulacra of Human Behavior](https://arxiv.org/abs/2304.03442). Background on agent design and simulation; not a direct validation of specialist startup evaluation.

These papers motivate design exploration. They do not prove that this particular implementation improves reasoning accuracy or reduces hallucinations.

## AI Coding Assistance

AI coding assistance contributed to scaffolding, typing, mock logic, tests, and documentation. Reported automated checks and partially completed browser acceptance are distinguished above; no claim of comprehensive independent verification is implied.
