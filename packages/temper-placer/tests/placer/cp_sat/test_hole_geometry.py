"""Drilled-hole placement constraints (``placer.cp_sat.hole_geometry``).

Five groups, each aimed at a way this constraint family could be green and
vacuous rather than green and correct:

1. ``TestRequirementProvenance`` -- every figure is READ from the tree, the
   strictest of the DRU and the board setup wins, and a caller-supplied
   figure that would RELAX either is refused. This is the group that stops a
   future solve being made feasible by lowering a requirement.
2. ``TestDrillExtraction`` -- the extractor sees the real board's 94 drilled
   pads. This is the falsifier for the bug that shipped in this module's
   first draft: ``Pin.drill`` is a ``DrillDefinition`` pyclass on through-hole
   pads and a bare ``0.0`` float on SMD pads, so a ``float(pin.drill)`` test
   inside a ``try/except TypeError`` classified all 94 real holes as
   drill-free and posted ZERO constraints while reporting success.
3. ``TestBoundSoundness`` -- the axis-projected bound never OVER-claims the
   true Euclidean hole gap, over the real board's 595 hole-bearing component
   pairs and over adversarial rotations. Soundness is the whole argument for
   the encoding; an unsound bound would admit placements that drill into each
   other.
4. ``TestOrToolsEncoding`` -- the constraints are actually BINDING on a real
   ``CpSatModel`` (pin-and-solve: a placement that violates the figure must
   come back INFEASIBLE), not merely posted.
5. ``TestIntraFootprintIsReportedNotConstrained`` -- a footprint whose own
   holes are too close is reported, never posted, because no placement can
   move a footprint's own pads relative to each other.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest
from ortools.sat.python import cp_model

from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.placer.cp_sat.hole_geometry import (
    HoleRequirementUnavailableError,
    _pin_hole,
    add_hole_geometry_to_model,
    extract_component_holes,
    resolve_hole_requirements,
)
from temper_placer.placer.cp_sat.model import CpSatModel

REPO_ROOT = Path(__file__).resolve().parents[5]
BOARD = REPO_ROOT / "pcb" / "temper.kicad_pcb"

#: The committed board's real drilled-pad population, counted independently of
#: this module by a raw s-expression scan of pcb/temper.kicad_pcb (94 holes
#: across 35 footprints; every drill diameter in [0.7, 3.0] mm). Pinned here so
#: the "extractor silently sees nothing" failure mode cannot be green.
REAL_BOARD_HOLE_COUNT = 94
REAL_BOARD_HOLE_REFS = 35

#: Rotation table, identical to isolation_barrier._project_onto_barrier_axis's
#: (and independently re-verified against kicad-cli's own reported pad
#: coordinates: U27 at (33.1, 47.96, 90 deg), pad 2 local (-9.0, 8.89), which
#: kicad-cli reports at (41.99, 56.96)).
ROT = {
    0: lambda x, y: (x, y),
    1: lambda x, y: (y, -x),
    2: lambda x, y: (-x, -y),
    3: lambda x, y: (-y, x),
}


@pytest.fixture(scope="module")
def real_netlist():
    return parse_kicad_pcb(BOARD).netlist


@pytest.fixture(scope="module")
def real_holes(real_netlist):
    out = {}
    for c in real_netlist.components:
        h = extract_component_holes(c)
        if h is not None:
            out[c.ref] = h
    return out


class _Pin:
    def __init__(self, number, position, drill, width=1.0, height=1.0):
        self.number = number
        self.position = position
        self.drill = drill
        self.width = width
        self.height = height
        self.shape = "circle"


class _Drill:
    def __init__(self, diameter, oval=False, width=None, offset=None):
        self.diameter = diameter
        self.oval = oval
        self.width = width
        self.offset = offset


class _Comp:
    def __init__(self, ref, pins, bounds=(10.0, 10.0)):
        self.ref = ref
        self.pins = pins
        self.bounds = bounds


class _Netlist:
    def __init__(self, components):
        self.components = components


# ---------------------------------------------------------------------------
# 1. requirement provenance
# ---------------------------------------------------------------------------
class TestRequirementProvenance:
    def test_reads_the_enforced_figures_from_the_tree(self):
        reqs = resolve_hole_requirements()
        # The DRU's `(rule "PTH hole to hole")` is 0.5mm and the board setup's
        # min_hole_to_hole is 0.3mm. KiCad enforces the stricter; so must the
        # placer, or it would solve against a figure the DRC does not accept.
        assert reqs.hole_to_hole_mm == pytest.approx(0.5)
        assert reqs.hole_to_edge_mm == pytest.approx(0.5)
        assert "hole to hole" in reqs.hole_to_hole_source.lower()
        assert "min_copper_edge_clearance" in reqs.hole_to_edge_source

    def test_neither_figure_claims_fabricator_provenance(self):
        """No JLCPCB hole-to-hole or hole-to-edge figure exists in-tree.

        ``docs/hardware/FAB_CAPABILITY.md``'s sourced hole rows are annular
        ring (2a), minimum drill diameter (2b) and hole-to-COPPER (2c); its
        sourced edge rows (5a/5b) are edge-to-COPPER. Claiming fab traceability
        for these two figures would be inventing a fabrication limit, which
        this module's contract forbids.
        """
        reqs = resolve_hole_requirements()
        assert reqs.hole_to_hole_fab_sourced is False
        assert reqs.hole_to_edge_fab_sourced is False

    def test_the_dru_figure_is_stricter_than_the_board_setup_figure(self):
        """Pins the direction of the max(), so a regression that took the
        board-setup figure instead would fail rather than silently relax."""
        import json

        rules = (
            json.loads((REPO_ROOT / "pcb" / "temper.kicad_pro").read_text())
            ["board"]["design_settings"]["rules"]
        )
        assert rules["min_hole_to_hole"] < resolve_hole_requirements().hole_to_hole_mm

    @pytest.mark.parametrize("kwarg", ["hole_to_hole_mm", "hole_to_edge_mm"])
    def test_a_relaxing_override_is_refused(self, kwarg):
        model = CpSatModel(units_per_mm=100)
        model.add_component("A", 0, 0, 100, 100)
        model.add_rotation("A", is_polarized=True)
        nl = _Netlist([_Comp("A", [_Pin("1", (0.0, 0.0), _Drill(1.0))])])
        with pytest.raises(ValueError, match="LOOSER"):
            add_hole_geometry_to_model(
                model, nl, board_w_mm=50.0, board_h_mm=50.0, **{kwarg: 0.01}
            )

    @pytest.mark.parametrize("kwarg", ["hole_to_hole_mm", "hole_to_edge_mm"])
    def test_a_tightening_override_is_accepted(self, kwarg):
        model = CpSatModel(units_per_mm=100)
        model.add_component("A", 0, 0, 100, 100)
        model.add_rotation("A", is_polarized=True)
        nl = _Netlist([_Comp("A", [_Pin("1", (0.0, 0.0), _Drill(1.0))])])
        rep = add_hole_geometry_to_model(
            model, nl, board_w_mm=50.0, board_h_mm=50.0, **{kwarg: 2.0}
        )
        assert getattr(rep.requirements, kwarg) == pytest.approx(2.0)

    def test_missing_dru_is_refused_not_silently_downgraded(self, tmp_path):
        """With no DRU resolvable, falling back to the board setup's looser
        0.3mm would under-constrain silently. It must raise instead.

        Driven through the ``dru_text`` injection point: monkeypatching
        ``_REPO_ROOT`` does NOT isolate this branch, because ``scripts`` is
        already on ``sys.path`` and ``generate_kicad_dru`` may already be
        imported, so the in-process generator still succeeds and the test
        would pass vacuously.
        """
        with pytest.raises(HoleRequirementUnavailableError, match="LOOSER"):
            resolve_hole_requirements(
                dru_path=tmp_path / "nope.kicad_dru", dru_text=""
            )

    def test_a_dru_without_a_hole_to_hole_rule_is_refused(self, tmp_path):
        with pytest.raises(HoleRequirementUnavailableError):
            resolve_hole_requirements(
                dru_path=tmp_path / "nope.kicad_dru",
                dru_text='(rule "Via hole clearance"\n (constraint hole_clearance (min 0.28mm))\n)',
            )


# ---------------------------------------------------------------------------
# 2. drill extraction
# ---------------------------------------------------------------------------
class TestDrillExtraction:
    def test_sees_every_drilled_pad_on_the_real_board(self, real_holes):
        assert len(real_holes) == REAL_BOARD_HOLE_REFS
        assert sum(h.n_holes for h in real_holes.values()) == REAL_BOARD_HOLE_COUNT

    def test_smd_float_zero_drill_is_not_a_hole(self):
        assert _pin_hole(_Pin("1", (0.0, 0.0), 0.0)) is None

    def test_drilldefinition_pyclass_is_not_swallowed(self):
        """The exact falsifier for this module's first-draft bug.

        ``float(DrillDefinition(...))`` raises ``TypeError``; a
        try/except-float test therefore returned False for every real
        through-hole pad and the module posted no constraints at all while
        reporting success.
        """
        hole = _pin_hole(_Pin("1", (0.0, 0.0), _Drill(1.3)))
        assert hole is not None
        rx, ry, _ = hole
        assert rx == pytest.approx(0.65)
        assert ry == pytest.approx(0.65)

    def test_oval_drill_is_bounded_by_its_larger_dimension(self):
        rx, ry, _ = _pin_hole(_Pin("1", (0.0, 0.0), _Drill(1.0, oval=True, width=2.4)))
        assert rx == pytest.approx(1.2)
        assert ry == pytest.approx(1.2)

    def test_drill_offset_is_absorbed_into_both_axis_radii(self):
        rx, ry, extra = _pin_hole(_Pin("1", (0.0, 0.0), _Drill(1.0, offset=(0.3, -0.4))))
        assert extra == pytest.approx(0.4)
        assert rx == pytest.approx(0.9)
        assert ry == pytest.approx(0.9)

    def test_a_drill_token_without_a_diameter_raises(self):
        from temper_placer.placer.cp_sat.hole_geometry import UnhandledDrillError

        with pytest.raises(UnhandledDrillError):
            _pin_hole(_Pin("1", (0.0, 0.0), _Drill(None, offset=(0.1, 0.1))))

    def test_axis_extents_are_swapped_not_maxed_under_rotation(self):
        """Ax/Ay must SWAP on a 90-degree rotation. Collapsing both onto
        max(Ax, Ay) would be sound but needlessly over-constrain an elongated
        part -- and would hide a genuine encoding error on a square one."""
        comp = _Comp("A", [
            _Pin("1", (-10.0, -1.0), _Drill(1.0)),
            _Pin("2", (10.0, 1.0), _Drill(1.0)),
        ])
        h = extract_component_holes(comp)
        assert h.ax_mm == pytest.approx(10.5)
        assert h.ay_mm == pytest.approx(1.5)


# ---------------------------------------------------------------------------
# 3. soundness of the axis-projected bound
# ---------------------------------------------------------------------------
def _world_holes(comp, cx, cy, rot):
    f = ROT[rot]
    out = []
    for pin in comp.pins:
        h = _pin_hole(pin)
        if h is None:
            continue
        rx, ry, _ = h
        ox, oy = f(float(pin.position[0]), float(pin.position[1]))
        out.append((cx + ox, cy + oy, max(rx, ry)))
    return out


def _bound(ha, hb, ca, cb, rota, rotb):
    axa, aya = (ha.ax_mm, ha.ay_mm) if rota % 2 == 0 else (ha.ay_mm, ha.ax_mm)
    axb, ayb = (hb.ax_mm, hb.ay_mm) if rotb % 2 == 0 else (hb.ay_mm, hb.ax_mm)
    return max(abs(ca[0] - cb[0]) - axa - axb, abs(ca[1] - cb[1]) - aya - ayb)


class TestBoundSoundness:
    def test_bound_never_over_claims_on_the_real_board(self, real_netlist, real_holes):
        """Over the committed board's own 595 hole-bearing component pairs.

        The direction that matters is one-sided: the bound may under-claim
        (conservatism, which only over-constrains) but must never exceed the
        true Euclidean gap, or the solver could accept a placement whose holes
        are genuinely too close.
        """
        comps = {c.ref: c for c in real_netlist.components}
        pos, rot = {}, {}
        for c in real_netlist.components:
            if getattr(c, "initial_position", None) is None:
                continue
            pos[c.ref] = (c.initial_position[0], c.initial_position[1])
            rot[c.ref] = int(getattr(c, "initial_rotation_quadrant", 0) or 0) % 4
        refs = [r for r in sorted(real_holes) if r in pos]
        assert len(refs) == REAL_BOARD_HOLE_REFS

        checked = 0
        for i, ra in enumerate(refs):
            wa = _world_holes(comps[ra], *pos[ra], rot[ra])
            for rb in refs[i + 1:]:
                wb = _world_holes(comps[rb], *pos[rb], rot[rb])
                truth = min(
                    math.hypot(xa - xb, ya - yb) - r1 - r2
                    for xa, ya, r1 in wa
                    for xb, yb, r2 in wb
                )
                b = _bound(real_holes[ra], real_holes[rb], pos[ra], pos[rb],
                           rot[ra], rot[rb])
                assert b <= truth + 1e-9, f"bound over-claims on {ra}/{rb}"
                checked += 1
        assert checked == len(refs) * (len(refs) - 1) // 2

    @pytest.mark.parametrize("rota", [0, 1, 2, 3])
    @pytest.mark.parametrize("rotb", [0, 1, 2, 3])
    def test_bound_never_over_claims_under_every_rotation_pair(self, rota, rotb):
        a = _Comp("A", [_Pin("1", (-4.0, -0.5), _Drill(1.0)),
                        _Pin("2", (4.0, 0.5), _Drill(1.4))])
        b = _Comp("B", [_Pin("1", (-1.5, -3.0), _Drill(0.8)),
                        _Pin("2", (1.5, 3.0), _Drill(2.0))])
        ha, hb = extract_component_holes(a), extract_component_holes(b)
        for dx in (-9.0, -3.25, 0.0, 2.5, 11.0):
            for dy in (-7.0, -1.75, 0.0, 4.5, 8.0):
                ca, cb = (0.0, 0.0), (dx, dy)
                wa = _world_holes(a, *ca, rota)
                wb = _world_holes(b, *cb, rotb)
                truth = min(
                    math.hypot(xa - xb, ya - yb) - r1 - r2
                    for xa, ya, r1 in wa
                    for xb, yb, r2 in wb
                )
                assert _bound(ha, hb, ca, cb, rota, rotb) <= truth + 1e-9


# ---------------------------------------------------------------------------
# 4. the constraints actually bind on a real CpSatModel
# ---------------------------------------------------------------------------
def _two_hole_model(units_per_mm=100, box_mm=1.0):
    """Two single-hole components, each a 1.0mm box holding a 1.0mm drill.

    The box is deliberately no larger than the hole. ``add_component`` gives
    ``x_start`` the domain ``[0, 1e6]``, so an oversized box pinned near the
    board edge is infeasible for a reason that has nothing to do with the
    hole-to-edge constraint under test -- which would make the edge tests pass
    or fail for the wrong reason.
    """
    model = CpSatModel(units_per_mm=units_per_mm)
    for ref in ("A", "B"):
        model.add_component(ref, 0, 0, model.mm_to_units(box_mm), model.mm_to_units(box_mm))
        model.add_rotation(ref, is_polarized=True)
    nl = _Netlist([
        _Comp("A", [_Pin("1", (0.0, 0.0), _Drill(1.0))]),
        _Comp("B", [_Pin("1", (0.0, 0.0), _Drill(1.0))]),
    ])
    return model, nl


def _pin_centres(model, ax, ay, bx, by):
    m = model.model_ref
    for ref, (x, y) in (("A", (ax, ay)), ("B", (bx, by))):
        cv = model.get_component(ref)
        m.Add(cv.x_center == model.mm_to_units(x))
        m.Add(cv.y_center == model.mm_to_units(y))


def _solve(model):
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 30.0
    return solver.Solve(model.model_ref)


class TestOrToolsEncoding:
    def test_hole_to_hole_rejects_a_too_close_pair(self):
        """Two 1.0mm holes 1.4mm apart -> 0.4mm gap, below the 0.5mm figure."""
        model, nl = _two_hole_model()
        add_hole_geometry_to_model(
            model, nl, board_w_mm=100.0, board_h_mm=100.0, enforce_hole_to_edge=False
        )
        _pin_centres(model, 50.0, 50.0, 51.4, 50.0)
        assert _solve(model) == cp_model.INFEASIBLE

    def test_hole_to_hole_accepts_a_compliant_pair(self):
        """Same pair at 1.6mm -> 0.6mm gap, clears 0.5mm."""
        model, nl = _two_hole_model()
        add_hole_geometry_to_model(
            model, nl, board_w_mm=100.0, board_h_mm=100.0, enforce_hole_to_edge=False
        )
        _pin_centres(model, 50.0, 50.0, 51.6, 50.0)
        assert _solve(model) in (cp_model.OPTIMAL, cp_model.FEASIBLE)

    def test_hole_to_hole_is_satisfied_on_either_axis(self):
        """The Chebyshev disjunction must accept separation on Y alone."""
        model, nl = _two_hole_model()
        add_hole_geometry_to_model(
            model, nl, board_w_mm=100.0, board_h_mm=100.0, enforce_hole_to_edge=False
        )
        _pin_centres(model, 50.0, 50.0, 50.0, 51.6)
        assert _solve(model) in (cp_model.OPTIMAL, cp_model.FEASIBLE)

    def test_hole_to_edge_rejects_a_hole_over_the_margin(self):
        """Hole centre 0.8mm from the edge with a 0.5mm radius leaves 0.3mm."""
        model, nl = _two_hole_model()
        add_hole_geometry_to_model(
            model, nl, board_w_mm=100.0, board_h_mm=100.0, enforce_hole_to_hole=False
        )
        _pin_centres(model, 0.8, 50.0, 50.0, 50.0)
        assert _solve(model) == cp_model.INFEASIBLE

    def test_that_rejection_is_caused_by_the_constraint_and_not_the_box(self):
        """The control for the test above.

        Identical model and identical pinned coordinates, with the edge family
        NOT posted: it must be FEASIBLE. Without this control the INFEASIBLE
        above would be equally consistent with the component box simply not
        fitting, and the test would prove nothing about the constraint.
        """
        model, nl = _two_hole_model()
        add_hole_geometry_to_model(
            model, nl, board_w_mm=100.0, board_h_mm=100.0,
            enforce_hole_to_hole=False, enforce_hole_to_edge=False,
        )
        _pin_centres(model, 0.8, 50.0, 50.0, 50.0)
        assert _solve(model) in (cp_model.OPTIMAL, cp_model.FEASIBLE)

    def test_hole_to_edge_accepts_a_compliant_hole(self):
        model, nl = _two_hole_model()
        add_hole_geometry_to_model(
            model, nl, board_w_mm=100.0, board_h_mm=100.0, enforce_hole_to_hole=False
        )
        _pin_centres(model, 1.2, 50.0, 50.0, 50.0)
        assert _solve(model) in (cp_model.OPTIMAL, cp_model.FEASIBLE)

    def test_a_non_rectangular_outline_is_refused_not_approximated(self):
        model, nl = _two_hole_model()
        with pytest.raises(ValueError, match="solver frame"):
            add_hole_geometry_to_model(
                model, nl, board_w_mm=100.0, board_h_mm=100.0,
                board_outline=(0.0, 0.0, 60.0, 100.0),
            )

    def test_report_counts_what_was_actually_posted(self, real_netlist):
        model = CpSatModel(units_per_mm=100)
        for c in real_netlist.components:
            w, h = c.bounds
            model.add_component(c.ref, 0, 0, model.mm_to_units(w), model.mm_to_units(h))
            model.add_rotation(c.ref, is_polarized=False)
        rep = add_hole_geometry_to_model(
            model, real_netlist, board_w_mm=164.0, board_h_mm=234.0
        )
        n = REAL_BOARD_HOLE_REFS
        assert rep.pairs_constrained == n * (n - 1) // 2
        assert len(rep.edge_constrained_refs) == n
        assert len(rep.holes_by_ref) == n


# ---------------------------------------------------------------------------
# 5. intra-footprint pairs are reported, never constrained
# ---------------------------------------------------------------------------
class TestIntraFootprintIsReportedNotConstrained:
    def test_a_self_violating_footprint_does_not_make_the_model_infeasible(self):
        """Two of ONE component's own holes 0.1mm apart.

        No placement can move a footprint's own pads relative to each other,
        so posting this as a constraint would make the model infeasible for
        something placement does not control -- the same argument
        ``domain_clearance.py`` makes about intra-footprint domain straddling.
        """
        model = CpSatModel(units_per_mm=100)
        model.add_component("A", 0, 0, model.mm_to_units(9.0), model.mm_to_units(9.0))
        model.add_rotation("A", is_polarized=True)
        nl = _Netlist([_Comp("A", [
            _Pin("1", (0.0, 0.0), _Drill(1.0)),
            _Pin("2", (1.1, 0.0), _Drill(1.0)),
        ])])
        rep = add_hole_geometry_to_model(model, nl, board_w_mm=100.0, board_h_mm=100.0)
        assert rep.intra_footprint_violations
        ref, gap = rep.intra_footprint_violations[0]
        assert ref == "A"
        assert gap == pytest.approx(0.1)
        assert rep.pairs_constrained == 0
        cv = model.get_component("A")
        model.model_ref.Add(cv.x_center == model.mm_to_units(50.0))
        model.model_ref.Add(cv.y_center == model.mm_to_units(50.0))
        assert _solve(model) in (cp_model.OPTIMAL, cp_model.FEASIBLE)

    def test_the_real_board_has_no_intra_footprint_violation(self, real_netlist):
        model = CpSatModel(units_per_mm=100)
        for c in real_netlist.components:
            w, h = c.bounds
            model.add_component(c.ref, 0, 0, model.mm_to_units(w), model.mm_to_units(h))
            model.add_rotation(c.ref, is_polarized=False)
        rep = add_hole_geometry_to_model(
            model, real_netlist, board_w_mm=164.0, board_h_mm=234.0
        )
        assert rep.intra_footprint_violations == []
