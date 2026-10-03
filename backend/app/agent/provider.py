"""LLM provider abstraction layer.

The orchestrator talks only to this module, never directly to the openai
client.  Swapping providers means writing a new ProviderResponse-returning
function and pointing get_provider() at it — no agent logic changes.

Supported providers (LLM_PROVIDER env var):
  openai  — uses the OpenAI chat-completions API with native tool-calling
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from app.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class ToolCallRequest:
    """A single tool-call the model wants to make."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ProviderResponse:
    """Normalised response from any LLM provider.

    Either content is set (the model is done) or tool_calls is non-empty
    (the model wants to call tools before finishing).
    """

    content: str | None
    tool_calls: list[ToolCallRequest] = field(default_factory=list)
    finish_reason: str = "stop"
    prompt_tokens: int = 0
    completion_tokens: int = 0


# ---------------------------------------------------------------------------
# OpenAI implementation
# ---------------------------------------------------------------------------


def _build_openai_tools(tool_schemas: list[dict]) -> list[dict]:
    """Convert our internal tool-schema list to the OpenAI function-calling format."""
    return [
        {
            "type": "function",
            "function": {
                "name": schema["name"],
                "description": schema["description"],
                "parameters": schema["parameters"],
            },
        }
        for schema in tool_schemas
    ]


def call_openai(
    messages: list[dict],
    tool_schemas: list[dict],
    *,
    model: str | None = None,
) -> ProviderResponse:
    """Call OpenAI chat-completions with tool-calling enabled."""
    from openai import OpenAI  # lazy import so missing key never breaks startup

    settings = get_settings()
    client = OpenAI(api_key=settings.openai_api_key)
    model = model or settings.llm_model

    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
    }
    if tool_schemas:
        kwargs["tools"] = _build_openai_tools(tool_schemas)
        kwargs["tool_choice"] = "auto"

    logger.debug("LLM request | model=%s messages=%d tools=%d", model, len(messages), len(tool_schemas))
    resp = client.chat.completions.create(**kwargs)

    choice = resp.choices[0]
    msg = choice.message

    tool_calls: list[ToolCallRequest] = []
    if msg.tool_calls:
        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                args = {}
            tool_calls.append(ToolCallRequest(id=tc.id, name=tc.function.name, arguments=args))

    usage = resp.usage
    return ProviderResponse(
        content=msg.content,
        tool_calls=tool_calls,
        finish_reason=choice.finish_reason or "stop",
        prompt_tokens=usage.prompt_tokens if usage else 0,
        completion_tokens=usage.completion_tokens if usage else 0,
    )


# ---------------------------------------------------------------------------
# Provider dispatch
# ---------------------------------------------------------------------------


def call_llm(
    messages: list[dict],
    tool_schemas: list[dict],
    *,
    model: str | None = None,
) -> ProviderResponse:
    """Route a single LLM call through whichever provider is configured."""
    settings = get_settings()
    provider = settings.llm_provider.lower()

    if provider == "openai":
        return call_openai(messages, tool_schemas, model=model)

    raise ValueError(f"Unknown LLM provider: {provider!r}.  Set LLM_PROVIDER=openai in .env")
