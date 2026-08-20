"""Prove the DRU pair-figure raise is MONOTONE: no pair's separation decreased.

The netclass auto-constraint family is the only separation family live on
every production solve. Re-sourcing its figures from
`netclass_rules.yaml`'s `class_pairs` (capped at an explicitly-unsourced
6.0mm) onto the DRU-resolved projections is a safety change, so the property
that actually needs proving is not "the HV pairs went up" but "NOTHING went
down" -- the DRU is deliberately looser than `class_pairs` on some
same-domain pairs (ACMains|HighVoltage: 3.0mm vs 6.0mm), and a naive
substitution would have silently weakened those.

Baseline is the function's DEFAULT (`dru_resolved_pairs=False`), which is
byte-identical to the pinned pre-Rust-port oracle
(`tests/pcl/_netclass_constraints_py_oracle.py`) -- i.e. exactly what every
production solve encoded before this change.

FAILS CLOSED: exits non-zero if any pair is lowered, or if the pair SET
changes (a raise that also silently dropped constraints would not be a
raise).

Read-only. Usage:

    python docs/evidence/2026-08-19-netclass-dru-raise-monotonicity.py \
           pcb/temper.kicad_pcb
"""

from __future__ import annotations

import collections
import sys
from pathlib import Path

import temper_placer.placer.cp_sat.netclass_constraints as nc
from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.placer.cp_sat._loop_utils import load_netclass_rules

TOL = 1e-9


def main(board_path: Path) -> int:
    netlist = parse_kicad_pcb(board_path).netlist
    design_rules = load_netclass_rules().design_rules

    def figures(**kwargs: object) -> dict[tuple[str, str], float]:
        return {
            (c.a, c.b): c.min_distance_mm
            for c in nc.generate_netclass_separated_constraints(
                netlist, netlist.components, design_rules, **kwargs
            )
        }

    old = figures()                          # pre-change production behaviour
    new = figures(dru_resolved_pairs=True)   # what the encoder now passes

    print(f"components : {len(netlist.components)}")
    print(f"pairs      : {len(old)} before, {len(new)} after")

    if set(old) != set(new):
        only_old = sorted(set(old) - set(new))[:10]
        only_new = sorted(set(new) - set(old))[:10]
        print("FAIL: the constraint pair SET changed, so this is not a pure raise.")
        print(f"  dropped (first 10): {only_old}")
        print(f"  added   (first 10): {only_new}")
        return 1

    lowered = {k: (old[k], new[k]) for k in old if new[k] < old[k] - TOL}
    raised = {k: (old[k], new[k]) for k in old if new[k] > old[k] + TOL}

    print(f"raised     : {len(raised)}")
    transitions = collections.Counter(
        (round(o, 4), round(n, 4)) for o, n in raised.values()
    )
    for (before, after), count in sorted(transitions.items()):
        print(f"    {before:7.4f} -> {after:7.4f} mm : {count}")

    print(f"LOWERED    : {len(lowered)}   (must be 0)")
    if lowered:
        for pair, (before, after) in sorted(lowered.items())[:20]:
            print(f"    {pair}: {before:.4f} -> {after:.4f} mm")
        print("FAIL: WEAKENING DETECTED -- a separation figure went DOWN.")
        return 1

    print("PASS: monotone raise -- every pair is >= its previous figure.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(main(Path(sys.argv[1])))
