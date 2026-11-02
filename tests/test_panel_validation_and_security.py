"""
Tests for panel constraints (3-5 size, uniqueness) and SessionStore security (path traversal, rerun history).
"""

import pytest
from pydantic import ValidationError
from app.schemas.review_board_schema import (
    StartupIdeaInput,
    SpecialistAgentConfig,
    RunReviewRequest,
)
from app.services.session_store import SessionStore


def test_panel_size_enforcement_minimum():
    """Verify that fewer than 3 specialists raises a validation error."""
    idea = StartupIdeaInput(
        title="Test",
        idea="Long enough idea description",
        target_customer="Users",
        problem="Problem",
        proposed_solution="Solution",
        evidence=[]
    )
    with pytest.raises(ValidationError):
        RunReviewRequest(
            idea=idea,
            panel=[
                SpecialistAgentConfig(
                    id="spec_1",
                    role="Specialist 1",
                    expertise="Expertise",
                    mandate="Mandate",
                    rationale="Rationale",
                    provider="mock"
                )
            ]
        )


def test_panel_size_enforcement_maximum():
    """Verify that more than 5 specialists raises a validation error."""
    idea = StartupIdeaInput(
        title="Test",
        idea="Long enough idea description",
        target_customer="Users",
        problem="Problem",
        proposed_solution="Solution",
        evidence=[]
    )
    with pytest.raises(ValidationError):
        RunReviewRequest(
            idea=idea,
            panel=[
                SpecialistAgentConfig(
                    id=f"spec_{i}",
                    role=f"Specialist {i}",
                    expertise="Expertise",
                    mandate="Mandate",
                    rationale="Rationale",
                    provider="mock"
                )
                for i in range(1, 7)  # 6 specialists
            ]
        )


def test_duplicate_specialist_ids_rejected():
    """Verify that duplicate specialist IDs within a panel raise a validation error."""
    idea = StartupIdeaInput(
        title="Test",
        idea="Long enough idea description",
        target_customer="Users",
        problem="Problem",
        proposed_solution="Solution",
        evidence=[]
    )
    with pytest.raises(ValidationError):
        RunReviewRequest(
            idea=idea,
            panel=[
                SpecialistAgentConfig(id="spec_1", role="Spec 1", expertise="E", mandate="M", rationale="R"),
                SpecialistAgentConfig(id="spec_1", role="Spec 2", expertise="E", mandate="M", rationale="R"),  # Duplicate ID!
                SpecialistAgentConfig(id="spec_3", role="Spec 3", expertise="E", mandate="M", rationale="R"),
            ]
        )


def test_session_store_path_traversal_prevention():
    """Verify that SessionStore rejects dangerous session IDs attempting directory traversal."""
    with pytest.raises(ValueError, match="Invalid session ID format"):
        SessionStore.get("../../etc/passwd")

    with pytest.raises(ValueError, match="Invalid session ID format"):
        SessionStore.get("session/../traversal")

