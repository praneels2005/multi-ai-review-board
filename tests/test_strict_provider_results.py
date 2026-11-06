"""Strict payload validation and truthful stage failures using real workflow paths."""
import asyncio
import json
from copy import deepcopy
from types import SimpleNamespace

import pytest

from app.models.connectors.base_connector import NormalizedProviderResponse, BaseAIAdapter
from app.models.connectors.mock_adapter import DeterministicMockAdapter
from app.models.connectors.openai_adapter import OpenAIAdapter
from app.models.connectors.gemini_adapter import GeminiAdapter
from app.schemas.provider_results import validate_result, ResponseFailure
from app.schemas.review_board_schema import BudgetConfig
from app.services.panel_service import PanelService
from app.services.review_orchestrator import ReviewBoardOrchestrator


TASKS = ("panel_generation", "specialist_review", "challenge_generation", "challenge_response", "coordinator_synthesis")


def response(data, error=None):
    return NormalizedProviderResponse(raw_text=json.dumps(data), parsed_json=data,
        error=error, provider="mock", model="mock-deterministic", is_simulated=True, latency_ms=0)


@pytest.fixture(scope="module")
def board():
    async def run():
        idea = PanelService.get_presets()["devtool_ebpf"]["idea"]
        panel = await PanelService.generate_panel(idea)
        session = await ReviewBoardOrchestrator().execute_board(idea, panel)
        return idea, panel, session
    return asyncio.run(run())


@pytest.fixture
def valid(board):
    _, panel, session = board
    return {
        "panel_generation": {"specialists": [s.model_dump() for s in panel]},
        "specialist_review": session.specialist_reviews[0].model_dump(),
        "challenge_generation": {"challenge_point": session.challenge_round[0].challenge_point},
        "challenge_response": {"response": session.challenge_round[0].response,
                               "reasoning_adjustment": session.challenge_round[0].reasoning_adjustment},
        "coordinator_synthesis": session.combined_review.model_dump(),
    }


@pytest.mark.parametrize("task", TASKS)
def test_valid_results_preserve_required_content(valid, task):
    result = validate_result(task, response(valid[task]))
    for key, value in result.items():
        assert value == valid[task][key]


@pytest.mark.parametrize("task", TASKS)
def test_missing_required_fields_never_get_success_defaults(task):
    with pytest.raises(ResponseFailure, match="schema_validation"):
        validate_result(task, response({}))


@pytest.mark.parametrize("task,key,value", [
    ("panel_generation", "specialists", "three specialists"),
    ("specialist_review", "risks", "a risk"),
    ("specialist_review", "strengths", [23]),
    ("specialist_review", "questions", []),
    ("specialist_review", "evidence_citations", [4]),
    ("challenge_generation", "challenge_point", {"text": "point"}),
    ("challenge_response", "response", 42),
    ("challenge_response", "reasoning_adjustment", "  "),
    ("coordinator_synthesis", "priorities", "priority"),
    ("coordinator_synthesis", "next_experiments", {}),
    ("coordinator_synthesis", "evidence_sufficiency", {"status": "sufficient"}),
    ("coordinator_synthesis", "evidence_sufficiency", {"status": "excellent", "analysis": "claim"}),
])
def test_wrong_types_and_blank_required_values_rejected(valid, task, key, value):
    data = valid[task]
    data[key] = value
    with pytest.raises(ResponseFailure, match="schema_validation"):
        validate_result(task, response(data))


@pytest.mark.parametrize("task", ["specialist_review", "coordinator_synthesis"])
@pytest.mark.parametrize("experiment", [{"hypothesis": "Test it"}, [], "an experiment", {"hypothesis": "H", "test_design": "D", "success_metric": 2}])
def test_nested_experiments_cannot_get_placeholders(valid, task, experiment):
    data = valid[task]
    data["validation_experiment" if task == "specialist_review" else "next_experiments"] = experiment if task == "specialist_review" else [experiment]
    with pytest.raises(ResponseFailure, match="schema_validation"):
        validate_result(task, response(data))


def test_optional_fields_and_empty_coordinator_collections_remain_valid(valid):
    specialist = valid["specialist_review"]
    specialist.pop("validation_experiment")
    specialist.pop("evidence_citations")
    specialist.pop("assumptions_and_unknowns")
    parsed = validate_result("specialist_review", response(specialist))
    assert parsed["validation_experiment"] is None and parsed["evidence_citations"] == []
    coordinator = valid["coordinator_synthesis"]
    coordinator.update(disagreements=[], next_experiments=[], priorities=[])
    assert validate_result("coordinator_synthesis", response(coordinator))["disagreements"] == []


@pytest.mark.parametrize("raw,category", [('not json', 'malformed_json'), ('[]', 'schema_validation'), ('null', 'schema_validation'), ('{"summary":"Looks good"}', 'schema_validation')])
def test_parser_distinguishes_syntax_from_schema(raw, category):
    parsed, error = BaseAIAdapter.parse_output(raw, "coordinator_synthesis")
    assert error.startswith(category + ":")
    with pytest.raises(ResponseFailure) as raised:
        validate_result("coordinator_synthesis", response(parsed, error))
    assert raised.value.kind == category


@pytest.mark.parametrize("mutation", ["duplicates", "too_many", "missing_role", "bad_provider", "missing_mandate"])
def test_panel_does_not_repair_invalid_configurations(valid, mutation):
    data = valid["panel_generation"]
    specs = data["specialists"]
    if mutation == "duplicates":
        specs[1]["id"] = specs[0]["id"]
    elif mutation == "too_many":
        specs.extend(deepcopy(specs))
    elif mutation == "bad_provider":
        specs[0]["provider"] = "nonexistent"
    else:
        specs[0].pop("role" if mutation == "missing_role" else "mandate")
    with pytest.raises(ResponseFailure, match="schema_validation"):
        validate_result("panel_generation", response(data))


def inject_invalid(monkeypatch, task, payload):
    original = DeterministicMockAdapter._generate_deterministic_content
    def generate(self, selected, system_prompt, user_prompt):
        return deepcopy(payload) if selected == task else original(self, selected, system_prompt, user_prompt)
    monkeypatch.setattr(DeterministicMockAdapter, "_generate_deterministic_content", generate)


def test_schema_invalid_specialist_is_failed_without_invented_findings(board, monkeypatch):
    idea, panel, _ = board
    inject_invalid(monkeypatch, "specialist_review", {"strengths": ["Unjustified positive"]})
    session = asyncio.run(ReviewBoardOrchestrator(BudgetConfig(max_retries=0)).execute_board(idea, panel))
    assert session.status == "partial_failure"
    for r in session.specialist_reviews:
        assert r.status == "failed" and "schema_validation" in r.error_message
        assert r.strengths == [] and r.risks == [] and r.validation_experiment is None
    assert session.challenge_round == []
    assert session.combined_review.next_experiments == []


@pytest.mark.parametrize("task,payload", [("challenge_generation", {"challenge_point": 9}), ("challenge_response", {"response": "Defense without adjustment"})])
def test_invalid_debate_stage_is_reported_without_false_specialist_warning(board, monkeypatch, task, payload):
    idea, panel, _ = board
    inject_invalid(monkeypatch, task, payload)
    events = []
    session = asyncio.run(ReviewBoardOrchestrator().execute_board(idea, panel, progress_callback=events.append))
    assert session.status == "partial_failure"
    assert session.challenge_round == []
    assert session.execution_summary["failures_encountered"] == 2
    failures = [e for e in events if e["type"] == "challenge_failed"]
    assert len(failures) == 2 and all("schema_validation" in e["error"] for e in failures)
    assert session.combined_review.failure_impact_analysis is None
    assert all(r.status == "success" for r in session.specialist_reviews)


@pytest.mark.parametrize("failed_exchange", [1, 2])
def test_valid_exchange_survives_a_different_failed_exchange(board, monkeypatch, failed_exchange):
    idea, panel, _ = board
    original = DeterministicMockAdapter._generate_deterministic_content
    calls = 0
    def generate(self, task, system_prompt, user_prompt):
        nonlocal calls
        if task == "challenge_response":
            calls += 1
            if calls == failed_exchange:
                return {"response": "Incomplete"}
        return original(self, task, system_prompt, user_prompt)
    monkeypatch.setattr(DeterministicMockAdapter, "_generate_deterministic_content", generate)
    session = asyncio.run(ReviewBoardOrchestrator().execute_board(idea, panel))
    assert session.status == "partial_failure"
    assert len(session.challenge_round) == 1
    saved = session.challenge_round[0]
    assert saved.reasoning_adjustment in " ".join(session.combined_review.priorities)
    assert session.execution_summary["failures_encountered"] == 1
    assert session.combined_review.failure_impact_analysis is None


@pytest.mark.parametrize("payload", [{"summary": "Looks good"}, {"summary": "Fine", "priorities": [], "disagreements": [], "next_experiments": [{"hypothesis": "H"}], "evidence_sufficiency": {"status": "thin", "analysis": "Unknown"}, "disclaimer": "Decision support"}])
def test_invalid_coordinator_triggers_truthful_fallback(board, monkeypatch, payload):
    idea, panel, _ = board
    inject_invalid(monkeypatch, "coordinator_synthesis", payload)
    session = asyncio.run(ReviewBoardOrchestrator().execute_board(idea, panel))
    result = session.combined_review
    assert session.status == "partial_failure"
    assert result.status == "failed" and result.is_fallback
    assert "schema_validation" in result.summary
    assert result.next_experiments == [] and result.disagreements == []
    assert "fallback" in result.failure_impact_analysis
    assert all(r.status == "success" for r in session.specialist_reviews)


@pytest.mark.parametrize("simulation,category,status", [("malformed_output", "malformed_json", "failed"), ("provider_error", "provider_error", "failed"), ("timeout", "timeout", "timed_out")])
def test_partial_specialist_failure_keeps_successful_findings(board, simulation, category, status):
    idea, panel, _ = board
    changed = deepcopy(panel)
    changed[1].simulate_failure = simulation
    session = asyncio.run(ReviewBoardOrchestrator(BudgetConfig(max_retries=0, timeout_seconds=0.1)).execute_board(idea, changed))
    failed = session.specialist_reviews[1]
    assert failed.status == status and category in failed.error_message
    assert failed.validation_experiment is None and failed.risks == [] and failed.strengths == []
    successes = [r for r in session.specialist_reviews if r.status == "success"]
    assert len(successes) == 3
    for review in successes:
        assert review.risks[0] in " ".join(session.combined_review.priorities)
        assert review.validation_experiment in session.combined_review.next_experiments
    assert changed[1].role in session.combined_review.failure_impact_analysis


def test_live_panel_invalid_output_is_explicit_mock_fallback(board, monkeypatch):
    idea, _, _ = board
    class Invalid:
        async def call(self, **kwargs):
            return response({"specialists": [{"id": "broken"}]})
    import app.services.panel_service as module
    monkeypatch.setattr(module, "get_provider_adapter", lambda provider: Invalid() if provider == "openai" else DeterministicMockAdapter())
    panel = asyncio.run(PanelService.generate_panel(idea, provider="openai"))
    assert 3 <= len(panel) <= 5
    assert all(s.provider == "mock" and s.model == "mock-deterministic" for s in panel)
    assert all(s.rationale.startswith("[EXPLICIT MOCK FALLBACK: openai schema_validation]") for s in panel)


def test_invalid_mock_panel_is_not_masked_by_another_fallback(board, monkeypatch):
    idea, _, _ = board
    inject_invalid(monkeypatch, "panel_generation", {"specialists": []})
    with pytest.raises(ResponseFailure, match="schema_validation"):
        asyncio.run(PanelService.generate_panel(idea))


@pytest.mark.parametrize("provider", ["openai", "gemini"])
@pytest.mark.parametrize("raw,category", [('not json', 'malformed_json'), ('[]', 'schema_validation'), ('{"summary":"Looks good"}', 'schema_validation')])
def test_live_adapter_parsing_and_schema_errors_remain_distinct(provider, raw, category):
    adapter = OpenAIAdapter(api_key="test-key") if provider == "openai" else GeminiAdapter(api_key="test-key")
    class Fake:
        async def create(self, **kwargs):
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=raw))], usage=None)
        def generate_content(self, **kwargs):
            return SimpleNamespace(text=raw)
    fake = Fake()
    adapter._client = SimpleNamespace(chat=SimpleNamespace(completions=fake), models=fake)
    result = asyncio.run(adapter.call("S", "U", task="coordinator_synthesis"))
    assert result.error.startswith(category + ":")
    assert result.is_simulated is False


@pytest.mark.parametrize("provider", ["openai", "gemini"])
def test_live_api_errors_and_parsed_content_redact_credentials(provider):
    secret = "private-provider-credential"
    adapter = OpenAIAdapter(api_key=secret) if provider == "openai" else GeminiAdapter(api_key=secret)
    class Fake:
        async def create(self, **kwargs):
            raise ConnectionError(f"upstream rejected {secret}")
        def generate_content(self, **kwargs):
            raise ConnectionError(f"upstream rejected {secret}")
    fake = Fake()
    adapter._client = SimpleNamespace(chat=SimpleNamespace(completions=fake), models=fake)
    with pytest.raises(RuntimeError) as raised:
        asyncio.run(adapter.call("S", "U"))
    assert "API Error" in str(raised.value) and secret not in str(raised.value)
    raw = json.dumps({"challenge_point": f"Reported {secret}"})
    class ValidFake:
        async def create(self, **kwargs):
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=raw))], usage=None)
        def generate_content(self, **kwargs):
            return SimpleNamespace(text=raw)
    good = ValidFake()
    adapter._client = SimpleNamespace(chat=SimpleNamespace(completions=good), models=good)
    result = asyncio.run(adapter.call("S", "U", task="challenge_generation"))
    assert result.error is None and secret not in result.raw_text
    assert secret not in result.parsed_json["challenge_point"]


@pytest.mark.parametrize("task", ["specialist_review", "coordinator_synthesis"])
def test_provider_declared_fallback_cannot_be_accepted_as_normal_success(valid, task):
    data = valid[task]
    data["is_fallback"] = True
    with pytest.raises(ResponseFailure, match="not a successful assessment"):
        validate_result(task, response(data))


def test_normalized_api_error_is_not_misclassified_as_malformed_json():
    with pytest.raises(ResponseFailure) as raised:
        validate_result("specialist_review", response(None, "Rate limit exceeded"))
    assert raised.value.kind == "provider_error"


@pytest.mark.parametrize("provider", ["openai", "gemini"])
def test_live_timeouts_remain_timeouts(provider):
    adapter = OpenAIAdapter(api_key="test-key") if provider == "openai" else GeminiAdapter(api_key="test-key")
    class Fake:
        async def create(self, **kwargs):
            raise asyncio.TimeoutError()
        def generate_content(self, **kwargs):
            raise asyncio.TimeoutError()
    fake = Fake()
    adapter._client = SimpleNamespace(chat=SimpleNamespace(completions=fake), models=fake)
    with pytest.raises(asyncio.TimeoutError) as raised:
        asyncio.run(adapter.call("S", "U"))
    assert "timed out" in str(raised.value)
