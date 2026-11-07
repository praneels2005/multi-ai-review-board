# Deterministic mock demo — manual demo runbook

**Manual acceptance status: 12 worksheet scenarios observed passing in a local browser on November 7, 2026, including the documented offline/reopen variant; abrupt backend restart was blocked.** The acceptance worksheet below separates observed passes from scenarios still requiring verification. Automated results and their application baseline are recorded in the [root README](../README.md#testing--verification). Passing automated tests does not sign off browser behavior. Final acceptance still requires reviewer confirmation; these observations are not a complete acceptance sign-off.

## 1. Open the project and start the services

`<repo-root>` below means your local checkout of `multi-ai-review-board`; replace it with that directory. Run all backend commands from this directory so session storage resolves consistently. Use a terminal and your browser; no particular editor is required.

The automated application baseline is `b7ed1e8f1cd96b8737596c892541460418825301` on `fix/review-board-reliability`. Run `git status --short --branch` and `git rev-parse HEAD` to record the checkout being demonstrated. Later documentation-only commits do not change that tested application baseline.

### One-time setup

```bash
cd "<repo-root>"
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Fresh dependency installation was not performed for the recorded verification. Backend requirements are unpinned; use the README prerequisites and record resolved versions when reproducing.

### Terminal A — backend

```bash
cd "<repo-root>"
source .venv/bin/activate
printf 'Local demo backend PID: %s\n' "$$"
exec env OPENAI_API_KEY= GEMINI_API_KEY= ANTHROPIC_API_KEY= GROQ_API_KEY= XAI_API_KEY= SERPER_API_KEY= SERPAPI_API_KEY= \
  python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --log-level info
```

Keep the printed PID for the interrupted-process scenario. `exec` replaces this terminal's shell; after stopping the backend, open a new terminal and repeat these commands. Do not use `--reload` for this demo: code edits could interrupt a run and a reloader introduces an additional process.

No existing `.env` file is overwritten. The explicit empty environment values override keys loaded from `.env` for this process. A legacy startup message saying that no live LLM provider was initialized does not prevent review-board mock operation. Do not set `LLM_PROVIDER=mock`: that separate legacy setting does not accept `mock`; select mock through the review-board controls below.

### Terminal B — frontend

```bash
cd "<repo-root>/frontend"
npm ci
npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

Open `http://localhost:5173` in your browser. Use that **same origin** for every tab; do not mix `localhost` and `127.0.0.1` frontend URLs, since their browser storage differs. The frontend calls `http://localhost:8000`. Use a browser with DevTools network inspection and request blocking for the network scenarios.

### Terminal C — health and inspection

```bash
cd "<repo-root>"
source .venv/bin/activate
curl --fail --silent http://127.0.0.1:8000/health
```

**Expected UI:** the review board opens and its three Walkthrough Presets load. **Pass:** health returns `status: ok`, frontend loads, presets appear, and API requests target your local backend. **Fail:** blank screen, failed preset requests, CORS/connectivity errors, or either port silently switching to a different value. Inspect both terminals and browser Network/Console. Resolve startup problems before proceeding.

## 2. Mock configuration and common inspection

For each baseline preset:

1. Under **Generator Model**, choose **Deterministic Mock**.
2. Select the preset, then click **Generate 3–5 Specialist Panel**.
3. Inspect every specialist's provider: **Deterministic Mock**, model `mock-deterministic`. Leave **Simulate Failure** at its normal/no-failure option.
4. Open **Budget & Caps**. Set call cap **20**, token cap **50000**, per-call timeout **12**, maximum retries **0**. Click **Save Controls**.
5. Click **Run Review Board** once. This is explicit new-run intent. Use **Saved Reviews**, refresh, or GET recovery to inspect an existing review; do not click Run again as a reconnection strategy.

The API's default output reservation/limit is 4096 per call; there is no extra UI control required. Panel generation is a separate mock call outside the review-run budget. Displayed costs are simulated estimates, not paid charges.

Open browser DevTools **before** the recovery scenarios. Enable **Preserve log** in Network and Console. Inspect the `POST /api/review-board/runs` payload: it contains the stable `session_id`, idea, panel and budget. Record the ID from that request/response. While active, this console expression also returns it:

```javascript
localStorage.getItem('review-board-active-run')
```

The active key is cleared after terminal recovery; use Saved Reviews or the recorded ID afterward. React development mode may make extra **GET** subscriptions; that alone is not duplicate provider execution. Check the per-run ledger and outputs.

After recording an ID, inspect the API from Terminal C:

```bash
DEMO_SESSION_ID='paste-the-exact-session-id'
curl --fail --silent "http://127.0.0.1:8000/api/review-board/sessions/$DEMO_SESSION_ID" | python -m json.tool
```

Inspect its raw persisted checkpoint without changing it:

```bash
python - "$DEMO_SESSION_ID" <<'PY'
import json, sys
from pathlib import Path
s = json.loads((Path('data/saved_reviews') / (sys.argv[1] + '.json')).read_text())
print(json.dumps({
    'session_id': s['session_id'], 'status': s['status'],
    'run_metadata': s.get('run_metadata'), 'execution_summary': s['execution_summary'],
    'specialists': [(r['specialist_id'], r['role'], r['status']) for r in s['specialist_reviews']],
    'debate_count': len(s['challenge_round']),
    'coordinator_status': (s.get('combined_review') or {}).get('status'),
}, indent=2))
PY
```

Never edit/delete an active checkpoint or its `.lock` file to reset a demo. Use a new explicit run identity when you want new work.

## 3. Baseline preset scenarios

Run all three independently using the common configuration. Switching presets resets the current panel, so generate a new panel for each.

### DevPulse

**Actions:** choose the DevPulse preset and execute it. Open **Specialist Feedback**, **Cross-Agent Debate**, then **Coordinator Synthesis**.

**Expected UI:** four successful, simulated specialists. Developer Experience discusses installation/configuration and unaided setup; Infrastructure discusses overhead/kernel compatibility and paired benchmarks; DevSecOps discusses privileges/telemetry leakage; GTM discusses budget-holder commitment. Each has a different validation intervention. The two debates quote actual reviews and tests. Coordinator priorities retain the four domains, with four exact specialist experiments.

**Pass:** `completed`; 4 unique specialist results; 2 exchanges; 9 run attempts; mock provenance; evidence `thin` with limitations; no specialist failure warning. The supplied 1.18% figure is attributed as a report below the stated ceiling, with repeatability unverified. An empty disagreement list is valid.

**Fail:** interchangeable assessments/experiments, invented specialist positions, generic invented experiments, unsupported consensus, hidden live execution, or lost saved results. Inspect the recorded session JSON, experiment objects and `provider_attempts`.

### GlowGreen

**Actions:** choose GlowGreen, regenerate the mock panel, execute, and inspect the same three result tabs.

**Expected UI:** distinct logistics, retention, formula/refill safety, and unit-economics concerns. Waitlist signups are not treated as paid retention. The supplied 42% return report remains attributed; it is not a newly invented outcome. Debate links the actual operational and validation concerns; coordinator retains the four experiments.

**Pass:** `completed`; 4 unique reviews; 2 exchanges; 9 run attempts; evidence `thin`; no failure warning. No fabricated postage, batch-return savings, guaranteed margins, or manufactured agreement.

**Fail:** waitlist signups presented as validated purchases, invented test results/costs, repeated generic assessments, or mismatched saved output. Inspect supplied evidence against review/combined text and compare all experiment fields.

### QuantumSleep

**Actions:** select QuantumSleep, regenerate the mock panel, execute, and inspect all result tabs plus evidence sufficiency.

**Expected UI:** clinical evidence, hardware durability/comfort, and health-claim substantiation are separate concerns. The founder diary is insufficient to establish clinical efficacy, causality or safety. Controlled study, hardware testing and a claim audit are **proposals**, not completed findings.

**Pass:** `completed`; 3 unique reviews; 1 exchange; 6 run attempts; evidence `thin` with explicit clinical limitations; no failure warning. No claimed scientific validation, regulatory approval, invented trial results, or invented clinical funding plan.

**Fail:** the diary proves efficacy, a proposed experiment appears as a result, or unsupported medical claims become coordinator facts. Inspect `evidence_sufficiency.analysis`, unknowns and proposed experiments in saved JSON.

For any completed preset, open **Saved Reviews**, choose the same ID, and confirm the same outputs return without a new `POST /runs`. A browser refresh after completion does not promise automatic restoration of the last completed view; use Saved Reviews when the active-run key has already been cleared.

## 4. Refresh during an active review

Normal mock runs take only about 1–2 seconds. Use the existing failure simulator to create an observable window; do not add sleeps or change product code.

**Actions:** choose DevPulse; generate its mock panel. Set timeout **30 seconds**, retries **0**, call cap 20, token cap 50000. On the **fourth specialist**, choose **Simulate Timeout**. Start once. Wait for at least one successful specialist checkpoint, confirm API status `in_progress`, record the ID, then refresh the page before 30 seconds elapse.

**Expected UI:** recovery reads the existing ID and restores partial results/progress. The intentional timeout eventually produces a `partial_failure`, preserving the other three specialists, one exchange and coordinator output. The timeout domain is identified in failure-impact analysis.

**Pass:** the same session ID before/after refresh; no new `POST /runs` from the refresh; 7 total run attempts with these settings; no repeated specialist results; one original ledger throughout. Calls may naturally increase as the **same** run finishes; they need not freeze at the pre-refresh count.

**Fail:** refresh initiates a new run, resets the ledger, loses completed results, or reports the timed-out specialist as successful. Inspect Network, saved JSON and `run_metadata`.

**Specific manual check:** preset loading must not replace a recovered idea, panel or session. The current implementation skips automatic default-preset application when recovering a remembered run. Regression tests cover both response orders through a hook harness; check the actual restored browser view as well. Record a failure if the view resets even when backend results remain intact.

## 5. Stream interruption and reconnection

### Stream-only failure with automatic polling

**Actions:** restore the controlled 30-second DevPulse scenario. In browser DevTools request blocking, block only this pattern **before starting**:

```text
*/api/review-board/sessions/*/events*
```

Leave `POST /runs` and `GET /sessions/{id}` unblocked. Start once and record the ID. Some tools do not terminate an already-open SSE request when blocking is enabled, hence setting the rule first. Remove the rule after this scenario.

**Expected UI:** the event-stream request fails, and the helper polls GET status/results for the same run. The run completes with the intended partial failure. There is no fallback POST `/run` or a second POST `/runs`.

**Pass:** one start request, only GET recovery traffic, the same ID/ledger and the expected 7 attempts. **Fail:** another execution POST, duplicate results, or lost terminal state despite successful status reads. Inspect Network and saved results.

### Full offline interval

**Actions:** start another controlled run, record its ID, set DevTools network mode to Offline briefly, then restore Online and refresh using the same browser origin.

**Expected UI:** if status reads also fail, the current observer can show an error and stop. The unresolved ID stays remembered. The refresh after returning online recovers it through GET; the server kept executing.

**Pass:** recovery preserves the run, with no new execution POST. **Fail:** a replacement run or ledger reset. **Do not require automatic resubscription merely by changing Offline back to Online**; full-network-outage recovery currently requires refresh/reopen if polling already failed.

## 6. Same active/completed review in two tabs

**Actions:** start the controlled long run in tab A. Record the ID. While active, open tab B at exactly `http://localhost:5173` in the same browser profile. Both tabs share the remembered active ID. After completion, alternatively use Saved Reviews in both tabs to select that same ID.

**Expected UI:** both tabs display the same persisted run; tab B only reads/subscribes. One tab's disconnection does not cancel execution. For a completed run, reopening is GET-only.

**Pass:** identical session IDs, outputs and final ledger in both tabs; a single start across the two tabs; no duplicate provider attempts. **Fail:** tab B starts a workflow or its results use a different ID. Inspect Network in both tabs and the common saved JSON. Do not click Run Review Board in tab B to attach; that button explicitly requests a new run. Also check the restored idea and panel as described in scenario 4.

## 7. Explicitly rerun a completed review

**Actions:** restore normal controls and no failure injections. Execute or reopen a completed baseline preset. Click **Rerun Review** once. Inspect the new result, then reopen the parent through Saved Reviews.

**Expected UI:** a genuinely new session ID and independent ledger, version increased, `rerun_of_session_id` pointing to the parent. The parent's findings/ledger remain intact, and its `rerun_history` contains the child once. Recovery of an ambiguous rerun response uses the same child key rather than repeating the operation.

**Pass:** exactly one new workflow with the preset's expected call count and correct lineage. **Fail:** parent overwritten, repeated child entries, old ID reused as new execution, or missing original findings. Inspect both session JSON files. Existing rerun semantics use the parent's stored idea/panel; editing an unrelated panel on screen does not change a saved parent's rerun configuration.

## 8. Simulate a provider failure

**Actions:** choose DevPulse and regenerate the panel. All providers remain mock. Set retries **0**, timeout **12**, normal budget. On the infrastructure specialist choose **Simulate Connection Error**; run once.

**Expected UI:** a failed specialist banner with an explicit simulated provider error. Three successful specialists keep their real findings; the failed specialist has no invented experiment. Coordinator output identifies the omitted infrastructure domain and degraded confidence. Session status is `partial_failure`.

**Pass:** 7 run attempts with retries 0, exactly three successful reviews, failed-domain warning, three surviving specialist experiments and saved partial results. **Fail:** a successful-looking failed specialist, generic invented fallback findings, missing successful outputs, or an unrelated failure warning. Inspect failed `error_message`, empty findings, combined review and ledger. Optional: set retries 1 for the safe simulated connection error; one extra attempt is allowed, not unlimited retries. Restore the failure dropdown afterward.

## 9. Deliberately exhaust the token budget

**Actions:** regenerate DevPulse with no failures. Set token cap **1000**, call cap 20, timeout 12 and retries 0. Click Run once.

**Expected UI:** status `budget_stopped`, no coordinator synthesis and no successful specialist findings. The default 4096 output reservation cannot fit, so no review provider attempt is dispatched. A budget-stop specialist card may appear; that is not a provider outage. The generic empty synthesis panel must not be mistaken for a completed review.

**Pass:** run `calls_made: 0`, `total_tokens: 0`, `reserved_tokens: 0`, `budget_stopped: true`; saved terminal state is retrievable; no fabricated review/experiment. Panel generation already occurred separately and is outside this ledger. **Fail:** successful synthesis, hidden fallback workflow, charged review calls despite the rejected reservation, or cleared prior results from a different saved run. Inspect saved `execution_summary` and budget-stop error text. Restore token cap **50000** afterward.

Optional partial-completion boundary: call cap **2**, token cap 50000; expect two specialist calls/results then `budget_stopped`. This supplements rather than replaces the token-cap test.

## 10. Saved sessions and side-effect-free reads

**Actions:** use Saved Reviews to reopen a completed, partial-failure and budget-stopped session. Inspect each with the GET/file commands from section 2. Reopen the same completed session twice without clicking rerun.

**Expected UI:** original statuses/results/ledger are retained. **Pass:** reads do not add calls, experiments, exchanges or session IDs; completed and budget-stopped runs stay in their respective terminal states. **Fail:** a read dispatches work, mutates the ledger or reports incomplete work as completed. Use raw file checksums/mtime only when the run is terminal and no other tab is updating lineage; an active worker legitimately writes checkpoints.

## 11. Abrupt process interruption and conservative restart

This scenario deliberately stops **only the local demo backend**. Do not use it against an unrelated server. Record the PID printed by Terminal A and verify it is that demo process.

**Actions:** start the controlled 30-second DevPulse run from scenario 4. Confirm the saved checkpoint contains at least one successful review and an in-flight attempt/reservation. Copy its ID and ledger. In Terminal C:

```bash
DEMO_BACKEND_PID='paste-the-PID-printed-by-Terminal-A'
ps -p "$DEMO_BACKEND_PID" -o pid=,command=
# Proceed only if this is your local uvicorn demo process.
kill -KILL "$DEMO_BACKEND_PID"
```

Restart Terminal A with the same working directory/storage and empty-key startup command. Restore connectivity, then refresh/reopen the **recorded review**. Do not press Run or Rerun to recover it.

**Expected UI/API:** the interrupted review is conservatively `partial_failure` because completed outputs were saved; it is `failed` if no stage output had been saved. `run_metadata.interrupted` explains that dispatched calls are not resumed. Existing reviews and the last durable ledger remain. No provider workflow restarts automatically.

**Pass:** the same ID, preserved findings, no new provider attempts and no reset of previously saved usage/reservations. The API may project an interrupted terminal status while the raw forensic JSON still says `in_progress`; reads intentionally do not rewrite it. An old attempt can remain `in_flight` in the saved ledger because its outcome is unknown. **Fail:** automatic resume/replay, false `completed`, lost findings, or fabricated zero usage. Inspect API status/metadata and raw JSON separately. `.lock` file existence alone does not mean its OS lock is still held.

This is conservative recovery, not durable provider-operation resume or exactly-once remote execution. In the offline demo there are no remote paid calls, but the application still preserves its general uncertainty semantics.

## 12. Repeat the automated verification locally

From repository root with the backend environment active:

```bash
python scripts/verify_offline_demo.py
env OPENAI_API_KEY= GEMINI_API_KEY= ANTHROPIC_API_KEY= GROQ_API_KEY= XAI_API_KEY= SERPER_API_KEY= SERPAPI_API_KEY= \
  python -m pytest -q
```

The explicit empty keys on the pytest command also protect legacy tests that otherwise select configured live clients. The verifier prints a fresh artifact directory under `data/saved_reviews/demo-verification/<timestamp>/`. It uses isolated saved sessions and explicitly forbids OpenAI/Gemini adapter calls. Those artifacts are not injected into the UI's normal history. Inspect `verification.json` and the three `sessions/*.json` files. Use a new `--output-dir` if overriding the default; an existing directory is rejected to protect earlier evidence.

In the frontend terminal after stopping Vite, or a separate terminal:

```bash
cd "<repo-root>/frontend"
node --test tests/*.test.cjs
npm run build
npx tsc --noEmit
```

**Pass:** verifier exits 0 with all three presets passing; tests/build/typecheck exit 0. **Fail:** any nonzero exit or paid-provider selection. Save the output and exact commit. These are automated checks; they do not sign off the manual scenarios above.

## Acceptance worksheet

Recorded results below apply only to the observed local browser session on November 7, 2026, at documentation checkout `8f8b795` (application code baseline `b7ed1e8`). Recheck them for your interview environment. Rows marked **Blocked** or **Not run** are outstanding; do not infer a pass from automated tests.

| Scenario | Observed result | Session ID / notes |
| --- | --- | --- |
| Startup and mock-only configuration | Pass | Local browser loaded; all generated specialists remained mock. |
| DevPulse review/debate/synthesis/save/reopen | Pass | Four distinct reviews, two exchanges, synthesis and saved reopening passed. `937378b1-3c9f-4fd7-92e9-08e2ffe33fa5` |
| GlowGreen review/debate/synthesis/save/reopen | Pass | Four distinct reviews, two exchanges, synthesis and saved reopening passed. `de63fde5-f056-4562-9414-8bc489ad5d81` |
| QuantumSleep evidence limitations/save/reopen | Pass | Three distinct reviews, one exchange, clinical uncertainty; reopened saved review. `62c3ab1b-e817-4290-bdcf-c5951a6626f8` |
| Refresh active review, including correct restored form/view | Pass | Restored idea, panel and partial findings; timeout run finished with seven attempts. `3858e723-a954-4550-815a-8737e86c8721` |
| Stream-only blocking and GET polling | Pass | Native DevTools showed one affected request under a stream-only blocking rule; snapshot polling retained findings and reached seven attempts. `06d26fff-e84f-49a1-986e-33ca332faf87` |
| Full offline interval, then refresh recovery | Pass (recorded variant) | Browser showed `ERR_INTERNET_DISCONNECTED`. After restoring Online and refreshing, the completed run was reopened from Saved Reviews with seven attempts. The other tab had cleared the active key when it finished. `2ca2acd3-5719-4bf3-81d1-ad5a3ef5c7ea` |
| Two tabs, same run | Pass | Both showed the controlled run and identical final partial-failure totals; one ledger with seven attempts. `3858e723-a954-4550-815a-8737e86c8721` |
| Explicit rerun and preserved lineage | Pass | Child `76c9e716-490f-4377-b33b-1083fd220aed`, six attempts, parent retained. |
| Simulated failure and surviving findings | Pass | Explicit infrastructure failure, three surviving reviews, seven attempts and failure-impact warning. `7156990d-0912-4574-92c3-f56f54bee690` |
| Token exhaustion; optional partial call-cap stop | Pass (token scenario) | Zero attempts/tokens; saved `budget_stopped`. `d93b0b0f-4a1b-4b20-851c-23157b7b83d2`. Optional call-cap scenario not run. |
| Side-effect-free saved-result reads | Pass | Reopened completed, partial-failure and budget-stopped runs; all seven recorded session file hashes remained unchanged. |
| Abrupt backend restart and conservative interrupted status | Blocked | Verified local worker and in-flight checkpoint, but the execution sandbox rejected the signal with `Operation not permitted`. No process restart occurred; this is not a passed browser test. |

The recorded follow-up exercised stream-only blocking and full offline toggling through native browser DevTools. The interrupted-process scenario remains outstanding because the sandbox rejected the worker signal. Run it from a local terminal against a dedicated demo process before final acceptance. The optional partial call-cap scenario also remains unrun. Real provider billing/cancellation and remote exactly-once behavior cannot be demonstrated by a mock-only run and are not claimed here.
