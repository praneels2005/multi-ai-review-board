"""
Tests for FastAPI Review Board API endpoints.
Verifies preset loading, dynamic panel generation, running review boards,
persisting sessions, listing history, and reopening/rerunning saved reviews.
"""

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.services.session_store import SessionStore


@pytest.fixture
def client():
    return TestClient(app)


def test_get_presets_endpoint(client):
    """Verify GET /api/review-board/presets returns pre-configured contrasting presets."""
    response = client.get("/api/review-board/presets")
    assert response.status_code == 200
    data = response.json()

    assert "devtool_ebpf" in data
    assert "ecommerce_d2c" in data
    assert "thin_evidence_neuro" in data

    # Verify preset structure
    devtool = data["devtool_ebpf"]
    assert "DevPulse" in devtool["idea"]["title"]
    assert len(devtool["idea"]["evidence"]) >= 1


def test_generate_panel_endpoint(client):
    """Verify POST /api/review-board/generate-panel returns 3-5 specialists."""
    payload = {
        "idea": {
            "title": "CloudCost Optimizer",
            "idea": "Automated Kubernetes cluster rightsizing and spot instance orchestration for AI workloads.",
            "target_customer": "FinOps and DevOps Leads",
            "problem": "Unused GPU/CPU allocations waste millions in cloud budgets.",
            "proposed_solution": "Dynamic cluster scaler driven by real-time queue demand.",
            "evidence": []
        }
    }

    response = client.post("/api/review-board/generate-panel", json=payload)
    assert response.status_code == 200
    specialists = response.json()

    assert 3 <= len(specialists) <= 5
    for s in specialists:
        assert "role" in s
        assert "mandate" in s
        assert "rationale" in s


def test_run_review_board_and_persistence(client):
    """Verify POST /api/review-board/run executes full workflow, saves session, and allows reopening."""
    # 1. Fetch preset
    presets_res = client.get("/api/review-board/presets")
    preset_data = presets_res.json()["devtool_ebpf"]["idea"]

    # 2. Generate panel
    panel_res = client.post("/api/review-board/generate-panel", json={"idea": preset_data})
    panel = panel_res.json()

    # 3. Run Review Board
    run_payload = {
        "idea": preset_data,
        "panel": panel,
        "budget_config": {
            "call_cap": 20,
            "token_cap": 50000,
            "timeout_seconds": 10.0,
            "max_retries": 1
        }
    }

    run_res = client.post("/api/review-board/run", json=run_payload)
    assert run_res.status_code == 200
    session_data = run_res.json()

    session_id = session_data["session_id"]
    assert session_data["status"] == "completed"
    assert len(session_data["specialist_reviews"]) == len(panel)
    assert session_data["combined_review"] is not None
    assert "disclaimer" in session_data["combined_review"]

    # 4. List sessions
    list_res = client.get("/api/review-board/sessions")
    assert list_res.status_code == 200
    sessions_list = list_res.json()
    assert any(s["session_id"] == session_id for s in sessions_list)

    # 5. Reopen saved session
    reopen_res = client.get(f"/api/review-board/sessions/{session_id}")
    assert reopen_res.status_code == 200
    reopened = reopen_res.json()
    assert reopened["session_id"] == session_id
    assert reopened["idea"]["title"] == preset_data["title"]

    # 6. Rerun saved session
    rerun_res = client.post(f"/api/review-board/sessions/{session_id}/rerun")
    assert rerun_res.status_code == 200
    rerun_data = rerun_res.json()
    assert rerun_data["session_id"] == session_id
    assert rerun_data["status"] == "completed"

    # Cleanup test session
    SessionStore.delete(session_id)

