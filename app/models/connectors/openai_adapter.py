"""
OpenAI Provider Adapter for Multiple AI Review Board.
Connects to OpenAI API using AsyncOpenAI, normalizes responses,
tracks token usage, and calculates real API costs.
"""

import asyncio
import json
import time
from typing import Optional, Dict, Any
from app.config.settings import settings
from app.models.connectors.base_connector import AITask, BaseAIAdapter, NormalizedProviderResponse


class OpenAIAdapter(BaseAIAdapter):
    """Adapter for OpenAI models (e.g. gpt-4o-mini, gpt-4o)."""
    provider_name = "openai"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.openai_api_key
        self._client = None
        if self.api_key:
            try:
                from openai import AsyncOpenAI
                self._client = AsyncOpenAI(api_key=self.api_key)
            except ImportError:
                self._client = None

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
    ) -> NormalizedProviderResponse:
        active_model = model or "gpt-4o-mini"
        start_time = time.perf_counter()

        if not self.api_key or not self._client:
            raise ValueError(
                "OpenAI API key not configured or client library unavailable. "
                "Configure OPENAI_API_KEY in .env or switch to the Deterministic Mock provider."
            )

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
                response_format={"type": "json_object"}
            )
            return response

        try:
            # Enforce per-call timeout
            response = await asyncio.wait_for(_make_api_call(), timeout=timeout_seconds)
            raw_text = response.choices[0].message.content or "{}"
            latency = (time.perf_counter() - start_time) * 1000

            # Usage tracking
            usage = response.usage
            in_tokens = usage.prompt_tokens if usage else len(system_prompt + user_prompt) // 4
            out_tokens = usage.completion_tokens if usage else len(raw_text) // 4
            total_tokens = usage.total_tokens if usage else in_tokens + out_tokens

            cost = self.calculate_cost(self.provider_name, active_model, in_tokens, out_tokens)

            try:
                parsed = json.loads(self.clean_json_string(raw_text))
            except Exception as parse_err:
                parsed = None

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
                error=None if parsed else "Failed to parse JSON response"
            )

        except asyncio.TimeoutError:
            raise asyncio.TimeoutError(f"OpenAI call to {active_model} timed out after {timeout_seconds}s")
        except Exception as e:
            sanitized_err = self.sanitize_api_keys(str(e), self.api_key)
            raise RuntimeError(f"OpenAI API Error: {sanitized_err}")

