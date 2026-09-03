"""Frozen pre-port Python oracle for DRC semantic identity.

Test-only by design. Production callers use ``temper_drc_rs``; this pin keeps
the removed Python behavior available only for differential migration proof.
"""

from __future__ import annotations

import re

_NET = re.compile(r"\[([^\]]+)\]")
_COMPONENT = re.compile(r"\bof (\S+?)(?:\s+on\s+\S.*)?$")
_NET_PAIR = re.compile(r"\(nets (.+) and (.+)\)$")


def _normalize_net_pair(description: str) -> str:
    match = _NET_PAIR.search(description)
    if match is None:
        return description
    first, second = sorted(match.groups())
    return f"{description[:match.start()]}(nets {first} and {second})"


def _split_actual_distance(description: str) -> tuple[str, str | None]:
    marker = "; actual "
    start = description.rfind(marker)
    if start < 0:
        if "actual " in description:
            raise ValueError("malformed actual distance")
        return _normalize_net_pair(description), None
    suffix = description[start + len(marker) :]
    if not suffix.endswith(" mm)"):
        raise ValueError("malformed actual distance")
    value = suffix[: -len(" mm)")]
    float(value)
    return _normalize_net_pair(f"{description[:start]})"), value


def identities(finding: dict) -> tuple[dict, dict, dict]:
    message, actual = _split_actual_distance(finding["description"])
    items = sorted(
        (
            {
            "description": item["description"],
            "x": str(item["pos"]["x"]),
            "y": str(item["pos"]["y"]),
            }
            for item in finding["items"]
        ),
        key=lambda item: (item["description"], item["x"], item["y"]),
    )
    nets = sorted(
        value
        for item in finding["items"]
        for value in _NET.findall(item["description"])
    )
    components = sorted(
        match.group(1)
        for item in finding["items"]
        if (match := _COMPONENT.search(item["description"])) is not None
    )
    family = {
        "category": finding["type"],
        "message_semantics": message,
        "nets": nets,
        "components": components,
        "items": []
        if finding["type"].removeprefix("W:") in {"creepage", "unconnected_items"}
        else items,
    }
    observation = {"family": family, "actual_distance_mm": actual}
    raw = {
        "category": finding["type"],
        "description": _normalize_net_pair(finding["description"]),
        "items": items,
    }
    return family, observation, raw
