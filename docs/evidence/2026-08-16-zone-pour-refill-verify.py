#!/usr/bin/env python3
"""kicad-cli --refill-zones verification of the Rust-generated zones.

Takes the zone outlines the production seam emits for the real board
(docs/evidence/2026-08-16-zone-pour-seam-verify.py), splices them into
a COPY of pcb/temper.kicad_pcb (replacing existing zones, same as the
route path's strip_existing_zones), and runs kicad-cli pcb drc
--refill-zones.  Counts isolated_copper findings -- the failure mode the
old single-ring emitter produced (167 islands board-wide).

Read-only: never writes the tracked board.

Usage: .venv/bin/python docs/evidence/2026-08-16-zone-pour-refill-verify.py
"""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PCB_PATH = REPO_ROOT / "pcb" / "temper.kicad_pcb"

ZONE_BLOCK_RE = re.compile(r"^  \(zone ", re.M)


def main() -> int:
    sys.path.insert(0, str(REPO_ROOT / "packages" / "temper-placer"))

    from temper_placer.io.kicad_parser import parse_kicad_pcb_v6
    from temper_placer.router_v6._zone_pour_stitch import _emit_zone_pours
    from temper_placer.router_v6.pad_connectivity_audit import _pads_by_net

    pcb = parse_kicad_pcb_v6(PCB_PATH)
    pads_by_net = _pads_by_net(pcb)
    net_name_to_number: dict[str, int] = {}
    for m in re.finditer(r'\(net\s+(\d+)\s+"([^"]+)"', PCB_PATH.read_text()):
        net_name_to_number[m.group(2)] = int(m.group(1))
    pad_positions: dict[str, list[tuple[float, float]]] = {
        net: [p.position for p in pads] for net, pads in pads_by_net.items()
    }
    segments: list[str] = []
    _emit_zone_pours(pad_positions, segments, net_name_to_number, pcb=pcb)
    zone_blocks = [s for s in segments if "(zone " in s]
    print(f"seam emitted {len(zone_blocks)} zone blocks")

    content = PCB_PATH.read_text()
    # Replace every existing zone with the seam's (R7 replace) using the
    # production strip primitive (balanced s-expression removal), not a
    # regex -- a regex strip breaks the file's nesting (measured).
    from temper_placer.router_v6._strip_copper import strip_existing_zones

    stripped, removed = strip_existing_zones(content)
    print(f"stripped {removed} committed zones")
    new_zones = "\n".join(zone_blocks)
    # Insert before the final closing paren (same seam as _write_routes_to_content).
    stripped = stripped.rstrip()
    assert stripped.endswith(")")
    out = stripped[:-1] + new_zones + "\n)\n"
    print(f"spliced content: {len(out)} bytes, {len(zone_blocks)} zones")

    with tempfile.TemporaryDirectory() as td:
        board_path = Path(td) / "refill.kicad_pcb"
        board_path.write_text(out)
        (Path(td) / "refill.kicad_pro").write_text(
            PCB_PATH.with_suffix(".kicad_pro").read_text()
        )
        (Path(td) / "refill.kicad_dru").write_text(
            (REPO_ROOT / "pcb" / "temper.kicad_dru").read_text()
        )
        rpt = Path(td) / "drc.rpt"
        r = subprocess.run(
            [
                "kicad-cli", "pcb", "drc", str(board_path),
                "--output", str(rpt), "--refill-zones", "--severity-all",
            ],
            capture_output=True, text=True, timeout=600,
        )
        print("kicad-cli exit:", r.returncode)
        if not rpt.exists():
            print("NO DRC REPORT -- parse or fill failure:")
            print(r.stdout[-800:])
            print(r.stderr[-800:])
            return 1
        text = rpt.read_text()
        isolated = len(re.findall(r"isolated_copper", text))
        creepage = len(re.findall(r"creepage", text))
        print(f"isolated_copper findings after --refill-zones: {isolated}")
        print(f"creepage findings after --refill-zones: {creepage}")
        ok = isolated == 0
        print(f"\nRESULT: {'PASS (no isolated islands)' if ok else 'FAIL'}")
        return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
