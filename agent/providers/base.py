from __future__ import annotations
from typing import Protocol

class ProviderError(RuntimeError):
    """Sanitized provider failure; must not contain prompt/source/provider response."""

class ProviderTimeoutError(ProviderError):
    """Sanitized provider timeout, for distinct telemetry."""

class LLMProvider(Protocol):
    model: str
    def generate(self, prompt: str, format_schema: dict | None = None) -> str: ...
