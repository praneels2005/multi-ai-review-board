"""
Tests for call cap and token cap budget enforcement.
Verifies that execution stops immediately when configured call/token caps are reached.
"""

import pytest
from app.schemas.review_board_schema import (
    StartupIdeaInput,
    SpecialistAgentConfig,
    BudgetConfig,
)
from app.services.review_orchestrator import ReviewBoardOrchestrator


@pytest.mark.anyio
async def test_call_cap_budget_stop():
    """Verify that execution halts when call cap is reached."""
    idea = StartupIdeaInput(
        title="Budget Test Idea",
        idea="Testing call cap stops on multi-agent execution.",
        target_customer="Platform Teams",
        problem="Runaway API costs",
        proposed_solution="Hard call cap stops",
        evidence=[]
    )

    # 4 specialists in panel, but call_cap is set to 2!
    panel = [
        SpecialistAgentConfig(
            id=f"spec_{i}",
            role=f"Specialist {i}",
            expertise="Expertise",
            mandate="Mandate",
            rationale="Rationale",
            provider="mock",
            model="mock-deterministic"
        )
        for i in range(1, 5)
    ]

    # Cap calls strictly at 2
    budget = BudgetConfig(call_cap=2, max_retries=0)
    orchestrator = ReviewBoardOrchestrator(budget_config=budget)

    session = await orchestrator.execute_board(idea=idea, panel=panel)

    assert orchestrator.calls_made == 2
    assert session.status == "budget_stopped"
    assert session.execution_summary["budget_stopped"] is True
    # Only 2 specialists ran before stop
    assert len(session.specialist_reviews) == 2


@pytest.mark.anyio
async def test_token_cap_budget_stop():
    """Verify that execution halts when token cap is exceeded."""
    idea = StartupIdeaInput(
        title="Token Cap Test Idea",
        idea="Testing token budget cap limits.",
        target_customer="Developers",
        problem="Token explosion",
        proposed_solution="Token limit stops",
        evidence=[]
    )

    panel = [
        SpecialistAgentConfig(
            id=f"spec_{i}",
            role=f"Specialist {i}",
            expertise="Expertise",
            mandate="Mandate",
            rationale="Rationale",
            provider="mock",
            model="mock-deterministic"
        )
        for i in range(1, 4)
    ]

    # Set extremely low token cap (e.g. 1500 tokens)
    budget = BudgetConfig(token_cap=1200, call_cap=20, max_retries=0)
    orchestrator = ReviewBoardOrchestrator(budget_config=budget)

    session = await orchestrator.execute_board(idea=idea, panel=panel)

    assert session.status == "budget_stopped"
    assert session.execution_summary["budget_stopped"] is True

