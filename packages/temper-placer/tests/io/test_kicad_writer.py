"""Tests for KiCad PCB writer."""

import json
from pathlib import Path

import numpy as np

from temper_placer.core.state import PlacementState
from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.io.kicad_writer import (
    PlacementUpdate,
    WriteResult,
    placements_from_json,
    placements_to_json,
    state_to_placements,
    write_placements_to_pcb,
)
from temper_placer.validation.placement_roundtrip import check_placement_roundtrip

# ---------------------------------------------------------------------------
# helpers for the round-trip oracle coverage (plan 2026-08-02-009 U2)
# ---------------------------------------------------------------------------


def _board_content(fp_blocks: str) -> str:
    return (
        "(kicad_pcb (version 20240108) (generator pcbnew)\n"
        "  (general (thickness 1.6))\n"
        '  (paper "A4")\n'
        "  (layers\n"
        '    (0 "F.Cu" signal)\n'
        '    (31 "B.Cu" signal)\n'
        '    (44 "Edge.Cuts" user)\n'
        "  )\n"
        "  (setup (pad_to_mask_clearance 0))\n"
        f"{fp_blocks}\n"
        ")\n"
    )


def _fp(
    ref: str,
    at: tuple[float, float, float | None],
    pads: list[tuple[str, float, float, float | None]],
    lib: str = "Test:PART",
) -> str:
    at_x, at_y, at_ang = at
    at_suffix = "" if at_ang is None else f" {at_ang}"
    pad_blocks = []
    for num, px, py, p_ang in pads:
        p_suffix = "" if p_ang is None else f" {p_ang}"
        pad_blocks.append(
            f'    (pad "{num}" smd rect (at {px} {py}{p_suffix}) (size 0.6 1.2)'
            f' (layers "F.Cu" "F.Paste" "F.Mask") (net 1 "n1"))'
        )
    pads_str = "\n".join(pad_blocks)
    return (
        f'  (footprint "{lib}" (layer "F.Cu")\n'
        f"    (tstamp 00000000-0000-0000-0000-000000000001)\n"
        f"    (at {at_x} {at_y}{at_suffix})\n"
        f'    (property "Reference" "{ref}" (at 0 0 0) (layer "F.SilkS"))\n'
        f"{pads_str}\n"
        "  )"
    )


def _template_and_components(tmp_path: Path, content: str) -> tuple[Path, list]:
    template = tmp_path / "template.kicad_pcb"
    template.write_text(content, encoding="utf-8")
    components = parse_kicad_pcb(template, normalize=False).netlist.components
    return template, components


def _asymmetric_part(ref: str, at: tuple[float, float, float | None]) -> str:
    """A 3-pad asymmetric footprint (pad centroid offset (10, 0)) with a
    distinct intrinsic pad angle on pad 1, so the round-trip exercises both
    the center-offset frame conversion and pad re-orientation."""
    return _fp(
        ref,
        at,
        [("1", 0.0, 0.0, 45.0), ("2", 10.0, 0.0, None), ("3", 20.0, 0.0, None)],
        lib="Test:ASYM3",
    )


class TestPlacementUpdate:
    """Tests for PlacementUpdate dataclass."""

    def test_basic_update(self):
        update = PlacementUpdate(ref="U1", x=10.0, y=20.0, rotation=90.0)
        assert update.ref == "U1"
        assert update.x == 10.0
        assert update.y == 20.0
        assert update.rotation == 90.0


class TestWriteResult:
    """Tests for WriteResult dataclass."""

    def test_no_warnings(self):
        result = WriteResult(
            output_path=Path("/tmp/test.kicad_pcb"),
            components_updated=10,
            components_skipped=2,
            warnings=[],
        )
        assert not result.has_warnings
        assert result.components_updated == 10
        assert result.components_skipped == 2

    def test_with_warnings(self):
        result = WriteResult(
            output_path=Path("/tmp/test.kicad_pcb"),
            components_updated=10,
            components_skipped=2,
            warnings=["Component X not found"],
        )
        assert result.has_warnings
        assert len(result.warnings) == 1


class TestPlacementsJson:
    """Tests for JSON serialization of placements."""

    def test_placements_to_json(self):
        placements = {
            "U1": PlacementUpdate(ref="U1", x=10.0, y=20.0, rotation=90.0),
            "R1": PlacementUpdate(ref="R1", x=30.0, y=40.0, rotation=0.0),
        }
        data = placements_to_json(placements)

        assert data["U1"]["x"] == 10.0
        assert data["U1"]["y"] == 20.0
        assert data["U1"]["rotation"] == 90.0
        assert data["R1"]["x"] == 30.0
        assert data["R1"]["rotation"] == 0.0

    def test_placements_from_json(self):
        data = {
            "U1": {"x": 10.0, "y": 20.0, "rotation": 90.0},
            "R1": {"x": 30.0, "y": 40.0, "rotation": 0.0},
        }
        placements = placements_from_json(data)

        assert placements["U1"].ref == "U1"
        assert placements["U1"].x == 10.0
        assert placements["U1"].y == 20.0
        assert placements["U1"].rotation == 90.0
        assert placements["R1"].ref == "R1"

    def test_roundtrip(self):
        """Test that to_json -> from_json preserves data."""
        original = {
            "U1": PlacementUpdate(ref="U1", x=10.5, y=20.5, rotation=180.0),
            "C1": PlacementUpdate(ref="C1", x=0.0, y=0.0, rotation=270.0),
        }

        data = placements_to_json(original)
        restored = placements_from_json(data)

        for ref in original:
            assert restored[ref].ref == original[ref].ref
            assert restored[ref].x == original[ref].x
            assert restored[ref].y == original[ref].y
            assert restored[ref].rotation == original[ref].rotation

    def test_json_serializable(self):
        """Test that placements_to_json output is JSON-serializable."""
        placements = {
            "U1": PlacementUpdate(ref="U1", x=10.0, y=20.0, rotation=90.0),
        }
        data = placements_to_json(placements)

        # Should not raise
        json_str = json.dumps(data)
        assert isinstance(json_str, str)

        # Should round-trip through JSON
        restored_data = json.loads(json_str)
        restored = placements_from_json(restored_data)
        assert restored["U1"].x == 10.0


class TestStateToPlacementsConversion:
    """Tests for converting PlacementState to placements."""

    def test_basic_conversion(self):
        """Test converting a simple state to placements."""

        # Create a state with 3 components
        positions = np.array([[10.0, 20.0], [30.0, 40.0], [50.0, 60.0]])
        # Rotation logits: strongly prefer specific rotations
        # Component 0: 0 degrees, Component 1: 90 degrees, Component 2: 180 degrees
        logits = np.array(
            [
                [10.0, 0.0, 0.0, 0.0],  # 0 deg
                [0.0, 10.0, 0.0, 0.0],  # 90 deg
                [0.0, 0.0, 10.0, 0.0],  # 180 deg
            ]
        )
        state = PlacementState.from_positions(positions, rotation_logits=logits)
        component_refs = ["U1", "R1", "C1"]

        placements = state_to_placements(state, component_refs)

        assert len(placements) == 3
        assert placements["U1"].x == 10.0
        assert placements["U1"].y == 20.0
        assert placements["U1"].rotation == 0.0  # 0 * 90
        assert placements["R1"].x == 30.0
        assert placements["R1"].rotation == 90.0  # 1 * 90
        assert placements["C1"].rotation == 180.0  # 2 * 90

    def test_conversion_with_origin(self):
        """Test that origin offset is applied."""

        positions = np.array([[10.0, 20.0]])
        state = PlacementState.from_positions(positions)
        component_refs = ["U1"]

        placements = state_to_placements(state, component_refs, origin=(100.0, 50.0))

        assert placements["U1"].x == 110.0  # 10 + 100
        assert placements["U1"].y == 70.0  # 20 + 50


# ---------------------------------------------------------------------------
# Round-trip oracle coverage for the production write paths (U2)
#
# docs/plans/2026-08-02-009-feat-transform-round-trip-oracle-plan.md U2:
# every production write path round-trips through the comparator, with the
# incident-class falsifiers asserted to fail.  The written file is re-parsed
# from disk (KTD4) and compared exactly against the model (KTD2).
# ---------------------------------------------------------------------------


class TestWritePlacementsToPcbRoundTrip:
    """``write_placements_to_pcb`` geometry round-trips through the oracle."""

    def test_mixed_rotations_asymmetric_parts_pass(self, tmp_path):
        """Mixed {0, 90, 180, 270} rotations on asymmetric (center-offset)
        parts: oracle PASS after re-parse."""
        content = _board_content(
            _asymmetric_part("U1", (10.0, 10.0, None))
            + "\n"
            + _asymmetric_part("U2", (40.0, 10.0, None))
            + "\n"
            + _asymmetric_part("U3", (10.0, 40.0, None))
            + "\n"
            + _asymmetric_part("U4", (40.0, 40.0, None))
        )
        template, components = _template_and_components(tmp_path, content)

        placements = {
            "U1": PlacementUpdate(ref="U1", x=10.0, y=10.0, rotation=0.0),
            "U2": PlacementUpdate(ref="U2", x=40.0, y=10.0, rotation=90.0),
            "U3": PlacementUpdate(ref="U3", x=10.0, y=40.0, rotation=180.0),
            "U4": PlacementUpdate(ref="U4", x=40.0, y=40.0, rotation=270.0),
        }
        out = tmp_path / "out.kicad_pcb"
        write_placements_to_pcb(template, out, placements, components=components)

        rotations = {ref: p.rotation for ref, p in placements.items()}
        positions = {ref: (p.x, p.y) for ref, p in placements.items()}
        result = check_placement_roundtrip(out, positions, rotations, components)
        assert result.passed, result.summary
        assert result.checked_components == 4

    def test_center_offset_component_anchor_differs_from_model(self, tmp_path):
        """A center-offset component: the written anchor differs from the
        model position by the R(-theta)-rotated offset, and the oracle
        (which computes the same subtraction) PASSES."""
        template, components = _template_and_components(
            tmp_path, _board_content(_asymmetric_part("Q1", (10.0, 20.0, None)))
        )
        pos = (100.0, 100.0)
        out = tmp_path / "out.kicad_pcb"
        write_placements_to_pcb(
            template,
            out,
            {"Q1": PlacementUpdate(ref="Q1", x=pos[0], y=pos[1], rotation=90.0)},
            components=components,
        )

        # centroid (10, 0); R(-90).(10, 0) = (0, -10): anchor (100, 110).
        written = out.read_text()
        assert "at 100.0 110.0 90.0" in written or "at 100 110 90" in written
        assert "at 100.0 100.0" not in written
        result = check_placement_roundtrip(out, {"Q1": pos}, {"Q1": 90.0}, components)
        assert result.passed, result.summary

    def test_falsifier_rotation_dropped_fails(self, tmp_path):
        """Mutant that skips the angle update (solved rotation never
        reaches the footprint): oracle FAILS on footprint angle."""
        template, components = _template_and_components(
            tmp_path, _board_content(_asymmetric_part("U1", (10.0, 20.0, None)))
        )
        out = tmp_path / "out.kicad_pcb"
        # rotation 0 written, model claims the solve chose 90.
        write_placements_to_pcb(
            template,
            out,
            {"U1": PlacementUpdate(ref="U1", x=50.0, y=60.0, rotation=0.0)},
            components=components,
        )
        result = check_placement_roundtrip(out, {"U1": (50.0, 60.0)}, {"U1": 90.0}, components)
        assert not result.passed
        assert any(m.kind == "footprint_angle" for m in result.mismatches)
        assert any(m.kind == "pad_angle" for m in result.mismatches)

    def test_falsifier_pad_bodies_not_reoriented_fails(self, tmp_path):
        """Pre-#412 class: the footprint rotates but pad bodies are left
        behind.  Oracle FAILS on pad body angles (this was the 55-of-60
        intra-component short on the real board)."""
        template, components = _template_and_components(
            tmp_path, _board_content(_asymmetric_part("U1", (10.0, 20.0, None)))
        )
        # Hand-build what the pre-fix writer emitted: footprint at 90 with
        # every pad body still at its template angle (0 / 0 / 45 unchanged).
        mutant = tmp_path / "mutant.kicad_pcb"
        mutant.write_text(
            _board_content(
                _fp(
                    "U1",
                    (50.0, 60.0, 90.0),
                    [("1", 0.0, 0.0, 45.0), ("2", 10.0, 0.0, None), ("3", 20.0, 0.0, None)],
                    lib="Test:ASYM3",
                )
            ),
            encoding="utf-8",
        )
        result = check_placement_roundtrip(mutant, {"U1": (50.0, 60.0)}, {"U1": 90.0}, components)
        assert not result.passed
        pad_angles = [m for m in result.mismatches if m.kind == "pad_angle"]
        assert pad_angles, f"expected pad_angle mismatches: {[str(m) for m in result.mismatches]}"
        # Pad 1 intrinsic 45: expected 90 + 45 = 135, actual 45.
        pad1 = [m for m in pad_angles if m.pad == "1"]
        assert pad1 and pad1[0].expected == 135.0 and pad1[0].actual == 45.0

    def test_falsifier_center_offset_not_subtracted_fails(self, tmp_path):
        """Pre-#460 class: center offset not subtracted (writer called
        without ``components=``, its documented pre-fix shape).  Oracle
        FAILS on footprint position for the asymmetric component."""
        template, components = _template_and_components(
            tmp_path, _board_content(_asymmetric_part("Q1", (10.0, 20.0, None)))
        )
        out = tmp_path / "out.kicad_pcb"
        # No components= -> the writer leaves the box centre as the anchor.
        write_placements_to_pcb(
            template,
            out,
            {"Q1": PlacementUpdate(ref="Q1", x=100.0, y=100.0, rotation=90.0)},
            components=None,
        )
        result = check_placement_roundtrip(
            out, {"Q1": (100.0, 100.0)}, {"Q1": 90.0}, components
        )
        assert not result.passed
        assert any(m.kind == "footprint_anchor" for m in result.mismatches)


class TestStateToPlacementsRoundTrip:
    """``state_to_placements`` -> ``write_placements_to_pcb`` round-trips."""

    def test_full_state_round_trip_pass(self, tmp_path):
        """A full PlacementState (mixed rotations, center-offset components)
        converts, writes, re-parses, and PASSES the oracle."""
        template, components = _template_and_components(
            tmp_path,
            _board_content(
                _asymmetric_part("U1", (10.0, 10.0, None))
                + "\n"
                + _asymmetric_part("U2", (40.0, 10.0, None))
            ),
        )
        positions = np.array([[10.0, 10.0], [40.0, 10.0]])
        logits = np.array(
            [
                [10.0, 0.0, 0.0, 0.0],  # 0 deg
                [0.0, 10.0, 0.0, 0.0],  # 90 deg
            ]
        )
        state = PlacementState.from_positions(positions, rotation_logits=logits)
        refs = ["U1", "U2"]
        placements = state_to_placements(state, refs, components=components)

        out = tmp_path / "out.kicad_pcb"
        write_placements_to_pcb(template, out, placements, components=components)

        rotations = {ref: p.rotation for ref, p in placements.items()}
        model_pos = {ref: (p.x, p.y) for ref, p in placements.items()}
        result = check_placement_roundtrip(out, model_pos, rotations, components)
        assert result.passed, result.summary
        assert result.checked_components == 2
