#!/usr/bin/env python3
"""Apply the recommended R24 re-placement to pcb/temper.kicad_pcb.

# provenance: commit=f2b09d84673b3a18d8fabe454230f1b240148f3d dirty=false

Writes the ONE candidate recommended in
``docs/evidence/2026-08-04-r24-barrier-resolve.md`` -- candidate 2, ``R24`` to
absolute (81.00, 21.50), rotation unchanged -- using the same mechanism the
prior board writes used (``write_placements_to_pcb`` with the ``components``
list so the writer's bbox-centre -> footprint-origin conversion is
rotation-aware, ``k3_swap_board_write_apply.py``).

Only ``R24`` is handed to the writer and ``preserve_unmatched=True``, so every
other footprint is left exactly as committed -- verified below by re-parsing
the written board and asserting that ``R24`` is the only ref whose position
changed.

Why candidate 2 and not candidate 1: candidate 1 (57.50, 38.50) is 6.5mm
closer in displacement and sits nearer R24's net-mates, but it measures
``courtyards_overlap`` 11 -> 12 and ``silk_over_copper`` 172 -> 173, each of
which is a ceiling RAISE requiring a ``Ceiling-Approval:`` trailer. Candidate 2
moves no DRC count at all (see the doc's Sec 4 table).

Usage:
    uv run --no-sync python docs/evidence/2026-08-04-r24-barrier-apply.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve()
while not (REPO / "pyproject.toml").exists():
    REPO = REPO.parent

_PLACER = REPO / "packages" / "temper-placer"
os.chdir(_PLACER)
sys.path.insert(0, str(_PLACER))

from temper_placer.io._write_board import (  # noqa: E402
    PlacementUpdate,
    write_placements_to_pcb,
)
from temper_placer.io.kicad_parser import parse_kicad_pcb  # noqa: E402

PCB = REPO / "pcb" / "temper.kicad_pcb"
TARGET_ABS = (81.00, 21.50)


def main() -> None:
    pcb = parse_kicad_pcb(PCB)
    origin = getattr(pcb.board, "origin", (0.0, 0.0))
    before = {c.ref: c.initial_position for c in pcb.netlist.components}
    rot = {c.ref: int(c.initial_rotation or 0) for c in pcb.netlist.components}
    print(
        f"R24 before: local {before['R24']} = absolute "
        f"({before['R24'][0]+origin[0]:.3f}, {before['R24'][1]+origin[1]:.3f})"
    )
    print(f"R24 target absolute: {TARGET_ABS}  (rotation unchanged, idx {rot['R24']})")

    res = write_placements_to_pcb(
        template_pcb=PCB,
        output_pcb=PCB,
        placements={
            "R24": PlacementUpdate(
                ref="R24", x=TARGET_ABS[0], y=TARGET_ABS[1], rotation=rot["R24"] * 90.0
            )
        },
        preserve_unmatched=True,
        components=pcb.netlist.components,
    )
    print(f"write: {res.components_updated} component(s) updated, {len(res.warnings)} warning(s)")
    for w in res.warnings[:10]:
        print("  warning:", w)

    pcb2 = parse_kicad_pcb(PCB)
    after = {c.ref: c.initial_position for c in pcb2.netlist.components}
    want = (TARGET_ABS[0] - origin[0], TARGET_ABS[1] - origin[1])
    got = after["R24"]
    moved = [
        r
        for r in before
        if r in after
        and (abs(after[r][0] - before[r][0]) > 1e-6 or abs(after[r][1] - before[r][1]) > 1e-6)
    ]
    print(f"round-trip R24: want_local {want} got_local {got}")
    print(f"refs whose position changed: {moved}")
    assert moved == ["R24"], f"expected only R24 to move, got {moved}"
    assert abs(got[0] - want[0]) < 0.02 and abs(got[1] - want[1]) < 0.02
    print("OK")


if __name__ == "__main__":
    main()
