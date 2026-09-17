"""Message-array construction and validation (R7).

Two invariants that only matter once a loop is involved, and that cost a
provider round-trip each to discover if they are not checked locally:

1. every ``role="tool"`` message answers an ``assistant.tool_calls[].id``, and
   every pending call is answered before the conversation moves on;
2. tool definitions pass through byte-unchanged, including JSON Schema keywords
   the client does not itself interpret.

Under parallel tool calls and subagent fan-out a malformed array otherwise
surfaces as a provider 400, which a classifier is liable to read as a model
failure. :func:`validate_messages` raises before any network I/O instead.
"""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

ROLES = ("system", "user", "assistant", "tool")


class MessageArrayError(ValueError):
    """A locally-detectable defect in the message array.

    Deliberately not a ``TransportError``: nothing was sent, so this is a caller
    bug rather than a transport outcome, and it must not appear in the failure
    taxonomy the ledger classifies against.
    """


@dataclass(frozen=True, slots=True)
class ToolCall:
    """One tool call. ``arguments`` stays the provider's raw string."""

    id: str
    name: str
    arguments: str
    index: int = 0


@dataclass(frozen=True, slots=True)
class ChatMessage:
    """One message. ``tool_call_id`` is set exactly when ``role == "tool"``."""

    role: str
    content: str | None = None
    tool_calls: tuple[ToolCall, ...] = field(default=())
    tool_call_id: str | None = None
    reasoning_content: str | None = None

    def to_wire(self) -> dict[str, Any]:
        """The provider-facing form of this message.

        ``reasoning_content`` is emitted when present, and that is a measured
        requirement rather than a nicety. This provider runs in a thinking mode
        and refuses an assistant tool-call turn that omits it:

            {"error": {"message": "The `reasoning_content` in the thinking mode
             must be passed back to the API."}}

        Worse, the refusal is conditional on server-side state. Measured 5/5
        against ids the provider had just generated -- accepted without the field
        -- and 5/5 against ids it had not seen, same body otherwise: refused. A
        client cannot inspect that state, so the only implementable rule is to
        always send the field back. Dropping it here produced a transport that
        worked in a quick test and would have failed later, which is the failure
        shape this repo calls correct by coincidence.
        """
        wire: dict[str, Any] = {"role": self.role}
        if self.content is not None:
            wire["content"] = self.content
        if self.reasoning_content is not None:
            wire["reasoning_content"] = self.reasoning_content
        if self.tool_calls:
            wire["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {"name": call.name, "arguments": call.arguments},
                }
                for call in self.tool_calls
            ]
        if self.tool_call_id is not None:
            wire["tool_call_id"] = self.tool_call_id
        return wire


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    """A tool definition passed through unchanged.

    ``parameters`` is deep-copied on construction and returned deep-copied on
    read, so a caller mutating its own schema dict cannot retroactively change
    what was sent — and unknown keywords such as ``$defs``, ``oneOf``, and
    ``additionalProperties`` survive rather than being filtered to a known set.
    """

    name: str
    description: str
    parameters: dict[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "parameters", copy.deepcopy(self.parameters))

    def to_wire(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": copy.deepcopy(self.parameters),
            },
        }

    def digest(self) -> str:
        """Stable digest of the schema as sent, for the fidelity oracle."""
        canonical = json.dumps(self.to_wire(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()


def validate_messages(messages: list[ChatMessage]) -> None:
    """Raise :class:`MessageArrayError` on a malformed array. Sends nothing."""
    if not messages:
        raise MessageArrayError("message array is empty")

    seen_call_ids: set[str] = set()
    pending: list[str] = []

    for position, message in enumerate(messages):
        if message.role not in ROLES:
            raise MessageArrayError(f"message {position}: unknown role {message.role!r}")

        if message.role == "tool":
            if message.tool_call_id is None:
                raise MessageArrayError(f"message {position}: role 'tool' requires a tool_call_id")
            if message.tool_calls:
                raise MessageArrayError(
                    f"message {position}: role 'tool' must not carry tool_calls"
                )
            if message.tool_call_id not in pending:
                raise MessageArrayError(
                    f"message {position}: tool_call_id {message.tool_call_id!r} matches no "
                    "pending assistant tool call"
                )
            pending.remove(message.tool_call_id)
            continue

        if pending:
            raise MessageArrayError(
                f"message {position}: role {message.role!r} arrived with tool call(s) "
                f"{pending!r} still unanswered"
            )

        if message.tool_call_id is not None:
            raise MessageArrayError(
                f"message {position}: role {message.role!r} must not carry a tool_call_id"
            )

        if message.role in ("system", "user") and message.content is None:
            raise MessageArrayError(f"message {position}: role {message.role!r} requires content")

        for call in message.tool_calls:
            if not call.id:
                raise MessageArrayError(f"message {position}: tool call with empty id")
            if call.id in seen_call_ids:
                raise MessageArrayError(f"message {position}: duplicate tool call id {call.id!r}")
            seen_call_ids.add(call.id)
            pending.append(call.id)

    if pending:
        raise MessageArrayError(f"message array ends with unanswered tool call(s) {pending!r}")


def build_wire_request(
    *,
    model: str,
    messages: list[ChatMessage],
    tools: list[ToolDefinition] | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> dict[str, Any]:
    """Assemble the request body, validating before anything is sent."""
    validate_messages(messages)
    body: dict[str, Any] = {
        "model": model,
        "messages": [message.to_wire() for message in messages],
    }
    if tools:
        body["tools"] = [tool.to_wire() for tool in tools]
    if temperature is not None:
        body["temperature"] = temperature
    if max_tokens is not None:
        # Present because a harness that cannot bound a completion cannot bound what
        # it spends, and the fixed-expenditure comparison S7 depends on is denominated
        # in exactly that bound.
        body["max_tokens"] = max_tokens
    return body
