"""
OpenAI Provider Adapter for Multiple AI Review Board.
Connects to OpenAI API using AsyncOpenAI, normalizes responses,
tracks token usage, and calculates real API costs.
"""

import asyncio
import json
import time
import httpx
from typing import Optional, Dict, Any
from app.config.settings import settings
from app.models.connectors.base_connector import AITask, BaseAIAdapter, NormalizedProviderResponse
from app.models.connectors.execution_usage import ProviderCallError, ProviderTimeoutError, usage_counts, exception_usage, conservative_tokens


class OpenAIAdapter(BaseAIAdapter):
    """Adapter for OpenAI models (e.g. gpt-4o-mini, gpt-4o)."""
    provider_name = "openai"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.openai_api_key
        self._client = None
        if self.api_key:
            try:
                from openai import AsyncOpenAI
                self._client = AsyncOpenAI(api_key=self.api_key, max_retries=0)
            except ImportError:
                self._client = None

    def check_configuration(self):
        super().check_configuration()
        if not self.api_key or not self._client:
            raise ValueError(
                "OpenAI API key not configured or client library unavailable. "
                "Configure OPENAI_API_KEY in .env or switch to the Deterministic Mock provider."
            )

    async def call(
        self,
        system_prompt: str,
        user_prompt: str,
        model: Optional[str] = "gpt-4o-mini",
        timeout_seconds: float = 15.0,
        temperature: float = 0.2,
        simulate_failure: Optional[str] = None,
        *,
        task: AITask = "specialist_review",
        max_output_tokens: int = 4096,
    ) -> NormalizedProviderResponse:
        active_model = model or "gpt-4o-mini"
        start_time = time.perf_counter()

        self.check_configuration()

        # Prompt injection defense: treat input data safely
        safe_user_prompt = self.sanitize_prompt_data(user_prompt)

        messages = [
            {
                "role": "system",
                "content": f"{system_prompt}\n\nIMPORTANT: Return ONLY a valid JSON object matching the requested schema without markdown backticks."
            },
            {"role": "user", "content": safe_user_prompt}
        ]

        async def _make_api_call():
            response = await self._client.chat.completions.create(
                model=active_model,
                messages=messages,
                temperature=temperature,
                response_format={"type": "json_object"},
                timeout=timeout_seconds,
                max_completion_tokens=max_output_tokens
            )
            return response

        try:
            # Enforce per-call timeout
            response = await self.bounded_request(_make_api_call(), timeout_seconds)
            raw_text = response.choices[0].message.content or "{}"
            latency = (time.perf_counter() - start_time) * 1000

            counts = usage_counts(response.usage, self.estimate_input_tokens(system_prompt, user_prompt), conservative_tokens(raw_text))
            in_tokens, out_tokens, total_tokens = (counts[k] for k in ("input_tokens", "output_tokens", "total_tokens"))

            cost = self.calculate_cost(self.provider_name, active_model, in_tokens, out_tokens)

            # Sanitize before parsing so neither structured results nor raw text leak keys.
            raw_text = self.sanitize_api_keys(raw_text, self.api_key)
            parsed, parse_error = self.parse_output(raw_text, task)

            return NormalizedProviderResponse(
                raw_text=self.sanitize_api_keys(raw_text, self.api_key),
                parsed_json=parsed,
                provider=self.provider_name,
                model=active_model,
                is_simulated=False,
                latency_ms=round(latency, 2),
                input_tokens=in_tokens,
                output_tokens=out_tokens,
                total_tokens=total_tokens,
                cost_estimate_usd=cost,
                usage_source=counts["usage_source"],
                usage_breakdown_estimated=counts["usage_breakdown_estimated"],
                error=parse_error
            )

        except (asyncio.TimeoutError, httpx.TimeoutException) as exc:
            raise ProviderTimeoutError(
                f"Openai call to {active_model} timed out after {timeout_seconds}s; local await cancelled, remote completion and billing are unknown",
                usage=exception_usage(exc),
            ) from None
        except Exception as e:
            # SDK timeout types need not inherit asyncio.TimeoutError.
            if e.__class__.__name__ == "APITimeoutError":
                raise ProviderTimeoutError(f"Openai request timed out; remote completion and billing are unknown", usage=exception_usage(e)) from None
            sanitized_err = self.sanitize_api_keys(str(e), self.api_key)
            status = getattr(e, "status_code", getattr(e, "code", None))
            raise ProviderCallError(f"Openai API Error: {sanitized_err}",
                                    retryable=(status == 429), usage=exception_usage(e)) from None
