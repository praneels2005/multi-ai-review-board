"""Behavioral regressions for extractive debate, synthesis and provenance."""
import asyncio
import json
from copy import deepcopy

import pytest

from app.models.connectors.mock_adapter import DeterministicMockAdapter
from app.models.connectors.mock_deliberation import (
    challenge, respond, synthesize, review_context, select_pairs,
)
from app.schemas.review_board_schema import BudgetConfig, EvidenceItem
from app.services.panel_service import PanelService
from app.services.review_orchestrator import ReviewBoardOrchestrator


@pytest.fixture(scope="module")
def boards():
    async def run():
        results = {}
        for key, preset in PanelService.get_presets().items():
            idea = preset["idea"]
            panel = await PanelService.generate_panel(idea)
            session = await ReviewBoardOrchestrator().execute_board(idea, panel)
            results[key] = idea, panel, session
        return results
    return asyncio.run(run())


def payload(board):
    idea, _, session = board
    return {"idea": idea.model_dump(), "reviews": [review_context(r) for r in session.specialist_reviews],
            "challenges": [c.model_dump() for c in session.challenge_round]}


def pair_payload(board):
    idea, panel, session = board
    panel_map = {s.id: s for s in panel}
    a, b = select_pairs(session.specialist_reviews, panel_map)[0]
    return {"idea": idea.model_dump(), "challenger": review_context(a, panel_map[a.specialist_id]),
            "target": review_context(b, panel_map[b.specialist_id])}


@pytest.mark.parametrize("key,concerns", [
    ("devtool_ebpf", ["installation and configuration friction", "kernel incompatibility", "sensitive telemetry", "budget-holder commitment"]),
    ("ecommerce_d2c", ["return friction", "repeat purchases", "microbial safety", "contribution margin"]),
    ("thin_evidence_neuro", ["confounding", "mechanical degradation", "therapeutic marketing may outrun"]),
])
def test_preset_debate_and_priorities_come_from_completed_findings(boards, key, concerns):
    _, panel, session = boards[key]
    assert session.status == "completed"
    combined = session.combined_review
    priorities = " ".join(combined.priorities).lower()
    for concern in concerns:
        assert concern in priorities
    reviews = {r.specialist_id: r for r in session.specialist_reviews}
    assert len(session.challenge_round) == (2 if len(panel) >= 4 else 1)
    for c in session.challenge_round:
        a, b = reviews[c.challenger_id], reviews[c.target_specialist_id]
        assert a.specialist_id != b.specialist_id
        assert any(risk in c.challenge_point for risk in a.risks)
        assert any(risk in c.challenge_point for risk in b.risks)
        assert b.validation_experiment.test_design in c.challenge_point
        assert b.validation_experiment.success_metric in c.reasoning_adjustment
        assert a.validation_experiment.success_metric in c.reasoning_adjustment
        assert c.challenge_point in c.response
        assert c.reasoning_adjustment.lower() in priorities
    assert combined.disagreements == []
    assert "not demonstrated consensus" in combined.summary
    assert combined.failure_impact_analysis is None
    # All exact hypotheses, designs and criteria survive aggregation.
    assert {json.dumps(e.model_dump(), sort_keys=True) for e in combined.next_experiments} == {
        json.dumps(r.validation_experiment.model_dump(), sort_keys=True) for r in reviews.values()}


def test_risk_mutation_changes_challenge_response_and_priorities(boards):
    context = pair_payload(boards["devtool_ebpf"])
    before = challenge(json.dumps(context))
    context["challenger"]["risks"] = ["Production trace buffers may overflow during traffic bursts."]
    after = challenge(json.dumps(context))
    assert before != after
    assert context["challenger"]["risks"][0] in after["challenge_point"]
    answer = respond(json.dumps({**context, **after}))
    assert context["challenger"]["risks"][0] in answer["reasoning_adjustment"]
    result = synthesize(json.dumps({"idea": context["idea"], "reviews": [context["challenger"], context["target"]]}))
    assert context["challenger"]["risks"][0] in " ".join(result["priorities"])


def test_experiment_mutation_changes_debate_and_survives_synthesis(boards):
    context = pair_payload(boards["ecommerce_d2c"])
    before = challenge(json.dumps(context))
    experiment = {"hypothesis": "Reusable containers survive the proposed cleaning process.",
                  "test_design": "Record container failures after each cleaning cycle in the proposed protocol.",
                  "success_metric": "Compare failure rate to the preregistered acceptance limit."}
    context["target"]["validation_experiment"] = experiment
    after = challenge(json.dumps(context))
    assert before != after
    assert experiment["test_design"] in after["challenge_point"]
    answer = respond(json.dumps({**context, **after}))
    assert experiment["success_metric"] in answer["reasoning_adjustment"]
    combined = synthesize(json.dumps({"idea": context["idea"], "reviews": [context["target"]]}))
    assert combined["next_experiments"] == [experiment]


@pytest.mark.parametrize("measurement", ["1.18", "24.5"])
def test_cpu_evidence_flows_through_review_debate_and_coordinator(boards, measurement):
    idea, panel, _ = boards["devtool_ebpf"]
    changed = idea.model_copy(deep=True)
    changed.evidence = [EvidenceItem(id="LAB-99", source="Measured workload benchmark",
        summary=f"CPU overhead measured {measurement}%.", data_type="benchmark")]
    async def run():
        orchestrator = ReviewBoardOrchestrator()
        reviews = [await orchestrator._run_single_specialist_with_retry(s, changed, {"LAB-99"}) for s in panel]
        # Include the performance specialist in an explicit exchange to inspect downstream grounding.
        debates = await orchestrator._run_multi_step_challenge_round(changed, reviews[1:3], {s.id: s for s in panel})
        combined = await orchestrator._run_coordinator_synthesis(changed, reviews, debates)
        return reviews, debates, combined
    reviews, debates, combined = asyncio.run(run())
    phrase = f"CPU overhead {measurement}% is " + ("below" if measurement == "1.18" else "not below")
    assert phrase in combined.evidence_sufficiency.analysis
    assert "LAB-99" in debates[0].challenge_point
    if measurement == "24.5":
        assert phrase in debates[0].challenge_point
        assert phrase in " ".join(combined.priorities)
        assert "1.18%" not in combined.model_dump_json()
    assert combined.evidence_sufficiency.status != "sufficient"


def test_source_projection_changes_downstream_evidence_conclusion(boards):
    data = payload(boards["devtool_ebpf"])
    measured = synthesize(json.dumps(data))
    assert "1.18% is below" in measured["evidence_sufficiency"]["analysis"]
    data["idea"]["evidence"][0]["source"] = "Hypothetical CPU projection"
    projected = synthesize(json.dumps(data))
    assert "1.18% is below" not in projected["evidence_sufficiency"]["analysis"]
    assert "numbers are not observed results" in projected["evidence_sufficiency"]["analysis"]


def test_quantumsleep_diary_does_not_establish_clinical_efficacy(boards):
    combined = boards["thin_evidence_neuro"][2].combined_review
    assessment = combined.evidence_sufficiency
    assert assessment.status in {"thin", "insufficient"}
    assert "insufficient to establish causality, clinical efficacy" in assessment.analysis
    assert boards["thin_evidence_neuro"][0].evidence[0].source in assessment.analysis
    text = combined.model_dump_json()
    for invented in ("20-person", "30% of proceeds", "medical certification"):
        assert invented not in text


@pytest.mark.parametrize("kind", ["anecdote", "benchmark", "pilot", "customer_interview"])
def test_multiple_weak_sources_never_promoted_by_type_or_count(boards, kind):
    data = payload(boards["devtool_ebpf"])
    data["idea"]["evidence"] = [{"id": f"weak-{i}", "source": "Founder notes",
        "summary": "A friend said the concept might be useful; no test was run.", "data_type": kind} for i in range(5)]
    result = synthesize(json.dumps(data))["evidence_sufficiency"]
    assert result["status"] != "sufficient"
    assert "do not establish independent corroboration" in result["analysis"]
    assert data["reviews"][0]["missing_assumptions"][0] in result["analysis"]


def test_no_evidence_is_explicitly_insufficient(boards):
    data = payload(boards["devtool_ebpf"])
    data["idea"]["evidence"] = []
    assert synthesize(json.dumps(data))["evidence_sufficiency"]["status"] == "insufficient"


def test_literal_disagreement_and_tradeoff_are_not_confused_with_complementary_risks(boards):
    data = payload(boards["devtool_ebpf"])
    data["reviews"] = data["reviews"][:2]
    a, b = data["reviews"]
    a["validation_experiment"]["hypothesis"] = "Users can install without assistance."
    b["validation_experiment"]["hypothesis"] = "Not users can install without assistance."
    direct = synthesize(json.dumps(data))
    assert len(direct["disagreements"]) == 1
    assert direct["disagreements"][0].startswith("Direct disagreement:")
    assert a["validation_experiment"]["hypothesis"] in direct["disagreements"][0]
    a["validation_experiment"]["hypothesis"] = "Minimize installation time."
    b["validation_experiment"]["hypothesis"] = "Maximize installation time."
    tradeoff = synthesize(json.dumps(data))
    assert tradeoff["disagreements"][0].startswith("Competing tradeoff:")
    b["validation_experiment"]["hypothesis"] = "Minimize telemetry exposure."
    complementary = synthesize(json.dumps(data))
    assert complementary["disagreements"] == []
    assert "not demonstrated consensus" in complementary["summary"]


def test_identical_reviews_do_not_create_disagreement_or_consensus(boards):
    data = payload(boards["devtool_ebpf"])
    a = data["reviews"][0]
    data["reviews"] = [a, {**deepcopy(a), "specialist_id": "copy", "role": "Another reviewer"}]
    data["challenges"] = []
    result = synthesize(json.dumps(data))
    assert result["disagreements"] == []
    assert result["next_experiments"] == [a["validation_experiment"]]
    assert "not demonstrated consensus" in result["summary"]


def test_distinct_metrics_prevent_experiment_deduplication(boards):
    data = payload(boards["devtool_ebpf"])
    a, b = data["reviews"][:2]
    b["validation_experiment"] = deepcopy(a["validation_experiment"])
    b["validation_experiment"]["success_metric"] = "Zero unauthorized telemetry exports in the sandbox."
    data["reviews"] = [a, b]
    assert synthesize(json.dumps(data))["next_experiments"] == [a["validation_experiment"], b["validation_experiment"]]


def test_pair_selection_responds_to_findings_not_ids_or_preset_names(boards):
    _, panel, session = boards["devtool_ebpf"]
    reviews = deepcopy(session.specialist_reviews)
    panel_map = {s.id: s for s in panel}
    # A literal opposing hypothesis must outrank generic complementary pairings.
    reviews[0].validation_experiment.hypothesis = "Minimize installation time."
    reviews[3].validation_experiment.hypothesis = "Maximize installation time."
    pairs = select_pairs(reviews, panel_map)
    assert {r.specialist_id for r in pairs[0]} == {reviews[0].specialist_id, reviews[3].specialist_id}
    before_roles = [(a.role, b.role) for a, b in pairs]
    for i, r in enumerate(reviews):
        old_id = r.specialist_id
        r.specialist_id = f"arbitrary-{i}"
        panel_map[r.specialist_id] = panel_map.pop(old_id)
    assert [(a.role, b.role) for a, b in select_pairs(reviews, panel_map)] == before_roles


def test_failed_reviews_never_supply_findings_or_experiments(boards):
    data = payload(boards["devtool_ebpf"])
    failed = data["reviews"][0]
    failed["status"] = "timed_out"
    failed["risks"] = ["Invented failed-agent risk"]
    failed["validation_experiment"]["hypothesis"] = "Invented failed-agent hypothesis"
    result = synthesize(json.dumps(data))
    assert "Invented failed-agent" not in json.dumps(result)
    assert failed["validation_experiment"] not in result["next_experiments"]


def test_specialist_timeout_names_missing_domain_and_degrades_confidence(boards):
    idea, panel, _ = boards["devtool_ebpf"]
    panel = deepcopy(panel)
    panel[1].simulate_failure = "timeout"
    session = asyncio.run(ReviewBoardOrchestrator(BudgetConfig(timeout_seconds=0.1, max_retries=0)).execute_board(idea, panel))
    assert session.status == "partial_failure"
    assert session.specialist_reviews[1].status == "timed_out"
    warning = session.combined_review.failure_impact_analysis
    assert panel[1].role in warning
    assert "degrading overall confidence" in warning
    assert panel[1].role not in " ".join(session.combined_review.priorities)
    assert len(session.combined_review.next_experiments) == 3


def test_non_specialist_failure_counter_does_not_invent_missing_domain(boards):
    idea, _, session = boards["devtool_ebpf"]
    orchestrator = ReviewBoardOrchestrator()
    orchestrator.failures_encountered = 3
    result = asyncio.run(orchestrator._run_coordinator_synthesis(idea, session.specialist_reviews, session.challenge_round))
    assert result.failure_impact_analysis is None


@pytest.mark.parametrize("key", ["devtool_ebpf", "ecommerce_d2c", "thin_evidence_neuro"])
def test_mock_provenance_is_visible_without_schema_changes(boards, key):
    result = boards[key][2].combined_review
    assert result.summary.startswith("[Deterministic mock synthesis; provider=mock; model=mock-deterministic]")
    assert result.status == "success" and not result.is_fallback


def test_determinism_and_input_preservation(boards):
    data = payload(boards["ecommerce_d2c"])
    before = deepcopy(data)
    assert synthesize(json.dumps(data)) == synthesize(json.dumps(data))
    context = pair_payload(boards["ecommerce_d2c"])
    first = challenge(json.dumps(context))
    assert first == challenge(json.dumps(context))
    response_context = json.dumps({**context, **first})
    assert respond(response_context) == respond(response_context)
    assert data == before


def test_missing_provider_debate_output_cannot_fabricate_an_exchange(boards, monkeypatch):
    idea, panel, session = boards["devtool_ebpf"]
    original = DeterministicMockAdapter._generate_deterministic_content
    def empty(self, task, system_prompt, user_prompt):
        return {} if task == "challenge_response" else original(self, task, system_prompt, user_prompt)
    monkeypatch.setattr(DeterministicMockAdapter, "_generate_deterministic_content", empty)
    orchestrator = ReviewBoardOrchestrator()
    result = asyncio.run(orchestrator._run_multi_step_challenge_round(
        idea, session.specialist_reviews, {s.id: s for s in panel}))
    assert result == []
    assert orchestrator.failures_encountered == 2


def test_conflicting_measurements_remain_unresolved_downstream(boards):
    data = payload(boards["devtool_ebpf"])
    data["idea"]["evidence"] = [
        {"id": "LOW", "source": "Lab A", "summary": "1.18% CPU overhead", "data_type": "benchmark"},
        {"id": "HIGH", "source": "Lab B", "summary": "24.5% CPU overhead", "data_type": "benchmark"},
    ]
    result = synthesize(json.dumps(data))["evidence_sufficiency"]
    assert "Conflicting supplied CPU reports" in result["analysis"]
    assert "[LOW]" in result["analysis"] and "[HIGH]" in result["analysis"]
    assert "Reconcile workload and measurement conditions" in result["analysis"]
    assert result["status"] != "sufficient"


def test_overlapping_experiment_receives_justified_defense_not_manufactured_shift(boards):
    context = pair_payload(boards["devtool_ebpf"])
    context["target"] = {**deepcopy(context["challenger"]), "specialist_id": "different-reviewer"}
    point = challenge(json.dumps(context))
    answer = respond(json.dumps({**context, **point}))
    assert context["target"]["validation_experiment"]["test_design"] in answer["response"]
    assert "retain the original criterion" in answer["reasoning_adjustment"]
    assert context["target"]["validation_experiment"]["success_metric"] in answer["reasoning_adjustment"]
    assert "not independent corroboration" in answer["reasoning_adjustment"]


@pytest.mark.parametrize("error,status", [(asyncio.TimeoutError(), "timed_out"), (ConnectionError("provider unavailable"), "failed")])
def test_actual_coordinator_fallback_is_explicit(boards, monkeypatch, error, status):
    idea, _, session = boards["devtool_ebpf"]
    orchestrator = ReviewBoardOrchestrator()
    async def fail(**kwargs):
        raise error
    monkeypatch.setattr(orchestrator, "_safe_provider_call", fail)
    result = asyncio.run(orchestrator._run_coordinator_synthesis(idea, session.specialist_reviews, session.challenge_round))
    assert result.status == status and result.is_fallback
    assert result.summary.startswith("[COORDINATOR")
    assert result.next_experiments == [] and result.disagreements == []
    assert "fallback" in result.failure_impact_analysis
    assert "specialist(s)" not in result.failure_impact_analysis
