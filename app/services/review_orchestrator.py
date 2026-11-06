"""
Review Board Orchestrator for Multiple AI Review Board.
Coordinates Phase 1 (Independent Reviews), Phase 2 (Bounded Multi-Step Challenge Round),
and Phase 3 (Coordinator Synthesis) with strict reliability controls:
pre-call budget reservation (call cap & token cap on all calls including retries),
timeouts, max 1 retry, citation validation against supplied evidence,
failure isolation, and explicit coordinator failure tracking.
"""

import asyncio
import json
import logging
import re
import time
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any, Tuple, Optional, Callable

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
from app.models.connectors.mock_deliberation import review_context, select_pairs
from app.models.connectors.base_connector import AITask, NormalizedProviderResponse
from app.schemas.provider_results import validate_result, ResponseFailure

logger = logging.getLogger(__name__)


class BudgetExceededError(Exception):
    """Raised when call cap or token budget cap would be exceeded."""
    pass


SPECIALIST_REVIEW_SYSTEM_PROMPT = """You are a specialized reviewer on a startup review board.
Evaluate the provided startup idea STRICTLY from your assigned domain role, expertise, and mandate.
Do NOT see or consider other specialists' reviews; evaluate independently.

Guidelines:
1. Ground your review in your domain expertise.
2. Provide critical, substantive feedback:
   - strengths: non-empty list of key competitive strengths from your vantage point
   - risks: non-empty list of specific domain failure points, technical or operational risks
   - missing_assumptions: non-empty list of unstated or unverified assumptions the founders are making
   - questions: non-empty list of probing questions for the founding team
   - validation_experiment: a concrete, low-cost experiment to test the most dangerous assumption (hypothesis, test_design, success_metric)
   - evidence_citations: list of supplied evidence IDs (e.g. ["E1"]) you relied on. ONLY cite IDs that actually exist in the prompt! Do NOT cite unsupplied IDs!
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

CHALLENGER_SYSTEM_PROMPT = """You are a specialist reviewer generating a sharp, rigorous challenge against a peer specialist's review.
Use the actual challenger and target findings. Identify a supported disagreement, competing objective, or complementary risk; do not invent a position or force disagreement.
Focus directly on domain trade-offs (e.g. speed vs security, unit margin vs customer convenience, wellness claims vs medical rigor).

Respond ONLY with a valid JSON object matching this schema:
{
  "challenge_point": "<1-3 concise sentences challenging the target specialist's reasoning or assumptions>"
}
"""

TARGET_RESPONSE_SYSTEM_PROMPT = """You are a target specialist responding to a peer specialist's challenge.
Review the challenge point against your domain evaluation.
Provide:
1. response: Your defense, operational counter-arguments, and clarification of trade-offs.
2. reasoning_adjustment: An explicit statement of how your reasoning, risk appraisal, or operational model shifts or adjusts in light of this challenge.

Respond ONLY with a valid JSON object matching this schema:
{
  "response": "<your defense and technical counter-argument>",
  "reasoning_adjustment": "<how reasoning or risk appraisal shifted after the challenge>"
}
"""

COORDINATOR_SYSTEM_PROMPT = """You are the independent Review Board Coordinator.
Your role is to synthesize the specialist reviews and debate round into a rigorous decision support report.

Mandates:
1. Summarize top priorities and strategic imperatives.
2. Highlight key disagreements, conflicting tradeoffs, and tensions between specialists.
3. Prioritize next validation experiments with high learning value and low execution cost.
4. Assess evidence relevance, methods, limitations, contradictions and unresolved assumptions.
   - Without evidence mark 'insufficient'. Anecdotes remain 'thin' and cannot establish clinical efficacy.
   - Evidence counts and source/type labels alone never justify 'sufficient'.
   - Preserve proposed experiments, including their procedures and success metrics; do not invent results.
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
    """Orchestrates multi-agent review board execution with strict reliability controls."""

    def __init__(self, budget_config: Optional[BudgetConfig] = None):
        self.budget = budget_config or BudgetConfig()
        self.calls_made = 0
        self.tokens_used = 0
        self.total_cost_usd = 0.0
        self.total_latency_ms = 0.0
        self.failures_encountered = 0
        self.budget_stopped = False

    async def _safe_provider_call(
        self,
        adapter,
        task: AITask,
        system_prompt: str,
        user_prompt: str,
        model: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
        simulate_failure: Optional[str] = None,
    ) -> NormalizedProviderResponse:
        """
        Unified provider call wrapper enforcing atomic pre-call budget checks.
        Reserves call from budget immediately before making provider invocation,
        preventing retries or coordinator calls from exceeding configured caps.
        """
        # 1. Hard Call Cap Check
        if self.calls_made >= self.budget.call_cap:
            self.budget_stopped = True
            raise BudgetExceededError(f"Call cap reached ({self.calls_made}/{self.budget.call_cap})")

        # 2. Hard Token Cap Pre-check (Reserve estimated input + baseline output tokens)
        estimated_tokens = (len(system_prompt) + len(user_prompt)) // 4 + 400
        if (self.tokens_used + estimated_tokens) > self.budget.token_cap:
            self.budget_stopped = True
            raise BudgetExceededError(
                f"Token cap would be exceeded ({self.tokens_used} consumed + est. {estimated_tokens} > cap {self.budget.token_cap})"
            )

        # 3. Reserve call immediately
        self.calls_made += 1
        effective_timeout = timeout_seconds if timeout_seconds is not None else self.budget.timeout_seconds

        # 4. Invoke Provider
        response = await adapter.call(
            task=task,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model=model,
            timeout_seconds=effective_timeout,
            simulate_failure=simulate_failure
        )

        # 5. Reconcile usage
        self.tokens_used += response.total_tokens
        self.total_cost_usd += response.cost_estimate_usd
        self.total_latency_ms += response.latency_ms

        return response

    async def execute_board(
        self,
        idea: StartupIdeaInput,
        panel: List[SpecialistAgentConfig],
        session_id: Optional[str] = None,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None
    ) -> ReviewBoardSession:
        """Run the complete 3-phase review board workflow with progress callbacks."""
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
        panel_map = {s.id: s for s in panel}

        def _notify(event_type: str, data: Dict[str, Any]):
            if progress_callback:
                try:
                    progress_callback({"type": event_type, "session_id": sid, **data})
                except Exception as ex:
                    logger.warning(f"Progress callback error: {ex}")

        # -------------------------------------------------------------
        # PHASE 1: Independent Specialist Reviews
        # -------------------------------------------------------------
        _notify("phase_started", {"phase": "specialists", "total": len(panel)})
        specialist_feedbacks: List[SpecialistFeedback] = []

        for specialist in panel:
            if self.budget_stopped or self.calls_made >= self.budget.call_cap or self.tokens_used >= self.budget.token_cap:
                session.status = "budget_stopped"
                self.budget_stopped = True
                break

            _notify("specialist_started", {"specialist_id": specialist.id, "role": specialist.role})

            feedback = await self._run_single_specialist_with_retry(
                specialist=specialist,
                idea=idea,
                valid_evidence_ids=valid_evidence_ids
            )
            specialist_feedbacks.append(feedback)
            if feedback.status in ["failed", "timed_out"]:
                self.failures_encountered += 1

            _notify("specialist_completed", {
                "specialist_id": specialist.id,
                "role": specialist.role,
                "status": feedback.status,
                "latency_ms": feedback.latency_ms
            })

        session.specialist_reviews = specialist_feedbacks

        if self.budget_stopped or session.status == "budget_stopped":
            session.status = "budget_stopped"
            session.execution_summary = self._build_execution_summary(budget_stopped=True)
            _notify("session_completed", {"status": session.status})
            return session

        # -------------------------------------------------------------
        # PHASE 2: Bounded Multi-Step Challenge & Response Round
        # -------------------------------------------------------------
        _notify("phase_started", {"phase": "debate"})
        challenge_items: List[ChallengeResponseItem] = []
        successful_feedbacks = [f for f in specialist_feedbacks if f.status == "success"]

        if len(successful_feedbacks) >= 2 and not self.budget_stopped:
            try:
                challenge_items = await self._run_multi_step_challenge_round(
                    idea=idea,
                    feedbacks=successful_feedbacks,
                    panel_map=panel_map,
                    notify_fn=_notify
                )
            except BudgetExceededError:
                self.budget_stopped = True
                session.status = "budget_stopped"
            except Exception as e:
                logger.warning(f"Debate round failed: {e}")

        session.challenge_round = challenge_items

        if self.budget_stopped:
            session.status = "budget_stopped"
            session.execution_summary = self._build_execution_summary(budget_stopped=True)
            _notify("session_completed", {"status": session.status})
            return session

        # -------------------------------------------------------------
        # PHASE 3: Coordinator Synthesis
        # -------------------------------------------------------------
        _notify("phase_started", {"phase": "coordinator"})
        try:
            combined = await self._run_coordinator_synthesis(
                idea=idea,
                specialist_feedbacks=specialist_feedbacks,
                challenges=challenge_items
            )
            session.combined_review = combined
            if combined.status in ["failed", "timed_out"] or combined.is_fallback:
                # Coordinator failed: Mark session explicitly as partial failure
                session.status = "partial_failure"
            elif self.failures_encountered > 0:
                session.status = "partial_failure"
            else:
                session.status = "completed"

            _notify("coordinator_completed", {
                "status": combined.status,
                "is_fallback": combined.is_fallback
            })

        except BudgetExceededError:
            self.budget_stopped = True
            session.status = "budget_stopped"
        except Exception as e:
            logger.error(f"Coordinator execution uncaught error: {e}")
            session.status = "partial_failure"

        session.execution_summary = self._build_execution_summary(
            budget_stopped=(session.status == "budget_stopped")
        )
        _notify("session_completed", {"status": session.status})
        return session

    async def _run_single_specialist_with_retry(
        self,
        specialist: SpecialistAgentConfig,
        idea: StartupIdeaInput,
        valid_evidence_ids: set
    ) -> SpecialistFeedback:
        """Execute a specialist review with per-agent timeout, strict output validation, and at most one retry."""
        adapter = get_provider_adapter(specialist.provider)
        # Keep identity, mandate, founder claims, and evidence separate. JSON encoding
        # prevents newlines or prompt-like text from becoming structural fields.
        user_prompt = json.dumps({
            "specialist": specialist.model_dump(include={"id", "role", "expertise", "mandate", "rationale"}),
            "idea": idea.model_dump(),
        }, ensure_ascii=False)

        max_attempts = 1 + min(self.budget.max_retries, 1)  # At most one retry
        last_error = ""

        for attempt in range(max_attempts):
            start_t = time.perf_counter()
            try:
                # Enforce budget reservation on EVERY attempt
                response = await self._safe_provider_call(
                    adapter=adapter,
                    task="specialist_review",
                    system_prompt=SPECIALIST_REVIEW_SYSTEM_PROMPT,
                    user_prompt=user_prompt,
                    model=specialist.model,
                    timeout_seconds=self.budget.timeout_seconds,
                    simulate_failure=specialist.simulate_failure
                )

                duration_ms = (time.perf_counter() - start_t) * 1000

                parsed = validate_result("specialist_review", response)

                # Validate evidence citations
                raw_citations = [str(c).strip().upper() for c in parsed.get("evidence_citations", [])]
                valid_cites = [c for c in raw_citations if c in valid_evidence_ids]
                invalid_cites = [c for c in raw_citations if c not in valid_evidence_ids]

                experiment_data = parsed.get("validation_experiment")
                experiment = None
                if experiment_data and isinstance(experiment_data, dict):
                    experiment = ValidationExperiment(
                        hypothesis=experiment_data["hypothesis"],
                        test_design=experiment_data["test_design"],
                        success_metric=experiment_data["success_metric"]
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

            except BudgetExceededError as be:
                self.budget_stopped = True
                last_error = str(be)
                duration_ms = (time.perf_counter() - start_t) * 1000
                return SpecialistFeedback(
                    specialist_id=specialist.id,
                    role=specialist.role,
                    provider=specialist.provider,
                    model=specialist.model,
                    is_simulated=(specialist.provider == "mock"),
                    status="failed",
                    error_message=f"Budget stop triggered: {be}",
                    latency_ms=round(duration_ms, 2)
                )

            except asyncio.TimeoutError:
                last_error = f"timeout: Timed out after {self.budget.timeout_seconds}s"
                duration_ms = (time.perf_counter() - start_t) * 1000
                if attempt == max_attempts - 1 or self.calls_made >= self.budget.call_cap:
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
                await asyncio.sleep(0.05)

            except Exception as e:
                last_error = self._error_detail(e)
                duration_ms = (time.perf_counter() - start_t) * 1000
                if attempt == max_attempts - 1 or self.calls_made >= self.budget.call_cap:
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
                await asyncio.sleep(0.05)

        return SpecialistFeedback(
            specialist_id=specialist.id,
            role=specialist.role,
            provider=specialist.provider,
            model=specialist.model,
            is_simulated=True,
            status="failed",
            error_message=last_error or "Maximum retry attempts exhausted."
        )

    async def _run_multi_step_challenge_round(
        self,
        idea: StartupIdeaInput,
        feedbacks: List[SpecialistFeedback],
        panel_map: Dict[str, SpecialistAgentConfig],
        notify_fn: Optional[Callable] = None
    ) -> List[ChallengeResponseItem]:
        """
        Execute a genuine two-step cross-agent debate round.
        Step A: Challenger generates a challenge against Target's review using Challenger's assigned provider.
        Step B: Target specialist receives that challenge and independently formulates defense & reasoning adjustment
                using Target's assigned provider!
        """
        if len(feedbacks) < 2:
            return []

        challenge_items: List[ChallengeResponseItem] = []

        # Form 1 or 2 debate pairs (bounded to 1 round)
        pairs = select_pairs(feedbacks, panel_map)

        for challenger_fb, target_fb in pairs:
            if self.budget_stopped:
                break

            try:
                challenger_spec = panel_map.get(challenger_fb.specialist_id)
                target_spec = panel_map.get(target_fb.specialist_id)
                if not challenger_spec or not target_spec:
                    continue

                # --- STEP A: Challenger generates challenge using Challenger's Adapter ---
                challenger_adapter = get_provider_adapter(challenger_spec.provider)
                exchange_context = {
                    "idea": idea.model_dump(),
                    "challenger": review_context(challenger_fb, challenger_spec),
                    "target": review_context(target_fb, target_spec),
                }
                step_a_user_prompt = json.dumps(exchange_context, ensure_ascii=False)
                challenger_res = await self._safe_provider_call(
                    adapter=challenger_adapter,
                    task="challenge_generation",
                    system_prompt=CHALLENGER_SYSTEM_PROMPT,
                    user_prompt=step_a_user_prompt,
                    model=challenger_spec.model,
                    timeout_seconds=self.budget.timeout_seconds
                )

                challenger_parsed = validate_result("challenge_generation", challenger_res)
                challenge_point = challenger_parsed["challenge_point"]

                # --- STEP B: Target Specialist responds using Target's Assigned Adapter ---
                target_adapter = get_provider_adapter(target_spec.provider)
                step_b_user_prompt = json.dumps({**exchange_context, "challenge_point": challenge_point}, ensure_ascii=False)
                target_res = await self._safe_provider_call(
                    adapter=target_adapter,
                    task="challenge_response",
                    system_prompt=TARGET_RESPONSE_SYSTEM_PROMPT,
                    user_prompt=step_b_user_prompt,
                    model=target_spec.model,
                    timeout_seconds=self.budget.timeout_seconds
                )

                target_parsed = validate_result("challenge_response", target_res)
                response_text = target_parsed["response"]
                reasoning_shift = target_parsed["reasoning_adjustment"]

                is_sim = (challenger_spec.provider == "mock" and target_spec.provider == "mock")

                item = ChallengeResponseItem(
                    challenger_id=challenger_spec.id,
                    challenger_role=challenger_spec.role,
                    challenger_provider=challenger_spec.provider,
                    target_specialist_id=target_spec.id,
                    target_role=target_spec.role,
                    target_provider=target_spec.provider,
                    target_model=target_spec.model,
                    challenge_point=challenge_point,
                    response=response_text,
                    reasoning_adjustment=reasoning_shift,
                    is_simulated=is_sim
                )
                challenge_items.append(item)

                if notify_fn:
                    notify_fn("challenge_exchange", {"item": item.model_dump()})

            except BudgetExceededError:
                raise
            except Exception as exc:
                self.failures_encountered += 1
                detail = self._error_detail(exc)
                logger.warning("Debate exchange failed: %s", detail)
                if notify_fn:
                    notify_fn("challenge_failed", {"challenger_id": challenger_fb.specialist_id,
                                                "target_specialist_id": target_fb.specialist_id,
                                                "error": detail})

        return challenge_items

    async def _run_coordinator_synthesis(
        self,
        idea: StartupIdeaInput,
        specialist_feedbacks: List[SpecialistFeedback],
        challenges: List[ChallengeResponseItem]
    ) -> CoordinatorCombinedReview:
        """
        Run the independent coordinator agent.
        Explicitly tracks coordinator failures and avoids masking errors as normal success.
        """
        adapter = get_provider_adapter("mock")

        failed_specialists = [f for f in specialist_feedbacks if f.status in ["failed", "timed_out"]]

        coordinator_context = {
            "idea": idea.model_dump(),
            "reviews": [review_context(f) for f in specialist_feedbacks],
            "challenges": [c.model_dump() for c in challenges],
        }

        start_t = time.perf_counter()
        try:
            response = await self._safe_provider_call(
                adapter=adapter,
                task="coordinator_synthesis",
                system_prompt=COORDINATOR_SYSTEM_PROMPT,
                user_prompt=json.dumps(coordinator_context, ensure_ascii=False),
                timeout_seconds=self.budget.timeout_seconds
            )
            duration_ms = (time.perf_counter() - start_t) * 1000

            parsed = validate_result("coordinator_synthesis", response)
            evidence_assessment = EvidenceSufficiencyAssessment.model_validate(parsed["evidence_sufficiency"])
            experiments = [ValidationExperiment.model_validate(exp) for exp in parsed["next_experiments"]]

            failure_impact = parsed.get("failure_impact_analysis") if failed_specialists else None
            if failed_specialists and not failure_impact:
                missing_roles = ", ".join([f.role for f in failed_specialists])
                failure_impact = (
                    f"Notice: {len(failed_specialists)} specialist(s) [{missing_roles}] failed or timed out during the review. "
                    f"Critical evaluation in these specific technical/operational areas could not be verified, degrading overall confidence. "
                    f"Founders must validate these omitted domains independently before committing resources."
                )

            if response.provider == "mock":
                provenance = "Deterministic mock synthesis"
            elif response.is_simulated:
                provenance = "Simulated synthesis"
            else:
                provenance = "Live provider synthesis"

            return CoordinatorCombinedReview(
                summary=(f"[{provenance}; provider={response.provider}; model={response.model}] {parsed['summary']}"),
                priorities=parsed["priorities"],
                disagreements=parsed["disagreements"],
                next_experiments=experiments,
                evidence_sufficiency=evidence_assessment,
                failure_impact_analysis=failure_impact,
                disclaimer="Decision support only. Not an investment recommendation. Consensus among AI agents does not constitute proof of market demand.",
                is_fallback=False,
                status="success",
                latency_ms=round(duration_ms, 2),
                token_usage={
                    "input_tokens": response.input_tokens,
                    "output_tokens": response.output_tokens,
                    "total_tokens": response.total_tokens
                },
                cost_estimate_usd=response.cost_estimate_usd
            )

        except BudgetExceededError as be:
            self.budget_stopped = True
            duration_ms = (time.perf_counter() - start_t) * 1000
            return CoordinatorCombinedReview(
                summary="[BUDGET STOPPED] Coordinator synthesis halted because the configured call or token cap was reached.",
                priorities=["Review individual completed specialist feedback cards."],
                disagreements=[],
                next_experiments=[],
                evidence_sufficiency=EvidenceSufficiencyAssessment(
                    status="insufficient",
                    analysis="Coordinator could not evaluate evidence sufficiency due to budget stop."
                ),
                failure_impact_analysis=f"Budget limit reached ({be}). Automated coordinator synthesis could not complete.",
                disclaimer="Decision support only. Not an investment recommendation.",
                is_fallback=True,
                status="failed",
                latency_ms=round(duration_ms, 2)
            )

        except asyncio.TimeoutError:
            duration_ms = (time.perf_counter() - start_t) * 1000
            return CoordinatorCombinedReview(
                summary="[COORDINATOR TIMEOUT] Coordinator synthesis failed because the upstream model timed out.",
                priorities=["Review completed specialist feedback directly."],
                disagreements=[],
                next_experiments=[],
                evidence_sufficiency=EvidenceSufficiencyAssessment(
                    status="insufficient",
                    analysis="Coordinator evaluation timed out."
                ),
                failure_impact_analysis=f"Coordinator call timed out after {self.budget.timeout_seconds}s. This is fallback guidance only.",
                disclaimer="Decision support only. Not an investment recommendation.",
                is_fallback=True,
                status="timed_out",
                latency_ms=round(duration_ms, 2)
            )

        except Exception as e:
            error_detail = self._error_detail(e)
            duration_ms = (time.perf_counter() - start_t) * 1000
            return CoordinatorCombinedReview(
                summary=f"[COORDINATOR FAILED] Coordinator synthesis failed due to an execution error: {error_detail}",
                priorities=["Review completed specialist feedback directly."],
                disagreements=[],
                next_experiments=[],
                evidence_sufficiency=EvidenceSufficiencyAssessment(
                    status="insufficient",
                    analysis="Coordinator evaluation encountered an execution error."
                ),
                failure_impact_analysis=f"Coordinator encountered an error ({error_detail}). This is an explicit fallback report.",
                disclaimer="Decision support only. Not an investment recommendation.",
                is_fallback=True,
                status="failed",
                latency_ms=round(duration_ms, 2)
            )

    @staticmethod
    def _error_detail(error):
        from app.config.settings import settings
        from app.models.connectors.base_connector import BaseAIAdapter
        detail = BaseAIAdapter.sanitize_api_keys(str(error), settings.openai_api_key, settings.gemini_api_key)
        if isinstance(error, ResponseFailure):
            return detail
        return f"{'timeout' if isinstance(error, asyncio.TimeoutError) else 'provider_error'}: {detail}"


    def _build_execution_summary(self, budget_stopped: bool = False) -> Dict[str, Any]:
        """Produce the aggregated execution summary."""
        return {
            "total_latency_ms": round(self.total_latency_ms, 2),
            "total_tokens": self.tokens_used,
            "total_cost_usd": round(self.total_cost_usd, 6),
            "calls_made": self.calls_made,
            "budget_stopped": budget_stopped or self.budget_stopped,
            "failures_encountered": self.failures_encountered
        }
