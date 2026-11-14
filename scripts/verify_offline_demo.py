#!/usr/bin/env python3
"""Verify the three real offline API workflows and save isolated, inspectable artifacts.

No UI acceptance is implied. Live provider adapters are explicitly forbidden.
Run from the repository with the backend dependencies installed.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient
from app.main import app
from app.models.connectors.gemini_adapter import GeminiAdapter
from app.models.connectors.mock_adapter import DeterministicMockAdapter
from app.models.connectors.openai_adapter import OpenAIAdapter
import app.services.session_store as storage

EXPECTATIONS = {
    "devtool_ebpf": ("DevPulse", ["installation and configuration friction", "kernel incompatibility", "sensitive telemetry", "budget-holder commitment"],
                     ["assistance requests", "paired baseline", "unauthorized access", "actual commitments"]),
    "ecommerce_d2c": ("GlowGreen", ["return friction", "repeat purchases", "microbial safety", "contribution margin"],
                      ["rejected item", "paid renewals", "qualified laboratory", "per-order ledger"]),
    "thin_evidence_neuro": ("QuantumSleep", ["confounding", "mechanical degradation", "therapeutic marketing may outrun"],
                           ["controlled, blinded study", "mechanical loading", "claim-by-claim"]),
}


def canonical(experiment):
    return json.dumps(experiment, sort_keys=True)


def verify(client, key, tasks):
    name, risks, designs = EXPECTATIONS[key]
    checks = []
    def check(label, condition):
        checks.append({"check": label, "passed": bool(condition)})
        if not condition:
            raise RuntimeError(f"{name}: {label}")

    idea = client.get("/api/review-board/presets").json()[key]["idea"]
    start = len(tasks)
    generated = client.post("/api/review-board/generate-panel", json={"idea": idea, "provider": "mock"})
    generated.raise_for_status()
    panel = generated.json()
    sid = f"demo-{key}-{uuid.uuid4()}"
    request = {"session_id": sid, "idea": idea, "panel": panel,
               "budget_config": {"call_cap": 20, "token_cap": 50000, "timeout_seconds": 12, "max_retries": 0}}
    result = client.post("/api/review-board/run", json=request)
    result.raise_for_status()
    session = result.json()
    feedbacks = session["specialist_reviews"]
    combined = session["combined_review"]
    check("complete mock workflow without fallback or false specialist-failure warning",
          session["status"] == "completed" and not combined["is_fallback"]
          and combined["failure_impact_analysis"] is None and
          all(r["status"] == "success" and r["provider"] == "mock" and r["is_simulated"] for r in feedbacks))
    check("substantively distinct domain risks and validation interventions", len(feedbacks) == len(risks) and all(
        risk in " ".join(r["risks"]).lower() and design in r["validation_experiment"]["test_design"].lower()
        for r, risk, design in zip(feedbacks, risks, designs)))
    by_id = {r["specialist_id"]: r for r in feedbacks}
    check("unique specialist results", len(by_id) == len(panel))
    supplied_ids = {e["id"].strip().upper() for e in idea["evidence"]}
    check("citations refer only to supplied evidence", all(
        set(r["evidence_citations"]) <= supplied_ids and not r["invalid_citations"] for r in feedbacks))
    debates = session["challenge_round"]
    check("bounded debate count", len(debates) == (2 if len(panel) >= 4 else 1))
    for index, exchange in enumerate(debates, 1):
        a, b = by_id[exchange["challenger_id"]], by_id[exchange["target_specialist_id"]]
        check(f"exchange {index} cites both actual risks and the target's actual test",
              a["specialist_id"] != b["specialist_id"] and
              any(risk in exchange["challenge_point"] for risk in a["risks"]) and
              any(risk in exchange["challenge_point"] for risk in b["risks"]) and
              b["validation_experiment"]["test_design"] in exchange["challenge_point"])
        check(f"exchange {index} qualifies the actual test criteria without claiming new evidence",
              b["validation_experiment"]["success_metric"] in exchange["reasoning_adjustment"] and
              a["validation_experiment"]["success_metric"] in exchange["reasoning_adjustment"] and
              "No new evidence or experiment results" in exchange["reasoning_adjustment"])
    priorities = " ".join(combined["priorities"])
    check("coordinator priorities retain actual specialist risks", all(
        risk in priorities for r in feedbacks for risk in r["risks"]))
    check("coordinator preserves the exact specialist hypotheses, designs and metrics",
          {canonical(e) for e in combined["next_experiments"]} ==
          {canonical(r["validation_experiment"]) for r in feedbacks})
    check("coordinator retains debate qualifications", all(
        e["reasoning_adjustment"] in priorities for e in debates))
    assessment = combined["evidence_sufficiency"]
    check("evidence limitations and supplied content are disclosed", assessment["status"] == "thin" and
          "independent corroboration" in assessment["analysis"] and
          all(e["summary"] in assessment["analysis"] for e in idea["evidence"]))
    check("no invented disagreement or unsupported consensus", combined["disagreements"] == [] and
          "not demonstrated consensus" in combined["summary"])
    if key == "thin_evidence_neuro":
        check("founder diary is insufficient for clinical efficacy",
              "insufficient to establish causality, clinical efficacy" in assessment["analysis"] and
              "20-person" not in json.dumps(combined) and "30% of proceeds" not in json.dumps(combined))
    check("coordinator provenance explicitly identifies simulation", combined["summary"].startswith("[Deterministic mock synthesis; provider=mock;"))
    reopened = client.get(f"/api/review-board/sessions/{sid}")
    reopened.raise_for_status()
    saved = json.loads((storage.STORAGE_DIR / f"{sid}.json").read_text())
    check("persisted JSON and GET results exactly match the final API result", reopened.json() == saved == session)
    count = len(tasks)
    repeated = client.post("/api/review-board/run", json=request)
    stream = client.get(f"/api/review-board/sessions/{sid}/events")
    check("completed replay and subscription perform zero provider calls", repeated.status_code == 200 and
          repeated.json() == session and stream.status_code == 200 and '"type": "session_final"' in stream.text and len(tasks) == count)
    summary = session["execution_summary"]
    check("run ledger and recorded adapter attempts agree", summary["calls_made"] == len(tasks) - start - 1 and
          summary["calls_made"] == len(summary["provider_attempts"]) and
          summary["total_tokens"] == sum(a["total_tokens"] for a in summary["provider_attempts"]) and
          summary["estimated_tokens"] == summary["reported_tokens"] == summary["reserved_tokens"] == 0 and
          summary["simulated_tokens"] == summary["total_tokens"] and not summary["budget_stopped"])
    return {"preset": name, "session_id": sid, "status": session["status"], "checks": checks,
            "checks_passed": len(checks), "calls_in_run": summary["calls_made"],
            "calls_including_panel_generation": len(tasks) - start, "simulated_tokens": summary["total_tokens"],
            "evidence_status": assessment["status"], "saved_file": str(storage.STORAGE_DIR / f"{sid}.json")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    output = (args.output_dir or ROOT / "data/saved_reviews/demo-verification" / timestamp).resolve()
    output.mkdir(parents=True, exist_ok=False)
    sessions = output / "sessions"
    tasks = []
    original = DeterministicMockAdapter.call
    async def record(self, **kwargs):
        tasks.append(kwargs["task"])
        return await original(self, **kwargs)
    async def forbidden(*args, **kwargs):
        raise RuntimeError("Live provider calls are forbidden in offline demo verification")
    report = {"git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
              "executed_at_utc": timestamp, "manual_ui_acceptance": "NOT EXECUTED; developer confirmation required",
              "live_provider_calls_allowed": False, "workflows": []}
    try:
        with patch.object(storage, "STORAGE_DIR", sessions), patch.object(DeterministicMockAdapter, "call", record), \
                patch.object(OpenAIAdapter, "call", forbidden), patch.object(GeminiAdapter, "call", forbidden), TestClient(app) as client:
            for key in EXPECTATIONS:
                report["workflows"].append(verify(client, key, tasks))
        report["passed"] = True
    except Exception as exc:
        report["passed"] = False
        report["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        (output / "verification.json").write_text(json.dumps(report, indent=2) + "\n")
        print(f"Verification artifacts: {output}")
    for workflow in report["workflows"]:
        print(f"{workflow['preset']}: PASS ({workflow['checks_passed']} checks, {workflow['calls_in_run']} run calls, {workflow['simulated_tokens']} simulated tokens)")
    print("Manual UI acceptance: pending developer verification")


if __name__ == "__main__":
    main()
