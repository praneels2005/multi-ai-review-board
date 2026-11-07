"""Bounded, extractive offline debate and synthesis over completed reviews.

No preset lookup or semantic inference: only literal opposing hypotheses/objectives
are classified as disagreements. Other distinct findings are complementary concerns.
Evidence is attributed, never verified by counting sources or by accepting a label.
"""

import json
import re
from itertools import combinations

from app.models.connectors.mock_specialist import _cpu_comparison, _hypothetical_source


DISCLAIMER = "Decision support only. Not an investment recommendation. Consensus among AI agents does not constitute proof of market demand."


def context(prompt):
    try:
        value = json.loads(prompt)
        return value if isinstance(value, dict) else {}
    except (ValueError, TypeError):
        return {}


def review_context(review, specialist=None):
    """Omit timing/usage and retain all substantive findings and specialist scope."""
    data = review.model_dump(exclude={"latency_ms", "token_usage", "cost_estimate_usd"})
    if specialist:
        data["mandate"] = specialist.mandate
        data["expertise"] = specialist.expertise
    return data


def _normal(text):
    return " ".join(text.lower().strip().rstrip(".").split())


def _hypothesis(review):
    return (review.get("validation_experiment") or {}).get("hypothesis", "")


def relationship(a, b):
    """Only recognize literal opposites; never infer disagreement from domain labels."""
    left, right = _normal(_hypothesis(a)), _normal(_hypothesis(b))
    if left and right and (left == "not " + right or right == "not " + left):
        return "Direct disagreement"
    # Explicit opposing objectives on exactly the same quantity, not guessed tensions.
    for first, second in ((left, right), (right, left)):
        if first.startswith("minimize ") and second == "maximize " + first[len("minimize "):]:
            return "Competing tradeoff"
    return "Complementary concerns"


def _finding(review):
    risks = review.get("risks", [])
    # Numerical adverse reports and contradictions deserve attention before generic risks.
    for risk in risks:
        if risk.startswith(("Conflicting supplied CPU reports", "Supplied report [")):
            return risk
    return next(iter(risks or review.get("missing_assumptions", [])), "No specific risk was supplied.")


def _terms(text):
    stop = {"the", "and", "for", "with", "from", "this", "that", "their", "review", "risk",
            "proposed", "target", "customer", "customers", "specialist", "whether", "before"}
    return set(re.findall(r"[a-z]{4,}", text.lower())) - stop


def select_pairs(feedbacks, panel_map):
    """Rank actual related findings, then cover distinct specialists within the old cap."""
    completed = [r for r in feedbacks if r.status == "success"]
    ranked = []
    for i, j in combinations(range(len(completed)), 2):
        a, b = (review_context(completed[k], panel_map.get(completed[k].specialist_id)) for k in (i, j))
        findings_a = _terms(_finding(a) + " " + _hypothesis(a))
        findings_b = _terms(_finding(b) + " " + _hypothesis(b))
        scope_a = _terms(a.get("mandate", "") + " " + a["role"] + " " + a.get("expertise", ""))
        scope_b = _terms(b.get("mandate", "") + " " + b["role"] + " " + b.get("expertise", ""))
        score = (relationship(a, b) != "Complementary concerns",
                 _finding(a) != _finding(b),
                 len(findings_a & findings_b), len(scope_a & scope_b),
                 scope_a != scope_b)
        ranked.append((score, i, j))
    ranked.sort(key=lambda item: (tuple(-int(n) for n in item[0]), item[1], item[2]))
    chosen, used = [], set()
    limit = 2 if len(completed) >= 4 else 1
    for _, i, j in ranked:
        if i in used or j in used:
            continue
        chosen.append((completed[i], completed[j]))
        used.update((i, j))
        if len(chosen) == limit:
            break
    return chosen


def _citation_note(a, b, idea):
    supplied = {e["id"].strip().upper() for e in idea.get("evidence", [])}
    cited = sorted(supplied & set(a.get("evidence_citations", []) + b.get("evidence_citations", [])))
    return (" Cited supplied reports: " + ", ".join(f"[{c}]" for c in cited) + "; citations do not establish validation."
            if cited else " No supplied evidence is cited for this exchange.")


def challenge(prompt):
    data = context(prompt)
    a, b = data.get("challenger", {}), data.get("target", {})
    if not a or not b:
        return {"challenge_point": "Cannot ground a challenge: completed challenger and target reviews were not supplied."}
    kind = relationship(a, b)
    experiment = b.get("validation_experiment") or {}
    question = (f"How will your test '{experiment.get('test_design', 'No test design supplied')}' "
                f"with success metric '{experiment.get('success_metric', 'No success metric supplied')}' "
                f"address or remain limited by my concern '{_finding(a)}'?")
    if kind != "Complementary concerns":
        question += f" Reconcile the proposed hypotheses '{_hypothesis(a)}' and '{_hypothesis(b)}'; neither is an observed result."
    return {"challenge_point": (
        f"{kind}: my review ({a['role']}) raises '{_finding(a)}'; your review ({b['role']}) raises '{_finding(b)}'. "
        f"Your unresolved assumptions: {'; '.join(b.get('missing_assumptions', [])) or 'none recorded'}. "
        + question + _citation_note(a, b, data.get("idea", {}))
    )}


def respond(prompt):
    data = context(prompt)
    a, b = data.get("challenger", {}), data.get("target", {})
    if not a or not b or not data.get("challenge_point"):
        return {"response": "Cannot address the challenge without the original reviews and challenge text.",
                "reasoning_adjustment": "No refinement can be justified from missing structured context."}
    experiment = b.get("validation_experiment") or {}
    peer_experiment = a.get("validation_experiment") or {}
    if _normal(_finding(a)) == _normal(_finding(b)) and experiment == peer_experiment:
        return {
            "response": (f"In response to: {data['challenge_point']} Our recorded concern and proposed test overlap. "
                         f"Retain the test '{experiment.get('test_design', 'not supplied')}' for '{_finding(b)}'."),
            "reasoning_adjustment": (f"Defense of original scope: this exchange supplies no distinct risk or new result, so retain "
                                     f"the original criterion '{experiment.get('success_metric', 'not supplied')}'. "
                                     "Duplicate proposals are not independent corroboration or proof of agreement."),
        }
    return {
        "response": (
            f"In response to: {data['challenge_point']} "
            f"I retain my original concern '{_finding(b)}'. My proposed test is '{experiment.get('test_design', 'not supplied')}', "
            f"judged by '{experiment.get('success_metric', 'not supplied')}'. "
            f"That test alone does not resolve your concern '{_finding(a)}'; "
            f"your proposed hypothesis '{peer_experiment.get('hypothesis', 'not supplied')}' remains a separate validation question."
        ),
        "reasoning_adjustment": (
            f"Qualification: interpret any future result for '{experiment.get('hypothesis', 'the original assessment')}' "
            f"only against '{experiment.get('success_metric', 'an unspecified criterion')}', "
            f"not as clearance of '{_finding(a)}'. Before a joint recommendation, also evaluate the peer criterion "
            f"'{peer_experiment.get('success_metric', 'not supplied; request a criterion')}'. "
            "No new evidence or experiment results were introduced; the exchange does not establish agreement."
        ),
    }


def _evidence(idea, reviews):
    evidence = idea.get("evidence", [])
    if not evidence:
        return {"status": "insufficient", "analysis": "No empirical evidence was supplied. Startup claims and specialist hypotheses remain unverified."}
    reports = [f"Supplied report [{e['id']}] ({e['data_type']}, source: {e['source']}): {e['summary']}" for e in evidence]
    favorable, adverse = _cpu_comparison(idea.get("proposed_solution", ""), evidence)
    limits = []
    for e in evidence:
        if e["data_type"] == "anecdote":
            limits.append(f"[{e['id']}] is anecdotal: insufficient to establish causality, clinical efficacy, safety, or representative demand.")
        if _hypothetical_source(e["source"]):
            limits.append(f"[{e['id']}] is labeled hypothetical or unmeasured; its numbers are not observed results.")
    unknowns = [f"{r['role']}: {item}" for r in reviews for item in r.get("missing_assumptions", [])]
    # A bounded mock cannot authenticate independence, methods, or claim coverage.
    # Retain 'thin' for supplied reports, never promote based on counts/types/labels.
    analysis = " ".join(reports + favorable + adverse + limits)
    analysis += " Evidence remains thin: source labels and multiple items do not establish independent corroboration or coverage of the claims being evaluated."
    if unknowns:
        analysis += " Untested assumptions: " + "; ".join(unknowns)
    analysis += " Methods, relevance, and independent corroboration require verification; this mock cannot certify sufficient evidence."
    return {"status": "thin", "analysis": analysis}


def synthesize(prompt):
    data = context(prompt)
    reviews = [r for r in data.get("reviews", []) if r.get("status") == "success"]
    reviews.sort(key=lambda r: (not _finding(r).startswith(("Conflicting supplied CPU reports", "Supplied report [")),))
    completed_ids = {r["specialist_id"] for r in reviews}
    exchanges = [c for c in data.get("challenges", [])
                 if c["challenger_id"] in completed_ids and c["target_specialist_id"] in completed_ids]
    priorities, experiments, seen = [], [], set()
    for r in reviews:
        risks = list(dict.fromkeys([_finding(r)] + r.get("risks", [])))
        priorities.extend(f"{r['role']}: resolve {risk}" for risk in risks)
        priorities.extend(f"{r['role']}: test unresolved assumption: {a}" for a in r.get("missing_assumptions", []))
        experiment = r.get("validation_experiment")
        if experiment:
            # Deduplicate only matching hypothesis, procedure AND metric. Preserve exact prose.
            key = tuple(_normal(experiment[k]) for k in ("hypothesis", "test_design", "success_metric"))
            if key not in seen:
                experiments.append(experiment)
                seen.add(key)
    for c in exchanges:
        priorities.append(f"Debate qualification ({c['target_role']} responding to {c['challenger_role']}): {c['reasoning_adjustment']}")
    disagreements = []
    for a, b in combinations(reviews, 2):
        kind = relationship(a, b)
        if kind != "Complementary concerns":
            disagreements.append(f"{kind}: {a['role']} proposes '{_hypothesis(a)}'; {b['role']} proposes '{_hypothesis(b)}'. These proposals remain untested.")
    sufficiency = _evidence(data.get("idea", {}), reviews)
    priorities.append("Evidence limitation: " + sufficiency["analysis"])
    summary = (f"Synthesized {len(reviews)} completed specialist reviews and {len(exchanges)} completed exchanges. "
               + ("Unresolved findings: " + "; ".join(f"{r['role']}: {_finding(r)}" for r in reviews) if reviews else "No completed findings are available.")
               + (" Explicit opposing hypotheses/objectives require resolution." if disagreements else
                  " No direct disagreement or competing objective was established by the bounded comparison; distinct risks are complementary concerns, not demonstrated consensus.")
               + " Proposed experiments are unexecuted, and supplied reports remain unverified.")
    return {"summary": summary, "priorities": priorities, "disagreements": disagreements,
            "next_experiments": experiments, "evidence_sufficiency": sufficiency,
            # The orchestrator owns specialist failure handling (Milestone 1A).
            "failure_impact_analysis": None, "disclaimer": DISCLAIMER}
