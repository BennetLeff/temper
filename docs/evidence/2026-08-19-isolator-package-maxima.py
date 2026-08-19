"""Read-only: the EXACT, rotation-invariant intra-footprint HV<->SELV pad gap.

Rotating a footprint rotates every pad and every pad position together, so
pairwise pad-edge distances inside one part are invariant under placement.
This number is therefore a PACKAGE CONSTANT: the most separation that part
can ever offer between its HV and SELV copper, at any position and any
rotation the placer could choose.

Uses core.pad_geometry.pad_pair_distance -- the exact Minkowski-sum
copper-to-copper distance the REQ-SAFE-01 validator and
scripts/check_isolation_keepout.py both use (no polygonisation error; its
own docstring notes it reports K1's pair as exactly 8.000mm where the
polygon approximation manufactures 7.9989mm).
"""
import math
import sys
from pathlib import Path

from temper_placer.core.isolation_constants import MIN_BARRIER_WIDTH_MM
from temper_placer.core.pad_geometry import pad_pair_distance
from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.placer.cp_sat.isolation_barrier import load_domain_manifest_nets

board_path = Path(sys.argv[1])
manifest = Path(sys.argv[2])
hv_nets, selv_nets = load_domain_manifest_nets(manifest)
pr = parse_kicad_pcb(board_path)


def tup(pin):
    return (
        pin.width,
        pin.height,
        pin.shape or "rect",
        pin.position[0],
        pin.position[1],
        math.radians(getattr(pin, "pad_rotation_deg", 0.0) or 0.0),
        getattr(pin, "roundrect_ratio", None) or 0.25,
    )


print(f"REQUIREMENT (MIN_BARRIER_WIDTH_MM, PD3 reinforced) = {MIN_BARRIER_WIDTH_MM} mm")
print("Exact copper-to-copper, rotation-invariant, per package.\n")
hdr = (f"{'ref':6} {'value':22} {'HVxSELV':>8} {'pkg_max_mm':>11} {'short_by':>9}  "
       f"binding pad pair (HV net / SELV net)")
print(hdr)
print("-" * len(hdr))

rows = []
for comp in pr.netlist.components:
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
    rows.append((comp.ref, getattr(comp, "value", ""), len(hv) * len(selv), best))

rows.sort(key=lambda r: r[3][0])
n_bad = 0
for ref, value, npairs, (d, a, b) in rows:
    short = MIN_BARRIER_WIDTH_MM - d
    bad = short > 1e-9
    n_bad += bad
    print(f"{ref:6} {str(value)[:22]:22} {npairs:8d} {d:11.4f} "
          f"{(f'{short:9.4f}' if bad else '        -')}  "
          f"pad {a.number}({a.net}) <-> pad {b.number}({b.net})")

print(f"\nisolation-bridging parts: {len(rows)}; "
      f"structurally below {MIN_BARRIER_WIDTH_MM}mm at EVERY placement: {n_bad}")
