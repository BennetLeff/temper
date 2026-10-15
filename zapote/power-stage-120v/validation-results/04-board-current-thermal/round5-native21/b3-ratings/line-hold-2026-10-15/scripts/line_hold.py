#!/usr/bin/env python3
"""B3 ratings basis at a higher inlet (line) current: does the c22 / c28 gate depend on the 11.1 A inlet hold?

    python3 line_hold.py [--i-line 13.5] [--workers 4]   # about 6 min; -> ../margins-line<I>.json

run_basis.py with one change: I_line (the board's line-path current) goes from 11.1 A to --i-line. In the B3 model
that moves exactly three inputs; every tank-current row (R5, R39, the bank, C5 / C6, the hv_mixed / bus_mixed copper
that runs through R5, sw_a / sw_b, the leg copper) is set by I_t and does not move:
  1. the ac_l_main / ac_n_main copper fields: run_study.cases() scales them by (I_line / 15)^2;
  2. L1's row in the c28 heat file (built at 11.1 A by make_heat_sources.C28_SCALE): x (I_line / 11.1)^2;
  3. BR1's share of the heatsink load in fet_case.t_case(): p_BR1 = 2 x 1.05 x 0.9 x I_line.
Solves go to ../../runs/line-hold-<I>/ (gitignored); the gate is the committed b3_ratings_gate.py.
"""
import argparse
import json
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
B3R = HERE.parents[1]
sys.path.insert(0, str(B3R))
import run_basis as rb  # noqa: E402

br, rs, tb, fc = rb.br, rb.br.rs, rb.tb, rb.fet_case
I_LINE_BASE = 11.1


def t_case(ceil, i_line):
    """fet_case.t_case (central corner) with BR1's sink share at i_line instead of 11.1 A."""
    i_t = 29.4 if ceil == 28.0 else 1.05 * ceil
    p_ls = 6.78 * (i_t / 21.47) ** 2 + 0.33
    p = {"HS": p_ls - 0.07, "LS": p_ls}
    p_sink = 2 * p["HS"] + 2 * p["LS"] + 2 * 1.05 * 0.9 * i_line
    t_sink = max(fc.FAN_SINK_SETPOINT_C, fc.INLET_C + fc.R_SA * p_sink)
    return {ref: t_sink + fc.R_PED * p_sink + p[s] * fc.RCS["central"] for ref, s in fc.SIDE.items()}


def inputs(op, i_line, runs):
    i_t = 29.4 if op == "c28" else 1.05 * rb.CEIL[op]
    tag = f"{op}_line"
    rs.OPS[tag] = {"I_t": i_t, "I_line": i_line, "parts": "nominal", "heat": "c28"}
    heat = json.loads(rs.HEAT_C28.read_text())
    k_t, k_l = (i_t / 29.4) ** 2, (i_line / I_LINE_BASE) ** 2
    for p in heat["parts"]:
        k = k_t if p["ref"] in br.TANK_ROWS else k_l if p["ref"] == "L1" else 1.0
        p["watts_nominal"] *= k
        p["watts_worst"] *= k
    path = runs / f"heat_{tag}.json"
    path.write_text(json.dumps(heat))
    return rs.cases(tag), path, "nominal"


def one(job):
    name, op, h, pitch, i_line, runs = job
    c = inputs(op, i_line, runs)
    br.op_inputs = lambda _op, _c=c: _c
    brd = tb.Board(rs.GEOM, rb.RUNS / "cache")
    # the base check: at 11.1 A this function must give fet_case.t_case() exactly (fet_case takes i_line since the basis
    # moved to 13.5 A; its default is now run_study.I_LINE_A)
    assert all(abs(a - b) < 1e-9 for a, b in zip(t_case(rb.CEIL[op], I_LINE_BASE).values(),
                                                 fc.t_case(rb.CEIL[op], i_line=I_LINE_BASE).values()))
    leads = {"pad": "2", "g": rb.LEAD_G, "t_rise": {r: t - rb.BAY_C for r, t in t_case(rb.CEIL[op], i_line).items()}}
    res = br.run_case(brd, op, h, pitch, "fraction", "network", {}, None, None, True, True, label=name, leads=leads)
    res["board_sha256"] = brd.data["board_sha256"]
    res["i_line_a"] = i_line
    (runs / f"{name}.json").write_text(json.dumps(res, indent=1) + "\n")
    return name


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--i-line", type=float, default=13.5)
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    sys.path.insert(0, str(B3R.parent))
    import a4_fields
    if not a4_fields.check():
        raise SystemExit(2)
    tag = f"{a.i_line:g}".replace(".", "p")
    runs = rb.RUNS / f"line-hold-{tag}"
    runs.mkdir(parents=True, exist_ok=True)
    tb.Board(rs.GEOM, rb.RUNS / "cache").fine()
    jobs = [(f"{c}_p{str(p).replace('.', 'p')}", op, h, p, a.i_line, runs) for c, (op, h) in rb.CASES.items()
            for p in (0.25, 0.5)]
    with ProcessPoolExecutor(max_workers=min(a.workers, 4)) as ex:
        for n in ex.map(one, jobs):
            print("  solved", n, flush=True)
    r = subprocess.run([sys.executable, str(B3R / "b3_ratings_gate.py"), "--runs", str(runs),
                        "--out", str(HERE.parent / f"margins-line{tag}.json"), "--bay-c", str(rb.BAY_C)])
    raise SystemExit(r.returncode)


if __name__ == "__main__":
    main()
