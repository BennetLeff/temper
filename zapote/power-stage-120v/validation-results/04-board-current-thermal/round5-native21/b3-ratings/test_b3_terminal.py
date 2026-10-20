#!/usr/bin/env python3
"""Tests for the B3 gate's mains-terminal clamp row (OPEN-ITEMS S21, 11-candidates/c54-j1-thermal). No board solves.

    python3 validation-results/04-board-current-thermal/round5-native21/b3-ratings/test_b3_terminal.py
"""
import sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import b3_ratings_gate as gate  # noqa: E402

fails = 0


def ok(cond, msg):
    global fails
    print(("ok   " if cond else "FAIL ") + msg)
    fails += 0 if cond else 1


def run(q25, q05, nets=("ac_l_in", "ac_n_in")):
    return ({"probes": {"J1": {"pad_max_cell_c": q25, "nets": list(nets)}}},
            {"probes": {"J1": {"pad_max_cell_c": q05, "nets": list(nets)}}})


BOM = {"J1": "1714971"}
# the s53 board of record's release-case J1 probe (b3-ratings/runs c17.5_h10, board 82af7bd9): c54 j1_thermal.py gives
# pad 99.03 C and a grid-maximum clamp of 98.8 C (results/j1_thermal.json release_14awg_13p5A.high)
r25, r05 = run(87.18773594617198, 86.90833844108334)
row = gate.terminal_rows("c17.5_h10", r25, r05, 61.0, 13.5, mpns=BOM)[0]
ok(row["gated"] and row["limit_c"] == 105.0, "J1 is a gated 105 C row")
ok(abs(row["pad_c"] - 99.0) < 0.05 and abs(row["est_c"] - 98.8) < 0.05,
   f"s53 release case: pad {row['pad_c']:.2f} C, clamp {row['est_c']:.2f} C = c54 high bound 98.8 C")
hot = gate.terminal_rows("c", r25, r05, 61.0, 15.0, mpns=BOM)[0]
ok(hot["est_c"] > row["est_c"], f"more line current, hotter clamp ({hot['est_c']:.2f} > {row['est_c']:.2f} C)")
cool = gate.terminal_rows("c", *run(77.0, 77.0), 61.0, 13.5, mpns=BOM)[0]
ok(cool["est_c"] > cool["pad_c"], f"a cooler pad: the clamp's own heat and the lead now sit above it "
   f"({cool['est_c']:.2f} > {cool['pad_c']:.2f} C)")
p_mid = {k: sum(v) / 2 for k, v in gate.TERM_GRID.items()}
ok(all(gate.terminal_clamp_c(99.0, 61.0, 13.5, {**p_mid, k: v[0]}) <= row["est_c"] + 1e-9 and
       gate.terminal_clamp_c(99.0, 61.0, 13.5, {**p_mid, k: v[1]}) <= row["est_c"] + 1e-9
       for k, v in gate.TERM_GRID.items()), "no one-at-a-time grid point exceeds the row")
for name, args, kw in (("another terminal MPN on the BOM", run(87.0, 87.0), {"mpns": {"J1": "1711725"}}),
                       ("J1 moved off the mains nets", run(87.0, 87.0, ("ac_l_in", "l_f")), {"mpns": BOM}),
                       ("run files without probes", ({}, {}), {"mpns": BOM})):
    try:
        gate.terminal_rows("c", *args, 61.0, 13.5, **kw)
        ok(False, f"terminal rows refuse: {name}")
    except SystemExit:
        ok(True, f"terminal rows refuse: {name}")
print(f"\n{fails} failure(s)")
raise SystemExit(1 if fails else 0)
