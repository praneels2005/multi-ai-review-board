"""
Tests for evidence citation validation and invalid citation flagging.
Verifies that cited evidence IDs are matched against supplied evidence,
and hallucinated/unsupplied IDs are explicitly flagged under invalid_citations.
"""

import pytest
from app.schemas.review_board_schema import (
    StartupIdeaInput,
    EvidenceItem,
    SpecialistAgentConfig,
    BudgetConfig,
)
from app.services.review_orchestrator import ReviewBoardOrchestrator


@pytest.mark.anyio
async def test_valid_evidence_citations_recognized():
    """Verify that supplied evidence IDs (E1, E2) are categorized as valid citations."""
    idea = StartupIdeaInput(
        title="DevPulse eBPF Tracing",
        idea="Continuous distributed tracing using eBPF probes for Kubernetes microservices.",
        target_customer="Platform Engineers",
        problem="High APM overhead and SDK maintenance",
        proposed_solution="Zero-code kernel eBPF probes",
        evidence=[
            EvidenceItem(id="E1", source="Lab Benchmark", summary="1.2% CPU overhead", data_type="benchmark"),
            EvidenceItem(id="E2", source="User Interview", summary="10 of 12 leads fatigue", data_type="customer_interview")
        ]
    )

    panel = [
        SpecialistAgentConfig(
            id="spec_1",
            role="Cloud Infrastructure & Kernel Systems Architect",
            expertise="eBPF kernel telemetry",
            mandate="Evaluate overhead benchmarks",
            rationale="Crucial technical angle",
            provider="mock",
            model="mock-deterministic"
        )
    ]

    orchestrator = ReviewBoardOrchestrator()
    session = await orchestrator.execute_board(idea=idea, panel=panel)

    review = session.specialist_reviews[0]
    assert review.status == "success"
    # E1 was cited by the mock adapter and is valid
    assert "E1" in review.evidence_citations
    assert len(review.invalid_citations) == 0


@pytest.mark.anyio
async def test_invalid_citations_flagged_when_unsupplied():
    """Verify that when a review cites an ID not in the supplied evidence list, it is marked invalid."""
    # Idea with NO evidence provided
    idea_no_evidence = StartupIdeaInput(
        title="DevPulse eBPF Tracing",
        idea="Continuous distributed tracing using eBPF probes for Kubernetes microservices.",
        target_customer="Platform Engineers",
        problem="High APM overhead",
        proposed_solution="eBPF probes",
        evidence=[]  # Zero evidence supplied
    )

    panel = [
        SpecialistAgentConfig(
            id="spec_1",
            role="Cloud Infrastructure & Kernel Systems Architect",
            expertise="eBPF kernel telemetry",
            mandate="Evaluate overhead benchmarks",
            rationale="Crucial technical angle",
            provider="mock",
            model="mock-deterministic"
        )
    ]

    orchestrator = ReviewBoardOrchestrator()
    session = await orchestrator.execute_board(idea=idea_no_evidence, panel=panel)

    review = session.specialist_reviews[0]
    # If the agent cited E1 even though no evidence was supplied, E1 MUST be in invalid_citations!
    if "E1" in (review.evidence_citations + review.invalid_citations):
        assert "E1" in review.invalid_citations
        assert "E1" not in review.evidence_citations

