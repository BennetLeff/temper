"""Tests for the mains<->SELV physical isolation-barrier CP-SAT constraint.

Mirrors ``tests/placer/cp_sat/test_domain_clearance.py``'s use of synthetic
fixtures (never the real board) for unit-level coverage; the real board is
exercised separately (see docs/evidence/2026-07-28-barrier-constrained-placement.md).
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from temper_placer.core.netlist import Component, Netlist, Pin
from temper_placer.geometry.kicad_transform import rotate_local_to_world_deg
from temper_placer.placer.cp_sat.isolation_barrier import (
    IsolatorPadGroups,
    Pad,
    _project_onto_barrier_axis,
    add_isolation_barrier_to_model,
    classify_domain_partition,
    compute_pad_groups,
    evaluate_isolator_feasibility,
    load_domain_manifest_nets,
)
from temper_placer.placer.cp_sat.model import CpSatModel

HV = frozenset({"AC_L", "AC_N", "DC_BUS"})
SELV = frozenset({"GND", "+3V3"})


def _comp(ref, pins, w=5.0, h=5.0) -> Component:
    return Component(ref=ref, footprint="test:fp", bounds=(w, h), pins=pins)


def _circle_pad(x: float, y: float, radius: float) -> Pad:
    """A synthetic circular pad of the given isotropic radius -- used by
    tests below that exercise the rotation-search/feasibility ALGORITHM
    (not real pad-shape derivation, which is `compute_pad_groups`'s own
    job, covered separately). A circle's exact axis-radius is the same
    value in every direction and at every rotation, so these fixtures
    reproduce exactly the pre-fix tests' isotropic-radius semantics."""
    return Pad(x=x, y=y, width=2 * radius, height=2 * radius, shape="circle")


# ---------------------------------------------------------------------------
# classify_domain_partition
# ---------------------------------------------------------------------------


def test_partition_hv_only_selv_only_isolator_unclassified():
    comps = [
        _comp("R1", [Pin("1", "1", (0, 0), net="AC_L")]),
        _comp("R2", [Pin("1", "1", (0, 0), net="GND")]),
        _comp("U1", [Pin("1", "1", (0, 0), net="AC_L"), Pin("2", "2", (5, 0), net="GND")]),
        _comp("R3", [Pin("1", "1", (0, 0), net="SOME_OTHER_NET")]),
    ]
    partition = classify_domain_partition(comps, HV, SELV)
    assert partition.hv_only == ["R1"]
    assert partition.selv_only == ["R2"]
    assert partition.isolators == ["U1"]
    assert partition.unclassified == ["R3"]
    assert partition.total == 4


def test_partition_never_substring_matches():
    """A net that merely CONTAINS an HV net's name must not classify as HV."""
    comps = [_comp("R9", [Pin("1", "1", (0, 0), net="AC_LINE_SENSE")])]
    partition = classify_domain_partition(comps, HV, SELV)
    assert partition.unclassified == ["R9"]
    assert partition.hv_only == []


# ---------------------------------------------------------------------------
# evaluate_isolator_feasibility
# ---------------------------------------------------------------------------


def test_isolator_feasible_on_x_axis():
    """Wide component (like the real board's PS1 aux-supply module): HV and
    SELV pad clusters 38.5mm apart in X -- comfortably clears an 8.5mm gap."""
    groups = IsolatorPadGroups(
        ref="PS1",
        hv_pads=[_circle_pad(0.0, 0.0, 1.5), _circle_pad(0.0, 10.75, 1.5)],
        selv_pads=[_circle_pad(38.5, 10.75, 1.5), _circle_pad(38.5, 2.75, 1.5)],
        other_pads=[],
    )
    feas = evaluate_isolator_feasibility(groups, corridor_width_mm=8.5)
    assert feas.feasible
    assert feas.feasible_axis == 0
    assert feas.hv_is_lo is True


def test_isolator_feasible_only_via_y_axis_rotation():
    """Regression test for a real bug found via a corridor-width control
    experiment against the real board (see docs/evidence/
    2026-07-28-barrier-constrained-placement.md): a K1-shaped isolator
    (bypass relay) whose HV/SELV clusters are 9.5mm apart in local Y but
    OVERLAP in local X. Against a barrier whose own axis is X (0), this is
    only feasible if a 90-degree rotation is chosen to bring the local-Y
    separation onto the barrier's X axis -- an earlier version of this
    module unconditionally fixed rotation to 0, which only ever tests
    local X (here, infeasible), and wrongly reported/encoded this case as
    UNSAT even at corridor widths the Y-axis gap should have cleared."""
    groups = IsolatorPadGroups(
        ref="K1",
        hv_pads=[_circle_pad(-3.175, 9.5, 3.17), _circle_pad(3.175, 9.5, 3.17)],
        selv_pads=[_circle_pad(-3.175, 0.0, 0.9), _circle_pad(3.175, 0.0, 0.9)],
        other_pads=[],
    )
    # gap_x (both clusters span the same X range) is negative/overlapping;
    # gap_y (9.5mm centre-to-centre minus radii) clears a 4mm corridor.
    feas = evaluate_isolator_feasibility(groups, corridor_width_mm=4.0, barrier_axis=0)
    assert feas.gap_x_mm < 0
    assert feas.gap_y_mm >= 4.0
    assert feas.feasible, (
        "barrier_axis=0 (X) must still be satisfiable by rotating 90 degrees "
        "to bring the Y-axis separation onto the X axis"
    )
    assert feas.chosen_rotation in (1, 3)  # a 90-degree family rotation, not 0


def test_isolator_infeasible_both_axes():
    """5mm-pitch two-pad component (like the real board's C6 Y-cap stub):
    provably cannot straddle an 8.5mm corridor on any axis or rotation."""
    groups = IsolatorPadGroups(
        ref="C6",
        hv_pads=[_circle_pad(0.0, 0.0, 0.9)],
        selv_pads=[_circle_pad(5.0, 0.0, 0.9)],
        other_pads=[],
    )
    feas = evaluate_isolator_feasibility(groups, corridor_width_mm=8.5)
    assert not feas.feasible
    assert feas.feasible_axis is None
    assert feas.gap_x_mm == pytest.approx(5.0 - 0.9 - 0.9)
    assert feas.gap_y_mm < 0  # pads coincide in Y entirely


def test_isolator_dip6_row_pitch_infeasible():
    """H11L1-style DIP-6, 7.62mm row pitch (JEDEC 300mil standard) minus pad
    radii: below 8.0mm regardless of orientation."""
    groups = IsolatorPadGroups(
        ref="U3",
        hv_pads=[_circle_pad(0.0, 0.0, 0.8), _circle_pad(0.0, 2.54, 0.8)],
        selv_pads=[_circle_pad(7.62, 5.08, 0.8), _circle_pad(7.62, 2.54, 0.8), _circle_pad(7.62, 0.0, 0.8)],
        other_pads=[],
    )
    feas = evaluate_isolator_feasibility(groups, corridor_width_mm=8.0)
    assert not feas.feasible
    assert feas.gap_x_mm == pytest.approx(7.62 - 1.6)


def test_evaluate_isolator_feasibility_rejects_non_isolator():
    groups = IsolatorPadGroups(ref="R1", hv_pads=[_circle_pad(0, 0, 0.5)], selv_pads=[], other_pads=[])
    with pytest.raises(ValueError, match="not a real isolator"):
        evaluate_isolator_feasibility(groups, corridor_width_mm=8.0)


def test_compute_pad_groups_splits_by_manifest_nets():
    comp = _comp(
        "U1",
        [
            Pin("1", "1", (0.0, 0.0), net="AC_L", width=1.0, height=2.0),
            Pin("2", "2", (5.0, 0.0), net="GND", width=1.0, height=1.0),
            Pin("3", "3", (2.5, 0.0), net="UNCLASSIFIED"),
        ],
    )
    groups = compute_pad_groups(comp, HV, SELV)
    # compute_pad_groups carries the pad's REAL shape through uninterpreted
    # (default Pin shape is "rect", default roundrect_ratio 0.25) -- it no
    # longer collapses every pad to an isotropic "circle" radius.
    assert groups.hv_pads == [Pad(0.0, 0.0, 1.0, 2.0, "rect", 0.25)]
    assert groups.selv_pads == [Pad(5.0, 0.0, 1.0, 1.0, "rect", 0.25)]
    assert len(groups.other_pads) == 1

    # And the exact axis radii derived from that shape are correct: for a
    # 1x2mm rect pad, axis_radius(0)=width/2=0.5, axis_radius(1)=height/2=1.0
    # -- NOT the old isotropic max(1,2)/2 = 1.0 in both directions.
    assert groups.hv_pads[0].axis_radius(0) == pytest.approx(0.5)
    assert groups.hv_pads[0].axis_radius(1) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# load_domain_manifest_nets
# ---------------------------------------------------------------------------


def test_load_domain_manifest_nets(tmp_path: Path):
    manifest = tmp_path / "domain_manifest.yaml"
    manifest.write_text(
        textwrap.dedent(
            """
            schema_version: 1
            domains:
              HV:
                nets: [ac_l, ac_n]
              SELV:
                nets: [gnd, "+3v3"]
            """
        )
    )
    hv, selv = load_domain_manifest_nets(manifest)
    assert hv == frozenset({"ac_l", "ac_n"})
    assert selv == frozenset({"gnd", "+3v3"})


def test_load_domain_manifest_nets_rejects_overlap(tmp_path: Path):
    manifest = tmp_path / "domain_manifest.yaml"
    manifest.write_text(
        textwrap.dedent(
            """
            domains:
              HV:
                nets: [shared]
              SELV:
                nets: [shared]
            """
        )
    )
    with pytest.raises(ValueError, match="both HV and SELV"):
        load_domain_manifest_nets(manifest)


# ---------------------------------------------------------------------------
# add_isolation_barrier_to_model -- full CP-SAT integration
# ---------------------------------------------------------------------------


def _build_model(components: list[Component]) -> CpSatModel:
    model = CpSatModel(units_per_mm=100)
    for comp in components:
        model.add_component(
            comp.ref,
            x_start_val=0,
            y_start_val=0,
            width=model.mm_to_units(comp.width),
            height=model.mm_to_units(comp.height),
        )
        model.add_rotation(comp.ref, is_polarized=False)
    model.set_bounds(0, 0, model.mm_to_units(100.0), model.mm_to_units(100.0))
    model.add_no_overlap_2d([c.ref for c in components])
    return model


def _write_manifest(tmp_path: Path) -> Path:
    manifest = tmp_path / "domain_manifest.yaml"
    manifest.write_text(
        textwrap.dedent(
            """
            domains:
              HV:
                nets: [AC_L]
              SELV:
                nets: [GND]
            """
        )
    )
    return manifest


def test_barrier_separates_domain_only_components_sat(tmp_path: Path):
    """HV-only and SELV-only components must land on OPPOSITE, consistent
    sides of the corridor -- not merely each individually avoid it (the bug
    the SeparatedConstraint-based design had: see module docstring)."""
    hv_comp = _comp("R_HV", [Pin("1", "1", (0, 0), net="AC_L")], w=5, h=5)
    selv_comp = _comp("R_SELV", [Pin("1", "1", (0, 0), net="GND")], w=5, h=5)
    netlist = Netlist(components=[hv_comp, selv_comp])
    model = _build_model(netlist.components)
    manifest = _write_manifest(tmp_path)

    report = add_isolation_barrier_to_model(
        model,
        netlist,
        manifest,
        board_w_mm=100.0,
        board_h_mm=100.0,
        corridor_width_mm=8.5,
    )

    solution = model.solve(time_limit_s=10.0)
    assert solution.feasible, solution.unsat_assumptions
    hv_x = solution.positions["R_HV"][0] / model.units_per_mm
    selv_x = solution.positions["R_SELV"][0] / model.units_per_mm
    corridor_lo = report.corridor_position_mm
    corridor_hi = corridor_lo + report.corridor_width_mm
    # HV strictly left of the corridor, SELV strictly right (half-width 2.5mm).
    assert hv_x + 2.5 <= corridor_lo + 0.02
    assert selv_x - 2.5 >= corridor_hi - 0.02
    assert report.partition.hv_only == ["R_HV"]
    assert report.partition.selv_only == ["R_SELV"]


def test_barrier_infeasible_isolator_forces_unsat(tmp_path: Path):
    """A C6-shaped isolator (5mm pad pitch) makes the WHOLE model infeasible,
    regardless of how much free room the rest of the board has."""
    hv_comp = _comp("R_HV", [Pin("1", "1", (0, 0), net="AC_L")], w=5, h=5)
    selv_comp = _comp("R_SELV", [Pin("1", "1", (0, 0), net="GND")], w=5, h=5)
    isolator = _comp(
        "C6",
        [
            Pin("1", "1", (0.0, 0.0), net="AC_L", width=1.8, height=1.8),
            Pin("2", "2", (5.0, 0.0), net="GND", width=1.8, height=1.8),
        ],
        w=8,
        h=4,
    )
    netlist = Netlist(components=[hv_comp, selv_comp, isolator])
    model = _build_model(netlist.components)
    manifest = _write_manifest(tmp_path)

    report = add_isolation_barrier_to_model(
        model,
        netlist,
        manifest,
        board_w_mm=100.0,
        board_h_mm=100.0,
        corridor_width_mm=8.5,
    )
    assert report.partition.isolators == ["C6"]
    assert report.infeasible_isolators == ["C6"]

    solution = model.solve(time_limit_s=10.0)
    assert not solution.feasible
    assert any("isolator_straddle_C6" in a for a in solution.unsat_assumptions)


def test_barrier_feasible_isolator_can_straddle(tmp_path: Path):
    """A PS1-shaped isolator (HV/SELV pads 38.5mm apart) can have its
    courtyard straddle the corridor while its own pads land on the correct
    sides -- SAT, and the resolved position is verified pad-level, not just
    courtyard-level."""
    hv_comp = _comp("R_HV", [Pin("1", "1", (0, 0), net="AC_L")], w=5, h=5)
    selv_comp = _comp("R_SELV", [Pin("1", "1", (0, 0), net="GND")], w=5, h=5)
    isolator = _comp(
        "PS1",
        [
            Pin("1", "1", (0.0, 0.0), net="AC_L", width=3.0, height=3.0),
            Pin("2", "2", (0.0, 10.75), net="AC_L", width=3.0, height=3.0),
            Pin("3", "3", (38.5, 10.75), net="GND", width=3.0, height=3.0),
            Pin("4", "4", (38.5, 2.75), net="GND", width=3.0, height=3.0),
        ],
        w=45,
        h=15,
    )
    netlist = Netlist(components=[hv_comp, selv_comp, isolator])
    model = _build_model(netlist.components)
    manifest = _write_manifest(tmp_path)

    report = add_isolation_barrier_to_model(
        model,
        netlist,
        manifest,
        board_w_mm=150.0,
        board_h_mm=100.0,
        corridor_width_mm=8.5,
    )
    assert report.partition.isolators == ["PS1"]
    assert report.infeasible_isolators == []

    solution = model.solve(time_limit_s=15.0)
    assert solution.feasible, solution.unsat_assumptions

    # Pad-level audit: recompute PS1's real pad positions from the resolved
    # centre (rotation is forced to 0 by add_isolation_barrier_to_model) and
    # confirm HV pads are strictly left of the corridor, SELV pads strictly
    # right -- the exact property scripts/check_isolation_keepout.py checks.
    ps1_x_units, _ = solution.positions["PS1"]
    ps1_rot = solution.rotations.get("PS1", 0)
    assert ps1_rot == 0
    ps1_x_mm = ps1_x_units / model.units_per_mm
    corridor_lo = report.corridor_position_mm
    corridor_hi = corridor_lo + report.corridor_width_mm
    hv_edge_mm = ps1_x_mm + 0.0 + 1.5  # local x=0, radius 1.5
    selv_edge_mm = ps1_x_mm + 38.5 - 1.5
    assert hv_edge_mm <= corridor_lo + 0.02
    assert selv_edge_mm >= corridor_hi - 0.02


# ---------------------------------------------------------------------------
# Consistency: _project_onto_barrier_axis's hand-unrolled 4-way dict must
# stay pinned to the sanctioned kicad_transform convention it claims to be
# an exact closed form of (see that function's own docstring for why it is
# not simply routed through kicad_transform's floating-point trig).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("local_x", "local_y"),
    [
        (0.0, 0.0),
        (1.0, 0.0),
        (0.0, 1.0),
        (3.7, -2.1),
        (-5.0, 5.0),
        (12.34, -0.001),
    ],
)
@pytest.mark.parametrize("rot_value", [0, 1, 2, 3])
def test_isolation_barrier_matches_kicad_transform(rot_value, local_x, local_y):
    expected_x, expected_y = rotate_local_to_world_deg(local_x, local_y, rot_value * 90.0)
    got_x = _project_onto_barrier_axis(local_x, local_y, rot_value, barrier_axis=0)
    got_y = _project_onto_barrier_axis(local_x, local_y, rot_value, barrier_axis=1)
    assert got_x == pytest.approx(expected_x, abs=1e-9)
    assert got_y == pytest.approx(expected_y, abs=1e-9)


# ---------------------------------------------------------------------------
# Plan 2026-08-02-016 U2: post-solve audit of the isolation barrier
# (audit_isolation_barrier recomputes the HV/SELV one-sided bounds from
# resolved coordinates; isolator pad-cluster straddles are a documented
# UNVERIFIED exemption).
# ---------------------------------------------------------------------------


def _barrier_report(
    *,
    hv_only=(),
    selv_only=(),
    isolators=(),
    orientation="vertical",
    corridor_position_mm=45.0,
    corridor_width_mm=8.5,
):
    from temper_placer.placer.cp_sat.isolation_barrier import (
        DomainPartition,
        IsolationBarrierReport,
    )

    report = IsolationBarrierReport(
        partition=DomainPartition(
            hv_only=list(hv_only),
            selv_only=list(selv_only),
            isolators=list(isolators),
        ),
        isolator_feasibility=[],
        orientation=orientation,
        corridor_width_mm=corridor_width_mm,
        corridor_position_mm=corridor_position_mm,
    )
    return report


def _barrier_placement(positions, sizes=None):
    from temper_placer.placer.cp_sat.audit import Placement

    sizes = sizes or dict.fromkeys(positions, (5.0, 5.0))
    return Placement(
        positions_mm=positions,
        sizes_mm=sizes,
        rotations={},
        board_w_mm=100.0,
        board_h_mm=60.0,
    )


class TestIsolationBarrierPostSolveAudit:
    """U2: the barrier's HV/SELV one-sided bounds are recomputed from
    resolved coordinates (R24 item 3), and isolators audit UNVERIFIED."""

    def test_hv_selv_correct_sides_pass(self) -> None:
        from temper_placer.placer.cp_sat.audit import audit_isolation_barrier

        # Vertical corridor from x=45 to x=53.5. HV at x=20 (end 22.5 <= 45),
        # SELV at x=60 (start 57.5 >= 53.5).
        report = _barrier_report(
            hv_only=("Q1",),
            selv_only=("U1",),
            isolators=("T1",),
            corridor_position_mm=45.0,
            corridor_width_mm=8.5,
        )
        placement = _barrier_placement(
            {"Q1": (20.0, 10.0), "U1": (60.0, 10.0), "T1": (50.0, 30.0)}
        )
        audit = audit_isolation_barrier(report, placement)
        assert audit.all_pass
        assert audit.violations == []
        # Isolators are a documented UNVERIFIED exemption: recorded, not failing.
        assert len(audit.unverified) == 1
        assert "UNVERIFIED" in audit.unverified[0].description
        assert "T1" in audit.unverified[0].constraint_id

    def test_hv_component_crosses_corridor_fails(self) -> None:
        from temper_placer.placer.cp_sat.audit import audit_isolation_barrier

        # Q1 center at x=44 with size 5 → end 46.5 > 45 (corridor lo).
        report = _barrier_report(hv_only=("Q1",), selv_only=("U1",))
        placement = _barrier_placement(
            {"Q1": (44.0, 10.0), "U1": (60.0, 10.0)},
            sizes={"Q1": (5.0, 5.0), "U1": (5.0, 5.0)},
        )
        audit = audit_isolation_barrier(report, placement)
        assert not audit.all_pass
        assert len(audit.violations) == 1
        v = audit.violations[0]
        assert v.constraint_id == "isolation_barrier_hv_Q1"
        assert "end=46.50mm" in v.description

    def test_selv_component_crosses_corridor_fails(self) -> None:
        from temper_placer.placer.cp_sat.audit import audit_isolation_barrier

        # U1 center at x=55 with size 5 → start 52.5 < 53.5 (corridor hi).
        report = _barrier_report(hv_only=("Q1",), selv_only=("U1",))
        placement = _barrier_placement(
            {"Q1": (20.0, 10.0), "U1": (55.0, 10.0)},
            sizes={"Q1": (5.0, 5.0), "U1": (5.0, 5.0)},
        )
        audit = audit_isolation_barrier(report, placement)
        assert not audit.all_pass
        assert len(audit.violations) == 1
        v = audit.violations[0]
        assert v.constraint_id == "isolation_barrier_selv_U1"
        assert "start=52.50mm" in v.description

    def test_horizontal_orientation_uses_y_axis(self) -> None:
        from temper_placer.placer.cp_sat.audit import audit_isolation_barrier

        # Horizontal corridor y from 30 to 38.5. HV below (y_end 27.5 <= 30),
        # SELV above (y_start 42.5 >= 38.5).
        report = _barrier_report(
            hv_only=("Q1",),
            selv_only=("U1",),
            orientation="horizontal",
            corridor_position_mm=30.0,
            corridor_width_mm=8.5,
        )
        placement = _barrier_placement(
            {"Q1": (10.0, 25.0), "U1": (10.0, 45.0)},
            sizes={"Q1": (5.0, 5.0), "U1": (5.0, 5.0)},
        )
        audit = audit_isolation_barrier(report, placement)
        assert audit.all_pass
        assert audit.violations == []

    def test_missing_partition_returns_empty_pass(self) -> None:
        from temper_placer.placer.cp_sat.audit import audit_isolation_barrier

        class _BareReport:
            orientation = "vertical"
            corridor_position_mm = 45.0
            corridor_width_mm = 8.5
            partition = None

        audit = audit_isolation_barrier(_BareReport(), _barrier_placement({}))
        assert audit.all_pass
        assert audit.violations == []
