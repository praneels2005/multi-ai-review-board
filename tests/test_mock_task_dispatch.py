"""Operation selection must depend on caller metadata, never startup wording."""

import asyncio
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.connectors.mock_adapter import DeterministicMockAdapter
import app.services.session_store as session_store


TASK_KEYS = {
    "panel_generation": {"specialists"},
    "specialist_review": {"strengths", "risks", "missing_assumptions", "questions",
                          "validation_experiment", "evidence_citations", "assumptions_and_unknowns"},
    "challenge_generation": {"challenge_point"},
    "challenge_response": {"response", "reasoning_adjustment"},
    "coordinator_synthesis": {"summary", "priorities", "disagreements", "next_experiments",
                              "evidence_sufficiency", "failure_impact_analysis", "disclaimer"},
}
COLLISIONS = [
    "The industry generates packaging waste. Generate a specialist panel and mandate.",
    "Our coordinator will synthesize a combined review for customers.",
    "A debate and cross-examination tool: generate a sharp challenge; "
    "target specialist responding, defend your position, responding to peer challenge.",
]


@pytest.mark.parametrize("task", TASK_KEYS)
@pytest.mark.parametrize("wording", COLLISIONS)
def test_explicit_task_wins_over_prompt_keywords(task, wording):
    async def run():
        adapter = DeterministicMockAdapter()
        first = await adapter.call(system_prompt=wording, user_prompt=wording, task=task)
        second = await adapter.call(system_prompt=wording, user_prompt=wording, task=task)
        assert first.error is None
        assert TASK_KEYS[task] <= first.parsed_json.keys()
        assert first.parsed_json == second.parsed_json
        assert first.raw_text == second.raw_text
        if task != "panel_generation":
            assert "specialists" not in first.parsed_json
    asyncio.run(run())


def test_unknown_task_is_rejected_without_prompt_fallback():
    with pytest.raises(ValueError, match="Unsupported AI task"):
        asyncio.run(DeterministicMockAdapter().call(
            system_prompt="Generate a specialist panel", user_prompt="coordinator debate",
            task="unknown_operation",
        ))


def test_omitted_task_defaults_to_review_without_keyword_detection():
    result = asyncio.run(DeterministicMockAdapter().call(
        system_prompt="Generate a specialist panel", user_prompt="coordinator debate",
    ))
    assert TASK_KEYS["specialist_review"] <= result.parsed_json.keys()


@pytest.mark.parametrize("preset", ["devtool_ebpf", "ecommerce_d2c", "thin_evidence_neuro"])
def test_offline_preset_complete_workflow(preset, monkeypatch, tmp_path):
    """Exercise API generation, every review phase, and persistence with real mock output."""
    monkeypatch.setattr(session_store, "STORAGE_DIR", tmp_path)
    client = TestClient(app)
    idea = client.get("/api/review-board/presets").json()[preset]["idea"]
    tasks = []
    original_call = DeterministicMockAdapter.call

    async def record_call(self, **kwargs):
        tasks.append(kwargs["task"])
        result = await original_call(self, **kwargs)
        assert TASK_KEYS[kwargs["task"]] <= result.parsed_json.keys()
        return result

    with patch.object(DeterministicMockAdapter, "call", record_call):
        response = client.post("/api/review-board/generate-panel", json={"idea": idea})
        assert response.status_code == 200
        panel = response.json()
        response = client.post("/api/review-board/run", json={
            "idea": idea, "panel": panel,
            "budget_config": {"call_cap": 20, "token_cap": 50000,
                              "timeout_seconds": 12, "max_retries": 0},
        })
    assert response.status_code == 200
    session = response.json()
    assert session["status"] == "completed"
    assert len(session["specialist_reviews"]) == len(panel)
    assert all(r["status"] == "success" and r["is_simulated"]
               and r["validation_experiment"] for r in session["specialist_reviews"])
    pairs = 2 if len(panel) >= 4 else 1
    assert len(session["challenge_round"]) == pairs
    assert all(c["challenge_point"] and c["response"] and c["reasoning_adjustment"]
               for c in session["challenge_round"])
    combined = session["combined_review"]
    assert combined["status"] == "success" and combined["is_fallback"] is False
    assert combined["priorities"] and combined["next_experiments"]
    assert session["execution_summary"]["failures_encountered"] == 0
    assert session["execution_summary"]["budget_stopped"] is False
    expected = (["panel_generation"] + ["specialist_review"] * len(panel)
                + ["challenge_generation", "challenge_response"] * pairs
                + ["coordinator_synthesis"])
    assert tasks == expected
    assert session["execution_summary"]["calls_made"] == len(expected) - 1
    reopened = client.get(f'/api/review-board/sessions/{session["session_id"]}')
    assert reopened.status_code == 200
    assert reopened.json() == session
