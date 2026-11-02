"""
Base Connector Interface & Response Normalization.
Defines the unified adapter interface, structured response contract,
cost calculators, and prompt sanitization defenses.
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, Type, Literal
import json
import re
import time
from pydantic import BaseModel, Field


AITask = Literal[
    "panel_generation", "specialist_review", "challenge_generation",
    "challenge_response", "coordinator_synthesis",
]


class NormalizedProviderResponse(BaseModel):
    """Unified response contract across all AI providers."""
    raw_text: str
    parsed_json: Optional[Dict[str, Any]] = None
    provider: str
    model: str
    is_simulated: bool
    latency_ms: float
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cost_estimate_usd: float = 0.0
    error: Optional[str] = None


class BaseAIAdapter(ABC):
    """Abstract base class for all LLM providers in the review board."""
    provider_name: str

    @abstractmethod
    async def call(
        self,
        system_prompt: str,
        user_prompt: str,
        model: Optional[str] = None,
        timeout_seconds: float = 15.0,
        temperature: float = 0.2,
        simulate_failure: Optional[str] = None,
        *,
        task: AITask = "specialist_review",
    ) -> NormalizedProviderResponse:
        """Execute a caller-selected task and return a normalized response.

        Task is internal routing metadata, never inferred from prompt content.
        Live adapters use the supplied prompts; mock uses task to select its generator.
        The default preserves existing standalone specialist-review callers.
        """
        pass

    @staticmethod
    def sanitize_prompt_data(raw_text: str) -> str:
        """
        Treat input text as data rather than instructions.
        Wraps content and disarms prompt injection markers.
        """
        # Neutralize common prompt injection patterns
        sanitized = raw_text.replace("```", "'''")
        sanitized = re.sub(r'(?i)(ignore previous instructions|system prompt:|system override)', '[FILTERED]', sanitized)
        return f"<user_startup_data>\n{sanitized}\n</user_startup_data>"

    @staticmethod
    def calculate_cost(provider: str, model: str, input_tokens: int, output_tokens: int) -> float:
        """Calculate estimated cost in USD based on token counts and model pricing."""
        model_lower = model.lower() if model else ""
        
        # Per million token rates: (input_price_per_m, output_price_per_m)
        pricing_table = {
            "mock": (0.15, 0.60),
            "gpt-4o-mini": (0.15, 0.60),
            "gpt-4o": (2.50, 10.00),
            "gpt-4-turbo": (10.00, 30.00),
            "gemini-1.5-flash": (0.075, 0.30),
            "gemini-2.0-flash": (0.10, 0.40),
            "gemini-3.5-flash-lite": (0.075, 0.30),
            "claude-3-5-sonnet": (3.00, 15.00),
            "claude-3-haiku": (0.25, 1.25),
        }
        
        rate = pricing_table.get(model_lower)
        if not rate:
            # Fallback based on provider
            if "gemini" in model_lower or provider == "gemini":
                rate = (0.075, 0.30)
            elif "openai" in provider:
                rate = (0.15, 0.60)
            else:
                rate = (0.15, 0.60)
                
        input_cost = (input_tokens / 1_000_000.0) * rate[0]
        output_cost = (output_tokens / 1_000_000.0) * rate[1]
        return round(input_cost + output_cost, 6)

    @staticmethod
    def clean_json_string(text: str) -> str:
        """Extract and clean valid JSON from raw LLM output."""
        cleaned = text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            if len(lines) > 2 and lines[0].startswith("```"):
                # Remove first and last line
                cleaned = "\n".join(lines[1:-1]).strip()
        return cleaned

    @staticmethod
    def sanitize_api_keys(text: str, *keys: Optional[str]) -> str:
        """Strip sensitive API keys from strings to protect logs and responses."""
        sanitized = text
        for key in keys:
            if key and len(key) > 5:
                sanitized = sanitized.replace(key, "[REDACTED_API_KEY]")
        return sanitized

