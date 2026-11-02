"""
Tests for the multi-step cross-agent debate round.
Verifies that the challenger generates a challenge against the target,
and the target specialist independently responds using their assigned provider.
"""

import pytest
from app.schemas.review_board_schema import (
    StartupIdeaInput,
    SpecialistAgentConfig,
    BudgetConfig,
)
from app.services.review_orchestrator import ReviewBoardOrchestrator


@pytest.mark.anyio
async def test_multi_step_debate_cross_agent_exchange():
    """Verify that challenge items record distinct challenger and target roles and providers."""
    idea = StartupIdeaInput(
        title="DevPulse eBPF Tracing",
        idea="Continuous distributed tracing using eBPF probes for Kubernetes microservices.",
        target_customer="Platform Engineers",
        problem="High APM overhead",
        proposed_solution="Zero-code kernel eBPF probes",
        evidence=[]
    )

    panel = [
        SpecialistAgentConfig(
            id="spec_1",
            role="Developer Experience Specialist",
            expertise="DevEx workflows",
            mandate="Evaluate CLI ergonomics",
            rationale="Essential adoption angle",
            provider="mock",
            model="mock-deterministic"
        ),
        SpecialistAgentConfig(
            id="spec_2",
            role="Kernel Systems Architect",
            expertise="eBPF kernel telemetry",
            mandate="Scrutinize kernel privileges",
            rationale="Performance angle",
            provider="mock",
            model="mock-deterministic"
        ),
        SpecialistAgentConfig(
            id="spec_3",
            role="DevSecOps Auditor",
            expertise="Host security",
            mandate="Audit root permissions",
            rationale="Security angle",
            provider="mock",
            model="mock-deterministic"
        )
    ]

    orchestrator = ReviewBoardOrchestrator()
    session = await orchestrator.execute_board(idea=idea, panel=panel)

    assert len(session.challenge_round) >= 1
    debate_item = session.challenge_round[0]

    # Verify challenger and target are distinct specialists
    assert debate_item.challenger_id != debate_item.target_specialist_id
    assert debate_item.challenger_role != debate_item.target_role

    # Verify challenge, response, and reasoning adjustment are present
    assert len(debate_item.challenge_point) > 10
    assert len(debate_item.response) > 10
    assert len(debate_item.reasoning_adjustment) > 10

    # Verify provider metadata
    assert debate_item.challenger_provider == "mock"
    assert debate_item.target_provider == "mock"
