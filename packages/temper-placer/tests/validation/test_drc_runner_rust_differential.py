"""Differential test: drc_runner's violation-grouping compute in Rust
(temper_drc_rs.group_violations) vs the pinned Python implementation
(Wave 4, Phase 4 — validation DRC-check slice).

``temper_placer/validation/drc_runner.py`` already delegates check execution
to ``temper_drc_rs.run_drc``; this migration EXTENDS that bridge by moving
the ``_violations_to_run_result`` grouping/normalization compute (shared
verbatim with ``drc_oracle._violations_to_run_result``) into the
``temper_drc_rs.group_violations`` kernel, so both modules consume the same
Rust grouping logic. The pre-migration ``_violations_to_run_result`` body is
pinned VERBATIM below (commit ``aece7c372``).

The ``_placement_to_board_dict`` / ``_constraints_to_dict`` marshalling
functions stay Python: they convert Phase-2 contract objects
(Placement/ConstraintSet from ``drc_types``) into the K1-schema dicts —
data marshalling over out-of-scope contracts, argued in-source.

Comparison convention: floats bit-exact via ``float.hex()``; RunResult
objects canonicalized into typed tuples.
"""

from __future__ import annotations

import random

import pytest
import temper_drc_rs as _tdrc
from hypothesis import given, settings
from hypothesis import strategies as st

# Rust symbol under test — must exist or this file fails to collect (RED).
GROUP_VIOLATIONS = _tdrc.group_violations

from temper_placer.validation.drc_result import (  # noqa: E402
    CheckResult as _CheckResult,
)
from temper_placer.validation.drc_result import (  # noqa: E402
    Issue as _Issue,
)
from temper_placer.validation.drc_result import (  # noqa: E402
    Location as _Location,
)
from temper_placer.validation.drc_result import (  # noqa: E402
    RunResult as _RunResult,
)
from temper_placer.validation.drc_result import (  # noqa: E402
    Severity as _Severity,
)
from temper_placer.validation.drc_runner import (
    _violations_to_run_result as shim_convert,  # noqa: E402
)
from temper_placer.validation.drc_types import (  # noqa: E402
    ComponentPlacement,
    Placement,
)

# The runner's wrapper adds elapsed_ms to the RunResult — drive it through
# the shim wrapper (the kernel-level records are pinned via drc_oracle's and
# this file's property/metamorphic suites).


# ---------------------------------------------------------------------------
# Oracle — the pre-migration _violations_to_run_result, verbatim
# (commit aece7c372; elapsed_ms parameter included)
# ---------------------------------------------------------------------------

_SEVERITY_MAP: dict[str, _Severity] = {
    "INFO": _Severity.INFO,
    "WARNING": _Severity.WARNING,
    "ERROR": _Severity.ERROR,
    "CRITICAL": _Severity.CRITICAL,
}


def _ref_violations_to_run_result(
    violation_dicts: list[dict],
    elapsed_ms: float = 0.0,
) -> _RunResult:
    """Pre-migration ``_violations_to_run_result``, verbatim."""
    grouped: dict[str, list[dict]] = {}
    for v in violation_dicts:
        name = v.get("check_name", "unknown")
        grouped.setdefault(name, []).append(v)

    check_results: list[_CheckResult] = []
    for check_name, violations in sorted(grouped.items()):
        issues: list[_Issue] = []
        has_failure = False
        for v in violations:
            severity_str = v.get("severity", "ERROR").upper()
            severity = _SEVERITY_MAP.get(severity_str, _Severity.ERROR)
            if severity in (_Severity.ERROR, _Severity.CRITICAL):
                has_failure = True

            loc_dict = v.get("location")
            location = None
            if loc_dict is not None and isinstance(loc_dict, dict):
                location = _Location(
                    x=loc_dict.get("x"),
                    y=loc_dict.get("y"),
                    layer=loc_dict.get("layer"),
                )

            issue = _Issue(
                severity=severity,
                code=v.get("code", "DRC_RS_000"),
                message=v.get("message", ""),
                category=v.get("category", "drc"),
                check_name=check_name,
                affected_items=v.get("affected_items", []),
                location=location,
                details=v.get("details", {}),
            )
            issues.append(issue)

        check_results.append(
            _CheckResult(
                check_name=check_name,
                passed=not has_failure,
                issues=issues,
            )
        )

    return _RunResult(check_results=check_results, total_elapsed_ms=elapsed_ms)


def _canon_run_result(rr):
    out = []
    for cr in rr.check_results:
        issues = []
        for i in cr.issues:
            issues.append(
                (
                    i.severity.name,
                    i.code,
                    i.message,
                    i.category,
                    i.check_name,
                    tuple(i.affected_items),
                    None
                    if i.location is None
                    else (None if i.location.x is None else float(i.location.x).hex(),
                          None if i.location.y is None else float(i.location.y).hex(),
                          i.location.layer),
                    tuple(sorted((k, repr(v)) for k, v in i.details.items())),
                )
            )
        out.append((cr.check_name, cr.passed, tuple(issues)))
    return tuple(out)


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


# ---------------------------------------------------------------------------
# Differential
# ---------------------------------------------------------------------------


def test_differential_deterministic():
    vs = [
        _violation_dict("a", "INFO"),
        _violation_dict("b", "CRITICAL", location={"x": 1.0, "y": None, "layer": None}),
        _violation_dict("a", "ERROR", affected=[]),
        _violation_dict("b", "WARNING", details={"k": 2.5}),
        {"severity": "ERROR", "check_name": "a"},  # defaults
        {"check_name": "c"},  # missing severity → ERROR default → failure
        _violation_dict("a", "BOGUS"),
        _violation_dict("c", "INFO", location={}),  # empty dict → DrcLocation(None,None,None)
    ]
    ref = _ref_violations_to_run_result(vs, elapsed_ms=12.5)
    got = shim_convert(vs, elapsed_ms=12.5)
    assert _canon_run_result(got) == _canon_run_result(ref)
    assert got.total_elapsed_ms == ref.total_elapsed_ms == 12.5


def test_differential_random():
    rng = random.Random(2026)
    names = ["drc_clearance", "safety_creepage", "emc_loop_area"]
    for _ in range(200):
        vs = []
        for _ in range(rng.randint(0, 8)):
            vs.append(
                _violation_dict(
                    check_name=rng.choice(names),
                    severity=rng.choice(["INFO", "WARNING", "ERROR", "CRITICAL", "X"]),
                    affected=[f"R{rng.randint(0, 9)}" for _ in range(rng.randint(0, 3))],
                    location=({"x": rng.uniform(-5, 5), "y": rng.uniform(-5, 5), "layer": "F.Cu"}
                              if rng.random() < 0.5 else None),
                )
            )
        ref = _ref_violations_to_run_result(vs)
        got = shim_convert(vs)
        assert _canon_run_result(got) == _canon_run_result(ref)


def test_differential_empty():
    ref = _ref_violations_to_run_result([])
    got = shim_convert([])
    assert _canon_run_result(got) == _canon_run_result(ref)
    assert got.check_results == []


# ---------------------------------------------------------------------------
# PBT — five non-vacuous properties of the migrated kernel (via the shim)
# ---------------------------------------------------------------------------


@settings(max_examples=40, deadline=None)
@given(
    st.lists(
        st.tuples(
            st.sampled_from(["a", "b", "c"]),
            st.sampled_from(["INFO", "WARNING", "ERROR", "CRITICAL"]),
        ),
        min_size=0,
        max_size=10,
    ),
)
def test_prop1_passed_matches_failure_flag(pairs):
    """P1: a group's ``passed`` is True iff no member has has_failure."""
    vs = [_violation_dict(n, s) for (n, s) in pairs]
    rr = shim_convert(vs)
    for cr in rr.check_results:
        expected = not any(i.severity in (_Severity.ERROR, _Severity.CRITICAL) for i in cr.issues)
        assert cr.passed is expected


def test_prop2_groups_sorted():
    """P2: check_results are ordered by check_name."""
    vs = [
        _violation_dict("b", "ERROR"),
        _violation_dict("a", "WARNING"),
        _violation_dict("c", "INFO"),
        _violation_dict("a", "ERROR"),
    ]
    rr = shim_convert(vs)
    assert [cr.check_name for cr in rr.check_results] == ["a", "b", "c"]


def test_prop3_default_fields():
    """P3: violations missing code/message/category/affected_items/details
    get the oracle's exact defaults."""
    rr = shim_convert([{"severity": "WARNING", "check_name": "g"}])
    (cr,) = rr.check_results
    (issue,) = cr.issues
    assert issue.code == "DRC_RS_000"
    assert issue.message == ""
    assert issue.category == "drc"
    assert issue.affected_items == []
    assert issue.details == {}
    assert issue.location is None


def test_prop4_unknown_severity_fails_closed():
    """P4: an unknown severity string normalizes to ERROR and fails the
    group (the oracle's Severity.ERROR fallback)."""
    rr = shim_convert([_violation_dict("g", "WAT")])
    (cr,) = rr.check_results
    assert cr.passed is False
    (issue,) = cr.issues
    assert issue.severity == _Severity.ERROR


def test_prop5_non_dict_location_ignored():
    """P5: a location that is not a dict (or is None) yields no Location on
    the issue (the oracle's isinstance guard)."""
    for bad in (None, "str", 42, ["x"], (1.0, 2.0)):
        rr = shim_convert([_violation_dict("g", "ERROR", location=bad)])
        (cr,) = rr.check_results
        (issue,) = cr.issues
        assert issue.location is None


# ---------------------------------------------------------------------------
# Metamorphic relations — three, honestly bounded
# ---------------------------------------------------------------------------


def test_mr1_permutation_preserves_partition():
    """MR1: permuting the input list permutes each group's members — the
    partition (check_name → multiset of issue tuples) is invariant."""
    rng = random.Random(31)
    vs = [_violation_dict(rng.choice(["a", "b", "c"]), rng.choice(["INFO", "ERROR", "WARNING"]))
          for _ in range(12)]
    base = shim_convert(vs)
    base_map = {
        cr.check_name: tuple(sorted((i.severity.name, i.code) for i in cr.issues))
        for cr in base.check_results
    }
    for _ in range(5):
        perm = vs[:]
        rng.shuffle(perm)
        got = shim_convert(perm)
        got_map = {
            cr.check_name: tuple(sorted((i.severity.name, i.code) for i in cr.issues))
            for cr in got.check_results
        }
        assert got_map == base_map


def test_mr2_location_roundtrip_through_kernel():
    """MR2: a violation with an explicit location (x, y, layer) is
    bit-identical through the kernel group and back into the Issue."""
    loc = {"x": 1.25, "y": -0.5, "layer": "B.Cu"}
    rr = shim_convert([_violation_dict("g", "ERROR", location=loc)])
    (cr,) = rr.check_results
    (issue,) = cr.issues
    assert issue.location is not None
    assert float(issue.location.x).hex() == 1.25.hex()
    assert float(issue.location.y).hex() == (-0.5).hex()
    assert issue.location.layer == "B.Cu"


def test_mr3_append_only_grows_group():
    """MR3: appending a violation to an existing group preserves the earlier
    records of that group (order-preserving append within the group)."""
    base = [_violation_dict("x", "ERROR"), _violation_dict("x", "WARNING")]
    rr = shim_convert(base)
    (cr,) = rr.check_results
    before = [i.severity.name for i in cr.issues]
    rr2 = shim_convert(base + [_violation_dict("x", "CRITICAL")])
    (cr2,) = rr2.check_results
    after = [i.severity.name for i in cr2.issues]
    assert after[:2] == before
    assert after == ["ERROR", "WARNING", "CRITICAL"]


# ---------------------------------------------------------------------------
# Boundary-schema contract tests (Python<->Rust dict-payload key-set audit,
# 2026-08-08)
# ---------------------------------------------------------------------------
#
# The rest of this file pins group_violations' *compute*. These two tests
# guard the OTHER half of the same Python<->Rust boundary this module
# crosses: that _placement_to_board_dict / _constraints_to_dict emit dicts
# temper_drc_rs actually accepts. That contract used to be silent --
# board_py_bridge.rs's hand-rolled extract_*() functions only ever read
# keys they know about, so a renamed/misspelled key on either side was
# invisible (this is exactly how the via/trace/zones K1-schema mismatch
# shipped undetected: see drc_runner.py's _placement_to_board_dict history).
#
# `build_board_state` (board_py_bridge.rs) now calls `reject_unknown_keys`
# at the board_dict top level and inside every component/via/trace/zone/
# net_class_rules sub-dict; `ConstraintSet` and every constraint sub-type
# (constraints.rs) now carry `#[serde(deny_unknown_fields)]`. That makes
# "no exception raised" a real, CI-enforced assertion instead of a
# vacuous one: any future rename/typo on either side of the boundary now
# makes these tests raise, not silently drop data.
#
# Demonstrated failing before the fix (reproduced live, not just by
# reasoning): reverting board_py_bridge.rs's guards and drc_runner.py's
# via/trace/zones key names back to their pre-fix shapes reproduces
# `ValueError: missing required key: net` here.


def test_placement_to_board_dict_matches_rust_k1_schema() -> None:
    """A fully-populated Placement (components, nets, net_classes, vias,
    traces) run through _placement_to_board_dict must produce a dict
    temper_drc_rs.run_drc() accepts without raising -- the K1-schema
    key-set contract between the Python builder and the Rust consumer."""
    from temper_placer.validation.drc_runner import _placement_to_board_dict

    placement = Placement(
        components={
            "C1": ComponentPlacement(
                ref="C1", footprint="0402", x=10.0, y=10.0, rotation=0.0,
                layer="F.Cu", width=1.0, height=1.0, net_class="Signal",
            ),
            "C2": ComponentPlacement(
                ref="C2", footprint="0402", x=50.0, y=50.0, rotation=0.0,
                layer="B.Cu", width=1.0, height=1.0, net_class="Signal",
            ),
        },
        nets={"N1": ["C1", "C2"]},
        net_classes={"N1": "Signal"},
        board_width=100.0,
        board_height=100.0,
        via_placement=_tdrc.ViaPlacement(
            vias=[
                _tdrc.Via(
                    position=(5.0, 5.0), from_layer="F.Cu", to_layer="B.Cu",
                    diameter=0.6, drill=0.3, net_name="N1",
                ),
            ]
        ),
        trace_placement=_tdrc.TracePlacement(
            segments=[
                _tdrc.TraceSegment(
                    net_name="N1", layer="F.Cu", width=0.25,
                    start=(0.0, 0.0), end=(10.0, 0.0),
                ),
            ]
        ),
    )
    board_dict = _placement_to_board_dict(placement)
    result = _tdrc.run_drc(board_dict, {})
    assert isinstance(result, list)


def test_constraints_to_dict_matches_rust_constraint_set_schema() -> None:
    """A fully-populated ConstraintSet (clearances, zones, critical_loops,
    thermal_constraints, component_groups) run through
    _constraints_to_dict, then through temper_drc_rs.run_drc(), must not
    raise -- the ConstraintSet #[serde(deny_unknown_fields)] contract."""
    from temper_placer.validation.drc_runner import _constraints_to_dict

    minimal_board = {
        "board": {"width_mm": 100.0, "height_mm": 100.0},
        "components": [],
        "nets": {},
        "net_classes": {},
    }
    constraints = _tdrc.ConstraintSet(
        clearances=[
            _tdrc.ClearanceRule(from_class="HV", to_class="LV", min_mm=6.0, description="safety"),
        ],
        zones=[
            _tdrc.ZoneDefinition(name="Z1", bounds=(0.0, 0.0, 10.0, 10.0),
                                  net_classes=["HV"], components=["Q1"]),
        ],
        critical_loops=[
            _tdrc.LoopConstraint(name="L1", nets=["N1"], max_area_mm2=100.0,
                                  weight=1.0, description=""),
        ],
        thermal_constraints=[
            _tdrc.ThermalConstraint(components=["Q1"], prefer_edge=True,
                                     min_spacing_mm=5.0,
                                     max_distance_from_edge_mm=20.0,
                                     description=""),
        ],
        component_groups=[
            _tdrc.GroupConstraint(name="G1", components=["Q1", "Q2"],
                                   max_spread_mm=25.0, zone=None,
                                   proximity_rules=[], description=""),
        ],
        net_classes={"N1": "Signal"},
        voltage_domains={},
        hv_clearance_mm=8.0,
        board_width=100.0,
        board_height=100.0,
    )
    constraints_dict = _constraints_to_dict(constraints)
    result = _tdrc.run_drc(minimal_board, constraints_dict)
    assert isinstance(result, list)


# ---------------------------------------------------------------------------
# Negative-path guards: the two tests above only prove the guard accepts a
# GOOD payload without raising -- that is necessary but not sufficient
# evidence the guard works ("a schema guard that has never been shown
# rejecting a bad payload is not evidence"). These prove it actually
# rejects a bad one, live, against the real installed extension -- not
# reasoned about, not reverted-after-manual-check, permanently pinned so a
# regression that silently disables the guard (e.g. an accidental
# `#[serde(deny_unknown_fields)]` removal, or a `reject_unknown_keys` call
# site deleted during a refactor) fails CI immediately.
# ---------------------------------------------------------------------------


def test_board_dict_rejects_unrecognized_via_key() -> None:
    """The hand-rolled board_py_bridge.rs guard (reject_unknown_keys,
    since this boundary is manual get_item() calls, not a serde Deserialize
    -- deny_unknown_fields does not apply here) must reject a via dict
    carrying the OLD pre-fix key name ("net_name" instead of "net") rather
    than silently ignoring it and defaulting x/y/pad to 0.0/0.0/0.6."""
    bad_board = {
        "board": {"width_mm": 100.0, "height_mm": 100.0},
        "components": [],
        "nets": {},
        "net_classes": {},
        "vias": [
            {
                "net_name": "N1",  # pre-fix key name; extract_via wants "net"
                "x": 5.0,
                "y": 5.0,
                "drill": 0.3,
                "pad": 0.6,
                "from_layer": "F.Cu",
                "to_layer": "B.Cu",
            }
        ],
    }
    with pytest.raises(ValueError, match="net_name"):
        _tdrc.run_drc(bad_board, {})


def test_board_dict_rejects_unrecognized_top_level_key() -> None:
    """A typo'd top-level board_dict key (e.g. a future rename that misses
    one call site) must raise, not vanish into an ignored dict entry."""
    bad_board = {
        "board": {"width_mm": 100.0, "height_mm": 100.0},
        "componentz": [],  # typo of "components"
        "nets": {},
        "net_classes": {},
    }
    with pytest.raises(ValueError, match="componentz"):
        _tdrc.run_drc(bad_board, {})


def test_constraints_dict_rejects_unrecognized_key() -> None:
    """The serde #[serde(deny_unknown_fields)] guard on ConstraintSet must
    reject an unrecognized top-level constraints_dict key. This is the
    guard 337a2c2f's thermal_constraints fix relies on staying live --
    before this remediation, an unrecognized key here (e.g. the legacy
    pyclass's "component_groups", which has no serde ConstraintSet field)
    was silently discarded by serde_json::from_value, not an error."""
    minimal_board = {
        "board": {"width_mm": 100.0, "height_mm": 100.0},
        "components": [],
        "nets": {},
        "net_classes": {},
    }
    with pytest.raises(ValueError, match="component_groups|unknown field"):
        _tdrc.run_drc(minimal_board, {"component_groups": []})


def test_constraints_dict_rejects_unrecognized_nested_key() -> None:
    """The deny_unknown_fields guard applies to nested constraint
    sub-structs too, not just the top-level ConstraintSet -- a zone dict
    carrying the legacy pyclass's "bounds"/"components" keys (real fields
    on the pyclass ZoneDefinition, but not on the serde ZoneDefinition
    build_constraint_set deserializes into) must raise."""
    minimal_board = {
        "board": {"width_mm": 100.0, "height_mm": 100.0},
        "components": [],
        "nets": {},
        "net_classes": {},
    }
    bad_constraints = {
        "zones": [{"name": "Z1", "net_classes": ["HV"], "bounds": [0, 0, 1, 1]}],
    }
    with pytest.raises(ValueError, match="bounds|unknown field"):
        _tdrc.run_drc(minimal_board, bad_constraints)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
