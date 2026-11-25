#!/usr/bin/env python3
"""c55 device trade: switching grids per candidate on the as-built native-21 deck.

    python3 -I trade.py <grid> --dev <name> [--workers 8] [--fix]      -> ../sims/<name>/<grid>/results.json
grids: full (gn 640-run decision grid: S1 ZVS at DT 340/408, S2 fault turn-off, S4 hard commutation, S5 first edge,
       legs A/B, 27/100/150 C, nominal/weak/strong 2EDR corners, ESL 10 / 1.06 nH),
       s4b (gn 42-run binding S4 set), energy (device-study loss grid: legs A/B, Tj 100/150, V 20..198, I 2..60 A,
       DT 569 ns, both directions, LONG window 3.75 us so slow turn-on networks finish), e1 (energy grid at Tj 150,
       leg A only - for slow models)
Rows are gn.run_case() rows (all its measures and screens) plus the generic die energy (devlib.GENERIC_ENERGY).
Device definitions: devices.py.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import G, H, SIMS, sha  # noqa: E402
import devlib  # noqa: E402
import devices  # noqa: E402

_MEAS: dict = {}
_EXTRA: dict = {}
_LOCK = threading.Lock()
_orig_run = G.run_d2.run


def _run(deck, p, keep=None, raw=False):
    p = dict(p)
    p.update(_EXTRA)
    r = _orig_run(deck, p, keep=keep, raw=raw)
    with _LOCK:
        _MEAS[str(keep)] = r["meas"]
    return r


G.run_d2.run = _run      # gn.run_case calls run_d2.run (module attribute) -> extra params + meas capture


def energy_grid(legs="AB", temps=(100, 150), dt=569):
    return [("E", "nom", leg, t, vb, il, d, dt, 10) for leg in legs for t in temps
            for vb in (20, 60, 100, 140, 170, 198) for il in (2, 5, 10, 15, 20, 30, 40, 50, 60) for d in (0, 1)]


def jobs(grid: str):
    if grid in ("full", "s4b", "s4screen"):
        return G.grid(grid)
    if grid in ("s4bL", "fullL"):
        # the same rows in the long window (3.75 us after the on command, gn's 'slowgate' deck): S4 rows whose slow
        # turn-on puts the commutation edge after the 0.75 us window have no 20-80 % edge there
        return G.grid(grid[:-1])
    if grid == "zvs170":
        # ZVS at a 200 ns dead time (R9 / R17 20 kohm) at its -15 % lower edge, 170 ns: S1 rows down to 3 A
        return [("S1", drv, leg, tj, vb, il, d, 170, 10) for drv in ("nom", "weak") for leg in "AB" for tj in (27, 150)
                for vb in (170, 198, 280) for il in (3, 5, 8, 12, 20, 37) for d in (0, 1)]
    if grid == "slowgate":
        # the gate-network study's 16-run turn-on-delay grid (S1, long window: incoming gate V at 1 / 2 / 3 us)
        return G.grid("slowgate")
    if grid == "s4L":
        # every S4 row of the full grid (336) in the long window
        return [j for j in G.grid("full") if j[0] == "S4"]
    if grid == "s2q":
        return [j for j in G.grid("full") if j[0] == "S2"]
    if grid == "energy":
        return energy_grid()
    if grid == "e1":
        return energy_grid("A", (150,))
    if grid in ("eA", "eAs"):
        # leg A only (leg B reuses it in c50; the two legs' committed CFD7 grids differ by < 2 %), Tj 100 / 150;
        # 'eAs' keeps the device study's 0.75 us window (fast-gate devices whose run time makes the long window costly)
        return energy_grid("A", (100, 150))
    if grid == "eA200":
        # leg A, long window, dead time 200 ns: a SiC part (t_trans ~42 ns) can run a shorter dead time (R9 / R17
        # change), which cuts its 4.3 V third-quadrant conduction
        return energy_grid("A", (100, 150), dt=200)
    raise ValueError(grid)


def run_case(deck, out, dev, j):
    case, drv, leg, t, vb, il, d, dt, esl, *_ = j
    cfg = dict(ron=dev["ron"], roff=dev["roff"], cgs=dev["cgs"], topo=dev.get("topo", "split"))
    trmax = "0.2n"
    for attempt in range(2):
        o = out if attempt == 0 else out / "retry"
        r = G.run_case(deck, o, cfg, "S1" if case == "E" else case, drv, leg, t, vb, il, d, dt, esl, trmax=trmax)
        if r["status"] == "complete":
            break
        trmax = "0.1n"
    r["case"] = case
    name = f"{'S1' if case == 'E' else case}_{drv}_{leg}_T{t}_v{vb}_i{il}_d{d}_dt{dt}_esl{esl}_s{trmax}"
    m = _MEAS.get(str(o / "runs" / name), {})
    if r["status"] == "complete" and "eg_hs" in m:
        inc, off = ("hs", "ls") if d == 0 else ("ls", "hs")
        t1 = 2e-6
        tw0, tw1 = t1 - 20e-9, t1 + dt * 1e-9 + (3.75e-6 if LONG[0] else 0.75e-6)
        e_tot = m["eg_hs"] + m["eg_ls"]
        p_end = m.get(f"pg_{inc}_end")
        r.update(eg_out_J=m[f"eg_{off}"], eg_in_J=m[f"eg_{inc}"], eg_tot_J=e_tot, pg_cond_end_W=p_end,
                 pg_cond_start_W=m.get(f"pg_{off}_start"),
                 eg_extra_J=(e_tot - p_end * (tw1 - tw0)) if p_end is not None else None,
                 eg_off_edge_J=m[f"eg_{off}"] - (m.get(f"pg_{off}_start") or 0) * 20e-9)
    if case == "E":
        r.pop("pass", None)
    else:
        r = G.screen(r)
    return r


LONG = [False]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("grid")
    ap.add_argument("--dev", required=True)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--fix", action="store_true")
    a = ap.parse_args()
    dev = devices.get(a.dev)
    LONG[0] = a.grid in ("energy", "e1", "eA", "eA200", "s4bL", "fullL", "s4L", "slowgate")
    energy = a.grid in ("energy", "e1", "eA", "eAs", "eA200")
    _EXTRA.update(devlib.params_extra(dev))
    out = SIMS / a.dev / a.grid
    out.mkdir(parents=True, exist_ok=True)
    deck = out / "deck.cir"
    deck.write_text(devlib.build(dev, long=LONG[0], energy_generic=energy))
    js = jobs(a.grid)
    if a.limit:
        js = js[:a.limit]
    prev = out / "results.json"
    if a.fix and prev.is_file():
        rows = json.loads(prev.read_text())["rows"]
        bad = [i for i, r in enumerate(rows) if r["status"] != "complete"]
        with ThreadPoolExecutor(a.workers) as ex:
            new = list(ex.map(lambda j: run_case(deck, out / "fix", dev, j), [js[i] for i in bad]))
        for i, r in zip(bad, new):
            rows[i] = r
    else:
        with ThreadPoolExecutor(a.workers) as ex:
            rows = list(ex.map(lambda j: run_case(deck, out, dev, j), js))
    ident = {"deck": sha(deck), "trade.py": sha(Path(__file__)), "devlib.py": sha(Path(devlib.__file__)),
             "devices.py": sha(Path(devices.__file__)), "gn.py": sha(Path(G.__file__)),
             "harness.py": sha(Path(H.__file__)), "matrix_A": sha(G.d2c.MATRICES["A"]),
             "matrix_B": sha(G.d2c.MATRICES["B"])}
    ident.update(devices.model_identity(a.dev))
    res = {"dev": a.dev, "spec": {k: v for k, v in dev.items() if k != "wrapper"}, "grid": a.grid,
           "long_window": LONG[0], "extra_params": dict(_EXTRA), "identity": ident, "rows": rows}
    (out / "results.json").write_text(json.dumps(res, indent=1, default=str) + "\n")
    bad = sum(r["status"] != "complete" for r in rows)
    print(a.dev, a.grid, f"{len(rows) - bad}/{len(rows)} complete", flush=True)


if __name__ == "__main__":
    main()
