#!/usr/bin/env python3
"""Port the standalone interlock and thermal-sense sources into the controller.

Each block goes in as its own sheet with no value or topology change. The only
edit is at the board boundary: the standalone inter-board headers (interlock
J1/J2, thermal-sense J3) and the thermal-sense +3V3/gnd net-name overrides are
removed, because on the integrated board those nets are wired directly to the
controller's v3v3/selv_gnd and to the MCU. The probe connectors stay.

The transform is a pure line filter, so ``verify_controller.py`` can re-run it
and prove the committed port equals ``source - removed lines`` byte for byte.

Usage: python3 tools/port_blocks.py [--check]
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

UNIT = Path(__file__).resolve().parents[1]
ZAPOTE = UNIT.parent

PORTS = {
    "interlock": {
        "source": ZAPOTE / "interlock/source-build-02/elec/src/interlock_unit.ato",
        "target": UNIT / "elec/src/interlock_block.ato",
        "drop_component": "InterlockHeader",
        "drop_instances": ("faults", "host"),
        "drop_overrides": (),
    },
    "thermal": {
        "source": ZAPOTE / "thermal-sense/source-build-02/elec/src/thermal_sense_unit.ato",
        "target": UNIT / "elec/src/thermal_block.ato",
        "drop_component": "ThermalHostConnector",
        "drop_instances": ("host",),
        "drop_overrides": ("vcc", "gnd"),
    },
}

HEADER = (
    "# PORTED for zapote/controller by tools/port_blocks.py from {src}\n"
    "# (sha256 {sha}). Removed only: the standalone {comp} header component, its\n"
    "# instances {inst} and their pin joins{ov}. Everything else is byte-identical.\n"
)


def port(spec: dict) -> tuple[str, list[str]]:
    text = spec["source"].read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    removed: list[str] = []
    in_drop = False
    inst = "|".join(spec["drop_instances"])
    inst_re = re.compile(rf"^\s+(?:({inst})\s*=\s*new\s|({inst})\.p\d+\s*~|\S+\s*~\s*({inst})\.p\d+\s*$)")
    ov = "|".join(spec["drop_overrides"]) or "^$"
    ov_re = re.compile(rf"^\s+({ov})\.override_net_name\s*=")
    for line in lines:
        if line.startswith(f"component {spec['drop_component']}:"):
            in_drop = True
            removed.append(line)
            continue
        if in_drop:
            if line.strip() == "" or line.startswith((" ", "\t")):
                removed.append(line)
                continue
            in_drop = False
        if inst_re.match(line) or (spec["drop_overrides"] and ov_re.match(line)):
            removed.append(line)
            continue
        out.append(line)
    sha = hashlib.sha256(text.encode()).hexdigest()
    rel = spec["source"].relative_to(ZAPOTE.parent)
    ov_note = (" and the " + "/".join(spec["drop_overrides"]) + " net-name overrides") if spec["drop_overrides"] else ""
    header = HEADER.format(src=rel, sha=sha, comp=spec["drop_component"],
                           inst="/".join(spec["drop_instances"]), ov=ov_note)
    return header + "".join(out), removed


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="fail if committed ports differ")
    args = ap.parse_args()
    bad = 0
    for name, spec in PORTS.items():
        text, removed = port(spec)
        if args.check:
            ok = spec["target"].read_text(encoding="utf-8") == text
            print(f"{name}: {'OK' if ok else 'DIFFERS'} ({len(removed)} boundary lines removed)")
            bad += not ok
        else:
            spec["target"].write_text(text, encoding="utf-8")
            print(f"{name}: wrote {spec['target'].relative_to(UNIT)}; removed {len(removed)} lines")
            for line in removed:
                print("   -", line.rstrip())
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
