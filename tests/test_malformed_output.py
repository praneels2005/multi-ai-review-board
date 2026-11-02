"""
Tests for malformed output and schema validation handling.
Verifies that when a provider returns invalid syntax or unparseable JSON,
the system isolates the failure gracefully without crashing the application.
"""

import pytest
from app.models.connectors.factory import get_provider_adapter
from app.schemas.review_board_schema import (
    StartupIdeaInput,
    SpecialistAgentConfig,
    BudgetConfig,
)
from app.services.review_orchestrator import ReviewBoardOrchestrator


@pytest.mark.anyio
async def test_mock_adapter_malformed_output_simulation():
    """Verify mock adapter returns error on malformed_output simulation."""
    adapter = get_provider_adapter("mock")
    response = await adapter.call(
        system_prompt="Test",
        user_prompt="Idea",
        simulate_failure="malformed_output"
    )

    assert response.parsed_json is None
    assert response.error is not None
    assert "Malformed" in response.error


@pytest.mark.anyio
async def test_orchestrator_handles_malformed_specialist_output():
    """Verify orchestrator marks specialist as failed when output is malformed without crashing."""
    idea = StartupIdeaInput(
        title="Test Idea",
        idea="A simple test idea with sufficient length.",
        target_customer="Test Users",
        problem="Test Problem",
        proposed_solution="Test Solution",
        evidence=[]
    )

    panel = [
        SpecialistAgentConfig(
            id="spec_1",
            role="Normal Specialist 1",
            expertise="General expertise",
            mandate="Review",
            rationale="Needed",
            provider="mock",
            model="mock-deterministic"
        ),
        SpecialistAgentConfig(
            id="spec_2",
            role="Buggy Specialist",
            expertise="Malformed specialist",
            mandate="Review with broken response",
            rationale="Testing edge cases",
            provider="mock",
            model="mock-deterministic",
            simulate_failure="malformed_output"
        ),
        SpecialistAgentConfig(
            id="spec_3",
            role="Normal Specialist 2",
            expertise="Security expertise",
            mandate="Security review",
            rationale="Verification",
            provider="mock",
            model="mock-deterministic"
        )
    ]

    orchestrator = ReviewBoardOrchestrator(budget_config=BudgetConfig(max_retries=0))
    session = await orchestrator.execute_board(idea=idea, panel=panel)

    assert len(session.specialist_reviews) == 3
    spec1_review = session.specialist_reviews[0]
    spec2_review = session.specialist_reviews[1]
    spec3_review = session.specialist_reviews[2]

    assert spec1_review.status == "success"
    assert spec2_review.status == "failed"
    assert spec3_review.status == "success"
    assert "Malformed" in (spec2_review.error_message or "") or "Failed to parse" in (spec2_review.error_message or "")

    # Entire board still produces session with coordinator synthesis
    assert session.combined_review is not None
    assert session.status == "partial_failure"
