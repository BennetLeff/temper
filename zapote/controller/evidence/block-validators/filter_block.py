#!/usr/bin/env python3
"""Filter pcb/controller.kicad_pcb to one ported block and map it to unit names.

Plain Python 3 text surgery on the saved KiCad 10 board (no KiCad needed). The
controller board is only read.  The output is a *new* board holding exactly the
block's footprints, so the existing unit exporters
(``current-sense/tools/extract_current_sense_native.py`` for interlock and
thermal-sense, ``rtd/native_measure.py`` for the RTD) run on it unchanged and
every saved-board/export binding stays self-consistent.

What the filter does (and nothing else):

1. keeps footprints whose ``SourceInstance`` starts with ``<prefix>.``
   (``interlock.``, ``thermal.``, ``rtd_pan.``).  ``interlock.`` and
   ``thermal.`` are stripped to give the unit instance names; ``rtd_pan.`` is
   the unit's own instance prefix and is kept (rtd/unit/HANDOFF.md).
2. derives the controller-net -> unit-net map from the unit's compiled source
   manifest (bridge nets + reference -> instance_path + strict_pin_map), by
   looking up the controller pad that carries each unit (instance, pad).  A
   unit net that lands on two controller nets, or two unit nets that land on
   one controller net, is reported as a CONFLICT and is NOT merged or split.
3. renames those nets, keeps every segment / via / zone whose net is one of the
   block's nets (all of that net's copper, so connectivity is not cut), and
   drops everything else (other footprints, foreign-net copper, all graphics
   except Edge.Cuts).  Stored zone fills are kept verbatim; no refill.

Unit instances with no controller footprint (the host connectors, which the
controller replaces by direct nets) are listed as ``absent_unit_instances`` in
the mapping report; nothing is synthesised for them.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

PREFIX = {"interlock": "interlock.", "thermal": "thermal.", "rtd_pan": "rtd_pan."}
STRIP = {"interlock": True, "thermal": True, "rtd_pan": False}
NET_RE = re.compile(r'\(net "((?:[^"\\]|\\.)*)"\)')


def split_top(text: str) -> list[str]:
    """Return the source text of each direct child form of the root form."""
    depth, i, n = 0, 0, len(text)
    in_str = False
    children, start = [], 0
    while i < n:
        c = text[i]
        if in_str:
            if c == "\\":
                i += 1
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c == "(":
            depth += 1
            if depth == 2:
                start = i
        elif c == ")":
            if depth == 2:
                children.append(text[start:i + 1])
            depth -= 1
        i += 1
    return children


def head(child: str) -> str:
    return re.match(r"\((\w+)", child).group(1)


def prop(child: str, name: str) -> str:
    m = re.search(r'\(property "' + re.escape(name) + r'" "((?:[^"\\]|\\.)*)"', child)
    return m.group(1) if m else ""


PAD_RE = re.compile(r'\n\t\t\(pad "([^"]*)" (\w+).*?\n\t\t\)', re.S)


def pads(fp: str):
    """Yield (pad_number, pad_type, net_name) for each pad in a footprint."""
    for m in PAD_RE.finditer(fp):
        net = NET_RE.search(m.group(0))
        yield m.group(1), m.group(2), (net.group(1) if net else "")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", type=Path, required=True)
    ap.add_argument("--block", choices=sorted(PREFIX), required=True)
    ap.add_argument("--source-manifest", type=Path, required=True)
    ap.add_argument("--out-board", type=Path, required=True)
    ap.add_argument("--mapping-report", type=Path, required=True)
    ap.add_argument("--drop-footprint", action="append", default=[],
                    help="unit instance name to delete (negative controls only)")
    ap.add_argument("--swap-pad-net", action="append", default=[],
                    help="UNIT_INSTANCE:PAD:UNIT_NET - move one pad to another "
                         "unit net after mapping (negative controls only)")
    args = ap.parse_args()

    prefix, strip = PREFIX[args.block], STRIP[args.block]
    manifest = json.loads(args.source_manifest.read_text())
    ref_to_inst = {c["reference"]: c["instance_path"] for c in manifest["bridge"]["components"]}
    pin_to_pad = {(p["instance_path"], p["pin"]): str(p["pad"]) for p in manifest["strict_pin_map"]}
    unit_instances = sorted(ref_to_inst.values())

    children = split_top(args.board.read_text(encoding="utf-8"))

    def unit_name(inst: str) -> str:
        return inst[len(prefix):] if strip else inst

    footprints = {}
    for ch in children:
        if head(ch) == "footprint":
            inst = prop(ch, "SourceInstance")
            if inst.startswith(prefix):
                footprints[unit_name(inst)] = ch
    for drop in args.drop_footprint:
        footprints.pop(drop)
    absent = sorted(set(unit_instances) - set(footprints))
    extra = sorted(set(footprints) - set(unit_instances))

    pad_net = {}
    for inst, fp in footprints.items():
        for number, _kind, net in pads(fp):
            pad_net.setdefault((inst, number), net)
    ctrl_to_unit: dict[str, set[str]] = {}
    unit_to_ctrl: dict[str, set[str]] = {}
    for net in manifest["bridge"]["nets"]:
        for ref, pin in net["nodes"]:
            inst = ref_to_inst[ref]
            if inst not in footprints:
                continue
            ctrl = pad_net.get((inst, pin_to_pad[(inst, pin)]), "")
            if ctrl:
                ctrl_to_unit.setdefault(ctrl, set()).add(net["name"])
                unit_to_ctrl.setdefault(net["name"], set()).add(ctrl)
    conflicts = []
    for unit, ctrls in sorted(unit_to_ctrl.items()):
        if len(ctrls) > 1:
            conflicts.append({"kind": "unit net on several controller nets",
                              "unit_net": unit, "controller_nets": sorted(ctrls)})
    for ctrl, units in sorted(ctrl_to_unit.items()):
        if len(units) > 1:
            conflicts.append({"kind": "several unit nets on one controller net",
                              "controller_net": ctrl, "unit_nets": sorted(units)})
    # pad-level equivalence with the unit's compiled netlist (independent of the Rust
    # validators): every unit (instance, pad) on a present instance must carry a
    # controller net that maps to its unit net, and no other pad may carry a net.
    unit_pad_net = {}
    for net in manifest["bridge"]["nets"]:
        for ref, pin in net["nodes"]:
            inst = ref_to_inst[ref]
            if inst in footprints:
                unit_pad_net[(inst, pin_to_pad[(inst, pin)])] = net["name"]
    controller_unit_name = {c: sorted(u)[0] for c, u in ctrl_to_unit.items() if len(u) == 1}
    pad_mismatch = {
        "unit_pad_missing_or_on_other_net": sorted(
            f"{i}.{p}" for (i, p), un in unit_pad_net.items()
            if controller_unit_name.get(pad_net.get((i, p), "")) != un),
        "controller_pad_connected_but_not_in_unit_netlist": sorted(
            f"{i}.{p}" for (i, p), cn in pad_net.items() if cn and (i, p) not in unit_pad_net),
        "pads_compared": len(unit_pad_net),
    }
    rename = {c: sorted(u)[0] for c, u in ctrl_to_unit.items()
              if len(u) == 1 and len(unit_to_ctrl[sorted(u)[0]]) == 1}
    kept_pad_nets = {net for fp in footprints.values() for _n, _k, net in pads(fp) if net}
    unmapped = sorted(kept_pad_nets - set(rename))
    block_nets = set(rename) | kept_pad_nets
    collisions = sorted(u for c, u in rename.items()
                        if u != c and u in block_nets and u not in rename)

    def rename_nets(s: str) -> str:
        return NET_RE.sub(lambda m: '(net "%s")' % rename.get(m.group(1), m.group(1)), s)

    out = []
    dropped = {"footprint": 0, "segment": 0, "via": 0, "zone": 0, "graphics": 0}
    for ch in children:
        h = head(ch)
        if h == "footprint":
            full = prop(ch, "SourceInstance")
            if full.startswith(prefix) and unit_name(full) in footprints:
                ch = ch.replace('(property "SourceInstance" "%s"' % full,
                                '(property "SourceInstance" "%s"' % unit_name(full), 1)
                out.append(rename_nets(ch))
            else:
                dropped["footprint"] += 1
        elif h in ("segment", "via", "zone"):
            m = NET_RE.search(ch)
            if m and m.group(1) in block_nets:
                out.append(rename_nets(ch))
            else:
                dropped[h] += 1
        elif h.startswith("gr_") or h in ("dimension", "group", "target", "generated"):
            if '(layer "Edge.Cuts")' in ch:
                out.append(ch)
            else:
                dropped["graphics"] += 1
        else:
            out.append(ch)

    for spec in args.swap_pad_net:
        inst, pad_no, net = spec.split(":", 2)
        for k, ch in enumerate(out):
            if head(ch) == "footprint" and prop(ch, "SourceInstance") == inst:
                pm = next(m for m in PAD_RE.finditer(ch) if m.group(1) == pad_no)
                new_pad = NET_RE.sub('(net "%s")' % net, pm.group(0), count=1)
                out[k] = ch.replace(pm.group(0), new_pad, 1)

    result = "(kicad_pcb\n\t" + "\n\t".join(out) + "\n)\n"
    args.out_board.write_text(result, encoding="utf-8")
    report = {
        "block": args.block,
        "controller_board": str(args.board),
        "unit_source_manifest": str(args.source_manifest),
        "unit_census": len(unit_instances),
        "controller_census": len(footprints),
        "absent_unit_instances": absent,
        "extra_controller_instances": extra,
        "net_map_controller_to_unit": dict(sorted(rename.items())),
        "net_map_conflicts": conflicts,
        "pad_net_equivalence_with_unit_netlist": pad_mismatch,
        "unit_name_collisions_with_unmapped_controller_nets": collisions,
        "unmapped_controller_nets_on_kept_pads": unmapped,
        "dropped_items": dropped,
        "negative_control": {"drop": args.drop_footprint, "swap": args.swap_pad_net},
    }
    args.mapping_report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({k: report[k] for k in ("block", "unit_census", "controller_census",
                                             "absent_unit_instances", "net_map_conflicts",
                                             "unmapped_controller_nets_on_kept_pads")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
