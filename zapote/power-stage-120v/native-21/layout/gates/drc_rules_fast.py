#!/usr/bin/env python3
"""Inner-loop DRC rules: drop the creepage constraints from a BUILD's copy of section.kicad_dru, in place.

    python3 native-21/layout/gates/drc_rules_fast.py BUILDDIR/section.kicad_dru

incr_iter.sh runs it when DRC_FAST is set (passes.sh and router_bench.py set it; chain.sh unsets it). Measured
2026-10-15 on one native-21 board, kicad-cli 10.0.4, no refill: 146 s with every rule, 48 s without the creepage
constraints, 2.1 s with no custom rules at all; the three creepage constraints are about two thirds of the DRC.
Every clearance constraint (functional HOT groups, tank nodes, the component exceptions, SELV/PE-HOT 8.0 mm, RES_A
12.6 mm outer) stays. The creepage groups are the ones barrier21.py checks on every build (both take SELV, PE, the HOT
groups and RES_A from write_rules21 through rules21), in plan view across all layers, and a path along the surface is
never shorter than its plan-view projection, so that check bounds the creepage from below. The full rules still run
on chain.sh's build.
"""
import re
import sys
from pathlib import Path

p = Path(sys.argv[1])
s = p.read_text()
fast, n = re.subn(r"\n\s*\(constraint creepage \(min [0-9.]+mm\)\)", "", s)
if fast.count("(") != fast.count(")"):
    sys.exit(f"drc_rules_fast: unbalanced rules after the edit of {p}")
p.write_text(fast)
print(f"drc fast: {n} creepage constraint(s) off (barrier21 checks the creepage groups in plan view)")
