"""Differential test: deterministic feedback zone adjustment, Rust vs oracle.

Wave 4, **Phase 5** (deterministic hubs slice). The pure adjustment compute of
``temper_placer/deterministic/feedback/zone_adjuster.py``
(``ZoneAdjuster.compute_adjustments``) moves to
``temper_design_bundle_python.deterministic_hubs.zone_adjustments_kernel``. The
Python module keeps its public API (``ZoneAdjustment``/``AdjustmentResult``
stay Python dataclasses) and delegates.

Bit-exactness pins:
- Per-zone violation counting preserves **first-seen insertion order**
  (``zone_counts`` is a dict; the kernel keeps a Vec in first-seen order).
- ``excess = count - threshold + 1`` (int arithmetic), ``expansion = excess *
  expansion_per_violation`` (single IEEE-754 product).
- ``min``/``max`` use Python semantics (NaN-propagating: ``b if b < a else a``)
  — replicated manually, not ``f64::min``/``f64::max``.
- ``abs(x2 - x1)`` width/height, direction gating via
  ``any(d in ["right", "left"] for d in can_expand)``. Deltas compare by
  numeric value (``float.hex()``): the oracle yields int-typed deltas for
  int-typed config bounds/max_size (test fixtures); the kernel coerces to f64.
  Values are bit-identical; the type deviation is recorded in VERIFICATION.md.
- Empty violations list => empty adjustments (vacuity guard).
- ``if not config`` treats a MISSING zone config and an EMPTY dict the same
  (skip) — pinned.
"""

from __future__ import annotations

import temper_design_bundle_python as _tdb
import tests.deterministic._zone_adjuster_py_oracle as _oracle
from tests.core._contract_canon import canon

# Rust symbols under test — must exist or this file fails to collect (RED).
_DH = _tdb.deterministic_hubs
RS_ADJUST = _DH.zone_adjustments_kernel


def _zones(*names):
    return list(names)


def _run(violation_zones, zone_config, threshold=5, expansion=0.5):
    """Run both sides; return (oracle_adjustments_dict, shim_adjustments_list)."""
    oracle_violations = [
        _oracle.MappedViolation(type="clearance", components=["Q2"], zone=z)
        for z in violation_zones
    ]
    adjuster = _oracle.ZoneAdjuster(
        zone_config, violation_threshold=threshold, expansion_per_violation=expansion
    )
    oracle_result = adjuster.compute_adjustments(oracle_violations)
    shim_list = RS_ADJUST(
        violation_zones, zone_config, threshold, expansion
    )
    return oracle_result.adjustments, shim_list


def _delta_key(v):
    """Numeric bit-exact key for a delta.

    The kernel coerces config numbers to f64, so an int-typed oracle delta
    (int-typed config bounds/max_size in test fixtures) is float-typed in the
    shim. Values are bit-identical (10 == 10.0 exactly); the type deviation is
    recorded in VERIFICATION.md and unobservable to consumers (all existing
    assertions are numeric). Comparing by value still catches any real numeric
    divergence.
    """
    return float(v).hex()


def _assert_parity(violation_zones, zone_config, threshold=5, expansion=0.5):
    oracle_adjs, shim_list = _run(violation_zones, zone_config, threshold, expansion)
    oracle_keys = list(oracle_adjs.keys())
    shim_keys = [name for name, _w, _h in shim_list]
    assert shim_keys == oracle_keys, f"insertion order diverges: {shim_keys} vs {oracle_keys}"
    for (name, delta_w, delta_h), (o_name, o_adj) in zip(shim_list, oracle_adjs.items()):
        assert name == o_name
        assert (_delta_key(delta_w), _delta_key(delta_h)) == (
            _delta_key(o_adj.delta_width),
            _delta_key(o_adj.delta_height),
        ), f"delta divergence for {name}: {(delta_w, delta_h)} vs {(o_adj.delta_width, o_adj.delta_height)}"


_ZONE_CONFIG = {
    "HV_POWER": {
        "bounds": [(60, 0), (75, 15)],
        "max_size": (25, 20),
        "can_expand": ["right", "down"],
    },
    "CONTROL": {
        "bounds": [(0, 0), (60, 30)],
        "max_size": (70, 35),
        "can_expand": ["right"],
    },
}


def test_no_adjustments_below_threshold():
    _assert_parity(_zones("HV_POWER"), _ZONE_CONFIG, threshold=5)


def test_expands_when_exceeding_threshold():
    _assert_parity(_zones(*(["HV_POWER"] * 10)), _ZONE_CONFIG, threshold=5)


def test_respects_max_size_limits():
    _assert_parity(_zones(*(["HV_POWER"] * 100)), _ZONE_CONFIG, threshold=5, expansion=1.0)


def test_expansion_directions():
    _assert_parity(_zones(*(["CONTROL"] * 10)), _ZONE_CONFIG, threshold=5)


def test_empty_violations_empty_result():
    _assert_parity(_zones(), _ZONE_CONFIG)


def test_violations_without_zone_ignored():
    _assert_parity(_zones(None, "HV_POWER", None, None, "HV_POWER", "HV_POWER", "HV_POWER", "HV_POWER", "HV_POWER", "HV_POWER"), _ZONE_CONFIG, threshold=5)


def test_empty_string_zone_falsy_skipped_shim_path():
    """Oracle's ``if v.zone:`` skips falsy zones — an empty-string zone must
    not be counted. Pinned through the SHIM path (the shim normalises falsy
    zones to None before the kernel; a kernel fed the raw string would count
    it as a zone named \"\")."""
    from temper_placer.deterministic.feedback.zone_adjuster import ZoneAdjuster as ShimAdjuster

    config = {
        "HV_POWER": {
            "bounds": [(60, 0), (75, 15)],
            "max_size": (25, 20),
            "can_expand": ["right", "down"],
        },
    }
    zone_list = [None, "", "HV_POWER", "", "HV_POWER", "HV_POWER", "HV_POWER", "HV_POWER", "HV_POWER", "HV_POWER"]
    oracle_violations = [
        _oracle.MappedViolation(type="clearance", components=[], zone=z) for z in zone_list
    ]
    oracle_result = _oracle.ZoneAdjuster(config, violation_threshold=5).compute_adjustments(
        oracle_violations
    )
    shim_violations = [
        _oracle.MappedViolation(type="clearance", components=[], zone=z) for z in zone_list
    ]
    shim_result = ShimAdjuster(config, violation_threshold=5).compute_adjustments(
        shim_violations
    )
    assert list(shim_result.adjustments.keys()) == list(oracle_result.adjustments.keys())
    assert canon(shim_result.adjustments["HV_POWER"].delta_width) == canon(
        oracle_result.adjustments["HV_POWER"].delta_width
    )


def test_missing_zone_config_skipped():
    config = {"GHOST": {"bounds": [(0, 0), (10, 10)], "can_expand": ["right", "up", "down", "left"]}}
    _assert_parity(_zones("GHOST", "GHOST", "GHOST", "GHOST", "GHOST"), config, threshold=5)


def test_empty_zone_config_dict_skipped():
    # zone present in config but the dict is empty -> `if not config` skips.
    config = {"EMPTY": {}}
    _assert_parity(_zones("EMPTY", "EMPTY", "EMPTY", "EMPTY", "EMPTY"), config, threshold=5)


def test_missing_bounds_skipped():
    config = {"NB": {"max_size": (20, 20), "can_expand": ["right", "up", "down", "left"]}}
    _assert_parity(_zones("NB", "NB", "NB", "NB", "NB"), config, threshold=5)


def test_default_can_expand_all_directions():
    config = {"ALL": {"bounds": [(0, 0), (10, 10)], "max_size": (20, 20)}}
    _assert_parity(_zones(*(["ALL"] * 10)), config, threshold=5)


def test_default_max_size_infinity():
    config = {"BIG": {"bounds": [(0, 0), (1, 1)], "can_expand": ["right", "up", "down", "left"]}}
    _assert_parity(_zones(*(["BIG"] * 100)), config, threshold=5, expansion=100.0)


def test_threshold_one_counts_all():
    _assert_parity(_zones("HV_POWER"), _ZONE_CONFIG, threshold=1)


def test_negative_deltas_not_emitted():
    # max_size smaller than current bounds -> target < width -> delta_w negative
    # -> the `delta_w > 0 or delta_h > 0` gate drops the zone on BOTH sides.
    config = {"SHRINK": {"bounds": [(0, 0), (50, 50)], "max_size": (10, 10), "can_expand": ["right", "up", "down", "left"]}}
    _assert_parity(_zones(*(["SHRINK"] * 10)), config, threshold=5)


def test_fractional_bounds_and_expansion():
    config = {
        "F": {
            "bounds": [(0.5, 0.25), (10.75, 8.5)],
            "max_size": (12.25, 9.5),
            "can_expand": ["right", "down", "left", "up"],
        }
    }
    _assert_parity(_zones(*(["F"] * 7)), config, threshold=5, expansion=0.125)


def test_reversed_bounds_abs():
    # bounds in (max, min) order -> width/height via abs still positive.
    config = {"R": {"bounds": [(75, 15), (60, 0)], "max_size": (80, 20), "can_expand": ["right", "up", "down", "left"]}}
    _assert_parity(_zones(*(["R"] * 10)), config, threshold=5)


# ---------------------------------------------------------------------------
# Malformed user-config shapes: the orchestrator passes user YAML through
# unvalidated (`zone.get("max_size", ...)` / `zone.get("can_expand", ...)` in
# `AutomatedZeroDRC._get_zone_config`), so these are PRODUCTION-reachable and
# must raise exactly like the oracle instead of silently changing geometry
# (P1: can_expand fallback-to-all-four-directions, max_size fallback-to-
# unbounded).
# ---------------------------------------------------------------------------


def _error_outcome(fn):
    try:
        return ("ok", fn())
    except Exception as exc:  # noqa: BLE001 -- comparing failure modes IS the test
        return ("raised", type(exc).__name__, str(exc))


def _run_both_outcomes(violation_zones, zone_config, threshold=5, expansion=0.5):
    oracle_violations = [
        _oracle.MappedViolation(type="clearance", components=[], zone=z)
        for z in violation_zones
    ]
    adjuster = _oracle.ZoneAdjuster(
        zone_config, violation_threshold=threshold, expansion_per_violation=expansion
    )
    o = _error_outcome(
        lambda: {
            k: (v.delta_width, v.delta_height)
            for k, v in adjuster.compute_adjustments(oracle_violations).adjustments.items()
        }
    )
    s = _error_outcome(
        lambda: {
            name: (delta_w, delta_h)
            for (name, delta_w, delta_h) in RS_ADJUST(violation_zones, zone_config, threshold, expansion)
        }
    )
    return o, s


def test_can_expand_non_list_parity():
    """Oracle semantics for a non-list can_expand: the oracle ITERATES the
    object (`any(d in [...] for d in can_expand)`) — a string iterates to
    characters (no direction matches -> NO adjustment, not an all-directions
    expansion), an int/None raises TypeError '<T> object is not iterable', and
    a list of tuples compares by equality (no match). The kernel must not
    fall back to all four directions (P1)."""
    base = {"Z": {"bounds": [(0, 0), (10, 10)], "max_size": (20, 20)}}
    for can_expand in ["right", "right,left", "", 42, None, [("right",)], [1, 2]]:
        cfg = {"Z": dict(base["Z"], can_expand=can_expand)}
        o, s = _run_both_outcomes(_zones(*(["Z"] * 6)), cfg)
        assert s == o, f"can_expand={can_expand!r} divergence: {s} vs {o}"


def test_max_size_non_pair_parity():
    """Oracle semantics for a non-2-tuple max_size: `max_width, max_height =
    max_size` is CPython 2-target unpack — a scalar (int/float) or None raises
    TypeError 'cannot unpack non-iterable <T> object', a 1-tuple ValueError
    'not enough values to unpack (expected 2, got 1)', a 3-tuple ValueError
    'too many values to unpack (expected 2)', and a 2-char string unpacks to
    chars and then fails the oracle's min() comparison. The kernel must not
    fall back to unbounded expansion (P1)."""
    base = {"Z": {"bounds": [(0, 0), (10, 10)], "can_expand": ["right", "up", "down", "left"]}}
    for max_size in [20, 20.5, None, (20,), (20, 20, 20), "20", "2020", [20, 20]]:
        cfg = {"Z": dict(base["Z"], max_size=max_size)}
        o, s = _run_both_outcomes(_zones(*(["Z"] * 6)), cfg)
        assert s == o, f"max_size={max_size!r} divergence: {s} vs {o}"


def test_present_none_keys_are_not_defaults():
    """`config.get("max_size", default)`/`config.get("can_expand", default)`
    return the STORED None when the key is present — the oracle then raises
    (unpack / iteration), it does NOT apply the default. The kernel must
    distinguish an absent key from a present-None (P1)."""
    for key in ["max_size", "can_expand"]:
        cfg = {"Z": {"bounds": [(0, 0), (10, 10)], key: None}}
        o, s = _run_both_outcomes(_zones(*(["Z"] * 6)), cfg)
        assert s == o, f"present-None {key} divergence: {s} vs {o}"
        assert s[0] == "raised" and s[1] == "TypeError"
