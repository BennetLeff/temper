#!/usr/bin/env python3
"""AR-FAULT raw extraction: netlist nodes + PCB copper for the fault loop.

Reads the candidate source-manifest.json (authored netlist) and the candidate
section.kicad_pcb (routed copper). Writes:
  raw/netlist_fault_loop.json
  raw/pcb_fault_loop.txt
No interpretation here - verbatim evidence only.
"""
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = Path("/Users/bennet/Desktop/temper/.worktrees/codex/buck-harness-experiment-plan")
MANIFEST = REPO / "zapote/power-entry/shunt-repair/candidate/source-manifest.json"
PCB = REPO / "zapote/power-entry/shunt-repair/candidate/section.kicad_pcb"

man = json.loads(MANIFEST.read_text())
comp = {c["reference"]: c for c in man["components"]}
netnodes = {n["name"]: n["nodes"] for n in man["bridge"]["nets"]}

INTEREST = ["plus", "a1", "PFC_BUS_PLUS_390V", "PFC_BUS_MINUS", "minus",
            "l1", "l2", "ac1", "ac2", "AC_L_RECTIFIED_INPUT",
            "AC_N_RECTIFIED_INPUT", "PE_CHASSIS", "q_boost-g"]
REFDES = {"U1": "Q_boost bridge GBJ2510", "U8": "boost inductor 760800301",
          "U9": "boost switch STW65N65DM2AG", "U10": "boost diode C3D20065D",
          "U12": "shunt 10mohm", "U36": "c1 560uF", "U37": "c2 560uF",
          "U38": "c3 560uF", "U39": "c4 560uF", "U40": "c_hf 470nF",
          "U2": "fuse holder", "U7": "MOV V150LA10AP", "U3": "CMC",
          "U4": "NTC", "U5": "bypass relay", "U42": "mains connector",
          "U52": "output connector", "U11": "PFC controller UCC28180D"}

exc = {"schema": "pfc-campaign-AR-FAULT-raw-netlist/v1",
       "netlist_evidence": {n: {"nodes": netnodes[n],
                                "node_meaning": [REFDES.get(a, a) for a, _ in netnodes[n]]}
                            for n in INTEREST if n in netnodes},
       "component_evidence": {r: {"mpn": comp[r]["mpn"], "value": comp[r]["value"],
                                  "instance_path": comp[r]["instance_path"]}
                              for r in REFDES if r in comp}}
(HERE / "netlist_fault_loop.json").write_text(json.dumps(exc, indent=2) + "\n")

pcb = PCB.read_text()
lines = []
def section(pat, net):
    start = pcb.find(pat.format(net=net))
    return start

# segment/via/zone entries carry (net "NAME") as a child; capture the enclosing
# top-level element by simple line scan.
depth = 0
buf = []
cur = None
for line in pcb.splitlines():
    stripped = line.strip()
    if stripped.startswith("(segment") or stripped.startswith("(via") or stripped.startswith("(zone"):
        cur = stripped.split()[0][1:]
        buf = [line]
        depth = line.count("(") - line.count(")")
        continue
    if cur is not None:
        buf.append(line)
        depth += line.count("(") - line.count(")")
        if depth <= 0:
            blob = "\n".join(buf)
            m = re.search(r'\(net "([^"]+)"\)', blob)
            if m and m.group(1) in INTEREST:
                lines.append(blob)
            cur = None

header = ("AR-FAULT attempt-001 raw PCB copper extract\n"
          "board: zapote/power-entry/shunt-repair/candidate/section.kicad_pcb\n"
          "nets of interest: " + ", ".join(INTEREST) + "\n"
          f"elements captured: {len(lines)}\n" + "=" * 70 + "\n")
(HERE / "pcb_fault_loop.txt").write_text(header + "\n\n".join(lines) + "\n")
print(f"netlist nodes written for: {list(exc['netlist_evidence'])}")
print(f"PCB elements captured: {len(lines)}")
for n in INTEREST:
    c = sum(1 for b in lines if f'(net "{n}")' in b)
    print(f"  {n}: {c}")
