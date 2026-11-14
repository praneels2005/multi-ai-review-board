"""
Tests for failure isolation and coordinator impact analysis.
Verifies that one failing specialist does not bring down the board,
and that the coordinator explicitly explains the impact of the missing role.
"""

import pytest
from app.schemas.review_board_schema import (
    StartupIdeaInput,
    SpecialistAgentConfig,
    BudgetConfig,
)
from app.services.review_orchestrator import ReviewBoardOrchestrator


@pytest.mark.anyio
async def test_failure_isolation_and_coordinator_impact_explanation():
    """Verify that when 1 of 3 specialists fails, the other 2 complete, and coordinator notes impact."""
    idea = StartupIdeaInput(
        title="DevPulse eBPF Tracing",
        idea="Continuous distributed tracing using eBPF probes for Kubernetes microservices.",
        target_customer="Platform Engineers",
        problem="High APM overhead",
        proposed_solution="eBPF probes",
        evidence=[]
    )

    panel = [
        SpecialistAgentConfig(
            id="spec_1",
            role="Developer Experience Specialist",
            expertise="Dev-ex workflows",
            mandate="Evaluate CLI ergonomics",
            rationale="Essential adoption angle",
            provider="mock",
            model="mock-deterministic"
        ),
        SpecialistAgentConfig(
            id="spec_2",
            role="Kernel Systems Architect",
            expertise="eBPF kernel telemetry",
            mandate="Scrutinize kernel compatibility",
            rationale="Essential performance angle",
            provider="mock",
            model="mock-deterministic",
            simulate_failure="provider_error"  # Injected failure
        ),
        SpecialistAgentConfig(
            id="spec_3",
            role="DevSecOps Auditor",
            expertise="Enterprise compliance",
            mandate="Assess root privileges",
            rationale="Essential security angle",
            provider="mock",
            model="mock-deterministic"
        )
    ]

    budget = BudgetConfig(max_retries=0)
    orchestrator = ReviewBoardOrchestrator(budget_config=budget)

    session = await orchestrator.execute_board(idea=idea, panel=panel)

    assert len(session.specialist_reviews) == 3
    statuses = [r.status for r in session.specialist_reviews]
    assert statuses == ["success", "failed", "success"]

    # Session completes as partial failure
    assert session.status == "partial_failure"
    assert session.execution_summary["failures_encountered"] == 1

    # Coordinator still produces synthesis
    assert session.combined_review is not None
    # Coordinator MUST explicitly provide a failure impact analysis explaining the missing role!
    impact = session.combined_review.failure_impact_analysis
    assert impact is not None
    assert len(impact) > 20
    assert "Kernel Systems Architect" in impact or "failed" in impact or "missing" in impact

