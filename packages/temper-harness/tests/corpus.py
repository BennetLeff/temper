"""Building a replay corpus out of the committed captures.

Shared by the oracle and fault suites so both check the same corpus. A second
builder would be a second answer to "what is in the corpus", and the two would
agree right up until one of them was edited.

Only *client-shaped* captures become corpus entries. ``orphan_tool_result`` cannot
be one: the client refuses to build that body at all (R7), so a replay could never
look it up, and its fixture is evidence about the provider rather than a corpus
entry. That is not a gap in the corpus; it is the corpus refusing to contain
something the client would never send.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from temper_harness.provider.deepseek import wire_body
from temper_harness.provider.interface import Request
from temper_harness.provider.messages import ChatMessage, ToolCall, ToolDefinition
from temper_harness.store import Mode, Recording, RecordingStore, scan_corpus

CAPTURED = Path(__file__).resolve().parent / "fixtures" / "captured"

MANIFEST: dict[str, Any] = json.loads((CAPTURED / "manifest.json").read_text(encoding="utf-8"))
ENTRIES: dict[str, dict[str, Any]] = {entry["name"]: entry for entry in MANIFEST["probes"]}

#: The probes whose request the client's own encoder can reproduce, and which are
#: therefore addressable by a replay lookup.
CORPUS_PROBES: tuple[str, ...] = tuple(
    sorted(name for name, entry in ENTRIES.items() if name != "orphan_tool_result")
)

ARM = "tier-a"
ATTEMPT = 0


def response_bytes(name: str) -> bytes:
    suffix = "sse" if ENTRIES[name]["stream"] else "json"
    return (CAPTURED / f"{name}.response.{suffix}").read_bytes()


def headers_of(name: str) -> dict[str, str]:
    meta = json.loads((CAPTURED / f"{name}.meta.json").read_text(encoding="utf-8"))
    return dict(meta["headers"])


def captured_body(name: str) -> dict[str, Any]:
    return json.loads((CAPTURED / f"{name}.request.json").read_text(encoding="utf-8"))


def captured_request(name: str, *, stream: bool | None = None) -> Request:
    """The captured request, carried in the client's own types.

    Built this way so ``wire_body`` reproduces the fixture byte for byte -- the
    property ``test_probe`` establishes, and the reason a replay lookup hits at all.
    A hand-assembled body would test the store against my copy of the request rather
    than against the one that was sent.
    """
    body = captured_body(name)
    messages = [
        ChatMessage(
            role=message["role"],
            content=message.get("content"),
            reasoning_content=message.get("reasoning_content"),
            tool_calls=tuple(
                ToolCall(
                    id=call["id"],
                    name=call["function"]["name"],
                    arguments=call["function"]["arguments"],
                )
                for call in message.get("tool_calls", ())
            ),
            tool_call_id=message.get("tool_call_id"),
        )
        for message in body["messages"]
    ]
    tools = tuple(
        ToolDefinition(
            name=tool["function"]["name"],
            description=tool["function"]["description"],
            parameters=tool["function"]["parameters"],
        )
        for tool in body.get("tools", ())
    )
    return Request(
        model=body["model"],
        messages=messages,
        tools=tools,
        temperature=body.get("temperature"),
        max_tokens=body.get("max_tokens"),
        served_from="replay",
        stream=bool(body.get("stream", False)) if stream is None else stream,
    )


def live_store(root: Path, *, arm: str = ARM, attempt: int = ATTEMPT) -> RecordingStore:
    return RecordingStore(root, mode=Mode.LIVE, arm=arm, attempt=attempt)


def replay_store(root: Path, *, arm: str = ARM, attempt: int = ATTEMPT) -> RecordingStore:
    return RecordingStore(root, mode=Mode.REPLAY, arm=arm, attempt=attempt)


def build_corpus(
    root: Path, *, arm: str = ARM, attempt: int = ATTEMPT, probes: tuple[str, ...] = CORPUS_PROBES
) -> list[Recording]:
    """Write every client-shaped capture into a fresh corpus, and return them.

    Returns the recordings rather than the root so a caller can perturb one and hand
    it back to the oracle without a second read from disk.
    """
    store = live_store(root, arm=arm, attempt=attempt)
    for name in probes:
        store.record(
            request=wire_body(captured_request(name)),
            response_raw=response_bytes(name),
            headers=headers_of(name),
            provider="deepseek",
            model="deepseek-flash",
            http_status=ENTRIES[name]["http_status"],
        )
    return scan_corpus(root)


def recording_named(recordings: list[Recording], name: str) -> Recording:
    """The recording made from one captured probe."""
    wanted = ENTRIES[name]["request_hash"]
    for recording in recordings:
        if recording.request_hash == wanted:
            return recording
    raise LookupError(f"no recording for probe {name!r} in this corpus")
