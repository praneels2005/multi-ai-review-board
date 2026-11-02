"""
API Router for Multiple AI Review Board.
Provides endpoints for presets, panel generation, executing review boards
(standard & real-time SSE streaming), listing saved sessions, reopening sessions,
and rerunning sessions with lineage tracking.
"""

import asyncio
import json
import uuid
from fastapi import APIRouter, HTTPException, Query
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
from app.services.review_orchestrator import ReviewBoardOrchestrator
from app.services.session_store import SessionStore

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
            model=request.model or ("gpt-4o-mini" if request.provider == "openai" else ("gemini-1.5-flash" if request.provider == "gemini" else "mock-deterministic"))
        )
        return specialists
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate specialist panel: {str(e)}")


@router.post("/run", response_model=ReviewBoardSession)
async def run_review_board(request: RunReviewRequest):
    """Execute the multi-agent review board (independent reviews, debate, and coordinator synthesis)."""
    try:
        orchestrator = ReviewBoardOrchestrator(budget_config=request.budget_config)
        session = await orchestrator.execute_board(
            idea=request.idea,
            panel=request.panel,
            session_id=request.session_id
        )
        SessionStore.save(session)
        return session
    except ValueError as ve:
        raise HTTPException(status_code=422, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Review board execution failed: {str(e)}")


@router.post("/run-stream")
async def run_review_board_stream(request: RunReviewRequest):
    """
    Execute review board with real-time Server-Sent Events (SSE) streaming progress.
    Emits per-agent start/complete events, debate exchanges, and final session state.
    """
    try:
        queue: asyncio.Queue = asyncio.Queue()

        def progress_callback(event: Dict[str, Any]):
            queue.put_nowait(event)

        async def sse_event_generator():
            orchestrator = ReviewBoardOrchestrator(budget_config=request.budget_config)
            
            # Run board in background task within loop
            task = asyncio.create_task(
                orchestrator.execute_board(
                    idea=request.idea,
                    panel=request.panel,
                    session_id=request.session_id,
                    progress_callback=progress_callback
                )
            )

            while not task.done() or not queue.empty():
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=0.2)
                    yield f"data: {json.dumps(event)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"

            session = await task
            SessionStore.save(session)
            final_event = {"type": "session_final", "session": session.model_dump()}
            yield f"data: {json.dumps(final_event)}\n\n"

        return StreamingResponse(sse_event_generator(), media_type="text/event-stream")

    except ValueError as ve:
        raise HTTPException(status_code=422, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Stream execution failed: {str(e)}")


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
async def rerun_session(session_id: str, budget_config: Optional[BudgetConfig] = None):
    """
    Rerun an existing review session preserving history.
    Generates a new session linked to the parent without overwriting the previous run.
    """
    try:
        existing = SessionStore.get(session_id)
        if not existing:
            raise HTTPException(status_code=404, detail=f"Review session '{session_id}' not found.")

        new_session_id = str(uuid.uuid4())
        cfg = budget_config or existing.budget_config
        orchestrator = ReviewBoardOrchestrator(budget_config=cfg)

        new_session = await orchestrator.execute_board(
            idea=existing.idea,
            panel=existing.panel,
            session_id=new_session_id
        )
        new_session.rerun_of_session_id = existing.session_id
        new_session.version = existing.version + 1

        # Save both new session and update parent rerun history
        SessionStore.save(new_session)
        SessionStore.record_rerun_lineage(existing.session_id, new_session_id)

        return new_session
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Rerunning review session failed: {str(e)}")
