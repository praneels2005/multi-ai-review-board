"""
Review Board Orchestrator for Multiple AI Review Board.
Coordinates Phase 1 (Independent Reviews), Phase 2 (Bounded Challenge Round),
and Phase 3 (Coordinator Synthesis) with strict reliability controls:
timeouts, at most one retry, call/token budget stops, citation validation,
and failure isolation.
"""

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any, Tuple, Optional

from app.schemas.review_board_schema import (
    StartupIdeaInput,
    SpecialistAgentConfig,
    SpecialistFeedback,
    ValidationExperiment,
    ChallengeResponseItem,
    CoordinatorCombinedReview,
    EvidenceSufficiencyAssessment,
    BudgetConfig,
    ReviewBoardSession,
)
from app.models.connectors.factory import get_provider_adapter
from app.models.connectors.base_connector import NormalizedProviderResponse

logger = logging.getLogger(__name__)


SPECIALIST_REVIEW_SYSTEM_PROMPT = """You are a specialized reviewer on a startup review board.
Evaluate the provided startup idea STRICTLY from your assigned domain role, expertise, and mandate.
Do NOT see or consider other specialists' reviews; evaluate independently.

Guidelines:
1. Ground your review in your domain expertise.
2. Provide critical, substantive feedback:
   - strengths: key competitive strengths from your vantage point
   - risks: specific domain failure points, technical or operational risks
   - missing_assumptions: unstated or unverified assumptions the founders are making
   - questions: probing questions for the founding team
   - validation_experiment: a concrete, low-cost experiment to test the most dangerous assumption (hypothesis, test_design, success_metric)
   - evidence_citations: list of supplied evidence IDs (e.g. ["E1"]) you relied on. Only cite IDs that actually exist in the prompt!
   - assumptions_and_unknowns: explicit labels for what is assumed vs what is unknown or unverified.
3. Do NOT invent market facts. Treat consensus as non-binding. This is decision support, not an investment recommendation.

Respond ONLY with a valid JSON object matching this schema:
{
  "strengths": ["<strength1>", "<strength2>"],
  "risks": ["<risk1>", "<risk2>"],
  "missing_assumptions": ["<assumption1>", "<assumption2>"],
  "questions": ["<question1>", "<question2>"],
  "validation_experiment": {
    "hypothesis": "<hypothesis statement>",
    "test_design": "<step by step test>",
    "success_metric": "<clear threshold>"
  },
  "evidence_citations": ["E1"],
  "assumptions_and_unknowns": ["<labeled assumption or unknown>"]
}
"""

CHALLENGE_ROUND_SYSTEM_PROMPT = """You are orchestrating a bounded challenge and response debate round between review board specialists.
Review the independent findings of each specialist. Identify 1 to 2 sharp points of disagreement, conflicting priorities, or contested assumptions between two specialists.
Have the challenger question the target specialist's logic, and provide the target specialist's counter-response and how their reasoning adjusted.

Respond ONLY with a valid JSON object matching this schema:
{
  "challenges": [
    {
      "challenger_id": "<id>",
      "challenger_role": "<role>",
      "target_specialist_id": "<id>",
      "target_role": "<role>",
      "challenge_point": "<specific challenge on reasoning or assumption>",
      "response": "<target specialist defense/counter-argument>",
      "reasoning_adjustment": "<how reasoning or risk appraisal shifted after challenge>"
    }
  ]
}
"""

COORDINATOR_SYSTEM_PROMPT = """You are the independent Review Board Coordinator.
Your role is to synthesize the specialist reviews and debate round into a rigorous decision support report.

Mandates:
1. Summarize top priorities and strategic imperatives.
2. Highlight key disagreements, conflicting tradeoffs, and tensions between specialists.
3. Prioritize next validation experiments with high learning value and low execution cost.
4. Critically assess evidence sufficiency: explain whether supplied evidence is sufficient, thin, or insufficient, and why.
5. If any specialist failed during the run, explicitly analyze how the missing perspective affects confidence.
6. Clearly state: This is decision support, not an investment recommendation. Do NOT treat consensus as proof of demand.

Respond ONLY with a valid JSON object matching this schema:
{
  "summary": "<executive synthesis>",
  "priorities": ["<priority1>", "<priority2>"],
  "disagreements": ["<disagreement1>", "<disagreement2>"],
  "next_experiments": [
    {
      "hypothesis": "<hypothesis>",
      "test_design": "<test>",
      "success_metric": "<metric>"
    }
  ],
  "evidence_sufficiency": {
    "status": "<sufficient|thin|insufficient>",
    "analysis": "<detailed rationale regarding evidence gaps>"
  },
  "failure_impact_analysis": "<analysis of missing specialist if any, otherwise null>",
  "disclaimer": "Decision support only. Not an investment recommendation. Consensus among AI agents does not constitute proof of market demand."
}
"""


class ReviewBoardOrchestrator:
    """Orchestrates multi-agent review board execution with reliability controls."""

    def __init__(self, budget_config: Optional[BudgetConfig] = None):
        self.budget = budget_config or BudgetConfig()
        self.calls_made = 0
        self.tokens_used = 0
        self.total_cost_usd = 0.0
        self.total_latency_ms = 0.0
        self.failures_encountered = 0

    def _check_budget(self) -> bool:
        """Return True if budget limits (call cap or token cap) are exceeded."""
        if self.calls_made >= self.budget.call_cap:
            logger.warning(f"Budget stop triggered: call cap reached ({self.calls_made}/{self.budget.call_cap})")
            return True
        if self.tokens_used >= self.budget.token_cap:
            logger.warning(f"Budget stop triggered: token cap reached ({self.tokens_used}/{self.budget.token_cap})")
            return True
        return False

    async def execute_board(
        self,
        idea: StartupIdeaInput,
        panel: List[SpecialistAgentConfig],
        session_id: Optional[str] = None
    ) -> ReviewBoardSession:
        """Run the complete 3-phase review board workflow."""
        sid = session_id or str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).isoformat()

        session = ReviewBoardSession(
            session_id=sid,
            created_at=created_at,
            idea=idea,
            panel=panel,
            budget_config=self.budget,
            status="in_progress"
        )

        valid_evidence_ids = {e.id.strip().upper() for e in idea.evidence}

        # -------------------------------------------------------------
        # PHASE 1: Independent Specialist Reviews
        # -------------------------------------------------------------
        specialist_feedbacks: List[SpecialistFeedback] = []
        for specialist in panel:
            if self._check_budget():
                session.status = "budget_stopped"
                break

            feedback = await self._run_single_specialist_with_retry(
                specialist=specialist,
                idea=idea,
                valid_evidence_ids=valid_evidence_ids
            )
            specialist_feedbacks.append(feedback)
            if feedback.status in ["failed", "timed_out"]:
                self.failures_encountered += 1

        session.specialist_reviews = specialist_feedbacks

        if session.status == "budget_stopped":
            session.execution_summary = self._build_execution_summary(budget_stopped=True)
            return session

        # -------------------------------------------------------------
        # PHASE 2: Bounded Challenge & Response Round
        # -------------------------------------------------------------
        challenge_items: List[ChallengeResponseItem] = []
        successful_feedbacks = [f for f in specialist_feedbacks if f.status == "success"]

        if len(successful_feedbacks) >= 2 and not self._check_budget():
            challenge_items = await self._run_challenge_round(idea, successful_feedbacks)
        session.challenge_round = challenge_items

        # -------------------------------------------------------------
        # PHASE 3: Coordinator Synthesis
        # -------------------------------------------------------------
        if not self._check_budget():
            combined = await self._run_coordinator_synthesis(
                idea=idea,
                specialist_feedbacks=specialist_feedbacks,
                challenges=challenge_items
            )
            session.combined_review = combined
        else:
            session.status = "budget_stopped"

        if session.status != "budget_stopped":
            session.status = "partial_failure" if self.failures_encountered > 0 else "completed"

        session.execution_summary = self._build_execution_summary(
            budget_stopped=(session.status == "budget_stopped")
        )
        return session

    async def _run_single_specialist_with_retry(
        self,
        specialist: SpecialistAgentConfig,
        idea: StartupIdeaInput,
        valid_evidence_ids: set
    ) -> SpecialistFeedback:
        """Execute a specialist review with per-agent timeout and at most one retry."""
        adapter = get_provider_adapter(specialist.provider)
        evidence_text = "\n".join([f"[{e.id}] ({e.data_type}) {e.summary}" for e in idea.evidence]) or "None"

        user_prompt = f"""Review the following startup idea according to your mandate:
Role: {specialist.role}
Domain Expertise: {specialist.expertise}
Review Mandate: {specialist.mandate}
Rationale: {specialist.rationale}

Startup Details:
Title: {idea.title}
Target Customer: {idea.target_customer}
Problem: {idea.problem}
Proposed Solution: {idea.proposed_solution}
Idea Description: {idea.idea}
Supplied Evidence Items:
{evidence_text}
"""

        max_attempts = 1 + min(self.budget.max_retries, 1)  # At most one retry
        last_error = ""

        for attempt in range(max_attempts):
            self.calls_made += 1
            start_t = time.perf_counter()

            try:
                # Per-call timeout enforcement
                response = await adapter.call(
                    system_prompt=SPECIALIST_REVIEW_SYSTEM_PROMPT,
                    user_prompt=user_prompt,
                    model=specialist.model,
                    timeout_seconds=self.budget.timeout_seconds,
                    simulate_failure=specialist.simulate_failure
                )

                duration_ms = (time.perf_counter() - start_t) * 1000
                self.tokens_used += response.total_tokens
                self.total_cost_usd += response.cost_estimate_usd
                self.total_latency_ms += duration_ms

                # Check if malformed or parsing failed
                parsed = response.parsed_json
                if not parsed or response.error:
                    raise ValueError(response.error or "Failed to parse structured JSON response from provider")

                # Validate evidence citations
                raw_citations = [str(c).strip().upper() for c in parsed.get("evidence_citations", [])]
                valid_cites = [c for c in raw_citations if c in valid_evidence_ids]
                invalid_cites = [c for c in raw_citations if c not in valid_evidence_ids]

                experiment_data = parsed.get("validation_experiment")
                experiment = None
                if experiment_data and isinstance(experiment_data, dict):
                    experiment = ValidationExperiment(
                        hypothesis=experiment_data.get("hypothesis", "Hypothesis not articulated"),
                        test_design=experiment_data.get("test_design", "Test design not provided"),
                        success_metric=experiment_data.get("success_metric", "Metric not specified")
                    )

                return SpecialistFeedback(
                    specialist_id=specialist.id,
                    role=specialist.role,
                    provider=specialist.provider,
                    model=specialist.model,
                    is_simulated=response.is_simulated,
                    status="success",
                    strengths=parsed.get("strengths", []),
                    risks=parsed.get("risks", []),
                    missing_assumptions=parsed.get("missing_assumptions", []),
                    questions=parsed.get("questions", []),
                    validation_experiment=experiment,
                    evidence_citations=valid_cites,
                    invalid_citations=invalid_cites,
                    assumptions_and_unknowns=parsed.get("assumptions_and_unknowns", []),
                    latency_ms=round(duration_ms, 2),
                    token_usage={
                        "input_tokens": response.input_tokens,
                        "output_tokens": response.output_tokens,
                        "total_tokens": response.total_tokens
                    },
                    cost_estimate_usd=response.cost_estimate_usd
                )

            except asyncio.TimeoutError as te:
                last_error = f"Timed out after {self.budget.timeout_seconds}s"
                duration_ms = (time.perf_counter() - start_t) * 1000
                self.total_latency_ms += duration_ms
                if attempt == max_attempts - 1:
                    return SpecialistFeedback(
                        specialist_id=specialist.id,
                        role=specialist.role,
                        provider=specialist.provider,
                        model=specialist.model,
                        is_simulated=(specialist.provider == "mock"),
                        status="timed_out",
                        error_message=last_error,
                        latency_ms=round(duration_ms, 2)
                    )
                await asyncio.sleep(0.1)

            except Exception as e:
                last_error = str(e)
                duration_ms = (time.perf_counter() - start_t) * 1000
                self.total_latency_ms += duration_ms
                if attempt == max_attempts - 1:
                    return SpecialistFeedback(
                        specialist_id=specialist.id,
                        role=specialist.role,
                        provider=specialist.provider,
                        model=specialist.model,
                        is_simulated=(specialist.provider == "mock"),
                        status="failed",
                        error_message=last_error,
                        latency_ms=round(duration_ms, 2)
                    )
                await asyncio.sleep(0.1)

        # Fallback if loop ends
        return SpecialistFeedback(
            specialist_id=specialist.id,
            role=specialist.role,
            provider=specialist.provider,
            model=specialist.model,
            is_simulated=True,
            status="failed",
            error_message=last_error or "Maximum retry attempts exhausted."
        )

    async def _run_challenge_round(
        self,
        idea: StartupIdeaInput,
        feedbacks: List[SpecialistFeedback]
    ) -> List[ChallengeResponseItem]:
        """Execute one bounded challenge and response round."""
        self.calls_made += 1
        adapter = get_provider_adapter("mock")

        summary_lines = []
        for f in feedbacks:
            summary_lines.append(f"Specialist: {f.role} ({f.specialist_id})")
            summary_lines.append(f"  Strengths: {'; '.join(f.strengths[:2])}")
            summary_lines.append(f"  Risks: {'; '.join(f.risks[:2])}")
            summary_lines.append(f"  Missing Assumptions: {'; '.join(f.missing_assumptions[:2])}")

        user_prompt = f"""Run a bounded challenge round for startup: '{idea.title}'
Specialist Reviews:
{chr(10).join(summary_lines)}
"""

        start_t = time.perf_counter()
        try:
            response = await adapter.call(
                system_prompt=CHALLENGE_ROUND_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                timeout_seconds=self.budget.timeout_seconds
            )
            duration_ms = (time.perf_counter() - start_t) * 1000
            self.tokens_used += response.total_tokens
            self.total_cost_usd += response.cost_estimate_usd
            self.total_latency_ms += duration_ms

            parsed = response.parsed_json or {}
            raw_challenges = parsed.get("challenges", [])

            items: List[ChallengeResponseItem] = []
            for c in raw_challenges[:2]:
                items.append(ChallengeResponseItem(
                    challenger_id=c.get("challenger_id", "spec_1"),
                    challenger_role=c.get("challenger_role", "Challenger Specialist"),
                    target_specialist_id=c.get("target_specialist_id", "spec_2"),
                    target_role=c.get("target_role", "Target Specialist"),
                    challenge_point=c.get("challenge_point", "Contested assumption"),
                    response=c.get("response", "Counter-argument"),
                    reasoning_adjustment=c.get("reasoning_adjustment", "Reasoning adjustment"),
                    is_simulated=True
                ))
            return items

        except Exception as e:
            logger.warning(f"Challenge round failed: {e}")
            return []

    async def _run_coordinator_synthesis(
        self,
        idea: StartupIdeaInput,
        specialist_feedbacks: List[SpecialistFeedback],
        challenges: List[ChallengeResponseItem]
    ) -> CoordinatorCombinedReview:
        """Run the independent coordinator agent to synthesize findings and assess evidence sufficiency."""
        self.calls_made += 1
        adapter = get_provider_adapter("mock")

        failed_specialists = [f for f in specialist_feedbacks if f.status in ["failed", "timed_out"]]
        successful_specialists = [f for f in specialist_feedbacks if f.status == "success"]

        prompt_lines = [
            f"Startup: {idea.title}",
            f"Problem: {idea.problem}",
            f"Solution: {idea.proposed_solution}",
            f"Supplied Evidence Count: {len(idea.evidence)}",
            f"Failed Specialists Count: {len(failed_specialists)}"
        ]
        if failed_specialists:
            prompt_lines.append("Failed Specialists (Note in failure impact analysis):")
            for f in failed_specialists:
                prompt_lines.append(f"- {f.role} (Status: {f.status}, Reason: {f.error_message})")

        prompt_lines.append("\nSuccessful Specialist Reviews:")
        for f in successful_specialists:
            prompt_lines.append(f"Specialist [{f.role}]:")
            prompt_lines.append(f"  Risks: {', '.join(f.risks)}")
            prompt_lines.append(f"  Assumptions: {', '.join(f.missing_assumptions)}")
            if f.validation_experiment:
                prompt_lines.append(f"  Proposed Exp: {f.validation_experiment.hypothesis} -> {f.validation_experiment.success_metric}")

        if challenges:
            prompt_lines.append("\nDebate Challenges:")
            for ch in challenges:
                prompt_lines.append(f"- {ch.challenger_role} challenged {ch.target_role}: '{ch.challenge_point}' -> Adjusted: '{ch.reasoning_adjustment}'")

        start_t = time.perf_counter()
        try:
            response = await adapter.call(
                system_prompt=COORDINATOR_SYSTEM_PROMPT,
                user_prompt="\n".join(prompt_lines),
                timeout_seconds=self.budget.timeout_seconds
            )
            duration_ms = (time.perf_counter() - start_t) * 1000
            self.tokens_used += response.total_tokens
            self.total_cost_usd += response.cost_estimate_usd
            self.total_latency_ms += duration_ms

            parsed = response.parsed_json or {}
            ev_data = parsed.get("evidence_sufficiency", {})
            evidence_assessment = EvidenceSufficiencyAssessment(
                status=ev_data.get("status", "thin"),
                analysis=ev_data.get("analysis", "Evidence relies on initial testimonials or unverified benchmarks.")
            )

            # Build experiments list
            experiments = []
            for exp in parsed.get("next_experiments", []):
                if isinstance(exp, dict):
                    experiments.append(ValidationExperiment(
                        hypothesis=exp.get("hypothesis", "Hypothesis"),
                        test_design=exp.get("test_design", "Test"),
                        success_metric=exp.get("success_metric", "Metric")
                    ))

            # Failure impact analysis
            failure_impact = parsed.get("failure_impact_analysis")
            if failed_specialists and not failure_impact:
                missing_roles = ", ".join([f.role for f in failed_specialists])
                failure_impact = f"Notice: {len(failed_specialists)} specialist(s) [{missing_roles}] failed during review. Critical evaluation in these specific technical/operational areas was omitted, lowering overall certainty. Founders must validate these domains independently."

            return CoordinatorCombinedReview(
                summary=parsed.get("summary", "Review board completed assessment."),
                priorities=parsed.get("priorities", ["Validate key technical bottlenecks.", "Confirm willingness to pay."]),
                disagreements=parsed.get("disagreements", ["Onboarding simplicity vs enterprise security governance."]),
                next_experiments=experiments,
                evidence_sufficiency=evidence_assessment,
                failure_impact_analysis=failure_impact,
                disclaimer="Decision support only. Not an investment recommendation. Consensus among AI agents does not constitute proof of market demand.",
                latency_ms=round(duration_ms, 2),
                token_usage={
                    "input_tokens": response.input_tokens,
                    "output_tokens": response.output_tokens,
                    "total_tokens": response.total_tokens
                },
                cost_estimate_usd=response.cost_estimate_usd
            )

        except Exception as e:
            logger.error(f"Coordinator synthesis failed: {e}")
            duration_ms = (time.perf_counter() - start_t) * 1000
            return CoordinatorCombinedReview(
                summary="Coordinator completed partial synthesis following an upstream execution timeout.",
                priorities=["Validate primary risk assumptions before deployment."],
                disagreements=["Tension between ease of onboarding and enterprise security."],
                next_experiments=[],
                evidence_sufficiency=EvidenceSufficiencyAssessment(
                    status="thin",
                    analysis="Evidence could not be fully cross-verified due to execution limits."
                ),
                failure_impact_analysis="Coordinator execution encountered limits. Review individual specialist feedback cards above.",
                disclaimer="Decision support only. Not an investment recommendation. Consensus among AI agents does not constitute proof of market demand.",
                latency_ms=round(duration_ms, 2)
            )

    def _build_execution_summary(self, budget_stopped: bool = False) -> Dict[str, Any]:
        """Produce the aggregated execution summary."""
        return {
            "total_latency_ms": round(self.total_latency_ms, 2),
            "total_tokens": self.tokens_used,
            "total_cost_usd": round(self.total_cost_usd, 6),
            "calls_made": self.calls_made,
            "budget_stopped": budget_stopped,
            "failures_encountered": self.failures_encountered
        }

