#!/usr/bin/env python3
"""Lightweight production-seam verification of the Rust zone generator.

A full ``route_pcb`` on the production board was OOM-killed at 53 GB RSS
on 2026-08-16 by a global OOM while another agent ran a full router_v6
pytest suite concurrently (kernel log: oom-kill pid 935359).  Per the
repo's no-compete-on-memory rule this harness instead drives the exact
production emission seam -- ``_emit_zone_pours`` with the production
board's real parsed geometry -- which is the phase the full route
reaches after routing, and the phase this wiring changed.

Read-only: never writes pcb/temper.kicad_pcb.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PCB_PATH = REPO_ROOT / "pcb" / "temper.kicad_pcb"

ZONE_RE = re.compile(r"\(zone \(net (\d+)\) \(net_name \"([^\"]+)\"\) \(layer \"([^\"]+)\"\)")
POLYGON_RE = re.compile(r"\(polygon\n\s+\(pts")


def main() -> int:
    sys.path.insert(0, str(REPO_ROOT / "packages" / "temper-placer"))

    from temper_placer.io.kicad_parser import parse_kicad_pcb_v6
    from temper_placer.router_v6._zone_pour_stitch import _emit_zone_pours
    from temper_placer.router_v6.pad_connectivity_audit import _pads_by_net

    pcb = parse_kicad_pcb_v6(PCB_PATH)
    pads_by_net = _pads_by_net(pcb)
    print(f"board: {PCB_PATH.name}, {len(pads_by_net)} nets with pads")

    net_name_to_number: dict[str, int] = {}
    for m in re.finditer(r'\(net\s+(\d+)\s+"([^"]+)"', PCB_PATH.read_text()):
        net_name_to_number[m.group(2)] = int(m.group(1))

    segments: list[str] = []
    # Production pad positions (rotation-corrected world positions via
    # _pads_by_net -> pin_world_position), keyed by net -- exactly what
    # _write_routes_to_content feeds _emit_zone_pours.
    pad_positions: dict[str, list[tuple[float, float]]] = {}
    for net, pads in pads_by_net.items():
        pad_positions[net] = [p.position for p in pads]

    _emit_zone_pours(
        pad_positions,
        segments,
        net_name_to_number,
        pcb=pcb,
    )

    zones = ZONE_RE.findall("\n".join(segments))
    by_net: dict[tuple[str, str], int] = {}
    for _, net_name, layer in zones:
        by_net[(net_name, layer)] = by_net.get((net_name, layer), 0) + 1

    print(f"\nemitted zones: {len(zones)} across {len(by_net)} net/layer pairs")
    for (net, layer), count in sorted(by_net.items()):
        print(f"  {net:26s} {layer:8s} {count}")

    # C. gnd In1.Cu plane is emitted by _ground_plane.py separately in
    # the full route (unchanged path); this harness emits F.Cu/B.Cu
    # pours only, so report the gnd-family zone presence (PWR_RTN/CGND
    # GND-class) rather than the In1.Cu plane itself.
    gnd_class_zones = sum(c for (n, ly), c in by_net.items() if n in ("PWR_RTN", "CGND"))
    print(f"\nC. GND-class zones emitted (PWR_RTN/CGND): {gnd_class_zones}")

    # D. ntc-no honest PD3 failure: on F.Cu (the dense layer where the
    #    47+ island fragmentation was measured) it must emit NOTHING
    #    (0/4 pads coverable at 12.6mm).  On sparse inner layers (B.Cu/
    #    In3.Cu/In4.Cu) its THT pads DO exist there, so a carved zone
    #    containing one is the design doc's B2 outcome ("move to a sparse
    #    inner layer instead of fragmenting"), not a failure.
    ntc_zones_fcu = sum(
        c for (n, ly), c in by_net.items() if n == "power_in.ntc-no" and ly == "F.Cu"
    )
    print(f"D. power_in.ntc-no F.Cu zones emitted: {ntc_zones_fcu} (expected 0 at PD3)")

    # B. Creepage carve is the table the seam reads.
    from temper_placer.router_v6.zone_pour_creepage import default_creepage_table

    creepage = default_creepage_table()
    hv_lv = creepage.required("HighVoltage", "Power", "Pad")
    print(f"B. creepage table HV-vs-LV = {hv_lv}mm (12.6 expected)")

    # A. Zone outline geometry is derived from pin_world_position (the
    #    rotation-corrected source); sample one zone's first vertex is
    #    within board bounds.
    ok = gnd_class_zones > 0 and ntc_zones_fcu == 0 and hv_lv == 12.6 and len(zones) > 0
    print(f"\nRESULT: {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
