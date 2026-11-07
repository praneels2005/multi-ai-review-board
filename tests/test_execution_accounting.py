"""Atomic accounting, visible estimates, safe retries and bounded SDK attempts."""
import asyncio
import json
import time
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.models.connectors.base_connector import NormalizedProviderResponse
from app.models.connectors.execution_usage import ProviderCallError, ProviderTimeoutError, usage_counts
from app.models.connectors.mock_adapter import DeterministicMockAdapter
from app.models.connectors.openai_adapter import OpenAIAdapter
from app.models.connectors.gemini_adapter import GeminiAdapter
from app.schemas.review_board_schema import BudgetConfig
from app.services.panel_service import PanelService
from app.services.review_orchestrator import ReviewBoardOrchestrator, BudgetExceededError


def normalized(total=50, source="provider_reported", parsed=None):
    return NormalizedProviderResponse(raw_text="{}", parsed_json=parsed or {}, provider="openai",
        model="test", is_simulated=False, latency_ms=1, input_tokens=10,
        output_tokens=max(0, total - 10), total_tokens=total, usage_source=source)


class FakeAdapter:
    provider_name = "openai"
    def __init__(self, total=50, error=None):
        self.total, self.error, self.calls = total, error, 0
    def estimate_input_tokens(self, system, user):
        return 100
    async def call(self, **kwargs):
        self.calls += 1
        await asyncio.sleep(0)
        if self.error:
            raise self.error
        return normalized(self.total)


async def call(orchestrator, adapter, task="specialist_review"):
    return await orchestrator._safe_provider_call(adapter, task, "system", "user")


def budget(**kwargs):
    return BudgetConfig(max_output_tokens_per_call=100, max_retries=0, **kwargs)


@pytest.mark.anyio
async def test_exact_call_cap_boundary():
    orchestrator = ReviewBoardOrchestrator(budget(call_cap=2))
    adapter = FakeAdapter()
    await call(orchestrator, adapter)
    await call(orchestrator, adapter)
    with pytest.raises(BudgetExceededError):
        await call(orchestrator, adapter)
    assert adapter.calls == orchestrator.calls_made == 2
    assert orchestrator.tokens_used == 100
    assert orchestrator.reserved_tokens == 0


@pytest.mark.anyio
async def test_exact_token_boundary_and_truthful_overrun():
    adapter = FakeAdapter(total=1000)
    orchestrator = ReviewBoardOrchestrator(budget(token_cap=1000))
    await call(orchestrator, adapter)
    assert orchestrator.tokens_used == 1000 and orchestrator.budget_stopped
    with pytest.raises(BudgetExceededError):
        await call(orchestrator, adapter)
    assert adapter.calls == 1
    assert orchestrator._build_execution_summary()["token_overrun"] == 0
    adapter = FakeAdapter(total=1200)
    orchestrator = ReviewBoardOrchestrator(budget(token_cap=1000))
    await call(orchestrator, adapter)
    summary = orchestrator._build_execution_summary()
    assert summary["total_tokens"] == summary["reported_tokens"] == 1200
    assert summary["token_overrun"] == 200 and summary["remaining_tokens"] == 0
    assert summary["reservation_overrun_tokens"] == 1000
    with pytest.raises(BudgetExceededError):
        await call(orchestrator, adapter)
    assert adapter.calls == 1


@pytest.mark.anyio
async def test_token_reservation_boundary_prevents_dispatch():
    adapter = FakeAdapter()
    orchestrator = ReviewBoardOrchestrator(budget(token_cap=1000))
    orchestrator.tokens_used = 801
    with pytest.raises(BudgetExceededError):
        await call(orchestrator, adapter)
    assert adapter.calls == orchestrator.calls_made == orchestrator.reserved_tokens == 0


@pytest.mark.anyio
@pytest.mark.parametrize("cap,expected", [(3, 3), (10, 5)])
async def test_concurrent_reservations_cannot_oversubscribe(cap, expected):
    gate = asyncio.Event()
    class Gated(FakeAdapter):
        async def call(self, **kwargs):
            self.calls += 1
            await gate.wait()
            return normalized(50)
    adapter = Gated()
    orchestrator = ReviewBoardOrchestrator(budget(token_cap=1000, call_cap=cap))
    tasks = [asyncio.create_task(call(orchestrator, adapter)) for _ in range(10)]
    for _ in range(5):
        await asyncio.sleep(0)
    assert adapter.calls == orchestrator.calls_made == expected
    assert orchestrator.reserved_tokens == expected * 200
    assert orchestrator.tokens_used == 0
    assert orchestrator._build_execution_summary()["remaining_tokens"] >= 0
    gate.set()
    results = await asyncio.gather(*tasks, return_exceptions=True)
    assert sum(isinstance(r, NormalizedProviderResponse) for r in results) == expected
    assert orchestrator.tokens_used == expected * 50
    assert orchestrator.reserved_tokens == 0
    assert len(orchestrator.attempts) == expected


@pytest.mark.anyio
@pytest.mark.parametrize("with_usage", [True, False])
async def test_failed_request_is_charged_with_known_usage_or_full_estimate(with_usage):
    error = ProviderCallError("Upstream failed", usage={"prompt_tokens": 30, "completion_tokens": 70, "total_tokens": 100} if with_usage else None)
    adapter = FakeAdapter(error=error)
    orchestrator = ReviewBoardOrchestrator(budget())
    with pytest.raises(ProviderCallError):
        await call(orchestrator, adapter)
    summary = orchestrator._build_execution_summary()
    assert summary["calls_made"] == 1 and summary["reserved_tokens"] == 0
    assert summary["total_tokens"] == (100 if with_usage else 200)
    assert summary["reported_tokens" if with_usage else "estimated_tokens"] == summary["total_tokens"]
    assert summary["provider_attempts"][0]["status"] == "provider_error"


@pytest.mark.anyio
async def test_cancelled_attempt_reconciles_reservation_without_refund_claim():
    started = asyncio.Event()
    class Wait(FakeAdapter):
        async def call(self, **kwargs):
            started.set()
            await asyncio.Event().wait()
    orchestrator = ReviewBoardOrchestrator(budget())
    task = asyncio.create_task(call(orchestrator, Wait()))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert orchestrator.reserved_tokens == 0 and orchestrator.tokens_used == 200
    assert orchestrator.attempts[0]["status"] == "cancelled"


@pytest.mark.anyio
async def test_shared_budget_charges_specialist_debate_and_coordinator_equally():
    orchestrator = ReviewBoardOrchestrator(budget(call_cap=4))
    adapter = FakeAdapter()
    tasks = ["specialist_review", "challenge_generation", "challenge_response", "coordinator_synthesis"]
    for task in tasks:
        await call(orchestrator, adapter, task)
    summary = orchestrator._build_execution_summary()
    assert summary["calls_made"] == 4 and summary["total_tokens"] == 200
    assert [a["task"] for a in summary["provider_attempts"]] == tasks
    assert summary["total_tokens"] == sum(a["total_tokens"] for a in summary["provider_attempts"])
    with pytest.raises(BudgetExceededError):
        await call(orchestrator, adapter)


@pytest.fixture(scope="module")
def panel_context():
    async def run():
        idea = PanelService.get_presets()["devtool_ebpf"]["idea"]
        panel = await PanelService.generate_panel(idea)
        return idea, panel
    return asyncio.run(run())


@pytest.mark.anyio
@pytest.mark.parametrize("call_cap,token_cap,expected", [(2, 50000, 2), (1, 50000, 1), (2, 1000, 1)])
async def test_safe_retry_obeys_attempt_and_token_caps(panel_context, monkeypatch, call_cap, token_cap, expected):
    idea, panel = panel_context
    class Retry(FakeAdapter):
        async def call(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise ProviderCallError("Explicitly rejected", retryable=True,
                    usage={"prompt_tokens": 850, "completion_tokens": 0, "total_tokens": 850})
            payload = DeterministicMockAdapter()._generate_deterministic_content("specialist_review", "", kwargs["user_prompt"])
            return normalized(50, parsed=payload)
    adapter = Retry()
    monkeypatch.setattr("app.services.review_orchestrator.get_provider_adapter", lambda provider: adapter)
    orchestrator = ReviewBoardOrchestrator(BudgetConfig(call_cap=call_cap, token_cap=token_cap, max_retries=1, max_output_tokens_per_call=100))
    result = await orchestrator._run_single_specialist_with_retry(panel[0], idea, {"E1", "E2"})
    assert orchestrator.calls_made == adapter.calls == expected
    assert result.status == ("success" if expected == 2 else "failed")
    assert orchestrator.tokens_used == (900 if expected == 2 else 850)


@pytest.mark.anyio
@pytest.mark.parametrize("kind", ["configuration", "schema", "malformed", "ambiguous_api", "timeout"])
async def test_nonretryable_or_ambiguous_outcome_does_not_repeat_paid_requests(panel_context, monkeypatch, kind):
    idea, panel = panel_context
    class Bad(FakeAdapter):
        def check_configuration(self):
            if kind == "configuration":
                raise ValueError("Missing API configuration")
        async def call(self, **kwargs):
            self.calls += 1
            if kind == "timeout":
                raise ProviderTimeoutError("Remote completion unknown")
            if kind == "ambiguous_api":
                raise ProviderCallError("Connection lost after dispatch")
            r = normalized()
            r.error = "schema_validation: missing field" if kind == "schema" else "malformed_json: invalid JSON"
            return r
    adapter = Bad()
    monkeypatch.setattr("app.services.review_orchestrator.get_provider_adapter", lambda provider: adapter)
    orchestrator = ReviewBoardOrchestrator(BudgetConfig(max_retries=1))
    result = await orchestrator._run_single_specialist_with_retry(panel[0], idea, {"E1", "E2"})
    assert result.status in {"failed", "timed_out"}
    assert adapter.calls == orchestrator.calls_made == (0 if kind == "configuration" else 1)
    assert result.validation_experiment is None


@pytest.mark.anyio
async def test_budget_exhaustion_preserves_completed_exchange(panel_context):
    idea, panel = panel_context
    orchestrator = ReviewBoardOrchestrator(BudgetConfig(call_cap=6, token_cap=100000))
    session = await orchestrator.execute_board(idea, panel)
    assert session.status == "budget_stopped"
    assert len(session.specialist_reviews) == 4
    assert all(r.status == "success" for r in session.specialist_reviews)
    assert len(session.challenge_round) == 1
    assert session.combined_review is None
    assert session.execution_summary["calls_made"] == 6
    assert session.execution_summary["reserved_tokens"] == 0


@pytest.mark.parametrize("provider", ["openai", "gemini"])
def test_sdk_config_disables_hidden_retries(provider):
    if provider == "openai":
        with patch("openai.AsyncOpenAI") as constructor:
            OpenAIAdapter(api_key="test-key")
            assert constructor.call_args.kwargs["max_retries"] == 0
    else:
        with patch("google.genai.Client") as constructor:
            GeminiAdapter(api_key="test-key")
            options = constructor.call_args.kwargs["http_options"]
            assert options.retry_options.attempts == 1
            # A custom async httpx client prevents SDK selection of aiohttp retries.
            assert options.httpx_async_client is not None
            asyncio.run(options.httpx_async_client.aclose())


@pytest.mark.anyio
@pytest.mark.parametrize("provider", ["openai", "gemini"])
async def test_live_sdk_usage_and_explicit_request_limits(provider):
    observed = {}
    async def generate(**kwargs):
        observed.update(kwargs)
        if provider == "openai":
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"challenge_point":"Concern"}'))],
                usage=SimpleNamespace(prompt_tokens=40, completion_tokens=60, total_tokens=100))
        return SimpleNamespace(text='{"challenge_point":"Concern"}',
            usage_metadata=SimpleNamespace(prompt_token_count=40, candidates_token_count=30, thoughts_token_count=30, total_token_count=100))
    adapter = OpenAIAdapter(api_key="test-key") if provider == "openai" else GeminiAdapter(api_key="test-key")
    adapter._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=generate)),
                                      aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate)))
    result = await adapter.call("S", "U", task="challenge_generation", timeout_seconds=.2, max_output_tokens=123)
    assert result.total_tokens == 100 and result.input_tokens == 40 and result.output_tokens == 60
    assert result.usage_source == "provider_reported"
    if provider == "openai":
        assert observed["timeout"] == .2 and observed["max_completion_tokens"] == 123
    else:
        assert observed["config"].max_output_tokens == 123
        assert observed["config"].http_options.timeout == 200
        assert observed["config"].http_options.retry_options.attempts == 1


@pytest.mark.anyio
@pytest.mark.parametrize("provider", ["openai", "gemini", "mock"])
async def test_timeouts_are_bounded_and_not_retried(provider):
    async def generate(**kwargs):
        await asyncio.sleep(10)
    if provider == "mock":
        adapter = DeterministicMockAdapter()
    else:
        adapter = OpenAIAdapter(api_key="test-key") if provider == "openai" else GeminiAdapter(api_key="test-key")
        adapter._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=generate)),
                                          aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate)))
    started = time.perf_counter()
    with pytest.raises(ProviderTimeoutError):
        await adapter.call("S", "U", timeout_seconds=.03, simulate_failure="timeout")
    assert time.perf_counter() - started < .2


@pytest.mark.anyio
@pytest.mark.parametrize("provider", ["openai", "gemini"])
async def test_remote_work_can_outlive_local_timeout_without_duplicate_retry(panel_context, monkeypatch, provider):
    idea, panel = panel_context
    completion = asyncio.Event()
    started = 0
    async def remote():
        await asyncio.sleep(.05)
        completion.set()
    remote_task = None
    async def generate(**kwargs):
        nonlocal started, remote_task
        started += 1
        remote_task = asyncio.create_task(remote())
        await asyncio.shield(remote_task)
    adapter = OpenAIAdapter(api_key="test-key") if provider == "openai" else GeminiAdapter(api_key="test-key")
    adapter._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=generate)),
                                      aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate)))
    monkeypatch.setattr("app.services.review_orchestrator.get_provider_adapter", lambda provider: adapter)
    orchestrator = ReviewBoardOrchestrator(BudgetConfig(timeout_seconds=.1, max_retries=1))
    # SDK raises its own timeout while an independent upstream operation continues.
    async def timed_generate(**kwargs):
        await asyncio.wait_for(generate(**kwargs), timeout=.01)
    if provider == "openai":
        adapter._client.chat.completions.create = timed_generate
    else:
        adapter._client.aio.models.generate_content = timed_generate
    result = await orchestrator._run_single_specialist_with_retry(panel[0], idea, {"E1", "E2"})
    assert result.status == "timed_out" and started == orchestrator.calls_made == 1
    assert not completion.is_set()
    assert "unknown" in result.error_message
    assert orchestrator.attempts[0]["cancellation_uncertain"]
    await remote_task
    assert completion.is_set()


@pytest.mark.parametrize("usage", [None, {}, {"prompt_tokens": 50}, {"prompt_tokens": None, "completion_tokens": None}])
def test_missing_usage_is_conservatively_estimated_and_labeled(usage):
    result = usage_counts(usage, 100, 200)
    assert result["usage_source"] == "estimated"
    assert result["total_tokens"] >= 250


@pytest.mark.anyio
@pytest.mark.parametrize("provider", ["openai", "gemini"])
async def test_cancellation_resistant_sdk_is_bounded_and_blocks_duplicate_dispatch(provider):
    finish = asyncio.Event()
    started = 0
    async def generate(**kwargs):
        nonlocal started
        started += 1
        try:
            await finish.wait()
        except asyncio.CancelledError:
            # Simulate an SDK transport delaying cancellation. It must not hold up
            # the local timeout or let the adapter dispatch another paid request.
            await finish.wait()
    adapter = OpenAIAdapter(api_key="test-key") if provider == "openai" else GeminiAdapter(api_key="test-key")
    adapter._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=generate)),
                                      aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate)))
    begin = time.perf_counter()
    with pytest.raises(ProviderTimeoutError):
        await adapter.call("S", "U", timeout_seconds=.01)
    assert time.perf_counter() - begin < .15
    assert started == 1
    with pytest.raises(ValueError, match="has not finished cancellation"):
        await adapter.call("S", "U", timeout_seconds=.01)
    assert started == 1
    finish.set()
    await asyncio.gather(*adapter._pending_requests, return_exceptions=True)


@pytest.mark.anyio
@pytest.mark.parametrize("provider", ["openai", "gemini"])
async def test_failed_sdk_request_preserves_reported_usage(provider):
    class Rejected(Exception):
        status_code = 429
        body = {"usage": {"prompt_tokens": 31, "completion_tokens": 0, "total_tokens": 31}}
    async def generate(**kwargs):
        raise Rejected("Rate limit rejection")
    adapter = OpenAIAdapter(api_key="test-key") if provider == "openai" else GeminiAdapter(api_key="test-key")
    adapter._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=generate)),
                                      aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate)))
    orchestrator = ReviewBoardOrchestrator(BudgetConfig())
    with pytest.raises(ProviderCallError) as raised:
        await call(orchestrator, adapter)
    assert raised.value.retryable
    assert orchestrator.tokens_used == orchestrator.usage_by_source["provider_reported"] == 31
    assert orchestrator.reserved_tokens == 0


def test_authoritative_total_without_breakdown_is_not_replaced_by_an_estimate():
    counts = usage_counts({"total_tokens": 87}, 100, 200)
    assert counts["total_tokens"] == 87
    assert counts["input_tokens"] + counts["output_tokens"] == 87
    assert counts["usage_source"] == "provider_reported"
    assert counts["usage_breakdown_estimated"] is True
