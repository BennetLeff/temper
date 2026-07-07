"""Netclass clearance rules — single source of truth (SSOT).

Loads ``netclass_rules.yaml`` and provides canonical accessors for per-pair
clearance values, ``because`` rationale strings, and net-class resolution.
"""

from __future__ import annotations

from pathlib import Path
from typing import TypedDict

import yaml

from temper_placer.core.design_rules import NetClassRules, TEMPER_NET_ASSIGNMENTS
from temper_placer.core.net_classification import classify_net_type


class NetClassRulesDict(TypedDict):
    """Container for the netclass rules loaded from YAML."""

    net_classes: dict[str, NetClassRules]
    pair_clearances: dict[tuple[str, str], float]
    default_clearance_mm: float
    because: dict[tuple[str, str], str]


def _canonical_key(class_a: str, class_b: str) -> tuple[str, str]:
    """Return direction-agnostic sorted tuple for pair lookups."""
    return tuple(sorted([class_a, class_b]))


def load_netclass_rules(path: Path) -> NetClassRulesDict:
    """Load and validate netclass rules from a YAML file.

    Returns a ``NetClassRulesDict`` with Pydantic-validated net class
    definitions, direction-agnostic pair clearances, and the default
    clearance fallback.
    """
    with open(path) as f:
        data = yaml.safe_load(f)

    net_classes: dict[str, NetClassRules] = {}
    for nc_data in data["net_classes"]:
        nc = NetClassRules(**nc_data)
        net_classes[nc.name] = nc

    pair_clearances: dict[tuple[str, str], float] = {}
    because: dict[tuple[str, str], str] = {}
    for cc in data["cross_class_clearances"]:
        key = _canonical_key(cc["class_a"], cc["class_b"])
        pair_clearances[key] = cc["clearance_mm"]
        if cc.get("because"):
            because[key] = cc["because"]

    default_clearance_mm: float = data["default_clearance_mm"]

    return NetClassRulesDict(
        net_classes=net_classes,
        pair_clearances=pair_clearances,
        default_clearance_mm=default_clearance_mm,
        because=because,
    )


def get_pair_clearance(
    class_a: str, class_b: str, *, rules: NetClassRulesDict
) -> float:
    """Return the clearance (mm) for a pair of net classes.

    1. Explicit entry in ``rules.pair_clearances`` (canonicalized).
    2. ``max(self-clearance-of-a, self-clearance-of-b)`` when both
       classes exist in ``rules.net_classes``.
    3. ``rules.default_clearance_mm`` as universal fallback.
    """
    key = _canonical_key(class_a, class_b)

    if key in rules["pair_clearances"]:
        return rules["pair_clearances"][key]

    if class_a in rules["net_classes"] and class_b in rules["net_classes"]:
        return max(
            rules["net_classes"][class_a].clearance,
            rules["net_classes"][class_b].clearance,
        )

    return rules["default_clearance_mm"]


def get_pair_because(
    class_a: str, class_b: str, *, rules: NetClassRulesDict
) -> str | None:
    """Return the rationale string for an explicit pair, or *None*."""
    key = _canonical_key(class_a, class_b)
    return rules["because"].get(key)


# ---------------------------------------------------------------------------
# Net-class resolution helpers
# ---------------------------------------------------------------------------

_NET_TYPE_TO_CLASS: dict[str, str] = {
    "ground": "GND",
    "power": "Power",
    "hv": "HighVoltage",
    "signal": "Signal",
}


def resolve_net_class(net_name: str) -> str:
    """Map a net name to its canonical net class.

    Precedence:
    1. ``TEMPER_NET_ASSIGNMENTS`` (explicit KiCad project assignments).
    2. Heuristic fallback via ``classify_net_type()`` — maps ``"ground"``
       → ``"GND"``, ``"power"`` → ``"Power"``, ``"hv"`` → ``"HighVoltage"``,
       ``"signal"`` → ``"Signal"``.
    """
    if net_name in TEMPER_NET_ASSIGNMENTS:
        return TEMPER_NET_ASSIGNMENTS[net_name]
    net_type = classify_net_type(net_name)
    return _NET_TYPE_TO_CLASS.get(net_type, "Signal")


# ---------------------------------------------------------------------------
# Shared utilities for downstream consumers
# ---------------------------------------------------------------------------

def get_default_rules_path() -> Path:
    """Return the default path to ``netclass_rules.yaml`` relative to this
    package's config directory."""
    return Path(__file__).resolve().parent.parent.parent / "configs" / "netclass_rules.yaml"


def format_netclass_sexpr_lines(rules: NetClassRulesDict) -> list[str]:
    """Return KiCad ``(net_class ...)`` s-expression lines for each net class
    in *rules*, sorted by class name.

    Usable both by the output-PCB writer and by ``_build_minimal_pcb``.
    """
    lines: list[str] = []
    for nc in sorted(rules["net_classes"].values(), key=lambda nc: nc.name):
        lines.append(
            f"  (net_class \"{nc.name}\""
            f" (clearance {nc.clearance})"
            f" (trace_width {nc.trace_width})"
            f" (via_dia {nc.via_diameter})"
            f" (via_drill {nc.via_drill}))"
        )
    return lines
