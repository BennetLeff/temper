#!/usr/bin/env python3
"""Body-level B3 solves (fill-fraction copper + datasheet package networks, the committed stage-19b model) on the
s32 board, for the realistic operating points and the fix sensitivities.

    python3 body_cases.py [--only NAME,...] [--workers 3] [--fresh]

Operating points (copper Joule scaling = run_study.py cases(); part heat = the committed c28 heat file):
  c28   28 A ceiling at its 1.05 x firmware RMS trip (I_t 29.4 A), inlet 11.1 A          (= run_study OPS c28)
  cNN   NN A commissioned ceiling (c22 = the 22 A default), I_t 1.05 x NN, inlet 11.1 A; tank-current rows of the c28
        heat file scaled by (I_t / 29.4)^2 exactly as body_runs.op_inputs('der14') does
  der14 stall derate (h10-stall), I_t 14.7 A                                              (= body_runs der14)
  nominal  run_study OPS nominal (round-3 1710 W at 120 V, line 14.25 A; superseded by the 11.1 A inlet hold)
Fix sensitivities (named '<op>_h<h>_p<pitch>_<fix>'): a4xK scales every copper Joule case by K; part:REF=K scales one
part's heat. Results: ../runs/body/<name>.json. Temperatures are at the model's 50 C ambient; verdict.py shifts them.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from paths import MODEL, RUNS

sys.path.insert(0, str(MODEL))
import body_runs as br  # noqa: E402
import thermal_body as tb  # noqa: E402

OUT = RUNS / "body"
CACHE = RUNS / "cache"
TANK_ROWS = br.TANK_ROWS

_orig_op_inputs = br.op_inputs


def make_op(op: str, a4x: float = 1.0, part_scale: dict | None = None, tag: str = ""):
    """(case string, heat json path, mode) for op with optional copper / part-heat scaling."""
    rs = br.rs
    if op.startswith("c") and op[1:].isdigit() and op != "c28":           # cNN: NN A ceiling at its 1.05 x trip
        ceil = float(op[1:])
        rs.OPS[op] = {"I_t": 1.05 * ceil, "I_line": 11.1, "parts": "nominal", "heat": "c28"}
        case, heat_path, mode = rs.cases(op), rs.HEAT_C28, "nominal"
        heat = json.loads(Path(heat_path).read_text())
        k = (1.05 * ceil / 29.4) ** 2
        for p in heat["parts"]:
            if p["ref"] in TANK_ROWS:
                p["watts_nominal"] *= k
                p["watts_worst"] *= k
    else:
        case, heat_path, mode = _orig_op_inputs(op)
        heat = json.loads(Path(heat_path).read_text())
    if a4x != 1.0:
        case = ",".join(f"{c}:{float(s) * a4x:.6g}" for c, _, s in (it.partition(":") for it in case.split(",")))
    for ref, f in (part_scale or {}).items():
        hit = [p for p in heat["parts"] if p["ref"] == ref]
        if not hit:
            raise KeyError(ref)
        for p in hit:
            p["watts_nominal"] *= f
            p["watts_worst"] *= f
    path = RUNS / "heat" / f"heat_{op}{tag}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(heat))
    return case, path, mode


def tasks():
    t = []
    # mesh study on s32 (global 1.0 / 0.5 / 0.25 mm) for the cases that decide verdicts
    for op, h in (("c28", 10), ("c28", 25), ("c22", 10), ("der14", 10), ("nominal", 10)):
        for p in (1.0, 0.5, 0.25):
            t.append(dict(name=f"{op}_h{h}_p{str(p).replace('.', 'p')}", op=op, h=h, pitch=p))
    # fix sensitivities at 0.5 mm (differences vs the same-mesh baseline; the base mesh error cancels to first order)
    for op in ("c28", "c22"):
        base = dict(op=op, pitch=0.5)
        for h in (15, 20):                                                     # board-face airflow
            t.append(dict(name=f"{op}_h{h}_p0p5", h=h, **base))
        t.append(dict(name=f"{op}_h10_p0p5_a4x0p7", h=10, a4x=0.7, **base))   # copper heat -30 % (~3 oz outer / wider tank paths)
        t.append(dict(name=f"{op}_h10_p0p5_a4x0p5", h=10, a4x=0.5, **base))
        t.append(dict(name=f"{op}_h10_p0p5_R5x0p5", h=10, parts={"R5": 0.5}, **base))   # 0.5 mOhm shunt
        t.append(dict(name=f"{op}_h10_p0p5_modx0p5", h=10, parts={"U41": 0.5, "U42": 0.5}, **base))
        t.append(dict(name=f"{op}_h10_p0p5_ps0p5", h=10, parts={"PS1": 0.5, "PS2": 0.5}, **base))
    # still-air ceiling sweep (0.5 mm): which commissioned ceiling keeps the copper under the laminate MOT
    for ceil in (14, 16, 18, 20):
        t.append(dict(name=f"c{ceil}_h10_p0p5", op=f"c{ceil}", h=10, pitch=0.5))
    return t


def run_one(t):
    out = OUT / f"{t['name']}.json"
    if out.exists() and not t.get("fresh"):
        return t["name"], 0.0
    tag = "_" + t["name"]
    case, heat, mode = make_op(t["op"], t.get("a4x", 1.0), t.get("parts"), tag)
    br.op_inputs = lambda op, _c=case, _h=heat, _m=mode: (_c, _h, _m)
    brd = tb.Board(br.rs.GEOM, CACHE)
    t0 = time.time()
    res = br.run_case(brd, t["op"], t["h"], t["pitch"], "fraction", "network", {}, None, None, True, True, label=t["name"])
    res["task"] = {k: v for k, v in t.items() if k != "fresh"}
    res["board_sha256"] = brd.data["board_sha256"]
    OUT.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=1) + "\n")
    return t["name"], time.time() - t0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--fresh", action="store_true")
    a = ap.parse_args()
    ts = tasks()
    if a.only:
        keep = set(a.only.split(","))
        ts = [t for t in ts if t["name"] in keep]
    for t in ts:
        t["fresh"] = a.fresh
    tb.Board(br.rs.GEOM, CACHE).fine()          # build the 0.0625 mm masks once, before the pool
    with ProcessPoolExecutor(max_workers=max(1, min(a.workers, 4))) as ex:
        for name, s in ex.map(run_one, ts):
            print(f"  {name}: {s:.0f} s", flush=True)


if __name__ == "__main__":
    main()
