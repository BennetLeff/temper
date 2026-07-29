"""Pad bodies must rotate with their footprint when a placement is written.

Root cause of ``pcb/temper.kicad_pcb``'s intra-component copper shorts
(issue #374, docs/evidence/2026-07-29-intra-component-shorts-root-cause.md):
``write_placements_to_pcb`` set ``footprint.at`` rotation but never touched
the pads' own ``(at x y angle)`` angles. In a ``.kicad_pcb`` that angle is
the pad's ABSOLUTE world orientation -- KiCad does not add the footprint's
angle to it -- so rotating the footprint moved every pad's *position* while
leaving every pad *body* unrotated. On an SSOP-20 (0.635 mm pitch,
1.2 x 0.4 mm pads) that puts 1.2 mm of copper across a 0.635 mm pitch:
0.565 mm of solid overlap between every adjacent pad pair.

These tests pin both halves of the contract:

  * WRITE: after ``write_placements_to_pcb`` rotates a footprint, each pad's
    absolute angle equals the new footprint rotation plus that pad's own
    intrinsic (library-defined) rotation -- and the resulting copper does
    not self-overlap.
  * READ: ``_parse_modules`` recovers the *intrinsic* rotation by
    subtracting the footprint angle, so parse(write(x)) is stable rather
    than accumulating a full footprint rotation on every pass.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from temper_placer.io._parse_modules import _extract_components_from_pcb
from temper_placer.io._write_types import PlacementUpdate
from temper_placer.io.kicad_writer import write_placements_to_pcb

kiutils_board = pytest.importorskip("kiutils.board")

_PITCH = 0.635
_PAD_W, _PAD_H = 1.2, 0.4
_N_PADS = 10


def _ssop20_template(path: Path, fp_rotation: float = 0.0, pad_angle: float | None = None) -> Path:
    """A one-footprint board holding an SSOP-20's left pad row."""
    ang = "" if pad_angle is None else f" {pad_angle:g}"
    pads = "\n".join(
        f'    (pad "{i}" smd rect (at -2.6 {-2.8575 + (i - 1) * _PITCH:.4f}{ang}) '
        f'(size {_PAD_W} {_PAD_H}) (layers "F.Cu" "F.Mask" "F.Paste")\n'
        f'      (net {i} "n{i}"))'
        for i in range(1, _N_PADS + 1)
    )
    nets = "".join(f'  (net {i} "n{i}")\n' for i in range(1, _N_PADS + 1))
    path.write_text(
        "(kicad_pcb (version 20211014) (generator test)\n"
        "  (general (thickness 1.6))\n"
        '  (layers (0 "F.Cu" signal) (1 "In1.Cu" signal) (2 "In2.Cu" signal) (31 "B.Cu" signal))\n'
        '  (net 0 "")\n'
        + nets
        + '  (footprint "Package_SO:SSOP-20_3.9x8.7mm_P0.635mm" (layer "F.Cu")\n'
        f"    (at 100 100 {fp_rotation:g})\n"
        '    (property "Reference" "U9")\n'
        f"{pads}\n"
        "  )\n"
        ")\n"
    )
    return path


def _pad_angles(board_path: Path) -> list[float]:
    board = kiutils_board.Board.from_file(str(board_path))
    fp = board.footprints[0]
    return [(pad.position.angle or 0.0) % 360.0 for pad in fp.pads]


def _min_adjacent_gap_mm(board_path: Path) -> float:
    """Smallest edge-to-edge gap between adjacent pads, in the board frame."""
    board = kiutils_board.Board.from_file(str(board_path))
    fp = board.footprints[0]
    frot = fp.position.angle or 0.0

    def world(pad):
        a = math.radians(frot)
        x, y = pad.position.X, pad.position.Y
        return (x * math.cos(a) + y * math.sin(a), -x * math.sin(a) + y * math.cos(a))

    pads = sorted(fp.pads, key=lambda p: int(p.number))
    gaps = []
    for a, b in zip(pads, pads[1:]):
        ax, ay = world(a)
        bx, by = world(b)
        aang = math.radians(a.position.angle or 0.0)
        bang = math.radians(b.position.angle or 0.0)

        # Half-extent of an axis-aligned box rotated by `ang`, along each axis.
        def half(w, h, ang, axis):
            if axis == 0:
                return abs(w / 2 * math.cos(ang)) + abs(h / 2 * math.sin(ang))
            return abs(w / 2 * math.sin(ang)) + abs(h / 2 * math.cos(ang))

        gx = abs(ax - bx) - half(a.size.X, a.size.Y, aang, 0) - half(b.size.X, b.size.Y, bang, 0)
        gy = abs(ay - by) - half(a.size.X, a.size.Y, aang, 1) - half(b.size.X, b.size.Y, bang, 1)
        gaps.append(max(gx, gy))
    return min(gaps)


@pytest.mark.parametrize("rotation", [90.0, 180.0, 270.0])
def test_write_rotates_pad_bodies(tmp_path: Path, rotation: float) -> None:
    template = _ssop20_template(tmp_path / "in.kicad_pcb")
    out = tmp_path / "out.kicad_pcb"

    write_placements_to_pcb(
        template, out, {"U9": PlacementUpdate(ref="U9", x=100.0, y=100.0, rotation=rotation)}
    )

    angles = _pad_angles(out)
    assert len(angles) == _N_PADS
    assert angles == [rotation % 360.0] * _N_PADS, (
        f"pad bodies did not follow the footprint to {rotation} deg: {angles}"
    )


@pytest.mark.parametrize("rotation", [90.0, 270.0])
def test_rotated_pads_do_not_self_overlap(tmp_path: Path, rotation: float) -> None:
    """The defect itself: quarter-turn placement must not squash the pitch."""
    template = _ssop20_template(tmp_path / "in.kicad_pcb")
    out = tmp_path / "out.kicad_pcb"

    write_placements_to_pcb(
        template, out, {"U9": PlacementUpdate(ref="U9", x=100.0, y=100.0, rotation=rotation)}
    )

    gap = _min_adjacent_gap_mm(out)
    expected = _PITCH - _PAD_H  # 0.235 mm
    assert gap == pytest.approx(expected, abs=1e-6), (
        f"adjacent pads {gap:.4f} mm apart after a {rotation} deg placement; "
        f"expected {expected:.4f} mm. A negative gap is solid copper overlap."
    )


def test_intrinsic_pad_rotation_is_preserved(tmp_path: Path) -> None:
    """A pad turned 45 deg in its library stays 45 deg off its footprint."""
    template = _ssop20_template(tmp_path / "in.kicad_pcb", fp_rotation=0.0, pad_angle=45.0)
    out = tmp_path / "out.kicad_pcb"

    write_placements_to_pcb(
        template, out, {"U9": PlacementUpdate(ref="U9", x=100.0, y=100.0, rotation=90.0)}
    )

    assert _pad_angles(out) == [135.0] * _N_PADS


def test_parse_recovers_intrinsic_rotation(tmp_path: Path) -> None:
    """A correctly-written board must not read back a doubled rotation."""
    board_path = _ssop20_template(tmp_path / "b.kicad_pcb", fp_rotation=270.0, pad_angle=270.0)
    board = kiutils_board.Board.from_file(str(board_path))

    components = _extract_components_from_pcb(board, [], (0.0, 0.0))
    assert len(components) == 1
    pins = components[0].pins
    assert pins, "component parsed with no pins"
    # Absolute 270 on a 270-degree footprint means zero intrinsic rotation:
    # consumers add the component rotation themselves.
    assert all(p.pad_rotation_deg == pytest.approx(0.0) for p in pins), [
        p.pad_rotation_deg for p in pins
    ]


def test_write_parse_write_is_stable(tmp_path: Path) -> None:
    """Round-tripping must not accumulate rotation on every pass."""
    template = _ssop20_template(tmp_path / "in.kicad_pcb")
    first = tmp_path / "first.kicad_pcb"
    second = tmp_path / "second.kicad_pcb"

    update = {"U9": PlacementUpdate(ref="U9", x=100.0, y=100.0, rotation=270.0)}
    write_placements_to_pcb(template, first, update)
    write_placements_to_pcb(first, second, update)

    assert _pad_angles(first) == _pad_angles(second) == [270.0] * _N_PADS
    assert _min_adjacent_gap_mm(second) == pytest.approx(_PITCH - _PAD_H, abs=1e-6)
