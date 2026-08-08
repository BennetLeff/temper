"""Anti-vacuity guard for the Python DRC ``Check`` classes.

Mirrors the Rust guard test added in the same remediation,
``rules::integration_tests::no_registered_rule_is_vacuous_across_varied_fixtures``
(``packages/temper-drc-rs/src/rules/mod.rs``): run every registered check
against a varied fixture set and fail if a check's name never shows up in
the accumulated output -- the "reports green, cannot fail" defect class
this whole remediation targets (see
``docs/evidence/2026-08-08-drc-safety-rule-vacuity-audit.md`` and the
Python-side follow-up that produced this file).

Background: ``drc_result.py`` used to have 15 ``Check`` subclasses whose
``run()`` unconditionally returned ``CheckResult(passed=True)`` while their
docstrings claimed Rust delegation. 14 of the 15 now delegate for real
(``_run_check_via_rust``); the one exception, ``PowerDomainCheck``, has
nothing to delegate to (``erc_power_domain`` is deliberately unregistered
in the Rust engine -- no ``voltage_domain`` field on the native schema) and
must report not-run (``passed=False`` + an INFO ``ERC_PWR_000`` marker),
never a fabricated pass.

This file has three responsibilities:

1. ``test_no_delegating_check_is_vacuous_across_varied_fixtures`` --
   the anti-vacuity guard proper: for each of the 12 delegating checks
   this suite can exercise through the ``Placement``/``ConstraintSet``
   contract, at least one fixture in the corpus must make that check's
   name appear in the accumulated ``Issue`` list. A check that is silent
   for every fixture in a deliberately varied corpus is presumptively
   vacuous again.
2. ``test_power_domain_check_never_reports_passed_true`` -- the
   ``PowerDomainCheck``-specific invariant: run across the SAME corpus
   (plus a trivial empty board), it must never once report
   ``passed=True``, and every result must carry the not-run marker.
3. ``test_clean_board_has_no_violations`` -- the pass-side complement: a
   deliberately unremarkable board produces zero issues from any
   delegating check, so the corpus is not "everything always fires".

TraceClearanceCheck and ViaSpacingCheck (``drc_trace_clearance`` /
``drc_via_spacing``) are EXCLUDED from the guard's per-check requirement.
Both are genuinely registered Rust rules and their ``run()`` bodies were
fixed identically to the other 12 (they now call ``_run_check_via_rust``
too) -- but a fixture that populates ``Placement.via_placement`` or
``Placement.trace_placement`` cannot reach ``temper_drc_rs.run_drc()`` at
all: ``drc_runner._placement_to_board_dict`` builds via/trace dicts with
keys (``position``/``diameter``/``net_name``) that do not match what
``temper_drc_rs::board_py_bridge::extract_via`` /
``extract_trace_segment`` require (``x``/``y``/``pad``/``net``), so
deserialization raises ``ValueError: missing required key: net`` before
any rule runs. This is a real, independent, pre-existing bug -- not
something this remediation introduced or is fixing -- documented and
pinned by ``test_via_and_trace_fixtures_hit_a_preexisting_dict_key_bug``
below so it stays visible rather than silently dropped from coverage.
"""

from __future__ import annotations

import pytest

from temper_placer.validation.drc_result import (
    Check,
    ClearanceCheck,
    ComponentOverlapCheck,
    CourtyardCheck,
    CreepageCheck,
    FloatingPinsCheck,
    GroundPlaneCheck,
    HVLVSeparationCheck,
    IsolationCheck,
    LoopAreaCheck,
    NetConnectivityCheck,
    NoiseCouplingCheck,
    PowerDomainCheck,
    Severity,
    ViaSpacingCheck,
    ZoneContainmentCheck,
)
from temper_placer.validation.drc_types import (
    ClearanceRule,
    ComponentPlacement,
    ConstraintSet,
    LoopConstraint,
    Placement,
    Via,
    ViaPlacement,
    ZoneDefinition,
)


def _comp(
    ref: str,
    x: float,
    y: float,
    net_class: str = "Signal",
    width: float = 1.0,
    height: float = 1.0,
) -> ComponentPlacement:
    return ComponentPlacement(
        ref=ref,
        footprint="0402",
        x=x,
        y=y,
        rotation=0.0,
        layer="F.Cu",
        width=width,
        height=height,
        net_class=net_class,
    )


# ---------------------------------------------------------------------------
# Fixture corpus: one deliberately-bad board per delegating check, so every
# registered rule's name is guaranteed to appear at least once in the
# accumulated output -- mirrors the Rust guard test's 26-fixtures-vs-27-rules
# shape at a scale matched to this suite's 12 checks.
# ---------------------------------------------------------------------------

_OVERLAPPING_COMPONENTS = Placement(
    components={
        "C1": _comp("C1", 10, 10, width=5, height=5),
        "C2": _comp("C2", 10, 10, width=5, height=5),
    },
    board_width=100,
    board_height=100,
)

_BAD_FIXTURES: list[tuple[Check, Placement, ConstraintSet]] = [
    (
        NetConnectivityCheck(),
        Placement(
            components={"C1": _comp("C1", 10, 10)},
            nets={"N_ORPHAN": ["C1"]},
            board_width=100,
            board_height=100,
        ),
        ConstraintSet(),
    ),
    (
        FloatingPinsCheck(),
        Placement(
            components={"C1": _comp("C1", 10, 10)},
            board_width=100,
            board_height=100,
        ),
        ConstraintSet(),
    ),
    (ComponentOverlapCheck(), _OVERLAPPING_COMPONENTS, ConstraintSet()),
    (CourtyardCheck(), _OVERLAPPING_COMPONENTS, ConstraintSet()),
    (
        ClearanceCheck(),
        Placement(
            components={
                "C1": _comp("C1", 0, 0, net_class="Signal"),
                "C2": _comp("C2", 1.0, 0, net_class="Power"),
            },
            board_width=100,
            board_height=100,
        ),
        ConstraintSet(
            clearances=[ClearanceRule(from_class="Signal", to_class="Power", min_mm=2.0)]
        ),
    ),
    (
        LoopAreaCheck(),
        Placement(
            components={"C1": _comp("C1", 0, 0), "C2": _comp("C2", 80, 80)},
            nets={"CLK": ["C1", "C2"]},
            board_width=100,
            board_height=100,
        ),
        ConstraintSet(
            critical_loops=[LoopConstraint(name="ClockLoop", nets=["CLK"], max_area_mm2=1.0)]
        ),
    ),
    (
        HVLVSeparationCheck(),
        Placement(
            components={
                "C1": _comp("C1", 0, 0, net_class="HV"),
                "C2": _comp("C2", 1.0, 0, net_class="LV"),
            },
            board_width=100,
            board_height=100,
        ),
        ConstraintSet(hv_clearance_mm=10.0),
    ),
    (
        NoiseCouplingCheck(),
        Placement(
            components={
                "C1": _comp("C1", 0, 0, net_class="power_switching"),
                "C2": _comp("C2", 0.5, 0, net_class="analog_sensor"),
            },
            board_width=100,
            board_height=100,
        ),
        ConstraintSet(
            clearances=[
                ClearanceRule(
                    from_class="power_switching", to_class="analog_sensor", min_mm=5.0
                )
            ]
        ),
    ),
    (
        GroundPlaneCheck(),
        Placement(
            components={"C1": _comp("C1", 10, 10, net_class="power_switching")},
            board_width=100,
            board_height=100,
        ),
        ConstraintSet(
            zones=[ZoneDefinition(name="GND_Plane", bounds=(0, 0, 50, 50), net_classes=["Signal"])]
        ),
    ),
    (
        IsolationCheck(),
        Placement(
            components={"C1": _comp("C1", 10, 10, net_class="Signal")},
            board_width=100,
            board_height=100,
        ),
        ConstraintSet(
            zones=[ZoneDefinition(name="Iso_Barrier", bounds=(0, 0, 50, 50), net_classes=["Signal"])]
        ),
    ),
    (
        CreepageCheck(),
        Placement(
            components={
                "C1": _comp("C1", 10, 10, net_class="opto_iso", width=3.0, height=2.0)
            },
            board_width=100,
            board_height=100,
        ),
        ConstraintSet(),
    ),
    (
        ZoneContainmentCheck(),
        Placement(
            components={"C1": _comp("C1", 10, 10, net_class="Power")},
            board_width=100,
            board_height=100,
        ),
        ConstraintSet(
            zones=[ZoneDefinition(name="PowerZone", bounds=(0, 0, 50, 50), net_classes=["Power"])]
        ),
    ),
]

# A deliberately unremarkable, clean board: two Signal components, one
# 2-pin net, well separated, no zones/loops/HV/noise/iso classes anywhere.
_CLEAN_PLACEMENT = Placement(
    components={
        "C1": _comp("C1", 10, 10, net_class="Signal"),
        "C2": _comp("C2", 50, 50, net_class="Signal"),
    },
    nets={"N1": ["C1", "C2"]},
    board_width=100,
    board_height=100,
)
_CLEAN_CONSTRAINTS = ConstraintSet(
    clearances=[ClearanceRule(from_class="Signal", to_class="Signal", min_mm=0.1)]
)


def test_no_delegating_check_is_vacuous_across_varied_fixtures() -> None:
    """Every delegating check's name must appear at least once in the
    accumulated Issue output across the fixture corpus.

    This is the direct Python-side mirror of the Rust guard test: a check
    that never once shows up in the output of a corpus built specifically
    to trip it is either broken again or -- the original defect -- was
    never wired to anything real in the first place.
    """
    seen_check_names: set[str] = set()
    for check, placement, constraints in _BAD_FIXTURES:
        result = check.run(placement, constraints)
        for issue in result.issues:
            seen_check_names.add(issue.check_name)

    expected = {check.name for check, _, _ in _BAD_FIXTURES}
    missing = expected - seen_check_names
    assert not missing, (
        f"the following checks never appeared in ANY fixture's output -- "
        f"presumptively vacuous again: {sorted(missing)}"
    )


@pytest.mark.parametrize("check,placement,constraints", _BAD_FIXTURES, ids=lambda v: getattr(v, "name", None) or "")
def test_each_bad_fixture_makes_its_own_check_fire(
    check: Check, placement: Placement, constraints: ConstraintSet
) -> None:
    """Per-fixture pin: the check the fixture was built for must fire on
    it specifically (not merely somewhere in the aggregate corpus)."""
    result = check.run(placement, constraints)
    fired_names = {issue.check_name for issue in result.issues}
    assert check.name in fired_names, (
        f"{check.name} was expected to fire on its own targeted bad fixture "
        f"and did not (got passed={result.passed}, issues={result.issues})"
    )


def test_clean_board_has_no_violations() -> None:
    """The pass-side complement: a deliberately unremarkable board produces
    zero issues from any delegating check -- the corpus is not rigged so
    that everything always fires regardless of input."""
    for check, _bad_placement, _bad_constraints in _BAD_FIXTURES:
        result = check.run(_CLEAN_PLACEMENT, _CLEAN_CONSTRAINTS)
        assert result.passed is True, (
            f"{check.name} reported passed=False on the clean board: {result.issues}"
        )
        assert result.issues == [], (
            f"{check.name} reported issues on the clean board: {result.issues}"
        )


def test_power_domain_check_never_reports_passed_true() -> None:
    """PowerDomainCheck must report not-run for EVERY input, never a pass.

    Run across the same varied corpus (each fixture's own placement) plus
    an empty board and the clean board -- passed=True must never appear,
    and every result must carry the INFO not-run marker (ERC_PWR_000),
    distinct from both a clean pass and a real ERROR/CRITICAL failure.
    """
    check = PowerDomainCheck()
    placements = (
        [(p, c) for _chk, p, c in _BAD_FIXTURES]
        + [(_CLEAN_PLACEMENT, _CLEAN_CONSTRAINTS)]
        + [(Placement(board_width=100, board_height=100), ConstraintSet())]
    )
    for placement, constraints in placements:
        result = check.run(placement, constraints)
        assert result.passed is False, (
            "PowerDomainCheck must never report passed=True (it cannot run: "
            "erc_power_domain has no Rust registration to delegate to)"
        )
        assert len(result.issues) == 1
        issue = result.issues[0]
        assert issue.code == "ERC_PWR_000"
        assert issue.severity == Severity.INFO, (
            "the not-run marker must be INFO severity, distinguishable from "
            "a real ERROR/CRITICAL failure"
        )
        assert issue.details.get("not_run") is True


def test_via_and_trace_fixtures_hit_a_preexisting_dict_key_bug() -> None:
    """Documents (does not fix) a real, independent, pre-existing bug that
    blocks exercising ViaSpacingCheck/TraceClearanceCheck through the
    Placement contract.

    ``drc_runner._placement_to_board_dict`` builds each via dict with keys
    ``position``/``diameter``/``net_name``; ``temper_drc_rs``'s
    ``extract_via`` (``board_py_bridge.rs``) requires ``x``/``y``/``pad``/
    ``net``. The two never overlap, so ANY placement with vias (or,
    identically, traces) raises before any DRC rule runs at all -- this
    affects EVERY delegating check's ``run()`` when vias/traces are
    present, not only the via/trace-specific ones, and it also affects the
    production ``CheckRunner.run()`` path (``drc_runner.py``), which shares
    the same builder.

    Out of scope for the vacuity remediation this file guards (a schema/
    key-mismatch bug is a different defect class from "hardcodes a
    passing result"), but pinned here so ``ViaSpacingCheck`` /
    ``TraceClearanceCheck``'s absence from the per-check vacuity guard
    above is a documented, re-discoverable fact instead of a silent gap.
    """
    placement = Placement(
        components={"C1": _comp("C1", 10, 10)},
        board_width=100,
        board_height=100,
        via_placement=ViaPlacement(
            vias=[
                Via(
                    position=(5.0, 5.0),
                    from_layer="F.Cu",
                    to_layer="B.Cu",
                    diameter=0.6,
                    drill=0.3,
                    net_name="N1",
                ),
                Via(
                    position=(5.2, 5.0),
                    from_layer="F.Cu",
                    to_layer="B.Cu",
                    diameter=0.6,
                    drill=0.3,
                    net_name="N2",
                ),
            ]
        ),
    )
    with pytest.raises(ValueError, match="missing required key: net"):
        ViaSpacingCheck().run(placement, ConstraintSet())
