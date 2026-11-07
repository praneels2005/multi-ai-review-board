"""Bounded offline specialist reviews, not semantic analysis or fact verification.

Mandate keyword matches select a review perspective; role and expertise break ties.
Evidence summaries are quoted verbatim as supplied reports. Only an unambiguous CPU
percentage and an explicit solution ceiling receive a numerical comparison.
"""

import json
import re
from decimal import Decimal
from app.models.connectors.mock_archetypes import PERSPECTIVES, GENERAL, Perspective, keyword_hits


def _score(text: str, perspective: Perspective) -> int:
    return len(keyword_hits(text, perspective.terms))


def _perspective(specialist: dict) -> Perspective:
    # Lexicographic priority makes a substantive mandate edit override an old title.
    scores = [tuple(_score(specialist.get(field, ""), p)
                    for field in ("mandate", "role", "expertise")) for p in PERSPECTIVES]
    best = max(range(len(scores)), key=scores.__getitem__)
    return PERSPECTIVES[best] if any(scores[best]) else GENERAL


def _hypothetical_source(source: str) -> bool:
    """Recognize explicit non-observation labels without inferring credibility."""
    return bool(re.search(r"\b(hypothetical|forecast|projection|projected|prediction|predicted|unmeasured)\b", source, re.I))


def _cpu_comparison(solution: str, evidence: list[dict]) -> tuple[list[str], list[str]]:
    """Compare only a narrow, explicit CPU ceiling/observation grammar.

    Source labels can disqualify hypothetical reports; sources never supply metrics.
    No range, negation, hypothetical, multiple-reading, or conflict resolution.
    Ambiguous summaries are still quoted by the caller but not interpreted.
    """
    ceiling = re.findall(r"(?:<|below\s+|under\s+)\s*(\d+(?:\.\d+)?)%\s+CPU overhead", solution, re.I)
    if len(ceiling) != 1 or re.search(r"\b(not|no|never)\b", solution, re.I):
        return [], []
    limit = Decimal(ceiling[0])
    observed = []
    for item in evidence:
        summary = item["summary"]
        if _hypothetical_source(item["source"]):
            continue
        if item["data_type"] != "benchmark" or re.search(
            r"\b(not|no|never|expected|target|claimed?|predicted|hypothetical|baseline|competitor|if|might|could|would|between|approximately|about)\b|[<>≤≥]|\d\s*[-–]\s*\d",
            summary, re.I,
        ):
            continue
        values = re.findall(r"(?<![\w.,+\-])(\d+(?:\.\d+)?)%\s+(?:average\s+)?CPU overhead", summary, re.I)
        values += re.findall(r"CPU overhead\s+(?:(?:was|measured|recorded|of|at)\s+)*(\d+(?:\.\d+)?)%", summary, re.I)
        if len(values) == 1:
            observed.append((item["id"].strip().upper(), values[0], Decimal(values[0]) < limit))
    strengths, risks = [], []
    conflicting = len({within for _, _, within in observed}) > 1
    for evidence_id, value, within in observed:
        text = (f"Supplied report [{evidence_id}]: CPU overhead {value}% is "
                f"{'below' if within else 'not below'} the proposed ceiling {ceiling[0]}%. "
                "This compares reported numbers only; conditions and repeatability are unverified.")
        (strengths if within and not conflicting else risks).append(text)
    if conflicting:
        risks.append("Conflicting supplied CPU reports fall on different sides of the target; do not select only the favorable report. Reconcile workload and measurement conditions.")
    return strengths, risks


def specialist_feedback(user_prompt: str) -> dict:
    """Use JSON context from the orchestrator; legacy raw calls make no factual claims."""
    try:
        context = json.loads(user_prompt)
    except json.JSONDecodeError:
        context = None
    if isinstance(context, dict) and "specialist" in context and "idea" in context:
        from app.schemas.review_board_schema import SpecialistAgentConfig, StartupIdeaInput
        specialist = SpecialistAgentConfig.model_validate(context["specialist"]).model_dump()
        idea = StartupIdeaInput.model_validate(context["idea"]).model_dump()
        structured = True
    else:
        # Existing standalone adapter callers provide plain text. Do not mine it
        # for evidence IDs, numerical results, or a purported specialist identity.
        specialist = {}
        idea = {"idea": user_prompt, "evidence": []}
        structured = False
    perspective = _perspective(specialist)
    evidence = idea["evidence"]
    strengths = [f"Potential strength (unvalidated), {perspective.focus}: {perspective.opportunity}; this depends on the assumption below."]
    risks = [f"Risk to test, {perspective.focus}: {perspective.risk}."]
    assumptions = [f"Assumption to test: {perspective.assumption}."]
    unknowns = ["Unknown: supplied evidence has not been independently verified; its presence does not validate the startup's claims."]
    if structured:
        unknowns.append(f"Review context — role: {specialist['role']}; expertise: {specialist['expertise']}; mandate: {specialist['mandate']}")
        # Quote founder statements as statements, never as established findings.
        for field in ("idea", "target_customer", "problem", "proposed_solution"):
            unknowns.append(f"Founder-supplied {field} (unverified): {idea[field]}")
    else:
        unknowns.append("Unknown: structured specialist mandate and startup fields were not provided; only general validation questions are available.")
    if perspective is GENERAL:
        unknowns.append("Unknown: this mandate does not match an available specialist perspective; the mock cannot supply domain-specific conclusions for it.")
    questions = [perspective.question,
                 f"For the supplied target customer, what evidence would resolve this mandate: {specialist.get('mandate', 'not supplied')}?"]
    citations = []
    for item in evidence:
        evidence_id = item["id"].strip().upper()  # Existing orchestrator citation normalization.
        citations.append(evidence_id)
        unknowns.append(f"Supplied report [{evidence_id}] ({item['data_type']}, source: {item['source']}): {item['summary']}")
        # Lexical relevance only: use the report as a question, not a favorable finding.
        if _score(item["summary"] + " " + item["source"], perspective):
            questions.append(
                f"Evidence follow-up [{evidence_id}] for {perspective.focus}: source {item['source']} reports {item['summary']} "
                f"What methods and conditions connect this report to the assumption that {perspective.assumption}?"
            )
        if _hypothetical_source(item["source"]):
            unknowns.append(f"Evidence limit [{evidence_id}]: the source is labeled hypothetical, projected, predicted, or unmeasured; do not treat its figures as observed results.")
        if item["data_type"] == "anecdote":
            unknowns.append(f"Evidence limit [{evidence_id}]: an anecdote alone cannot establish causality, clinical efficacy, or representative demand.")
    if not evidence:
        risks.append("Insufficient evidence: no supporting evidence was supplied. The proposed benefits remain unverified.")
    elif all(e["data_type"] == "anecdote" for e in evidence):
        risks.append("Insufficient evidence for validation: only anecdotal reports were supplied; controlled effects, safety, and repeatable demand remain unknown.")
    else:
        unknowns.append(f"Unknown: whether the supplied reports adequately test {perspective.focus}; verify methods, relevance, adverse outcomes, and coverage before drawing conclusions.")
    if perspective.focus == "runtime performance":
        favorable, unfavorable = _cpu_comparison(idea.get("proposed_solution", ""), evidence)
        strengths.extend(favorable)
        risks.extend(unfavorable)
    return {
        "strengths": strengths,
        "risks": risks,
        "missing_assumptions": assumptions,
        "questions": questions,
        "validation_experiment": {
            "hypothesis": f"Proposed hypothesis (not a result): {perspective.hypothesis}",
            "test_design": (perspective.design + (
                f" Apply this proposed test to the founder-described solution ({idea['proposed_solution']}) "
                f"with the supplied target customers ({idea['target_customer']}); verify the stated problem "
                f"({idea['problem']}) rather than accepting it as fact."
                if structured else " Define the solution, target customers, and problem before testing."
            )),
            "success_metric": perspective.metric,
        },
        "evidence_citations": list(dict.fromkeys(citations)),
        "invalid_citations": [],
        "assumptions_and_unknowns": unknowns,
    }
