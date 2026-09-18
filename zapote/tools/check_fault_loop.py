#!/usr/bin/env python3
"""Fault-loop consistency check.

Rejects a discharge model that assigns current (or energy) to an element that
cannot conduct in the declared loop.

Motivating error: an AR-FAULT discharge model put energy into the current-sense
shunt U12, but the retained netlist shows U12 sits between `PFC_BUS_MINUS` and
the bridge return (`minus`), while the internal capacitor-discharge loop is
capacitors -> shorted U10 -> U9 -> capacitors. The loop never crosses the shunt,
so any current assigned to it is a wiring error, not a small error.

Rule: an element can carry current in a loop only when **at least two of its
terminals** are on that loop's nets. A two-terminal element needs both; a
three-terminal device such as a MOSFET qualifies on its two power terminals even
though its gate is on a control net.

Usage:
  check_fault_loop.py --netlist <netlist.json> --loop-nets A,B,C \
                      --assignments <assignments.json>

The netlist file is a map of net name -> {"nodes": [[ref, pin], ...]} (the shape
the campaign's `netlist_fault_loop.json` uses). The assignments file is a map of
element reference -> number (energy in J, or current in A). Zero means "not in
this loop" and is ignored.

Exit 0 when every non-zero assignment is loop-consistent, 1 when any is not,
2 on usage error.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys


def element_nets(netlist: dict) -> dict[str, set[str]]:
    """ref -> set of net names its terminals sit on."""
    membership: dict[str, set[str]] = {}
    evidence = netlist.get("netlist_evidence", netlist)
    for net, info in evidence.items():
        for ref, _pin in info["nodes"]:
            membership.setdefault(ref, set()).add(net)
    return membership


def terminals_on_loop(nets: set[str], loop: set[str]) -> int:
    return len(nets & loop)


def check(netlist: dict, loop_nets: set[str], assignments: dict[str, float]) -> list[str]:
    membership = element_nets(netlist)
    failures: list[str] = []
    for ref, value in assignments.items():
        if not value:
            continue
        nets = membership.get(ref)
        if nets is None:
            failures.append(f"{ref} carries {value} but has no terminals in the netlist evidence")
            continue
        on_loop = terminals_on_loop(nets, loop_nets)
        if on_loop < 2:
            failures.append(
                f"{ref} carries {value} but only {on_loop} of its terminals "
                f"{sorted(nets)} lie on the declared loop {sorted(loop_nets)}"
            )
    return failures


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--netlist", type=pathlib.Path, required=True)
    parser.add_argument("--loop-nets", required=True, help="comma-separated loop net names")
    parser.add_argument("--assignments", type=pathlib.Path, required=True)
    args = parser.parse_args(argv)

    netlist = json.loads(args.netlist.read_text())
    assignments = json.loads(args.assignments.read_text())
    loop_nets = {n.strip() for n in args.loop_nets.split(",") if n.strip()}
    if not loop_nets:
        print("no loop nets given", file=sys.stderr)
        return 2

    failures = check(netlist, loop_nets, assignments)
    if failures:
        print("FAULT LOOP INCONSISTENT")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("FAULT LOOP CONSISTENT")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
