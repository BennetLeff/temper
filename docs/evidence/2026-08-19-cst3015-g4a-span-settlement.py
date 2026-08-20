#!/usr/bin/env python3
"""Read-only: settle the CST3015 (T1/T2) and G4A-E (K1) intra-package HV<->SELV
copper span, and show exactly which composition of rotations produces the two
figures that were in dispute (9.100 vs 7.800 mm; 8.000 vs 5.425 mm).

THE QUESTION. Two analyses disagreed about the same CST3015 land pattern:

    analysis/t1-sense-node-relocation   (5e53ceaa0)   9.100 mm
    analysis/per-pairing-placer-solve   (30edd0a93)   7.800 mm  ("corrected")

and, on the G4A-E relay, 8.000 mm vs 5.425 mm. A real footprint has one
geometry, so exactly one of each pair is right.

THE ANSWER. 9.100 mm and 8.000 mm. Proof, in three independent parts:

1. THE INVARIANT. Every pad of one footprint is carried by the SAME rigid
   motion, so the copper-to-copper distance between two pads OF THE SAME
   FOOTPRINT is a rigid-body invariant: it cannot depend on where the part is
   placed or how it is rotated. Section 1 below demonstrates that directly --
   the correct transform returns the identical number at 0/90/180/270 AND at a
   deliberately non-square 37 degrees, while the disputed transform does not.
   A quantity that changes under a rigid rotation is not a distance; failing
   this test is by itself disqualifying.

2. KICAD'S SEMANTICS, RESOLVED (not bounded). In a `.kicad_pcb` file a pad's
   `(at x y ANGLE)` carries a FOOTPRINT-LOCAL, UNROTATED position and an
   ABSOLUTE world orientation -- the parent footprint's angle is added to the
   position at load time but NEVER to the angle. This is stated in-tree by
   `scripts/check_pad_orientation.py` (lines 5-11), is the convention that
   gate exists to police, and is what `scripts/measure_cross_domain_creepage.py`
   implements. It is confirmed here by the board's own bytes: the library
   footprints `pcb/libs/temper.pretty/CST3015.kicad_mod` and
   `Relay_SPST_Omron-G4A-E.kicad_mod` carry NO pad angle at all (every pad is
   at 0), and the placed instances read:

       T2  footprint angle   0   ->  every pad's absolute angle    0
       T1  footprint angle  90   ->  every pad's absolute angle   90
       K1  footprint angle   0   ->  every pad's absolute angle  180

   T1's pads carry exactly the footprint's own 90 degrees: the rotation DID
   reach the pads, i.e. T1 is a faithful rigid placement of the library part.
   K1's 180 is a symmetry of every one of its pad shapes (axis-aligned rect /
   circle), so it moves no copper. Both instances therefore present exactly the
   library geometry -- 9.100 mm and 8.000 mm.

3. WHERE 7.800 / 5.425 COME FROM. `temper-design-bundle`'s parser
   (`parse_engine.rs:1722`) stores

       Pin.pad_rotation_deg = pad_absolute_angle - footprint_angle

   i.e. FOOTPRINT-RELATIVE, to pair with `Pin.position`, which is likewise
   footprint-local. The world body angle is therefore
   `component_rotation + pad_rotation_deg` -- which is precisely what
   `router_v6/obstacle_map.py:313`, `router_v6/kicad_connectivity.py:277` and
   `placer/cp_sat/tank_creepage.py:465` all use.

   `analysis/per-pairing-placer-solve`'s helpers
   (`2026-08-19-per-pairing-residual-attribution.py:42-50`'s `wtup`, and
   `isolation_barrier.py`'s `_worst_axis_radius` candidate
   `pad.axis_radius(axis, pad_rot_rad)`) rotate each pad's POSITION by the
   component rotation but hand `pad_rotation_deg` ALONE to the pad BODY. That
   is a shear, not a rotation: the pads translate around the footprint origin
   while their copper stays pointing the old way. Section 1 shows it yields
   9.100/8.000 at rotation quadrants 0 and 2 and 7.800/5.425 at 1 and 3 -- the
   two disputed figures, exactly.

   The reasoning that produced it is a TRUE statement applied to the wrong
   variable: "a pad angle in a .kicad_pcb is already absolute, so do not
   compose it" is correct about the FILE, but `Pin.pad_rotation_deg` no longer
   holds the file's value -- the parser already subtracted the footprint angle.
   Dropping the component rotation there does not decline to compose; it
   discards a rotation the pad positions have already received.

   Consequently the composition is NOT ambiguous and does not need bounding by
   a max over candidates. `_worst_axis_radius`'s max is also not conservative
   in the way it claims for THIS purpose: a bound that is not rotation-invariant
   cannot be a bound on a rigid-body invariant.

4. HANDEDNESS IS IMMATERIAL HERE. Section 2 evaluates every pair under BOTH
   R(+theta) and R(-theta) (KiCad rotates footprint children clockwise in the
   Y-down frame, i.e. R(-theta) -- `core_graph_geometry.rs:188-200`). Every
   intra-package figure is identical under both, so the convention question
   cannot move any number in this dispute.

Distances come from `core.pad_geometry.pad_pair_distance`, the exact
Minkowski-sum kernel the REQ-SAFE-01 validator and
`scripts/check_isolation_keepout.py` both use (no polygonisation error; its own
docstring records that it reports K1's pair as exactly 8.000 mm where a polygon
approximation manufactures 7.9989 mm).

NOTHING HERE WRITES. `pcb/temper.kicad_pcb` is opened read-only.

Usage::

    python docs/evidence/2026-08-19-cst3015-g4a-span-settlement.py pcb/temper.kicad_pcb
"""

from __future__ import annotations

import math
import re
import sys
from pathlib import Path

from temper_placer.core.pad_geometry import pad_pair_distance
from temper_placer.core.pin_geometry import pin_world_position_at
from temper_placer.io.kicad_parser import parse_kicad_pcb

# HV-side pads vs SELV-side pads, per each footprint's own declared pin roles.
GROUPS: dict[str, tuple[list[str], list[str]]] = {
    "T1": (["1", "2"], ["3", "4"]),
    "T2": (["1", "2"], ["3", "4"]),
    "K1": (["13", "14"], ["A1", "A2"]),
}


def sexpr_blocks(text: str, tag: str) -> list[str]:
    """Every balanced-paren block in *text* opening with *tag*."""
    out: list[str] = []
    idx = 0
    while True:
        start = text.find(tag, idx)
        if start < 0:
            return out
        depth = 0
        j = start
        while j < len(text):
            if text[j] == "(":
                depth += 1
            elif text[j] == ")":
                depth -= 1
                if depth == 0:
                    out.append(text[start : j + 1])
                    break
            j += 1
        idx = j + 1


def parse_footprint(block: str) -> dict:
    ref = re.search(r'\(property "Reference" "([^"]+)"', block)
    at = re.search(r"\(at ([-\d.]+) ([-\d.]+)(?: ([-\d.]+))?\)", block)
    pads = []
    for pb in sexpr_blocks(block, "(pad "):
        m = re.match(
            r'\(pad "([^"]*)" (\S+) (\S+) \(at ([-\d.]+) ([-\d.]+)(?: ([-\d.]+))?\) '
            r"\(size ([\d.]+) ([\d.]+)\)",
            pb,
        )
        if not m:
            continue
        num, _ptype, shape, px, py, pang, w, h = m.groups()
        net = re.search(r'\(net \d+ "([^"]*)"\)', pb)
        layers = re.search(r"\(layers ([^)]*)\)", pb)
        pads.append(
            {
                "num": num,
                "shape": shape,
                "lx": float(px),
                "ly": float(py),
                "abs_ang": float(pang or 0.0),
                "w": float(w),
                "h": float(h),
                "net": net.group(1) if net else None,
                "layers": layers.group(1) if layers else "",
            }
        )
    return {
        "ref": ref.group(1) if ref else "?",
        "fx": float(at.group(1)),
        "fy": float(at.group(2)),
        "frot": float(at.group(3) or 0.0),
        "pads": pads,
    }


def _shape(pad: dict) -> str:
    return "thru_hole" if ("*.Cu" in pad["layers"] and pad["shape"] == "circle") else pad["shape"]


def rigid(fp: dict, pad: dict, extra_deg: float, sign: float) -> tuple:
    """KiCad `.kicad_pcb` semantics: local position rotated by the footprint
    angle, body at its ABSOLUTE angle. `extra_deg` rigidly rotates the whole
    footprint further -- position AND absolute body angle move together.

    `sign` selects the rotation handedness (+1 = R(+theta), -1 = R(-theta));
    both are reported, because the pad body angle must be negated relative to
    Shapely's CCW `rotate` for the transform to be rigid in KiCad's Y-down frame.
    """
    th = sign * math.radians(fp["frot"] + extra_deg)
    c, s = math.cos(th), math.sin(th)
    wx = fp["fx"] + pad["lx"] * c - pad["ly"] * s
    wy = fp["fy"] + pad["lx"] * s + pad["ly"] * c
    return (pad["w"], pad["h"], _shape(pad), wx, wy,
            sign * math.radians(pad["abs_ang"] + extra_deg), 0.25)


def sheared(fp: dict, pad: dict, extra_deg: float, sign: float) -> tuple:
    """The disputed transform: position rotated, BODY LEFT BEHIND."""
    th = sign * math.radians(fp["frot"] + extra_deg)
    c, s = math.cos(th), math.sin(th)
    wx = fp["fx"] + pad["lx"] * c - pad["ly"] * s
    wy = fp["fy"] + pad["lx"] * s + pad["ly"] * c
    return (pad["w"], pad["h"], _shape(pad), wx, wy, 0.0, 0.25)


def min_span(fp: dict, fn, extra_deg: float, sign: float) -> tuple[float, str, str]:
    hv, selv = GROUPS[fp["ref"]]
    best: tuple[float, str, str] | None = None
    for a in fp["pads"]:
        if a["num"] not in hv:
            continue
        for b in fp["pads"]:
            if b["num"] not in selv:
                continue
            d = pad_pair_distance(fn(fp, a, extra_deg, sign), fn(fp, b, extra_deg, sign))
            if best is None or d < best[0]:
                best = (d, a["num"], b["num"])
    assert best is not None, f"no HV x SELV pair on {fp['ref']}"
    return best


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    board = Path(argv[1])
    if not board.is_file():
        print(f"ERROR: no such board: {board}", file=sys.stderr)
        return 2

    src = board.read_text()
    fps: dict[str, dict] = {}
    for block in sexpr_blocks(src, "(footprint "):
        f = parse_footprint(block)
        if f["ref"] in GROUPS:
            fps[f["ref"]] = f
    missing = set(GROUPS) - set(fps)
    if missing:
        print(f"ERROR: footprints not found on the board: {sorted(missing)}", file=sys.stderr)
        return 2

    # ---------------------------------------------------------------- 1 ----
    print("=" * 92)
    print("1. FROM THE BOARD'S OWN BYTES, UNDER KICAD'S .kicad_pcb SEMANTICS")
    print("=" * 92)
    for ref in ("T2", "T1", "K1"):
        fp = fps[ref]
        print(f"\n{ref}  (footprint at {fp['fx']} {fp['fy']} rot={fp['frot']:g})")
        for p in fp["pads"]:
            if p["num"]:
                print(f"    pad {p['num']:>3}  {p['shape']:<9} local=({p['lx']:>7g},{p['ly']:>6g})  "
                      f"abs_angle={p['abs_ang']:>5g}  size={p['w']:g}x{p['h']:g}  net={p['net']}")
        for sign, label in ((-1.0, "R(-theta), KiCad"), (1.0, "R(+theta)")):
            cells = []
            for extra in (0.0, 90.0, 180.0, 270.0, 37.0):
                d, _, _ = min_span(fp, rigid, extra, sign)
                cells.append(f"{d:.4f}")
            ok = len(set(cells)) == 1
            print(f"    RIGID   {label:<18} at +0/90/180/270/37 deg: "
                  f"{' '.join(cells)}   {'INVARIANT (as a distance must be)' if ok else 'NOT INVARIANT'}")
        cells = []
        for extra in (0.0, 90.0, 180.0, 270.0):
            d, _, _ = min_span(fp, sheared, extra, -1.0)
            cells.append(f"{d:.4f}")
        print(f"    SHEARED (position rotated, body left behind) at +0/90/180/270: "
              f"{' '.join(cells)}   "
              f"{'NOT INVARIANT -- not a distance' if len(set(cells)) > 1 else 'invariant'}")
        print("    all HV x SELV pairs as placed:")
        hv, selv = GROUPS[ref]
        for a in fp["pads"]:
            if a["num"] not in hv:
                continue
            for b in fp["pads"]:
                if b["num"] not in selv:
                    continue
                d = pad_pair_distance(rigid(fp, a, 0.0, -1.0), rigid(fp, b, 0.0, -1.0))
                print(f"        pad {a['num']:>3} ({a['net']}) <-> pad {b['num']:>3} ({b['net']}): {d:.4f} mm")

    # ---------------------------------------------------------------- 2 ----
    print()
    print("=" * 92)
    print("2. THROUGH THE PLACER'S OWN PARSER: WHICH COMPOSITION REPRODUCES WHICH FIGURE")
    print("=" * 92)
    parsed = parse_kicad_pcb(board)
    comps = {c.ref: c for c in parsed.netlist.components if c.ref in GROUPS}

    print("\n`Pin.pad_rotation_deg` as parsed (parse_engine.rs:1722 stores it")
    print("FOOTPRINT-RELATIVE: pad_absolute_angle - footprint_angle):")
    for ref in ("T2", "T1", "K1"):
        c = comps[ref]
        rots = {p.number: getattr(p, "pad_rotation_deg", 0.0) for p in c.pins if p.number}
        print(f"    {ref}: initial_rotation_quadrant={c.initial_rotation_quadrant}  {rots}")

    def tup(pin, comp, rot_q: int, compose: bool) -> tuple:
        x, y = pin_world_position_at(pin, comp, None, rot_q)
        pad_rot = math.radians(getattr(pin, "pad_rotation_deg", 0.0) or 0.0)
        body = (rot_q * math.pi / 2.0 + pad_rot) if compose else pad_rot
        return (pin.width, pin.height, pin.shape or "rect", x, y, body,
                getattr(pin, "roundrect_ratio", None) or 0.25)

    def span(comp, rot_q: int, compose: bool) -> float:
        hv, selv = GROUPS[comp.ref]
        return min(
            pad_pair_distance(tup(a, comp, rot_q, compose), tup(b, comp, rot_q, compose))
            for a in comp.pins if a.number in hv
            for b in comp.pins if b.number in selv
        )

    hdr = (f"\n{'ref':5} {'rot_q':>6} | {'comp_rot + pad_rot  (canonical)':>32} | "
           f"{'pad_rot alone  (disputed)':>28}")
    print(hdr)
    print("-" * (len(hdr) - 1))
    for ref in ("T2", "T1", "K1"):
        c = comps[ref]
        base = span(c, 0, True)
        for q in range(4):
            good, bad = span(c, q, True), span(c, q, False)
            note = "" if abs(good - base) < 1e-9 else "  <-- NOT INVARIANT"
            print(f"{ref:5} {q:6} | {good:32.4f} | {bad:28.4f}{note}")

    print("\nSETTLED: CST3015 (T1, T2) = 9.1000 mm; G4A-E (K1) = 8.0000 mm.")
    print("The 7.800 / 5.425 figures are the SHEARED transform at rotation quadrants 1 and 3.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
