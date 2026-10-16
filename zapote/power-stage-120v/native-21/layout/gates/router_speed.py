#!/usr/bin/env python3
"""Router speed harness: time incr21 on router_bench inputs and require byte-identical copper.

    python3 native-21/layout/gates/router_speed.py baseline INPUTS REF          # once, on the reference code
    python3 native-21/layout/gates/router_speed.py check INPUTS REF [--seeds 23,29] [--repeat N] [--out DIR]

INPUTS holds router_bench output dirs (sN/ripped.json, sN/r0/drc.json: the ripped board and its open pairs). Each
seed runs `INCR21_FROZEN=1 incr21.py ripped.json r0/drc.json OUT.json` from this unit, one at a time (timing). baseline
writes REF/sN.json (the copper), REF/sN.log (incr21's summary lines) and REF/times.json, after one untimed warm-up run
(numba compiles its cached A* core on the first). check runs the same and fails unless every seed's copper is
byte-identical to REF and its summary lines match; it prints per-seed seconds (the minimum of --repeat runs) against
the baseline's. A speedup counts only with identical copper: the router's output is what the gates have accepted.
No KiCad needed: incr21 is Python (shapely, numpy, scipy; numba optional).
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

U = Path(__file__).resolve().parents[3]          # zapote/power-stage-120v
INCR21 = U / "native-21" / "layout" / "incr21.py"
SUMMARY = re.compile(r"^(rip-up:|base kept,|  open )")


def seeds_in(inputs, only):
    found = sorted(int(p.name[1:]) for p in Path(inputs).glob("s*") if (p / "ripped.json").exists()
                   and (p / "r0" / "drc.json").exists())
    if only:
        want = [int(s) for s in only.split(",")]
        missing = set(want) - set(found)
        if missing:
            sys.exit(f"router_speed: no inputs for seeds {sorted(missing)} in {inputs}")
        return want
    return found


def run(inputs, seed, out):
    d = Path(inputs) / f"s{seed}"
    env = dict(os.environ, INCR21_FROZEN="1")
    t = time.perf_counter()
    r = subprocess.run([sys.executable, str(INCR21), str(d / "ripped.json"), str(d / "r0" / "drc.json"), str(out)],
                       cwd=U, env=env, capture_output=True, text=True)
    dt = time.perf_counter() - t
    if r.returncode != 0:
        sys.exit(f"router_speed: seed {seed} failed (exit {r.returncode}):\n{r.stdout[-2000:]}\n{r.stderr[-4000:]}")
    return dt, "\n".join(ln for ln in r.stdout.splitlines() if SUMMARY.match(ln)) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=("baseline", "check"))
    ap.add_argument("inputs")
    ap.add_argument("ref")
    ap.add_argument("--seeds", help="comma-separated subset (default: every seed in INPUTS)")
    ap.add_argument("--repeat", type=int, default=1, help="runs per seed; the minimum time counts")
    ap.add_argument("--out", help="where check writes its copper (default: a temp dir under REF's parent)")
    a = ap.parse_args()
    ref = Path(a.ref).resolve()
    seeds = seeds_in(a.inputs, a.seeds)
    if a.mode == "baseline":
        ref.mkdir(parents=True, exist_ok=True)
        run(a.inputs, seeds[0], ref / "warmup.json")
        (ref / "warmup.json").unlink()
        times = {}
        for s in seeds:
            best = None
            for _ in range(a.repeat):
                dt, summary = run(a.inputs, s, ref / f"s{s}.json")
                best = dt if best is None else min(best, dt)
            times[s] = round(best, 2)
            (ref / f"s{s}.log").write_text(summary)
            print(f"seed {s}: {best:7.2f} s  {summary.splitlines()[-1] if summary.strip() else ''}", flush=True)
        (ref / "times.json").write_text(json.dumps(times, indent=1) + "\n")
        print(f"baseline total {sum(times.values()):.2f} s over {len(times)} seeds -> {ref}")
        return
    base = {int(k): v for k, v in json.loads((ref / "times.json").read_text()).items()}
    out = Path(a.out).resolve() if a.out else ref.parent / f"check-{os.getpid()}"
    out.mkdir(parents=True, exist_ok=True)
    bad, tot, tot0 = [], 0.0, 0.0
    for s in seeds:
        best, summary = None, None
        for _ in range(a.repeat):
            dt, summary = run(a.inputs, s, out / f"s{s}.json")
            best = dt if best is None else min(best, dt)
        same = (out / f"s{s}.json").read_bytes() == (ref / f"s{s}.json").read_bytes()
        same_log = summary == (ref / f"s{s}.log").read_text()
        if not (same and same_log):
            bad.append(s)
        tot, tot0 = tot + best, tot0 + base[s]
        print(f"seed {s}: {best:7.2f} s (baseline {base[s]:7.2f} s, x{base[s] / best:4.2f})  copper "
              f"{'identical' if same else 'DIFFERS'}, summary {'same' if same_log else 'DIFFERS'}", flush=True)
    print(f"total {tot:.2f} s against {tot0:.2f} s (x{tot0 / tot:.2f}); "
          f"{'IDENTICAL on every seed' if not bad else f'FAIL: seeds {bad} differ'}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
