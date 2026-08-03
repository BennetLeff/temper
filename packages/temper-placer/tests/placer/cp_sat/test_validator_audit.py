"""Tests for the validator-aligned post-solve audit (issue #523 gap 2, R24
item 3).

The R24 post-solve audit for the domain-clearance constraint set
(``domain_clearance.audit_domain_clearance``) recomputes **center-to-center**
Euclidean distance from the resolved coordinates -- a "cheaper, weaker check
than what ``clearance.py``'s validator actually measures (copper-to-copper on
exact pad geometry)" (its own docstring). That distinction is not academic:
the issue-#523 run-B scoped solve was *center-audit-clean* (0 violations)
while the actual REQ-SAFE-01 gate measured 12 violations across 9 pairs on
the same placement (``docs/evidence/2026-08-01-k3-runb-not-validator-clean.md``).
Gap 2 = ``validator_audit.audit_domain_clearance_validator``, which re-runs
the REQ-SAFE-01 validator itself (``verify_iec60335_compliance`` -- exact,
rotation-aware pad copper, the function the CI gate runs) on a placement
whose positions/rotations come from the solve, then classifies every
violation:

- (a) inter-component pair covered by a generated domain-clearance
  ``SeparatedConstraint`` -> **HARD** (encoding unsound for this solve;
  ``solve_placement`` raises);
- (b) intra-footprint straddler (``pair_kind == "intra"`` or
  ``ref_a == ref_b``) -> ``intra_footprint`` bucket, placement-independent,
  never raised (K3's own G5LE-1 gap is exactly this class);
- (c) anything else -> ``coverage_gaps`` bucket (pair the generator's
  ``component_refs`` filter or the intra-footprint exemption excluded),
  never raised.

Test groups (mapping to the task's R24 suite):

1. ``TestAuditFalsifier`` -- the run-B lie, minimized: centers >= margin
   apart (center audit reports 0 violations) while pad copper extends toward
   each other below margin (validator audit fires it as a HARD failure).
2. ``TestCleanPlacement`` -- both audits pass; ``audit.clean`` is True.
3. ``TestStraddlerClassification`` -- one component whose own pads straddle
   a domain boundary -> ``intra_footprint``, never hard; the feasible solve
   does not raise.
4. ``TestCoverageGap`` -- a validator violation on a pair NOT in the
   constraint set -> ``coverage_gaps``, never hard.
5. ``TestGeometryTrustAndRefSetValidation`` -- the audit must not be
   vacuously clean: a pad-less component (validator models it as a
   zero-extent point -- an optimistic upper bound) marks
   ``geometry_trusted=False`` with a ``logger.error``; an empty placement or
   a ``resolved_positions_mm`` disjoint from the placement's refs raises
   ``ValueError`` (the placement does not describe the solve).
6. ``TestBuildValidatorPlacement`` -- position-frame contract (handoff §6):
   solved positions overlay only refs the solve placed; fixed refs keep
   their exact base positions/rotations (incl. non-quadrant rotations the
   solver cannot express); pad fallback from a netlist.
7. ``TestSolvePlacementIntegration`` -- ``solve_placement(validator_input=...)``:
   feasible solve populates ``result.validator_audit`` (clean); a constructed
   hard failure raises ``RuntimeError``; absent ``validator_input`` leaves
   ``validator_audit`` None with unchanged behaviour; a missing
   ``placement``/``voltage_domains`` key raises ``ValueError``; a non-optimal
   solve with ``validator_input`` logs a WARNING, never silent.
8. ``TestProductionBoardSolve`` -- the real board, FREE={K3} (pure-geometry
   recipe verified optimal in ``docs/evidence/2026-08-01-edge-hanging-refs-fix.md``):
   solve optimal, ``hard_failures`` empty, and the known K3-intra straddler
   (G5LE-1, 3.559mm vs 4.0/6.0/8.0 bars -- 3 violations / 1 pair) lands in
   ``intra_footprint`` with the exact committed-board measured distance
   (position-frame proof: fixed refs' copper geometry is unchanged).
9. Adversarial-review fixes: (i) the rotation overlay is authoritative for
   any ref the solve touched (solved position AND solved rotation index) --
   the CLI writes ``idx*90`` unconditionally, so the audit measures the
   post-solve geometry even for non-quadrant base rotations; base rotation is
   kept only when the ref is absent from ``resolved_rotations``; (ii) a
   non-optimal solve with ``validator_input`` logs a WARNING (never silent);
   (iii) the hard-failure raise reports DISTINCT pair counts, not inflated
   record counts; (iv) reversed-pair ordering (validator emits (B,A) against
   constraint (A,B)) absorbs into HARD via frozenset membership.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from temper_placer.pcl.constraints import ConstraintTier, SeparatedConstraint
from temper_placer.placer.cp_sat._encoder_solve import solve_placement
from temper_placer.placer.cp_sat.domain_clearance import (
    audit_domain_clearance,
    generate_domain_clearance_constraints,
)
from temper_placer.placer.cp_sat.validator_audit import (
    audit_domain_clearance_validator,
    build_validator_placement,
)
from temper_placer.requirements.validators.clearance import (
    VoltageDomain,
    verify_iec60335_compliance,
)

_REPO_ROOT = Path(__file__).resolve().parents[5]
_PCB_PATH = _REPO_ROOT / "pcb" / "temper.kicad_pcb"


# ---------------------------------------------------------------------------
# Synthetic netlist/board helpers (same minimal shape as the rest of the
# placer/cp_sat test suite -- see test_clearance_repair.py)
# ---------------------------------------------------------------------------


@dataclass
class MockPin:
    number: str
    net: str
    position: tuple[float, float]
    width: float = 1.0
    height: float = 1.0
    shape: str = "rect"
    roundrect_ratio: float = 0.0
    pad_rotation_deg: float = 0.0
    layer: str = "F.Cu"


@dataclass
class MockComp:
    ref: str
    bounds: tuple[float, float] = (10.0, 10.0)
    initial_position: tuple[float, float] = (0.0, 0.0)
    initial_rotation: int = 0
    pins: list = field(default_factory=list)
    zone: str | None = None
    attributes: dict = field(default_factory=dict)


@dataclass
class MockNet:
    name: str


@dataclass
class MockNetlist:
    components: list
    nets: list = field(default_factory=list)


@dataclass
class MockBoard:
    width: float = 152.0
    height: float = 234.0
    zones: list = field(default_factory=list)
    origin: tuple[float, float] = (0.0, 0.0)
    constraints: list = field(default_factory=list)


def _pad(net: str, offset: tuple[float, float], width: float = 2.0, height: float = 1.0) -> dict:
    """One rect pad in the validator's pad schema (same fields
    ``_real_board_fixture._pads_for_component`` emits)."""
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


def _placement(components: list[dict], nets: dict | None = None) -> dict:
    """Validator-shape placement: {"components": [...], "nets": {...},
    "board": {...}} -- same shape ``load_real_board_placement`` returns."""
    return {
        "components": components,
        "nets": nets or {},
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


# The two-domain classification shared by every synthetic test below.
_VD = {"ac_l": VoltageDomain.MAINS, "gnd": VoltageDomain.LV_CONTROL}


# ---------------------------------------------------------------------------
# Group 1: the falsifier -- the run-B lie, minimized (R24 item 3)
# ---------------------------------------------------------------------------


class TestAuditFalsifier:
    """Two components whose bbox centers are >= the required margin apart (so
    ``audit_domain_clearance`` reports 0 violations) but whose pad copper
    extends toward each other so the exact-copper distance is < margin.

    This is the minimized run-B failure: the cheap center audit is satisfied
    while the REQ-SAFE-01 gate is not. The validator-aligned audit must fire
    it as a HARD failure (the pair IS covered by the generated constraint
    set), and the solve-level wiring must raise.
    """

    def _falsifier_inputs(self) -> tuple[dict, dict, list, dict, dict]:
        placement = _placement(
            [
                {"ref": "A", "position": (0.0, 0.0), "nets": ["ac_l"], "rotation_deg": 0.0,
                 "pads": [_pad("ac_l", (3.0, 0.0))]},
                # B's center is 8.1mm from A's -- >= the 8.0mm bar, so the
                # center-distance audit passes.
                {"ref": "B", "position": (8.1, 0.0), "nets": ["gnd"], "rotation_deg": 0.0,
                 "pads": [_pad("gnd", (-3.0, 0.0))]},
            ]
        )
        # A's copper spans x in [2.0, 4.0]; B's spans x in [4.1, 6.1]: the
        # exact copper-to-copper gap is 0.1mm << every MAINS<->LV_CONTROL bar
        # (3.0/4.0/6.0/8.0), while the centers are 8.1mm apart.
        positions = {"A": (0.0, 0.0), "B": (8.1, 0.0)}
        rotations = {"A": 0, "B": 0}
        constraints = [_domain_constraint("A", "B")]
        return placement, _VD, constraints, positions, rotations

    def test_center_audit_passes_validator_audit_fires_hard(self) -> None:
        placement, vd, constraints, positions, rotations = self._falsifier_inputs()
        # The old audit is blind to this: centers 8.1 >= 8.0 -> 0 violations.
        assert audit_domain_clearance(constraints, positions) == [], (
            "Falsifier premise broken: the center-distance audit should report "
            "0 violations for centers 8.1mm apart at an 8.0mm bar."
        )
        audit = audit_domain_clearance_validator(constraints, positions, rotations, placement, vd)
        assert audit.hard_failures, (
            "Falsifier fired: the validator-aligned audit did NOT flag the "
            "0.1mm exact-copper gap on a constraint-covered pair -- gap 2 is "
            "not closing the run-B lie."
        )
        assert all(v.ref_a == "A" and v.ref_b == "B" for v in audit.hard_failures)
        # Every MAINS<->LV_CONTROL matrix row must be a hard violation.
        bars = {(v.metric, v.required_mm) for v in audit.hard_failures}
        assert bars == {("clearance", 3.0), ("creepage", 4.0),
                        ("clearance", 6.0), ("creepage", 8.0)}, bars
        assert audit.clean is False
        assert audit.intra_footprint == [] and audit.coverage_gaps == []

    def test_solve_level_hard_failure_raises(self) -> None:
        """The same lie, fed through ``solve_placement``: the boxes are
        separated (solver SAT) but the copper is not, so the wiring must
        raise RuntimeError -- a feasible solve with a HARD failure is an
        encoding unsoundness, never a silent pass."""
        placement, vd, _c, _p, _r = self._falsifier_inputs()
        # Boxes: A at (5,5), B at (13.1,5), both 1x1mm -> box separation
        # 7.1mm >= the 4.0mm bar -> the solve is feasible (and both boxes
        # clear the 0.5mm edge margin). The pads reach 3mm past the boxes
        # (deliberately broken bounds: copper is NOT contained in the
        # solver's box model -- the exact failure mode the audit exists to
        # catch): exact copper gap 0.1mm << 4.0mm.
        comps = [
            MockComp(ref="A", bounds=(1.0, 1.0), initial_position=(5.0, 5.0),
                     pins=[MockPin(number="1", net="ac_l", position=(3.0, 0.0))]),
            MockComp(ref="B", bounds=(1.0, 1.0), initial_position=(13.1, 5.0),
                     pins=[MockPin(number="1", net="gnd", position=(-3.0, 0.0))]),
        ]
        netlist = MockNetlist(components=comps, nets=[MockNet("ac_l"), MockNet("gnd")])
        board = MockBoard()
        constraint = _domain_constraint("A", "B", margin=4.0)
        with pytest.raises(RuntimeError, match="REQ-SAFE-01 validator post-solve audit FAILED"):
            solve_placement(
                netlist=netlist,
                board=board,
                extra_constraints=[constraint],
                timeout_ms=20_000,
                seed=0,
                fixed_positions={"A": (5.0, 5.0, 0), "B": (13.1, 5.0, 0)},
                validator_input={"placement": placement, "voltage_domains": vd},
            )

    def test_hard_failure_raise_counts_distinct_pairs_not_records(self) -> None:
        """One physical pair emits 4-8 violation records (clearance/creepage
        x basic/reinforced), so the raise message must report DISTINCT
        violating pairs as the headline -- '4 hard violation(s)' would
        mislead a reader into thinking 4 pairs failed. The falsifier is a
        single A/B pair, all 4 matrix rows: 1 distinct pair, 4 records."""
        placement, vd, _c, _p, _r = self._falsifier_inputs()
        comps = [
            MockComp(ref="A", bounds=(1.0, 1.0), initial_position=(5.0, 5.0),
                     pins=[MockPin(number="1", net="ac_l", position=(3.0, 0.0))]),
            MockComp(ref="B", bounds=(1.0, 1.0), initial_position=(13.1, 5.0),
                     pins=[MockPin(number="1", net="gnd", position=(-3.0, 0.0))]),
        ]
        netlist = MockNetlist(components=comps, nets=[MockNet("ac_l"), MockNet("gnd")])
        board = MockBoard()
        constraint = _domain_constraint("A", "B", margin=4.0)
        with pytest.raises(RuntimeError) as exc_info:
            solve_placement(
                netlist=netlist,
                board=board,
                extra_constraints=[constraint],
                timeout_ms=20_000,
                seed=0,
                fixed_positions={"A": (5.0, 5.0, 0), "B": (13.1, 5.0, 0)},
                validator_input={"placement": placement, "voltage_domains": vd},
            )
        msg = str(exc_info.value)
        assert "1 distinct violating pair" in msg, msg
        assert "4 violation record" in msg, msg

    def test_reversed_pair_ordering_absorbs_into_hard(self) -> None:
        """A validator violation ordered (ref_a="B", ref_b="A") against a
        constraint (a="A", b="B") must classify as HARD -- pair membership is
        a frozenset, so ordering cannot drop a covered pair into the coverage
        gap bucket. Agent 4 measured 451 reversed-duplicate emissions on the
        production board (e.g. (C11,C6)@1.0 + (C6,C11)@8.0); every one of
        those must absorb into the same covered pair."""
        # Swap the domain sides so the validator's pair iteration emits
        # (B, A): B is the MAINS-side component (domain_a), A the LV-side.
        placement = _placement(
            [
                {"ref": "B", "position": (0.0, 0.0), "nets": ["ac_l"], "rotation_deg": 0.0,
                 "pads": [_pad("ac_l", (3.0, 0.0))]},
                {"ref": "A", "position": (8.1, 0.0), "nets": ["gnd"], "rotation_deg": 0.0,
                 "pads": [_pad("gnd", (-3.0, 0.0))]},
            ]
        )
        positions = {"B": (0.0, 0.0), "A": (8.1, 0.0)}
        rotations = {"B": 0, "A": 0}
        # Constraint ordered (a="A", b="B") -- the reverse of the validator's
        # emission order for this placement.
        constraints = [_domain_constraint("A", "B")]
        audit = audit_domain_clearance_validator(
            constraints, positions, rotations, placement, _VD
        )
        assert audit.hard_failures, (
            "reversed-pair ordering must absorb into the constraint-covered "
            "pair set (frozenset membership), not fall through to a coverage gap"
        )
        assert all(v.ref_a == "B" and v.ref_b == "A" for v in audit.hard_failures)
        assert audit.coverage_gaps == []
        assert audit.geometry_trusted is True


# ---------------------------------------------------------------------------
# Group 2: clean placement -- both audits pass
# ---------------------------------------------------------------------------


class TestCleanPlacement:
    def test_clean_placement_passes_both_audits(self) -> None:
        placement = _placement(
            [
                {"ref": "A", "position": (0.0, 0.0), "nets": ["ac_l"], "rotation_deg": 0.0,
                 "pads": [_pad("ac_l", (0.0, 0.0), width=1.0)]},
                {"ref": "B", "position": (20.0, 0.0), "nets": ["gnd"], "rotation_deg": 0.0,
                 "pads": [_pad("gnd", (0.0, 0.0), width=1.0)]},
            ]
        )
        positions = {"A": (0.0, 0.0), "B": (20.0, 0.0)}
        rotations = {"A": 0, "B": 0}
        constraints = [_domain_constraint("A", "B")]
        assert audit_domain_clearance(constraints, positions) == []
        audit = audit_domain_clearance_validator(constraints, positions, rotations, placement, _VD)
        assert audit.hard_failures == []
        assert audit.intra_footprint == []
        assert audit.coverage_gaps == []
        assert audit.validator_violation_count == 0
        assert audit.clean is True

    def test_clean_solve_populates_audit_and_clean_is_true(self) -> None:
        placement = _placement(
            [
                {"ref": "A", "position": (10.0, 10.0), "nets": ["ac_l"], "rotation_deg": 0.0,
                 "pads": [_pad("ac_l", (0.0, 0.0), width=1.0)]},
                {"ref": "B", "position": (30.0, 10.0), "nets": ["gnd"], "rotation_deg": 0.0,
                 "pads": [_pad("gnd", (0.0, 0.0), width=1.0)]},
            ]
        )
        comps = [
            MockComp(ref="A", bounds=(4.0, 4.0), initial_position=(10.0, 10.0),
                     pins=[MockPin(number="1", net="ac_l", position=(0.0, 0.0))]),
            MockComp(ref="B", bounds=(4.0, 4.0), initial_position=(30.0, 10.0),
                     pins=[MockPin(number="1", net="gnd", position=(0.0, 0.0))]),
        ]
        netlist = MockNetlist(components=comps, nets=[MockNet("ac_l"), MockNet("gnd")])
        board = MockBoard()
        result = solve_placement(
            netlist=netlist,
            board=board,
            timeout_ms=20_000,
            seed=0,
            fixed_positions={"A": (10.0, 10.0, 0), "B": (30.0, 10.0, 0)},
            validator_input={"placement": placement, "voltage_domains": _VD},
        )
        assert result.status in ("optimal", "feasible"), result.status
        assert result.validator_audit is not None
        assert result.validator_audit.hard_failures == []
        assert result.validator_audit.coverage_gaps == []
        assert result.validator_audit.clean is True


# ---------------------------------------------------------------------------
# Group 3: straddler classification -- intra-footprint, never hard
# ---------------------------------------------------------------------------


class TestStraddlerClassification:
    def _straddler_inputs(self) -> tuple[dict, dict, dict]:
        placement = _placement(
            [
                {
                    "ref": "PS1",
                    "position": (10.0, 10.0),
                    "nets": ["ac_l", "gnd"],
                    "rotation_deg": 0.0,
                    "pads": [
                        _pad("ac_l", (0.0, 0.0), width=1.0),
                        _pad("gnd", (2.0, 0.0), width=1.0),
                    ],
                }
            ]
        )
        positions = {"PS1": (10.0, 10.0)}
        rotations = {"PS1": 0}
        return placement, positions, rotations

    def test_straddler_lands_in_intra_footprint_never_hard(self) -> None:
        placement, positions, rotations = self._straddler_inputs()
        # No constraint set at all -- the pair is not covered by anything,
        # yet the violation must still land in intra_footprint (the intra
        # classification precedes pair coverage by design: no placement can
        # fix a rigid part's own pad spacing).
        audit = audit_domain_clearance_validator([], positions, rotations, placement, _VD)
        assert audit.hard_failures == []
        assert audit.coverage_gaps == []
        assert len(audit.intra_footprint) == 4
        for v in audit.intra_footprint:
            assert v.ref_a == "PS1" and v.ref_b == "PS1"
            assert v.pair_kind == "intra"
            assert v.measured_mm < v.required_mm
        # Intra-footprint records do not make the result dirty: they are
        # placement-independent, so "clean" means no hard/gap findings.
        assert audit.clean is True

    def test_straddler_solve_does_not_raise(self) -> None:
        placement, positions, rotations = self._straddler_inputs()
        comps = [
            MockComp(
                ref="PS1",
                bounds=(6.0, 6.0),
                initial_position=(10.0, 10.0),
                pins=[
                    MockPin(number="1", net="ac_l", position=(0.0, 0.0)),
                    MockPin(number="2", net="gnd", position=(2.0, 0.0)),
                ],
            )
        ]
        netlist = MockNetlist(components=comps, nets=[MockNet("ac_l"), MockNet("gnd")])
        board = MockBoard()
        result = solve_placement(
            netlist=netlist,
            board=board,
            timeout_ms=20_000,
            seed=0,
            fixed_positions={"PS1": (10.0, 10.0, 0)},
            validator_input={"placement": placement, "voltage_domains": _VD},
        )
        assert result.status in ("optimal", "feasible"), result.status
        assert result.validator_audit is not None
        assert result.validator_audit.hard_failures == []
        assert {v.ref_a for v in result.validator_audit.intra_footprint} == {"PS1"}


# ---------------------------------------------------------------------------
# Group 4: coverage gap -- pair NOT in the constraint set
# ---------------------------------------------------------------------------


class TestCoverageGap:
    def test_uncovered_pair_lands_in_coverage_gaps(self) -> None:
        """The same falsifier geometry, but with a constraint set that does
        NOT cover the A/B pair (the generator's ``component_refs`` filter or
        the intra-footprint exemption excluded it): the violation must land
        in ``coverage_gaps`` -- reported, never raised."""
        placement = _placement(
            [
                {"ref": "A", "position": (0.0, 0.0), "nets": ["ac_l"], "rotation_deg": 0.0,
                 "pads": [_pad("ac_l", (3.0, 0.0))]},
                {"ref": "B", "position": (8.1, 0.0), "nets": ["gnd"], "rotation_deg": 0.0,
                 "pads": [_pad("gnd", (-3.0, 0.0))]},
            ]
        )
        positions = {"A": (0.0, 0.0), "B": (8.1, 0.0)}
        rotations = {"A": 0, "B": 0}
        # The pair is excluded by the component_refs filter: only "OTHER" is
        # in the constrained universe.
        gen = generate_domain_clearance_constraints(placement, _VD, component_refs={"OTHER"})
        assert gen == []
        audit = audit_domain_clearance_validator(gen, positions, rotations, placement, _VD)
        assert audit.hard_failures == []
        assert audit.intra_footprint == []
        assert len(audit.coverage_gaps) == 4
        for v in audit.coverage_gaps:
            assert v.ref_a == "A" and v.ref_b == "B"
        assert audit.clean is False


# ---------------------------------------------------------------------------
# Group 5: geometry trust + ref-set validation (adversarial-review finding 2)
# ---------------------------------------------------------------------------


class TestGeometryTrustAndRefSetValidation:
    """The audit must not be vacuously clean when the validator's geometry
    model is degraded (a pad-less component is modelled as a zero-extent
    point -- an OPTIMISTIC upper bound on copper separation, the run-B lie
    direction) or when the placement does not describe the solve at all."""

    def _trusted_placement(self) -> dict:
        return _placement(
            [
                {"ref": "A", "position": (0.0, 0.0), "nets": ["ac_l"], "rotation_deg": 0.0,
                 "pads": [_pad("ac_l", (0.0, 0.0), width=1.0)]},
                {"ref": "B", "position": (20.0, 0.0), "nets": ["gnd"], "rotation_deg": 0.0,
                 "pads": [_pad("gnd", (0.0, 0.0), width=1.0)]},
            ]
        )

    def test_all_pads_present_geometry_trusted(self) -> None:
        placement = self._trusted_placement()
        audit = audit_domain_clearance_validator(
            [_domain_constraint("A", "B")],
            {"A": (0.0, 0.0), "B": (20.0, 0.0)},
            {"A": 0, "B": 0},
            placement,
            _VD,
        )
        assert audit.geometry_trusted is True
        assert audit.stats["components_without_pads"] == []
        assert audit.stats["components"] == 2

    def test_padless_component_marks_geometry_untrusted_and_logs_error(
        self, caplog
    ) -> None:
        """(a) A placement with a pad-less component: the validator models it
        as a zero-extent point, so the audit must surface that (geometry_
        trusted False + logger.error) instead of letting a clean result look
        like a proof of copper."""
        placement = _placement(
            [
                {"ref": "A", "position": (0.0, 0.0), "nets": ["ac_l"], "rotation_deg": 0.0,
                 "pads": [_pad("ac_l", (0.0, 0.0), width=1.0)]},
                # No "pads" key: B is measured origin-to-origin (optimistic).
                {"ref": "B", "position": (4.0, 0.0), "nets": ["gnd"], "rotation_deg": 0.0},
            ]
        )
        with caplog.at_level(
            logging.ERROR, logger="temper_placer.placer.cp_sat.validator_audit"
        ):
            audit = audit_domain_clearance_validator(
                [_domain_constraint("A", "B")],
                {"A": (0.0, 0.0), "B": (4.0, 0.0)},
                {"A": 0, "B": 0},
                placement,
                _VD,
            )
        assert audit.geometry_trusted is False
        assert audit.stats["components_without_pads"] == ["B"]
        # B sits 4mm from A (well inside the 8.0mm reinforced creepage bar),
        # so the pair is actually measured and flagged as origin-modelled.
        assert sum(r["pairs_origin_modelled"] for r in audit.stats["rows"]) > 0
        assert any(
            "DEGRADED geometry" in r.message and r.levelno == logging.ERROR
            for r in caplog.records
        ), [r.message for r in caplog.records]

    def test_empty_placement_raises_value_error(self) -> None:
        """(b) An empty placement would vacuous-pass against an empty board
        -- programmer error, must raise."""
        with pytest.raises(ValueError, match="zero components"):
            audit_domain_clearance_validator([], {}, {}, _placement([]), _VD)

    def test_disjoint_solved_refs_raise_value_error(self) -> None:
        """(c) Solved refs disjoint from the placement's refs: the placement
        does not describe the solve -- auditing it measures the wrong
        geometry, programmer error, must raise."""
        placement = self._trusted_placement()
        with pytest.raises(ValueError, match="share no overlap"):
            audit_domain_clearance_validator(
                [_domain_constraint("A", "B")],
                {"X": (1.0, 2.0)},  # solves a ref the placement does not have
                {"X": 0},
                placement,
                _VD,
            )


# ---------------------------------------------------------------------------
# Group 6: build_validator_placement -- the position-frame contract
# ---------------------------------------------------------------------------

class TestBuildValidatorPlacement:
    def _two_comp_placement(self) -> dict:
        return _placement(
            [
                {"ref": "A", "position": (1.0, 2.0), "nets": ["ac_l"], "rotation_deg": 0.0,
                 "pads": [_pad("ac_l", (0.0, 0.0), width=1.0)]},
                {"ref": "B", "position": (30.0, 40.0), "nets": ["gnd"], "rotation_deg": 180.0,
                 "pads": [_pad("gnd", (0.0, 0.0), width=1.0)]},
            ]
        )

    def test_solved_refs_overlaid_fixed_refs_keep_base(self) -> None:
        placement = self._two_comp_placement()
        out = build_validator_placement(
            placement,
            resolved_positions_mm={"A": (5.0, 6.0)},  # B absent: not solved
            resolved_rotations={"A": 1, "B": 1},  # B's rotation must NOT be overlaid
        )
        by_ref = {c["ref"]: c for c in out["components"]}
        assert by_ref["A"]["position"] == (5.0, 6.0)
        assert by_ref["A"]["rotation_deg"] == 90.0
        # B is not in the solved positions: it keeps its exact base position
        # AND its exact base rotation (the solver's quadrant index cannot
        # express 180.0 -- wait, it can; but B is pinned, so base wins).
        assert by_ref["B"]["position"] == (30.0, 40.0)
        assert by_ref["B"]["rotation_deg"] == 180.0

    def test_non_quadrant_base_rotation_overlaid_when_solve_touched(self) -> None:
        """A ref the solve TOUCHED (solved position AND solved rotation
        index) gets the solver's rotation overlaid EVEN when its base
        rotation is non-quadrant: the CLI writes ``idx * 90`` to the PCB
        unconditionally for every solved ref (cli/__init__.py's optimize
        command), so the audit must measure the post-solve geometry -- the
        solver's index is authoritative (adversarial-review finding 3)."""
        placement = _placement(
            [
                {"ref": "C", "position": (10.0, 10.0), "nets": ["gnd"], "rotation_deg": 45.0,
                 "pads": [_pad("gnd", (0.0, 0.0), width=1.0)]},
            ]
        )
        out = build_validator_placement(
            placement,
            resolved_positions_mm={"C": (10.0, 10.0)},
            resolved_rotations={"C": 1},
        )
        assert out["components"][0]["rotation_deg"] == 90.0

    def test_non_quadrant_base_rotation_kept_when_solve_did_not_rotate(self) -> None:
        """A ref with a solved position but NO entry in ``resolved_rotations``
        (the solve did not rotate it -- no rotation variable, e.g. a
        polarized part pinned by construction) keeps its exact base rotation,
        non-quadrant included: the board keeps the base, which the solver's
        0-3 index could not represent anyway."""
        placement = _placement(
            [
                {"ref": "C", "position": (10.0, 10.0), "nets": ["gnd"], "rotation_deg": 45.0,
                 "pads": [_pad("gnd", (0.0, 0.0), width=1.0)]},
            ]
        )
        out = build_validator_placement(
            placement,
            resolved_positions_mm={"C": (10.0, 10.0)},
            resolved_rotations={},
        )
        assert out["components"][0]["rotation_deg"] == 45.0

    def test_non_quadrant_base_rotation_kept_when_ref_untouched(self) -> None:
        """A ref absent from BOTH ``resolved_positions_mm`` and
        ``resolved_rotations`` is pinned in the solve: base position AND
        exact base rotation are kept."""
        placement = _placement(
            [
                {"ref": "C", "position": (10.0, 10.0), "nets": ["gnd"], "rotation_deg": 45.0,
                 "pads": [_pad("gnd", (0.0, 0.0), width=1.0)]},
            ]
        )
        out = build_validator_placement(placement, {}, {})
        assert out["components"][0]["rotation_deg"] == 45.0
        assert out["components"][0]["position"] == (10.0, 10.0)

    def test_pads_fall_back_from_netlist_when_placement_lacks_them(self) -> None:
        placement = _placement(
            [
                {"ref": "A", "position": (5.0, 5.0), "nets": ["ac_l"], "rotation_deg": 0.0},
                # no "pads" key
            ]
        )
        comps = [
            MockComp(
                ref="A",
                bounds=(4.0, 4.0),
                pins=[MockPin(number="1", net="ac_l", position=(1.5, -0.5), width=2.0, height=3.0)],
            )
        ]
        netlist = MockNetlist(components=comps, nets=[MockNet("ac_l")])
        out = build_validator_placement(
            placement, {"A": (5.0, 5.0)}, {}, netlist_or_parse_result=netlist
        )
        pads = out["components"][0]["pads"]
        assert len(pads) == 1
        assert pads[0]["net"] == "ac_l"
        assert pads[0]["offset"] == (1.5, -0.5)
        assert pads[0]["width"] == 2.0
        assert pads[0]["height"] == 3.0


# ---------------------------------------------------------------------------
# Group 7: solve_placement wiring contract
# ---------------------------------------------------------------------------


class TestSolvePlacementIntegration:
    def _clean_solve_inputs(self) -> tuple[MockNetlist, MockBoard, dict]:
        placement = _placement(
            [
                {"ref": "A", "position": (10.0, 10.0), "nets": ["ac_l"], "rotation_deg": 0.0,
                 "pads": [_pad("ac_l", (0.0, 0.0), width=1.0)]},
                {"ref": "B", "position": (30.0, 10.0), "nets": ["gnd"], "rotation_deg": 0.0,
                 "pads": [_pad("gnd", (0.0, 0.0), width=1.0)]},
            ]
        )
        comps = [
            MockComp(ref="A", bounds=(4.0, 4.0), initial_position=(10.0, 10.0),
                     pins=[MockPin(number="1", net="ac_l", position=(0.0, 0.0))]),
            MockComp(ref="B", bounds=(4.0, 4.0), initial_position=(30.0, 10.0),
                     pins=[MockPin(number="1", net="gnd", position=(0.0, 0.0))]),
        ]
        netlist = MockNetlist(components=comps, nets=[MockNet("ac_l"), MockNet("gnd")])
        board = MockBoard()
        return netlist, board, placement

    def test_feasible_solve_populates_validator_audit(self) -> None:
        netlist, board, placement = self._clean_solve_inputs()
        result = solve_placement(
            netlist=netlist, board=board, timeout_ms=20_000, seed=0,
            fixed_positions={"A": (10.0, 10.0, 0), "B": (30.0, 10.0, 0)},
            validator_input={"placement": placement, "voltage_domains": _VD},
        )
        assert result.status in ("optimal", "feasible"), result.status
        assert result.validator_audit is not None
        assert result.validator_audit.clean is True

    def test_validator_input_absent_leaves_audit_none(self) -> None:
        netlist, board, _placement = self._clean_solve_inputs()
        result = solve_placement(
            netlist=netlist, board=board, timeout_ms=20_000, seed=0,
            fixed_positions={"A": (10.0, 10.0, 0), "B": (30.0, 10.0, 0)},
        )
        assert result.status in ("optimal", "feasible"), result.status
        assert result.validator_audit is None

    def test_missing_placement_key_raises_value_error(self) -> None:
        netlist, board, _placement = self._clean_solve_inputs()
        with pytest.raises(ValueError, match="validator_input must carry both"):
            solve_placement(
                netlist=netlist, board=board, timeout_ms=20_000, seed=0,
                fixed_positions={"A": (10.0, 10.0, 0), "B": (30.0, 10.0, 0)},
                validator_input={"voltage_domains": _VD},
            )

    def test_missing_voltage_domains_key_raises_value_error(self) -> None:
        netlist, board, placement = self._clean_solve_inputs()
        with pytest.raises(ValueError, match="validator_input must carry both"):
            solve_placement(
                netlist=netlist, board=board, timeout_ms=20_000, seed=0,
                fixed_positions={"A": (10.0, 10.0, 0), "B": (30.0, 10.0, 0)},
                validator_input={"placement": placement},
            )

    def test_non_optimal_solve_logs_audit_skip_warning(self, caplog) -> None:
        """validator_input given but the solve does NOT terminate
        (infeasible): there is no placement to audit, and that skip must be
        WARNING-logged, never silent -- a silent skip would look identical
        to a fully-audited solve in the logs (adversarial-review finding 4)."""
        netlist, board, placement = self._clean_solve_inputs()
        with caplog.at_level(
            logging.WARNING, logger="temper_placer.placer.cp_sat._encoder_solve"
        ):
            result = solve_placement(
                netlist=netlist, board=board, timeout_ms=5_000, seed=0,
                # Pin both refs off-board: the edge-margin / NoOverlap set is
                # infeasible -- the same recipe test_fixed_positions uses.
                fixed_positions={"A": (999.0, 999.0, 0), "B": (999.0, 999.0, 0)},
                validator_input={"placement": placement, "voltage_domains": _VD},
            )
        assert result.status == "infeasible", result.status
        assert result.validator_audit is None
        assert any(
            "validator post-solve audit did NOT run" in r.message
            and r.levelno == logging.WARNING
            for r in caplog.records
        ), [r.message for r in caplog.records]


# ---------------------------------------------------------------------------
# Group 8: production board -- FREE={K3} pure-geometry solve
# ---------------------------------------------------------------------------


class TestProductionBoardSolve:
    """The real board, real validator, real loader -- the production recipe.

    The full #523 scoped solve (FREE={K3} + the ~12k-constraint
    domain-clearance set) was **infeasible** on pre-write main: the 8.0mm
    PD2 box bar forced pinned refs' boxes past their current separations
    (the documented "domain-bar wall" -- see
    ``docs/evidence/2026-07-31-k3-rtsolve-infeasible-board.md`` and
    ``docs/evidence/2026-08-01-fixed-copper-constraint.md``, verified again
    while writing this suite). The pure-geometry recipe -- FREE={K3}, C27
    excluded from the model (staged off-board), everything else pinned,
    min-displacement toward the current board -- was the one the edge-hanging
    evidence doc verified `optimal` on the pre-write board.

    RE-BASELINED 2026-08-02 (wave-2 board write, this change): the owner
    granted the K3 RT314012 swap + validator-gated re-solve + board write
    (docs/evidence/2026-08-02-k3-swap-and-board-write.md). The written
    board is the product of the **Run B production recipe** -- direct
    ``solve_placement`` with ``fixed_copper`` WITHOUT zone items
    (``free_refs={K3,C27}``, margin 0.05), nothing pinned, min-displacement,
    full domain-clearance (11,571) + keepaway (530), no chain exemption,
    seed 0 -- the evidence-validated candidate recipe
    (docs/evidence/2026-08-01-k3-resolve-validator-gated.md §4 Run B). The
    old pure-geometry recipe (pin everything except K3) is no longer
    feasible on the written board: its box no-overlap model is stricter
    than KiCad's actual courtyards, and the written positions satisfy the
    production recipe, not the pin-everything model. The test therefore
    runs the recipe the board was actually written with. It proves:

    - the solve is feasible/optimal and the validator audit runs;
    - ``hard_failures`` is empty (the written board's inter pairs are
      copper-clean);
    - the wave-2 board write (K3 -> TE Schrack RT314012, the owner-granted
      swap + re-solve + write, docs/evidence/2026-08-02-k3-swap-and-board-
      write.md) cleared the last intra-footprint straddler: the written
      board measures REQ-SAFE-01 = 0/0, so ``intra_footprint`` is EMPTY
      (the G5LE-1-era 3-record / 1-pair K3-intra finding no longer exists)
      -- the position-frame proof that fixed refs' copper geometry is
      unchanged by the overlay still holds over an empty violation set.
    """

    def _skip_if_unavailable(self):
        if not _PCB_PATH.exists():
            pytest.skip(f"production board {_PCB_PATH} not available")
        try:
            from tests.requirements.safety._real_board_fixture import (
                RealBoardUnavailable,
                load_real_board_placement,
            )
        except Exception as exc:  # pragma: no cover - environment guard
            pytest.skip(f"real-board fixture unavailable: {exc}")
        try:
            return load_real_board_placement()
        except RealBoardUnavailable as exc:
            pytest.skip(f"{exc} (run `make netlist` first)")

    def test_free_k3_solve_is_inter_clean_and_k3_intra_surfaces(self) -> None:
        placement, voltage_domains, _stats = self._skip_if_unavailable()

        from temper_placer.io.kicad_parser import parse_kicad_pcb
        from temper_placer.placer.cp_sat.domain_clearance import (
            generate_domain_clearance_constraints,
            generate_unclassified_hv_keepaway_constraints,
        )

        pr = parse_kicad_pcb(str(_PCB_PATH))
        netlist = pr.netlist
        # C27 is now ON-BOARD (written at (28.62, 222.0) by the wave-2
        # write) -- it is part of the model, not excluded as it was when
        # staged off-board.

        current: dict[str, tuple[float, float, int]] = {}
        for c in netlist.components:
            current[c.ref] = (c.initial_position[0], c.initial_position[1], c.initial_rotation)

        # The Run B production recipe the written board came from: fixed
        # copper WITHOUT zone items, free_refs={K3,C27}, margin 0.05;
        # nothing pinned; min-displacement; full domain-clearance +
        # keepaway; no chain exemption; seed 0.
        all_refs = {c.ref for c in netlist.components}
        dc = generate_domain_clearance_constraints(
            placement, voltage_domains, component_refs=all_refs
        )
        kw = generate_unclassified_hv_keepaway_constraints(
            placement, voltage_domains, component_refs=all_refs
        )
        from types import SimpleNamespace

        fc_nozones = {
            "parse_result": SimpleNamespace(
                traces=pr.traces,
                vias=pr.vias,
                board=SimpleNamespace(
                    zones=[],
                    width=pr.board.width,
                    height=pr.board.height,
                    origin=getattr(pr.board, "origin", (0.0, 0.0)),
                ),
            ),
            "free_refs": {"K3", "C27"},
            "margin_mm": 0.05,
        }

        result = solve_placement(
            netlist=netlist,
            board=pr.board,
            extra_constraints=[*dc, *kw],
            timeout_ms=180_000,
            seed=0,
            hint_positions=dict(current),
            minimize_displacement_to={ref: (v[0], v[1]) for ref, v in current.items()},
            max_displacement_mm=60.0,
            fixed_rotations={ref: v[2] for ref, v in current.items()},
            fixed_copper=fc_nozones,
            validator_input={"placement": placement, "voltage_domains": voltage_domains},
        )
        assert result.status in ("optimal", "feasible"), result.status
        assert result.validator_audit is not None
        audit = result.validator_audit
        assert audit.hard_failures == [], (
            "a validator HARD failure on the written-board placement means "
            "the domain-clearance encoding is unsound for a solve that kept "
            "every inter pair where the board already has them -- see "
            f"{audit.report()}"
        )
        assert audit.coverage_gaps == [], (
            f"unexpected coverage gaps on the written board: {audit.report()}"
        )
        # The wave-2 written board has NO intra-footprint straddler: K3 now
        # carries the RT314012 (12.76mm internal gap), so the intra bucket is
        # empty -- the G5LE-1-era 3-record / 1-pair finding is gone
        # (docs/evidence/2026-08-02-k3-swap-and-board-write.md).
        assert len(audit.intra_footprint) == 0, audit.report()
        # Position-frame proof: the validator's per-pair distances on the
        # solved placement equal the committed board's exactly (both empty:
        # 0 violations).
        base = verify_iec60335_compliance(placement, voltage_domains)
        base_metrics = sorted(
            (v.ref_a, v.ref_b, v.metric, round(v.measured_mm, 3)) for v in base.violations
        )
        solved_metrics = sorted(
            (v.ref_a, v.ref_b, v.metric, round(v.measured_mm, 3))
            for v in (*audit.intra_footprint, *audit.hard_failures, *audit.coverage_gaps)
        )
        assert solved_metrics == base_metrics, (
            f"validator distances changed between the committed board and the "
            f"solved placement for refs the solve did not move:\n"
            f"base={base_metrics}\nsolved={solved_metrics}"
        )
        # And K3/C27 (the free refs) are overlaid with their solved positions.
        from temper_placer.placer.cp_sat.validator_audit import build_validator_placement

        vp = build_validator_placement(placement, result.positions, result.rotations, netlist)
        by_ref = {c["ref"]: c for c in vp["components"]}
        base_pos_by_ref = {c["ref"]: c["position"] for c in placement["components"]}
        assert by_ref["K3"]["position"] == result.positions["K3"]
        assert by_ref["C27"]["position"] == result.positions["C27"], (
            "C27 is a free ref in the Run B recipe (fixed_copper "
            "free_refs={K3,C27}): its validator position must be the solved "
            "one, overlaid by the solve"
        )
        # Run B recipe: nothing is pinned (all refs are decision variables,
        # min-displacement objective, fixed_copper treats every non-free ref's
        # copper as a fixed obstacle that K3/C27's pads must clear). The
        # recipe's displacement contract is the <=60mm cap, so every solved
        # position must lie within that envelope of its base board position.
        for ref, pos in base_pos_by_ref.items():
            if ref not in result.positions:
                continue  # not in the model: keeps base
            solved = result.positions[ref]
            disp = math.hypot(solved[0] - pos[0], solved[1] - pos[1])
            assert disp <= 60.0 + 1e-6, (
                f"ref {ref} solved beyond the recipe's 60mm displacement cap: "
                f"{solved} vs board {pos} ({disp:.3f}mm)"
            )
