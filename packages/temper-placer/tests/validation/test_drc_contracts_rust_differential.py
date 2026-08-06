"""Differential test: drc_types / drc_result contract pyclasses in Rust
(temper-drc-rs) vs the pinned Python oracles.

Wave 4, **Phase 2** (contracts land earlier than the Phase-4 validation
compute; the verdict note in ``docs/wave4-verdicts.yaml``). The pyo3
pyclasses in ``packages/temper-drc-rs/src/drc_contracts.rs`` must reproduce
the pre-migration ``temper_placer/validation/drc_types.py`` and
``temper_placer/validation/drc_result.py`` bit-identically. Those
implementations are pinned VERBATIM as the oracles
(``_drc_types_py_oracle.py`` / ``_drc_result_py_oracle.py``, commit
``17553437d``).

The contract-migration conventions (#724 board/netlist, #715 constraints)
apply: construction with identical kwargs, field parity including
None-vs-empty and int-vs-float leaf types, ``__eq__``/``__repr__``/``__str__``
byte-parity, mutation vs frozen semantics, iteration, dict conversion. See
``packages/temper-drc-rs/VERIFICATION.md`` for the structural proof.

The consumer-semantics audit is pinned here in two layers:

* the direct differential (this file) — construction + field round-trip +
  repr/str/eq + mutation + ``to_dict`` + the RunResult/CheckResult access
  patterns the #717/#761 shims and ``drc_oracle``/``drc_runner`` use
  (iteration, attribute reads, dict conversion, json serialization,
  severity surface); and
* the existing #717 differentials + #761 suites, which drive the contract
  objects through the delegation shims end-to-end and must stay green
  unchanged (``test_drc_runner_rust_differential.py``,
  ``test_drc_oracle_rust_differential.py``, ``test_drc_fence_rust_differential.py``,
  ``test_drc_rust_differential.py``, the report differentials).

Each corpus entry is stored RAW (only scalars / tuples / lists / dicts);
``pack`` resolves the nested contract values against the chosen side so the
oracle side holds oracle dataclasses and the Rust side holds Rust
pyclasses — the repr of a Rust ``Issue`` holding a Rust ``Location`` is
compared against the oracle ``Issue`` holding an oracle ``Location``.
"""

from __future__ import annotations

import json
import random

import pytest
import temper_drc_rs as _tdrc
from hypothesis import given, settings
from hypothesis import strategies as st

# Rust symbols under test -- must exist or this file fails to collect (RED).
RS_SEVERITY = _tdrc.Severity
RS_LOCATION = _tdrc.Location
RS_ISSUE = _tdrc.Issue
RS_CHECK_RESULT = _tdrc.CheckResult
RS_RUN_RESULT = _tdrc.RunResult
RS_COMPONENT_PLACEMENT = _tdrc.ComponentPlacement
RS_PLACEMENT = _tdrc.Placement
RS_CLEARANCE_RULE = _tdrc.ClearanceRule
RS_ZONE_DEFINITION = _tdrc.ZoneDefinition
RS_LOOP_CONSTRAINT = _tdrc.LoopConstraint
RS_THERMAL_CONSTRAINT = _tdrc.ThermalConstraint
RS_GROUP_CONSTRAINT = _tdrc.GroupConstraint
RS_CONSTRAINT_SET = _tdrc.ConstraintSet
RS_VIA = _tdrc.Via
RS_VIA_PLACEMENT = _tdrc.ViaPlacement
RS_TRACE_SEGMENT = _tdrc.TraceSegment
RS_TRACE_PLACEMENT = _tdrc.TracePlacement

import tests.validation._drc_result_py_oracle as _result_oracle
import tests.validation._drc_types_py_oracle as _types_oracle
from tests.validation._drc_contract_canon import canon

_SEV = _result_oracle.Severity
_RS_SEV = {"INFO": RS_SEVERITY.INFO, "WARNING": RS_SEVERITY.WARNING,
           "ERROR": RS_SEVERITY.ERROR, "CRITICAL": RS_SEVERITY.CRITICAL}


# ---------------------------------------------------------------------------
# Per-side resolvers for nested contract values.
# ---------------------------------------------------------------------------


def _pack(side, spec):
    """Resolve a RAW spec tree into per-side contract objects."""
    tag = spec[0]
    if tag == "$sev":
        return _SEV[spec[1]] if side == "py" else _RS_SEV[spec[1]]
    if tag == "$loc":
        _, x, y, layer = spec
        return (_result_oracle.Location(x, y, layer) if side == "py"
                else RS_LOCATION(x, y, layer))
    if tag == "$issue":
        _, sev, code, message, category, affected = spec
        return (_result_oracle.Issue(_SEV[sev], code, message, category, "c", affected)
                if side == "py" else
                RS_ISSUE(_RS_SEV[sev], code, message, category, "c", affected))
    if tag == "$comp":
        _, ref, x, y, rot, layer, w, h, nc, vd = spec
        return (_types_oracle.ComponentPlacement(
                    ref, "fp", x, y, rot, layer, w, h, nc, vd) if side == "py"
                else RS_COMPONENT_PLACEMENT(ref, "fp", x, y, rot, layer, w, h, nc, vd))
    if tag == "$rule":
        _, f, t, m, d = spec
        return (_types_oracle.ClearanceRule(f, t, m, d) if side == "py"
                else RS_CLEARANCE_RULE(f, t, m, d))
    if tag == "$zone":
        _, name, bounds, net_classes, components = spec
        return (_types_oracle.ZoneDefinition(name, bounds, net_classes, components)
                if side == "py" else RS_ZONE_DEFINITION(name, bounds, net_classes, components))
    if tag == "$loop":
        _, name, nets, area, weight, desc = spec
        return (_types_oracle.LoopConstraint(name, nets, area, weight, desc) if side == "py"
                else RS_LOOP_CONSTRAINT(name, nets, area, weight, desc))
    if tag == "$thermal":
        _, comps, pref, minsp, maxdist, desc = spec
        return (_types_oracle.ThermalConstraint(
                    comps, pref, minsp, maxdist, desc) if side == "py"
                else RS_THERMAL_CONSTRAINT(comps, pref, minsp, maxdist, desc))
    if tag == "$group":
        _, name, comps, spread, zone, prox, desc = spec
        return (_types_oracle.GroupConstraint(
                    name, comps, spread, zone, prox, desc) if side == "py"
                else RS_GROUP_CONSTRAINT(name, comps, spread, zone, prox, desc))
    if tag == "$via":
        _, pos, fl, tl, diam, drill, net = spec
        return (_types_oracle.Via(pos, fl, tl, diam, drill, net) if side == "py"
                else RS_VIA(pos, fl, tl, diam, drill, net))
    if tag == "$seg":
        _, net, layer, w, start, end = spec
        return (_types_oracle.TraceSegment(net, layer, w, start, end) if side == "py"
                else RS_TRACE_SEGMENT(net, layer, w, start, end))
    raise ValueError(f"unknown spec {spec!r}")


def _resolve(side, value):
    if isinstance(value, (tuple, list)) and value and isinstance(value[0], str) \
            and value[0].startswith("$"):
        if value[0] == "$cr":
            return _pack_check(side, value)
        return _pack(side, value)
    if isinstance(value, dict):
        return {_resolve(side, k): _resolve(side, v) for k, v in value.items()}
    if isinstance(value, tuple):
        return tuple(_resolve(side, v) for v in value)
    if isinstance(value, list):
        return [_resolve(side, v) for v in value]
    return value


# ---------------------------------------------------------------------------
# Construction corpus -- every class, exercising positional vs keyword,
# int-vs-float leaves, None-vs-empty, defaults-vs-explicit, and the full
# severity surface. Values are RAW; ``_resolve`` maps them per side.
# ---------------------------------------------------------------------------

_COMPONENT_ARGS = [
    (("R1", "R_0402", 10.0, 20.0, 90.0, "F.Cu", 1.0, 0.5), {}),
    (("R1", "R_0402", 10, 20, 0, "B.Cu", 1, 0), {}),  # int leaves stay int
    (("C1", "C_0603", -1.5, 2.25, 45.0, "F.Cu", 0.6, 0.3),
     {"net_class": "HighVoltage", "voltage_domain": "HV"}),
    (("Q1", "TO-220", 0.0, 0.0, 0.0, "F.Cu", 10.0, 15.0),
     {"net_class": "Signal", "voltage_domain": None}),
    (("L1", "L_0805", 1e-8, -1e-8, 0.0, "F.Cu", 0.8, 0.8), {}),
]

_PLACEMENT_ARGS = [
    ((), {}),
    (({"X": ("$comp", "R1", 1.0, 2.0, 0.0, "F.Cu", 1.0, 1.0, "Signal", None)},), {}),
    ((), {"components": {"R1": ("$comp", "R1", 1.0, 2.0, 0.0, "F.Cu", 1.0, 1.0,
                                "Signal", None),
                         "C1": ("$comp", "C1", 3.0, 4.0, 90.0, "B.Cu", 2, 2,
                                "Power", None)},
           "nets": {"GND": ["R1", "C1"]},
           "zones": {"Z1": (0.0, 0.0, 5.0, 5.0)},
           "net_classes": {"GND": "Signal"},
           "voltage_domains": {"GND": "LV"}}),
    ((), {"components": {}, "board_width": 100, "board_height": 80}),  # int dims
    ((), {"via_placement": None, "trace_placement": None}),
]

_RULE_ARGS = [
    (("HV", "LV", 6.0), {}),
    (("Signal", "Signal", 0.2, "default"), {}),
    (("*", "HV", 10, "wildcard"), {}),  # int min_mm
    (("A", "B", 0.0), {"description": ""}),
]

_ZONE_ARGS = [
    (("HV_ZONE", (0.0, 0.0, 50.0, 50.0)), {}),
    (("Z", (0, 0, 10, 10)), {"net_classes": ["HighVoltage"], "components": ["Q1"]}),
    (("EMPTY", (1.0, 2.0, 3.0, 4.0)), {}),
]

_LOOP_ARGS = [
    (("crit_loop", ["N1", "N2", "N3"], 120.0), {}),
    (("loop", ["N1"], 1), {"weight": 2.5, "description": "desc"}),  # int area
    (("loop2", [], 0.0), {}),
]

_THERMAL_ARGS = [
    ((["Q1", "Q2"],), {}),
    ((["Q1"],), {"prefer_edge": True, "min_spacing_mm": 2.0,
                 "max_distance_from_edge_mm": 50.0, "description": "hot"}),
    (([],), {}),
]

_GROUP_ARGS = [
    (("snubber", ["Q1", "Q2", "D1"]), {}),
    (("grp", ["A", "B"]), {"max_spread_mm": 25, "zone": "Z1",
                           "proximity_rules": [{"ref": "A", "max_dist": 2.0}],
                           "description": "d"}),
    (("empty", []), {"zone": None}),
]

_VIAS_ARGS = [
    (((5.0, 5.0), "F.Cu", "B.Cu", 0.6, 0.3, "GND"), {}),
    (((1, 2), "In1.Cu", "In2.Cu", 1, 0, "NET"), {}),  # int leaves
]

_CONSTRAINT_SET_ARGS = [
    ((), {}),
    ((), {"clearances": [("$rule", "HV", "LV", 6.0, ""), ("$rule", "*", "*", 0.3, "")],
          "zones": [("$zone", "Z1", (0.0, 0.0, 10.0, 10.0), ["HV"], ["Q1"])],
          "critical_loops": [("$loop", "L1", ["N1"], 100.0, 1.0, "")],
          "net_classes": {"GND": "Signal"},
          "voltage_domains": {"GND": "LV"}}),
    ((), {"hv_clearance_mm": 8, "board_width": 100, "board_height": 80}),
]

_SEGMENT_ARGS = [
    (("GND", "F.Cu", 0.25, (0.0, 0.0), (10.0, 10.0)), {}),
    (("NET", "B.Cu", 1, (0, 0), (3, 4)), {}),  # int leaves
]

_LOCATION_ARGS = [
    ((), {}),
    ((1.25, -2.75, "F.Cu"), {}),
    ((0.0, 0.0, ""), {}),  # layer falsy in __str__
    ((0, 0, "F.Cu"), {}),  # int leaves
    ((None, None, None), {}),
    ((1.0,), {}),
]

_ISSUE_ARGS = [
    ((("$sev", "ERROR"), "DRC_CLR_001", "msg", "drc", "drc_clearance"), {}),
    ((("$sev", "CRITICAL"), "SAF_001", "m", "safety", "check"),
     {"affected_items": ["C1", "C2"],
      "location": ("$loc", 1.0, 2.0, "F.Cu"),
      "details": {"a": 1, "b": [1.5, 2], "c": {"k": "v"}}}),
    ((("$sev", "WARNING"), "X", "m", "erc", "c"), {"affected_items": []}),
    ((("$sev", "INFO"), "I1", "m", "emc", "c"), {"details": {}}),
    ((("$sev", "ERROR"), "C", "m", "drc", "c"), {"constraint_id": "CT-7"}),
    ((("$sev", "ERROR"), "C", "m", "drc", "c"), {"constraint_id": None}),
]

_CHECK_RESULT_ARGS = [
    (("c", True), {}),
    (("c", False), {"issues": [("$issue", "ERROR", "E1", "m", "drc", ["R1"]),
                               ("$issue", "WARNING", "W1", "m", "drc", [])],
                    "metrics": {"min_clearance_mm": 0.2, "overlap_count": 3}}),
    (("c", True), {"elapsed_ms": 1, "metrics": {"k": 0}}),  # int elapsed
    (("c", False), {"issues": []}),
]

_RUN_RESULT_ARGS = [
    ((), {}),
    ((), {"check_results": [("$cr", "a", True, []), ("$cr", "b", False, [])],
          "total_elapsed_ms": 12.5}),
    ((), {"check_results": [], "total_elapsed_ms": 0}),
]

_VIA_PLACEMENT_ARGS = [
    ((), {}),
    ((), {"vias": [("$via", (0.0, 0.0), "F.Cu", "B.Cu", 0.6, 0.3, "GND")]}),
]

_TRACE_PLACEMENT_ARGS = [
    ((), {}),
    ((), {"segments": [("$seg", "N", "F.Cu", 0.2, (0.0, 0.0), (1.0, 1.0))]}),
]


def _pack_check(side, raw):
    """Pack a ``$cr`` CheckResult spec into the chosen side.

    Spec is ``("$cr", name, passed, [issue_specs], [metrics])``; metrics
    defaults to ``{}`` when the 5th element is omitted."""
    name, passed, issue_specs = raw[1], raw[2], raw[3]
    metrics = raw[4] if len(raw) > 4 else {}
    issues = [_resolve(side, spec) for spec in issue_specs]
    if side == "py":
        return _result_oracle.CheckResult(name, passed, issues, 0.0, metrics)
    return RS_CHECK_RESULT(name, passed, issues, 0.0, metrics)


def _resolve_full(side, value):
    if isinstance(value, tuple) and value and isinstance(value[0], str) \
            and value[0] == "$cr":
        return _pack_check(side, value)
    return _resolve(side, value)


def _pair(py_cls, rs_cls, raw_args, raw_kwargs):
    # raw_args is a flat positional-args tuple; resolve each element so a
    # nested ``$sev``/``$loc`` spec tuple stays an element (not the whole
    # arg list).
    args = tuple(_resolve_full("py", a) for a in raw_args)
    kwargs = _resolve_full("py", raw_kwargs)
    rs_args = tuple(_resolve_full("rs", a) for a in raw_args)
    rs_kwargs = _resolve_full("rs", raw_kwargs)
    return py_cls(*args, **kwargs), rs_cls(*rs_args, **rs_kwargs)


# (py_cls, rs_cls, corpus)
_LEAF_CASES = [
    (_result_oracle.Location, RS_LOCATION, _LOCATION_ARGS),
    (_result_oracle.Issue, RS_ISSUE, _ISSUE_ARGS),
    (_result_oracle.CheckResult, RS_CHECK_RESULT, _CHECK_RESULT_ARGS),
    (_result_oracle.RunResult, RS_RUN_RESULT, _RUN_RESULT_ARGS),
    (_types_oracle.ComponentPlacement, RS_COMPONENT_PLACEMENT, _COMPONENT_ARGS),
    (_types_oracle.Placement, RS_PLACEMENT, _PLACEMENT_ARGS),
    (_types_oracle.ClearanceRule, RS_CLEARANCE_RULE, _RULE_ARGS),
    (_types_oracle.ZoneDefinition, RS_ZONE_DEFINITION, _ZONE_ARGS),
    (_types_oracle.LoopConstraint, RS_LOOP_CONSTRAINT, _LOOP_ARGS),
    (_types_oracle.ThermalConstraint, RS_THERMAL_CONSTRAINT, _THERMAL_ARGS),
    (_types_oracle.GroupConstraint, RS_GROUP_CONSTRAINT, _GROUP_ARGS),
    (_types_oracle.ConstraintSet, RS_CONSTRAINT_SET, _CONSTRAINT_SET_ARGS),
    (_types_oracle.Via, RS_VIA, _VIAS_ARGS),
    (_types_oracle.TraceSegment, RS_TRACE_SEGMENT, _SEGMENT_ARGS),
]

_COLLECTION_CASES = [
    (_types_oracle.ViaPlacement, RS_VIA_PLACEMENT, _VIA_PLACEMENT_ARGS),
    (_types_oracle.TracePlacement, RS_TRACE_PLACEMENT, _TRACE_PLACEMENT_ARGS),
]


# ---------------------------------------------------------------------------
# Construction + field round-trip + repr/str
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "py_cls,rs_cls,corpus",
    _LEAF_CASES,
    ids=[c[0].__name__ for c in _LEAF_CASES],
)
def test_construction_field_repr_str_identical(py_cls, rs_cls, corpus):
    """Construction with identical args (positional and kwargs) must produce
    bit-identical fields, repr AND str."""
    for raw_args, raw_kwargs in corpus:
        py, rs = _pair(py_cls, rs_cls, raw_args, raw_kwargs)
        assert canon(py) == canon(rs), f"{py_cls.__name__}{raw_args} {raw_kwargs}"
        assert repr(py) == repr(rs), f"repr mismatch {py_cls.__name__}{raw_args} {raw_kwargs}"
        assert str(py) == str(rs), f"str mismatch {py_cls.__name__}{raw_args} {raw_kwargs}"


@pytest.mark.parametrize(
    "py_cls,rs_cls,corpus",
    _COLLECTION_CASES,
    ids=[c[0].__name__ for c in _COLLECTION_CASES],
)
def test_collection_construction_field_repr_str_identical(py_cls, rs_cls, corpus):
    for raw_args, raw_kwargs in corpus:
        py, rs = _pair(py_cls, rs_cls, raw_args, raw_kwargs)
        assert canon(py) == canon(rs)
        assert repr(py) == repr(rs)
        assert str(py) == str(rs)


@pytest.mark.parametrize(
    "py_cls,rs_cls,corpus",
    _LEAF_CASES,
    ids=[c[0].__name__ for c in _LEAF_CASES],
)
def test_equality_matrix_identical(py_cls, rs_cls, corpus):
    """Equality must agree pairwise across the WHOLE corpus.

    Driving every ordered pair through both sides makes the assertion
    independent of the corpus ordering. Also pins the equal-to-`object()`
    False result."""
    py_matrix, rs_matrix = [], []
    for a, ak in corpus:
        for b, bk in corpus:
            py_matrix.append(_pair(py_cls, rs_cls, a, ak)[0] ==
                             _pair(py_cls, rs_cls, b, bk)[0])
            rs_matrix.append(_pair(py_cls, rs_cls, a, ak)[1] ==
                             _pair(py_cls, rs_cls, b, bk)[1])
    assert py_matrix == rs_matrix
    # Self-equality on the diagonal => non-vacuous.
    assert any(py_matrix) and not all(py_matrix)
    a, ak = corpus[0]
    py, rs = _pair(py_cls, rs_cls, a, ak)
    assert (py == object()) is False
    assert (rs == object()) is False


@pytest.mark.parametrize(
    "py_cls,rs_cls,corpus",
    _COLLECTION_CASES,
    ids=[c[0].__name__ for c in _COLLECTION_CASES],
)
def test_collection_equality_matrix_identical(py_cls, rs_cls, corpus):
    py_matrix, rs_matrix = [], []
    for a, ak in corpus:
        for b, bk in corpus:
            py_matrix.append(_pair(py_cls, rs_cls, a, ak)[0] ==
                             _pair(py_cls, rs_cls, b, bk)[0])
            rs_matrix.append(_pair(py_cls, rs_cls, a, ak)[1] ==
                             _pair(py_cls, rs_cls, b, bk)[1])
    assert py_matrix == rs_matrix


def test_mutation_semantics_identical():
    """The contracts are plain (non-frozen) dataclasses: attribute
    assignment must work on both sides, store the raw object (no coercion —
    an int stays int), and be visible to later reads."""
    py_comp = _types_oracle.ComponentPlacement(
        ref="R1", footprint="fp", x=1.0, y=2.0, rotation=0.0, layer="F.Cu",
        width=1.0, height=1.0)
    rs_comp = RS_COMPONENT_PLACEMENT(
        ref="R1", footprint="fp", x=1.0, y=2.0, rotation=0.0, layer="F.Cu",
        width=1.0, height=1.0)
    for obj in (py_comp, rs_comp):
        obj.net_class = "Power"
        obj.x = 5  # int assignment stays int
    assert canon(py_comp) == canon(rs_comp)
    assert py_comp.x == 5 and rs_comp.x == 5
    assert type(py_comp.x) is type(rs_comp.x) is int

    py_p = _types_oracle.Placement()
    rs_p = RS_PLACEMENT()
    for obj in (py_p, rs_p):
        obj.via_placement = None
        obj.nets = {"GND": ["R1"]}
        obj.board_width = 63.5
    assert canon(py_p) == canon(rs_p)


def test_unhashable_identical():
    """eq=True, frozen=False dataclasses are unhashable with CPython's exact
    message; the pyclasses must raise the same TypeError."""
    for obj in (_result_oracle.Location(1.0, 2.0, "F.Cu"), RS_LOCATION(1.0, 2.0, "F.Cu")):
        with pytest.raises(TypeError, match="unhashable type"):
            hash(obj)


# ---------------------------------------------------------------------------
# Severity surface
# ---------------------------------------------------------------------------


def test_severity_surface_identical():
    """name/value/weight/is_failure/repr/str/ordering/equality/hashability."""
    py_members = [_SEV.INFO, _SEV.WARNING, _SEV.ERROR, _SEV.CRITICAL]
    rs_members = [RS_SEVERITY.INFO, RS_SEVERITY.WARNING, RS_SEVERITY.ERROR,
                  RS_SEVERITY.CRITICAL]
    for py, rs in zip(py_members, rs_members):
        assert rs.name == py.name
        assert rs.value == py.value
        assert type(rs.value) is type(py.value) is int
        assert rs.weight == py.weight
        assert rs.is_failure == py.is_failure
        assert repr(rs) == repr(py)
        assert str(rs) == str(py)
    # Ordering: lt/le agree and only between Severity members.
    for a in py_members:
        for b in py_members:
            ra = _RS_SEV[a.name]
            rb = _RS_SEV[b.name]
            assert (ra < rb) == (a < b), (a, b)
            assert (ra <= rb) == (a <= b), (a, b)
    # Non-member comparisons return NotImplemented -> TypeError, both sides.
    for obj in (RS_SEVERITY.INFO, _SEV.INFO):
        with pytest.raises(TypeError):
            obj < 1  # noqa: B015
    # Members are hashable and compare by value+name.
    assert RS_SEVERITY.ERROR == RS_SEVERITY.ERROR
    assert RS_SEVERITY.ERROR != RS_SEVERITY.WARNING
    assert hash(RS_SEVERITY.INFO) == hash(RS_SEVERITY.INFO)
    # Iteration over a list of members works (dict keys / sorted usage).
    assert sorted([RS_SEVERITY.CRITICAL, RS_SEVERITY.INFO]) == \
        [RS_SEVERITY.INFO, RS_SEVERITY.CRITICAL]
    # Class-level enumeration: the pyo3 `members()` substitute for the
    # Enum's `list(Severity)` (no metaclass hook on pyclasses) yields the
    # same members in the same order as iterating the oracle enum — pinned
    # so the report formatter's severity enumeration cannot silently drift.
    assert [m.name for m in RS_SEVERITY.members()] == \
        [m.name for m in list(_SEV)]
    assert RS_SEVERITY.members() == [RS_SEVERITY.INFO, RS_SEVERITY.WARNING,
                                     RS_SEVERITY.ERROR, RS_SEVERITY.CRITICAL]


# ---------------------------------------------------------------------------
# Consumer semantics -- the #717/#761 access patterns, pinned directly
# ---------------------------------------------------------------------------


def _violation_dict(check_name="drc_clearance", severity="ERROR", code="DRC_CLR_001",
                    message="m", category="drc", affected=None, location=None, details=None):
    return {
        "severity": severity,
        "code": code,
        "message": message,
        "category": category,
        "check_name": check_name,
        "affected_items": affected if affected is not None else ["C1"],
        "location": location,
        "details": details if details is not None else {},
    }


def test_consumer_violations_to_run_result_identical():
    """The #717 consumer path: ``_violations_to_run_result`` builds the
    contract objects. Drive the verbatim oracle (dataclass output) and the
    shim (pyclass output) with identical violation dicts and canon-compare
    the full RunResult surface — attribute reads, list/dict iteration,
    severity.name, location float.hex(), details round-trip."""
    import tests.validation._drc_oracle_py_oracle as _oracle
    from temper_placer.validation.drc_oracle import DRCOracle as ShimOracle

    rng = random.Random(99)
    severities = ["INFO", "WARNING", "ERROR", "CRITICAL", "BOGUS"]
    for _ in range(30):
        vs = []
        for _ in range(rng.randint(0, 8)):
            has_loc = rng.random() < 0.5
            vs.append(
                _violation_dict(
                    check_name=rng.choice(["drc_clearance", "safety_creepage", "emc_loop_area"]),
                    severity=rng.choice(severities),
                    affected=[f"C{rng.randint(0, 20)}" for _ in range(rng.randint(0, 3))],
                    location={"x": rng.uniform(-10, 10), "y": rng.uniform(-10, 10),
                              "layer": "F.Cu"} if has_loc else None,
                    details={"k": rng.uniform(-5, 5)} if rng.random() < 0.3 else {},
                )
            )
        oracle_rr = _oracle.DRCOracle._violations_to_run_result(vs)
        shim_rr = ShimOracle._violations_to_run_result(vs)
        assert canon(oracle_rr) == canon(shim_rr)


def test_consumer_runresult_summary_access_patterns():
    """The #761 + drc_fence access patterns: counts, penalty, fail-closed
    passed, all_issues, by_category/by_severity/issues_for_component, and
    iteration over check_results. Both sides built from identical inputs and
    compared canonically."""
    def build(run_cls, check_cls, issue_cls, sev):
        issues = [
            issue_cls(sev.ERROR, "E1", "bad", "drc", "c", ["R1"]),
            issue_cls(sev.WARNING, "W1", "warn", "drc", "c", ["R1", "R2"]),
            issue_cls(sev.INFO, "I1", "info", "thermal", "c", ["R3"]),
            issue_cls(sev.CRITICAL, "C1", "crit", "safety", "c", []),
        ]
        return run_cls(
            check_results=[
                check_cls("c", False, issues=issues),
                check_cls("empty_ok", True, issues=[]),
                check_cls("warn_only", True,
                          issues=[issue_cls(sev.WARNING, "W2", "w", "drc", "c", [])]),
            ],
            total_elapsed_ms=7.5,
        )

    py_rr = build(_result_oracle.RunResult, _result_oracle.CheckResult,
                  _result_oracle.Issue, _SEV)
    rs_rr = build(RS_RUN_RESULT, RS_CHECK_RESULT, RS_ISSUE, RS_SEVERITY)

    for attr in ("passed", "total_checks", "passed_checks", "failed_checks",
                 "info_count", "warning_count", "error_count", "critical_count",
                 "total_penalty", "total_elapsed_ms"):
        assert getattr(rs_rr, attr) == getattr(py_rr, attr), attr
    assert canon(rs_rr.all_issues) == canon(py_rr.all_issues)
    assert [c.check_name for c in rs_rr.check_results] == \
        [c.check_name for c in py_rr.check_results]
    # empty run fails closed -- the anti-vacuity rule
    assert RS_RUN_RESULT().passed is False
    assert _result_oracle.RunResult().passed is False

    for cat in ("drc", "safety", "thermal", "absent"):
        assert canon(rs_rr.by_category(cat)) == canon(py_rr.by_category(cat)), cat
    for sev in [_SEV.INFO, _SEV.WARNING, _SEV.ERROR, _SEV.CRITICAL]:
        rs_sev = _RS_SEV[sev.name]
        assert canon(rs_rr.by_severity(rs_sev)) == canon(py_rr.by_severity(sev)), sev
    for ref in ("R1", "R2", "R3", "NOPE"):
        assert canon(rs_rr.issues_for_component(ref)) == \
            canon(py_rr.issues_for_component(ref)), ref

    # CheckResult-level access patterns
    rs_c = rs_rr.check_results[0]
    py_c = py_rr.check_results[0]
    for attr in ("info_count", "warning_count", "error_count", "critical_count",
                 "total_issues", "penalty"):
        assert getattr(rs_c, attr) == getattr(py_c, attr), attr
    assert canon(rs_c.merge(rs_c)) == canon(py_c.merge(py_c))
    assert rs_c.merge(rs_c).check_name == py_c.merge(py_c).check_name
    assert rs_c.merge(rs_c).passed == py_c.merge(py_c).passed


def test_consumer_to_dict_and_json_identical():
    """dict conversion (to_dict) and json serialization of the result
    surface — the ``drc_cli``/report/json path."""
    def build(run_cls, check_cls, issue_cls, loc_cls, sev):
        return run_cls(
            check_results=[
                check_cls("c", False, issues=[
                    issue_cls(sev.ERROR, "E1", "m", "drc", "c",
                              ["R1"], loc_cls(1.25, -2.75, "F.Cu"), {"k": 1}, "CT-1"),
                ], metrics={"overlap_count": 2}),
            ],
            total_elapsed_ms=3.0,
        )

    py_rr = build(_result_oracle.RunResult, _result_oracle.CheckResult,
                  _result_oracle.Issue, _result_oracle.Location, _SEV)
    rs_rr = build(RS_RUN_RESULT, RS_CHECK_RESULT, RS_ISSUE, RS_LOCATION, RS_SEVERITY)
    assert json.dumps(rs_rr.to_dict(), sort_keys=True) == \
        json.dumps(py_rr.to_dict(), sort_keys=True)
    assert json.dumps(rs_rr.check_results[0].issues[0].to_dict(), sort_keys=True) == \
        json.dumps(py_rr.check_results[0].issues[0].to_dict(), sort_keys=True)
    assert json.dumps(rs_rr.check_results[0].issues[0].location.to_dict()) == \
        json.dumps(py_rr.check_results[0].issues[0].location.to_dict())


def test_consumer_location_issue_str_identical():
    """The custom __str__ surfaces used by drc_fence / reports."""
    cases = [
        ((1.25, -2.75, "F.Cu"), "(1.25, -2.75) on F.Cu"),
        ((1.0, 2.0, None), "(1.00, 2.00)"),
        ((None, 2.0, "F.Cu"), "unknown"),
        ((0.0, 0.0, ""), "(0.00, 0.00)"),
    ]
    for (x, y, layer), expected in cases:
        py = _result_oracle.Location(x, y, layer)
        rs = RS_LOCATION(x, y, layer)
        assert str(py) == str(rs) == expected, (x, y, layer)

    py_i = _result_oracle.Issue(_SEV.ERROR, "E1", "msg", "drc", "c", ["A", "B", "C", "D"])
    rs_i = RS_ISSUE(RS_SEVERITY.ERROR, "E1", "msg", "drc", "c", ["A", "B", "C", "D"])
    assert str(py_i) == str(rs_i) == "[E1] msg (A, B, C (+1 more))"
    py_s = _result_oracle.Issue(_SEV.INFO, "I9", "m", "drc", "c", [])
    rs_s = RS_ISSUE(RS_SEVERITY.INFO, "I9", "m", "drc", "c", [])
    assert str(py_s) == str(rs_s) == "[I9] m ()"


def test_consumer_metrics_summary_identical():
    """The #761 drc_fence kernel input path: a pyclass-built RunResult's
    check_results feed ``temper_drc_rs.metrics_summary`` exactly as the
    fence builds its payload."""
    issue = _result_oracle.Issue
    check = _result_oracle.CheckResult
    run = _result_oracle.RunResult

    rng = random.Random(0xC0FFEE)
    for _ in range(20):
        checks = []
        for _ in range(rng.randint(0, 6)):
            issues = [issue(rng.choice([_SEV.INFO, _SEV.WARNING, _SEV.ERROR,
                                        _SEV.CRITICAL]), f"C{i}", "m",
                            rng.choice(["erc", "drc", "safety", "emc", "other"]), "c")
                      for i in range(rng.randint(0, 3))]
            metrics = {f"m{k}": rng.choice([rng.uniform(0, 5), rng.randint(0, 3)])
                       for k in range(rng.randint(0, 3))}
            checks.append(check(f"chk{rng.randint(0, 3)}", rng.random() < 0.5,
                                issues, rng.uniform(0, 100), metrics))
        rr = run(checks, rng.uniform(0, 1000))

        # Rust kernel over the dataclass-built objects (the same field reads
        # the fence makes on the pyclass objects after migration).
        rs_payload = _tdrc.metrics_summary(
            [(c.check_name, c.elapsed_ms,
              [i.category for i in c.issues],
              list(c.metrics.items()))
             for c in rr.check_results]
        )

        # Independent Python reference loop (mirrors the pinned fence oracle).
        py_checks_run, py_timings = [], {}
        py_erc = py_drc = py_safety = py_emc = 0
        py_custom = {}
        for c in rr.check_results:
            py_checks_run.append(c.check_name)
            py_timings[c.check_name] = c.elapsed_ms
            for i in c.issues:
                if i.category == "erc":
                    py_erc += 1
                elif i.category == "drc":
                    py_drc += 1
                elif i.category == "safety":
                    py_safety += 1
                elif i.category == "emc":
                    py_emc += 1
            for k, v in c.metrics.items():
                py_custom[k] = py_custom.get(k, 0) + v

        assert rs_payload["checks_run"] == py_checks_run
        assert dict(rs_payload["check_timings"]) == py_timings
        assert (rs_payload["erc_issues"], rs_payload["drc_issues"],
                rs_payload["safety_issues"], rs_payload["emc_issues"]) == \
            (py_erc, py_drc, py_safety, py_emc)
        assert dict(rs_payload["custom_metrics"]) == py_custom


def test_consumer_placement_constraints_marshalling():
    """The drc_runner marshalling reads (comp.layer, comp.x, ...,
    via.position, placement.zones bounds, constraint rule fields) must
    return identical values for pyclass-built objects — the #717
    ``_placement_to_board_dict``/``_constraints_to_dict`` input surface."""
    comp = _types_oracle.ComponentPlacement
    placement = _types_oracle.Placement(
        components={
            "R1": comp("R1", "fp", 1.0, 2.0, 90.0, "B.Cu", 1.0, 1.0, "HighVoltage", "HV"),
        },
        zones={"Z1": (0.0, 0.0, 5.0, 5.0)},
        board_width=100, board_height=80,
    )
    rs_placement = RS_PLACEMENT(
        components={
            "R1": RS_COMPONENT_PLACEMENT("R1", "fp", 1.0, 2.0, 90.0, "B.Cu", 1.0, 1.0,
                                          "HighVoltage", "HV"),
        },
        zones={"Z1": (0.0, 0.0, 5.0, 5.0)},
        board_width=100, board_height=80,
    )
    for p in (placement, rs_placement):
        c = p.components["R1"]
        assert c.layer == "B.Cu"
        assert c.net_class == "HighVoltage"
        assert list(p.zones["Z1"]) == [0.0, 0.0, 5.0, 5.0]
        assert p.get_component("R1") is not None
        assert p.get_component("NOPE") is None
        assert p.get_net_class("GND") == "Signal"
        assert p.get_voltage_domain("GND") is None
        assert p.components_in_zone("Z1") == ["R1"]
        assert p.components_in_zone("NOPE") == []
        assert p.all_pairs() == []  # single component -> no pairs
        assert p.get_component("R1").center == (1.0, 2.0)
        assert p.distance_between("R1", "R1") == 0.0
        assert p.distance_between("R1", "NOPE") is None
        assert p.edge_distance_between("R1", "R1") == 0.0


def test_consumer_constraint_set_methods():
    """ConstraintSet.get_clearance/get_zone/get_loop/get_group + ClearanceRule
    wildcard semantics."""
    rule = _types_oracle.ClearanceRule
    zone = _types_oracle.ZoneDefinition
    loop = _types_oracle.LoopConstraint
    args = {
        "clearances": [rule("HV", "LV", 6.0), rule("*", "*", 0.3)],
        "zones": [zone("Z1", (0.0, 0.0, 10.0, 10.0), ["HV"], ["Q1"])],
        "critical_loops": [loop("L1", ["N1"], 100.0)],
    }
    py_cs = _types_oracle.ConstraintSet(**args)
    rs_cs = RS_CONSTRAINT_SET(**args)
    for cs in (py_cs, rs_cs):
        assert cs.get_clearance("HV", "LV") == 6.0
        assert cs.get_clearance("A", "B") == 0.3  # wildcard rule matches
        assert cs.get_clearance("X", "Y") == 0.3  # "*" rule applies to any pair
        assert cs.get_zone("Z1") is not None
        assert cs.get_zone("NOPE") is None
        assert cs.get_loop("L1") is not None
        assert cs.get_loop("NOPE") is None
        assert cs.get_group("NOPE") is None
    for rule_obj in (rule("HV", "LV", 6.0), RS_CLEARANCE_RULE("HV", "LV", 6.0)):
        assert rule_obj.applies_to("HV", "LV") is True
        assert rule_obj.applies_to("LV", "HV") is True
        assert rule_obj.applies_to("A", "B") is False
    for wild in (rule("*", "LV", 1.0), RS_CLEARANCE_RULE("*", "LV", 1.0)):
        assert wild.applies_to("A", "B") is True


def test_consumer_geometry_accessors_identical():
    """The placement geometry accessors used by deterministic stages: bounds,
    distance, overlap, edge distance, trace length/bounding box, via radius."""
    pa = _types_oracle.ComponentPlacement("A", "fp", 0.0, 0.0, 0.0, "F.Cu", 10.0, 10.0)
    pb = _types_oracle.ComponentPlacement("B", "fp", 20.0, 0.0, 0.0, "F.Cu", 10.0, 10.0)
    ra = RS_COMPONENT_PLACEMENT("A", "fp", 0.0, 0.0, 0.0, "F.Cu", 10.0, 10.0)
    rb = RS_COMPONENT_PLACEMENT("B", "fp", 20.0, 0.0, 0.0, "F.Cu", 10.0, 10.0)
    assert canon(ra.bounds) == canon(pa.bounds)
    assert canon(ra.center) == canon(pa.center)
    assert ra.distance_to(rb) == pa.distance_to(pb)
    assert ra.edge_distance_to(rb) == pa.edge_distance_to(pb)
    assert ra.overlaps(rb) == pa.overlaps(pb)
    assert ra.overlap_area(rb) == pa.overlap_area(pb)
    # Overlapping pair
    pb2 = _types_oracle.ComponentPlacement("B", "fp", 5.0, 0.0, 0.0, "F.Cu", 10.0, 10.0)
    rb2 = RS_COMPONENT_PLACEMENT("B", "fp", 5.0, 0.0, 0.0, "F.Cu", 10.0, 10.0)
    assert ra.overlaps(rb2) == pa.overlaps(pb2) is True
    assert canon(ra.overlap_area(rb2)) == canon(pa.overlap_area(pb2))

    seg_p = _types_oracle.TraceSegment("N", "F.Cu", 0.2, (0.0, 0.0), (3.0, 4.0))
    seg_r = RS_TRACE_SEGMENT("N", "F.Cu", 0.2, (0.0, 0.0), (3.0, 4.0))
    assert seg_r.length == seg_p.length
    assert canon(seg_r.bounding_box) == canon(seg_p.bounding_box)

    via_p = _types_oracle.Via((1.0, 1.0), "F.Cu", "B.Cu", 0.6, 0.3, "GND")
    via_r = RS_VIA((1.0, 1.0), "F.Cu", "B.Cu", 0.6, 0.3, "GND")
    assert via_r.radius == via_p.radius

    vp_p = _types_oracle.ViaPlacement([via_p])
    vp_r = RS_VIA_PLACEMENT([via_r])
    assert vp_r.via_count == vp_p.via_count == 1
    assert canon(vp_r.get_vias_for_net("GND")) == canon(vp_p.get_vias_for_net("GND"))
    assert vp_r.get_vias_for_net("NOPE") == []

    tp_p = _types_oracle.TracePlacement([seg_p])
    tp_r = RS_TRACE_PLACEMENT([seg_r])
    assert tp_r.segment_count == tp_p.segment_count == 1
    assert canon(tp_r.get_segments_for_net("N")) == canon(tp_p.get_segments_for_net("N"))
    assert tp_r.get_segments_for_net("NOPE") == []


def test_consumer_from_dict_to_dict_roundtrip_identical():
    """Placement/ConstraintSet from_dict/to_dict — the drc_cli YAML path and
    the marshalling surface — must agree exactly with the oracles."""
    placement_dict = {
        "components": [
            {"ref": "R1", "footprint": "R_0402", "x": 1.0, "y": 2.0},
            {"ref": "C1", "footprint": "C_0603", "x": 3.0, "y": 4.0,
             "rotation": 45.0, "layer": "B.Cu", "width": 0.6, "height": 0.3,
             "net_class": "Power"},
        ],
        "nets": {"GND": ["R1", "C1"]},
        "zones": [{"name": "Z1", "bounds": [0, 0, 10, 10]}],
        "board_width": 100.0,
        "board_height": 80.0,
        "net_classes": {"GND": "Signal"},
        "voltage_domains": {"GND": "LV"},
    }
    py_p = _types_oracle.Placement.from_dict(placement_dict)
    rs_p = RS_PLACEMENT.from_dict(placement_dict)
    assert canon(py_p) == canon(rs_p)
    assert canon(RS_PLACEMENT.from_dict(RS_PLACEMENT.from_dict(placement_dict).to_dict())) == \
        canon(py_p)

    constraints_dict = {
        "clearances": [
            {"from": "HV", "to": "LV", "clearance_mm": 6.0, "description": "safety"},
            {"from": "A", "to": "B", "clearance_mm": 0.3},
        ],
        "zones": [{"name": "Z1", "bounds": [0, 0, 10, 10], "net_classes": ["HV"],
                   "components": ["Q1"]}],
        "critical_loops": [{"name": "L1", "nets": ["N1"], "max_area_mm2": 100.0,
                            "weight": 1.0, "description": ""}],
        "net_classes": {"GND": "Signal"},
        "voltage_domains": {"GND": "LV"},
        "hv_clearance_mm": 8.0,
        "board": {"width_mm": 100.0, "height_mm": 80.0},
    }
    py_cs = _types_oracle.ConstraintSet.from_dict(constraints_dict)
    rs_cs = RS_CONSTRAINT_SET.from_dict(constraints_dict)
    assert canon(py_cs) == canon(rs_cs)
    # to_dict emits exactly clearances/zones/critical_loops/net_classes/
    # voltage_domains/hv_clearance_mm/board — so the round-trip is exact for
    # a dict that carries only those keys (thermal/groups are NOT emitted,
    # verbatim oracle behaviour).
    assert canon(RS_CONSTRAINT_SET.from_dict(RS_CONSTRAINT_SET.from_dict(
        constraints_dict).to_dict())) == canon(py_cs)

    # thermal/groups are parsed by from_dict identically on both sides.
    full = {**constraints_dict,
            "thermal": [{"components": ["Q1"], "prefer_edge": True}],
            "groups": [{"name": "G1", "components": ["Q1", "Q2"], "max_spread_mm": 25.0}]}
    assert canon(_types_oracle.ConstraintSet.from_dict(full)) == \
        canon(RS_CONSTRAINT_SET.from_dict(full))


# ---------------------------------------------------------------------------
# PBT -- five non-vacuous properties (R1c)
# ---------------------------------------------------------------------------


@settings(max_examples=60, deadline=None)
@given(st.sampled_from(["INFO", "WARNING", "ERROR", "CRITICAL"]))
def test_prop1_severity_weight_table(name):
    """P1: the severity weight table is exactly the documented mapping and
    is_failure marks exactly ERROR and CRITICAL."""
    member = _RS_SEV[name]
    assert member.weight == {"INFO": 0.0, "WARNING": 1.0, "ERROR": 10.0,
                             "CRITICAL": 100.0}[name]
    assert member.is_failure == (name in ("ERROR", "CRITICAL"))
    assert member.name == name


@settings(max_examples=60, deadline=None)
@given(st.lists(st.booleans(), min_size=0, max_size=8))
def test_prop2_run_result_passed_fail_closed(flags):
    """P2: RunResult.passed == (there is at least one check and every check
    passed) — empty runs fail closed (anti-vacuity)."""
    rr = RS_RUN_RESULT([RS_CHECK_RESULT(f"c{i}", f) for i, f in enumerate(flags)], 0.0)
    expected = len(flags) > 0 and all(flags)
    assert rr.passed is expected


@settings(max_examples=60, deadline=None)
@given(st.integers(min_value=0, max_value=6))
def test_prop3_error_count_is_recomputed(n_errors):
    """P3: CheckResult.error_count/critical_count/warning_count are exactly
    recomputed from the issue list's severities (no hidden field)."""
    sev = [RS_SEVERITY.ERROR] * n_errors + [RS_SEVERITY.CRITICAL] * n_errors \
        + [RS_SEVERITY.WARNING] * n_errors
    c = RS_CHECK_RESULT("c", False,
                        [RS_ISSUE(s, "E", "m", "drc", "c") for s in sev], 0.0, {})
    assert c.error_count == n_errors
    assert c.critical_count == n_errors
    assert c.warning_count == n_errors
    assert c.total_issues == 3 * n_errors
    assert c.penalty == n_errors * (10.0 + 100.0 + 1.0)


@settings(max_examples=60, deadline=None)
@given(st.lists(st.floats(min_value=0, max_value=100), min_size=0, max_size=10))
def test_prop4_penalty_is_severity_weighted_sum(items):
    """P4: total_penalty == sum of per-issue severity weights over ALL
    check_results, and is >= 0 (a bare empty run scores 0)."""
    def pick(w):
        return RS_SEVERITY.ERROR if w > 66 else \
            RS_SEVERITY.CRITICAL if w > 33 else RS_SEVERITY.WARNING

    c = RS_CHECK_RESULT("c", True,
                        [RS_ISSUE(pick(w), "E", "m", "drc", "c") for w in items], 0.0, {})
    rr = RS_RUN_RESULT([c], 0.0)
    expected = sum(pick(w).weight for w in items)
    assert rr.total_penalty == expected
    assert rr.total_penalty >= 0.0
    assert RS_RUN_RESULT().total_penalty == 0.0


@settings(max_examples=60, deadline=None)
@given(st.integers(min_value=0, max_value=5), st.integers(min_value=0, max_value=4))
def test_prop5_from_dict_to_dict_preserves_constraint_leaves(n_rules, n_zones):
    """P5: ConstraintSet.to_dict round-trips through from_dict preserving
    every leaf — the marshalling surface is total (no key dropped, no type
    widened)."""
    cs_dict = {
        "clearances": [{"from": "A", "to": "B", "clearance_mm": 0.3 + i}
                       for i in range(n_rules)],
        "zones": [{"name": f"Z{i}", "bounds": [0, 0, 10 + i, 10]} for i in range(n_zones)],
    }
    cs = RS_CONSTRAINT_SET.from_dict(cs_dict)
    back = RS_CONSTRAINT_SET.from_dict(cs.to_dict())
    assert canon(back) == canon(cs)
    assert len(back.clearances) == n_rules
    assert len(back.zones) == n_zones


# ---------------------------------------------------------------------------
# MRs -- three metamorphic relations (R1d)
# ---------------------------------------------------------------------------


def test_mr1_merge_is_order_preserving_concatenation():
    """MR1: CheckResult.merge concatenates issues in order, ANDs passed, adds
    elapsed_ms, and later metrics keys win — all order-sensitive semantics."""
    rs_a = RS_CHECK_RESULT("c", True,
                           [RS_ISSUE(RS_SEVERITY.ERROR, "E1", "m", "drc", "c")], 1.0, {"x": 1})
    rs_b = RS_CHECK_RESULT("c", False,
                           [RS_ISSUE(RS_SEVERITY.WARNING, "W1", "m", "drc", "c")], 2.0, {"x": 2})
    py_a = _result_oracle.CheckResult("c", True,
                                      [_result_oracle.Issue(_SEV.ERROR, "E1", "m", "drc", "c")],
                                      1.0, {"x": 1})
    py_b = _result_oracle.CheckResult("c", False,
                                      [_result_oracle.Issue(_SEV.WARNING, "W1", "m", "drc", "c")],
                                      2.0, {"x": 2})
    for x, y, xr, yr in [(py_a, py_b, rs_a, rs_b), (py_b, py_a, rs_b, rs_a)]:
        assert canon(xr.merge(yr)) == canon(x.merge(y))
    assert [i.code for i in rs_a.merge(rs_b).issues] == ["E1", "W1"]
    assert rs_a.merge(rs_b).passed is False
    assert rs_a.merge(rs_a).passed is True
    assert rs_a.merge(rs_b).elapsed_ms == 3.0
    assert rs_a.merge(rs_b).metrics == {"x": 2}  # later wins


def test_mr2_run_result_permutation_invariant():
    """MR2: total_penalty and the aggregate counts are invariant under
    permutation of check_results (sum over a multiset)."""
    import itertools

    def make_checks(iss, sev):
        return [iss(sev.ERROR, "E", "m", "drc", "c"), iss(sev.WARNING, "W", "m", "drc", "c")]

    rs_rr = RS_RUN_RESULT(
        [RS_CHECK_RESULT(f"c{i}", True, make_checks(RS_ISSUE, RS_SEVERITY))
         for i in range(3)], 1.0)
    py_rr = _result_oracle.RunResult(
        [_result_oracle.CheckResult(f"c{i}", True, make_checks(_result_oracle.Issue, _SEV))
         for i in range(3)], 1.0)
    for perm in itertools.permutations(range(3)):
        rs_p = RS_RUN_RESULT([rs_rr.check_results[i] for i in perm], 1.0)
        py_p = _result_oracle.RunResult([py_rr.check_results[i] for i in perm], 1.0)
        assert rs_p.total_penalty == py_p.total_penalty == rs_rr.total_penalty
        assert (rs_p.error_count, rs_p.warning_count) == \
            (py_p.error_count, py_p.warning_count)


def test_mr3_by_category_is_partitioning():
    """MR3: every non-empty check appears in exactly one by_category group
    (category keys are disjoint), and empty-issue checks appear in every
    by_category result (the oracle's ``or not r.issues`` clause)."""
    rs_issues = [RS_ISSUE(RS_SEVERITY.ERROR, "E", "m", "drc", "c"),
                 RS_ISSUE(RS_SEVERITY.WARNING, "W", "m", "safety", "c")]
    py_issues = [_result_oracle.Issue(_SEV.ERROR, "E", "m", "drc", "c"),
                 _result_oracle.Issue(_SEV.WARNING, "W", "m", "safety", "c")]
    rs_rr = RS_RUN_RESULT([RS_CHECK_RESULT("a", False, rs_issues),
                           RS_CHECK_RESULT("empty", True, [])], 0.0)
    py_rr = _result_oracle.RunResult([_result_oracle.CheckResult("a", False, py_issues),
                                      _result_oracle.CheckResult("empty", True, [])], 0.0)
    for cat in ("drc", "safety", "emc"):
        rs_names = sorted(c.check_name for c in rs_rr.by_category(cat))
        py_names = sorted(c.check_name for c in py_rr.by_category(cat))
        assert rs_names == py_names
    assert "empty" in [c.check_name for c in rs_rr.by_category("drc")]
    assert "a" in [c.check_name for c in rs_rr.by_category("drc")]
    # The non-empty check appears in exactly the categories its issues carry.
    a_names = {c.check_name for c in rs_rr.by_category("drc") + rs_rr.by_category("safety")}
    assert "a" in a_names and "empty" in a_names
    assert {i.category for i in rs_rr.check_results[0].issues} == {"drc", "safety"}
