"""Run identity, disconnected subscriptions, durable checkpoints and conservative restart."""
import asyncio
import json
import multiprocessing
import os
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.connectors.mock_adapter import DeterministicMockAdapter
from app.schemas.review_board_schema import BudgetConfig, RunReviewRequest, ReviewBoardSession
from app.services.panel_service import PanelService
from app.services.review_runs import ReviewRuns, RunConflict
from app.services.session_store import SessionStore
import app.services.session_store as storage


@pytest.fixture(scope="module")
def config():
    async def run():
        idea = PanelService.get_presets()["devtool_ebpf"]["idea"]
        panel = await PanelService.generate_panel(idea)
        return RunReviewRequest(idea=idea, panel=panel)
    return asyncio.run(run())


@pytest.fixture(autouse=True)
def isolated_storage(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "STORAGE_DIR", tmp_path)


@pytest.fixture
def calls(monkeypatch):
    calls = []
    original = DeterministicMockAdapter.call
    async def record(self, **kwargs):
        calls.append(kwargs["task"])
        return await original(self, **kwargs)
    monkeypatch.setattr(DeterministicMockAdapter, "call", record)
    return calls


async def wait_for(predicate):
    for _ in range(1000):
        if predicate():
            return
        await asyncio.sleep(.005)
    raise AssertionError("Checkpoint not reached")


@pytest.mark.anyio
async def test_duplicate_submissions_share_one_run_and_original_ledger(config, calls):
    sid = ReviewRuns.start(config, "stable")
    assert ReviewRuns.start(config, "stable") == sid
    result = await ReviewRuns.wait(sid)
    count = len(calls)
    ledger = deepcopy(result.execution_summary)
    assert ReviewRuns.start(config, "stable") == sid
    again = await ReviewRuns.wait(sid)
    assert len(calls) == count == 9
    assert again.model_dump() == result.model_dump()
    assert again.execution_summary == ledger
    assert result.status == "completed"


@pytest.mark.anyio
async def test_concurrent_submissions_attach_atomically(config, calls):
    async def submit():
        await asyncio.sleep(0)
        return ReviewRuns.start(config, "concurrent")
    ids = await asyncio.gather(*(submit() for _ in range(10)))
    assert set(ids) == {"concurrent"}
    session = await ReviewRuns.wait("concurrent")
    assert len(calls) == session.execution_summary["calls_made"] == 9
    assert len({r.specialist_id for r in session.specialist_reviews}) == 4


@pytest.mark.anyio
@pytest.mark.parametrize("change", ["idea", "panel", "budget"])
async def test_conflicting_parameters_cannot_reuse_identity(config, calls, change):
    ReviewRuns.start(config, "conflict")
    changed = config.model_copy(deep=True)
    if change == "idea":
        changed.idea.problem += " Extra scope."
    elif change == "panel":
        changed.panel[0].mandate += " Different mandate."
    else:
        changed.budget_config = BudgetConfig(call_cap=10)
    with pytest.raises(RunConflict, match="different review parameters"):
        ReviewRuns.start(changed, "conflict")
    await ReviewRuns.wait("conflict")
    assert len(calls) == 9


@pytest.mark.anyio
async def test_explicit_new_identity_runs_again_without_overwriting(config, calls):
    for sid in ("first", "second"):
        ReviewRuns.start(config, sid)
        await ReviewRuns.wait(sid)
    assert len(calls) == 18
    assert SessionStore.get("first").session_id == "first"
    assert SessionStore.get("second").session_id == "second"


@pytest.mark.anyio
async def test_client_disconnect_does_not_cancel_specialist_or_lose_outputs(config, calls):
    sid = ReviewRuns.start(config, "disconnect")
    stream = ReviewRuns.events(sid)
    await anext(stream)
    await stream.aclose()
    # The run is owned by the registry, not the subscriber's generator.
    result = await ReviewRuns.wait(sid)
    assert result.status == "completed"
    assert len(result.specialist_reviews) == 4
    assert len(calls) == 9
    assert SessionStore.get(sid).model_dump() == result.model_dump()


@pytest.mark.anyio
@pytest.mark.parametrize("phase", ["specialists", "debate", "coordinator"])
async def test_reconnect_during_each_phase_preserves_results_and_budget(config, calls, phase):
    sid = ReviewRuns.start(config, "phase-" + phase)
    def ready():
        state = ReviewRuns.snapshot(sid)
        return state.run_metadata.get("phase") == phase and (phase != "specialists" or len(state.specialist_reviews) >= 1)
    await wait_for(ready)
    before = ReviewRuns.snapshot(sid)
    stream = ReviewRuns.events(sid)
    frame = await anext(stream)
    event = json.loads(frame.split("data: ", 1)[1])
    assert event["session"]["specialist_reviews"] == [r.model_dump() for r in before.specialist_reviews]
    assert event["session"]["execution_summary"] == before.execution_summary
    await stream.aclose()
    result = await ReviewRuns.wait(sid)
    assert len(calls) == 9
    assert len(result.specialist_reviews) == 4 and len(result.challenge_round) == 2
    assert result.execution_summary["total_tokens"] == sum(a["total_tokens"] for a in result.execution_summary["provider_attempts"])


@pytest.mark.anyio
@pytest.mark.parametrize("outcome", ["completed", "partial_failure", "budget_stopped"])
async def test_terminal_recovery_is_read_only_and_does_not_repeat_events(config, calls, outcome):
    request = config.model_copy(deep=True)
    if outcome == "partial_failure":
        request.panel[1].simulate_failure = "malformed_output"
    elif outcome == "budget_stopped":
        request.budget_config = BudgetConfig(call_cap=2)
    sid = ReviewRuns.start(request, outcome)
    result = await ReviewRuns.wait(sid)
    assert result.status == outcome
    path = SessionStore._validate_session_id(sid)
    original = path.read_bytes(), path.stat().st_mtime_ns
    count = len(calls)
    first = [frame async for frame in ReviewRuns.events(sid)]
    event = json.loads(first[0].split("data: ", 1)[1])
    assert event["type"] == "session_final" and event["session"] == result.model_dump()
    assert [frame async for frame in ReviewRuns.events(sid, event["sequence"])] == []
    for _ in range(3):
        assert ReviewRuns.snapshot(sid).model_dump() == result.model_dump()
    assert (path.read_bytes(), path.stat().st_mtime_ns) == original
    assert len(calls) == count


@pytest.mark.anyio
async def test_reservation_is_durable_before_provider_dispatch(config, monkeypatch):
    original = DeterministicMockAdapter.call
    observed = []
    async def inspect(self, **kwargs):
        snapshot = SessionStore.get("durable")
        ledger = snapshot.execution_summary
        observed.append(ledger["calls_made"])
        assert ledger["reserved_tokens"] > 0
        assert ledger["provider_attempts"][-1]["status"] == "in_flight"
        return await original(self, **kwargs)
    monkeypatch.setattr(DeterministicMockAdapter, "call", inspect)
    ReviewRuns.start(config, "durable")
    session = await ReviewRuns.wait("durable")
    assert observed == list(range(1, 10))
    assert session.execution_summary["reserved_tokens"] == 0


@pytest.mark.anyio
async def test_cancelled_http_waiter_does_not_cancel_run(config, calls):
    ReviewRuns.start(config, "waiter")
    waiter = asyncio.create_task(ReviewRuns.wait("waiter"))
    await asyncio.sleep(.02)
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter
    result = await ReviewRuns.wait("waiter")
    assert result.status == "completed" and len(calls) == 9


@pytest.mark.anyio
async def test_owner_interruption_retains_completed_findings_and_ledger(config, calls):
    sid = ReviewRuns.start(config, "interrupt")
    await wait_for(lambda: len(ReviewRuns.snapshot(sid).specialist_reviews) >= 1)
    before = ReviewRuns.snapshot(sid)
    task = ReviewRuns.tasks[(str(SessionStore._ensure_dir()), sid)]
    task.cancel()
    await task
    recovered = ReviewRuns.snapshot(sid)
    assert recovered.status == "partial_failure" and recovered.run_metadata["interrupted"]
    assert recovered.specialist_reviews[0].model_dump() == before.specialist_reviews[0].model_dump()
    count = len(calls)
    ReviewRuns.start(config, sid)
    await ReviewRuns.wait(sid)
    assert len(calls) == count
    assert recovered.execution_summary["calls_made"] >= before.execution_summary["calls_made"]


def abandoned_checkpoint(directory, data):
    # Separate process owns and releases the OS lock on abrupt exit, as on restart.
    from pathlib import Path
    import app.services.session_store as child_storage
    child_storage.STORAGE_DIR = Path(directory)
    session = ReviewBoardSession.model_validate(data)
    handle = SessionStore.acquire_run_lock(session.session_id)
    SessionStore.save(session)
    os._exit(0)


@pytest.mark.anyio
async def test_process_restart_never_replays_unknown_dispatch(config, calls):
    from datetime import datetime, timezone
    session = ReviewBoardSession(session_id="crashed", created_at=datetime.now(timezone.utc).isoformat(),
        idea=config.idea, panel=config.panel, budget_config=BudgetConfig(), status="in_progress",
        run_metadata={"fingerprint": ReviewRuns.fingerprint(config), "sequence": 4},
        execution_summary={"calls_made": 1, "total_tokens": 0, "reserved_tokens": 7000,
                           "provider_attempts": [{"attempt": 1, "status": "in_flight", "reserved_tokens": 7000}]})
    proc = multiprocessing.get_context("spawn").Process(target=abandoned_checkpoint,
        args=(str(storage.STORAGE_DIR), session.model_dump()))
    proc.start()
    await asyncio.to_thread(proc.join, 10)
    assert proc.exitcode == 0
    path = SessionStore._validate_session_id("crashed")
    raw = path.read_bytes()
    recovered = ReviewRuns.snapshot("crashed")
    assert recovered.status == "failed" and recovered.run_metadata["interrupted"]
    assert recovered.execution_summary == session.execution_summary
    assert path.read_bytes() == raw  # Reads never rewrite interruption status or reset usage.
    ReviewRuns.start(config, "crashed")
    assert (await ReviewRuns.wait("crashed")).status == "failed"
    assert calls == []


def test_atomic_save_failure_preserves_previous_valid_file(config, monkeypatch):
    from datetime import datetime, timezone
    session = ReviewBoardSession(session_id="atomic", created_at=datetime.now(timezone.utc).isoformat(),
                                idea=config.idea, panel=config.panel, budget_config=BudgetConfig())
    SessionStore.save(session)
    original = SessionStore._validate_session_id("atomic").read_bytes()
    def fail(*args):
        raise OSError("Simulated replace failure")
    monkeypatch.setattr(os, "replace", fail)
    session.status = "failed"
    with pytest.raises(OSError):
        SessionStore.save(session)
    assert SessionStore._validate_session_id("atomic").read_bytes() == original
    assert list(storage.STORAGE_DIR.glob(".checkpoint-*")) == []


@pytest.mark.anyio
async def test_failed_pre_dispatch_checkpoint_never_calls_provider(config, calls, monkeypatch):
    original = SessionStore.save
    writes = 0
    def save(session):
        nonlocal writes
        writes += 1
        if session.execution_summary.get("reserved_tokens", 0) > 0:
            raise OSError("Disk unavailable before dispatch")
        return original(session)
    monkeypatch.setattr(SessionStore, "save", save)
    ReviewRuns.start(config, "disk-error")
    result = await ReviewRuns.wait("disk-error")
    assert result.status in {"failed", "partial_failure"}
    assert calls == [] and result.execution_summary.get("calls_made", 0) == 0


def test_api_duplicate_conflict_subscribe_and_explicit_rerun(config, calls):
    with TestClient(app) as client:
        payload = {**config.model_dump(), "session_id": "api-key"}
        result = client.post("/api/review-board/run", json=payload)
        assert result.status_code == 200
        count = len(calls)
        assert client.post("/api/review-board/run", json=payload).json() == result.json()
        altered = deepcopy(payload)
        altered["idea"]["problem"] += " Conflicting requirement."
        assert client.post("/api/review-board/runs", json=altered).status_code == 409
        assert client.post("/api/review-board/runs", json=payload, headers={"Idempotency-Key":"different"}).status_code == 409
        stream = client.get("/api/review-board/sessions/api-key/events")
        assert stream.status_code == 200 and '"type": "session_final"' in stream.text
        assert client.get("/api/review-board/sessions/unknown/events").status_code == 404
        assert len(calls) == count
        rerun = client.post("/api/review-board/sessions/api-key/rerun", headers={"Idempotency-Key":"new-child"})
        assert rerun.status_code == 200 and rerun.json()["rerun_of_session_id"] == "api-key"
        repeat = client.post("/api/review-board/sessions/api-key/rerun", headers={"Idempotency-Key":"new-child"})
        assert repeat.json() == rerun.json() and len(calls) == count * 2
        parent = client.get("/api/review-board/sessions/api-key").json()
        assert parent["rerun_history"] == ["new-child"]


def duplicate_worker(directory, data, connection):
    from pathlib import Path
    import app.services.session_store as worker_storage
    worker_storage.STORAGE_DIR = Path(directory)
    async def submit():
        # If the shared lock fails to exclude this worker, any provider invocation is a defect.
        async def forbidden(*args, **kwargs):
            connection.send("DUPLICATE_PROVIDER")
            raise AssertionError("Duplicate worker")
        DeterministicMockAdapter.call = forbidden
        sid = ReviewRuns.start(RunReviewRequest.model_validate(data), "multi-worker")
        connection.send(sid)
    asyncio.run(submit())
    connection.close()


@pytest.mark.anyio
async def test_shared_storage_lock_excludes_another_worker(config, calls, monkeypatch):
    gate = asyncio.Event()
    original = DeterministicMockAdapter.call
    async def held(self, **kwargs):
        await gate.wait()
        return await original(self, **kwargs)
    monkeypatch.setattr(DeterministicMockAdapter, "call", held)
    ReviewRuns.start(config, "multi-worker")
    await asyncio.sleep(.01)
    context = multiprocessing.get_context("spawn")
    reader, writer = context.Pipe(duplex=False)
    process = context.Process(target=duplicate_worker, args=(str(storage.STORAGE_DIR), config.model_dump(), writer))
    process.start()
    await asyncio.to_thread(process.join, 10)
    assert process.exitcode == 0 and reader.recv() == "multi-worker"
    assert not reader.poll(.05)
    gate.set()
    assert (await ReviewRuns.wait("multi-worker")).status == "completed"
    assert len(calls) == 9
    reader.close()
    writer.close()


@pytest.mark.anyio
async def test_legacy_stream_endpoint_disconnect_retains_server_task(config, calls):
    from app.api.review_board_router import run_review_board_stream
    request = config.model_copy(update={"session_id":"legacy-stream"})
    response = await run_review_board_stream(request, None)
    await anext(response.body_iterator)
    await response.body_iterator.aclose()
    assert (await ReviewRuns.wait("legacy-stream")).status == "completed"
    assert len(calls) == 9


@pytest.mark.anyio
async def test_legacy_saved_completed_run_cannot_be_reexecuted(config, calls):
    from app.services.review_orchestrator import ReviewBoardOrchestrator
    previous = await ReviewBoardOrchestrator().execute_board(config.idea, config.panel, session_id="legacy")
    previous.run_metadata = {}  # Old saved files have no idempotency metadata.
    SessionStore.save(previous)
    count = len(calls)
    assert ReviewRuns.start(config, "legacy") == "legacy"
    assert (await ReviewRuns.wait("legacy")).model_dump() == previous.model_dump()
    assert len(calls) == count


@pytest.mark.anyio
async def test_saved_draft_identifier_is_rejected_instead_of_hanging_or_silently_executing(config, calls):
    from datetime import datetime, timezone
    draft = ReviewBoardSession(session_id="draft", created_at=datetime.now(timezone.utc).isoformat(),
        idea=config.idea, panel=config.panel, budget_config=BudgetConfig(), status="draft")
    SessionStore.save(draft)
    with pytest.raises(RunConflict, match="saved draft"):
        ReviewRuns.start(config, "draft")
    assert calls == [] and SessionStore.get("draft").status == "draft"


@pytest.mark.anyio
async def test_terminal_checkpoint_is_published_once_without_duplicate_final_versions(config, monkeypatch):
    original = SessionStore.save
    terminal_sequences = []
    def save(session):
        if session.status in {"completed", "partial_failure", "budget_stopped", "failed"}:
            terminal_sequences.append(session.run_metadata["sequence"])
        original(session)
    monkeypatch.setattr(SessionStore, "save", save)
    ReviewRuns.start(config, "single-final")
    session = await ReviewRuns.wait("single-final")
    assert terminal_sequences == [session.run_metadata["sequence"]]
    assert len([frame async for frame in ReviewRuns.events("single-final")]) == 1


@pytest.mark.anyio
async def test_shutdown_before_worker_starts_releases_claim_without_dispatch(config, calls):
    sid = ReviewRuns.start(config, "never-started")
    task = ReviewRuns.tasks[(str(SessionStore._ensure_dir()), sid)]
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    await asyncio.sleep(0)
    assert calls == []
    recovered = ReviewRuns.snapshot(sid)
    assert recovered.status == "failed" and recovered.run_metadata["interrupted"]
    assert recovered.execution_summary["calls_made"] == 0
    assert ReviewRuns.start(config, sid) == sid
    assert (await ReviewRuns.wait(sid)).status == "failed"
    assert calls == []
