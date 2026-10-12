"""Tests for the Gemini message translation (app/agent/provider.py).

These test _build_gemini_contents directly, no live API calls, since that
function is a pure translation from our OpenAI-shape messages to Gemini's
Content/Part shape. Live API behavior (what roles it actually accepts, how
it replies) was verified by hand against the real API, see provider.py's
comments for what that caught.
"""

import json

from app.agent.provider import _build_gemini_contents


def test_system_message_becomes_system_instruction() -> None:
    system_instruction, contents = _build_gemini_contents([{"role": "system", "content": "You are Sentra."}])
    assert system_instruction == "You are Sentra."
    assert contents == []


def test_user_message_becomes_user_content() -> None:
    _, contents = _build_gemini_contents([{"role": "user", "content": "Investigate this."}])
    assert len(contents) == 1
    assert contents[0].role == "user"
    assert contents[0].parts[0].text == "Investigate this."


def test_assistant_tool_calls_become_model_function_call_parts() -> None:
    messages = [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "get_service_status", "arguments": json.dumps({"service": "checkout"})},
                }
            ],
        }
    ]
    _, contents = _build_gemini_contents(messages)
    assert len(contents) == 1
    assert contents[0].role == "model"
    part = contents[0].parts[0]
    assert part.function_call.name == "get_service_status"
    assert part.function_call.args == {"service": "checkout"}


def test_thought_signature_is_replayed_back_when_present() -> None:
    """gemini-2.5+/3.x "thinking" models reject a replayed function call
    that's missing its original thought_signature (confirmed live: a 400).
    When provider_metadata carries one, it must end up back on the Part."""
    messages = [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "get_service_status", "arguments": "{}"},
                    "provider_metadata": {"thought_signature": b"opaque-bytes"},
                }
            ],
        }
    ]
    _, contents = _build_gemini_contents(messages)
    assert contents[0].parts[0].thought_signature == b"opaque-bytes"


def test_missing_provider_metadata_still_works() -> None:
    """OpenAI-originated history (or just an older message) never sets
    provider_metadata, that must not blow up the Gemini translation."""
    messages = [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {"id": "call_1", "type": "function", "function": {"name": "get_service_status", "arguments": "{}"}}
            ],
        }
    ]
    _, contents = _build_gemini_contents(messages)
    assert contents[0].parts[0].function_call.name == "get_service_status"
    assert contents[0].parts[0].thought_signature is None


def test_assistant_plain_text_becomes_model_text_part() -> None:
    _, contents = _build_gemini_contents([{"role": "assistant", "content": "HYPOTHESIS:\n..."}])
    assert contents[0].role == "model"
    assert contents[0].parts[0].text == "HYPOTHESIS:\n..."


def test_tool_message_becomes_user_function_response_with_looked_up_name() -> None:
    """Gemini's API rejects role="tool" outright (confirmed live), function
    responses have to go back as a normal user turn."""
    messages = [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "get_service_status", "arguments": "{}"},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "call_1", "content": "TYPE: service_status\nSTATUS: healthy"},
    ]
    _, contents = _build_gemini_contents(messages)

    tool_result_content = contents[1]
    assert tool_result_content.role == "user"
    part = tool_result_content.parts[0]
    assert part.function_response.name == "get_service_status"
    assert part.function_response.response == {"result": "TYPE: service_status\nSTATUS: healthy"}


def test_multiple_tool_calls_in_one_turn_each_get_their_own_part() -> None:
    messages = [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {"id": "call_1", "type": "function", "function": {"name": "get_service_status", "arguments": "{}"}},
                {"id": "call_2", "type": "function", "function": {"name": "search_runbooks", "arguments": "{}"}},
            ],
        },
        {"role": "tool", "tool_call_id": "call_1", "content": "result 1"},
        {"role": "tool", "tool_call_id": "call_2", "content": "result 2"},
    ]
    _, contents = _build_gemini_contents(messages)

    assistant_content = contents[0]
    assert len(assistant_content.parts) == 2
    assert {p.function_call.name for p in assistant_content.parts} == {"get_service_status", "search_runbooks"}

    # Each tool message's function_response must resolve to the right name,
    # not just whichever call happened to be last.
    assert contents[1].parts[0].function_response.name == "get_service_status"
    assert contents[2].parts[0].function_response.name == "search_runbooks"


def test_full_conversation_round_trip_shape() -> None:
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "investigate"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {"id": "call_1", "type": "function", "function": {"name": "get_service_status", "arguments": "{}"}}
            ],
        },
        {"role": "tool", "tool_call_id": "call_1", "content": "healthy"},
        {"role": "assistant", "content": "HYPOTHESIS:\n...\nCONFIDENCE: low\nREASONING: ..."},
    ]
    system_instruction, contents = _build_gemini_contents(messages)

    assert system_instruction == "sys"
    assert [c.role for c in contents] == ["user", "model", "user", "model"]
