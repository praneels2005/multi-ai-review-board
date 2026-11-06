"""Own review execution independently of HTTP subscriptions, using existing files.

A run's OS file lock is held until its worker finishes. The initial checkpoint is
written before scheduling any provider work; reconnecting and reads never schedule
work. No remote exactly-once or crash-resume guarantee is implied.
"""
import asyncio
import hashlib
import json
import uuid
from datetime import datetime, timezone

from app.schemas.review_board_schema import BudgetConfig, ReviewBoardSession
from app.services.review_orchestrator import ReviewBoardOrchestrator
from app.services.session_store import SessionStore

TERMINAL = {"completed", "partial_failure", "budget_stopped", "failed"}


class RunConflict(ValueError):
    pass


class ReviewRuns:
    tasks = {}

    @staticmethod
    def fingerprint(request, parent=None):
        data = {"idea": request.idea.model_dump(), "panel": [s.model_dump() for s in request.panel],
                "budget_config": (request.budget_config or BudgetConfig()).model_dump(), "parent": parent}
        return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    @classmethod
    def start(cls, request, key=None, parent=None):
        if key and request.session_id and key != request.session_id:
            raise RunConflict("Idempotency-Key and session_id must match")
        sid = key or request.session_id or str(uuid.uuid4())
        SessionStore._validate_session_id(sid)
        fingerprint = cls.fingerprint(request, parent)
        handle = SessionStore.acquire_run_lock(sid)
        if handle is None:
            existing = SessionStore.get(sid)
            if existing is None:
                raise RunConflict("Run is being initialized; retry the same identified request")
            cls._check_identity(existing, fingerprint, request, parent)
            return sid
        try:
            existing = SessionStore.get(sid, detect_interruption=False)
            if existing:
                cls._check_identity(existing, fingerprint, request, parent)
                if existing.status not in TERMINAL and existing.status != "in_progress":
                    raise RunConflict("Identifier belongs to a saved draft; start with a new run identifier")
                if existing.status == "in_progress":
                    # Lock ownership proves no worker owns this persisted dispatch.
                    SessionStore.save(SessionStore.interrupted(existing))
                return sid
            initial = ReviewBoardSession(
                session_id=sid, created_at=datetime.now(timezone.utc).isoformat(), idea=request.idea,
                panel=request.panel, budget_config=request.budget_config or BudgetConfig(), status="in_progress",
                rerun_of_session_id=parent, version=(SessionStore.get(parent).version + 1 if parent else 1),
                run_metadata={"fingerprint": fingerprint, "sequence": 1, "phase": "pending"},
            )
            SessionStore.save(initial)
            if parent:
                SessionStore.record_rerun_lineage(parent, sid)
            task = asyncio.create_task(cls._execute(initial, handle))
            task_key = (str(SessionStore._ensure_dir()), sid)
            cls.tasks[task_key] = task  # Strong reference survives disconnected HTTP clients.
            def finished(done, owned_handle=handle):
                cls.tasks.pop(task_key, None)
                # Also cover shutdown before the coroutine's first instruction.
                if not owned_handle.closed:
                    SessionStore.release_run_lock(owned_handle)
            task.add_done_callback(finished)
            handle = None  # Execution task owns the lock now.
            return sid
        finally:
            if handle is not None:
                SessionStore.release_run_lock(handle)

    @classmethod
    def _check_identity(cls, existing, fingerprint, request, parent):
        original = existing.run_metadata.get("fingerprint")
        if original is None:
            # Legacy saved runs are retrieval-only too; compare normalized parameters.
            from app.schemas.review_board_schema import RunReviewRequest
            old = RunReviewRequest(idea=existing.idea, panel=existing.panel, budget_config=existing.budget_config)
            original = cls.fingerprint(old, existing.rerun_of_session_id)
        if original != fingerprint:
            raise RunConflict("Run identifier already belongs to different review parameters")

    @classmethod
    async def _execute(cls, initial, handle):
        current = initial
        orchestrator = ReviewBoardOrchestrator(initial.budget_config)
        def checkpoint(session):
            nonlocal current
            session.run_metadata = {**current.run_metadata, **session.run_metadata}
            session.run_metadata["sequence"] = current.run_metadata.get("sequence", 0) + 1
            session.created_at = initial.created_at
            session.rerun_of_session_id = initial.rerun_of_session_id
            session.version = initial.version
            durable = session.model_copy(deep=True)
            if durable.status in TERMINAL and durable.run_metadata.get("last_event") != "session_completed":
                durable.status = "in_progress"
            SessionStore.save(durable)
            current = durable
        try:
            result = await orchestrator.execute_board(initial.idea, initial.panel,
                session_id=initial.session_id, checkpoint_callback=checkpoint)
            if current.status not in TERMINAL:
                checkpoint(result)
        except BaseException as exc:
            interrupted = SessionStore.interrupted(current)
            interrupted.run_metadata["sequence"] = current.run_metadata.get("sequence", 0) + 1
            # Preserve completed outputs and the last durable ledger, not fabricated findings.
            try:
                SessionStore.save(interrupted)
            except OSError:
                pass  # Existing checkpoint remains conservative; no more provider calls.
            if not isinstance(exc, (Exception, asyncio.CancelledError)):
                raise
        finally:
            SessionStore.release_run_lock(handle)

    @staticmethod
    def snapshot(sid):
        session = SessionStore.get(sid)
        if session is None:
            raise KeyError(sid)
        return session

    @classmethod
    async def wait(cls, sid):
        while True:
            session = cls.snapshot(sid)
            if session.status in TERMINAL:
                return session
            task = cls.tasks.get((str(SessionStore._ensure_dir()), sid))
            if task:
                await asyncio.shield(task)
            else:
                # A worker sharing the same storage may own the execution lock.
                await asyncio.sleep(.05)

    @classmethod
    async def events(cls, sid, after=0):
        # A coalesced state snapshot is sufficient; intermediate events need not be replayed.
        idle = 0
        while True:
            session = cls.snapshot(sid)
            sequence = session.run_metadata.get("sequence", 1)
            # Restart projection is a new state even without a write on read.
            if session.run_metadata.get("interrupted"):
                sequence += 1
            terminal = session.status in TERMINAL
            if sequence > after:
                after = sequence
                event = {"type": "session_final" if terminal else "session_snapshot",
                         "session_id": sid, "session": session.model_dump(), "sequence": sequence}
                yield f"id: {sequence}\ndata: {json.dumps(event)}\n\n"
            if terminal:
                return
            idle += 1
            if idle % 200 == 0:
                yield ": keep-alive\n\n"
            await asyncio.sleep(.05)
