"""
Tests for evidence grounding in the Multiple AI Review Board.
Verifies that evidence sufficiency is evaluated strictly on the supplied evidence items,
preventing keyword-based hallucinations (e.g. eBPF ideas with zero evidence must be marked insufficient).
"""

import pytest
from app.schemas.review_board_schema import (
    StartupIdeaInput,
    EvidenceItem,
    SpecialistAgentConfig,
)
from app.services.review_orchestrator import ReviewBoardOrchestrator


def _get_panel():
    return [
        SpecialistAgentConfig(
            id=f"spec_{i}",
            role=f"Domain Specialist {i}",
            expertise="Systems Architecture and Compliance",
            mandate="Evaluate technical bottlenecks",
            rationale="Crucial technical angle",
            provider="mock",
            model="mock-deterministic"
        )
        for i in range(1, 4)
    ]


@pytest.mark.anyio
async def test_ebpf_idea_with_zero_evidence_rated_insufficient():
    """Verify that an eBPF idea with ZERO evidence is rated insufficient, NOT sufficient."""
    idea_zero_evidence = StartupIdeaInput(
        title="DevPulse eBPF Tracing",
        idea="Continuous distributed tracing using eBPF probes for Kubernetes microservices.",
        target_customer="Platform Engineers",
        problem="High APM overhead",
        proposed_solution="Zero-code kernel eBPF probes",
        evidence=[]  # Zero evidence supplied
    )

    orchestrator = ReviewBoardOrchestrator()
    session = await orchestrator.execute_board(idea=idea_zero_evidence, panel=_get_panel())

    assert session.combined_review is not None
    ev_status = session.combined_review.evidence_sufficiency.status
    # MUST be insufficient, NOT sufficient!
    assert ev_status == "insufficient"
    assert "No empirical evidence was supplied" in session.combined_review.evidence_sufficiency.analysis


@pytest.mark.anyio
async def test_thin_anecdotal_evidence_rated_thin():
    """Verify that an idea with only an anecdotal testimonial is rated thin."""
    idea_anecdotal = StartupIdeaInput(
        title="SleepPillow Neurotech",
        idea="Brainwave acoustic sleep pillow.",
        target_customer="Insomniacs",
        problem="Sleep onset delay",
        proposed_solution="Piezo acoustic frequencies",
        evidence=[
            EvidenceItem(
                id="E1",
                source="Founder Personal Diary",
                summary="Slept 8 hours on prototype",
                data_type="anecdote"
            )
        ]
    )

    orchestrator = ReviewBoardOrchestrator()
    session = await orchestrator.execute_board(idea=idea_anecdotal, panel=_get_panel())

    assert session.combined_review is not None
    ev_status = session.combined_review.evidence_sufficiency.status
    assert ev_status == "thin"


@pytest.mark.anyio
async def test_multiple_empirical_items_do_not_validate_unresolved_assumptions():
    """Benchmarks and interviews alone do not demonstrate coverage of critical assumptions."""
    idea_backed = StartupIdeaInput(
        title="DevPulse eBPF Tracing",
        idea="Continuous distributed tracing using eBPF probes for Kubernetes microservices.",
        target_customer="Platform Engineers",
        problem="High APM overhead",
        proposed_solution="Zero-code kernel eBPF probes",
        evidence=[
            EvidenceItem(
                id="E1",
                source="50-node synthetic benchmark",
                summary="1.18% CPU overhead",
                data_type="benchmark"
            ),
            EvidenceItem(
                id="E2",
                source="12 customer interviews",
                summary="10 of 12 confirm APM bill fatigue",
                data_type="customer_interview"
            )
        ]
    )

    orchestrator = ReviewBoardOrchestrator()
    session = await orchestrator.execute_board(idea=idea_backed, panel=_get_panel())

    assert session.combined_review is not None
    ev_status = session.combined_review.evidence_sufficiency.status
    assert ev_status == "thin"
    analysis = session.combined_review.evidence_sufficiency.analysis
    assert "1.18% CPU overhead" in analysis
    assert "10 of 12 confirm APM bill fatigue" in analysis
    assert "Untested assumptions:" in analysis

