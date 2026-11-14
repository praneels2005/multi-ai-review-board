"""
API Router for Multiple AI Review Board.
Provides endpoints for presets, panel generation, executing review boards
(standard & real-time SSE streaming), listing saved sessions, reopening sessions,
and rerunning sessions with lineage tracking.
"""

from fastapi import APIRouter, HTTPException, Query, Header
from fastapi.responses import StreamingResponse
from typing import List, Dict, Any, Optional

from app.schemas.review_board_schema import (
    StartupIdeaInput,
    SpecialistAgentConfig,
    GeneratePanelRequest,
    RunReviewRequest,
    ReviewBoardSession,
    BudgetConfig,
)
from app.services.panel_service import PanelService
from app.services.session_store import SessionStore
from app.services.review_runs import ReviewRuns, RunConflict

router = APIRouter(prefix="/api/review-board", tags=["Multiple AI Review Board"])


@router.get("/presets", response_model=Dict[str, Any])
def get_presets():
    """Retrieve pre-built contrasting startup ideas and thin-evidence presets."""
    return PanelService.get_presets()


@router.post("/generate-panel", response_model=List[SpecialistAgentConfig])
async def generate_panel(request: GeneratePanelRequest):
    """Dynamically generate 3 to 5 domain-specific specialist agents for an idea."""
    try:
        specialists = await PanelService.generate_panel(
            idea_input=request.idea,
            provider=request.provider,
            model=request.model or ("gpt-4o-mini" if request.provider == "openai" else ("gemini-3.5-flash-lite" if request.provider == "gemini" else "mock-deterministic"))
        )
        return specialists
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate specialist panel: {str(e)}")


def start_identified_run(request, key=None, parent=None):
    try:
        return ReviewRuns.start(request, key, parent)
    except RunConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/runs", response_model=ReviewBoardSession, status_code=202)
async def start_review_board(request: RunReviewRequest, idempotency_key: Optional[str] = Header(None)):
    """Start or attach to an identified run without waiting or subscribing."""
    sid = start_identified_run(request, idempotency_key)
    return ReviewRuns.snapshot(sid)


@router.post("/run", response_model=ReviewBoardSession)
async def run_review_board(request: RunReviewRequest, idempotency_key: Optional[str] = Header(None)):
    """Compatibility endpoint: start once, then await the same durable run."""
    sid = start_identified_run(request, idempotency_key)
    return await ReviewRuns.wait(sid)


@router.post("/run-stream")
async def run_review_board_stream(request: RunReviewRequest, idempotency_key: Optional[str] = Header(None)):
    """Compatibility endpoint: start once, then subscribe independently."""
    sid = start_identified_run(request, idempotency_key)
    return StreamingResponse(ReviewRuns.events(sid), media_type="text/event-stream",
                             headers={"X-Review-Session-ID": sid, "Cache-Control": "no-cache"})


@router.get("/sessions/{session_id}/events")
async def subscribe_review(session_id: str, after: int = Query(0, ge=0), last_event_id: Optional[str] = Header(None)):
    """Read snapshots only. Subscribing can never start provider work."""
    try:
        ReviewRuns.snapshot(session_id)
        cursor = max(after, int(last_event_id or 0))
        if cursor < 0:
            raise ValueError("Invalid event cursor")
    except KeyError:
        raise HTTPException(status_code=404, detail="Review session not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return StreamingResponse(ReviewRuns.events(session_id, cursor), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache"})


@router.get("/sessions", response_model=List[Dict[str, Any]])
def list_sessions():
    """List all saved review board sessions for history and reopening."""
    return SessionStore.list_all()


@router.get("/sessions/{session_id}", response_model=ReviewBoardSession)
def get_session(session_id: str):
    """Reopen a previously saved review session with path-traversal validation."""
    try:
        session = SessionStore.get(session_id)
        if not session:
            raise HTTPException(status_code=404, detail=f"Review session '{session_id}' not found.")
        return session
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))


@router.post("/sessions/{session_id}/rerun", response_model=ReviewBoardSession)
async def rerun_session(session_id: str, budget_config: Optional[BudgetConfig] = None,
                        idempotency_key: Optional[str] = Header(None)):
    """Explicit new run; an optional key also makes retries of this action safe."""
    try:
        existing = ReviewRuns.snapshot(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Review session not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if existing.status == "in_progress":
        raise HTTPException(status_code=409, detail="Original run is still active")
    request = RunReviewRequest(idea=existing.idea, panel=existing.panel,
                               budget_config=budget_config or existing.budget_config)
    sid = start_identified_run(request, idempotency_key, parent=session_id)
    return await ReviewRuns.wait(sid)
