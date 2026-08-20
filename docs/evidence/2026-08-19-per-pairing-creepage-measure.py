#!/usr/bin/env python3
"""Read-only: what the per-pairing creepage requirement changes, measured.

Prints, in one run:

1. **The per-pairing table as implemented** -- every declared pairing, its
   working voltage, insulation class, table row, requirement (or
   ``NOT DETERMINABLE``) and enforceable floor, straight out of
   ``elec/insulation_manifest.yaml`` through the Rust rule.
2. **The five blocking isolation-bridging components**, each graded against
   its OWN binding pairing rather than against a single scalar. The gap is
   the exact, rotation-invariant, copper-to-copper package maximum -- the
   same ``pad_pair_distance`` kernel ``scripts/check_isolation_keepout.py``
   and the REQ-SAFE-01 validator use -- so it is a placement-independent
   package constant (method and provenance:
   ``docs/evidence/2026-08-19-isolator-package-maxima.py``, reproduced here
   rather than imported because that file lives on an unmerged branch).
3. **The board-wide pad-pair census**, before and after: every cross-domain
   HV<->SELV pad pair whose exact copper-to-copper gap is below its
   requirement, counted at the old 12.6 mm scalar and at the new per-pairing
   figures, broken out by pairing and by verdict (PASS / FAIL /
   INDETERMINATE).
4. **The HV-halo effect**: how much board area the HV pads' required-creepage
   dilation occupies, and how many SELV pads sit inside it, before and after.

This is a MEASUREMENT TOOL, NOT A GATE. It never exits non-zero because
violations were found -- only because it could not run a trustworthy
measurement at all. ``scripts/check_insulation_pairings.py`` is the gate.

Nothing here writes to ``pcb/temper.kicad_pcb`` or to any manifest.

Usage::

    python docs/evidence/2026-08-19-per-pairing-creepage-measure.py \
        pcb/temper.kicad_pcb elec/domain_manifest.yaml
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

from temper_placer.core import insulation_coordination as ic
from temper_placer.core.isolation_constants import (
    MIN_BARRIER_WIDTH_IS_DETERMINATE,
    MIN_BARRIER_WIDTH_MM,
)
from temper_placer.core.pad_geometry import pad_pair_distance
from temper_placer.core.pin_geometry import pin_world_position
from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.placer.cp_sat.isolation_barrier import load_domain_manifest_nets

# The scalar this change replaces. Written here as a literal ON PURPOSE and
# ONLY here: this script's whole job is to report the before/after delta, and
# it cannot do that once the old value no longer exists anywhere. It is never
# used as a requirement -- only as the "before" column.
OLD_SCALAR_MM = 12.6


def rule(title: str) -> None:
    print()
    print("=" * 100)
    print(title)
    print("=" * 100)


def tup(pin):  # noqa: ANN001, ANN201 - mirrors the isolator-maxima script
    """Pad tuple in LOCAL footprint coordinates.

    Correct ONLY for pairs of pads belonging to the SAME component, which is
    what section 2 measures (a package constant is rotation- and
    placement-invariant precisely because every pad moves together). Use
    :func:`world_tup` for any cross-component pair.
    """
    return (
        pin.width,
        pin.height,
        pin.shape or "rect",
        pin.position[0],
        pin.position[1],
        math.radians(getattr(pin, "pad_rotation_deg", 0.0) or 0.0),
        getattr(pin, "roundrect_ratio", None) or 0.25,
    )


def world_tup(pin, comp):  # noqa: ANN001, ANN201
    """Pad tuple in WORLD (board) coordinates.

    `pin.position` is a local footprint offset. Comparing two components'
    pads with local offsets would place every footprint at the origin and
    report almost every pair as violating -- the exact error this helper
    exists to make impossible to write by accident. Position uses
    `pin_world_position` (the canonical rotation- and side-aware call); the
    pad's own `(at x y angle)` rotation is ALREADY absolute in a .kicad_pcb
    file and is not composed with the footprint angle -- the convention
    `scripts/check_pad_orientation.py` exists to police and
    `scripts/measure_cross_domain_creepage.py` documents.
    """
    x, y = pin_world_position(pin, comp)
    return (
        pin.width,
        pin.height,
        pin.shape or "rect",
        x,
        y,
        math.radians(getattr(pin, "pad_rotation_deg", 0.0) or 0.0),
        getattr(pin, "roundrect_ratio", None) or 0.25,
    )


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__)
        return 2
    board_path = Path(argv[1])
    manifest_path = Path(argv[2])
    if not board_path.is_file() or not manifest_path.is_file():
        print(f"ERROR: missing input ({board_path}, {manifest_path})", file=sys.stderr)
        return 2

    resolution = ic.resolve_declaration()

    # ---------------------------------------------------------------- 1 ----
    rule("1. THE PER-PAIRING TABLE AS IMPLEMENTED")
    print(
        f"declaration : {ic.DECLARATION_PATH}\n"
        f"pollution   : PD{resolution.pollution_degree()}, material group "
        f"{resolution.material_group()}\n"
        f"verified    : {resolution.verified_on()} at "
        f"{resolution.measured_at_commit()[:9]}\n"
    )
    hdr = (
        f"{'pairing':24} {'class':11} {'V rms':>8} {'f (Hz)':>8} {'row':>12} "
        f"{'table':>9} {'required':>12} {'floor mm':>9}"
    )
    print(hdr)
    print("-" * len(hdr))
    for p in resolution.pairings():
        req = (
            f"{p.requirement_mm():.2f} mm"
            if p.is_determinable()
            else "NOT DETERMINABLE"
        )
        print(
            f"{p.key():24} {p.insulation():11} {p.working_voltage_vrms():8.1f} "
            f"{p.frequency_hz():8.0f} {p.voltage_range():>12} {p.table():>9} "
            f"{req:>12} {p.enforceable_floor_mm():9.2f}"
        )
    print()
    print(
        f"barrier floor (worst crossing) = {resolution.barrier_floor_mm():.1f} mm, "
        f"set by {resolution.barrier_governing_pairing().key()}"
    )
    print(f"barrier requirement determinable = {resolution.barrier_is_determinable()}")
    print(
        f"MIN_BARRIER_WIDTH_MM = {MIN_BARRIER_WIDTH_MM} "
        f"(was {OLD_SCALAR_MM}); determinate = {MIN_BARRIER_WIDTH_IS_DETERMINATE}"
    )
    print()
    print("LIMITATION:")
    for line in ic.limitation().split(". "):
        if line.strip():
            print(f"  {line.strip().rstrip('.')}.")

    # ---------------------------------------------------------------- 2 ----
    hv_nets, selv_nets = load_domain_manifest_nets(manifest_path)
    parsed = parse_kicad_pcb(board_path)

    rule("2. ISOLATION-BRIDGING COMPONENTS, GRADED AGAINST THEIR OWN PAIRING")
    print(
        "gap = exact rotation-invariant copper-to-copper package maximum: the "
        "most\nseparation the part can offer at ANY placement and ANY "
        "rotation.\n"
    )
    hdr = (
        f"{'ref':5} {'binding HV net':26} {'SELV net':26} {'pairing':22} "
        f"{'gap':>7} {'old req':>8} {'old':>6} {'new req':>16} {'new':>14}"
    )
    print(hdr)
    print("-" * len(hdr))
    rows = []
    for comp in parsed.netlist.components:
        hv = [p for p in comp.pins if p.net in hv_nets]
        selv = [p for p in comp.pins if p.net in selv_nets]
        if not hv or not selv:
            continue
        best = None
        for a in hv:
            for b in selv:
                d = pad_pair_distance(tup(a), tup(b))
                if best is None or d < best[0]:
                    best = (d, a, b)
        rows.append((comp.ref, best))
    rows.sort(key=lambda r: r[1][0])

    summary: list[tuple[str, str, str]] = []
    for ref, (gap, a, b) in rows:
        pairing = ic.requirement_for_nets(a.net, b.net)
        old_verdict = "PASS" if gap >= OLD_SCALAR_MM else "FAIL"
        new_verdict = pairing.grade(gap)
        new_req = (
            f"{pairing.requirement_mm():.1f} mm"
            if pairing.is_determinable()
            else f">={pairing.enforceable_floor_mm():.1f} (indet.)"
        )
        print(
            f"{ref:5} {a.net:26} {b.net:26} {pairing.key():22} {gap:7.3f} "
            f"{OLD_SCALAR_MM:8.1f} {old_verdict:>6} {new_req:>16} {new_verdict:>14}"
        )
        summary.append((ref, old_verdict, new_verdict))
    print()
    moved = [r for r, o, n in summary if o != n]
    print(
        f"{sum(1 for _, o, _ in summary if o == 'FAIL')} of {len(summary)} failed the "
        f"old scalar; "
        f"{sum(1 for _, _, n in summary if n == 'FAIL')} fail their own pairing; "
        f"{sum(1 for _, _, n in summary if n == 'INDETERMINATE')} are indeterminate."
    )
    print(f"verdict changed for: {', '.join(moved) if moved else '(none)'}")

    # ---------------------------------------------------------------- 3 ----
    rule("3. BOARD-WIDE CROSS-DOMAIN PAD-PAIR CENSUS, BEFORE AND AFTER")
    hv_pads = []
    selv_pads = []
    for comp in parsed.netlist.components:
        for pin in comp.pins:
            if pin.net in hv_nets:
                hv_pads.append((comp.ref, pin, world_tup(pin, comp)))
            elif pin.net in selv_nets:
                selv_pads.append((comp.ref, pin, world_tup(pin, comp)))
    print(f"HV pads: {len(hv_pads)}   SELV pads: {len(selv_pads)}   "
          f"pairs: {len(hv_pads) * len(selv_pads)}")
    if not hv_pads or not selv_pads:
        print("ERROR: zero pads on one side; refusing to report a vacuous census",
              file=sys.stderr)
        return 3

    old_bad = 0
    new_fail = 0
    new_indet = 0
    per_pairing: dict[str, list[int]] = {}
    for _, pa, ta in hv_pads:
        for _, pb, tb in selv_pads:
            gap = pad_pair_distance(ta, tb)
            pairing = ic.requirement_for_nets(pa.net, pb.net)
            key = pairing.key()
            bucket = per_pairing.setdefault(key, [0, 0, 0, 0])
            bucket[0] += 1
            if gap < OLD_SCALAR_MM:
                old_bad += 1
                bucket[1] += 1
            verdict = pairing.grade(gap)
            if verdict == "FAIL":
                new_fail += 1
                bucket[2] += 1
            elif verdict == "INDETERMINATE":
                new_indet += 1
                bucket[3] += 1

    hdr = (f"{'pairing':24} {'floor':>7} {'det':>5} {'pairs':>8} "
           f"{'old<12.6':>9} {'new FAIL':>9} {'new INDET':>10}")
    print()
    print(hdr)
    print("-" * len(hdr))
    for key in sorted(per_pairing):
        total, old_n, fail_n, indet_n = per_pairing[key]
        a, b = key.split("<->")
        pr = resolution.pairing(a, b)
        print(
            f"{key:24} {pr.enforceable_floor_mm():7.2f} "
            f"{str(pr.is_determinable()):>5} {total:8d} {old_n:9d} "
            f"{fail_n:9d} {indet_n:10d}"
        )
    print("-" * len(hdr))
    print(
        f"{'TOTAL':24} {'':7} {'':5} {len(hv_pads) * len(selv_pads):8d} "
        f"{old_bad:9d} {new_fail:9d} {new_indet:10d}"
    )
    print()
    print(
        f"BEFORE: {old_bad} pad pairs below the 12.6 mm scalar.\n"
        f"AFTER : {new_fail} below their own pairing's floor "
        f"(delta {new_fail - old_bad:+d}), plus {new_indet} that clear the "
        f"floor\n        but whose requirement is NOT DETERMINABLE -- "
        f"{new_fail + new_indet} pairs in total cannot be\n        certified, "
        f"against {old_bad} before."
    )

    # ---------------------------------------------------------------- 4 ----
    rule("4. HV HALO: BOARD AREA AND SELV PADS INSIDE IT, BEFORE AND AFTER")
    try:
        from shapely.geometry import Point
        from shapely.ops import unary_union
    except ImportError:
        print("shapely unavailable; halo section skipped (not a measurement failure)")
        return 0

    hv_union = unary_union(
        [Point(t[3], t[4]).buffer(0.01) for _, _, t in hv_pads]
    )
    selv_points = [Point(t[3], t[4]) for _, _, t in selv_pads]
    for label, radius in (("old scalar", OLD_SCALAR_MM),
                          ("new barrier floor", MIN_BARRIER_WIDTH_MM)):
        halo = hv_union.buffer(radius)
        inside = sum(1 for pt in selv_points if halo.contains(pt))
        print(
            f"{label:18} radius {radius:5.1f} mm -> halo area "
            f"{halo.area:9.0f} mm2, SELV pads inside: {inside}/{len(selv_points)}"
        )
    print(
        "\n(Pad CENTRES against a pad-centre halo -- a coarse, comparable "
        "before/after\n index, not the exact copper-to-copper census of "
        "section 3.)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
