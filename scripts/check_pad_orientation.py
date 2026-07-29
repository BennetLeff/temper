#!/usr/bin/env python3
"""Pad-orientation gate: catch footprint rotations that never reached the pads.

Motivation (docs/evidence/2026-07-29-intra-component-shorts-root-cause.md).
In a ``.kicad_pcb`` file, a pad's ``(at x y angle)`` angle is the pad's
**absolute** world orientation. KiCad's parser does *not* add the parent
footprint's ``(at x y angle)`` to it -- that additive convention holds only
inside ``.kicad_mod`` library files. Consequence: rotating a footprint by
writing its ``at`` angle rotates every pad's *position* (KiCad rotates the
``at`` offsets at load time) but leaves every pad *body* pointing the way it
did before, unless each pad's own angle is rewritten too.

That omission is invisible on coarse parts and catastrophic on fine-pitch
ones. An SSOP-20 (0.635 mm pitch, 1.2 x 0.4 mm pads) rotated 270 degrees ends
up with 1.2 mm-long pad bodies lying along the 0.635 mm pitch axis: every
adjacent pad pair overlaps by 0.565 mm of solid copper. Measured on
``pcb/temper.kicad_pcb`` (kicad-cli 10.0.4): 55 of its 60 intra-component
``shorting_items``, 76 of its ``solder_mask_bridge`` violations, and 93 of its
``lib_footprint_mismatch`` violations all come from this single omission.
Copper shorts on a mains-connected board are fatal defects (docs/STRATEGY.md).

WHAT THIS CHECKS
----------------
Two independent, purely geometric checks over the board's own bytes -- no
library lookup, no KiCad invocation:

  1. PAD-BODY ROTATION REACHED THE PADS. For every footprint whose board
     rotation is not a multiple of 180 degrees (90/270 are the rotations that
     actually change a rectangular pad's footprint on the board), at least one
     of its pads must carry a non-zero absolute ``at`` angle. A rotated
     footprint whose pads are *all* at absolute angle 0 is the exact signature
     of the serializer bug above. Footprints at 0/180 are exempt: a 180-degree
     rotation maps every axis-aligned pad shape onto itself, so an omitted
     angle there is unobservable in copper.

     A footprint whose *library* pads are genuinely all at intrinsic
     ``-fp_angle`` (so that absolute 0 is correct) is legal KiCad and does
     exist in the wild; it is rare enough that the intended remedy is an
     explicit entry in ``ALLOWLIST`` with a justification, not a weakened
     check.

  2. NO INTRA-FOOTPRINT COPPER OVERLAP. For every pair of pads on the same
     footprint that (a) share at least one copper layer and (b) carry
     *different* net names, the pads' world-frame copper must not overlap or
     touch. This is the defect the rotation bug produces, checked directly,
     and it also catches the second, independent cause: hand-built library
     footprints whose pad dimensions exceed their own pitch. Both are
     fabrication blockers.

     Pads are modeled by their exact rotated bounding box (rect/roundrect) or
     circumscribing box (circle/oval). For non-overlap this is CONSERVATIVE in
     the safe direction only for axis-aligned pairs; for arbitrary rotations
     it is a separating-axis test over the two oriented rectangles, which is
     exact for ``rect`` and an over-estimate (never an under-estimate) of the
     copper extent for the rounded shapes. A gate that over-estimates copper
     can raise a false alarm but can never miss a real short.

FAIL-CLOSED CONTRACT (docs/METHODOLOGY.md Sec 4/5)
--------------------------------------------------
Never exits 0 unless it positively confirms it measured real, non-empty data.
Exits non-zero for every one of:
  - the board file is missing or fails to parse
  - the board declares zero footprints
  - zero pads exist across all footprints
  - zero pad PAIRS were geometrically compared (check 2 evaluated nothing)
  - any violation of check 1 or check 2

Usage:
    python3 scripts/check_pad_orientation.py [BOARD ...]

With no arguments, checks ``pcb/temper.kicad_pcb``.
"""

from __future__ import annotations

import argparse
import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path

# Footprints whose pads are legitimately at absolute angle 0 despite a
# 90/270-degree board rotation -- i.e. the library defines their pads with an
# intrinsic rotation that exactly cancels the placement. Keyed by library id.
# Each entry needs a justification; this is an escape hatch for real KiCad
# geometry, not for silencing the serializer bug.
ALLOWLIST: dict[str, str] = {}

_ROT_TOLERANT_SHAPES = frozenset({"circle"})


class BoardParseError(Exception):
    """The board file could not be read as an s-expression board."""


# --------------------------------------------------------------------------
# Minimal s-expression reader. Deliberately not kiutils: this gate must be
# able to see exactly what bytes are on disk, including the *absence* of an
# optional angle token, without a library's defaulting sitting in between.
# --------------------------------------------------------------------------

_TOKEN_RE = re.compile(r'\(|\)|"(?:[^"\\]|\\.)*"|[^\s()]+')


def parse_sexpr(text: str) -> list:
    """Parse an s-expression document into nested lists of str."""
    stack: list[list] = []
    cur: list = []
    for tok in _TOKEN_RE.findall(text):
        if tok == "(":
            stack.append(cur)
            cur = []
        elif tok == ")":
            if not stack:
                raise BoardParseError("unbalanced ')' in board file")
            parent = stack.pop()
            parent.append(cur)
            cur = parent
        else:
            cur.append(tok[1:-1] if tok.startswith('"') else tok)
    if stack:
        raise BoardParseError("unbalanced '(' in board file")
    return cur


def _children(node: list, key: str) -> list[list]:
    return [c for c in node if isinstance(c, list) and c and c[0] == key]


def _child(node: list, key: str) -> list | None:
    found = _children(node, key)
    return found[0] if found else None


@dataclass(frozen=True)
class Pad:
    number: str
    shape: str
    net: str | None
    layers: tuple[str, ...]
    # World frame
    cx: float
    cy: float
    width: float
    height: float
    angle_deg: float  # absolute, as written in the file


@dataclass(frozen=True)
class Footprint:
    lib_id: str
    ref: str
    rotation_deg: float
    pads: tuple[Pad, ...]


def _rotate(x: float, y: float, deg: float) -> tuple[float, float]:
    """KiCad's footprint-child rotation (y-down board frame)."""
    a = math.radians(deg)
    return (x * math.cos(a) + y * math.sin(a), -x * math.sin(a) + y * math.cos(a))


def load_footprints(board_path: Path) -> list[Footprint]:
    """Read every footprint and its world-frame pads out of *board_path*."""
    try:
        text = board_path.read_text(errors="replace")
    except OSError as exc:
        raise BoardParseError(f"cannot read {board_path}: {exc}") from exc

    doc = parse_sexpr(text)
    if not doc or not isinstance(doc[0], list):
        raise BoardParseError(f"{board_path} is not an s-expression document")
    board = doc[0]
    if not board or board[0] not in ("kicad_pcb",):
        raise BoardParseError(f"{board_path} is not a kicad_pcb document")

    footprints: list[Footprint] = []
    for node in _children(board, "footprint") + _children(board, "module"):
        at = _child(node, "at")
        if at is None:
            raise BoardParseError(f"footprint {node[1] if len(node) > 1 else '?'} has no (at ...)")
        fx, fy = float(at[1]), float(at[2])
        frot = float(at[3]) % 360.0 if len(at) > 3 else 0.0

        ref = ""
        for prop in _children(node, "property"):
            if len(prop) > 2 and prop[1] == "Reference":
                ref = prop[2]
        if not ref:
            for txt in _children(node, "fp_text"):
                if len(txt) > 2 and txt[1] == "reference":
                    ref = txt[2]

        pads: list[Pad] = []
        for pd in _children(node, "pad"):
            pat = _child(pd, "at")
            psz = _child(pd, "size")
            if pat is None or psz is None:
                continue
            lx, ly = float(pat[1]), float(pat[2])
            pang = float(pat[3]) % 360.0 if len(pat) > 3 else 0.0
            rx, ry = _rotate(lx, ly, frot)
            net = _child(pd, "net")
            layers = _child(pd, "layers")
            pads.append(
                Pad(
                    number=pd[1] if len(pd) > 1 else "",
                    shape=pd[3] if len(pd) > 3 else "rect",
                    net=(net[2] if net is not None and len(net) > 2 else None),
                    layers=tuple(layers[1:]) if layers else (),
                    cx=fx + rx,
                    cy=fy + ry,
                    width=float(psz[1]),
                    height=float(psz[2]),
                    angle_deg=pang,
                )
            )
        footprints.append(
            Footprint(
                lib_id=node[1] if len(node) > 1 else "?",
                ref=ref or "?",
                rotation_deg=frot,
                pads=tuple(pads),
            )
        )
    return footprints


def _layers_intersect(a: Pad, b: Pad) -> bool:
    """True when two pads can share copper on at least one layer."""

    def expand(layers: tuple[str, ...]) -> set[str]:
        out: set[str] = set()
        for ly in layers:
            if ly in ("*.Cu", "*"):
                out |= {"F.Cu", "In1.Cu", "In2.Cu", "B.Cu"}
            elif ly.endswith(".Cu"):
                out.add(ly)
        return out

    la, lb = expand(a.layers), expand(b.layers)
    if not la or not lb:
        # A pad with no declared copper layer cannot be proven separate;
        # treat it as sharing (fail-closed) rather than silently skipping.
        return True
    return bool(la & lb)


def _corners(p: Pad) -> list[tuple[float, float]]:
    hw, hh = p.width / 2.0, p.height / 2.0
    a = math.radians(p.angle_deg)
    cos_a, sin_a = math.cos(a), math.sin(a)
    return [
        (p.cx + dx * cos_a - dy * sin_a, p.cy + dx * sin_a + dy * cos_a)
        for dx, dy in ((-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh))
    ]


def pads_overlap(a: Pad, b: Pad, tol: float = 1e-9) -> bool:
    """Separating-axis test over the two pads' oriented bounding boxes.

    Touching counts as overlapping: KiCad's connectivity engine merges nets
    across coincident copper edges, and a zero-gap pad pair is a solder
    bridge waiting to happen either way.
    """
    if a.shape in _ROT_TOLERANT_SHAPES and b.shape in _ROT_TOLERANT_SHAPES:
        # Two circles: exact, and independent of any rotation.
        return math.hypot(a.cx - b.cx, a.cy - b.cy) <= (a.width + b.width) / 2.0 + tol

    ca, cb = _corners(a), _corners(b)
    for poly in (ca, cb):
        for i in range(len(poly)):
            x1, y1 = poly[i]
            x2, y2 = poly[(i + 1) % len(poly)]
            # Outward normal of this edge.
            nx, ny = -(y2 - y1), (x2 - x1)
            norm = math.hypot(nx, ny)
            if norm == 0.0:
                continue
            nx, ny = nx / norm, ny / norm
            pa = [nx * x + ny * y for x, y in ca]
            pb = [nx * x + ny * y for x, y in cb]
            # Separation requires a strictly positive gap: coincident edges
            # are a copper connection to KiCad's connectivity engine, not a
            # clearance of zero.
            if min(pa) > max(pb) + tol or min(pb) > max(pa) + tol:
                return False  # separating axis found
    return True


@dataclass
class Report:
    unrotated_pads: list[str]
    overlaps: list[str]
    footprints_checked: int
    pads_checked: int
    pairs_compared: int


def check_board(board_path: Path) -> Report:
    footprints = load_footprints(board_path)
    unrotated: list[str] = []
    overlaps: list[str] = []
    pads_checked = 0
    pairs = 0

    for fp in footprints:
        pads_checked += len(fp.pads)

        # --- Check 1: did the footprint rotation reach the pad bodies? ---
        quarter_turn = fp.rotation_deg % 180.0 != 0.0
        if quarter_turn and fp.pads and fp.lib_id not in ALLOWLIST:
            # `any(...)` rather than `all(... == 0)`: over an empty pad list
            # `any` is False, so the fail-closed reading ("nothing carries a
            # rotation") is what an empty footprint would get -- and the
            # `fp.pads` guard above means we never actually reach that case.
            # See docs/METHODOLOGY.md Sec 5 / scripts/check_vacuous_gates.py.
            if not any(p.angle_deg % 360.0 != 0.0 for p in fp.pads):
                unrotated.append(
                    f"{fp.ref} ({fp.lib_id}): footprint rotated {fp.rotation_deg:g} deg "
                    f"but all {len(fp.pads)} pads carry absolute angle 0 -- the pad "
                    f"bodies were never rotated with the footprint"
                )

        # --- Check 2: intra-footprint copper overlap on different nets ---
        pads = list(fp.pads)
        for i in range(len(pads)):
            for j in range(i + 1, len(pads)):
                a, b = pads[i], pads[j]
                if a.net is None or b.net is None or a.net == b.net:
                    continue
                if not _layers_intersect(a, b):
                    continue
                pairs += 1
                if pads_overlap(a, b):
                    overlaps.append(
                        f"{fp.ref} ({fp.lib_id}): pad {a.number} [{a.net}] and "
                        f"pad {b.number} [{b.net}] overlap in copper "
                        f"(centres {math.hypot(a.cx - b.cx, a.cy - b.cy):.3f} mm apart, "
                        f"sizes {a.width}x{a.height} @ {a.angle_deg:g} deg and "
                        f"{b.width}x{b.height} @ {b.angle_deg:g} deg)"
                    )

    return Report(
        unrotated_pads=unrotated,
        overlaps=overlaps,
        footprints_checked=len(footprints),
        pads_checked=pads_checked,
        pairs_compared=pairs,
    )


def _report_board(board_path: Path) -> int:
    print(f"=== {board_path} ===")
    if not board_path.exists():
        print(f"FAIL: board not found: {board_path}")
        return 1
    try:
        rep = check_board(board_path)
    except BoardParseError as exc:
        print(f"FAIL: {exc}")
        return 1

    # Fail-closed: refuse to report success on data we never measured.
    if rep.footprints_checked == 0:
        print("FAIL: board declares zero footprints -- nothing was checked")
        return 1
    if rep.pads_checked == 0:
        print("FAIL: zero pads across all footprints -- nothing was checked")
        return 1
    if rep.pairs_compared == 0:
        print("FAIL: zero pad pairs compared -- the overlap check evaluated nothing")
        return 1

    print(
        f"checked {rep.footprints_checked} footprints, {rep.pads_checked} pads, "
        f"{rep.pairs_compared} different-net pad pairs"
    )

    failed = False
    if rep.unrotated_pads:
        failed = True
        print(f"\nFAIL: {len(rep.unrotated_pads)} rotated footprint(s) with unrotated pad bodies:")
        for line in rep.unrotated_pads:
            print(f"  - {line}")
        print(
            "\n  A .kicad_pcb pad's (at x y angle) angle is ABSOLUTE, not relative to\n"
            "  its footprint. Whatever wrote this board rotated the footprints without\n"
            "  rewriting the pad angles. Regenerate the board through a writer that\n"
            "  calls temper_placer.io._write_board._reorient_pads (fixed 2026-07-29)."
        )
    if rep.overlaps:
        failed = True
        print(f"\nFAIL: {len(rep.overlaps)} intra-footprint copper overlap(s) on different nets:")
        for line in rep.overlaps:
            print(f"  - {line}")
        print(
            "\n  Each of these is a copper short inside a single component -- a fatal\n"
            "  defect on a mains-connected board (docs/STRATEGY.md). If the pads also\n"
            "  overlap in the footprint's OWN local frame, the library .kicad_mod is\n"
            "  wrong and a human must fix it; see\n"
            "  docs/evidence/2026-07-29-intra-component-shorts-root-cause.md."
        )

    if not failed:
        print("PASS: no unrotated pad bodies, no intra-footprint copper overlaps")
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("boards", nargs="*", type=Path, help="board files to check")
    args = parser.parse_args(argv)

    boards = args.boards
    if not boards:
        repo_root = Path(__file__).resolve().parent.parent
        boards = [repo_root / "pcb" / "temper.kicad_pcb"]

    if not boards:
        print("FAIL: no boards to check")
        return 1

    exit_code = 0
    for board in boards:
        exit_code |= _report_board(board)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
