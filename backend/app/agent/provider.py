"""LLM provider abstraction layer.

The orchestrator talks only to this module, never directly to the openai
client.  Swapping providers means writing a new ProviderResponse-returning
function and pointing get_provider() at it — no agent logic changes.

Supported providers (LLM_PROVIDER env var):
  openai  — uses the OpenAI chat-completions API with native tool-calling
  gemini  — uses the Gemini API (google-genai) with native tool-calling
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from app.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class ToolCallRequest:
    """A single tool-call the model wants to make.

    provider_metadata is an opaque bag a provider can stash extra data in
    that it'll need back if this call gets replayed into a later request
    (e.g. Gemini's thought_signature). Providers that don't need this
    leave it None; the orchestrator never looks inside it, just carries it
    along in the message history.
    """

    id: str
    name: str
    arguments: dict[str, Any]
    provider_metadata: dict[str, Any] | None = None


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
# Gemini implementation
# ---------------------------------------------------------------------------
#
# Unlike OpenAI's flat message list, Gemini wants a `contents` list of
# Content(role, parts) plus a separate system_instruction. call_gemini gets
# the *entire* conversation so far as our own OpenAI-shape `messages` on
# every call (the orchestrator doesn't keep a Gemini-native history around),
# so _build_gemini_contents rebuilds the Gemini shape from scratch each time.


def _build_gemini_contents(messages: list[dict]) -> tuple[str | None, list[Any]]:
    from google.genai import types

    system_instruction: str | None = None
    contents: list[Any] = []
    # Gemini's function_response part needs the function's *name*, but our
    # "tool" messages only carry a tool_call_id. Track the mapping from the
    # preceding assistant turn so we can look the name back up.
    tool_call_id_to_name: dict[str, str] = {}

    for msg in messages:
        role = msg["role"]

        if role == "system":
            system_instruction = msg["content"]
        elif role == "user":
            contents.append(types.Content(role="user", parts=[types.Part.from_text(text=msg["content"])]))
        elif role == "assistant":
            if msg.get("tool_calls"):
                parts = []
                for tc in msg["tool_calls"]:
                    name = tc["function"]["name"]
                    args = json.loads(tc["function"]["arguments"])
                    tool_call_id_to_name[tc["id"]] = name
                    signature = (tc.get("provider_metadata") or {}).get("thought_signature")
                    if signature is not None:
                        # Gemini 2.5+/3.x "thinking" models require this
                        # exact opaque blob to be replayed back on a later
                        # turn (confirmed live: it 400s without it), which
                        # from_function_call doesn't have a slot for.
                        parts.append(
                            types.Part(
                                function_call=types.FunctionCall(name=name, args=args), thought_signature=signature
                            )
                        )
                    else:
                        parts.append(types.Part.from_function_call(name=name, args=args))
                contents.append(types.Content(role="model", parts=parts))
            else:
                contents.append(
                    types.Content(role="model", parts=[types.Part.from_text(text=msg.get("content") or "")])
                )
        elif role == "tool":
            # The Gemini API rejects role="tool" outright ("not supported,
            # use SYSTEM/USER/ASSISTANT/.../MODEL"), despite some SDK docs
            # showing it. Confirmed live: function responses go back as
            # role="user", same as a normal user turn.
            name = tool_call_id_to_name.get(msg["tool_call_id"], "unknown_tool")
            contents.append(
                types.Content(
                    role="user",
                    parts=[types.Part.from_function_response(name=name, response={"result": msg["content"]})],
                )
            )

    return system_instruction, contents


def call_gemini(
    messages: list[dict],
    tool_schemas: list[dict],
    *,
    model: str | None = None,
) -> ProviderResponse:
    """Call Gemini with tool-calling enabled."""
    from google import genai
    from google.genai import types

    settings = get_settings()
    client = genai.Client(api_key=settings.gemini_api_key)
    model = model or settings.gemini_model

    system_instruction, contents = _build_gemini_contents(messages)

    config_kwargs: dict[str, Any] = {}
    if system_instruction:
        config_kwargs["system_instruction"] = system_instruction
    if tool_schemas:
        declarations = [
            types.FunctionDeclaration(
                name=schema["name"],
                description=schema["description"],
                parameters_json_schema=schema["parameters"],
            )
            for schema in tool_schemas
        ]
        config_kwargs["tools"] = [types.Tool(function_declarations=declarations)]

    logger.debug("LLM request | model=%s messages=%d tools=%d", model, len(contents), len(tool_schemas))
    response = client.models.generate_content(
        model=model,
        contents=contents,
        config=types.GenerateContentConfig(**config_kwargs),
    )

    candidate = response.candidates[0] if response.candidates else None
    parts = candidate.content.parts if candidate and candidate.content and candidate.content.parts else []

    tool_calls: list[ToolCallRequest] = []
    text_chunks: list[str] = []
    for part in parts:
        if part.function_call is not None:
            provider_metadata = {"thought_signature": part.thought_signature} if part.thought_signature else None
            tool_calls.append(
                ToolCallRequest(
                    id=part.function_call.id or str(uuid.uuid4()),
                    name=part.function_call.name or "",
                    arguments=part.function_call.args or {},
                    provider_metadata=provider_metadata,
                )
            )
        elif part.text:
            text_chunks.append(part.text)

    usage = response.usage_metadata
    return ProviderResponse(
        content="\n".join(text_chunks) if text_chunks else None,
        tool_calls=tool_calls,
        finish_reason=str(candidate.finish_reason) if candidate and candidate.finish_reason else "stop",
        prompt_tokens=usage.prompt_token_count if usage and usage.prompt_token_count else 0,
        completion_tokens=usage.candidates_token_count if usage and usage.candidates_token_count else 0,
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
    if provider == "gemini":
        return call_gemini(messages, tool_schemas, model=model)

    raise ValueError(f"Unknown LLM provider: {provider!r}.  Set LLM_PROVIDER=openai or gemini in .env")
