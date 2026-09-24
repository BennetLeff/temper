#!/usr/bin/env python3
"""Give the fixture's three no-MPN symbol shapes distinct KiCad library IDs.

Atopile 0.2.69 emits `lib:None` for each generic fixture component.
`gen_schematics.py` keys library definitions by that ID and otherwise loses
the two- and ten-pin symbol shapes. This transform changes only part names;
the compiled components, footprints, pin numbers and nets must remain equal.
"""

from __future__ import annotations

import sys
from pathlib import Path

FIXTURE = Path(__file__).resolve().parents[1]
REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO / "scripts"))
from gen_pcb_skeleton import parse_netlist  # noqa: E402


def normalize() -> None:
    source = FIXTURE / "build/default.net"
    output = FIXTURE / "candidate/source/normalized.net"
    text = source.read_text(encoding="utf-8")
    counts = {"RailInput": 2, "DutHarness": 1, "ProbePoint": 10}
    for part, count in counts.items():
        description = f"elec/src/rail_order_fixture.ato:{part}"
        old_source = f'(libsource (lib "lib") (part "None") (description "{description}"))'
        new_source = f'(libsource (lib "lib") (part "{part}") (description "{description}"))'
        if text.count(old_source) != count:
            raise ValueError(f"Atopile libsource count changed for {part}")
        text = text.replace(old_source, new_source)
        old_library = f'(libpart (lib "lib") (part "None")\n      (description "{description}")'
        new_library = f'(libpart (lib "lib") (part "{part}")\n      (description "{description}")'
        if text.count(old_library) != 1:
            raise ValueError(f"Atopile libpart shape changed for {part}")
        text = text.replace(old_library, new_library)
    if '(part "None")' in text:
        raise ValueError("unclassified generic part remains")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text, encoding="utf-8")
    before = parse_netlist(source)
    after = parse_netlist(output)
    if before.components != after.components or before.nets != after.nets:
        output.unlink()
        raise ValueError("symbol-ID normalization changed compiled connectivity")
    print(f"wrote {output}: three distinct symbol shapes, unchanged nets")


if __name__ == "__main__":
    normalize()
