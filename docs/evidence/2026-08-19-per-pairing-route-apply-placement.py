# provenance: commit=de3e5dabe65f2ac01680b59dfb0ece2a130b4770 dirty=false
# Measurements taken at this commit (barrier 20.0mm configuration) and at
# fd4e73644fec24b26a0c0c4ec51f5c7573c151e4 (barrier 12.6mm configuration),
# working tree clean in both. See
# docs/evidence/2026-08-19-per-pairing-placement-routed.md
"""Apply a solved placement JSON to a TEMPLATE board, writing a SCRATCH board.

Never writes pcb/temper.kicad_pcb: --output is mandatory and is refused if it
resolves to the template. Verifies the template's sha256 before and after.

Contract copied from the production CLI path
(temper_placer/cli/__init__.py's `optimize`) and from
docs/evidence/2026-08-12-heatsink-writeback.py:

  * rotation degrees = rotations.get(ref, 0) * 90.0   (the solve emits an INDEX)
  * board_origin = board.origin  -- parse_kicad_pcb normalises against
    Edge.Cuts, so omitting it writes every footprint ~20mm off the outline
  * components = netlist.components -- converts CP-SAT bbox-centre coords to
    KiCad footprint-anchor coords
  * copy_kicad_project_sidecar so .kicad_pro/.kicad_dru travel with the board
  * check_placement_roundtrip + check_board_containment afterwards
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from temper_placer.io._write_types import PlacementUpdate
from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.io.kicad_writer import write_placements_to_pcb
from temper_placer.validation._drc_api import copy_kicad_project_sidecar
from temper_placer.validation.placement_roundtrip import check_placement_roundtrip


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--placement", type=Path, required=True)
    ap.add_argument("--template", type=Path, default=Path("pcb/temper.kicad_pcb"))
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    if args.output.resolve() == args.template.resolve():
        ap.error("--output must not be the template board")

    before = sha256(args.template)
    print(f"template sha256 BEFORE : {before}")

    data = json.loads(args.placement.read_text(encoding="utf-8"))
    prov = data.get("provenance", {})
    expected = prov.get("board_sha256_expected")
    if expected and expected != before:
        raise SystemExit(f"placement was solved against {expected}, template is {before}")
    print(f"placement provenance   : status={prov.get('status')} "
          f"relaxed={prov.get('relaxed_isolator_straddle')} seed={prov.get('seed')}")

    positions = {ref: tuple(xy) for ref, xy in data["positions"].items()}
    rot_idx = data.get("rotations", {})

    parse = parse_kicad_pcb(args.template)
    netlist, board = parse.netlist, parse.board
    print(f"board.origin           : {board.origin}")
    print(f"components in netlist  : {len(netlist.components)}")
    print(f"components in placement: {len(positions)}")

    missing = sorted({c.ref for c in netlist.components} - set(positions))
    if missing:
        print(f"WARNING: {len(missing)} netlist components absent from the "
              f"placement (left at their committed positions): {missing[:20]}")

    placements = {
        ref: PlacementUpdate(ref=ref, x=xy[0], y=xy[1],
                             rotation=float(rot_idx.get(ref, 0)) * 90.0)
        for ref, xy in positions.items()
    }

    result = write_placements_to_pcb(
        template_pcb=args.template,
        output_pcb=args.output,
        placements=placements,
        preserve_unmatched=True,
        components=netlist.components,
        board_origin=board.origin,
    )
    print(f"written                : {result.output_path}")
    print(f"components_updated     : {result.components_updated}  "
          f"skipped={result.components_skipped}")
    for w in result.warnings:
        print(f"  WRITE WARNING: {w}")

    copy_kicad_project_sidecar(args.output, args.template)

    # check_placement_roundtrip wants positions in FILE coordinates ("the same
    # coordinate frame the writer wrote"), while the solve emits the
    # normalize=True frame. Add board.origin back, exactly as
    # write_placements_to_pcb's board_origin kwarg does internally. (The
    # production CLI's own call omits this and is off by board.origin --
    # reported, not copied.)
    ox, oy = board.origin
    file_frame = {ref: (xy[0] + ox, xy[1] + oy) for ref, xy in positions.items()}
    rt = check_placement_roundtrip(
        args.output, file_frame,
        rotations={r: float(rot_idx.get(r, 0)) * 90.0 for r in positions},
        template_components=netlist.components,
    )
    ok = rt.passed
    print(f"placement roundtrip    : {rt.summary}")

    cont = subprocess.run(
        [sys.executable, "scripts/check_board_containment.py", "--board", str(args.output)],
        capture_output=True, text=True,
    )
    print(f"board containment      : rc={cont.returncode}")
    print("  " + "\n  ".join((cont.stdout + cont.stderr).strip().splitlines()[-12:]))

    after = sha256(args.template)
    print(f"template sha256 AFTER  : {after}")
    if after != before:
        raise SystemExit("TEMPLATE BOARD WAS MODIFIED -- aborting")
    print(f"scratch board sha256   : {sha256(args.output)}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
