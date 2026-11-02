"""
Gemini Provider Adapter for Multiple AI Review Board.
Connects to Google GenAI API using google-genai SDK, normalizes responses,
tracks token usage, and calculates real API costs.
"""

import asyncio
import json
import time
from typing import Optional, Dict, Any
from app.config.settings import settings
from app.models.connectors.base_connector import BaseAIAdapter, NormalizedProviderResponse


class GeminiAdapter(BaseAIAdapter):
    """Adapter for Google Gemini models (e.g. gemini-1.5-flash, gemini-2.0-flash)."""
    provider_name = "gemini"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.gemini_api_key
        self._client = None
        if self.api_key:
            try:
                from google import genai
                self._client = genai.Client(api_key=self.api_key)
            except Exception:
                self._client = None

    async def call(
        self,
        system_prompt: str,
        user_prompt: str,
        model: Optional[str] = "gemini-1.5-flash",
        timeout_seconds: float = 15.0,
        temperature: float = 0.2,
        simulate_failure: Optional[str] = None,
    ) -> NormalizedProviderResponse:
        active_model = model or getattr(settings, "gemini_model", "gemini-1.5-flash")
        start_time = time.perf_counter()

        if not self.api_key or not self._client:
            raise ValueError(
                "Gemini API key not configured or google-genai library unavailable. "
                "Configure GEMINI_API_KEY in .env or switch to the Deterministic Mock provider."
            )

        safe_user_prompt = self.sanitize_prompt_data(user_prompt)
        combined_prompt = f"System Instructions:\n{system_prompt}\n\nIMPORTANT: Return ONLY a valid JSON object matching the requested schema without markdown backticks.\n\nUser Input:\n{safe_user_prompt}"

        def _sync_gemini_call():
            try:
                # Use standard client generation
                response = self._client.models.generate_content(
                    model=active_model,
                    contents=combined_prompt,
                )
                return response
            except Exception as e:
                raise e

        try:
            # Enforce timeout over threaded sync call
            response = await asyncio.wait_for(
                asyncio.to_thread(_sync_gemini_call),
                timeout=timeout_seconds
            )
            raw_text = response.text or "{}"
            latency = (time.perf_counter() - start_time) * 1000

            # Usage estimation or extraction
            in_tokens = len(combined_prompt) // 4
            out_tokens = len(raw_text) // 4
            if hasattr(response, "usage_metadata") and response.usage_metadata:
                in_tokens = getattr(response.usage_metadata, "prompt_token_count", in_tokens)
                out_tokens = getattr(response.usage_metadata, "candidates_token_count", out_tokens)

            total_tokens = in_tokens + out_tokens
            cost = self.calculate_cost(self.provider_name, active_model, in_tokens, out_tokens)

            try:
                parsed = json.loads(self.clean_json_string(raw_text))
            except Exception:
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
            raise asyncio.TimeoutError(f"Gemini call to {active_model} timed out after {timeout_seconds}s")
        except Exception as e:
            sanitized_err = self.sanitize_api_keys(str(e), self.api_key)
            raise RuntimeError(f"Gemini API Error: {sanitized_err}")

