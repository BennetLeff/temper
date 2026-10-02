#!/usr/bin/env python3
"""D-11 scope-conflict evidence; read-only, standard library, no native builds.

Uses the committed D-10 S-expression reader (hashed below), not its audit.
Nominal equations demonstrate OVP coupling, not an approved replacement design.
"""
from __future__ import annotations

import csv
import hashlib
import json
import platform
import runpy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[7]
PS = "zapote/power-stage-120v/"
READER = PS + "validation-results/06-controller-interface/scripts/interface_check.py"
BASE = "4574380993f525cdfa4f41702416b398a22689c3"


def main() -> None:
    reader = runpy.run_path(str(ROOT / READER))
    board_path = PS + "native-17/section.kicad_pcb"
    net_path = PS + "frozen/default.net"
    bom_path = PS + "frozen/default.csv"
    source_path = PS + "elec/src/power_stage_120v.ato"
    board = reader["board"](board_path, all_parts=True)
    nets = reader["parse"](net_path).one("nets")
    selected = {}
    for net in nets.children("net"):
        name = str(net.one("name").items[1])
        if name not in {"vsense_in", "ovp_thresh"}:
            continue
        frozen = sorted((str(n.one("ref").items[1]), str(n.one("pin").items[1]))
                        for n in net.children("node"))
        native = sorted((ref, pin) for ref, fp in board.items()
                        for pin, pads in fp["pads"].items()
                        if any(p["net"] == name for p in pads))
        if frozen != native:
            raise ValueError(f"STOP: netlist/native disagreement on {name}")
        selected[name] = {"netlist_line": net.line, "nodes": frozen,
                          "native_matches": True}
    if not {("U4", "2"), ("U7", "4")} <= set(selected["vsense_in"]["nodes"]):
        raise ValueError("Shared-tap finding no longer applies: re-review D-11")
    expected = {**{f"R{i}": "RC1206FR-07470KL" for i in range(26, 30)},
                "R30": "RT0603BRD0715K8L", "R36": "RT0603BRD0710KL",
                "R37": "RT0603BRD07140KL", "U4": "AMC1311BDWVR",
                "U7": "TLV3201AIDBVR"}
    with (ROOT / bom_path).open(newline="") as handle:
        rows = list(csv.reader(handle))
    for ref, mpn in expected.items():
        matches = [row for row in rows if len(row) > 1 and ref in row[1].split(",")]
        if len(matches) != 1 or matches[0][0] != mpn or board[ref]["value"] != mpn:
            raise ValueError(f"BOM/native identity changed: {ref}")
    source = (ROOT / source_path).read_text()
    required = ["u_vsense.VINP ~ VSENSE_IN", "u_ovp.INN ~ VSENSE_IN",
                "r_ovp_top.value = 10kohm", "r_ovp_bot.value = 140kohm",
                "r_div_bot.value = 15.8kohm"]
    if not all(line in source for line in required):
        raise ValueError("Source circuit changed: re-review D-11")
    source_lines = {line: source[:source.index(line)].count("\n") + 1 for line in required}
    top = 4 * 470_000.0
    bottom = 15_800.0
    ratio = bottom / (top + bottom)
    threshold = 2.5 * 140_000.0 / (10_000.0 + 140_000.0)
    # Counterexample only. No resistor selection/rating/accuracy approval.
    example_bottom = 12_400.0
    example_ratio = example_bottom / (top + example_bottom)
    paths = [board_path, net_path, bom_path, source_path, READER]
    result = {
        "status": "BLOCKED_SCOPE_SHARED_OVP_DIVIDER",
        "model_provider": "OpenAI GPT-6 / Codex",
        "base_revision": BASE,
        "runtime": platform.python_version(),
        "input_sha256": {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in paths},
        "source_lines": source_lines,
        "nets": selected,
        "native_parts": {r: board[r] for r in expected},
        "nominal_only": {
            "top_ohm": top, "bottom_ohm": bottom,
            "ovp_reference_v": threshold,
            "current_linear_bus_limit_v": 2 / ratio,
            "current_ovp_trip_v": threshold / ratio,
            "range_table": [{"bus_v": v, "current_u4_input_v": v * ratio,
                             "counterexample_u4_input_v": v * example_ratio}
                            for v in (170, 198, 240, 280)],
            "counterexample_bottom_ohm_NOT_RECOMMENDED": example_bottom,
            "counterexample_ovp_trip_v": threshold / example_ratio,
            "minimum_ovp_trip_if_280V_maps_to_at_most_2V": threshold * 280 / 2,
        },
    }
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
