"""
Connector Factory for Multiple AI Review Board.
Instantiates and caches provider adapters (Mock, OpenAI, Gemini).
"""

from typing import Dict
from app.models.connectors.base_connector import BaseAIAdapter
from app.models.connectors.mock_adapter import DeterministicMockAdapter
from app.models.connectors.openai_adapter import OpenAIAdapter
from app.models.connectors.gemini_adapter import GeminiAdapter

_ADAPTER_CACHE: Dict[str, BaseAIAdapter] = {}


def get_provider_adapter(provider: str) -> BaseAIAdapter:
    """Retrieve or instantiate the adapter for a given provider."""
    normalized_provider = (provider or "mock").strip().lower()

    if normalized_provider not in _ADAPTER_CACHE:
        if normalized_provider == "mock":
            _ADAPTER_CACHE[normalized_provider] = DeterministicMockAdapter()
        elif normalized_provider == "openai":
            _ADAPTER_CACHE[normalized_provider] = OpenAIAdapter()
        elif normalized_provider in ["gemini", "google"]:
            _ADAPTER_CACHE[normalized_provider] = GeminiAdapter()
        else:
            # Fallback to mock adapter
            _ADAPTER_CACHE[normalized_provider] = DeterministicMockAdapter()

    return _ADAPTER_CACHE[normalized_provider]

