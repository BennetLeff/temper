"""Differential: ``router_v6/constraints_design_rules.ClearanceMatrix`` /
``ZoneManager`` hot-path clearance kernels vs the pinned oracle.

Arms
----
* **oracle** -- ``tests/router_v6/_constraints_design_rules_py_oracle.py``, a
  verbatim copy of the module as of ``4884d284c`` (origin/main).
* **shim** -- the shipped ``temper_placer.router_v6.constraints_design_rules``,
  whose ``ClearanceMatrix``/``ZoneManager`` methods now delegate to
  ``temper_drc_rs``'s ``clearance_matrix.rs`` kernels.

Both arms define their OWN ``ClearanceMatrix``/``ZoneManager``/``RoutingZone``
dataclasses (the oracle's is a pinned, non-delegating copy); comparisons
build one instance of each with identical field values and compare method
return values via ``tests.router_v6._signature.sig`` -- type-carrying,
``float.hex()``-exact, no tolerance.

Ported (see the oracle module docstring for the Wave-4 triage rationale):
``ClearanceMatrix.get_clearance``, ``_get_base_clearance``,
``get_track_width``, ``get_via_diameter``, ``get_via_drill``,
``is_differential_pair``, ``add_differential_pair``'s clearance arithmetic,
and ``ZoneManager.get_zone_at``.

NOT ported (dead code / GEOS boundary / one-shot glue -- see the oracle
docstring): ``ZoneManager.get_clearance``, ``ZoneManager.can_route_net_at``,
``ClearanceMatrix.can_route_at``, ``infer_zones``, ``DesignRulesParser.*``,
``ClearanceMatrix.parse``.

Traps this file pins explicitly
--------------------------------
CPython's two-argument ``max(a, b)`` keeps the FIRST argument unless the
second compares strictly greater -- a NaN operand on either side never wins
that comparison, so ``max`` silently keeps whichever operand it saw first.
``f64::max`` has IEEE-754-minimum-propagating (NaN-discarding) semantics
instead. Both ``_get_base_clearance``'s class-clearance fallback and
``get_clearance``'s zone-override ``max`` are exercised here with a NaN
class clearance to prove the Rust kernel does NOT use ``f64::max``
(:func:`test_get_base_clearance_max_keeps_nan_not_f64_max`,
:func:`test_get_clearance_zone_override_max_keeps_nan_not_f64_max`).
"""

from __future__ import annotations

import math

import pytest

import tests.router_v6._constraints_design_rules_py_oracle as ORACLE
from temper_placer.core.netclass_rules_gen import NetClassRules
from temper_placer.router_v6 import constraints_design_rules as SHIM
from tests.router_v6._signature import sig

pytest.importorskip("temper_drc_rs")
import temper_drc_rs as _temper_drc_rs  # noqa: E402  isort: skip

REQUIRED_RUST_SYMBOLS = (
    "clearance_get_base_clearance_py",
    "clearance_class_attr_py",
    "clearance_is_differential_pair_py",
    "clearance_diff_pair_required_py",
    "clearance_get_clearance_py",
    "clearance_zone_at_py",
)


def test_required_rust_symbols_present():
    """Fails collection loudly if the extension is stale, not a silent skip."""
    missing = [s for s in REQUIRED_RUST_SYMBOLS if not hasattr(_temper_drc_rs, s)]
    assert not missing, f"temper_drc_rs missing symbols: {missing} -- rebuild with maturin develop"


# ---------------------------------------------------------------------------
# Shared fixture data
# ---------------------------------------------------------------------------

_RULES = {
    "Signal": NetClassRules(name="Signal", trace_width=0.15, clearance=0.2, via_diameter=0.5, via_drill=0.25),
    "Power": NetClassRules(name="Power", trace_width=0.3, clearance=0.5, via_diameter=0.8, via_drill=0.4),
    "GND": NetClassRules(name="GND", trace_width=0.25, clearance=0.3, via_diameter=0.6, via_drill=0.3),
    "HighVoltage": NetClassRules(
        name="HighVoltage", trace_width=0.5, clearance=3.0, via_diameter=1.2, via_drill=0.6
    ),
}

_NET_TO_CLASS = {
    "VCC_3V3": "Power",
    "GND_1": "GND",
    "SIG_A": "Signal",
    "SIG_B": "Signal",
    "MAINS_L": "HighVoltage",
    "USB_D+": "Signal",
    "USB_D-": "Signal",
}

_CLEARANCES = {
    ("Power", "Power"): 0.5,
    ("Power", "Signal"): 0.3,
    ("GND", "Power"): 0.3,
}

_SQUARE = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
_FAR_SQUARE = [(100.0, 100.0), (110.0, 100.0), (110.0, 110.0), (100.0, 110.0)]


def _build_matrix(module, *, zones=None, differential_pairs=None):
    """Build a ``module.ClearanceMatrix`` (module is ORACLE or SHIM) with
    identical field values, optionally with a zone_manager and/or
    differential pairs."""
    zone_manager = None
    if zones:
        routing_zones = [
            module.RoutingZone(
                name=name,
                polygon=poly,
                clearance_mm=clearance_mm,
                allowed_net_classes=allowed,
            )
            for name, poly, clearance_mm, allowed in zones
        ]
        zone_manager = module.ZoneManager(routing_zones)

    return module.ClearanceMatrix(
        _clearances=dict(_CLEARANCES),
        default_clearance=0.2,
        default_track_width=0.2,
        default_via_diameter=0.6,
        default_via_drill=0.3,
        _net_class_rules=dict(_RULES),
        _net_to_class=dict(_NET_TO_CLASS),
        zone_manager=zone_manager,
        _differential_pairs=dict(differential_pairs or {}),
    )


# ---------------------------------------------------------------------------
# get_track_width / get_via_diameter / get_via_drill
# ---------------------------------------------------------------------------

NETS = ["VCC_3V3", "GND_1", "SIG_A", "MAINS_L", "UNKNOWN_NET"]


@pytest.mark.parametrize("net", NETS)
def test_get_track_width_matches_oracle(net):
    oracle_m = _build_matrix(ORACLE)
    shim_m = _build_matrix(SHIM)
    assert sig(shim_m.get_track_width(net)) == sig(oracle_m.get_track_width(net))


@pytest.mark.parametrize("net", NETS)
def test_get_via_diameter_matches_oracle(net):
    oracle_m = _build_matrix(ORACLE)
    shim_m = _build_matrix(SHIM)
    assert sig(shim_m.get_via_diameter(net)) == sig(oracle_m.get_via_diameter(net))


@pytest.mark.parametrize("net", NETS)
def test_get_via_drill_matches_oracle(net):
    oracle_m = _build_matrix(ORACLE)
    shim_m = _build_matrix(SHIM)
    assert sig(shim_m.get_via_drill(net)) == sig(oracle_m.get_via_drill(net))


# ---------------------------------------------------------------------------
# is_differential_pair
# ---------------------------------------------------------------------------

DIFF_PAIRS = {frozenset(["USB_D+", "USB_D-"]): 0.05}


@pytest.mark.parametrize(
    ("net_a", "net_b"),
    [
        ("USB_D+", "USB_D-"),
        ("USB_D-", "USB_D+"),
        ("USB_D+", "SIG_A"),
        ("SIG_A", "SIG_B"),
    ],
)
def test_is_differential_pair_matches_oracle(net_a, net_b):
    oracle_m = _build_matrix(ORACLE, differential_pairs=DIFF_PAIRS)
    shim_m = _build_matrix(SHIM, differential_pairs=DIFF_PAIRS)
    assert sig(shim_m.is_differential_pair(net_a, net_b)) == sig(
        oracle_m.is_differential_pair(net_a, net_b)
    )


# ---------------------------------------------------------------------------
# _get_base_clearance
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("net_a", "net_b"),
    [
        ("VCC_3V3", "VCC_3V3"),  # key1 direct hit: (Power, Power)
        ("GND_1", "VCC_3V3"),  # key2 hit: (Power, GND) stored as (GND, Power)
        ("VCC_3V3", "SIG_A"),  # key1 hit: (Power, Signal)
        ("SIG_A", "VCC_3V3"),  # key2 hit: reversed order
        ("SIG_A", "SIG_B"),  # no table entry -> class fallback max(0.2, 0.2)
        ("MAINS_L", "SIG_A"),  # no table entry -> max(3.0, 0.2) = 3.0
        ("UNKNOWN_NET", "SIG_A"),  # unknown net -> "Default" class -> default_clearance
    ],
)
def test_get_base_clearance_matches_oracle(net_a, net_b):
    oracle_m = _build_matrix(ORACLE)
    shim_m = _build_matrix(SHIM)
    assert sig(shim_m._get_base_clearance(net_a, net_b)) == sig(
        oracle_m._get_base_clearance(net_a, net_b)
    )


def test_get_base_clearance_max_keeps_nan_not_f64_max():
    """CPython `max` keeps the FIRST NaN; `f64::max` would discard it."""
    nan_rules = dict(_RULES)
    nan_rules["HighVoltage"] = NetClassRules(
        name="HighVoltage", trace_width=0.5, clearance=math.nan, via_diameter=1.2, via_drill=0.6
    )
    oracle_m = ORACLE.ClearanceMatrix(_net_class_rules=dict(nan_rules), _net_to_class=dict(_NET_TO_CLASS))
    shim_m = SHIM.ClearanceMatrix(_net_class_rules=dict(nan_rules), _net_to_class=dict(_NET_TO_CLASS))

    want = oracle_m._get_base_clearance("MAINS_L", "SIG_A")
    got = shim_m._get_base_clearance("MAINS_L", "SIG_A")
    assert math.isnan(want), "oracle should produce NaN here (sanity check on the fixture)"
    assert math.isnan(got), "kernel discarded a NaN CPython's max would keep"


# ---------------------------------------------------------------------------
# get_clearance (differential pair shortcut, base clearance, zone override)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("net_a", "net_b", "x", "y"),
    [
        ("VCC_3V3", "VCC_3V3", None, None),
        ("SIG_A", "SIG_B", None, None),
        ("USB_D+", "USB_D-", None, None),  # differential pair shortcut
        ("MAINS_L", "SIG_A", None, None),  # no zone info supplied
    ],
)
def test_get_clearance_matches_oracle_no_zone(net_a, net_b, x, y):
    oracle_m = _build_matrix(ORACLE, differential_pairs=DIFF_PAIRS)
    shim_m = _build_matrix(SHIM, differential_pairs=DIFF_PAIRS)
    assert sig(shim_m.get_clearance(net_a, net_b, x, y)) == sig(
        oracle_m.get_clearance(net_a, net_b, x, y)
    )


_HV_ZONE = ("HV", _SQUARE, 3.0, {"HighVoltage", "GND", "Power"})
_SIGNAL_ZONE = ("Signal", _FAR_SQUARE, 0.2, {"Signal", "GND", "Power"})


@pytest.mark.parametrize(
    ("net_a", "net_b", "x", "y"),
    [
        # Inside the HV zone, one net IS HighVoltage -> zone override applies.
        ("MAINS_L", "SIG_A", 5.0, 5.0),
        # Inside the HV zone, neither net is HighVoltage -> zone does not apply.
        ("SIG_A", "SIG_B", 5.0, 5.0),
        # Outside every zone -> unzoned, base clearance only.
        ("MAINS_L", "SIG_A", 500.0, 500.0),
        # Inside the (non-HV) Signal zone -> zone_applies is False by construction
        # (only "HV"-named zones ever apply, per the oracle).
        ("MAINS_L", "SIG_A", 105.0, 105.0),
    ],
)
def test_get_clearance_matches_oracle_with_zones(net_a, net_b, x, y):
    zones = [_HV_ZONE, _SIGNAL_ZONE]
    oracle_m = _build_matrix(ORACLE, zones=zones, differential_pairs=DIFF_PAIRS)
    shim_m = _build_matrix(SHIM, zones=zones, differential_pairs=DIFF_PAIRS)
    assert sig(shim_m.get_clearance(net_a, net_b, x, y)) == sig(
        oracle_m.get_clearance(net_a, net_b, x, y)
    )


def test_get_clearance_zone_override_max_keeps_nan_not_f64_max():
    """The zone-override `max(base_clearance, zone.clearance_mm)` must keep a
    NaN base clearance rather than discarding it via `f64::max`."""
    nan_rules = {
        "HighVoltage": NetClassRules(
            name="HighVoltage", trace_width=0.5, clearance=math.nan, via_diameter=1.2, via_drill=0.6
        ),
    }
    zones = [_HV_ZONE]
    oracle_m = ORACLE.ClearanceMatrix(_net_class_rules=dict(nan_rules), _net_to_class=dict(_NET_TO_CLASS))
    shim_m = SHIM.ClearanceMatrix(_net_class_rules=dict(nan_rules), _net_to_class=dict(_NET_TO_CLASS))
    oracle_m.zone_manager = ORACLE.ZoneManager(
        [ORACLE.RoutingZone(name="HV", polygon=_SQUARE, clearance_mm=3.0, allowed_net_classes={"HighVoltage"})]
    )
    shim_m.zone_manager = SHIM.ZoneManager(
        [SHIM.RoutingZone(name="HV", polygon=_SQUARE, clearance_mm=3.0, allowed_net_classes={"HighVoltage"})]
    )

    want = oracle_m.get_clearance("MAINS_L", "SIG_A", 5.0, 5.0)
    got = shim_m.get_clearance("MAINS_L", "SIG_A", 5.0, 5.0)
    assert math.isnan(want), "oracle should produce NaN here (sanity check on the fixture)"
    assert math.isnan(got), "kernel discarded a NaN CPython's max would keep"


# ---------------------------------------------------------------------------
# add_differential_pair's clearance arithmetic
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("spacing_mm", "track_width"),
    [
        (0.25, 0.15),
        (0.5, 0.1),
        (0.1, 0.2),  # goes negative, by design (see oracle docstring)
        (0.0, 0.0),
    ],
)
def test_add_differential_pair_matches_oracle(spacing_mm, track_width):
    """Builds a matrix whose 'USB_D+' net resolves to a class with the given
    track width, then compares the resulting registered clearance."""
    rules = {"Signal": NetClassRules(name="Signal", trace_width=track_width, clearance=0.2)}
    net_to_class = {"USB_D+": "Signal", "USB_D-": "Signal"}

    oracle_m = ORACLE.ClearanceMatrix(_net_class_rules=dict(rules), _net_to_class=dict(net_to_class))
    shim_m = SHIM.ClearanceMatrix(_net_class_rules=dict(rules), _net_to_class=dict(net_to_class))

    oracle_m.add_differential_pair("USB_D+", "USB_D-", spacing_mm)
    shim_m.add_differential_pair("USB_D+", "USB_D-", spacing_mm)

    key = frozenset(["USB_D+", "USB_D-"])
    assert sig(shim_m._differential_pairs[key]) == sig(oracle_m._differential_pairs[key])


# ---------------------------------------------------------------------------
# ZoneManager.get_zone_at
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("x", "y"),
    [
        (5.0, 5.0),  # inside HV zone
        (105.0, 105.0),  # inside Signal zone
        (500.0, 500.0),  # unzoned
        (0.0, 0.0),  # exact corner vertex (boundary)
        (10.0, 5.0),  # exact edge (boundary)
    ],
)
def test_get_zone_at_matches_oracle(x, y):
    zones = [_HV_ZONE, _SIGNAL_ZONE]
    oracle_m = _build_matrix(ORACLE, zones=zones)
    shim_m = _build_matrix(SHIM, zones=zones)

    oracle_zone = oracle_m.zone_manager.get_zone_at(x, y)
    shim_zone = shim_m.zone_manager.get_zone_at(x, y)

    if oracle_zone is None:
        assert shim_zone is None
    else:
        assert shim_zone is not None
        assert sig(shim_zone.name) == sig(oracle_zone.name)
        assert sig(shim_zone.clearance_mm) == sig(oracle_zone.clearance_mm)
        assert sig(shim_zone.polygon) == sig(oracle_zone.polygon)


def test_get_zone_at_no_zones_returns_none():
    oracle_m = _build_matrix(ORACLE)
    shim_m = _build_matrix(SHIM)
    assert oracle_m.zone_manager is None
    assert shim_m.zone_manager is None


# ---------------------------------------------------------------------------
# Wiring proof: the SHIPPED entry points must reach Rust, not just compare
# equal to a parallel Python implementation.
# ---------------------------------------------------------------------------


def _boom(*_a, **_k):
    raise RuntimeError("REACHED_RUST")


@pytest.mark.parametrize(
    "rust_symbol",
    [
        "clearance_get_base_clearance_py",
        "clearance_class_attr_py",
        "clearance_is_differential_pair_py",
        "clearance_diff_pair_required_py",
        "clearance_get_clearance_py",
        "clearance_zone_at_py",
    ],
)
def test_shipped_module_delegates_to_rust(rust_symbol):
    """A green differential compares the oracle against the shim and passes
    whether or not production delegates -- this is the assertion that
    catches the RUST-EXISTS-UNWIRED state. Monkeypatching each Rust symbol
    to raise and calling the SHIPPED entry point must propagate the raise.
    """
    original = getattr(_temper_drc_rs, rust_symbol)
    setattr(_temper_drc_rs, rust_symbol, _boom)
    try:
        matrix = SHIM.ClearanceMatrix(
            _net_class_rules={"Signal": NetClassRules(name="Signal", trace_width=0.2, clearance=0.2)},
            _net_to_class={"A": "Signal", "B": "Signal"},
        )
        with pytest.raises(RuntimeError, match="REACHED_RUST"):
            if rust_symbol == "clearance_get_base_clearance_py":
                matrix._get_base_clearance("A", "B")
            elif rust_symbol == "clearance_class_attr_py":
                matrix.get_track_width("A")
            elif rust_symbol == "clearance_is_differential_pair_py":
                matrix.is_differential_pair("A", "B")
            elif rust_symbol == "clearance_diff_pair_required_py":
                matrix.add_differential_pair("A", "B", 0.25)
            elif rust_symbol == "clearance_get_clearance_py":
                matrix.get_clearance("A", "B")
            elif rust_symbol == "clearance_zone_at_py":
                zm = SHIM.ZoneManager(
                    [SHIM.RoutingZone(name="Z", polygon=_SQUARE, clearance_mm=0.2, allowed_net_classes={"Signal"})]
                )
                zm.get_zone_at(5.0, 5.0)
    finally:
        setattr(_temper_drc_rs, rust_symbol, original)
