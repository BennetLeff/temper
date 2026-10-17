#!/usr/bin/env python3
"""Router benchmark: rip seeded signal nets out of the accepted copper and let incr21 join them again.

    python3 native-21/layout/gates/router_bench.py OUTDIR [--seed 7] [--nets 12] [--min-tracks 2] [--max-tracks 12]

1. snapshot native-21/layout/copper.json (OUTDIR/accepted.json) and pick --nets nets at random (--seed) among the
   signal nets with --min-tracks..--max-tracks tracks: not incr21's WIDE nets, not a pour's net, no supply / power /
   switching name;
2. drop their tracks and vias (OUTDIR/ripped.json) and build it (OUTDIR/r0): the open pairs;
3. route them, frozen base (INCR21_FROZEN), and build (OUTDIR/r1);
4. report OUTDIR/bench.json: open pairs before / after, what incr21 says it left open, KiCad errors added by type
   (r1 against r0), the plan-view barrier line, copper re-added against ripped, and the per-step times (laps).
   Open pairs of a net whose accepted copper enters another net's protected pour (gates/protected_cross.py: a patch
   authored it on purpose; the router may not) count as "policy", the rest as router failures.
Test points stay off both builds (BOARD_ONLY21_NO_TEST_POINTS): they sit on the old copper of their net. Both builds
check with the inner-loop rules (DRC_FAST, gates/drc_rules_fast.py) unless --full-drc.
copper.json and reference-labels.json are rewritten by the builds and restored from snapshots at the end, also on
failure. It is one writer of
the layout files, like passes.sh and chain.sh: never run it beside them in the same worktree.
"""
import argparse
import collections
import json
import os
import random
import re
import shutil
import subprocess
import sys
from pathlib import Path

U = Path(__file__).resolve().parents[3]          # zapote/power-stage-120v
L = U / "native-21" / "layout"
POWERISH = re.compile(r"gnd|pe|hot|v\d|vcc|vdd|bus|rect|sw_|leg|coil|res_a|tank|l_|n_", re.I)


def wide_nets():
    src = (L / "incr21.py").read_text()
    body = re.search(r"WIDE = \((.*?)\)\n", src, re.S).group(1)
    return set(re.findall(r'"([^"]+)"', body))


def pick_nets(copper, n, seed, lo, hi):
    per_net = collections.Counter(t["net"] for t in copper["tracks"])
    pour = {z.get("net") for z in copper["zones"]}
    wide = wide_nets()
    cand = sorted(x for x, c in per_net.items()
                  if lo <= c <= hi and x not in wide and x not in pour and not POWERISH.search(x))
    if len(cand) < n:
        sys.exit(f"router_bench: only {len(cand)} candidate nets for --nets {n}")
    return random.Random(seed).sample(cand, n), len(cand), per_net


def build(base, drc_in, out, frozen, fast, settle=0):
    env = dict(os.environ, BOARD_ONLY21_NO_TEST_POINTS="1", INCR21_SETTLE=str(settle))
    env.pop("DRC_FAST", None)
    if fast:
        env["DRC_FAST"] = "1"
    env.pop("INCR21_FROZEN", None)
    if frozen:
        env["INCR21_FROZEN"] = "1"
    log = Path(f"{out}.log")
    with open(log, "w") as fh:
        rc = subprocess.call(["sh", "native-21/layout/incr_iter.sh", str(base), str(drc_in), str(out)],
                             cwd=U, stdout=fh, stderr=subprocess.STDOUT, env=env)
    if rc != 0:
        sys.exit(f"router_bench: build {out} failed (exit {rc}); see {log}")
    return log.read_text()


def errors(drc_path):
    d = json.loads(Path(drc_path).read_text())
    return collections.Counter(v["type"] for v in d["violations"] if v["severity"] == "error"), len(d.get("unconnected_items", []))


def open_split(drc_path, out, nets):
    """Open pairs after routing: (policy, router). Policy: the pair's net is a ripped net whose accepted copper
    enters another net's protected pour (protected_cross.py)."""
    pairs = json.loads(Path(drc_path).read_text()).get("unconnected_items", [])
    pnet = [re.search(r"\[([^\]]*)\]", v["items"][0]["description"]).group(1) for v in pairs]
    ask = sorted({n for n in pnet if n in nets})
    flagged = {}
    if ask:
        r = subprocess.run([sys.executable, str(L / "gates" / "protected_cross.py"), str(out / "ripped.json"),
                            str(out / "accepted.json"), *ask], cwd=U, capture_output=True, text=True, check=True)
        flagged = json.loads(r.stdout.strip().splitlines()[-1])
    policy = [n for n in pnet if n in flagged]
    return {"policy": policy, "router": [n for n in pnet if n not in flagged], "protected_cross": flagged}


def laps(out):
    p = Path(out) / "steps.jsonl"
    rows = [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []
    return {r["step"]: r["s"] for r in rows}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("outdir")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--nets", type=int, default=12)
    ap.add_argument("--min-tracks", type=int, default=2)
    ap.add_argument("--max-tracks", type=int, default=12)
    ap.add_argument("--full-drc", action="store_true", help="check with every rule (default: DRC_FAST)")
    ap.add_argument("--settle", type=int, default=0, help="pour-cut repair rounds (incr_iter INCR21_SETTLE; default 0: off)")
    a = ap.parse_args()
    out = Path(a.outdir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    live = L / "copper.json"
    accepted = out / "accepted.json"
    shutil.copyfile(live, accepted)
    labels = U / "native-21" / "reference-labels.json"
    labels_snap = out / "reference-labels.json"
    shutil.copyfile(labels, labels_snap)
    try:
        copper = json.loads(accepted.read_text())
        nets, ncand, per_net = pick_nets(copper, a.nets, a.seed, a.min_tracks, a.max_tracks)
        ripped = dict(copper)
        ripped["tracks"] = [t for t in copper["tracks"] if t["net"] not in nets]
        ripped["vias"] = [v for v in copper["vias"] if v.get("net") not in nets]
        (out / "ripped.json").write_text(json.dumps(ripped))
        for d in ("r0", "r1"):
            shutil.rmtree(out / d, ignore_errors=True)
        build(out / "ripped.json", "-", out / "r0", frozen=False, fast=not a.full_drc)
        log1 = build(out / "ripped.json", out / "r0" / "drc.json", out / "r1", frozen=True, fast=not a.full_drc,
                     settle=a.settle)
        routed = json.loads(live.read_text())
    finally:
        shutil.copyfile(accepted, live)
        shutil.copyfile(labels_snap, labels)
    e0, open0 = errors(out / "r0" / "drc.json")
    e1, open1 = errors(out / "r1" / "drc.json")
    tried = re.search(r"(\d+) open pairs tried, (\d+) still open", log1)
    settles = [int(n) for n in re.findall(r"^fast_conn: (\d+) unconnected", log1, re.M)]
    barrier = (out / "r1" / "barrier.txt").read_text().splitlines()[0]
    st = laps(out / "r1")
    rep = {
        "seed": a.seed, "drc": "full" if a.full_drc else "fast", "settle": a.settle, "nets": nets, "candidates": ncand,
        "ripped": {"tracks": sum(per_net[n] for n in nets),
                   "vias": len(copper["vias"]) - len(ripped["vias"])},
        "readded": {"tracks": len(routed["tracks"]) - len(ripped["tracks"]),
                    "vias": len(routed["vias"]) - len(ripped["vias"])},
        "open_before": open0, "open_after": open1, "open_split": open_split(out / "r1" / "drc.json", out, set(nets)),
        "incr21": {"tried": int(tried.group(1)), "still_open": int(tried.group(2))} if tried else None,
        "settle_open": settles,
        "errors_before": dict(e0), "errors_after": dict(e1), "errors_added": dict(e1 - e0),
        "barrier": barrier,
        "barrier_clean": bool(re.search(r": 0 violations;.*: 0 violations", barrier)),
        "seconds": {"router": st.get("incr21"), "build_r1": round(sum(st.values()), 1),
                    "kicad_drc_r1": st.get("kicad_drc"),
                    "settle": round(sum(v for k, v in st.items() if k.startswith("settle")), 1)},
    }
    (out / "bench.json").write_text(json.dumps(rep, indent=1) + "\n")
    s = rep["seconds"]
    print(f"router_bench seed {a.seed}: {len(nets)} nets ({rep['ripped']['tracks']} tracks, {rep['ripped']['vias']} vias) "
          f"-> open {open0} -> {open1} (router {len(rep['open_split']['router'])}, policy {len(rep['open_split']['policy'])}); errors added {rep['errors_added'] or 0}; barrier {'clean' if rep['barrier_clean'] else 'VIOLATED'}; "
          f"router {s['router']} s, settle {s['settle']} s {settles}, build {s['build_r1']} s (DRC {s['kicad_drc_r1']} s)")


if __name__ == "__main__":
    main()
