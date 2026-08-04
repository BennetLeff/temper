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


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
