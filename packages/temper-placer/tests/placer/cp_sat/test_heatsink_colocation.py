"""The shared-heatsink co-location constraint must reject the board as
committed, and accept a placement that could actually be assembled.

A constraint never seen to reject anything is not a constraint, so the
first test here reads ``pcb/temper.kicad_pcb`` directly (read-only) and
asserts the real, current U5/U6 placement fails.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from temper_placer.placer.cp_sat.heatsink_colocation import (
    ALIGNMENT_TOLERANCE_MM,
    COMMON_ROTATIONS,
    HEATSINK_GROUPS,
    HS1_MOUNTING_FACE_LENGTH_MM,
    MAX_COLOCATED_GAP_MM,
    TO247_FOOTPRINT_WIDTH_MM,
    check_heatsink_colocation,
    heatsink_colocation_wire_constraints,
)

REPO_ROOT = Path(__file__).resolve().parents[5]
REAL_BOARD = REPO_ROOT / "pcb" / "temper.kicad_pcb"

HS1 = HEATSINK_GROUPS[0]

# The two TO-247 IGBTs' unrotated box size, as ``parse_kicad_pcb`` reports
# it for ``Package_TO_SOT_THT:TO-247-3_Vertical``.
TO247_W0_H0 = (16.4, 5.9)


def test_derived_gap_is_face_length_less_two_packages():
    assert MAX_COLOCATED_GAP_MM == pytest.approx(
        HS1_MOUNTING_FACE_LENGTH_MM - 2 * TO247_FOOTPRINT_WIDTH_MM
    )
    assert MAX_COLOCATED_GAP_MM == pytest.approx(87.2)


def test_rejects_the_committed_board_placement():
    """The whole point: U5 at 270deg and U6 at 180deg is unbuildable."""
    from temper_placer.io.kicad_parser import parse_kicad_pcb

    assert REAL_BOARD.exists(), f"board not found: {REAL_BOARD}"
    result = parse_kicad_pcb(REAL_BOARD, normalize=False)
    by_ref = {c.ref: c for c in result.netlist.components}
    for ref in HS1.refs:
        assert ref in by_ref, f"{ref} missing from the real board"

    positions = {r: tuple(by_ref[r].initial_position) for r in HS1.refs}
    rotations = {r: int(by_ref[r].initial_rotation) for r in HS1.refs}
    sizes = {r: tuple(by_ref[r].bounds) for r in HS1.refs}

    # Guard the premise: if the board is ever fixed, this test must fail
    # loudly rather than keep asserting a stale violation.
    assert rotations == {"U5": 3, "U6": 2}, (
        f"committed rotations changed: {rotations} -- re-derive this test "
        f"against the new board before editing the expectation"
    )

    violations = check_heatsink_colocation(positions, rotations, sizes, HS1)
    kinds = {v.kind for v in violations}

    assert "rotation" in kinds, f"expected a rotation violation, got {violations}"
    assert "alignment" in kinds, f"expected an alignment violation, got {violations}"

    rot_v = next(v for v in violations if v.kind == "rotation")
    assert "270deg" in rot_v.detail and "180deg" in rot_v.detail, rot_v.detail

    align_v = next(v for v in violations if v.kind == "alignment")
    assert align_v.measured > 70.0, align_v
    assert align_v.limit == ALIGNMENT_TOLERANCE_MM


def test_accepts_a_buildable_placement():
    """Same rotation, collinear, inside the heatsink face."""
    positions = {"U5": (40.0, 100.0), "U6": (60.0, 100.0)}
    rotations = {"U5": 0, "U6": 0}
    sizes = {"U5": TO247_W0_H0, "U6": TO247_W0_H0}
    assert check_heatsink_colocation(positions, rotations, sizes, HS1) == []


@pytest.mark.parametrize("rot", COMMON_ROTATIONS)
def test_accepts_every_common_rotation(rot: int):
    """All four agreeing rotations describe equally buildable assemblies."""
    offset = (20.0, 0.0) if rot % 2 == 0 else (0.0, 20.0)
    positions = {"U5": (60.0, 100.0), "U6": (60.0 + offset[0], 100.0 + offset[1])}
    rotations = {"U5": rot, "U6": rot}
    sizes = {"U5": TO247_W0_H0, "U6": TO247_W0_H0}
    assert check_heatsink_colocation(positions, rotations, sizes, HS1) == []


def test_rejects_rotation_mismatch_even_when_touching():
    """Rotation is not fixable by moving the parts closer together."""
    positions = {"U5": (60.0, 100.0), "U6": (72.0, 100.0)}
    rotations = {"U5": 0, "U6": 1}
    sizes = {"U5": TO247_W0_H0, "U6": TO247_W0_H0}
    violations = check_heatsink_colocation(positions, rotations, sizes, HS1)
    assert [v.kind for v in violations if v.kind == "rotation"] == ["rotation"]


def test_rejects_a_gap_wider_than_the_heatsink_face():
    positions = {"U5": (10.0, 100.0), "U6": (10.0 + MAX_COLOCATED_GAP_MM + 20.0, 100.0)}
    rotations = {"U5": 0, "U6": 0}
    sizes = {"U5": TO247_W0_H0, "U6": TO247_W0_H0}
    violations = check_heatsink_colocation(positions, rotations, sizes, HS1)
    assert [v.kind for v in violations] == ["separation"]


def test_rejects_perpendicular_offset_beyond_tolerance():
    positions = {"U5": (40.0, 100.0), "U6": (60.0, 100.0 + ALIGNMENT_TOLERANCE_MM + 0.5)}
    rotations = {"U5": 0, "U6": 0}
    sizes = {"U5": TO247_W0_H0, "U6": TO247_W0_H0}
    violations = check_heatsink_colocation(positions, rotations, sizes, HS1)
    assert [v.kind for v in violations] == ["alignment"]


# ---------------------------------------------------------------------------
# Wire format
# ---------------------------------------------------------------------------

# Every wire type this module emits must already exist in the Pumpkin
# engine's own ``match ctype`` (main.rs:307-627) -- an unregistered type is
# ``exit(2)``, not a warning.
PUMPKIN_REGISTERED_TYPES = frozenset(
    {
        "separated",
        "adjacent",
        "aligned",
        "anchored",
        "enclosing",
        "keepout",
        "on_side",
        "bounded",
        "fixed_rotation",
        "loop_area",
    }
)


@pytest.mark.parametrize("rot", COMMON_ROTATIONS)
def test_wire_constraints_use_only_registered_types(rot: int):
    wire = heatsink_colocation_wire_constraints(HS1, rot)
    assert wire, "expected constraints to be emitted"
    for c in wire:
        assert c["type"] in PUMPKIN_REGISTERED_TYPES, c


def test_wire_constraints_match_engine_source_registration():
    """Read the engine's own dispatch, so this cannot drift silently."""
    main_rs = REPO_ROOT / "docs" / "evidence" / "2026-08-07-pumpkin-engine" / "src" / "main.rs"
    source = main_rs.read_text()
    for rot in COMMON_ROTATIONS:
        for c in heatsink_colocation_wire_constraints(HS1, rot):
            assert f'"{c["type"]}" => {{' in source, (
                f"pumpkin_engine has no arm for {c['type']!r} -- it would exit(2)"
            )


@pytest.mark.parametrize("rot", COMMON_ROTATIONS)
def test_wire_constraints_pin_both_igbts_to_the_same_rotation(rot: int):
    wire = heatsink_colocation_wire_constraints(HS1, rot)
    pins = {c["component"]: c["rot"] for c in wire if c["type"] == "fixed_rotation"}
    assert pins == {"U5": rot, "U6": rot}


def test_alignment_axis_is_perpendicular_to_the_row():
    """rot 0/2 puts the lead row along X, so centres must share Y."""
    for rot in (0, 2):
        aligned = next(c for c in heatsink_colocation_wire_constraints(HS1, rot) if c["type"] == "aligned")
        # main.rs:402 / handlers/aligned.py:46 treat only "x"/"major" as cx.
        assert aligned["axis"] == "horizontal"
    for rot in (1, 3):
        aligned = next(c for c in heatsink_colocation_wire_constraints(HS1, rot) if c["type"] == "aligned")
        assert aligned["axis"] == "x"


def test_wire_constraints_drop_absent_components():
    assert heatsink_colocation_wire_constraints(HS1, 0, present_refs=frozenset({"U5"})) == []


def test_rejects_an_out_of_range_rotation():
    with pytest.raises(ValueError, match="rot_index"):
        heatsink_colocation_wire_constraints(HS1, 4)
