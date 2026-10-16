#!/usr/bin/env python3
"""Control: the snapshot's run_basis.one re-solves c28_h10@55 at 0.5 mm; compare with the chain's run file (PS runs/)."""
import json, sys
from pathlib import Path
sys.dont_write_bytecode = True
SNAP = Path("/Users/bennet/Desktop/temper/worktrees/runs-native21/airflow28/snap")
R5 = SNAP / "zapote/power-stage-120v/validation-results/04-board-current-thermal/round5-native21"
sys.path[:0] = [str(R5 / "b3-convergence"), str(R5 / "b3-ratings")]
import run_basis as rb
out = Path("/Users/bennet/Desktop/temper/worktrees/runs-native21/airflow28/runs/control")
rb.one(("c28_h10_p0p5", "c28_h10", 28.0, 10, 55.0, 0.5, str(out), {}, (), rb.tb.ALPHA_CU))
a = json.loads((out / "c28_h10_p0p5.json").read_text())
b = json.loads(Path("/Users/bennet/Desktop/temper/worktrees/runs-native21/airflow28/ps-basis/c28_h10_p0p5.json").read_text())
d = max(abs(p["tj_c"] - q["tj_c"]) for p, q in zip(a["parts"], b["parts"]))
print("board", a["board_sha256"] == b["board_sha256"], "peak", a["peak_1mm_block"]["temperature_c"], b["peak_1mm_block"]["temperature_c"],
      "max part tj diff", d, "fet_row", a["fet_row_max_c"], b["fet_row_max_c"])
