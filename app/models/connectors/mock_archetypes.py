"""Bounded offline archetypes and shared whole-token matching, not semantic inference."""

import json
import re
from dataclasses import dataclass


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
        ("security", "devsecops", "privilege", "privileges", "permission", "permissions", "root", "exfiltration", "redaction", "host", "soc2"),
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



@dataclass(frozen=True)
class Archetype:
    key: str
    terms: tuple[str, ...]
    role: str
    expertise: str
    mandate: str
    rationale: str
    perspective: Perspective


def keyword_hits(text: str, terms: tuple[str, ...]) -> set[str]:
    """Count distinct explicit terms, with boundaries at BOTH ends (no stemming)."""
    return {term for term in terms if re.search(r"\b" + re.escape(term) + r"\b", text, re.I)}


ARCHETYPES = (
    Archetype(
        "developer_adoption",
        ('developer', 'developers', 'devtool', 'ebpf', 'kubernetes', 'tracing', 'sdk', 'cli', 'api', 'database'),
        'Developer Experience & CLI Usability Specialist',
        'Developer onboarding friction, SDK ergonomics, CLI workflows, and engineering team adoption.',
        'Evaluate whether developers will willingly adopt and maintain this tool, assess configuration overhead, and review local-to-cloud workflows.',
        'Developer tools fail primarily on initial friction; dev-ex review ensures workflow friction does not kill bottom-up adoption.',
        PERSPECTIVES[0],
    ),
    Archetype(
        "runtime_performance",
        ('ebpf', 'kubernetes', 'kernel', 'cpu', 'observability', 'tracing', 'infrastructure'),
        'Cloud Infrastructure & Kernel Systems Architect',
        'eBPF kernel telemetry, Linux observability, CPU/memory overhead, and large-scale Kubernetes clustering.',
        'Scrutinize runtime overhead claims, node-level security privileges, Linux kernel compatibility, and agent footprint.',
        'Enterprise platform teams will reject observability agents that add latency or introduce kernel instability.',
        PERSPECTIVES[1],
    ),
    Archetype(
        "deployment_security",
        ('ebpf', 'kubernetes', 'privileged', 'daemonset', 'telemetry', 'security', 'redaction'),
        'DevSecOps & Compliance Auditor',
        'Production host security, privileged daemonsets, SOC2, HIPAA compliance, and telemetry data redaction.',
        'Assess risks of root access / privileged daemonset deployment and sensitive data exfiltration in production traces.',
        'Enterprise CISOs block observability tools that request excessive container capabilities without verification.',
        PERSPECTIVES[2],
    ),
    Archetype(
        "developer_gtm",
        ('ebpf', 'kubernetes', 'datadog', 'observability', 'open-core', 'procurement'),
        'Open-Core & Enterprise GTM Strategist',
        'Open-core monetization, buyer vs user persona dynamics, competitive displacement against Datadog/Dynatrace.',
        'Evaluate pricing tiers, willingness to pay from VP/Director buyers, and defense against legacy observability incumbents.',
        'High developer love must translate into a scalable enterprise contract model with clear buyer value.',
        PERSPECTIVES[3],
    ),
    Archetype(
        "reverse_logistics",
        ('refillable', 'refills', 'skincare', 'return', 'returns', 'sanitization', 'logistics', 'packaging'),
        'Sustainable Supply Chain & Reverse Logistics Specialist',
        'Closed-loop circular packaging, return shipping logistics, wash/sterilization facility operations, and carton lifecycle.',
        'Analyze unit costs and friction of customer container returns, sanitation compliance, and breakage/loss rates in transit.',
        'Refillable models collapse when return logistics costs exceed the savings of reusable packaging.',
        PERSPECTIVES[4],
    ),
    Archetype(
        "customer_retention",
        ('skincare', 'refillable', 'refills', 'subscription', 'cosmetics', 'renewals', 'retention'),
        'D2C Retention & Customer Lifecycle Strategist',
        'Subscription churn modeling, cohort retention, unboxing behavior, and paid customer acquisition payback.',
        'Evaluate churn risk at 90 days, customer willingness to complete physical return loops, and LTV-to-CAC ratios.',
        'D2C brands live and die by repeat purchase rates; physical friction in returning empties often causes subscription cancellations.',
        PERSPECTIVES[5],
    ),
    Archetype(
        "cosmetic_safety",
        ('skincare', 'refillable', 'cosmetic', 'cosmetics', 'formulation', 'serums', 'cleansers'),
        'Cosmetic Formulation & FDA Regulatory Compliance Officer',
        'FDA cosmetic safety, stability testing in refill containers, preservative efficacy, and MoCRA regulation standards.',
        'Assess microbial contamination risks during customer refills and compliance with US MoCRA labelling and safety requirements.',
        'Refilled bottles run contamination risks that can trigger FDA recalls or severe liability without preservative stability.',
        PERSPECTIVES[6],
    ),
    Archetype(
        "unit_economics",
        ('skincare', 'refillable', 'packaging', 'aluminum', 'margin', 'procurement', 'sanitization'),
        'Unit Economics & Packaging Procurement Analyst',
        'Bill of materials (BOM), custom aluminum/glass mold costs, shipping tare weight, and gross margin optimization.',
        'Audit gross margin after accounting for two-way shipping, packaging depreciation, and return sanitization labor.',
        'Circular products often suffer from hidden operational labor that drains gross margins below 50%.',
        PERSPECTIVES[7],
    ),
    Archetype(
        "clinical_evidence",
        ('sleep', 'insomnia', 'neurotech', 'brainwave', 'entrainment', 'pillow', 'neural'),
        'Neurobiology & Sleep Medicine Researcher',
        'EEG polysomnography, acoustic binaural stimulation, circadian rhythm physiology, and sleep architecture (REM/NREM).',
        'Scrutinize scientific plausibility of acoustic brainwave entrainment through sleep surfaces, demand peer-reviewed citations.',
        'Consumer sleep aids frequently make claims unsupported by double-blind clinical trials.',
        PERSPECTIVES[8],
    ),
    Archetype(
        "hardware_durability",
        ('pillow', 'sleep', 'transducers', 'acoustic', 'hardware', 'ergonomics', 'battery'),
        'Consumer Hardware & Ergonomics Engineer',
        'Transducer acoustic integration, washable foam textiles, thermal dissipation, battery safety, and wearability.',
        'Examine thermal dissipation, transducer comfort during side-sleeping, and machine-washable mechanical durability.',
        'Hardware in bedding faces extreme comfort constraints and sweat/washing degradation.',
        PERSPECTIVES[9],
    ),
    Archetype(
        "health_claims",
        ('insomnia', 'sleep', 'neurotech', 'therapeutic', 'curing', 'brainwave', 'health'),
        'FDA Regulatory & Health Claims Attorney',
        'FDA 510(k) wellness exemptions vs Class II medical device classification, FTC advertising truth-in-claims standards.',
        'Identify high-risk disease treatment claims (insomnia/apnea) versus general wellness wording, evaluate recall liability.',
        'Unsubstantiated therapeutic sleep claims draw immediate FTC and FDA warning letters.',
        PERSPECTIVES[10],
    ),
)


def _domain(key, terms, role, expertise, mandate, risk, assumption, question,
            hypothesis, design, metric):
    perspective = Perspective(
        terms, key.replace('_', ' '),
        f"an explicit {key.replace('_', ' ')} proposal allows its central assumption to be tested",
        risk, assumption, question, hypothesis, design, metric,
    )
    return Archetype(key, terms, role, expertise, mandate,
                     f"This perspective tests {assumption}; keyword relevance is not proof of expertise or validation.",
                     perspective)


ARCHETYPES += (
    _domain('financial_controls', ('fintech', 'payments', 'payment', 'lending', 'banking', 'reconciliation', 'fraud', 'ledger'),
        'Fintech Payments & Financial Controls Specialist',
        'Payment reconciliation, transaction controls, fraud exposure, and lending workflows.',
        'Audit financial controls, reconciliation and fraud exposure before handling customer funds.',
        'unreconciled transactions or fraud losses may make handling customer funds unsafe',
        'each transaction can be reconciled and exceptions investigated',
        'How are duplicate, disputed, and missing transactions detected and reconciled?',
        'A sandbox transaction flow reconciles balances and exposes exceptions without moving real funds.',
        'Replay synthetic payments, duplicates, disputes, and settlement exceptions through a sandbox ledger; inspect reconciliation and audit trails.',
        'Predeclare reconciliation and exception-detection criteria; report unmatched balances and missed exceptions.'),
    _domain('learning_outcomes', ('edtech', 'education', 'students', 'teachers', 'tutoring', 'curriculum', 'classroom', 'learning'),
        'Education & Learning Outcomes Specialist',
        'Curriculum alignment, teacher workflows, accessibility, and learning outcome evaluation.',
        'Evaluate learning outcomes and curriculum fit separately from classroom engagement.',
        'engagement may not translate into durable learning or fit teacher workflows',
        'students can demonstrate learning beyond memorizing the tool responses',
        'Which curriculum-aligned outcome can be measured independently of time spent in the tool?',
        'Students using the prototype improve on a predefined curriculum-aligned task relative to a suitable comparison.',
        'With appropriate consent and educational oversight, compare baseline and follow-up curriculum tasks; record teacher effort, accessibility barriers, and comparison conditions.',
        'Predeclare a learning-outcome criterion and teacher-effort limit; report results and limitations without substituting engagement for attainment.'),
    _domain('carbon_integrity', ('carbon', 'credits', 'emissions', 'offsets', 'additionality', 'sequestration', 'verification'),
        'Carbon Credit Integrity & Emissions Accounting Specialist',
        'Carbon baselines, additionality, permanence, double counting, and verification boundaries.',
        'Audit carbon credit additionality, permanence and emissions accounting boundaries.',
        'non-additional credits or double counting may invalidate the claimed emissions benefit',
        'a defensible baseline and traceable accounting can support the proposed carbon claim',
        'What baseline, permanence controls, and ownership records support each proposed credit?',
        'A proposed carbon claim can be traced to an auditable baseline and non-duplicated accounting.',
        'Ask independent qualified reviewers to inspect a sample project baseline, credit ownership, reversal provisions, and emissions boundaries; record unresolved verification gaps.',
        'Predeclare completeness and integrity criteria; withhold claims for projects with unresolved additionality or double-counting findings.'),
    _domain('dental_workflows', ('dental', 'dentist', 'dentists', 'dentistry', 'appointments', 'claims', 'patient', 'practice'),
        'Dental Practice Workflow & Patient Operations Specialist',
        'Dental scheduling, claims workflows, practice operations, and patient record handling.',
        'Evaluate dental scheduling and claims handoffs without asserting clinical efficacy.',
        'appointment or claims handoff errors may increase staff burden and disrupt patient operations',
        'practice staff can complete scheduling and claims tasks with accurate records',
        'Which scheduling or claims exception forces staff back to manual work?',
        'Practice staff complete representative scheduling and claims tasks with fewer unresolved handoff errors.',
        'Observe practice staff using synthetic patient records for booking, rescheduling, and rejected claims; compare against the current workflow and log manual corrections.',
        'Predeclare task-completion, correction-rate, and staff-time criteria; investigate every record-handling error.'),
    _domain('agricultural_operations', ('agriculture', 'farm', 'farms', 'farmers', 'crop', 'crops', 'irrigation', 'soil'),
        'Agricultural Irrigation & Field Operations Specialist',
        'Crop constraints, soil measurements, irrigation scheduling, and field trial design.',
        'Evaluate irrigation recommendations against soil and crop constraints.',
        'unreliable soil measurements or irrigation recommendations may harm crops under field conditions',
        'recommendations remain appropriate across the intended soil and crop conditions',
        'Which soil conditions and sensor failures make an irrigation recommendation unsafe?',
        'The proposed irrigation workflow meets agronomist-defined crop and water-use constraints.',
        'Have qualified agronomists define a bounded field comparison and safety limits; log soil conditions, sensor faults, irrigation decisions, and crop outcomes without assuming yield improvements.',
        'Predeclare water-use and crop-safety criteria and report adverse conditions alongside any measured benefit.'),
    _domain('privacy_governance', ('privacy', 'consent', 'gdpr', 'pii', 'personal data', 'data deletion'),
        'Privacy & Data Governance Specialist',
        'Personal data inventories, consent boundaries, retention, and deletion verification.',
        'Audit privacy consent, data retention and deletion boundaries.',
        'untracked personal data flows or ineffective deletion may violate the intended privacy boundary',
        'the proposed processing can operate within documented consent and retention limits',
        'Where does personal data travel and how is deletion verified across copies?',
        'The prototype enforces its declared consent and deletion boundary on synthetic records.',
        'Inventory data flows and test consent withdrawal and deletion using synthetic records across storage and downstream copies; request qualified privacy review.',
        'Predeclare allowed flows and deletion checks; resolve unaccounted copies and blocked consent withdrawal before rollout.'),
    _domain('retrieval_quality', ('search', 'retrieval', 'documents', 'pdfs', 'citations', 'semantic', 'indexing'),
        'Document Retrieval & Citation Quality Specialist',
        'Retrieval relevance, document indexing, citation attribution, and answer coverage.',
        'Evaluate retrieval relevance and whether citations actually support answers.',
        'irrelevant retrieval or unsupported citations may mislead users even when an answer appears fluent',
        'source documents contain retrievable support for the intended questions',
        'Which questions lack relevant documents or receive citations that do not support the answer?',
        'The prototype retrieves supporting passages and abstains on unsupported questions.',
        'Create a labeled set of answerable and unanswerable document questions; assess retrieved passages, citation support, and abstentions with independent reviewers.',
        'Predeclare relevance, citation-support, and abstention criteria; report unsupported answers and coverage gaps.'),
)

# Generic padding has distinct questions and experiments, and never masquerades as
# a confident domain match. These are not additional domain archetypes.
FALLBACKS = (
    Archetype('discovery', (), 'Customer Problem Validation Specialist',
        'Problem interviews, observed customer behavior, and prototype task evaluation.',
        'Validate the customer problem before accepting the proposed benefit.',
        'The mock lacks enough domain matches; customer problem validation remains necessary.', GENERAL),
    Archetype('delivery', (), 'Delivery Feasibility Specialist',
        'Operational dependencies, exception handling, and delivery feasibility.',
        'Test delivery dependencies and operational exceptions.',
        'The mock lacks enough domain matches; delivery feasibility remains unverified.',
        Perspective(('delivery feasibility', 'delivery dependencies', 'operational exceptions'),
            'delivery feasibility', 'an explicit delivery process can be tested',
            'unverified dependencies or operational exceptions may prevent reliable delivery',
            'the proposed delivery process handles representative exceptions',
            'Which dependency failure prevents the proposed solution from being delivered?',
            'The proposed delivery process completes representative tasks despite anticipated exceptions.',
            'Map dependencies and rehearse the proposed delivery process with simulated dependency failures; record blocked tasks and manual interventions.',
            'Predeclare delivery-completion and intervention criteria; disclose blocked scenarios.')),
    Archetype('viability', (), 'Commercial Viability Specialist',
        'Buyer commitment, acquisition effort, and commercial validation.',
        'Test buyer commitment and acquisition effort.',
        'The mock lacks enough domain matches; commercial viability remains unverified.', PERSPECTIVES[3]),
)

PERSPECTIVES = tuple(a.perspective for a in ARCHETYPES) + tuple(a.perspective for a in FALLBACKS)
FIELD_WEIGHTS = {'title': 4, 'proposed_solution': 4, 'idea': 2, 'problem': 2, 'target_customer': 1}

# An archetype may join a panel only if at least one of its anchor terms matches, in
# addition to the two-distinct-term threshold. Anchors are domain-defining words; the
# remaining trigger terms ("practice", "claims", "learning", "search", "health", ...)
# also occur in many unrelated domains and can only support an anchored match.
ANCHORS = {
    'developer_adoption': ('developer', 'developers', 'devtool', 'sdk', 'cli', 'ebpf', 'kubernetes'),
    'runtime_performance': ('ebpf', 'kubernetes', 'kernel', 'cpu'),
    'deployment_security': ('ebpf', 'kubernetes', 'privileged', 'daemonset', 'redaction'),
    'developer_gtm': ('ebpf', 'kubernetes', 'datadog', 'open-core'),
    'reverse_logistics': ('refillable', 'refills', 'sanitization', 'logistics', 'packaging'),
    'customer_retention': ('subscription', 'renewals', 'retention'),
    'cosmetic_safety': ('cosmetic', 'cosmetics', 'formulation', 'skincare', 'serums', 'cleansers'),
    'unit_economics': ('packaging', 'aluminum', 'margin', 'procurement', 'sanitization'),
    'clinical_evidence': ('sleep', 'insomnia', 'neurotech', 'brainwave', 'entrainment', 'neural'),
    'hardware_durability': ('transducers', 'acoustic', 'hardware', 'ergonomics', 'battery'),
    'health_claims': ('insomnia', 'neurotech', 'therapeutic', 'curing', 'brainwave'),
    'financial_controls': ('fintech', 'lending', 'banking', 'reconciliation', 'ledger'),
    'learning_outcomes': ('edtech', 'education', 'teachers', 'tutoring', 'curriculum', 'classroom'),
    'carbon_integrity': ('carbon', 'emissions', 'offsets', 'additionality', 'sequestration'),
    'dental_workflows': ('dental', 'dentist', 'dentists', 'dentistry'),
    'agricultural_operations': ('agriculture', 'farm', 'farms', 'farmers', 'crop', 'crops', 'irrigation'),
    'privacy_governance': ('privacy', 'gdpr', 'pii', 'personal data', 'data deletion'),
    'retrieval_quality': ('retrieval', 'semantic', 'indexing', 'citations'),
}


def prompt_fields(prompt: str) -> dict:
    """Structured founder fields only; evidence labels never select domain roles.

    Plain-text standalone adapter calls are treated as a description. Production
    panel generation supplies JSON, so multiline fields cannot spoof field weights.
    """
    try:
        data = json.loads(prompt)
    except (ValueError, TypeError):
        data = None
    if isinstance(data, dict):
        idea = data.get('idea', data)
        if isinstance(idea, dict):
            return {field: str(idea.get(field, '')) for field in FIELD_WEIGHTS}
    return {'idea': prompt}


def score_archetype(fields: dict, archetype: Archetype) -> tuple[int, set[str]]:
    hits = set()
    score = 0
    for field, weight in FIELD_WEIGHTS.items():
        matches = keyword_hits(fields.get(field, ''), archetype.terms)
        hits.update(matches)
        score += weight * len(matches)
    return score, hits


def generate_panel(prompt: str) -> list[dict]:
    fields = prompt_fields(prompt)
    scored = [(index, archetype, *score_archetype(fields, archetype))
              for index, archetype in enumerate(ARCHETYPES)]
    # Two distinct terms AND at least one domain anchor; a missing ANCHORS entry
    # falls back to every trigger term (no extra restriction).
    eligible = [entry for entry in scored
                if len(entry[3]) >= 2 and entry[3] & set(ANCHORS.get(entry[1].key, entry[1].terms))]
    # Highest weighted scores determine membership; canonical library order keeps
    # presentation stable. Repeated copies of one term cannot cross the threshold.
    selected = sorted(sorted(eligible, key=lambda item: (-item[2], item[0]))[:5])
    members = [(a, f"[MOCK KEYWORD MATCH: {len(hits)} distinct terms; score={score}]", hits)
               for _, a, score, hits in selected]
    for fallback in FALLBACKS:
        if len(members) >= 3:
            break
        members.append((fallback, '[EXPLICIT MOCK FALLBACK]', set()))
    return [{
        'id': f'spec_{index + 1}', 'role': a.role, 'expertise': a.expertise,
        'mandate': (a.mandate + ' Review focus: {focus}.').format(focus=a.perspective.focus),
        'rationale': f"{tag} {a.rationale}" + (f" Matched terms: {', '.join(sorted(hits))}." if hits else ''),
        'provider': 'mock', 'model': 'mock-deterministic',
    } for index, (a, tag, hits) in enumerate(members)]
