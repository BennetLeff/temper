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
import re
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


#: The `user_id` shape the provider documents: `[a-zA-Z0-9\-_]+`, at most 512 characters.
#:
#: Matched with `fullmatch` rather than `^...$`: `$` also matches immediately *before* a
#: trailing newline, so `"abc\n"` passed an anchored search -- a value the provider's own
#: shape forbids, sent to the wire after local validation said it was fine.
USER_ID_PATTERN = re.compile(r"[a-zA-Z0-9\-_]+")
USER_ID_MAX_LENGTH = 512

#: The effort values the provider documents as *requestable*, and what each maps to.
#: Transcribed from https://api-docs.deepseek.com/guides/thinking_mode (retrieved
#: 2026-09-17), because a caller asking for `medium` and getting `high` should be able to
#: find that out from the client rather than from a latency graph.
REASONING_EFFORT_MAP = {
    "minimal": "low",
    "low": "low",
    "medium": "high",
    "high": "high",
    "xhigh": "high",
    "max": "max",
    "ultra": "max",
}


class RequestParameterError(ValueError):
    """A request parameter the provider would reject, caught before the network.

    Deliberately a ``ValueError`` and not a ``TransportError``: nothing was sent, so this
    is a caller defect rather than a transport outcome, and it must not enter the failure
    taxonomy the ledger classifies against.
    """


def validate_user_id(user_id: str) -> str:
    """Check a `user_id` against the provider's documented shape.

    Worth checking locally because `user_id` is not cosmetic: the provider documents it as
    the isolation control for KVCache, content safety, and scheduling. A malformed one is
    rejected by the provider -- and a *missing* one means two experiment arms share a cache,
    which would silently halve one arm's input cost at cache-hit rates and invalidate a
    fixed-expenditure comparison. Recorded in the plan as an arm-isolation requirement.
    """
    if not user_id or not USER_ID_PATTERN.fullmatch(user_id):
        raise RequestParameterError(
            f"user_id must match {USER_ID_PATTERN.pattern!r}, got {user_id!r}"
        )
    if len(user_id) > USER_ID_MAX_LENGTH:
        raise RequestParameterError(
            f"user_id must be at most {USER_ID_MAX_LENGTH} characters, got {len(user_id)}"
        )
    return user_id


def validate_reasoning_effort(effort: str) -> str:
    if effort not in REASONING_EFFORT_MAP:
        raise RequestParameterError(
            f"reasoning_effort must be one of {sorted(REASONING_EFFORT_MAP)}, got {effort!r}"
        )
    return effort


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
    user_id: str | None = None,
    thinking: bool | None = None,
    reasoning_effort: str | None = None,
) -> dict[str, Any]:
    """Assemble the request body, validating before anything is sent.

    Three of these deserve a warning rather than just a type.

    ``temperature`` is **accepted and silently ignored**, because the provider enables
    thinking mode by default and documents that thinking mode does not support
    `temperature`, `presence_penalty`, or `frequency_penalty`: setting them "will not
    trigger an error but will also have no effect". A caller therefore cannot buy
    determinism with `temperature=0` on this model by default, and nothing in the response
    says so -- which is why it is written here. It takes effect when ``thinking`` is
    explicitly disabled.

    ``user_id`` is not cosmetic. The provider documents it as the isolation control for
    KVCache, content safety, and scheduling. A cache shared between two experiment arms
    would halve one arm's input cost at cache-hit rates -- enough to corrupt a
    fixed-expenditure comparison without an error appearing anywhere.

    ``thinking=False`` is the only way to make ``temperature`` effective, and the cheapest
    way to cut output tokens, because reasoning is billed as output.
    """
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
    if user_id is not None:
        body["user_id"] = validate_user_id(user_id)
    if thinking is not None:
        body["thinking"] = {"type": "enabled" if thinking else "disabled"}
    if reasoning_effort is not None:
        body["reasoning_effort"] = validate_reasoning_effort(reasoning_effort)
    return body
