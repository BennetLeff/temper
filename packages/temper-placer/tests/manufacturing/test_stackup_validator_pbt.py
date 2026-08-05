"""Property-based tests for the Rust stackup validator (``temper_io_types``)
— Wave 4 Phase 4 leftovers slice.

The Rust implementation must satisfy the same closed-form invariants the
pre-migration Python implementation satisfies, asserted INDEPENDENTLY of
the oracle (the differential test owns bit-parity; this file owns the
formulas, thresholds, fail-closed behaviour and metamorphic relations).
Every property is fail-capable.

R1c: properties P1-P7.  R1d: MR1-MR4.
"""

from __future__ import annotations

import pytest
import temper_io_types as _io
from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.core.board import Layer, LayerStackup

VALIDATE_STACKUP = _io.validate_stackup

# 4-layer canonical stackup (F.Cu 2oz, In1 1oz plane, In2 1oz plane, B.Cu 1oz).
_STACKUP = LayerStackup.default_4layer()

_FILL_PCT = st.floats(min_value=0.0, max_value=200.0, allow_nan=False, allow_infinity=False)
_IMPEDANCE = st.floats(min_value=-200.0, max_value=300.0, allow_nan=False, allow_infinity=False)

_SYMMETRY_NAME = "Copper Symmetry"
_BALANCE_NAME = "Copper Balance"
_IMPEDANCE_NAME = "Controlled Impedance"
_ADJACENCY_NAME = "Return-Path Adjacency"

_NET_NAMES = ["USB_D+", "USB_D-", "USB_DP", "USB_DM", "ETH_RX+", "ETH_RX-"]


def _fill_dict(values):
    return dict(zip(["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"], values))


def _by_name(report, name):
    for r in report.results:
        if r.check_name == name:
            return r
    raise KeyError(name)


# ---------------------------------------------------------------------------
# P1: symmetry details formula — when the symmetry check warns, its details
# dict equals the closed-form recomputation (bit-exact).
# ---------------------------------------------------------------------------


@pytest.mark.property
@given(f1=_FILL_PCT, f2=_FILL_PCT, f3=_FILL_PCT, f4=_FILL_PCT)
@settings(max_examples=50, deadline=30000)
def test_p1_symmetry_warn_details_formula(f1, f2, f3, f4):
    """Warn-case details == {max_eff, min_eff, imbalance} recomputed."""
    report = VALIDATE_STACKUP(_STACKUP, copper_fill_percentages=_fill_dict([f1, f2, f3, f4]))
    r = _by_name(report, _SYMMETRY_NAME)
    weights = {
        "F.Cu": 2.0 * (f1 / 100.0),
        "In1.Cu": 1.0 * (f2 / 100.0),
        "In2.Cu": 1.0 * (f3 / 100.0),
        "B.Cu": 1.0 * (f4 / 100.0),
    }
    total = sum(weights.values())
    if r.passed:
        return  # pass case has no details; covered by P2's threshold split
    # Fail-capable: only reachable when the implementation warns.
    assert r.details is not None
    max_eff = max(weights.values())
    min_eff = min(weights.values())
    assert float(r.details["max_eff"]).hex() == max_eff.hex()
    assert float(r.details["min_eff"]).hex() == min_eff.hex()
    assert float(r.details["imbalance"]).hex() == ((max_eff - min_eff) / total).hex()


# ---------------------------------------------------------------------------
# P2: symmetry threshold — warn iff imbalance > 0.25 (with the formula from
# P1), pass otherwise.
# ---------------------------------------------------------------------------


@pytest.mark.property
@given(f1=_FILL_PCT, f2=_FILL_PCT, f3=_FILL_PCT, f4=_FILL_PCT)
@settings(max_examples=50, deadline=30000)
def test_p2_symmetry_threshold(f1, f2, f3, f4):
    """passed == (imbalance <= 0.25), and the skip arms are unreachable here."""
    report = VALIDATE_STACKUP(_STACKUP, copper_fill_percentages=_fill_dict([f1, f2, f3, f4]))
    r = _by_name(report, _SYMMETRY_NAME)
    weights = {
        "F.Cu": 2.0 * (f1 / 100.0),
        "In1.Cu": 1.0 * (f2 / 100.0),
        "In2.Cu": 1.0 * (f3 / 100.0),
        "B.Cu": 1.0 * (f4 / 100.0),
    }
    total = sum(weights.values())
    if total == 0:
        # Zero-copper skip: message pinned.
        assert r.message == "Zero effective copper -- symmetry check skipped"
        return
    max_eff = max(weights.values())
    min_eff = min(weights.values())
    imbalance = (max_eff - min_eff) / total
    assert r.passed == (imbalance <= 0.25)


# ---------------------------------------------------------------------------
# P3: balance threshold — warn iff min < 25 or max > 75.
# ---------------------------------------------------------------------------


@pytest.mark.property
@given(f1=_FILL_PCT, f2=_FILL_PCT, f3=_FILL_PCT, f4=_FILL_PCT)
@settings(max_examples=50, deadline=30000)
def test_p3_balance_threshold(f1, f2, f3, f4):
    """passed == (min >= 25 and max <= 75)."""
    report = VALIDATE_STACKUP(_STACKUP, copper_fill_percentages=_fill_dict([f1, f2, f3, f4]))
    r = _by_name(report, _BALANCE_NAME)
    vals = [f1, f2, f3, f4]
    assert r.passed == (min(vals) >= 25.0 and max(vals) <= 75.0)


# ---------------------------------------------------------------------------
# P4: structural invariants — four checks, fixed order, fail-closed report.
# ---------------------------------------------------------------------------


@pytest.mark.property
@given(nets=st.frozensets(st.sampled_from(_NET_NAMES), min_size=0, max_size=4))
@settings(max_examples=50, deadline=30000)
def test_p4_report_structure(nets):
    """Always exactly [Symmetry, Adjacency, Impedance, Balance]; all_passed is
    the conjunction, and never vacuously true on a real run."""
    report = VALIDATE_STACKUP(_STACKUP, differential_nets=nets)
    assert [r.check_name for r in report.results] == [
        _SYMMETRY_NAME,
        _ADJACENCY_NAME,
        _IMPEDANCE_NAME,
        _BALANCE_NAME,
    ]
    assert report.all_passed == all(r.passed for r in report.results)
    # A fresh report with no results fails closed.
    assert _io.StackupValidationReport(results=[]).all_passed is False


# ---------------------------------------------------------------------------
# P5: fill resolution — explicit non-empty dict wins; empty dict falls back
# to the Temper defaults on a 4-layer F.Cu-first stackup.
# ---------------------------------------------------------------------------


@pytest.mark.property
@given(f1=_FILL_PCT, f2=_FILL_PCT, f3=_FILL_PCT, f4=_FILL_PCT)
@settings(max_examples=50, deadline=30000)
def test_p5_explicit_fill_wins(f1, f2, f3, f4):
    """Explicit fill values are used verbatim (symmetry reflects them)."""
    explicit = _fill_dict([f1, f2, f3, f4])
    report = VALIDATE_STACKUP(_STACKUP, copper_fill_percentages=explicit)
    r = _by_name(report, _SYMMETRY_NAME)
    if r.details is not None:
        # The warn-case details must reflect the explicit values.
        weights = {
            "F.Cu": 2.0 * (f1 / 100.0),
            "In1.Cu": 1.0 * (f2 / 100.0),
            "In2.Cu": 1.0 * (f3 / 100.0),
            "B.Cu": 1.0 * (f4 / 100.0),
        }
        assert float(r.details["max_eff"]).hex() == max(weights.values()).hex()


def test_p5b_empty_fill_uses_defaults():
    """copper_fill_percentages={} is falsy -> Temper defaults (35/95/95/30)."""
    report = VALIDATE_STACKUP(_STACKUP, copper_fill_percentages={})
    r = _by_name(report, _SYMMETRY_NAME)
    assert "22.4%" in r.message  # default-fill imbalance


def test_p5c_non4layer_no_fill_all_skipped():
    """A 2-layer stackup with no fill skips the fill-dependent checks."""
    stackup = LayerStackup(layers=(Layer("L1", "signal", 1.0, True), Layer("L2", "plane", 1.0, False)))
    report = VALIDATE_STACKUP(stackup)
    assert all(r.passed for r in report.results)


# ---------------------------------------------------------------------------
# P6: impedance validity split — pass iff 70 <= z <= 120; each failure class
# has its pinned message prefix.
# ---------------------------------------------------------------------------


@pytest.mark.property
@given(z=_IMPEDANCE)
@settings(max_examples=50, deadline=30000)
def test_p6_impedance_validity_split(z):
    """The impedance check's three branches split exactly at 0 and [70,120]."""
    report = VALIDATE_STACKUP(
        _STACKUP, differential_nets=frozenset({"USB_D+"}), impedance_spec_ohms=z
    )
    r = _by_name(report, _IMPEDANCE_NAME)
    if z <= 0:
        assert not r.passed
        assert r.message.startswith("Invalid impedance value:")
    elif 70.0 <= z <= 120.0:
        assert r.passed
    else:
        assert not r.passed
        assert r.message.startswith("Impedance ")


# ---------------------------------------------------------------------------
# P7: adjacency — diff nets + 4-layer plane-L3 stackup warns unless
# stitching vias; no diff nets skips.
# ---------------------------------------------------------------------------


@pytest.mark.property
@given(nets=st.frozensets(st.sampled_from(_NET_NAMES), min_size=1, max_size=3))
@settings(max_examples=50, deadline=30000)
def test_p7_adjacency_with_diff_nets_warns(nets):
    """The canonical 4-layer stackup warns on L4-PWR adjacency for diff nets."""
    report = VALIDATE_STACKUP(_STACKUP, differential_nets=nets)
    r = _by_name(report, _ADJACENCY_NAME)
    assert not r.passed
    assert r.layer == "L4 (B.Cu)"
    # Stitching vias flip it to a pass.
    report_vias = VALIDATE_STACKUP(_STACKUP, differential_nets=nets, has_stitching_vias=True)
    r_vias = _by_name(report_vias, _ADJACENCY_NAME)
    assert r_vias.passed


def test_p7b_adjacency_no_diff_nets_skips():
    report = VALIDATE_STACKUP(_STACKUP, differential_nets=frozenset())
    r = _by_name(report, _ADJACENCY_NAME)
    assert r.passed
    assert "No differential nets" in r.message


# ---------------------------------------------------------------------------
# MR1: fill-dict insertion-order permutation invariance (distinct values).
# ---------------------------------------------------------------------------


@pytest.mark.property
@given(vals=st.lists(_FILL_PCT, min_size=4, max_size=4).filter(lambda v: len(set(v)) == 4))
@settings(max_examples=50, deadline=30000)
def test_mr1_fill_dict_order_permutation(vals):
    """Reordering the fill dict's insertion order changes nothing."""
    names = ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"]
    base = dict(zip(names, vals))
    permuted = dict(reversed(list(base.items())))
    r1 = VALIDATE_STACKUP(_STACKUP, copper_fill_percentages=base)
    r2 = VALIDATE_STACKUP(_STACKUP, copper_fill_percentages=permuted)
    assert [x.message for x in r1.results] == [x.message for x in r2.results]
    assert [x.passed for x in r1.results] == [x.passed for x in r2.results]


# ---------------------------------------------------------------------------
# MR2: impedance boundary closure — 70.0 and 120.0 pass, the open neighbours
# fail, and the pass set is exactly the closed interval.
# ---------------------------------------------------------------------------


def test_mr2_impedance_boundary_closure():
    for z in (70.0, 120.0):
        r = _by_name(
            VALIDATE_STACKUP(_STACKUP, differential_nets=frozenset({"USB_D+"}), impedance_spec_ohms=z),
            _IMPEDANCE_NAME,
        )
        assert r.passed, z
    for z in (69.999999999, 120.000000001):
        r = _by_name(
            VALIDATE_STACKUP(_STACKUP, differential_nets=frozenset({"USB_D+"}), impedance_spec_ohms=z),
            _IMPEDANCE_NAME,
        )
        assert not r.passed, z


# ---------------------------------------------------------------------------
# MR3: differential-net set contents — the missing-spec message names the
# nets in sorted order, so two sets with the same members produce the same
# message regardless of construction.
# ---------------------------------------------------------------------------


@pytest.mark.property
@given(nets=st.frozensets(st.sampled_from(_NET_NAMES), min_size=1, max_size=4))
@settings(max_examples=50, deadline=30000)
def test_mr3_differential_net_set_membership(nets):
    """Same members, different iteration order -> same impedance message."""
    r1 = _by_name(
        VALIDATE_STACKUP(_STACKUP, differential_nets=nets, impedance_spec_ohms=None),
        _IMPEDANCE_NAME,
    )
    r2 = _by_name(
        VALIDATE_STACKUP(_STACKUP, differential_nets=frozenset(sorted(nets)), impedance_spec_ohms=None),
        _IMPEDANCE_NAME,
    )
    assert r1.message == r2.message
    # And the nets are named inside the message.
    for n in nets:
        assert n in r1.message


# ---------------------------------------------------------------------------
# MR4: default-fill equivalence — omitting the fill dict equals passing the
# Temper defaults explicitly on the canonical stackup.
# ---------------------------------------------------------------------------


def test_mr4_default_fill_equivalence():
    defaults = {"F.Cu": 35.0, "In1.Cu": 95.0, "In2.Cu": 95.0, "B.Cu": 30.0}
    r_implied = VALIDATE_STACKUP(_STACKUP)
    r_explicit = VALIDATE_STACKUP(_STACKUP, copper_fill_percentages=defaults)
    assert [x.message for x in r_implied.results] == [x.message for x in r_explicit.results]
    assert [x.passed for x in r_implied.results] == [x.passed for x in r_explicit.results]
