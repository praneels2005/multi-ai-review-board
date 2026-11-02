"""
API Router for Multiple AI Review Board.
Provides endpoints for presets, panel generation, executing review boards,
listing saved sessions, reopening sessions, and rerunning sessions.
"""

from fastapi import APIRouter, HTTPException, Query
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
            provider="mock",
            model="mock-deterministic"
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
        # Save session to persistent store
        SessionStore.save(session)
        return session
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Review board execution failed: {str(e)}")


@router.get("/sessions", response_model=List[Dict[str, Any]])
def list_sessions():
    """List all saved review board sessions for history and reopening."""
    return SessionStore.list_all()


@router.get("/sessions/{session_id}", response_model=ReviewBoardSession)
def get_session(session_id: str):
    """Reopen a previously saved review session."""
    session = SessionStore.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Review session '{session_id}' not found.")
    return session


@router.post("/sessions/{session_id}/rerun", response_model=ReviewBoardSession)
async def rerun_session(session_id: str, budget_config: Optional[BudgetConfig] = None):
    """Rerun an existing review session with its stored idea and panel configuration."""
    existing = SessionStore.get(session_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Review session '{session_id}' not found.")

    try:
        cfg = budget_config or existing.budget_config
        orchestrator = ReviewBoardOrchestrator(budget_config=cfg)
        new_session = await orchestrator.execute_board(
            idea=existing.idea,
            panel=existing.panel,
            session_id=existing.session_id
        )
        SessionStore.save(new_session)
        return new_session
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Rerunning review session failed: {str(e)}")

