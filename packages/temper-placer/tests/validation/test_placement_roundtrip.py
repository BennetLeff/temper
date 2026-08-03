"""Unit tests for the transform round-trip oracle (U1).

Covers docs/plans/2026-08-02-009-feat-transform-round-trip-oracle-plan.md
U1's seven scenarios plus the plan-arithmetic correction the portfolio
review demanded: under the ``new_fp_angle + intrinsic`` convention
(verified against ``io/_write_board.py::_reorient_pads``), a footprint
rotated 180 deg whose pad has an intrinsic angle of 90 deg yields an
expected pad body angle of **270**, not 180 (the plan's U1 scenario-3
number was wrong; ``_reorient_pads`` shifts the pad by the *delta*
(180 - 0 = 180), i.e. 90 + 180 = 270).

Structure: PASS scenarios write through the production writer
(``write_placements_to_pcb``) and assert the oracle reports no mismatch;
FAIL scenarios hand-build the written board exactly the way each
historical bug class produced it and assert the oracle fails on the
specific mismatch kind it exists to catch.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.io.kicad_writer import PlacementUpdate, write_placements_to_pcb
from temper_placer.validation.placement_roundtrip import (
    RoundTripResult,
    canonical_angle,
    check_placement_roundtrip,
)

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _board_content(fp_blocks: str) -> str:
    """A minimal, kiutils-parseable board skeleton around footprint blocks."""
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
    """One footprint block.  ``at`` is (x, y, angle-or-None); each pad is
    (number, x, y, angle-or-None) -- angle None omits the angle token."""
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


def _template_components(path: Path):
    """Parse template components in file (unnormalized) coordinates."""
    return parse_kicad_pcb(path, normalize=False).netlist.components


def _write_template(tmp_path: Path, content: str) -> Path:
    template = tmp_path / "template.kicad_pcb"
    template.write_text(content, encoding="utf-8")
    return template


def _placements_dict(
    items: dict[str, tuple[float, float, float]],
) -> dict[str, PlacementUpdate]:
    return {
        ref: PlacementUpdate(ref=ref, x=v[0], y=v[1], rotation=v[2])
        for ref, v in items.items()
    }


# ---------------------------------------------------------------------------
# comparator plumbing
# ---------------------------------------------------------------------------


class TestCanonicalization:
    def test_angle_mod_360(self):
        assert canonical_angle(360.0) == 0.0
        assert canonical_angle(0.0) == 0.0
        assert canonical_angle(270.0) == 270.0
        assert canonical_angle(-90.0) == 270.0
        assert canonical_angle(720.0) == 0.0

    def test_result_passed_and_summary(self):
        from temper_placer.validation.placement_roundtrip import RoundTripMismatch

        ok = RoundTripResult(checked_components=1, checked_pads=2)
        assert ok.passed
        assert "PASS" in ok.summary

        bad = RoundTripResult(
            mismatches=[RoundTripMismatch(ref="U1", kind="footprint_angle")],
            checked_components=1,
            checked_pads=2,
        )
        assert not bad.passed
        assert "FAIL" in bad.summary
        assert "U1" in bad.summary

    def test_required_inputs(self, tmp_path):
        board = _write_template(tmp_path, _board_content(""))
        with pytest.raises(ValueError, match="template_components"):
            check_placement_roundtrip(board, {"U1": (0.0, 0.0)})
        with pytest.raises(ValueError, match="does not exist"):
            check_placement_roundtrip(tmp_path / "nope.kicad_pcb", {}, [])


# ---------------------------------------------------------------------------
# U1 scenarios 1-5: PASS cases written through the production writer
# ---------------------------------------------------------------------------


class TestRoundTripPass:
    def test_scenario1_identity_write(self, tmp_path):
        """All rotations zero: re-parsed geometry equals the model exactly."""
        content = _board_content(
            _fp("U1", (10.0, 20.0, None), [("1", -0.775, 0.0, None), ("2", 0.775, 0.0, None)])
        )
        template = _write_template(tmp_path, content)
        components = _template_components(template)
        out = tmp_path / "out.kicad_pcb"
        write_placements_to_pcb(
            template,
            out,
            _placements_dict({"U1": (10.0, 20.0, 0.0)}),
            components=components,
        )

        result = check_placement_roundtrip(out, {"U1": (10.0, 20.0)}, {}, components)
        assert result.passed, result.summary
        assert result.checked_components == 1
        assert result.checked_pads == 2

    def test_scenario2_rotation_180_symmetric_part(self, tmp_path):
        """Rotation 180 on a symmetric part: footprint angle and every pad
        body shift by 180; oracle reports no mismatch."""
        content = _board_content(
            _fp("U1", (10.0, 20.0, None), [("1", -0.775, 0.0, None), ("2", 0.775, 0.0, None)])
        )
        template = _write_template(tmp_path, content)
        components = _template_components(template)
        out = tmp_path / "out.kicad_pcb"
        write_placements_to_pcb(
            template,
            out,
            _placements_dict({"U1": (50.0, 60.0, 180.0)}),
            components=components,
        )

        written = out.read_text()
        assert "at 50.0 60.0 180.0" in written or "at 50 60 180" in written
        result = check_placement_roundtrip(out, {"U1": (50.0, 60.0)}, {"U1": 180.0}, components)
        assert result.passed, result.summary

    def test_scenario3_intrinsic_pad_angle_corrected_270(self, tmp_path):
        """A footprint rotated to 180 whose pads carry an intrinsic angle of
        90 (pad abs 90 at fp 0) must end with pad body angle 270 -- the
        portfolio review's correction of the plan's erroneous 180.  Written
        through the production writer, the oracle must PASS, and a mutant
        board that re-oriented pads to 180 (the plan's wrong arithmetic)
        must FAIL with expected 270."""
        content = _board_content(
            _fp("U1", (10.0, 20.0, None), [("1", -0.775, 0.0, 90.0), ("2", 0.775, 0.0, 90.0)])
        )
        template = _write_template(tmp_path, content)
        components = _template_components(template)
        out = tmp_path / "out.kicad_pcb"
        write_placements_to_pcb(
            template,
            out,
            _placements_dict({"U1": (50.0, 60.0, 180.0)}),
            components=components,
        )

        # The production writer implements new_fp_angle + intrinsic:
        # pads 90 -> 270.  Verify the file and the oracle agree.
        written = out.read_text()
        assert "270" in written
        result = check_placement_roundtrip(out, {"U1": (50.0, 60.0)}, {"U1": 180.0}, components)
        assert result.passed, result.summary

        # Mutant: re-orient pads to 180 (the plan's erroneous arithmetic).
        # The oracle must FAIL on pad_angle with expected 270, actual 180.
        mutant = _write_template(
            tmp_path,
            _board_content(_fp("U1", (50.0, 60.0, 180.0), [("1", -0.775, 0.0, 180.0), ("2", 0.775, 0.0, 180.0)])),
        )
        mutant_out = tmp_path / "mutant.kicad_pcb"
        mutant_out.write_text(mutant.read_text(), encoding="utf-8")
        bad = check_placement_roundtrip(
            mutant_out, {"U1": (50.0, 60.0)}, {"U1": 180.0}, components
        )
        assert not bad.passed
        pad_angle = [m for m in bad.mismatches if m.kind == "pad_angle"]
        assert pad_angle, f"expected pad_angle mismatches, got: {[str(m) for m in bad.mismatches]}"
        assert pad_angle[0].expected == 270.0
        assert pad_angle[0].actual == 180.0

    def test_scenario4_rotation_normalizing_to_zero(self, tmp_path):
        """A 360-equivalent angle writes as (or re-parses as) 0; mod-360
        canonicalization makes the oracle PASS."""
        content = _board_content(
            _fp("U1", (10.0, 20.0, 270.0), [("1", -0.775, 0.0, 270.0), ("2", 0.775, 0.0, 270.0)])
        )
        template = _write_template(tmp_path, content)
        components = _template_components(template)
        out = tmp_path / "out.kicad_pcb"
        write_placements_to_pcb(
            template,
            out,
            _placements_dict({"U1": (50.0, 60.0, 360.0)}),
            components=components,
        )

        result = check_placement_roundtrip(out, {"U1": (50.0, 60.0)}, {"U1": 360.0}, components)
        assert result.passed, result.summary

    def test_scenario5_center_offset_component(self, tmp_path):
        """A TO-247-style asymmetric part (3 pads, centroid offset (10, 0)):
        the expected anchor is the model position minus the R(-theta)-rotated
        center offset, and the oracle matches the written anchor."""
        content = _board_content(
            _fp(
                "Q1",
                (10.0, 20.0, None),
                [("1", 0.0, 0.0, None), ("2", 10.0, 0.0, None), ("3", 20.0, 0.0, None)],
                lib="Test:TO247",
            )
        )
        template = _write_template(tmp_path, content)
        components = _template_components(template)
        q1 = next(c for c in components if c.ref == "Q1")
        assert q1.attributes["_center_offset_x"] == "10.0"

        out = tmp_path / "out.kicad_pcb"
        pos = (100.0, 100.0)
        write_placements_to_pcb(
            template,
            out,
            _placements_dict({"Q1": (pos[0], pos[1], 90.0)}),
            components=components,
        )

        # R(-90) of (10, 0) is (0, -10): anchor must be (100, 110).
        assert "at 100.0 110.0 90.0" in out.read_text() or "at 100 110 90" in out.read_text()
        result = check_placement_roundtrip(out, {"Q1": pos}, {"Q1": 90.0}, components)
        assert result.passed, result.summary


# ---------------------------------------------------------------------------
# U1 scenarios 6-7: falsifiers that MUST FAIL the oracle
# ---------------------------------------------------------------------------


class TestRoundTripFalsifiers:
    def test_scenario6_dropped_rotation_fails(self, tmp_path):
        """A written board where the solver's rotation was never applied
        (angle stays at the template's) must FAIL on footprint angle and
        every pad body."""
        content = _board_content(
            _fp("U1", (10.0, 20.0, None), [("1", -0.775, 0.0, None), ("2", 0.775, 0.0, None)])
        )
        template = _write_template(tmp_path, content)
        components = _template_components(template)

        # Write with rotation 0 -- the board the pre-fix writer produced --
        # while the model claims the solve chose 180.
        out = tmp_path / "out.kicad_pcb"
        write_placements_to_pcb(
            template, out, _placements_dict({"U1": (50.0, 60.0, 0.0)}), components=components
        )
        result = check_placement_roundtrip(out, {"U1": (50.0, 60.0)}, {"U1": 180.0}, components)
        assert not result.passed
        kinds = {m.kind for m in result.mismatches}
        assert "footprint_angle" in kinds
        assert "pad_angle" in kinds

    def test_scenario7_sign_flip_fails(self, tmp_path):
        """A board written with R(+theta) instead of the sanctioned R(-theta)
        center-offset subtraction must FAIL at the footprint anchor and at
        non-symmetric pad positions.  The two anchors (89.6064, 102.8236 vs
        the sign-flipped 94.4209, 90.7873) are the pcbnew-verified numbers
        from _adapter_convert.py's own docstring."""
        content = _board_content(
            _fp(
                "Q1",
                (10.0, 20.0, None),
                [("1", 0.0, 0.0, None), ("2", 20.0, 8.0, None)],
                lib="Test:TO247",
            )
        )
        template = _write_template(tmp_path, content)
        components = _template_components(template)

        pos = (100.0, 100.0)
        theta = 37.0
        # The sign-flipped (standard-CCW) anchor for center offset (10, 4):
        # pos - R(+37) . (10, 4) = (94.4209, 90.7873).  Written as the board
        # the pre-fix sign bug produced (angle and pads re-oriented fine).
        wrong_anchor = (94.4209, 90.7873)
        mutant = _write_template(
            tmp_path,
            _board_content(
                _fp(
                    "Q1",
                    (wrong_anchor[0], wrong_anchor[1], theta),
                    [("1", 0.0, 0.0, theta), ("2", 20.0, 8.0, theta)],
                    lib="Test:TO247",
                )
            ),
        )
        result = check_placement_roundtrip(mutant, {"Q1": pos}, {"Q1": theta}, components)
        assert not result.passed
        kinds = {m.kind for m in result.mismatches}
        assert "footprint_anchor" in kinds
        assert "pad_position" in kinds
        # Sanity: the expected anchor is the pcbnew-verified one.
        anchor = [m for m in result.mismatches if m.kind == "footprint_anchor"][0]
        exp_x, exp_y = anchor.expected
        assert math.isclose(exp_x, 89.6064, abs_tol=1e-3)
        assert math.isclose(exp_y, 102.8236, abs_tol=1e-3)

    def test_missing_model_ref_reports_mismatch(self, tmp_path):
        """A model ref absent from the written board is itself a failure
        (the writer dropped the component), not a silent skip.  The ref must
        exist in the template for the oracle to know it was expected."""
        content = _board_content(
            _fp("U1", (10.0, 20.0, None), [("1", -0.775, 0.0, None), ("2", 0.775, 0.0, None)])
            + "\n"
            + _fp("U2", (10.0, 40.0, None), [("1", -0.775, 0.0, None), ("2", 0.775, 0.0, None)])
        )
        template = _write_template(tmp_path, content)
        components = _template_components(template)
        assert {c.ref for c in components} == {"U1", "U2"}

        # A written board that only contains U1 (U2 was dropped).
        dropped = _write_template(
            tmp_path,
            _board_content(
                _fp("U1", (10.0, 20.0, None), [("1", -0.775, 0.0, None), ("2", 0.775, 0.0, None)])
            ),
        )
        result = check_placement_roundtrip(
            dropped, {"U1": (10.0, 20.0), "U2": (10.0, 40.0)}, {}, components
        )
        assert not result.passed
        assert any(m.kind == "footprint_missing" for m in result.mismatches)
