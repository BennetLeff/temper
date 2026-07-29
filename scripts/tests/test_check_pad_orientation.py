"""Tests for check_pad_orientation.py.

Fixtures are hand-written ``.kicad_pcb`` text rather than kiutils-built
boards on purpose: this gate exists because a *serializer* dropped an
optional token, so every fixture must be able to express the exact
presence/absence of a pad's ``(at x y angle)`` angle, which a library's
defaulting would paper over.

The canonical geometry is a real SSOP-20 (Package_SO, 0.635 mm pitch,
1.2 x 0.4 mm pads) -- the package that made this defect visible on
``pcb/temper.kicad_pcb``. At 270 degrees:

  * with each pad carrying absolute angle 270, adjacent pads are 0.635 mm
    apart with 0.4 mm of copper across the pitch axis -> 0.235 mm gap, clear;
  * with the pad angles omitted (absolute 0, the serializer bug), the same
    pads present 1.2 mm of copper across a 0.635 mm pitch -> 0.565 mm of
    solid overlap, i.e. a short.

Groups:
  TestRotationReachedPads  -- check 1: rotated footprint, unrotated pad bodies
  TestOverlap              -- check 2: intra-footprint copper overlap
  TestGeometry             -- the separating-axis primitive itself
  TestAntiVacuity          -- fail-closed on missing/empty/unparseable input
  TestFailBeforePassAfter  -- explicit before/after falsifier pair
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "check_pad_orientation", _SCRIPTS / "check_pad_orientation.py"
)
assert _spec and _spec.loader
check_pad_orientation = importlib.util.module_from_spec(_spec)
sys.modules["check_pad_orientation"] = check_pad_orientation
_spec.loader.exec_module(check_pad_orientation)

Pad = check_pad_orientation.Pad
BoardParseError = check_pad_orientation.BoardParseError

# SSOP-20 side-row pad geometry, footprint-local (mm).
_PITCH = 0.635
_PAD_W, _PAD_H = 1.2, 0.4


def _ssop20_board(
    fp_rotation: float, pad_angle: float | None, nets: list[str] | None = None
) -> str:
    """Render a one-footprint board: an SSOP-20 left row of 10 pads.

    *pad_angle* of ``None`` omits the angle token entirely -- the exact
    on-disk shape the buggy serializer produced.
    """
    if nets is None:
        nets = [f"net{i}" for i in range(1, 11)]
    ang = "" if pad_angle is None else f" {pad_angle:g}"
    pads = []
    for i, net in enumerate(nets, start=1):
        y = -2.8575 + (i - 1) * _PITCH
        pads.append(
            f'    (pad "{i}" smd rect (at -2.6 {y:.4f}{ang}) (size {_PAD_W} {_PAD_H}) '
            f'(layers "F.Cu" "F.Mask" "F.Paste")\n'
            f'      (net {i} "{net}"))'
        )
    pad_block = "\n".join(pads)
    return (
        "(kicad_pcb (version 20211014) (generator test)\n"
        "  (general (thickness 1.6))\n"
        '  (layers (0 "F.Cu" signal) (31 "B.Cu" signal))\n'
        '  (net 0 "")\n'
        + "".join(f'  (net {i} "{n}")\n' for i, n in enumerate(nets, start=1))
        + '  (footprint "Package_SO:SSOP-20_3.9x8.7mm_P0.635mm" (layer "F.Cu")\n'
        f"    (at 124.21 85.63 {fp_rotation:g})\n"
        '    (property "Reference" "U9")\n'
        f"{pad_block}\n"
        "  )\n"
        ")\n"
    )


def _write(tmp_path: Path, text: str, name: str = "b.kicad_pcb") -> Path:
    p = tmp_path / name
    p.write_text(text)
    return p


class TestRotationReachedPads:
    def test_rotated_footprint_with_unrotated_pads_is_flagged(self, tmp_path: Path) -> None:
        board = _write(tmp_path, _ssop20_board(fp_rotation=270, pad_angle=None))
        rep = check_pad_orientation.check_board(board)
        assert len(rep.unrotated_pads) == 1, rep.unrotated_pads
        assert "U9" in rep.unrotated_pads[0]
        assert "270" in rep.unrotated_pads[0]

    def test_explicit_zero_angle_is_flagged_too(self, tmp_path: Path) -> None:
        """An explicitly-written 0 means the same thing as an omitted token."""
        board = _write(tmp_path, _ssop20_board(fp_rotation=90, pad_angle=0))
        rep = check_pad_orientation.check_board(board)
        assert len(rep.unrotated_pads) == 1, rep.unrotated_pads

    def test_correctly_rotated_pads_are_clean(self, tmp_path: Path) -> None:
        board = _write(tmp_path, _ssop20_board(fp_rotation=270, pad_angle=270))
        rep = check_pad_orientation.check_board(board)
        assert rep.unrotated_pads == []

    @pytest.mark.parametrize("rotation", [0, 180])
    def test_half_turns_are_exempt(self, tmp_path: Path, rotation: int) -> None:
        """180 degrees maps an axis-aligned pad onto itself: unobservable."""
        board = _write(tmp_path, _ssop20_board(fp_rotation=rotation, pad_angle=None))
        rep = check_pad_orientation.check_board(board)
        assert rep.unrotated_pads == []

    def test_allowlisted_library_is_exempt(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setitem(
            check_pad_orientation.ALLOWLIST,
            "Package_SO:SSOP-20_3.9x8.7mm_P0.635mm",
            "test justification",
        )
        board = _write(tmp_path, _ssop20_board(fp_rotation=270, pad_angle=None))
        rep = check_pad_orientation.check_board(board)
        assert rep.unrotated_pads == []


class TestOverlap:
    def test_unrotated_pad_bodies_overlap_across_the_pitch(self, tmp_path: Path) -> None:
        """The whole point: 1.2 mm of copper on a 0.635 mm pitch."""
        board = _write(tmp_path, _ssop20_board(fp_rotation=270, pad_angle=None))
        rep = check_pad_orientation.check_board(board)
        # 10 pads, all distinct nets. Adjacent pads are 0.635 mm apart and
        # 1.2 mm wide across that axis -> 0.565 mm of overlap, 9 pairs. Pads
        # two apart are 1.270 mm from centre to centre -> a 0.070 mm gap,
        # clear. So exactly the 9 adjacent pairs short, matching the
        # adjacent-only pattern KiCad reports for U9 on the real board.
        assert len(rep.overlaps) == 9, rep.overlaps
        assert all("U9" in line for line in rep.overlaps)

    def test_correctly_rotated_pads_do_not_overlap(self, tmp_path: Path) -> None:
        board = _write(tmp_path, _ssop20_board(fp_rotation=270, pad_angle=270))
        rep = check_pad_orientation.check_board(board)
        assert rep.overlaps == []
        assert rep.pairs_compared == 45  # C(10, 2), all distinct nets

    def test_same_net_pads_may_overlap(self, tmp_path: Path) -> None:
        """Two pads of one net touching is a net tie, not a short."""
        nets = ["shared"] * 10
        board = _write(tmp_path, _ssop20_board(fp_rotation=270, pad_angle=None, nets=nets))
        rep = check_pad_orientation.check_board(board)
        assert rep.overlaps == []

    def test_exact_edge_contact_counts_as_a_short(self, tmp_path: Path) -> None:
        """Zero gap is a copper connection, not a clearance of zero.

        This is the ``K1`` case on the real board: two 6.35 mm-wide pads on a
        6.35 mm pitch, meeting exactly.
        """
        a = Pad("13", "rect", "a", ("F.Cu",), cx=0.0, cy=0.0, width=6.35, height=1.2, angle_deg=0)
        b = Pad("14", "rect", "b", ("F.Cu",), cx=6.35, cy=0.0, width=6.35, height=1.2, angle_deg=0)
        assert check_pad_orientation.pads_overlap(a, b)

    def test_pads_on_disjoint_layers_are_not_compared(self, tmp_path: Path) -> None:
        a = Pad("1", "rect", "a", ("F.Cu",), cx=0.0, cy=0.0, width=2.0, height=2.0, angle_deg=0)
        b = Pad("2", "rect", "b", ("B.Cu",), cx=0.0, cy=0.0, width=2.0, height=2.0, angle_deg=0)
        assert not check_pad_orientation._layers_intersect(a, b)

    def test_through_hole_wildcard_layer_intersects_everything(self) -> None:
        a = Pad("1", "circle", "a", ("*.Cu",), cx=0.0, cy=0.0, width=2.0, height=2.0, angle_deg=0)
        b = Pad("2", "rect", "b", ("B.Cu",), cx=0.0, cy=0.0, width=2.0, height=2.0, angle_deg=0)
        assert check_pad_orientation._layers_intersect(a, b)


class TestGeometry:
    def test_separated_rects_do_not_overlap(self) -> None:
        a = Pad("1", "rect", "a", ("F.Cu",), cx=0.0, cy=0.0, width=1.0, height=1.0, angle_deg=0)
        b = Pad("2", "rect", "b", ("F.Cu",), cx=2.0, cy=0.0, width=1.0, height=1.0, angle_deg=0)
        assert not check_pad_orientation.pads_overlap(a, b)

    def test_rotation_changes_the_verdict(self) -> None:
        """1.2 x 0.4 pads 0.635 mm apart: overlapping at 0, clear at 90.

        This single pair is the whole defect in miniature -- the SSOP-20's
        adjacent-pad geometry, with the pad angle the only thing that varies.
        """

        def pad(number: str, net: str, cx: float, angle: float) -> Pad:
            return Pad(
                number=number,
                shape="rect",
                net=net,
                layers=("F.Cu",),
                cx=cx,
                cy=0.0,
                width=1.2,
                height=0.4,
                angle_deg=angle,
            )

        assert check_pad_orientation.pads_overlap(pad("1", "a", 0.0, 0), pad("2", "b", 0.635, 0))
        assert not check_pad_orientation.pads_overlap(
            pad("1", "a", 0.0, 90), pad("2", "b", 0.635, 90)
        )

    def test_overlapping_circles(self) -> None:
        """The R30 case: 8 mm round pads on a 5 mm pitch."""
        a = Pad("1", "circle", "a", ("*.Cu",), cx=0.0, cy=0.0, width=8.0, height=8.0, angle_deg=0)
        b = Pad("2", "circle", "b", ("*.Cu",), cx=5.0, cy=0.0, width=8.0, height=8.0, angle_deg=0)
        assert check_pad_orientation.pads_overlap(a, b)


class TestAntiVacuity:
    def test_missing_board_fails(self, tmp_path: Path) -> None:
        assert check_pad_orientation.main([str(tmp_path / "nope.kicad_pcb")]) == 1

    def test_unparseable_board_fails(self, tmp_path: Path) -> None:
        board = _write(tmp_path, "(kicad_pcb (version 1)\n")  # unbalanced
        assert check_pad_orientation.main([str(board)]) == 1

    def test_non_board_document_fails(self, tmp_path: Path) -> None:
        board = _write(tmp_path, '(footprint "x" (at 0 0))\n')
        assert check_pad_orientation.main([str(board)]) == 1

    def test_board_with_no_footprints_fails(self, tmp_path: Path) -> None:
        board = _write(tmp_path, '(kicad_pcb (version 20211014) (net 0 ""))\n')
        assert check_pad_orientation.main([str(board)]) == 1

    def test_board_with_no_pads_fails(self, tmp_path: Path) -> None:
        board = _write(
            tmp_path,
            "(kicad_pcb (version 20211014)\n"
            '  (footprint "X" (at 0 0) (property "Reference" "U1"))\n)\n',
        )
        assert check_pad_orientation.main([str(board)]) == 1

    def test_board_with_no_comparable_pairs_fails(self, tmp_path: Path) -> None:
        """One pad means zero pairs: the overlap check measured nothing."""
        board = _write(
            tmp_path,
            "(kicad_pcb (version 20211014)\n"
            '  (footprint "X" (at 0 0) (property "Reference" "U1")\n'
            '    (pad "1" smd rect (at 0 0) (size 1 1) (layers "F.Cu") (net 1 "n1")))\n)\n',
        )
        assert check_pad_orientation.main([str(board)]) == 1


class TestFailBeforePassAfter:
    def test_gate_fails_on_dropped_angles_and_passes_once_written(self, tmp_path: Path) -> None:
        """The falsifier: one edit -- adding the pad angles -- flips the verdict."""
        broken = _write(tmp_path, _ssop20_board(270, pad_angle=None), "broken.kicad_pcb")
        assert check_pad_orientation.main([str(broken)]) == 1

        fixed = _write(tmp_path, _ssop20_board(270, pad_angle=270), "fixed.kicad_pcb")
        assert check_pad_orientation.main([str(fixed)]) == 0
