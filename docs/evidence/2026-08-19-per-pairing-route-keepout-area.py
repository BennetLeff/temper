# provenance: commit=de3e5dabe65f2ac01680b59dfb0ece2a130b4770 dirty=false
# Measurements taken at this commit (barrier 20.0mm configuration) and at
# fd4e73644fec24b26a0c0c4ec51f5c7573c151e4 (barrier 12.6mm configuration),
# working tree clean in both. See
# docs/evidence/2026-08-19-per-pairing-placement-routed.md
"""How much of the board the HV<->SELV keepout covers, at both barrier widths.

`compute_hv_selv_keepout` unions a `DEFAULT_CORRIDOR_WIDTH_MM`-radius disc
around every HV-domain pad, and that union is a hard obstacle for the A*
grid, the straight-line fallback, the zone pour and the via search. Since
`DEFAULT_CORRIDOR_WIDTH_MM = MIN_BARRIER_WIDTH_MM + 0.5`, the per-pairing
branch's raise of MIN_BARRIER_WIDTH_MM from 12.6 to 20.0 moves the disc
radius 13.1 -> 20.5 mm. This measures what that costs in routable area, on
whichever board it is given -- so the router-side confound can be separated
from anything the placement did.

The HV pad inventory and the board polygon are taken through the SAME calls
`_power_islands.generate_power_islands_content` makes (`_pads_by_net`,
`_get_board_polygon`, `load_domain_manifest_nets`), not a re-derivation.

Read-only.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from temper_placer.io.kicad_parser import parse_kicad_pcb_v6
from temper_placer.placer.cp_sat.isolation_barrier import load_domain_manifest_nets
from temper_placer.router_v6._ground_plane import compute_hv_selv_keepout
from temper_placer.router_v6.pad_connectivity_audit import _pads_by_net
from temper_placer.router_v6.routing_space import _get_board_polygon


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", type=Path, required=True)
    ap.add_argument("--manifest", type=Path, default=Path("elec/domain_manifest.yaml"))
    ap.add_argument("--label", default="")
    ap.add_argument("--widths", default="13.1,20.5")
    args = ap.parse_args()

    pcb = parse_kicad_pcb_v6(args.board)
    pads_by_net = _pads_by_net(pcb)
    board_polygon = _get_board_polygon(pcb)
    hv_nets, selv_nets = load_domain_manifest_nets(args.manifest)

    hv_positions = [pad.position
                    for net in sorted(hv_nets)
                    for pad in pads_by_net.get(net, [])]

    area = board_polygon.area
    print(f"=== {args.label or args.board} ===")
    print(f"HV nets {len(hv_nets)}  SELV nets {len(selv_nets)}  "
          f"HV pads {len(hv_positions)}")
    print(f"board polygon area = {area:.0f} mm^2")

    for w in [float(x) for x in args.widths.split(",")]:
        ko = compute_hv_selv_keepout(hv_positions, [], board_polygon, w)
        a = 0.0 if ko is None else ko.intersection(board_polygon).area
        print(f"  corridor_width={w:5.1f} mm  keepout = {a:9.1f} mm^2 "
              f"({a / area * 100:5.1f}% of the board)  "
              f"free = {area - a:9.1f} mm^2")


if __name__ == "__main__":
    main()
