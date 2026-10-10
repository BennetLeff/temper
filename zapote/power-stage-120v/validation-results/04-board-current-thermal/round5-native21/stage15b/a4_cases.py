#!/usr/bin/env python3
"""Run the 14 A4 cases that B3's c28 sum uses (18 um plating, run_cases.py pitches) on a candidate's copper.

    python3 a4_cases.py <power_copper.json.gz> <out_dir>   -> <out_dir>/<case>-p<pitch>-pl18.json / -heat.npz
"""
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "model"))
import run_cases as rc  # noqa: E402  (stage15b copy; CASES and FINE unchanged)

copper, out = Path(sys.argv[1]), Path(sys.argv[2])
out.mkdir(parents=True, exist_ok=True)
USED = {"sw_a", "sw_a_low", "sw_b_high", "sw_b_low", "res_a", "coil_feed", "leg_a_18p7", "leg_b_18p7",
        "hv_mixed_a", "hv_mixed_b", "bus_mixed_q2", "bus_mixed_q5", "ac_n_main", "ac_l_main"}
cases = rc.CASES + [('ac_n_main', 'ac_n_in', ['J1.2:15'], [], ['L1.2'], ''), ('ac_l_main', 'ac_l_in', ['J1.1:15'], [], ['F1.1'], '')]
env = {**os.environ, "A4_COPPER": str(copper), "A4_DIR": str(out), "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1"}


def one(c):
    name, net, sources, draws, sinks, _ = c
    pitch = "0.0625" if net in rc.FINE else "0.125"
    label = f"{name}-p{pitch.replace('.', '')}-pl18"
    cmd = [sys.executable, str(HERE / "model/run_board.py"), "--net", net, "--name", label, "--pitch", pitch, "--plating", "18"]
    for s in sources: cmd += ["--source", s]
    for d in draws: cmd += ["--draw", d]
    for s in sinks: cmd += ["--sink", s]
    r = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if r.returncode:
        raise RuntimeError(label + r.stdout + r.stderr[-1500:])
    m = json.loads((out / f"{label}.json").read_text())
    return label, m["r_ohm"], m["loss_w"]


with ThreadPoolExecutor(6) as ex:
    rows = list(ex.map(one, [c for c in cases if c[0] in USED]))
(out / "a4_summary.json").write_text(json.dumps({l: {"r_mohm": r * 1e3, "loss_w": w} for l, r, w in rows}, indent=1) + "\n")
print(" ".join(f"{l.split('-')[0]}:{r*1e3:.3f}mOhm" for l, r, w in rows if l.startswith(("sw_a", "leg_a", "bus_mixed_q2", "hv_mixed_a"))))
