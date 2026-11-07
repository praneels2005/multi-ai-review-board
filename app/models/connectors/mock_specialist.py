"""Bounded offline specialist reviews, not semantic analysis or fact verification.

Mandate keyword matches select a review perspective; role and expertise break ties.
Evidence summaries are quoted verbatim as supplied reports. Only an unambiguous CPU
percentage and an explicit solution ceiling receive a numerical comparison.
"""

import json
import re
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class Perspective:
    terms: tuple[str, ...]
    focus: str
    opportunity: str
    risk: str
    assumption: str
    question: str
    hypothesis: str
    design: str
    metric: str


PERSPECTIVES = (
    Perspective(
        ("developer experience", "cli", "onboarding", "adopt", "configuration", "workflow", "sdk"),
        "developer adoption",
        "reducing setup work could make the proposed tool easier to evaluate",
        "installation and configuration friction may prevent users reaching a useful first result",
        "target users can complete setup without sustained founder assistance",
        "Which installation step prevents a target user reaching their first useful result?",
        "Target users can complete the proposed setup and reach a useful result unaided.",
        "Observe representative target users installing the prototype from its documentation; record blocked steps, completion time, and assistance requests.",
        "Before testing, agree a setup-time ceiling and completion-rate target; compare observed unaided completions and assistance requests against those targets.",
    ),
    Perspective(
        ("infrastructure", "kernel", "cpu", "overhead", "benchmark", "performance", "footprint", "compatibility"),
        "runtime performance",
        "a measurable performance target could make the technical proposal testable",
        "runtime overhead or kernel incompatibility may make the proposed deployment impractical",
        "performance remains acceptable on representative workloads and supported platforms",
        "Which workloads, kernel versions, and baseline measurements define acceptable runtime overhead?",
        "The prototype meets its declared performance target on representative workloads.",
        "Run paired baseline and instrumented workloads across the intended deployment matrix; record CPU overhead, memory, errors, and workload conditions, including adverse results.",
        "Compare measured overhead with the predeclared solution target across the deployment matrix; report uncertainty and every configuration that misses the target.",
    ),
    Perspective(
        ("security", "devsecops", "privilege", "permission", "root", "exfiltration", "redaction", "host", "soc2"),
        "deployment security",
        "a documented permission boundary could make a security review tractable",
        "excessive privileges or sensitive telemetry exposure may block deployment",
        "the deployment can operate within the customer's permission and data-handling policies",
        "What is the minimum permission set, and which sensitive fields can leave the host?",
        "The prototype can perform its intended function within an approved least-privilege boundary.",
        "Prepare a permission and data-flow inventory; ask a target security reviewer to inspect a sandbox deployment and attempt unauthorized access and telemetry leakage.",
        "Record policy violations and required permissions; proceed only when the reviewer accepts the documented boundary and blocking findings are resolved.",
    ),
    Perspective(
        ("gtm", "pricing", "price", "willingness to pay", "buyer", "monetization", "open-core", "contract", "competitive"),
        "buyer commitment",
        "a defined target customer provides a starting point for testing a purchasing decision",
        "interest from users may not translate into budget-holder commitment or viable acquisition",
        "a reachable buyer controls budget and sees enough value to switch",
        "Who authorizes payment, and what concrete commitment would distinguish interest from purchase intent?",
        "Qualified budget holders will make a concrete pilot commitment at an explicitly proposed price.",
        "Present the proposed solution and a clearly labeled trial offer to target budget holders; record price objections, procurement steps, and actual commitments separately from verbal enthusiasm.",
        "Predeclare a commitment criterion and acquisition-cost ceiling; compare qualified commitments and observed acquisition effort with those criteria.",
    ),
    Perspective(
        ("logistics", "supply chain", "return", "shipping", "sanitization", "breakage", "transit", "fulfillment"),
        "reverse logistics",
        "a defined return process could make the proposed reuse loop measurable",
        "return friction, handling losses, or cleaning requirements may undermine the reuse loop",
        "returned items can be collected and prepared for reuse at an acceptable cost",
        "What happens to each item from customer return through inspection and reuse?",
        "The proposed return loop can recover reusable items within agreed operational and cost limits.",
        "Run a traced return-loop pilot with target customers; log each handoff, return delay, postage, cleaning effort, rejected item, and reuse decision.",
        "Predeclare recovery-rate, turnaround, and cost-per-reusable-item limits; assess measured pilot outcomes against all three, without excluding rejected returns.",
    ),
    Perspective(
        ("retention", "churn", "lifecycle", "repeat purchase", "cohort", "subscription", "ltv", "cac"),
        "customer retention",
        "a repeat-use proposition could allow repeat purchase behavior to be measured",
        "subscription friction or unmet expectations may prevent repeat purchases",
        "customers continue using and paying for the product beyond initial curiosity",
        "Why would a customer renew, cancel, or stop using the product after the first cycle?",
        "Target customers voluntarily renew after experiencing the full proposed usage cycle.",
        "Track a consented cohort through the actual usage and renewal cycle; distinguish paid renewals, cancellations, inactivity, and incentives; interview dropouts.",
        "Predeclare a paid-renewal target and observation window; report renewals over the full starting cohort and cancellation reasons, not waitlist signups.",
    ),
    Perspective(
        ("cosmetic", "formulation", "microbial", "contamination", "preservative", "stability", "mocra", "refill generations"),
        "formulation and refill safety",
        "a specified refill process could be evaluated for product integrity before rollout",
        "repeated handling and refilling may compromise formula stability or microbial safety",
        "the formula and container remain suitable throughout the intended refill cycle",
        "What stability and contamination evidence covers the proposed formulation and refill process?",
        "The formulation and container maintain their specified safety and stability properties through intended use.",
        "Have a qualified laboratory define an appropriate stability and microbial testing protocol for the proposed formulation, container, and refill handling conditions before consumer testing.",
        "Use the laboratory's predefined acceptance criteria and report every failed condition; a commercial demand signal cannot substitute for safety results.",
    ),
    Perspective(
        ("unit economics", "gross margin", "procurement", "bill of materials", "bom", "depreciation", "margin", "labor"),
        "unit economics",
        "an explicit fulfillment model allows its cost drivers to be itemized",
        "unmeasured shipping, packaging, returns, and support costs may eliminate contribution margin",
        "realized revenue covers the full variable cost of fulfilling and supporting an order",
        "Which costs are excluded from the proposed per-order margin calculation?",
        "Realized order revenue exceeds all attributable variable costs under observed fulfillment conditions.",
        "Build a per-order ledger from supplier quotes and a small operational pilot; record outbound and return shipping, packaging, losses, cleaning, support, and actual revenue separately.",
        "Compare fully loaded contribution margin with a predeclared viability threshold; disclose cost sensitivity and missing line items instead of substituting assumed rates.",
    ),
    Perspective(
        ("neurobiology", "sleep medicine", "scientific", "clinical", "peer-reviewed", "brainwave", "entrainment", "eeg", "polysomnography"),
        "clinical evidence",
        "a specific claimed effect can be translated into a falsifiable research question",
        "an apparent improvement may reflect placebo effects, reporting bias, or confounding rather than the proposed mechanism",
        "the proposed effect can be measured safely and distinguished from a suitable control",
        "What controlled evidence distinguishes the claimed effect from expectation and natural variation?",
        "The claimed effect differs from a suitable control on a preregistered outcome.",
        "Ask qualified researchers to assess plausibility, safety, and ethics before designing a controlled, blinded study; prespecify outcomes, controls, and an appropriate sample-size analysis.",
        "Use preregistered effect, uncertainty, and safety criteria assessed by qualified researchers; a personal diary cannot establish efficacy or mechanism.",
    ),
    Perspective(
        ("hardware", "ergonomics", "transducer", "thermal", "wash", "durability", "battery", "comfort", "side-sleeping"),
        "hardware usability and durability",
        "a concrete physical design can be subjected to fit and durability checks",
        "heat, discomfort, cleaning, or mechanical degradation may make the proposed device unsuitable for repeated use",
        "the device remains safe, comfortable, and functional under its intended use and cleaning conditions",
        "Which intended use and cleaning conditions cause discomfort or mechanical degradation?",
        "The prototype remains functional and comfortable through its specified use and cleaning conditions.",
        "Complete qualified safety review, then evaluate a prototype against an intended-use matrix covering fit, temperature, cleaning, and repeated mechanical loading; log defects and discomfort.",
        "Predeclare functional, comfort, and safety acceptance criteria; record failure modes by condition and require resolution of safety-critical defects.",
    ),
    Perspective(
        ("health claims", "disease", "therapeutic", "wellness", "attorney", "advertising", "treatment", "liability", "regulatory"),
        "health-claim substantiation",
        "explicit proposed claims can be audited before public marketing",
        "therapeutic marketing may outrun available substantiation and applicable requirements",
        "each public claim can be supported by suitable evidence and reviewed for the intended jurisdiction",
        "Which exact proposed claims are supported, and which should be withheld pending evidence and qualified review?",
        "Each proposed public claim can be traced to adequate substantiation for its intended use.",
        "Create a claim-by-claim evidence matrix and have qualified regulatory reviewers identify gaps and required next steps; hold unsupported claims out of test marketing.",
        "Record a substantiation and review decision for every claim; do not infer regulatory clearance or therapeutic efficacy from testimonials.",
    ),
)
GENERAL = Perspective(
    (), "mandate validation",
    "an explicitly stated problem can be investigated before committing to a solution",
    "the proposed solution may not resolve the target customer's actual problem",
    "the customer's problem and the proposed benefit can be observed in practice",
    "What observation would falsify the central assumption in this mandate?",
    "The proposed solution resolves an observed target-customer problem relevant to this mandate.",
    "Translate the supplied mandate into an observable task with target customers; record current behavior and prototype behavior, including non-adoption and adverse outcomes.",
    "Agree the mandate-specific outcome and acceptance criterion before testing; report observed outcomes and unresolved gaps rather than assuming validation.",
)


def _score(text: str, perspective: Perspective) -> int:
    return sum(bool(re.search(r"\b" + re.escape(term), text.lower())) for term in perspective.terms)


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
