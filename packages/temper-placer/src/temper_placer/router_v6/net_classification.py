"""
Canonical net classification for the placer.

This module is the single source of truth for "is this net a power net,
ground net, HV net, or signal net?" — and the analogous pin-name
classification. It supersedes the 20+ duplicate lists that previously
appeared in `core/`, `routing/`, `router_v6/`, `heuristics/`, `losses/`,
`io/`, `experiments/`, `deterministic/`, and `placement/`.

The patterns here are taken verbatim from `core/net_types.py:284-288`
(the most curated set in the codebase, used by
`NetClassSpec.classify_net`). New code should use these helpers
rather than defining local keyword lists.
"""

from __future__ import annotations

# Net-name substring patterns. Matched case-insensitively against
# `name.upper()`. A net is "ground" if any of these is a substring,
# "power" if any power pattern matches, "hv" if any HV pattern matches.
# The precedence is: ground > power > hv > signal.
GROUND_NET_PATTERNS: frozenset[str] = frozenset(
    {"GND", "PGND", "CGND", "AGND", "DGND", "VSS"}
)
POWER_NET_PATTERNS: frozenset[str] = frozenset(
    {"+3V3", "+5V", "+12V", "+15V", "VCC", "VDD", "VBUS"}
)
HV_NET_PATTERNS: frozenset[str] = frozenset(
    {"AC_L", "AC_N", "PE", "DC_BUS+", "DC_BUS-", "SW_NODE"}
)

# Pin-name patterns. Pin names are typically shorter and use different
# conventions (e.g., "VCC" for power pins, "GND" for ground pins) than
# net names (e.g., "+3V3" for power rails). The two pattern sets are
# intentionally distinct.
GROUND_PIN_PATTERNS: frozenset[str] = frozenset(
    {"GND", "VSS", "AGND", "DGND", "PGND", "CGND"}
)
POWER_PIN_PATTERNS: frozenset[str] = frozenset(
    {"VCC", "VDD", "VIN", "VOUT", "PVCC", "VBUS", "PWR"}
)
HV_PIN_PATTERNS: frozenset[str] = frozenset(
    {"AC_L", "AC_N", "PE", "HV", "MAINS", "RECT"}
)
CLOCK_PIN_PATTERNS: frozenset[str] = frozenset(
    {"CLK", "CLOCK", "XTAL1", "XTAL2", "OSC_IN", "OSC_OUT"}
)


def _matches_any(name: str, patterns: frozenset[str]) -> bool:
    upper = name.upper()
    return any(p in upper for p in patterns)


def is_ground_net(name: str) -> bool:
    """Return True if `name` matches a ground-net pattern."""
    return _matches_any(name, GROUND_NET_PATTERNS)


def is_power_net(name: str) -> bool:
    """Return True if `name` matches a power-net pattern."""
    return _matches_any(name, POWER_NET_PATTERNS)


def is_hv_net(name: str) -> bool:
    """Return True if `name` matches a high-voltage-net pattern."""
    return _matches_any(name, HV_NET_PATTERNS)


def is_signal_net(name: str) -> bool:
    """Return True if `name` is none of ground, power, or HV."""
    return not (is_ground_net(name) or is_power_net(name) or is_hv_net(name))


def classify_net_type(name: str) -> str:
    """Return one of 'ground', 'power', 'hv', or 'signal'.

    Precedence: ground > power > hv > signal. Matches
    `NetClassSpec.classify_net` in `core/net_types.py`.
    """
    if is_ground_net(name):
        return "ground"
    if is_power_net(name):
        return "power"
    if is_hv_net(name):
        return "hv"
    return "signal"


def is_ground_pin(pin_name: str) -> bool:
    return _matches_any(pin_name, GROUND_PIN_PATTERNS)


def is_power_pin(pin_name: str) -> bool:
    return _matches_any(pin_name, POWER_PIN_PATTERNS)


def is_hv_pin(pin_name: str) -> bool:
    return _matches_any(pin_name, HV_PIN_PATTERNS)


def is_clock_pin(pin_name: str) -> bool:
    return _matches_any(pin_name, CLOCK_PIN_PATTERNS)
