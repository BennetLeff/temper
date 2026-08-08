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

.. note:: **Bug history (2026-07-27).** This module is a near-duplicate
   of `core/net_classification.py` (same patterns, same docstring claim
   of being "the" single source of truth -- itself an instance of the
   duplication this module's own docstring says it supersedes; that
   module's own bug-history note records the same defect). `_matches_any`
   used to test membership with plain substring containment (`p in
   upper`) rather than the word-boundary regex used here.
   `HV_NET_PATTERNS`'s bare 2-character `"PE"` is the sharpest example: as
   a plain substring it matches any net name that merely *contains* "PE"
   -- "SPEED", "TYPE", "OPEN", "EXPECT", "PERIPHERAL" -- none of which are
   remotely HV. This is the identical defect class already confirmed
   twice elsewhere in this repo (`creepage_check.py`, merge 5076e715;
   `clearance_check.py`, merge 466c7724) and fixed with the same
   technique: see `docs/evidence/2026-07-27-net-classification-gate.md`.
   `"PE"` itself currently matches nothing in this project's compiled
   netlist (the `pe` net was merged into `gnd` -- `elec/domain_manifest.yaml`),
   so this was a purely latent landmine for any future net name
   containing "PE", not a proven live false positive today -- fixed
   anyway, for the same defense-in-depth reason
   `clearance_engine._net_class_to_voltage_class` was fixed despite no
   live caller triggering it.

Wave 4 (PORT, ``docs/wave4-verdicts.yaml`` removal_surfaces entry for this
file, 157 LOC -- "keyword/regex lookup tables ... not numeric compute"):
``is_ground_net``/``is_power_net``/``is_hv_net``/``is_signal_net``/
``classify_net_type`` and the four ``is_*_pin`` helpers delegate to
``temper_io_types`` (``is_power_net_v6``/``is_signal_net_v6``/
``classify_net_type_v6`` plus the shared ``is_ground_net``/``is_hv_net``/
``is_*_pin`` bindings core/net_classification.py already uses -- ground/HV
net patterns and all four pin pattern sets are byte-identical between the
two Python modules, so the Rust side holds exactly one copy of each; only
power-net classification needs a router_v6-specific kernel, because
``POWER_NET_PATTERNS`` here carries four extra entries
(``"+340V"``/``"DC_BUS"``/``"PWR_RTN"``/``"V_BUS"``) and ``is_power_net``
adds a "starts with '+'" prefix heuristic core/net_classification.py does
not have). ``_SINGLE_LAYER_MODE``/``set_single_layer_mode``/
``get_single_layer_mode`` stay Python: process-local mutable session
state, not a numeric kernel, and ``test_quality_metrics_oracle_pin.py``
asserts on the module-global ``_SINGLE_LAYER_MODE`` directly.

R19: the pre-migration constants and ``_matches_any`` are retained,
unchanged and unused in production, as the in-repo statement of the
matching rule the Rust port reproduces -- pinned oracle for
``tests/router_v6/test_net_classification_rust_differential.py``.
"""

from __future__ import annotations

import re

import temper_io_types as _rs

# Net-name word-boundary patterns, delimited by "_" or start/end of the
# (uppercased) name. A net is "ground" if any of these matches, "power" if
# any power pattern matches, "hv" if any HV pattern matches. The precedence
# is: ground > power > hv > signal.
GROUND_NET_PATTERNS: frozenset[str] = frozenset({"GND", "PGND", "CGND", "AGND", "DGND", "VSS"})
POWER_NET_PATTERNS: frozenset[str] = frozenset(
    {"+3V3", "+5V", "+12V", "+15V", "VCC", "VDD", "VBUS",
     "+340V", "DC_BUS", "PWR_RTN", "V_BUS"}
)
HV_NET_PATTERNS: frozenset[str] = frozenset({"AC_L", "AC_N", "PE", "DC_BUS+", "DC_BUS-", "SW_NODE"})

# Pin-name patterns. Pin names are typically shorter and use different
# conventions (e.g., "VCC" for power pins, "GND" for ground pins) than
# net names (e.g., "+3V3" for power rails). The two pattern sets are
# intentionally distinct.
GROUND_PIN_PATTERNS: frozenset[str] = frozenset({"GND", "VSS", "AGND", "DGND", "PGND", "CGND"})
POWER_PIN_PATTERNS: frozenset[str] = frozenset({"VCC", "VDD", "VIN", "VOUT", "PVCC", "VBUS", "PWR"})
HV_PIN_PATTERNS: frozenset[str] = frozenset({"AC_L", "AC_N", "PE", "HV", "MAINS", "RECT"})
CLOCK_PIN_PATTERNS: frozenset[str] = frozenset(
    {"CLK", "CLOCK", "XTAL1", "XTAL2", "OSC_IN", "OSC_OUT"}
)


def _matches_any(name: str, patterns: frozenset[str]) -> bool:
    """Word-boundary pattern match, delimited by "_" or start/end of string.

    A pattern ending in a non-alphanumeric character (e.g. "DC_BUS+",
    "DC_BUS-") has no trailing boundary to anchor on and is matched with a
    leading anchor only -- mirrors the "B+" special case in
    ``creepage_check._is_high_voltage_net`` /
    ``clearance_check._is_hv_keyword_match``.

    Kept, unchanged and unused by any production predicate below, as the
    R19 pinned pre-migration oracle: the Rust port
    (``temper-io-types``'s ``placer_core::netclass``) reproduces exactly
    this matching rule, and the differential runs it against the Rust for
    every name it generates.
    """
    upper = name.upper()
    for p in patterns:
        escaped = re.escape(p)
        if p and not p[-1].isalnum():
            if re.search(rf"(?:^|_){escaped}", upper):
                return True
        elif re.search(rf"(?:^|_){escaped}(?:$|[\d_])", upper):
            return True
    return False


_SINGLE_LAYER_MODE: bool = False


def set_single_layer_mode(enabled: bool) -> None:
    """Enable or disable single-layer routing mode.

    In single-layer mode, all nets (including power, ground, and HV)
    are treated as signal nets so they get routed on a single layer.
    """
    global _SINGLE_LAYER_MODE
    _SINGLE_LAYER_MODE = enabled


def get_single_layer_mode() -> bool:
    """Return whether single-layer routing mode is enabled."""
    return _SINGLE_LAYER_MODE


def is_ground_net(name: str) -> bool:
    """Return True if `name` matches a ground-net pattern."""
    if _SINGLE_LAYER_MODE:
        return False
    return _rs.is_ground_net(name)


def is_power_net(name: str) -> bool:
    """Return True if `name` matches a power-net pattern."""
    if _SINGLE_LAYER_MODE:
        return False
    return _rs.is_power_net_v6(name)


def is_hv_net(name: str) -> bool:
    """Return True if `name` matches a high-voltage-net pattern."""
    if _SINGLE_LAYER_MODE:
        return False
    return _rs.is_hv_net(name)


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
    return _rs.is_ground_pin(pin_name)


def is_power_pin(pin_name: str) -> bool:
    return _rs.is_power_pin(pin_name)


def is_hv_pin(pin_name: str) -> bool:
    return _rs.is_hv_pin(pin_name)


def is_clock_pin(pin_name: str) -> bool:
    return _rs.is_clock_pin(pin_name)
