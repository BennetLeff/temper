"""Differential test: Rust validator-audit sequencing vs the pinned Python oracle.

Orchestration-port unit U-I (Rust Orchestration Engine plan 2026-08-09-001,
Wave-4 CP-SAT placement-loop slice): the R24 post-solve audit SEQUENCING of
``temper_placer/placer/cp_sat/validator_audit.py`` moved to
``temper-orchestration``'s ``validator_audit.rs`` as the
``audit_domain_clearance_validator`` pyfunction (the two ``ValueError``
guards, the validator-placement build call, the ``verify_iec60335_compliance``
re-run, the ``stats`` extraction, the geometry-trust computation + the
degraded-geometry ``logger.error``, the ``covered_pairs`` frozenset build,
the per-violation bucket dispatch + ``DomainClearanceValidatorViolation``
construction, and the ``DomainClearanceValidatorAuditResult`` assembly).
The pre-migration audit is pinned VERBATIM as
``_validator_audit_py_oracle.py``; every assertion drives IDENTICAL inputs
through both the delegated shim (Rust sequencing) and the oracle audit, and
asserts the canonicalized ``DomainClearanceValidatorAuditResult`` -- every
bucket, every violation field, the reason strings, ``stats``,
``geometry_trusted`` -- is byte-identical.

Boundary (what is NOT compared -- the Python call-backs both sides share by
construction): ``build_validator_placement`` (unchanged in the shim; invoked
as a call-back by the Rust arm), ``verify_iec60335_compliance`` (the exact
REQ-SAFE-01 validator; the U-I boundary -- the mocked edge cases below
script BOTH arms through the same fake), and the result dataclasses. The
mocked edge cases additionally pin call-ARGUMENT parity: the fake validator
records the ``validator_placement`` each arm hands it and the two are
compared canonicalized, so the Rust arm demonstrably calls the boundary with
the oracle's exact geometry (not merely a result-equal one).

The three fallback paths the oracle defends against (and the port must
reproduce bit-identically) are exercised explicitly, because the real
validator never emits them:

- ``pair_kind`` falsy (None / "") -> ``v.pair_kind or ("intra" if
  ``v.ref_a == v.ref_b`` else "inter")``: VALUE equality on the ORIGINAL
  attribute values -- two falsy refs (``None == None``) are "intra", two
  equal-valued distinct strings are "intra" (identity is NOT the test).
- ``measured_mm`` / ``required_mm`` None -> ``float("nan")`` in the
  violation record (the covered-pair reason's ``:.3f`` format on a None
  raises in BOTH arms -- parity of the raise is asserted too).
- ``stats.rows[].pairs_origin_modelled`` falsy (None) -> contributes 0 to
  the geometry-trust sum (``int(... or 0)``).

PBT (5 non-vacuous properties) + metamorphic (4 relations) as required by
the U-I dispatch.
"""

from __future__ import annotations

import logging
import math
import random
from types import SimpleNamespace

import pytest

import tests.placer.cp_sat._validator_audit_py_oracle as _oracle
from temper_placer.pcl.constraints import ConstraintTier, SeparatedConstraint
from temper_placer.placer.cp_sat import validator_audit as _shim
from temper_placer.requirements.validators.clearance import VoltageDomain

# ---------------------------------------------------------------------------
# Shared fixtures (same minimal shape as test_validator_audit.py)
# ---------------------------------------------------------------------------


def _pad(net: str, offset: tuple[float, float], width: float = 2.0, height: float = 1.0) -> dict:
    """One rect pad in the validator's pad schema."""
    return {
        "number": "1",
        "net": net,
        "offset": offset,
        "width": width,
        "height": height,
        "shape": "rect",
        "roundrect_ratio": 0.0,
        "pad_rotation_deg": 0.0,
        "layer": "F.Cu",
    }


def _placement(components: list[dict]) -> dict:
    """Validator-shape placement: {"components": [...], "nets": {...},
    "board": {...}}."""
    return {
        "components": components,
        "nets": {},
        "board": {"surface_cutouts": []},
    }


def _domain_constraint(a: str, b: str, margin: float = 8.0, cid: str | None = None) -> SeparatedConstraint:
    return SeparatedConstraint(
        a=a,
        b=b,
        min_distance_mm=margin,
        tier=ConstraintTier.HARD,
        id=cid or f"domain_clearance_{a}_{b}",
        because=f"test {a}<->{b} at {margin}mm",
    )


_VD = {"ac_l": VoltageDomain.MAINS, "gnd": VoltageDomain.LV_CONTROL}


def _run_both(constraints, positions, rotations, placement, vd, netlist=None):
    """Drive IDENTICAL inputs through the delegated shim (Rust) and the
    oracle audit; return (delegated, oracle)."""
    delegated = _shim.audit_domain_clearance_validator(
        constraints, positions, rotations, placement, vd, netlist
    )
    oracle = _oracle.audit_domain_clearance_validator(
        constraints, positions, rotations, placement, vd, netlist
    )
    return delegated, oracle


# ---------------------------------------------------------------------------
# Canonicalization (NaN-aware; dicts by sorted key; floats by .hex())
# ---------------------------------------------------------------------------


def _fnum(x):
    if x is None:
        return None
    if isinstance(x, float) and math.isnan(x):
        return "nan"
    return float(x).hex()


def _canon_value(v):
    if isinstance(v, dict):
        return tuple(sorted((k, _canon_value(x)) for k, x in v.items()))
    if isinstance(v, (list, tuple)):
        return tuple(_canon_value(x) for x in v)
    if isinstance(v, float):
        return _fnum(v)
    return repr(v)


def _canon_violation(v):
    return (
        v.ref_a,
        v.ref_b,
        v.boundary,
        v.insulation_type,
        v.metric,
        _fnum(v.measured_mm),
        _fnum(v.required_mm),
        v.pair_kind,
        v.closest_pads,
        v.reason,
    )


def _canon_audit(a):
    return (
        tuple(_canon_violation(v) for v in a.hard_failures),
        tuple(_canon_violation(v) for v in a.intra_footprint),
        tuple(_canon_violation(v) for v in a.coverage_gaps),
        a.covered_pair_count,
        a.validator_violation_count,
        _canon_value(a.stats),
        a.geometry_trusted,
    )


# ---------------------------------------------------------------------------
# Direct differentials through the REAL validator
# ---------------------------------------------------------------------------

_SCENARIOS = {}


def _scenario(name):
    def deco(fn):
        _SCENARIOS[name] = fn
        return fn

    return deco


@_scenario("falsifier_hard")
def _falsifier():
    """The minimized run-B lie: centers 8.1mm apart (>= the 8.0mm bar) but
    pad copper reaches to a 0.1mm exact gap -> 4 HARD records on the
    constraint-covered A/B pair."""
    placement = _placement(
        [
            {"ref": "A", "position": (0.0, 0.0), "nets": ["ac_l"], "rotation_deg": 0.0,
             "pads": [_pad("ac_l", (3.0, 0.0))]},
            {"ref": "B", "position": (8.1, 0.0), "nets": ["gnd"], "rotation_deg": 0.0,
             "pads": [_pad("gnd", (-3.0, 0.0))]},
        ]
    )
    return [_domain_constraint("A", "B")], {"A": (0.0, 0.0), "B": (8.1, 0.0)}, {"A": 0, "B": 0}, placement


@_scenario("clean")
def _clean():
    placement = _placement(
        [
            {"ref": "A", "position": (0.0, 0.0), "nets": ["ac_l"], "rotation_deg": 0.0,
             "pads": [_pad("ac_l", (0.0, 0.0), width=1.0)]},
            {"ref": "B", "position": (20.0, 0.0), "nets": ["gnd"], "rotation_deg": 0.0,
             "pads": [_pad("gnd", (0.0, 0.0), width=1.0)]},
        ]
    )
    return [_domain_constraint("A", "B")], {"A": (0.0, 0.0), "B": (20.0, 0.0)}, {"A": 0, "B": 0}, placement


@_scenario("straddler_intra")
def _straddler():
    """One component whose OWN pads straddle a domain boundary (pad1 ac_l,
    pad2 gnd) -> intra-footprint bucket, never hard."""
    placement = _placement(
        [
            {"ref": "S", "position": (0.0, 0.0), "nets": ["ac_l"], "rotation_deg": 0.0,
             "pads": [_pad("ac_l", (-2.0, 0.0)), _pad("gnd", (2.0, 0.0))]},
        ]
    )
    return [], {"S": (0.0, 0.0)}, {"S": 0}, placement


@_scenario("coverage_gap")
def _gap():
    """A violating pair with NO constraint -> coverage_gaps bucket."""
    placement = _placement(
        [
            {"ref": "A", "position": (0.0, 0.0), "nets": ["ac_l"], "rotation_deg": 0.0,
             "pads": [_pad("ac_l", (3.0, 0.0))]},
            {"ref": "B", "position": (5.0, 0.0), "nets": ["gnd"], "rotation_deg": 0.0,
             "pads": [_pad("gnd", (-3.0, 0.0))]},
        ]
    )
    return [], {"A": (0.0, 0.0), "B": (5.0, 0.0)}, {"A": 0, "B": 0}, placement


@_scenario("reversed_pair_ordering")
def _reversed():
    """Validator emits (B, A) against a constraint ordered (a=A, b=B):
    frozenset membership absorbs it into hard, never a gap."""
    placement = _placement(
        [
            {"ref": "B", "position": (0.0, 0.0), "nets": ["ac_l"], "rotation_deg": 0.0,
             "pads": [_pad("ac_l", (3.0, 0.0))]},
            {"ref": "A", "position": (8.1, 0.0), "nets": ["gnd"], "rotation_deg": 0.0,
             "pads": [_pad("gnd", (-3.0, 0.0))]},
        ]
    )
    return [_domain_constraint("A", "B")], {"B": (0.0, 0.0), "A": (8.1, 0.0)}, {"B": 0, "A": 0}, placement


@_scenario("degraded_geometry")
def _degraded():
    """Component X carries NO pads -> validator models it as a zero-extent
    point; geometry_trusted False + logger.error; the (X, B) pair is still
    measured origin-to-origin (pairs_origin_modelled > 0)."""
    placement = _placement(
        [
            {"ref": "X", "position": (0.0, 0.0), "nets": ["ac_l"], "rotation_deg": 0.0},
            {"ref": "B", "position": (3.0, 0.0), "nets": ["gnd"], "rotation_deg": 0.0,
             "pads": [_pad("gnd", (0.0, 0.0), width=1.0)]},
        ]
    )
    return [_domain_constraint("X", "B")], {"X": (0.0, 0.0), "B": (3.0, 0.0)}, {"X": 0, "B": 0}, placement


@pytest.mark.parametrize("name", sorted(_SCENARIOS), ids=sorted(_SCENARIOS))
def test_real_validator_differential(name):
    """Every scenario: delegated (Rust) and oracle audits must be
    canonical-identical, and each scenario must land in its expected bucket
    (the non-vacuity guard -- a scenario whose audit is empty everywhere
    proves nothing)."""
    constraints, positions, rotations, placement = _SCENARIOS[name]()
    delegated, oracle = _run_both(constraints, positions, rotations, placement, _VD)
    assert _canon_audit(delegated) == _canon_audit(oracle), (
        f"[{name}] audit diverged:\n  delegated={_canon_audit(delegated)}\n  oracle={_canon_audit(oracle)}"
    )
    # Per-scenario non-vacuity: the right bucket must be non-empty.
    if name == "falsifier_hard":
        assert delegated.hard_failures and not delegated.intra_footprint and not delegated.coverage_gaps
    elif name == "clean":
        assert not delegated.hard_failures and not delegated.coverage_gaps and delegated.clean
    elif name == "straddler_intra":
        assert delegated.intra_footprint and not delegated.hard_failures
    elif name == "coverage_gap":
        assert delegated.coverage_gaps and not delegated.hard_failures
    elif name == "reversed_pair_ordering":
        assert delegated.hard_failures and not delegated.coverage_gaps
    elif name == "degraded_geometry":
        assert delegated.geometry_trusted is False and "X" in delegated.stats.get("components_without_pads", [])


def test_value_error_parity_empty_placement():
    placement = _placement([])
    with pytest.raises(ValueError) as de:
        _shim.audit_domain_clearance_validator([], {"A": (0.0, 0.0)}, {}, placement, _VD)
    with pytest.raises(ValueError) as oe:
        _oracle.audit_domain_clearance_validator([], {"A": (0.0, 0.0)}, {}, placement, _VD)
    assert str(de.value) == str(oe.value)
    assert "zero components" in str(de.value)


def test_value_error_parity_disjoint_refs():
    placement = _placement(
        [
            {"ref": "A", "position": (0.0, 0.0), "nets": ["ac_l"], "rotation_deg": 0.0,
             "pads": [_pad("ac_l", (0.0, 0.0))]},
        ]
    )
    with pytest.raises(ValueError) as de:
        _shim.audit_domain_clearance_validator([], {"Z": (1.0, 1.0)}, {}, placement, _VD)
    with pytest.raises(ValueError) as oe:
        _oracle.audit_domain_clearance_validator([], {"Z": (1.0, 1.0)}, {}, placement, _VD)
    assert str(de.value) == str(oe.value)
    assert "no overlap" in str(de.value)


# ---------------------------------------------------------------------------
# Mocked-validator edge cases (the fallbacks the real validator never emits)
# ---------------------------------------------------------------------------


def _run_mocked(violations, stats=None, covered=True):
    """Script BOTH arms through the same fake validator returning
    *violations* / *stats*; the constraint set covers the A-B pair only
    when *covered*. Record each arm's validator_placement argument.
    Return (delegated, oracle, delegated_calls, oracle_calls)."""
    import temper_placer.requirements.validators.clearance as _clearance_mod

    delegated_calls: list = []
    oracle_calls: list = []

    def fake_delegated(vp, vd):
        delegated_calls.append(vp)
        return SimpleNamespace(violations=violations, stats=stats or {})

    def fake_oracle(vp, vd):
        oracle_calls.append(vp)
        return SimpleNamespace(violations=violations, stats=stats or {})

    monkeypatch = pytest.MonkeyPatch()
    try:
        monkeypatch.setattr(_clearance_mod, "verify_iec60335_compliance", fake_delegated)
        monkeypatch.setattr(_oracle, "verify_iec60335_compliance", fake_oracle)
        placement = _placement(
            [
                {"ref": "A", "position": (0.0, 0.0), "nets": ["ac_l"], "rotation_deg": 0.0,
                 "pads": [_pad("ac_l", (0.0, 0.0), width=1.0)]},
                {"ref": "B", "position": (10.0, 0.0), "nets": ["gnd"], "rotation_deg": 0.0,
                 "pads": [_pad("gnd", (0.0, 0.0), width=1.0)]},
            ]
        )
        constraints = [_domain_constraint("A", "B")] if covered else []
        positions = {"A": (0.0, 0.0), "B": (10.0, 0.0)}
        rotations = {"A": 0, "B": 0}
        delegated = _shim.audit_domain_clearance_validator(
            constraints, positions, rotations, placement, _VD
        )
        oracle = _oracle.audit_domain_clearance_validator(
            constraints, positions, rotations, placement, _VD
        )
        return delegated, oracle, delegated_calls, oracle_calls
    finally:
        monkeypatch.undo()


def _violation(
    ref_a="A",
    ref_b="B",
    boundary="MAINS-LV",
    insulation_type=None,
    metric="clearance",
    measured_mm=1.5,
    required_mm=3.0,
    pair_kind="inter",
    closest_pads=None,
):
    return SimpleNamespace(
        ref_a=ref_a,
        ref_b=ref_b,
        boundary=boundary,
        insulation_type=insulation_type,
        metric=metric,
        measured_mm=measured_mm,
        required_mm=required_mm,
        pair_kind=pair_kind,
        closest_pads=closest_pads,
    )


_INS_BASIC = SimpleNamespace(value="BASIC")


def test_mocked_falsy_pair_kind_none_refs_is_intra():
    """pair_kind=None AND ref_a=None AND ref_b=None: the oracle's fallback is
    ``("intra" if v.ref_a == v.ref_b else "inter")`` on the ORIGINAL values
    -- None == None is True, so the record is intra. The port must not
    compare the \"?\" defaults (identity) and answer inter."""
    d, o, dc, oc = _run_mocked([_violation(ref_a=None, ref_b=None, pair_kind=None)])
    assert _canon_audit(d) == _canon_audit(o)
    assert len(d.intra_footprint) == 1 and d.intra_footprint[0].pair_kind == "intra"
    assert d.intra_footprint[0].ref_a == "?" and d.intra_footprint[0].ref_b == "?"
    # Call-argument parity: the Rust arm hands the boundary the same geometry.
    assert _canon_value(dc[0]) == _canon_value(oc[0])


def test_mocked_falsy_pair_kind_equal_value_refs_is_intra():
    """pair_kind=None with ref_a == ref_b == \"U1\" (equal VALUES): intra by
    value equality, not object identity."""
    d, o, _, _ = _run_mocked([_violation(ref_a="U1", ref_b="U1", pair_kind="")])
    assert _canon_audit(d) == _canon_audit(o)
    assert len(d.intra_footprint) == 1 and d.intra_footprint[0].pair_kind == "intra"


def test_mocked_falsy_pair_kind_covered_pair_is_hard_with_formatted_reason():
    """pair_kind=None with a covered pair: hard bucket, and the reason must
    render ``{measured_mm:.3f}mm < {required_mm}mm`` bit-identically (the
    CPython format path)."""
    d, o, _, _ = _run_mocked([_violation(pair_kind=None, measured_mm=1.23456, required_mm=3.0)])
    assert _canon_audit(d) == _canon_audit(o)
    assert len(d.hard_failures) == 1 and d.hard_failures[0].pair_kind == "inter"
    assert "measures 1.235mm copper-to-copper < 3.0mm required" in d.hard_failures[0].reason


def test_mocked_none_measurements_gap_bucket_uses_nan():
    """measured_mm=None / required_mm=None on an UNCOVERED pair: no reason
    formatting, so no raise -- the record carries nan for both (the oracle's
    ``if v.measured_mm is not None else float(\"nan\")``)."""
    d, o, _, _ = _run_mocked(
        [_violation(measured_mm=None, required_mm=None)], covered=False
    )
    assert _canon_audit(d) == _canon_audit(o)
    assert len(d.coverage_gaps) == 1
    assert math.isnan(d.coverage_gaps[0].measured_mm) and math.isnan(d.coverage_gaps[0].required_mm)
    assert d.coverage_gaps[0].pair_kind == "inter"


def test_mocked_none_measurements_covered_pair_raises_in_both():
    """measured_mm=None on a COVERED pair: the hard reason's ``:.3f`` format
    raises TypeError in the oracle -- the port must raise identically, not
    silently produce a different reason. The audit's own construction would
    have mapped None -> nan, but the REASON is built from the RAW violation
    first, so both arms raise before any record is constructed."""
    import temper_placer.requirements.validators.clearance as _clearance_mod

    placement = _placement(
        [
            {"ref": "A", "position": (0.0, 0.0), "nets": ["ac_l"], "rotation_deg": 0.0,
             "pads": [_pad("ac_l", (0.0, 0.0), width=1.0)]},
            {"ref": "B", "position": (10.0, 0.0), "nets": ["gnd"], "rotation_deg": 0.0,
             "pads": [_pad("gnd", (0.0, 0.0), width=1.0)]},
        ]
    )
    constraints = [_domain_constraint("A", "B")]
    positions = {"A": (0.0, 0.0), "B": (10.0, 0.0)}
    rotations = {"A": 0, "B": 0}
    monkeypatch = pytest.MonkeyPatch()
    try:
        def bad_measured_fake(vp, vd):
            return SimpleNamespace(
                violations=[_violation(measured_mm=None, required_mm=3.0)], stats={}
            )

        monkeypatch.setattr(_clearance_mod, "verify_iec60335_compliance", bad_measured_fake)
        monkeypatch.setattr(_oracle, "verify_iec60335_compliance", bad_measured_fake)
        with pytest.raises(TypeError):
            _shim.audit_domain_clearance_validator(
                constraints, positions, rotations, placement, _VD
            )
        with pytest.raises(TypeError):
            _oracle.audit_domain_clearance_validator(
                constraints, positions, rotations, placement, _VD
            )
    finally:
        monkeypatch.undo()


def test_mocked_none_insulation_falsy_boundary_metric_defaults():
    """insulation_type=None (-> \"?\"), boundary=\"\" (-> \"?\"), metric
    falsy (-> \"?\"): the record defaults must match the oracle's
    ``or \"?\"`` / ``is not None`` handling."""
    d, o, _, _ = _run_mocked(
        [_violation(insulation_type=None, boundary="", metric="", closest_pads=None)]
    )
    assert _canon_audit(d) == _canon_audit(o)
    hard = d.hard_failures[0]
    assert hard.insulation_type == "?" and hard.boundary == "?" and hard.metric == "?"
    assert hard.closest_pads is None


def test_mocked_insulation_enum_value_extracted():
    """insulation_type carries a .value enum (the real validator's type):
    the record must carry the VALUE, not the enum object."""
    d, o, _, _ = _run_mocked([_violation(insulation_type=_INS_BASIC)])
    assert _canon_audit(d) == _canon_audit(o)
    assert d.hard_failures[0].insulation_type == "BASIC"


def test_mocked_pairs_origin_modelled_none_contributes_zero():
    """A stats row carrying pairs_origin_modelled=None must contribute 0 to
    the origin sum (the oracle's ``int(... or 0)``) -- geometry stays
    trusted when nothing else is degraded."""
    stats = {"rows": [{"pairs_origin_modelled": None}, {"pairs_origin_modelled": 0}]}
    d, o, _, _ = _run_mocked([], stats=stats)
    assert _canon_audit(d) == _canon_audit(o)
    assert d.geometry_trusted is True


def test_mocked_origin_modelled_marks_geometry_untrusted(caplog):
    """A stats row with pairs_origin_modelled=2 marks geometry_trusted False
    and emits the degraded-geometry logger.error through the same logger
    name the oracle module uses."""
    caplog.set_level(logging.INFO)
    stats = {"rows": [{"pairs_origin_modelled": 2}]}
    d, o, _, _ = _run_mocked([], stats=stats)
    assert _canon_audit(d) == _canon_audit(o)
    assert d.geometry_trusted is False
    degraded = [r.getMessage() for r in caplog.records if "DEGRADED geometry" in r.getMessage()]
    assert degraded, "degraded-geometry logger.error not emitted"
    # One from each arm (oracle logger + the port's same-name logger).
    assert len(degraded) >= 1


def test_mocked_summary_log_and_stats_parity(caplog):
    """The post-audit info summary (violation counts) and the raw stats
    capture must be identical, and the summary log must fire."""
    caplog.set_level(logging.INFO)
    stats = {
        "components_without_pads": [],
        "rows": [{"pairs_origin_modelled": 0}],
        "violating_pairs": [("A", "B")],
    }
    d, o, _, _ = _run_mocked([_violation(pair_kind=None, measured_mm=1.0, required_mm=3.0)], stats=stats)
    assert _canon_audit(d) == _canon_audit(o)
    assert d.stats["violating_pairs"] == [("A", "B")]
    summary = [r.getMessage() for r in caplog.records if "post-solve audit:" in r.getMessage()]
    assert summary, "summary info log not emitted"
    assert "1 hard" in summary[0]


# ---------------------------------------------------------------------------
# PBT (5 non-vacuous properties)
# ---------------------------------------------------------------------------


def _random_component(rng, ref, net, center, partner_center, pad_reach=2.0):
    """A two-pad component whose pads reach *toward* the partner -- biases
    the corpus toward real violations (the non-vacuity guard)."""
    dx = partner_center[0] - center[0]
    dy = partner_center[1] - center[1]
    norm = math.hypot(dx, dy) or 1.0
    ux, uy = dx / norm, dy / norm
    pads = [
        _pad(net, (ux * pad_reach, uy * pad_reach), width=1.0, height=1.0),
        _pad(net, (-ux * pad_reach, -uy * pad_reach), width=1.0, height=1.0),
    ]
    return {
        "ref": ref,
        "position": center,
        "nets": [net],
        "rotation_deg": 0.0,
        "pads": pads,
    }


def _random_audit_case(rng, cover_fraction=0.5):
    """A random 4-component placement (2 MAINS, 2 LV) with a random
    constraint subset; returns (constraints, positions, rotations,
    placement)."""
    centers = {
        "A": (rng.uniform(0.0, 20.0), rng.uniform(0.0, 20.0)),
        "B": (rng.uniform(0.0, 20.0), rng.uniform(0.0, 20.0)),
        "C": (rng.uniform(0.0, 20.0), rng.uniform(0.0, 20.0)),
        "D": (rng.uniform(0.0, 20.0), rng.uniform(0.0, 20.0)),
    }
    comps = [
        _random_component(rng, "A", "ac_l", centers["A"], centers["B"]),
        _random_component(rng, "B", "gnd", centers["B"], centers["A"]),
        _random_component(rng, "C", "ac_l", centers["C"], centers["D"]),
        _random_component(rng, "D", "gnd", centers["D"], centers["C"]),
    ]
    pairs = [("A", "B"), ("C", "D"), ("A", "D"), ("C", "B")]
    constraints = [
        _domain_constraint(a, b, margin=rng.choice([3.0, 4.0, 6.0, 8.0]))
        for a, b in pairs
        if rng.random() < cover_fraction
    ]
    rotations = {ref: rng.choice([0, 1, 2, 3]) for ref in centers}
    return constraints, centers, rotations, _placement(comps)


def test_pbt_differential_random_corpus():
    """P1 -- random-corpus differential: for every generated case the
    delegated (Rust) audit is canonical-identical to the oracle audit. The
    corpus is biased (pads reach toward partners in a 20x20 box with
    3-8mm bars) so it MUST land violations in BOTH the hard and the gap
    buckets -- asserted below; a corpus that never did would make this
    differential vacuous."""
    rng = random.Random(20260812)
    hard_cases = 0
    gap_cases = 0
    total = 30
    for _ in range(total):
        constraints, positions, rotations, placement = _random_audit_case(rng)
        delegated, oracle = _run_both(constraints, positions, rotations, placement, _VD)
        assert _canon_audit(delegated) == _canon_audit(oracle), (
            f"corpus case diverged:\n  delegated={_canon_audit(delegated)}\n  oracle={_canon_audit(oracle)}"
        )
        hard_cases += bool(delegated.hard_failures)
        gap_cases += bool(delegated.coverage_gaps)
    # Non-vacuity: the corpus exercises the hard AND gap dispatch paths.
    assert hard_cases >= 5, f"corpus too clean: only {hard_cases} hard cases"
    assert gap_cases >= 5, f"corpus too clean: only {gap_cases} gap cases"


def test_pbt_hard_implies_covered_pair():
    """P2 -- classification soundness on the DELEGATED arm: every hard
    failure's pair is in the constraint-covered pair set, every coverage
    gap's pair is not (the solver-validator pair-set alignment invariant).
    Non-vacuous: the corpus above is proven to produce hard AND gap cases."""
    rng = random.Random(20260813)
    saw_hard = saw_gap = 0
    for _ in range(30):
        constraints, positions, rotations, placement = _random_audit_case(rng)
        audit = _shim.audit_domain_clearance_validator(
            constraints, positions, rotations, placement, _VD
        )
        covered = {frozenset((c.a, c.b)) for c in constraints}
        for v in audit.hard_failures:
            saw_hard += 1
            assert frozenset((v.ref_a, v.ref_b)) in covered, v
        for v in audit.coverage_gaps:
            saw_gap += 1
            assert frozenset((v.ref_a, v.ref_b)) not in covered, v
    assert saw_hard >= 5 and saw_gap >= 5


def test_pbt_intra_never_hard():
    """P3 -- bucket discipline: an intra-footprint violation (pair_kind
    intra or ref_a == ref_b) lands in intra_footprint, never hard/gap. The
    straddler scenario guarantees the path is exercised."""
    rng = random.Random(20260814)
    saw_intra = 0
    for _ in range(20):
        constraints, positions, rotations, placement = _random_audit_case(rng)
        # Inject a mixed-domain straddler component into the placement.
        placement["components"].append(
            {
                "ref": "S", "position": (rng.uniform(0.0, 20.0), rng.uniform(0.0, 20.0)),
                "nets": ["ac_l"], "rotation_deg": 0.0,
                "pads": [_pad("ac_l", (-2.0, 0.0)), _pad("gnd", (2.0, 0.0))],
            }
        )
        positions["S"] = placement["components"][-1]["position"]
        rotations["S"] = 0
        audit = _shim.audit_domain_clearance_validator(
            constraints, positions, rotations, placement, _VD
        )
        for v in audit.intra_footprint:
            saw_intra += 1
            assert v.pair_kind == "intra" or v.ref_a == v.ref_b
        for v in audit.hard_failures + audit.coverage_gaps:
            assert not (v.pair_kind == "intra" or v.ref_a == v.ref_b)
    assert saw_intra >= 1, "straddler never produced an intra record -- vacuous P3"


def test_pbt_geometry_trusted_iff_all_pads():
    """P4 -- geometry-trust invariant: every component carrying pads =>
    geometry_trusted True (origin-modelled pairs require a pad-less
    component). Non-vacuous via the degraded scenario + the pad-less
    injection below (which MUST flip trust to False)."""
    rng = random.Random(20260815)
    for _ in range(20):
        constraints, positions, rotations, placement = _random_audit_case(rng)
        audit = _shim.audit_domain_clearance_validator(
            constraints, positions, rotations, placement, _VD
        )
        assert audit.geometry_trusted is True, (
            f"all pads present but geometry_trusted={audit.geometry_trusted}: {audit.stats}"
        )
    # Pad-less injection flips trust (the degraded path).
    constraints, positions, rotations, placement = _random_audit_case(rng)
    placement["components"].append(
        {"ref": "N", "position": (10.0, 10.0), "nets": ["ac_l"], "rotation_deg": 0.0}
    )
    positions["N"] = (10.0, 10.0)
    audit = _shim.audit_domain_clearance_validator(
        constraints, positions, rotations, placement, _VD
    )
    assert audit.geometry_trusted is False
    assert "N" in audit.stats.get("components_without_pads", [])


def test_pbt_covered_pair_count_matches_constraint_set():
    """P5 -- the covered_pair_count diagnostic equals the number of DISTINCT
    str-str pairs in the constraint set (constraint duplication collapses),
    on both arms. Non-vacuous: duplicate + reversed constraints are injected
    so a naive len(constraints) count would diverge."""
    rng = random.Random(20260816)
    for _ in range(20):
        constraints, positions, rotations, placement = _random_audit_case(rng, cover_fraction=1.0)
        # Inject duplicates and reversed-order duplicates.
        base = list(constraints)
        constraints = base + [_domain_constraint(c.a, c.b, margin=c.min_distance_mm) for c in base]
        constraints += [_domain_constraint(c.b, c.a, margin=c.min_distance_mm) for c in base]
        delegated, oracle = _run_both(constraints, positions, rotations, placement, _VD)
        assert _canon_audit(delegated) == _canon_audit(oracle)
        distinct = {frozenset((c.a, c.b)) for c in constraints}
        assert delegated.covered_pair_count == len(distinct), (
            f"covered_pair_count {delegated.covered_pair_count} != distinct pairs {len(distinct)}"
        )
        assert delegated.covered_pair_count == oracle.covered_pair_count


# ---------------------------------------------------------------------------
# Metamorphic relations (4)
# ---------------------------------------------------------------------------


def _meta_base_case():
    """A 4-component line layout with guaranteed violating pair sets:
    (A,B) and (C,D) covered (hard-capable) while (B,C) is uncovered but
    still violates (gap-capable). Every component carries two pads at
    +/-2mm on x so copper reaches toward both neighbours.

    Positions: A=0, B=5, C=13, D=15 (mm). Copper gaps: A-B 1mm, C-D 2mm
    (covered -> HARD); B-C 4mm (uncovered -> GAP) -- all below the
    MAINS/LV bars (3.0/4.0/6.0/8.0). The B-D LV-LV pair is 10mm apart
    (non-violating at the 0.5/1.0mm LV-LV bars) and the A-D / A-C cross
    pairs are >= 13mm apart (non-violating) -- this matters for the
    domain-role-swap relation M4: the validator measures LV-LV pairs but
    not HV-HV pairs, so a same-domain pair close enough to violate would
    break swap invariance. B-D is far enough that the swap leaves both
    arms silent on it."""
    return (
        [_domain_constraint("A", "B"), _domain_constraint("C", "D")],
        {"A": (0.0, 0.0), "B": (5.0, 0.0), "C": (13.0, 0.0), "D": (15.0, 0.0)},
        {"A": 0, "B": 0, "C": 0, "D": 0},
        _placement(
            [
                {"ref": "A", "position": (0.0, 0.0), "nets": ["ac_l"], "rotation_deg": 0.0,
                 "pads": [_pad("ac_l", (-2.0, 0.0)), _pad("ac_l", (2.0, 0.0))]},
                {"ref": "B", "position": (5.0, 0.0), "nets": ["gnd"], "rotation_deg": 0.0,
                 "pads": [_pad("gnd", (-2.0, 0.0)), _pad("gnd", (2.0, 0.0))]},
                {"ref": "C", "position": (13.0, 0.0), "nets": ["ac_l"], "rotation_deg": 0.0,
                 "pads": [_pad("ac_l", (-2.0, 0.0)), _pad("ac_l", (2.0, 0.0))]},
                {"ref": "D", "position": (15.0, 0.0), "nets": ["gnd"], "rotation_deg": 0.0,
                 "pads": [_pad("gnd", (-2.0, 0.0)), _pad("gnd", (2.0, 0.0))]},
            ]
        ),
    )


def test_meta_constraint_order_irrelevant():
    """M1 -- reversing the constraint list order does not change the audit:
    coverage is a pair-set property."""
    constraints, positions, rotations, placement = _meta_base_case()
    a1 = _shim.audit_domain_clearance_validator(constraints, positions, rotations, placement, _VD)
    a2 = _shim.audit_domain_clearance_validator(
        list(reversed(constraints)), positions, rotations, placement, _VD
    )
    assert _canon_audit(a1) == _canon_audit(a2)
    assert a1.hard_failures and a1.coverage_gaps  # the base case is live


def test_meta_unrelated_constraint_additive():
    """M2 -- adding an UNRELATED constraint (a pair with no components in
    the placement) leaves every bucket unchanged and increments
    covered_pair_count by exactly one."""
    constraints, positions, rotations, placement = _meta_base_case()
    a1 = _shim.audit_domain_clearance_validator(constraints, positions, rotations, placement, _VD)
    a2 = _shim.audit_domain_clearance_validator(
        constraints + [_domain_constraint("Z", "W")], positions, rotations, placement, _VD
    )
    assert _canon_audit(a1)[:3] == _canon_audit(a2)[:3]  # buckets identical
    assert a2.covered_pair_count == a1.covered_pair_count + 1
    assert a2.validator_violation_count == a1.validator_violation_count


def test_meta_translation_invariance():
    """M3 -- translating the whole placement by (dx, dy) preserves the
    copper geometry, so the audit is invariant (buckets, counts, trust)."""
    constraints, positions, rotations, placement = _meta_base_case()
    a1 = _shim.audit_domain_clearance_validator(constraints, positions, rotations, placement, _VD)
    dx, dy = 12.5, -7.25
    translated = _placement(
        [
            {**c, "position": (c["position"][0] + dx, c["position"][1] + dy)}
            for c in placement["components"]
        ]
    )
    t_positions = {ref: (x + dx, y + dy) for ref, (x, y) in positions.items()}
    a2 = _shim.audit_domain_clearance_validator(
        constraints, t_positions, rotations, translated, _VD
    )
    assert _canon_audit(a1) == _canon_audit(a2)
    assert a1.hard_failures and a1.coverage_gaps


def test_meta_domain_role_swap_absorbs_reversed():
    """M4 -- swapping which side is MAINS vs LV_CONTROL reverses the
    validator's pair emission; frozenset coverage must absorb it: the same
    buckets with ref_a/ref_b swapped per violation."""
    constraints, positions, rotations, placement = _meta_base_case()
    a1 = _shim.audit_domain_clearance_validator(constraints, positions, rotations, placement, _VD)
    swapped = _placement(
        [
            {**c, "nets": ["gnd" if c["nets"][0] == "ac_l" else "ac_l"],
             "pads": [_pad("gnd" if p["net"] == "ac_l" else "ac_l", p["offset"], p["width"], p["height"])
                      for p in c["pads"]]}
            for c in placement["components"]
        ]
    )
    a2 = _shim.audit_domain_clearance_validator(constraints, positions, rotations, swapped, _VD)

    def _pair_key(audit, bucket):
        # Order-insensitive per-violation key: the validator's pair emission
        # reverses under the swap, so compare by pair-set + measured values,
        # not by the ordered refs / order-embedded closest-pads strings
        # (those renderings are pinned bit-identically by the direct
        # differentials, where both arms share the emission order).
        return sorted(
            (tuple(sorted((v.ref_a, v.ref_b))), v.boundary, v.insulation_type, v.metric,
             _fnum(v.measured_mm), _fnum(v.required_mm), v.pair_kind)
            for v in getattr(audit, bucket)
        )

    assert _pair_key(a1, "hard_failures") == _pair_key(a2, "hard_failures")
    assert _pair_key(a1, "coverage_gaps") == _pair_key(a2, "coverage_gaps")
    assert _pair_key(a1, "intra_footprint") == _pair_key(a2, "intra_footprint")
    assert a1.covered_pair_count == a2.covered_pair_count
    assert a1.validator_violation_count == a2.validator_violation_count
    assert a1.geometry_trusted == a2.geometry_trusted
    assert a1.hard_failures and a1.coverage_gaps
