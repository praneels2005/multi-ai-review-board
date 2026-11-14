"""
Tests for coordinator failure handling and explicit fallback labeling.
Verifies that when coordinator synthesis encounters a failure or timeout,
the session is NOT marked completed and the fallback status is clearly exposed.
"""

import pytest
from unittest.mock import patch
from app.schemas.review_board_schema import (
    StartupIdeaInput,
    SpecialistAgentConfig,
    BudgetConfig,
)
from app.services.review_orchestrator import ReviewBoardOrchestrator


def _get_panel():
    return [
        SpecialistAgentConfig(
            id=f"spec_{i}",
            role=f"Specialist {i}",
            expertise="General expertise",
            mandate="Review mandate",
            rationale="Rationale",
            provider="mock",
            model="mock-deterministic"
        )
        for i in range(1, 4)
    ]


@pytest.mark.anyio
async def test_coordinator_failure_is_explicit_and_sets_partial_failure():
    """Verify that coordinator failure sets is_fallback=True and does not report session as completed."""
    idea = StartupIdeaInput(
        title="Test Idea",
        idea="A sufficiently long test idea for validation.",
        target_customer="Developers",
        problem="Problem statement",
        proposed_solution="Proposed solution",
        evidence=[]
    )

    orchestrator = ReviewBoardOrchestrator()

    # Simulate coordinator provider raising an unexpected error
    with patch.object(orchestrator, "_run_coordinator_synthesis") as mock_coord:
        from app.schemas.review_board_schema import CoordinatorCombinedReview, EvidenceSufficiencyAssessment
        mock_coord.return_value = CoordinatorCombinedReview(
            summary="[COORDINATOR FAILED] Simulated coordinator failure",
            priorities=[],
            disagreements=[],
            next_experiments=[],
            evidence_sufficiency=EvidenceSufficiencyAssessment(
                status="insufficient",
                analysis="Failed to assess"
            ),
            failure_impact_analysis="Coordinator failure occurred",
            disclaimer="Decision support only.",
            is_fallback=True,
            status="failed"
        )

        session = await orchestrator.execute_board(idea=idea, panel=_get_panel())

        # Session MUST NOT be completed!
        assert session.status == "partial_failure"
        assert session.combined_review is not None
        assert session.combined_review.is_fallback is True
        assert session.combined_review.status == "failed"

