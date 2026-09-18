"""Redacted shape summaries, so a live run can be compared without its content.

The canary's job is to answer one question: does the provider still *behave* the way
the recorded corpus says it does? Answering it must not require committing what the
provider said. So a response is reduced to structural facts -- key names, nesting,
counts, closed-vocabulary enums, and presence booleans -- and never a value from
free text.

Two constraints pull against each other, and both matter:

* **Structural enough to be worth comparing.** A missing ``system_fingerprint``, a
  renamed usage field, usage moving off the final stream chunk, or a 400 becoming a
  200 are all shape changes, and all of them would break this client.
* **Insensitive enough to survive a stochastic model.** The canary re-issues the same
  prompts, so the *content* differs every run. Anything that varies with output
  length or wording -- an event count, whether a particular turn happened to emit
  visible content -- would make the canary fail for a reason that is not a shape
  change. Those facts are deliberately absent, which is why this module records
  ``content_present`` and not ``content_is_empty``.

The byte count and digest are recorded for provenance and excluded from comparison,
because they can never match across two runs of a sampled model.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from temper_harness.provider.deepseek import is_event_stream

#: Facts that describe *this* response rather than the provider's behaviour. Recorded
#: for provenance, never compared.
VOLATILE_SHAPE_KEYS = frozenset({"response_sha256", "response_bytes"})


def _sorted_keys(value: Any) -> list[str]:
    return sorted(value) if isinstance(value, Mapping) else []


def _nested_keys(section: Any) -> dict[str, list[str]]:
    if not isinstance(section, Mapping):
        return {}
    return {key: _sorted_keys(item) for key, item in section.items() if isinstance(item, Mapping)}


def _completion_shape(status: int, raw: bytes) -> dict[str, Any]:
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {"kind": "unparseable", "http_status": status}

    if isinstance(payload, Mapping) and "error" in payload:
        error = payload.get("error")
        return {
            "kind": "error_body",
            "http_status": status,
            "error_keys": _sorted_keys(error),
            "error_type": error.get("type") if isinstance(error, Mapping) else None,
            "error_code": error.get("code") if isinstance(error, Mapping) else None,
        }
    if not isinstance(payload, Mapping):
        return {"kind": "not_an_object", "http_status": status}

    choices = payload.get("choices")
    choice = choices[0] if isinstance(choices, list) and choices else {}
    message = choice.get("message") if isinstance(choice, Mapping) else {}
    usage = payload.get("usage")
    message = message if isinstance(message, Mapping) else {}

    return {
        "kind": "completion",
        "http_status": status,
        "top_level_keys": _sorted_keys(payload),
        "choice_keys": _sorted_keys(choice),
        "message_keys": _sorted_keys(message),
        "usage_keys": _sorted_keys(usage),
        "usage_nested_keys": _nested_keys(usage),
        "finish_reasons": [
            item.get("finish_reason") for item in choices if isinstance(item, Mapping)
        ]
        if isinstance(choices, list)
        else [],
        "tool_calls_present": bool(message.get("tool_calls")),
        "tool_call_keys": _sorted_keys((message.get("tool_calls") or [{}])[0]),
        "tool_call_function_keys": _sorted_keys(
            ((message.get("tool_calls") or [{}])[0].get("function") or {})
            if isinstance((message.get("tool_calls") or [{}])[0], Mapping)
            else {}
        ),
        "content_present": "content" in message,
        "reasoning_present": "reasoning_content" in message,
        "system_fingerprint_present": "system_fingerprint" in payload,
        "usage_total_reconciles": _usage_reconciles(usage),
    }


def _as_int(value: Any) -> int | None:
    """An int, or ``None``. ``bool`` excluded: ``True`` is an ``int`` in Python."""
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return int(value)


def _usage_reconciles(usage: Any) -> bool | None:
    if not isinstance(usage, Mapping):
        return None
    prompt = _as_int(usage.get("prompt_tokens"))
    completion = _as_int(usage.get("completion_tokens"))
    total = _as_int(usage.get("total_tokens"))
    if prompt is None or completion is None or total is None:
        return None
    return total == prompt + completion


def _stream_shape(status: int, raw: bytes) -> dict[str, Any]:
    payloads: list[Mapping[str, Any]] = []
    for line in raw.split(b"\n"):
        if not line.startswith(b"data: "):
            continue
        body = line[len(b"data: ") :]
        if body.strip() == b"[DONE]":
            continue
        try:
            chunk = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {"kind": "unparseable_stream", "http_status": status}
        if isinstance(chunk, Mapping):
            payloads.append(chunk)

    if not payloads:
        return {"kind": "empty_stream", "http_status": status, "sentinel_present": False}

    delta_key_shapes = sorted(
        {
            tuple(sorted(cast))
            for payload in payloads
            for cast in [_first_delta(payload)]
            if cast is not None
        }
    )
    carrying_usage = [index for index, payload in enumerate(payloads) if "usage" in payload]
    with_finish = [
        index for index, payload in enumerate(payloads) if _first_finish_reason(payload) is not None
    ]
    fragment_keys = sorted(
        {
            tuple(sorted(fragment))
            for payload in payloads
            for fragment in (_first_delta(payload) or {}).get("tool_calls") or ()
            if isinstance(fragment, Mapping)
        }
    )

    return {
        "kind": "stream",
        "http_status": status,
        "sentinel_present": b"data: [DONE]" in raw,
        "chunk_top_level_keys": _sorted_keys(payloads[0]),
        "choice_keys": _sorted_keys(_first_choice(payloads[0])),
        "delta_key_shapes": [list(shape) for shape in delta_key_shapes],
        "usage_event_count": len(carrying_usage),
        "usage_on_final_event": carrying_usage == [len(payloads) - 1],
        "finish_reason_on_final_event": with_finish == [len(payloads) - 1],
        "finish_reasons": sorted(
            {
                reason
                for payload in payloads
                for reason in [_first_finish_reason(payload)]
                if reason is not None
            }
        ),
        "tool_call_fragment_keys": [list(shape) for shape in fragment_keys],
        "usage_total_reconciles": _usage_reconciles(
            payloads[-1].get("usage") if "usage" in payloads[-1] else None
        ),
    }


def _first_choice(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    choices = payload.get("choices")
    if isinstance(choices, list) and choices and isinstance(choices[0], Mapping):
        return choices[0]
    return {}


def _first_delta(payload: Mapping[str, Any]) -> Mapping[str, Any] | None:
    delta = _first_choice(payload).get("delta")
    return delta if isinstance(delta, Mapping) else None


def _first_finish_reason(payload: Mapping[str, Any]) -> Any:
    return _first_choice(payload).get("finish_reason")


def shape_of_exchange(*, http_status: int, raw: bytes, content_type: str | None) -> dict[str, Any]:
    """The structural summary of one exchange. Contains no free text."""
    if is_event_stream(content_type):
        shape = _stream_shape(http_status, raw)
    else:
        shape = _completion_shape(http_status, raw)
    shape["response_bytes"] = len(raw)
    shape["response_sha256"] = hashlib.sha256(raw).hexdigest()
    return shape


def shape_digest(shape: Mapping[str, Any]) -> str:
    """A digest of the *behavioural* part of a shape, volatile facts excluded."""
    stable = {key: value for key, value in shape.items() if key not in VOLATILE_SHAPE_KEYS}
    return hashlib.sha256(
        json.dumps(stable, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def compare_shapes(recorded: Mapping[str, Any], live: Mapping[str, Any]) -> list[str]:
    """The differences between two shapes. Empty means the provider's behaviour held.

    Every recorded key is compared, exact lists included, so an *addition* is reported
    as well as a removal or a change. That asymmetry was considered and rejected: the
    fields a provider is most likely to add are the ones that matter here -- a cost
    field, a new usage breakdown -- and a canary that shrugged at those would be silent
    about a change to what a call costs to compute. Reported, and a human decides.
    """
    differences: list[str] = []
    # The union, not just the recorded keys: a wholly new shape key is a change the
    # client should hear about, and iterating `recorded` alone would silently ignore
    # one. The earlier claim that this was "forward-compatible on purpose" was wrong in
    # both directions -- it reported additions *inside* a compared list while missing a
    # new top-level key -- so the honest version reports every structural difference and
    # a human decides whether it matters.
    for key in sorted(set(recorded) | set(live)):
        if key in VOLATILE_SHAPE_KEYS:
            continue
        expected = recorded.get(key)
        actual = live.get(key)
        if actual != expected:
            differences.append(f"{key}: recorded {expected!r}, live {actual!r}")
    return differences
