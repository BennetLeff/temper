"""Summarise the step timings (steps.jsonl, written by laps.sh) of chain / passes / incr_iter / regate runs.

    python3 gates/laps.py BUILDDIR_OR_OUTROOT_OR_FILE... [--root ROOT]

Per script (chain, chain/fit, ..., incr_iter, regate/core, ...): runs, mean wall time per run, and each step's
count, mean and total seconds and share of that script's time, slowest first. Steps of one script run are sequential,
so they sum to that run's wall time; the chain/* parallel blocks overlap regate/core and each other, and
chain's wait_blocks is the critical path through them.
"""
import argparse, collections, glob, json, os, statistics


def load(paths):
    rows = []
    for p in paths:
        files = sorted(glob.glob(os.path.join(p, "**", "steps.jsonl"), recursive=True)) if os.path.isdir(p) else [p]
        for f in files:
            with open(f) as fh:
                rows += [json.loads(line) for line in fh if line.strip()]
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--root", help="only laps under this outermost run (the 'root' field)")
    a = ap.parse_args()
    rows = [r for r in load(a.paths) if not a.root or r["root"] == a.root]
    if not rows:
        raise SystemExit("no laps found")
    by_script = collections.defaultdict(list)
    for r in rows:
        by_script[r["script"]].append(r)
    roots = sorted({r["root"] for r in rows})
    print(f"{len(rows)} laps, {len(roots)} root run(s): {', '.join(roots[-3:])}{' ...' if len(roots) > 3 else ''}")
    for script, rs in sorted(by_script.items(), key=lambda kv: -sum(r["s"] for r in kv[1])):
        runs = collections.Counter(r["run"] for r in rs)
        total = sum(r["s"] for r in rs)
        print(f"\n{script}: {len(runs)} run(s), {total / len(runs):.1f} s per run")
        steps = collections.defaultdict(list)
        for r in rs:
            steps[r["step"]].append(r["s"])
        for step, s in sorted(steps.items(), key=lambda kv: -sum(kv[1])):
            print(f"  {step:34} n={len(s):<3} mean {statistics.mean(s):8.2f} s  total {sum(s):9.1f} s  {sum(s) / total:6.1%}")


if __name__ == "__main__":
    main()
