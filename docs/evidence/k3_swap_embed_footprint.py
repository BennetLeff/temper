#!/usr/bin/env python3
"""K3 relay footprint embed-swap: G5LE-1 -> temper:Relay_SPDT_Schrack-RT314012.

# provenance: commit=<filled-at-write-time> dirty=<bool>

Mirrors the K2 swap (#524) as applied in the repo's own precedent commit
(6af87796f, "feat(pcb,elec): swap K3 discharge relay ..." on branch
fix/k3-relay-swap-resolved): line-oriented replacement of K3's embedded
G5LE-1 footprint block with the RT314012 geometry taken from K2's embedded
block in the SAME board file (the canonical in-repo copy, byte-identical
geometry to the project temper.pretty library footprint), keeping K3's
tstamp and sheetpath, at K3's current board position (69.72, 29) rot 90 --
the solve moves it later; this commit only swaps the part.

Pads carry nets BY NUMBER from the netlist (elec/build/default.net after
make netlist): pad 1=COM/DC_BUS_RTN, 2=coil1/discharge.k_dis2-coil1,
3=NO/discharge.k_dis2-no, 4=NC/discharge.k_dis2-nc, 5=coil2 which shares
the discharge.k_dis1-coil2 node (the two relay coils are wired in series
through a shared node -- see elec/domain_manifest.yaml's coil list
comment; there is no separate "discharge.k_dis2-coil2" net record). Both
physical holes of the duplicated contact pads share the same net.

The net NUMBERS are taken from the board's own net table (net 5
DC_BUS_RTN, 40 discharge.k_dis2-coil1, 41 discharge.k_dis2-nc, 42
discharge.k_dis2-no, 37 discharge.k_dis1-coil2) so the written block's
(net N "name") pairs resolve consistently with the existing table.

Usage:
    python3 docs/evidence/k3_swap_embed_footprint.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
PCB = REPO / "pcb" / "temper.kicad_pcb"

# K3's tstamp preserved from the current G5LE-1 block (identity stability).
K3_TSTAMP = "3b259aaf-aef7-308b-67a9-bfce59ba6aea"
K3_AT = "69.72 29 90"

# net-number -> net-name for the nets the RT314012 pads carry (from the
# board's own net table).
NETS = {
    "1": (5, "DC_BUS_RTN"),
    "2": (40, "discharge.k_dis2-coil1"),
    "3": (42, "discharge.k_dis2-no"),
    "4": (41, "discharge.k_dis2-nc"),
    "5": (37, "discharge.k_dis1-coil2"),
}


def extract_block(text: str, start_marker: str) -> tuple[str, int, int]:
    """Return the full footprint block starting at the line containing
    start_marker (its own line through the matching closing line)."""
    lines = text.splitlines(keepends=True)
    start = next(i for i, l in enumerate(lines) if start_marker in l)
    depth = 0
    end = start
    for i in range(start, len(lines)):
        depth += lines[i].count("(") - lines[i].count(")")
        if depth <= 0:
            end = i
            break
    return "".join(lines[start : end + 1]), start, end


def main() -> None:
    text = PCB.read_text()
    k2_block, k2_start, k2_end = extract_block(
        text, '(footprint "temper:Relay_SPDT_Schrack-RT314012"'
    )
    k3_block, k3_start, k3_end = extract_block(
        text, '(footprint "Relay_THT:Relay_SPDT_Omron-G5LE-1"'
    )

    print(f"K2 block lines {k2_start+1}..{k2_end+1}")
    print(f"K3 block lines {k3_start+1}..{k3_end+1}")

    # Transform K2's block into K3's.
    new = k2_block
    # 1. tstamp -> K3's preserved tstamp
    new = re.sub(r"\(tstamp [0-9a-f-]+\)", f"(tstamp {K3_TSTAMP})", new, count=1)
    # 2. position -> K3's current board position (footprint origin stays;
    #    the solve moves it later)
    new = re.sub(r"\(at [0-9.]+ [0-9.]+(?: [0-9.]+)?\)", f"(at {K3_AT})", new, count=1)
    # 3. Reference property -> K3
    new = re.sub(r'\(property "Reference" "K2"\)', '(property "Reference" "K3")', new, count=1)
    # 4. Sheetpath -> discharge.k_dis2
    new = re.sub(
        r'\(property "Sheetpath" "discharge\.k_dis1"\)',
        '(property "Sheetpath" "discharge.k_dis2")',
        new,
        count=1,
    )
    # 5. Rewrite every pad net: (pad "N" ... (net M "name")) by number.
    # Pad records span two lines ((at ...) line then (net ...) line), so
    # match across newlines.
    def fix_pad(m: re.Match[str]) -> str:
        pad_no = m.group(1)
        net_no, net_name = NETS[pad_no]
        body = m.group(2)
        return f'(pad "{pad_no}" thru_hole {body}(net {net_no} "{net_name}"))'

    new = re.sub(
        r'\(pad "([1-5])" thru_hole (.+?)(\(net \d+ "[^"]+"\))\)',
        fix_pad,
        new,
        flags=re.S,
    )

    # Sanity: every pad must now carry a net that exists in the board table.
    for pad_no, (net_no, net_name) in NETS.items():
        assert f'(pad "{pad_no}"' in new, f"pad {pad_no} missing"
        assert f'(net {net_no} "{net_name}")' in new, f"net {net_no} {net_name} missing on pad {pad_no}"
    assert new.count('(net ') == 8, f"expected 8 pad nets, got {new.count('(net ')}"

    # Replace K3's block.
    lines = text.splitlines(keepends=True)
    new_lines = lines[:k3_start] + [new] + lines[k3_end + 1 :]
    PCB.write_text("".join(new_lines))
    print(f"wrote {PCB}: K3 block replaced (lines {k3_start+1}..{k3_end+1})")


if __name__ == "__main__":
    main()
