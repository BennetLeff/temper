#!/usr/bin/env python3
"""Read-only, standard-library pin extraction for D10; not a design validator.

Run from any directory. Output is JSON on stdout; exits nonzero on power-board
source/netlist/pad disagreement. No Rust or pcbnew import/build is performed.
"""
from __future__ import annotations

import bisect
import hashlib
import json
from pathlib import Path
import platform
import re
import subprocess
from dataclasses import dataclass
from typing import Iterator

ROOT = Path(__file__).resolve().parents[5]
PS = "zapote/power-stage-120v/"

@dataclass(frozen=True)
class Node:
    items: tuple[str | Node, ...]
    line: int

    @property
    def tag(self) -> str:
        return str(self.items[0])

    def children(self, tag: str) -> Iterator[Node]:
        return (x for x in self.items if isinstance(x, Node) and x.tag == tag)

    def one(self, tag: str) -> Node:
        values = list(self.children(tag))
        if len(values) != 1:
            raise ValueError(f"Expected one {tag} at line {self.line}, got {len(values)}")
        return values[0]


def parse(path: str) -> Node:
    source = (ROOT / path).read_text()
    newlines = [m.start() for m in re.finditer("\n", source)]
    stack: list[tuple[list[str | Node], int]] = []
    result: list[Node] = []
    for m in re.finditer(r'"(?:\\.|[^"\\])*"|[()]|[^\s()]+', source):
        token = m.group()
        if token == "(":
            stack.append(([], bisect.bisect_left(newlines, m.start()) + 1))
        elif token == ")":
            items, line = stack.pop()
            node = Node(tuple(items), line)
            if stack:
                stack[-1][0].append(node)
            else:
                result.append(node)
        else:
            stack[-1][0].append(json.loads(token) if token.startswith('"') else token)
    if stack or len(result) != 1:
        raise ValueError(f"Malformed document: {path}")
    return result[0]


def board(path: str, all_parts: bool = False) -> dict:
    result = {}
    for fp in parse(path).children("footprint"):
        props = {str(p.items[1]): str(p.items[2]) for p in fp.children("property")}
        ref = props.get("Reference", "")
        if not all_parts and not (ref.startswith("J") or "ESP32" in str(fp.items[1]) or props.get("Sheetpath") == "power_mgmt.buck_3v3.buck"):
            continue
        pads = {}
        for pad in fp.children("pad"):
            nets = list(pad.children("net"))
            pads.setdefault(str(pad.items[1]), []).append({"net": str(nets[0].items[-1]) if nets else None, "line": pad.line})
        result[ref] = {"value": props.get("Value"), "footprint": fp.items[1], "sheetpath": props.get("Sheetpath"), "line": fp.line, "pads": pads}
    return result


def main() -> None:
    paths = {
        "power": PS + "native-17/section.kicad_pcb",
        "interlock": "zapote/interlock/candidate/section.kicad_pcb",
        "gate-drive": "zapote/gate-drive/candidate/section.kicad_pcb",
        "current-sense": "zapote/current-sense/candidate/section.kicad_pcb",
        "thermal-sense": "zapote/thermal-sense/candidate/section.kicad_pcb",
        "rtd": "zapote/rtd/unit/candidate/section.kicad_pcb",
        "controller": "pcb/temper.kicad_pcb",
    }
    source_path = PS + "elec/src/power_stage_120v.ato"
    source_map = {}
    for i, line in enumerate((ROOT / source_path).read_text().splitlines(), 1):
        m = re.match(r"\s*j_selv\.p(\d+) ~ (\w+)", line)
        if m:
            source_map[m[1]] = {"net": m[2].lower(), "line": i}
    net_path = PS + "frozen/default.net"
    net_doc = parse(net_path)
    nets = {}
    header = {}
    for net in net_doc.one("nets").children("net"):
        name = str(net.one("name").items[1])
        nodes = [{"ref": str(n.one("ref").items[1]), "pin": str(n.one("pin").items[1]), "line": n.line} for n in net.children("node")]
        nets[name] = {"line": net.line, "nodes": nodes}
        for n in nodes:
            if n["ref"] == "J4":
                header[n["pin"]] = name
    boards = {name: {"path": path, "connectors": board(path)} for name, path in paths.items()}
    # Authored semantic candidates, never a claim that a cable exists.
    candidates = {
        "1": [("controller", "U3", "3", "+15V", "possible supply input, already connected locally")],
        "3": [("controller", "U27", "2", "+3V3", "rail only; no supply connector")],
        "5": [("controller", "U27", "4", "PWM_HS", "unallocated producer"), ("gate-drive", "J1", "1", "pwm_h", "another receiver")],
        "6": [("controller", "U27", "5", "PWM_LS", "unallocated producer"), ("gate-drive", "J1", "2", "pwm_l", "another receiver")],
        "9": [("interlock", "J2", "6", "permit", "producer")],
        "10": [("interlock", "J1", pin, net, "candidate receiver; select one") for pin, net in [("2", "ocp_fault"), ("3", "ovp_fault"), ("8", "aux_fault")]],
        "11": [("controller", "U27", "38", "V_BUS_SENSE", "single-ended input already locally driven")],
        "14": [("controller", "U27", "39", "I_SENSE", "input already locally driven"), ("current-sense", "J2", "4", "SENSE_MON", "another output; not a receiver")],
    }
    returns = [("interlock", "J2", "2", "gnd", "common return"), ("gate-drive", "J1", "4", "ctrl_gnd", "common return"), ("current-sense", "J2", "2", "gnd", "common return"), ("thermal-sense", "J3", "2", "gnd", "common return"), ("rtd", "J2", "2", "gnd", "common return"), ("rtd", "J2", "3", "gnd", "common return")]
    for pin in ["2", "4", "15", "16"]:
        candidates[pin] = returns
    correspondence = {}
    for pin in source_map:
        rows = []
        for unit, ref, pad, expected, role in candidates.get(pin, []):
            actual = boards[unit]["connectors"][ref]["pads"][pad]
            if {p["net"] for p in actual} != {expected}:
                raise ValueError(f"STOP: counterpart changed: {unit} {ref}.{pad}")
            rows.append({"unit": unit, "ref": ref, "pin": pad, "net": expected, "role": role, "lines": [p["line"] for p in actual]})
        correspondence[pin] = {"selected_harness": None, "candidates_only": rows}
    native = boards["power"]["connectors"]["J4"]["pads"]
    comparison = []
    for pin in sorted(source_map, key=int):
        expected = source_map[pin]["net"]
        actual = {p["net"] for p in native[pin]}
        comparison.append({"pin": pin, "source": source_map[pin], "netlist": header.get(pin), "board_nets": sorted(actual), "match": actual == {expected} and header.get(pin) == expected})
    if len(comparison) != 16 or not all(row["match"] for row in comparison):
        raise ValueError(f"STOP: J4 source/netlist/native contradiction: {comparison}")
    # Preserve the actual endpoint identities, not just connector net labels.
    selected = set(header.values()) | {"ct_s1", "ct_s2", "ct_sense_mon", "pe", "v3v3"}
    power_parts = board(paths["power"], all_parts=True)
    special_parts = {k: v for k, v in power_parts.items() if k in {"T1", "R39", "C42", "R38", "R40", "R41", "R42", "R47", "D4", "D5", "PS1", "U4", "U9", "U10", "U11", "U12", "U13", "Q1", "Q4"}}
    selected_net_comparison = {}
    for net in sorted(selected):
        if net not in nets:
            continue
        frozen_nodes = {(n["ref"], n["pin"]) for n in nets[net]["nodes"]}
        native_nodes = {(ref, pin) for ref, fp in power_parts.items() for pin, pads in fp["pads"].items() if any(p["net"] == net for p in pads)}
        selected_net_comparison[net] = {"match": frozen_nodes == native_nodes, "netlist_only": sorted(frozen_nodes-native_nodes), "native_only": sorted(native_nodes-frozen_nodes)}
    if not all(v["match"] for v in selected_net_comparison.values()):
        raise ValueError(f"STOP: selected native/netlist endpoint contradiction: {selected_net_comparison}")
    input_paths = list(paths.values()) + [source_path, net_path, PS + "frozen/default.csv", "elec/src/main.ato", "elec/src/modules.ato", "zapote/ports.toml", "zapote/project.toml", "zapote/interlock/interface-contract.json"]
    input_paths += ["zapote/interlock/INTERFACES.md", "zapote/interlock/source-build-02/elec/src/interlock_unit.ato", "zapote/gate-drive/INTERFACES.md", "zapote/current-sense/INTERFACES.md", "zapote/thermal-sense/INTERFACES.md", "zapote/rtd/unit/HANDOFF.md", PS + "elec/src/parts.ato"]
    digest = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in input_paths}
    git = lambda *args: subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()
    # Use last input-changing commit so regenerating after a documentation commit is stable.
    source_revision = git("log", "-1", "--format=%H", "--", *input_paths)
    result = {"scope": "D10 exact structural extraction; electrical acceptance remains in README", "input_revision": source_revision, "runtime": platform.python_version(), "input_sha256": digest, "j4_comparison": comparison, "counterpart_candidates": correspondence, "boards": boards, "power_selected_nets": {k: nets[k] for k in sorted(selected) if k in nets}, "power_selected_parts": special_parts, "selected_net_comparison": selected_net_comparison}
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
