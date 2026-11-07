"""
Deterministic Mock Adapter for Multiple AI Review Board.
Provides offline, deterministic, rich generation without requiring any API keys.
Accurately simulates latency, token usage, cost, and failure modes for testing.
Grounded strictly in supplied evidence (not superficial keywords).
"""

import asyncio
import json
import time
from typing import Optional, Dict, Any
from app.models.connectors.base_connector import AITask, BaseAIAdapter, NormalizedProviderResponse
from app.models.connectors.execution_usage import ProviderCallError, ProviderTimeoutError, usage_counts, exception_usage, conservative_tokens


class DeterministicMockAdapter(BaseAIAdapter):
    """Deterministic mock adapter generating rich domain-specific review responses."""
    provider_name = "mock"

    def estimate_input_tokens(self, system_prompt, user_prompt):
        # Exact input count for the mock's defined simulated tokenizer.
        return len(system_prompt + user_prompt) // 4

    async def call(
        self,
        system_prompt: str,
        user_prompt: str,
        model: Optional[str] = "mock-deterministic",
        timeout_seconds: float = 15.0,
        temperature: float = 0.2,
        simulate_failure: Optional[str] = None,
        *,
        task: AITask = "specialist_review",
        max_output_tokens: int = 4096,
    ) -> NormalizedProviderResponse:
        start_time = time.perf_counter()
        active_model = model or "mock-deterministic"

        # Handle failure simulations for tests and demo walkthroughs
        if simulate_failure == "timeout":
            if timeout_seconds > 0:
                await asyncio.sleep(timeout_seconds)
            raise ProviderTimeoutError(f"Mock call to {active_model} timed out after {timeout_seconds}s; local simulation stopped", request_sent=False)

        if simulate_failure == "provider_error":
            await asyncio.sleep(min(0.1, timeout_seconds / 2))
            raise ProviderCallError(f"Simulated upstream connection failure to provider '{self.provider_name}'", retryable=True, request_sent=False)

        if simulate_failure == "malformed_output":
            await asyncio.sleep(min(0.15, timeout_seconds / 2))
            malformed_text = '{"status": "incomplete", "strengths": ["Premature closure", "error": syntax_error'
            latency = (time.perf_counter() - start_time) * 1000
            return NormalizedProviderResponse(
                raw_text=malformed_text,
                parsed_json=None,
                provider=self.provider_name,
                model=active_model,
                is_simulated=True,
                latency_ms=round(latency, 2),
                input_tokens=150,
                output_tokens=30,
                total_tokens=180,
                cost_estimate_usd=self.calculate_cost(self.provider_name, active_model, 150, 30),
                usage_source="simulated",
                error="malformed_json: Malformed JSON response from mock provider"
            )

        # Realistic simulated network latency (150ms to 350ms)
        await asyncio.sleep(min(0.15, timeout_seconds / 2))

        # Generate deterministic response based on prompt contents
        parsed_data = self._generate_deterministic_content(task, system_prompt, user_prompt)
        raw_text = json.dumps(parsed_data, indent=2)
        parsed_data, output_error = self.parse_output(raw_text, task)

        latency = (time.perf_counter() - start_time) * 1000
        input_tokens = len(system_prompt + user_prompt) // 4
        output_tokens = len(raw_text) // 4
        total_tokens = input_tokens + output_tokens
        cost = self.calculate_cost(self.provider_name, active_model, input_tokens, output_tokens)

        return NormalizedProviderResponse(
            raw_text=raw_text,
            parsed_json=parsed_data,
            provider=self.provider_name,
            model=active_model,
            is_simulated=True,
            latency_ms=round(latency, 2),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            cost_estimate_usd=cost,
            usage_source="simulated",
            error=output_error
        )

    def _generate_deterministic_content(
        self, task: AITask, system_prompt: str, user_prompt: str
    ) -> Dict[str, Any]:
        """Select the operation from trusted caller metadata, never prompt text."""
        if task == "panel_generation":
            return self._generate_panel(user_prompt)
        if task == "specialist_review":
            return self._generate_specialist_feedback(system_prompt, user_prompt)
        if task == "challenge_generation":
            return self._generate_challenger_point(user_prompt)
        if task == "challenge_response":
            return self._generate_target_defense(user_prompt)
        if task == "coordinator_synthesis":
            return self._generate_coordinator_synthesis(user_prompt)
        raise ValueError(f"Unsupported AI task: {task!r}")

    def _generate_panel(self, user_prompt: str) -> Dict[str, Any]:
        from app.models.connectors.mock_archetypes import generate_panel
        return {"specialists": generate_panel(user_prompt)}

    def _generate_specialist_feedback(self, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
        from app.models.connectors.mock_specialist import specialist_feedback
        return specialist_feedback(user_prompt)

    def _generate_challenger_point(self, user_prompt: str) -> Dict[str, Any]:
        from app.models.connectors.mock_deliberation import challenge
        return challenge(user_prompt)

    def _generate_target_defense(self, user_prompt: str) -> Dict[str, Any]:
        from app.models.connectors.mock_deliberation import respond
        return respond(user_prompt)

    def _generate_coordinator_synthesis(self, user_prompt: str) -> Dict[str, Any]:
        from app.models.connectors.mock_deliberation import synthesize
        return synthesize(user_prompt)
