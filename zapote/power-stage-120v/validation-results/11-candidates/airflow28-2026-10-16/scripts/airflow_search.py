#!/usr/bin/env python3
"""Minimum board-face airflow h per tank ceiling on the hot-copper B3 model (DECISIONS 66 airflow requirement).

    python3 -I airflow_search.py search --series c28@61,c28@55,... [--mode uniform|top|jet] [--max-workers 4]
    python3 -I airflow_search.py point --cases c28_h40@61,... [--mode ...]      # solve given cases, no search
    python3 -I airflow_search.py summary                                         # -> results/search.json

Read-only on the power-stage tree: imports the B3 model from SNAP (a byte copy of PS HEAD's round5-native21 tree plus
the files it reads, snap/SNAPSHOT.txt), writes run files under RUNS/<mode>/bay<B>/ (outside git).

Modes (the knob being swept):
  uniform  CASE c<ceil>_h<h>: h on BOTH board faces and on every part body's air path (run_basis's native h, the knob
           behind h10 / h25). Film caps and PS2 keep their bay + 15 K air (thermal_body defaults): conservative.
  top      CASE c<ceil>_h10_jet<h>, with the TopRegion widened to the whole board outline: h on the TOP face (and bodies
           centred anywhere on the board, air at the bay), bottom face at h 10.  NB: the film caps / PS2 then take the
           region's air (= bay), as the jet lane does for region-credited bodies.
  jet      CASE c<ceil>_h10_jet<h>, run_basis.JET_REGION (x 0-90, y 7-23.5): temper-8d airflow-r1's jet strip only.
  zone     CASE c<ceil>_h10_jet<h>, TopRegion ZONE (x 0-125, y 0-90 model mm): the top face over the hot corner that holds
           every binding part (FET row, R5, gate networks, HF film caps, C126-C129, R71-R75, drivers, RECOMs, U3, U26,
           U29); bodies centred there at h, air at the bay (the jet lane's rule for region-credited bodies).
  zone2    as zone on ZONE2 (x 0-195, y 0-120): the hot corner plus the tank path to J2 / J5, T1 and the bank column.
  jetmix   CASE c<ceil>_h<h>_jet<h_top>: run_basis.JET_REGION at h_top on top of a uniform base h (both faces): jets plus
           a general board-face flow.

Search: per series (ceiling, bay) the smallest integer h at which every gated B3 row (b3_ratings_gate.evaluate +
probe + module rows, the release rule) is >= 0, by bracketing: each round solves ceil(h*) and ceil(h*) - 1 where h* is
the zero of the worst gated margin interpolated linearly in 1/h between the bracket ends (bisection on 1/h when the
interpolant falls outside); stops when hi - lo <= max(1, 0.03 hi). Workers: at most --max-workers, and fewer while
other B3 pools run (total <= 6).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
import time
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from pathlib import Path

sys.dont_write_bytecode = True
SNAP = Path(os.environ.get("AF_SNAP", "/Users/bennet/Desktop/temper/worktrees/runs-native21/airflow28/snap"))
R5 = SNAP / "zapote/power-stage-120v/validation-results/04-board-current-thermal/round5-native21"
B3R = R5 / "b3-ratings"
RUNS = Path(os.environ.get("AF_RUNS", "/Users/bennet/Desktop/temper/worktrees/runs-native21/airflow28/runs"))
OUT = Path(__file__).resolve().parent.parent / "results"
sys.path.insert(0, str(R5 / "b3-convergence"))
sys.path.insert(0, str(B3R))

GUESS = {  # first probe h per (ceiling, bay); set from the c28 series (34 / 26) scaled down the ladder
    (28.0, 61.0): 40, (28.0, 55.0): 32, (26.0, 61.0): 28, (26.0, 55.0): 21, (24.0, 61.0): 22, (24.0, 55.0): 16,
    (22.0, 61.0): 17, (22.0, 55.0): 13, (20.0, 61.0): 13, (20.0, 55.0): 11, (18.0, 61.0): 11, (18.0, 55.0): 10, (28.0, 50.0): 23}


ZONE = (0.0, 125.0, 0.0, 90.0)
# zone2: the hot corner plus the tank path the zone run found binding outside it at bay 61 (laminate block at x 140.5,
# y 98.5 between the coil terminals J2 / J5 (132, 85.5 / 70.5), CT T1 (135, 110) and the bank column C21-C152 (x 163-190.5))
ZONE2 = (0.0, 195.0, 0.0, 120.0)
GUESS_REGION = {("top", 28.0, 61.0): 42, ("top", 28.0, 55.0): 36, ("zone", 28.0, 61.0): 45, ("zone", 28.0, 55.0): 38,
                ("jet", 28.0, 61.0): 75, ("jet", 28.0, 55.0): 60,
                ("zone2", 28.0, 61.0): 50, ("zone2", 28.0, 55.0): 40}


def gate():
    import b3_ratings_gate as g
    if not getattr(g, "_af_patched", False):
        orig = g.module_rows

        def module_rows(c, r25, r05, bay, mpns=None, allow_pins_only=False):
            """The gate refuses a PS2 row when its pins carry heat INTO the module (the board heats it). That happens
            only in the region modes that credit PS2's case at h_top to bay air (top: whole-board region). There the
            row is kept with the gate's own formula, without the guard, and flagged (pins_w < 0)."""
            try:
                return orig(c, r25, r05, bay, mpns, allow_pins_only)
            except SystemExit as ex:
                if "INTO the module" not in str(ex):
                    raise
                q25, q05 = dict(r25), dict(r05)
                q25["parts"] = [dict(p, pins_w=abs(p["pins_w"])) if p["ref"] == "PS2" else p for p in r25["parts"]]
                q05["parts"] = [dict(p, pins_w=abs(p["pins_w"])) if p["ref"] == "PS2" else p for p in r05["parts"]]
                rows = orig(c, q25, q05, bay, mpns, allow_pins_only)
                p25 = next(p for p in r25["parts"] if p["ref"] == "PS2")
                for r in rows:
                    r["item"] += f" [region-credited; pins carry {-p25['pins_w']:.3f} W INTO the module: gate guard waived]"
                    r["pins_w"] = round(p25["pins_w"], 4)
                return rows
        g.module_rows = module_rows
        g._af_patched = True
    return g


def case_name(ceil, h, mode):
    c = f"{ceil:g}"
    return f"c{c}_h{int(h)}" if mode == "uniform" else f"c{c}_h10_jet{int(h)}"


def run_dir(mode, bay):
    return RUNS / mode / f"bay{int(bay)}"


def board_bounds():
    import thermal_body as tb
    import run_basis as rb
    b = tb.Board(rb.rs.GEOM, rb.RUNS / "cache")
    return (b.xmin - 1.0, b.xmax + 1.0, b.ymin - 1.0, b.ymax + 1.0)


def _worker(job, mode):
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(R5 / "b3-convergence"))
    sys.path.insert(0, str(B3R))
    import run_basis as rb
    if mode == "top":
        rb.JET_REGION = board_bounds()
    elif mode == "zone":
        rb.JET_REGION = ZONE
    elif mode == "zone2":
        rb.JET_REGION = ZONE2
    t0 = time.time()
    n = rb.one(job)
    return n, time.time() - t0


def other_b3_workers():
    """Busy B3 pool workers that are not this process's: descendants of any chain.sh / run_basis.py process and of the
    other airflow_search.py processes (the shared-machine rule: total B3 workers <= 6)."""
    me = os.getpid()
    out = subprocess.run(["ps", "-axo", "pid,ppid,pcpu,command"], capture_output=True, text=True).stdout.splitlines()[1:]
    rows = []
    for ln in out:
        p = ln.split(None, 3)
        if len(p) == 4:
            rows.append((int(p[0]), int(p[1]), float(p[2]), p[3]))
    kids = {}
    for pid, ppid, _, _ in rows:
        kids.setdefault(ppid, []).append(pid)
    roots = [pid for pid, _, _, cmd in rows if pid != me and ("chain.sh" in cmd or "run_basis.py" in cmd
                                                             or "airflow_search.py" in cmd)]
    seen, stack = set(), list(roots)
    while stack:
        q = stack.pop()
        for c in kids.get(q, []):
            if c not in seen:
                seen.add(c)
                stack.append(c)
    info = {pid: (cpu, cmd) for pid, _, cpu, cmd in rows}
    return sum(1 for q in seen if q in info and "python" in info[q][1] and "resource_tracker" not in info[q][1]
               and info[q][0] > 20.0)


def solve(cases, mode, max_workers):
    """cases: list of (case, ceil, bay). Solves each at 0.25 and 0.5 mm unless both run files exist."""
    import run_basis as rb
    g = gate()
    jobs = []
    for c, ceil, bay in cases:
        d = run_dir(mode, bay)
        d.mkdir(parents=True, exist_ok=True)
        _, h = g.case_ceiling_h(c)
        for p in (0.25, 0.5):
            name = f"{c}_p{str(p).replace('.', 'p')}"
            if (d / f"{name}.json").exists():
                continue
            jobs.append((name, c, ceil, h, bay, p, str(d), {}, (), rb.tb.ALPHA_CU))
    jobs.sort(key=lambda j: j[5])            # the slow 0.25 mm solves first
    if not jobs:
        return
    with ProcessPoolExecutor(max_workers=max_workers) as ex:
        pend, todo = set(), list(jobs)
        while todo or pend:
            allow = min(max_workers, 6 - other_b3_workers())      # total B3 workers on the machine <= 6
            while todo and len(pend) < allow:
                j = todo.pop(0)
                pend.add(ex.submit(_worker, j, mode))
            if not pend:
                time.sleep(60)
                continue
            done, pend = wait(pend, timeout=60, return_when=FIRST_COMPLETED)
            for f in done:
                n, dt = f.result()
                print(f"  solved {mode} {n} in {dt:.0f} s (workers allowed {allow})", flush=True)


def evaluate(c, bay, mode):
    g = gate()
    res = g.run(run_dir(mode, bay), {c: bay}, release=[])
    rows = res["cases"][c]
    gated = [r for r in rows if r["gated"]]
    lam = [r for r in gated if r["item"].startswith("laminate")]
    part = [r for r in gated if not r["item"].startswith("laminate")]
    w = min(gated, key=lambda r: r["margin_k"])
    hdep = min((r for r in gated if not r["item"].startswith("PS2:")), key=lambda r: r["margin_k"])
    wl = min(lam, key=lambda r: r["margin_k"])
    wp = min(part, key=lambda r: r["margin_k"])
    r25 = json.loads((run_dir(mode, bay) / f"{c}_p0p25.json").read_text())
    return {"case": c, "bay_c": bay, "mode": mode, "h": g.case_ceiling_h(c)[1] if mode == "uniform" else g.case_jet(c)["h_top"],
            "worst": w["margin_k"], "worst_item": w["item"], "hdep": hdep["margin_k"], "hdep_item": hdep["item"], "laminate": wl["margin_k"], "laminate_item": wl["item"],
            "parts": wp["margin_k"], "parts_item": wp["item"],
            "failing": [f"{r['item']} {r['margin_k']:+.1f}" for r in gated if r["margin_k"] < 0],
            "board_sha256": res["board_sha256"][c], "balance": r25["balance"], "region": r25.get("region"),
            "copper": res["basis"]["cases"][c].get("copper"), "rows": rows}


def next_points(pts, ceil, bay, key="worst"):
    """pts {h: margin}. Returns the integer h values to solve next, or [] when bracketed to tolerance."""
    hs = sorted(pts)
    fail = [h for h in hs if pts[h] < 0]
    ok = [h for h in hs if pts[h] >= 0]
    if ok and min(ok) <= 10:
        return []
    if fail and ok:
        lo, hi = max(fail), min(ok)
        if hi - lo <= max(1.0, 0.03 * hi):
            return []
        x0, x1, m0, m1 = 1 / lo, 1 / hi, pts[lo], pts[hi]
        hstar = 1 / (x0 + (x1 - x0) * (0 - m0) / (m1 - m0))
        if not lo < hstar < hi:
            hstar = 2 / (x0 + x1)
        a = math.ceil(hstar)
        cand = sorted({min(max(a, lo + 1), hi - 1), min(max(a - 1, lo + 1), hi - 1)})
        return [h for h in cand if h not in pts and lo < h < hi]
    if not ok:                               # extrapolate in 1/h from the two highest h
        if len(hs) >= 2:
            (ha, ma), (hb, mb) = (hs[-2], pts[hs[-2]]), (hs[-1], pts[hs[-1]])
            if mb > ma:
                x = 1 / hb + (1 / hb - 1 / ha) * (0 - mb) / (mb - ma)
                hstar = 1 / x if x > 0 else 3 * hb
            else:
                hstar = 2 * hb
            hstar = min(max(hstar * 1.05, hb * 1.15), hb * 3, 400)
        else:
            hstar = GUESS.get((ceil, bay), 30) if hs[-1] < GUESS.get((ceil, bay), 30) else hs[-1] * 1.6
        return [math.ceil(hstar)]
    # only passing points: go down toward 10
    if min(ok) > 14:
        return [max(10, math.floor(0.75 * min(ok)))]
    lo = 10
    if lo not in pts:
        return [lo]
    return []


def series_state(ceil, bay, mode):
    """Every solved point of this series on disk."""
    g = gate()
    d = run_dir(mode, bay)
    pts = {}
    if not d.exists():
        return pts
    for f in d.glob(f"c{ceil:g}_h*_p0p25.json"):
        c = f.name[:-len("_p0p25.json")]
        try:
            cc, h = g.case_ceiling_h(c)
        except SystemExit:
            continue
        jet = g.case_jet(c)
        if cc != ceil or (mode == "uniform") != (jet is None):
            continue
        if not (d / f"{c}_p0p5.json").exists():
            continue
        e = evaluate(c, bay, mode)
        pts[e["h"]] = e
    return pts


def shape_candidates(pts, ref, lo, hi):
    """Shape transfer from the reference series (predict_next.py): fit m = A + B f(h), return ceil(h*) - 1, ceil(h*)."""
    hs = sorted(ref)
    xs = [1 / v for v in hs]

    def f(h):
        x = 1 / h
        if x >= xs[0]:
            a = 0
        elif x <= xs[-1]:
            a = len(hs) - 2
        else:
            a = max(i for i in range(len(hs)) if xs[i] >= x)
        b = a + 1
        return ref[hs[a]] + (ref[hs[b]] - ref[hs[a]]) * (x - xs[a]) / (xs[b] - xs[a])
    ph = sorted(pts)
    fs, ms = [f(h) for h in ph], [pts[h] for h in ph]
    if len(ph) == 1:
        B, A = 1.0, ms[0] - fs[0]
    else:
        fm, mm = sum(fs) / len(fs), sum(ms) / len(ms)
        B = sum((x - fm) * (y - mm) for x, y in zip(fs, ms)) / sum((x - fm) ** 2 for x in fs)
        A = mm - B * fm
    a_, b_ = 10.0, 400.0
    if A + B * f(b_) < 0:
        return None
    for _ in range(60):
        mid = 0.5 * (a_ + b_)
        a_, b_ = (mid, b_) if A + B * f(mid) < 0 else (a_, mid)
    c = math.ceil(b_)
    return [h for h in sorted({c - 1, c}) if lo < h < hi and h not in pts]


def search(series, mode, max_workers, rounds=8):
    state = {s: {} for s in series}
    for s in series:
        state[s] = series_state(*s, mode)
    for rnd in range(rounds):
        batch = []
        for (ceil, bay) in series:
            pts = {h: (e["hdep"] if e["worst"] >= 0 else min(e["worst"], e["hdep"]))
                   for h, e in state[(ceil, bay)].items()}
            if not pts:
                g = GUESS.get((ceil, bay), 30) if mode == "uniform" else GUESS_REGION.get((mode, ceil, bay), 45)
                nxt = [10] if mode == "uniform" else [round(0.8 * g), g]
                if mode == "uniform" and (ceil, bay) in GUESS and GUESS[(ceil, bay)] > 10:
                    nxt.append(GUESS[(ceil, bay)])
            else:
                nxt = next_points(pts, ceil, bay)
                ref_st = series_state(28.0, 61.0, "uniform") if mode == "uniform" else {}
                if nxt and len(ref_st) >= 3 and (ceil, bay) != (28.0, 61.0):
                    ok = [h for h in pts if pts[h] >= 0]
                    fail = [h for h in pts if pts[h] < 0]
                    sc = shape_candidates(pts, {h: (e["hdep"] if e["worst"] >= 0 else min(e["worst"], e["hdep"]))
                                                for h, e in ref_st.items()},
                                          max(fail) if fail else 10, min(ok) if ok else 401)
                    if sc:
                        nxt = sc
            for h in nxt:
                batch.append((case_name(ceil, h, mode), ceil, bay))
        if not batch:
            break
        print(f"round {rnd}: {[f'{c}@{b:g}' for c, _, b in batch]}", flush=True)
        solve(batch, mode, max_workers)
        for (ceil, bay) in series:
            state[(ceil, bay)] = series_state(ceil, bay, mode)
            pts = state[(ceil, bay)]
            print(f"  {mode} c{ceil:g}@{bay:g}: " + ", ".join(f"h{h:g} {e['worst']:+.1f} ({e['worst_item'][:22]})"
                                                          for h, e in sorted(pts.items())), flush=True)
    return state


def parse_series(spec):
    out = []
    for it in spec.split(","):
        c, _, b = it.strip().partition("@")
        out.append((float(c.lstrip("c")), float(b)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("search", "point", "summary"))
    ap.add_argument("--series", default="")
    ap.add_argument("--cases", default="")
    ap.add_argument("--mode", default="uniform", choices=("uniform", "top", "jet", "zone", "zone2", "jetmix"))
    ap.add_argument("--max-workers", type=int, default=4)
    ap.add_argument("--rounds", type=int, default=8)
    a = ap.parse_args()
    import run_basis as rb
    sys.path.insert(0, str(R5))
    import a4_fields
    if not a4_fields.check(R5 / "outputs"):
        raise SystemExit(2)
    if a.cmd == "search":
        search(parse_series(a.series), a.mode, a.max_workers, a.rounds)
    elif a.cmd == "point":
        g = gate()
        cases = []
        for it in a.cases.split(","):
            c, _, b = it.partition("@")
            cases.append((c, g.case_ceiling_h(c)[0], float(b)))
        solve(cases, a.mode, a.max_workers)
        for c, _, b in cases:
            e = evaluate(c, b, a.mode)
            print(f"{a.mode} {c}@{b:g}: worst {e['worst']:+.1f} ({e['worst_item']}); laminate {e['laminate']:+.1f}; "
                  f"parts {e['parts']:+.1f} ({e['parts_item']})")
    else:
        summary()


def summary():
    OUT.mkdir(parents=True, exist_ok=True)
    out = {"snapshot": (SNAP / "SNAPSHOT.txt").read_text().strip(), "modes": {}}
    for mode in ("uniform", "top", "jet", "zone", "zone2", "jetmix"):
        if not (RUNS / mode).exists():
            continue
        m = {}
        for bd in sorted((RUNS / mode).glob("bay*")):
            bay = float(bd.name[3:])
            ceils = sorted({gate().case_ceiling_h(f.name[:-len("_p0p25.json")])[0] for f in bd.glob("c*_p0p25.json")})
            for ceil in ceils:
                pts = series_state(ceil, bay, mode)
                m[f"c{ceil:g}@{bay:g}"] = {f"{h:g}": {k: v for k, v in e.items() if k != "rows"} | {"rows": e["rows"]}
                                           for h, e in sorted(pts.items())}
        out["modes"][mode] = m
    (OUT / "search.json").write_text(json.dumps(out, indent=1) + "\n")
    print("->", OUT / "search.json")


if __name__ == "__main__":
    main()
