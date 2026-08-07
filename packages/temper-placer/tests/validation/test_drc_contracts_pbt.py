"""Property-based tests for the migrated drc contract pyclasses
(temper_drc_rs.drc_contracts) — the suites-only home for the R20
discriminators moved out of `test_drc_contracts_rust_differential.py`.

#850's differential-disabled re-run (docs/evidence/2026-08-06-r20-differential-
disabled-rerun.md) found all 11 drc-contracts campaign mutants survive the
suites-only run because their discriminating assertions lived only inside the
differential. Every one of those assertions is a deterministic invariant of
the exported pyclass surface (a pinned literal, a recomputed count, or an
independent recomputation) — none needs the oracle, so each is moved here as
a literal property case. The differential keeps its own (identical)
assertions; nothing here weakens it.

Each test documents which surviving mutant it discriminates (cMx labels match
the campaign in /tmp/wt9-r20_r20_driver.py).
"""

from __future__ import annotations

import temper_drc_rs as _tdrc

S = _tdrc.Severity


# ---------------------------------------------------------------------------
# cM1 — Severity WARNING weight 1.0 -> 2.0
# ---------------------------------------------------------------------------


def test_p1_severity_weight_table_pinned():
    """The severity weight table is exactly {INFO 0.0, WARNING 1.0, ERROR
    10.0, CRITICAL 100.0} and is_failure marks exactly ERROR/CRITICAL. A port
    that raised WARNING to 2.0 fails the pin (surviving mutant cM1)."""
    assert S.INFO.weight == 0.0 and S.INFO.is_failure is False
    assert S.WARNING.weight == 1.0 and S.WARNING.is_failure is False
    assert S.ERROR.weight == 10.0 and S.ERROR.is_failure is True
    assert S.CRITICAL.weight == 100.0 and S.CRITICAL.is_failure is True
    assert S.WARNING.name == "WARNING" and S.WARNING.value == 2


# ---------------------------------------------------------------------------
# cM2 — CheckResult.info_count counts INFO (not ERROR)
# ---------------------------------------------------------------------------


def test_p2_info_count_recomputed_from_issues():
    """info_count is exactly the number of INFO-severity issues in the list. A
    port whose info_count read the ERROR count instead fails the pin
    (surviving mutant cM2)."""
    c = _tdrc.CheckResult(
        "c", False,
        [_tdrc.Issue(S.INFO, "I1", "m", "drc", "c"),
         _tdrc.Issue(S.INFO, "I2", "m", "drc", "c"),
         _tdrc.Issue(S.ERROR, "E1", "m", "drc", "c")],
        0.0, {},
    )
    assert c.info_count == 2
    assert c.error_count == 1
    assert c.warning_count == 0
    assert c.critical_count == 0
    assert _tdrc.CheckResult("c", True, [], 0.0, {}).info_count == 0


# ---------------------------------------------------------------------------
# cM3 — RunResult.passed fails closed on an empty run
# ---------------------------------------------------------------------------


def test_p3_run_result_passed_fails_closed():
    """RunResult.passed is True iff there is at least one check and every
    check passed — an empty run fails closed. A port that dropped the
    empty-run clause would report True for `RunResult()` (surviving mutant
    cM3)."""
    assert _tdrc.RunResult().passed is False
    assert _tdrc.RunResult([], 0.0).passed is False
    assert _tdrc.RunResult([_tdrc.CheckResult("c", True, [], 0.0, {})], 0.0).passed is True
    assert _tdrc.RunResult([_tdrc.CheckResult("c", False, [], 0.0, {})], 0.0).passed is False


# ---------------------------------------------------------------------------
# cM4 — CheckResult.merge: later metrics win
# ---------------------------------------------------------------------------


def test_p4_merge_later_metrics_win():
    """merge concatenates issues in order, ANDs passed, adds elapsed_ms, and
    later metrics keys win ({**a, **b}). A port that dropped the later-wins
    loop ({**a} semantics) keeps the first value and fails the pin (surviving
    mutant cM4)."""
    a = _tdrc.CheckResult("c", True, [_tdrc.Issue(S.ERROR, "E1", "m", "drc", "c")], 1.0, {"x": 1, "y": 1})
    b = _tdrc.CheckResult("c", False, [_tdrc.Issue(S.WARNING, "W1", "m", "drc", "c")], 2.0, {"x": 2})
    merged = a.merge(b)
    assert merged.metrics == {"x": 2, "y": 1}
    assert [i.code for i in merged.issues] == ["E1", "W1"]
    assert merged.passed is False
    assert merged.elapsed_ms == 3.0
    assert a.merge(a).metrics == {"x": 1, "y": 1}


# ---------------------------------------------------------------------------
# cM5 — Location.__repr__ includes the layer field
# ---------------------------------------------------------------------------


def test_p5_location_repr_includes_layer():
    """repr(Location) renders all three fields, including layer. A port that
    omitted the layer field fails the literal pin (surviving mutant cM5)."""
    assert repr(_tdrc.Location(1.25, -2.75, "F.Cu")) == \
        "Location(x=1.25, y=-2.75, layer='F.Cu')"
    assert repr(_tdrc.Location(0.0, 0.0, "")) == "Location(x=0.0, y=0.0, layer='')"


# ---------------------------------------------------------------------------
# cM6 — Issue.__str__ affected-items truncation
# ---------------------------------------------------------------------------


def test_p6_issue_str_truncation_at_three():
    """Issue.__str__ lists the first 3 affected items then `(+1 more)`; 3 or
    fewer items are listed in full. A port that truncated at 2 instead of 3
    fails the literal pin (surviving mutant cM6)."""
    assert str(_tdrc.Issue(S.ERROR, "E1", "msg", "drc", "c", ["A", "B", "C", "D"])) == \
        "[E1] msg (A, B, C (+1 more))"
    assert str(_tdrc.Issue(S.ERROR, "E1", "msg", "drc", "c", ["A", "B", "C"])) == \
        "[E1] msg (A, B, C)"
    assert str(_tdrc.Issue(S.INFO, "I9", "m", "drc", "c", [])) == "[I9] m ()"


# ---------------------------------------------------------------------------
# cM7 — ComponentPlacement.bounds
# ---------------------------------------------------------------------------


def test_p7_component_bounds_from_center_and_size():
    """bounds is (x - hw, y - hh, x + hw, y + hh). A port with a sign flip on
    the x_min term returns (x + hw, ...) and fails the literal pin (surviving
    mutant cM7)."""
    a = _tdrc.ComponentPlacement("A", "fp", 0.0, 0.0, 0.0, "F.Cu", 10.0, 10.0)
    assert tuple(a.bounds) == (-5.0, -5.0, 5.0, 5.0)
    b = _tdrc.ComponentPlacement("B", "fp", 20.0, 10.0, 0.0, "F.Cu", 4.0, 2.0)
    assert tuple(b.bounds) == (18.0, 9.0, 22.0, 11.0)


# ---------------------------------------------------------------------------
# cM8 — ConstraintSet.get_clearance
# ---------------------------------------------------------------------------


def test_p8_get_clearance_matches_first_applicable_rule():
    """get_clearance returns the first rule whose applies_to() fires, else
    0.0. A port that disabled the rule-matching loop would always return 0.0
    and fail the pin (surviving mutant cM8)."""
    cs = _tdrc.ConstraintSet([
        _tdrc.ClearanceRule("HV", "LV", 6.0),
        _tdrc.ClearanceRule("*", "*", 0.3),
    ])
    assert cs.get_clearance("HV", "LV") == 6.0
    assert cs.get_clearance("A", "B") == 0.3
    assert cs.get_clearance("X", "Y") == 0.3
    empty = _tdrc.ConstraintSet()
    assert empty.get_clearance("A", "B") == 0.0


# ---------------------------------------------------------------------------
# cM9 — Placement.from_dict rotation default
# ---------------------------------------------------------------------------


def test_p9_from_dict_rotation_default_zero():
    """A component dict without a rotation key gets the 0.0 default. A port
    that defaulted to 90.0 fails the pin (surviving mutant cM9)."""
    p = _tdrc.Placement.from_dict({
        "components": [{"ref": "R1", "footprint": "R_0402", "x": 1.0, "y": 2.0}]
    })
    assert p.components["R1"].rotation == 0.0
    p2 = _tdrc.Placement.from_dict({
        "components": [{"ref": "R1", "footprint": "R_0402", "x": 1.0, "y": 2.0,
                        "rotation": 45.0}]
    })
    assert p2.components["R1"].rotation == 45.0


# ---------------------------------------------------------------------------
# cM10 — CheckResult.penalty is the severity-weighted sum
# ---------------------------------------------------------------------------


def test_p10_penalty_is_severity_weighted_sum():
    """penalty == sum(issue.severity.weight) in issue order (INFO 0, WARNING 1,
    ERROR 10, CRITICAL 100) — recomputed here, not via the oracle. A port that
    accumulated 2*w would double every term and fail the pin (surviving mutant
    cM10)."""
    for sev, weight in [(S.INFO, 0.0), (S.WARNING, 1.0), (S.ERROR, 10.0),
                        (S.CRITICAL, 100.0)]:
        c = _tdrc.CheckResult("c", True, [_tdrc.Issue(sev, "E", "m", "drc", "c")], 0.0, {})
        assert c.penalty == weight, sev.name
    mixed = _tdrc.CheckResult(
        "c", True,
        [_tdrc.Issue(S.ERROR, "E", "m", "drc", "c"),
         _tdrc.Issue(S.WARNING, "W", "m", "drc", "c"),
         _tdrc.Issue(S.INFO, "I", "m", "drc", "c")],
        0.0, {},
    )
    assert mixed.penalty == 10.0 + 1.0 + 0.0
    assert _tdrc.CheckResult("c", True, [], 0.0, {}).penalty == 0.0


# ---------------------------------------------------------------------------
# cM11 — Severity.members() declaration order
# ---------------------------------------------------------------------------


def test_p11_severity_members_declaration_order():
    """members() yields INFO, WARNING, ERROR, CRITICAL in declaration order
    (the report formatter's severity enumeration). A port that swapped the
    order fails the literal pin (surviving mutant cM11)."""
    assert [m.name for m in S.members()] == ["INFO", "WARNING", "ERROR", "CRITICAL"]
    assert S.members() == [S.INFO, S.WARNING, S.ERROR, S.CRITICAL]
