"""
Tests for timeout enforcement and retry bounding.
Verifies that per-call timeouts are strictly enforced and at most one retry
is attempted on transient failures.
"""

import pytest
import time
from app.schemas.review_board_schema import (
    StartupIdeaInput,
    SpecialistAgentConfig,
    BudgetConfig,
)
from app.services.review_orchestrator import ReviewBoardOrchestrator


@pytest.mark.anyio
async def test_per_agent_timeout_enforcement():
    """Verify that a specialist exceeding timeout limit is interrupted and marked timed_out."""
    idea = StartupIdeaInput(
        title="Timeout Test Idea",
        idea="Testing timeout enforcement on slow specialist responses.",
        target_customer="Test Developers",
        problem="Slow upstream APIs",
        proposed_solution="Enforce timeouts strictly",
        evidence=[]
    )

    panel = [
        SpecialistAgentConfig(
            id="spec_timeout",
            role="Slow Specialist",
            expertise="Simulated slow response",
            mandate="Evaluate timeouts",
            rationale="Testing timeout limit",
            provider="mock",
            model="mock-deterministic",
            simulate_failure="timeout"
        )
    ]

    # Configure short timeout (0.2s) and 0 retries
    budget = BudgetConfig(timeout_seconds=0.2, max_retries=0)
    orchestrator = ReviewBoardOrchestrator(budget_config=budget)

    start_t = time.perf_counter()
    session = await orchestrator.execute_board(idea=idea, panel=panel)
    duration = time.perf_counter() - start_t

    review = session.specialist_reviews[0]
    assert review.status == "timed_out"
    assert "Timed out" in (review.error_message or "")
    # Should terminate reasonably quickly
    assert duration < 2.5


@pytest.mark.anyio
async def test_at_most_one_retry_on_failure():
    """Verify that failing agent attempts at most one retry (2 calls total)."""
    idea = StartupIdeaInput(
        title="Retry Test Idea",
        idea="Testing retry limits on failing calls.",
        target_customer="Test Developers",
        problem="Transient errors",
        proposed_solution="Bound retries to 1",
        evidence=[]
    )

    panel = [
        SpecialistAgentConfig(
            id="spec_fail",
            role="Failing Specialist",
            expertise="Throws connection errors",
            mandate="Verify retry count",
            rationale="Ensure max 1 retry",
            provider="mock",
            model="mock-deterministic",
            simulate_failure="provider_error"
        )
    ]

    budget = BudgetConfig(timeout_seconds=1.0, max_retries=1)
    orchestrator = ReviewBoardOrchestrator(budget_config=budget)

    session = await orchestrator.execute_board(idea=idea, panel=panel)

    review = session.specialist_reviews[0]
    assert review.status == "failed"
    # Specialist was attempted twice (1 initial + 1 retry) and coordinator made 1 call = 3 total calls
    assert orchestrator.calls_made == 3
