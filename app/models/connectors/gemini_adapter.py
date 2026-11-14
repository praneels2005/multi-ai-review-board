"""
Gemini Provider Adapter for Multiple AI Review Board.
Connects to Google GenAI API using google-genai SDK, normalizes responses,
tracks token usage, and calculates real API costs.
"""

import asyncio
import json
import time
from typing import Optional, Dict, Any
from google.genai import types
import httpx
from app.config.settings import settings
from app.models.connectors.base_connector import AITask, BaseAIAdapter, NormalizedProviderResponse
from app.models.connectors.execution_usage import ProviderCallError, ProviderTimeoutError, usage_counts, exception_usage, conservative_tokens


class GeminiAdapter(BaseAIAdapter):
    """Adapter for Google Gemini models (e.g. gemini-1.5-flash, gemini-2.0-flash)."""
    provider_name = "gemini"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.gemini_api_key
        self._client = None
        if self.api_key:
            try:
                from google import genai
                self._client = genai.Client(api_key=self.api_key, http_options=types.HttpOptions(
                    api_version="v1beta",
                    retry_options=types.HttpRetryOptions(attempts=1),
                    httpx_async_client=httpx.AsyncClient(transport=httpx.AsyncHTTPTransport(retries=0)),
                ))
            except Exception:
                self._client = None

    def check_configuration(self):
        super().check_configuration()
        if not self.api_key or not self._client:
            raise ValueError(
                "Gemini API key not configured or google-genai library unavailable. "
                "Configure GEMINI_API_KEY in .env or switch to the Deterministic Mock provider."
            )

    async def call(
        self,
        system_prompt: str,
        user_prompt: str,
        model: Optional[str] = "gemini-3.8-flash",
        timeout_seconds: float = 15.0,
        temperature: float = 0.2,
        simulate_failure: Optional[str] = None,
        *,
        task: AITask = "specialist_review",
        max_output_tokens: int = 4096,
    ) -> NormalizedProviderResponse:
        active_model = model or getattr(settings, "gemini_model", "gemini-3.5-flash-lite")
        start_time = time.perf_counter()

        self.check_configuration()

        safe_user_prompt = self.sanitize_prompt_data(user_prompt)
        combined_prompt = f"System Instructions:\n{system_prompt}\n\nIMPORTANT: Return ONLY a valid JSON object matching the requested schema without markdown backticks.\n\nUser Input:\n{safe_user_prompt}"

        models_to_try = [active_model]
        if active_model != "gemini-3.5-flash-lite":
            models_to_try.append("gemini-3.5-flash-lite")

        for current_model in models_to_try:
            active_model = current_model
            try:
                # Native async transport: no unbounded worker thread after cancellation.
                response = await self.bounded_request(
                    self._client.aio.models.generate_content(
                        model=active_model, contents=combined_prompt,
                        config=types.GenerateContentConfig(
                            temperature=temperature, max_output_tokens=max_output_tokens,
                            response_mime_type="application/json",
                            http_options=types.HttpOptions(
                                api_version="v1beta",
                                timeout=max(1, int(timeout_seconds * 1000)),
                                retry_options=types.HttpRetryOptions(attempts=1),
                            ),
                        ),
                    ), timeout_seconds,
                )
                raw_text = response.text or "{}"
                latency = (time.perf_counter() - start_time) * 1000

                counts = usage_counts(getattr(response, "usage_metadata", None), self.estimate_input_tokens(system_prompt, user_prompt), conservative_tokens(raw_text))
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
                    f"Gemini call to {active_model} timed out after {timeout_seconds}s; local await cancelled, remote completion and billing are unknown",
                    usage=exception_usage(exc),
                ) from None
            except Exception as e:
                # SDK timeout types need not inherit asyncio.TimeoutError.
                if e.__class__.__name__ == "APITimeoutError":
                    raise ProviderTimeoutError(f"Gemini request timed out; remote completion and billing are unknown", usage=exception_usage(e)) from None
                status = getattr(e, "status_code", getattr(e, "code", None))
                is_capacity_error = (status in [503, 429] or "503" in str(e) or "high demand" in str(e).lower())
                if is_capacity_error and current_model != models_to_try[-1]:
                    # Automatically fallback to gemini-3.5-flash-lite on high demand
                    continue
                sanitized_err = self.sanitize_api_keys(str(e), self.api_key)
                raise ProviderCallError(f"Gemini API Error: {sanitized_err}",
                                        retryable=(status in [429, 503] or is_capacity_error), usage=exception_usage(e)) from None
