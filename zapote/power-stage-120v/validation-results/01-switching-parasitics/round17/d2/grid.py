#!/usr/bin/env python3
"""Round 17 D2 grid: every switching case of 01-switching-parasitics.md on a
FEM port matrix, judged against the task's acceptance criteria.

    grid.py --matrix FILE --out DIR [--workers 2] [--only S1,S2] [--limit N]

Cases (the task's Step 3, single-transition deck leg_matrix.cir):
  S1 nominal ZVS     IL = 37 A                        buses 170/198/280 V
  S2 fault turn-off  IL = 61, 71 A                    280 V
  S3 light load      IL = 2, 5, 10 A                  170/198/280 V
  S4 hard turn-on    IL = -20 A (partner diode on)    170/198/280 V
each for DIR 0/1 (low-side / high-side turned off first), dead time
250/307/348/391/450 ns (250/450 stress corners; 307/348/391 the D-1
estimated min/nominal/max for the fitted 39 kOhm, not guaranteed limits)
and capacitor ESL 5/10/20 nH (TDK bound <= ~20 nH).

Criteria (task table):
  VDS die peak            <= 520 V (S1, S3, S4), <= 585 V (S2 at 280 V)
  off-device die VGS      < 3.0 V after the partner's on command
                          (datasheet min VGS(th) 3.5 V - 0.5 V)
  die VGS transient       within +/-30 V (datasheet dynamic rating)
  ZVS (S1 at 348 ns)      incoming die VDS at its on command <= 5 % of VBUS
A case that aborts in ngspice counts as FAIL (no result).

Two verdicts per case (D-4 review, P1): `stress_pass` (abort, VDS, off-gate,
VGS transient) and `task_pass` = stress_pass and, for S1 at the nominal
348 ns, ZVS. The off-gate label is a timing observation, not a diagnosis
(D-4, P2): `above_limit_at_partner_cmd` (the off gate is still >= 3.0 V at
the partner's on command), `later_peak` (it is below then, and peaks above
later), `unknown` (a measurement is missing), `aborted`.

Resumable, with identity: each case file stores the SHA-256 of the matrix
values, the deck, run_d2.py, this file and the vendor model library; a case
is reused only if all match, otherwise it is rerun (D-4, P1: a reused
directory must not attribute old simulations to a new matrix). Writes
DIR/results.jsonl and DIR/summary.json.
"""
from __future__ import annotations

import argparse
import functools
import hashlib
import itertools
import json
import re
import subprocess
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import run_d2

DT = (250, 307, 348, 391, 450)
NOMINAL_DT = 348
HERE = Path(__file__).resolve().parent


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else "missing"


def deck_for(L) -> Path:
    """4-port matrix -> leg_matrix.cir; 5-port (P5 = bulk C6) -> leg_matrix5.cir."""
    return {4: run_d2.DECK, 5: HERE / "leg_matrix5.cir"}[len(L)]


@functools.lru_cache(maxsize=None)
def ngspice_version() -> str:
    out = subprocess.run(["ngspice", "-v"], capture_output=True, text=True)
    m = re.search(r"ngspice-(\S+)", out.stdout + out.stderr)
    return m[1] if m else "unknown"


def includes(deck: Path) -> dict[str, str]:
    """Hashes of the deck's .include files as the runner resolves them (vendor
    lib from the kit, '../common/' from the kit's common/, params.inc excluded:
    it is generated from the case parameters, which are already identity)."""
    out = {}
    for name in re.findall(r"^\.include\s+(\S+)", deck.read_text(), re.M):
        if name == "params.inc":
            continue
        path = (run_d2.KIT / "models" / "vendor" / name if name.endswith(".lib")
                else run_d2.KIT / "common" / name.split("../common/", 1)[1] if name.startswith("../common/")
                else deck.parent / name)
        out[name] = _sha(path)
    return out


def identity(L, overrides: dict | None = None) -> dict:
    """Everything a case result depends on, hashed (D-9 review, P2: includes,
    runner and simulator build too, not only the deck and this file)."""
    deck = deck_for(L)
    return {"matrix": hashlib.sha256(json.dumps([[round(float(v), 9) for v in row] for row in L]).encode()).hexdigest(),
            "deck": _sha(deck), "includes": includes(deck), "run_d2": _sha(HERE / "run_d2.py"),
            "runner": _sha(run_d2.KIT / "common" / "run_ngspice.py"), "ngspice": ngspice_version(),
            "grid": _sha(Path(__file__).resolve()), "overrides": dict(sorted((overrides or {}).items()))}


# Scenario parameters that the case tuple, labels and acceptance logic are
# derived from; --set must not change them (D-9 review, P2).
SCENARIO_KEYS = {"VBUS", "IL", "DIR", "DT", "LESL", "LSHUNT", "TRMAX", "T1"}
ESL = (5, 10, 20)


def cases(only: set[str] | None, esl=None):
    esls = tuple(esl) if esl else ESL
    rows = []
    for vbus, il, d, dt, esl in itertools.product((170, 198, 280), (37,), (0, 1), DT, esls):
        rows.append(("S1", vbus, il, d, dt, esl))
    for il, d, dt, esl in itertools.product((61, 71), (0, 1), DT, esls):
        rows.append(("S2", 280, il, d, dt, esl))
    for vbus, il, d, dt, esl in itertools.product((170, 198, 280), (2, 5, 10), (0, 1), DT, esls):
        rows.append(("S3", vbus, il, d, dt, esl))
    for vbus, d, dt, esl in itertools.product((170, 198, 280), (0, 1), DT, esls):
        rows.append(("S4", vbus, -20, d, dt, esl))
    return [r for r in rows if not only or r[0] in only]


def tag(c) -> str:
    s, vbus, il, d, dt, esl = c
    return f"{s}_v{vbus}_i{il}_d{d}_dt{dt}_esl{esl}"


def one(args):
    c, L, out, overrides = args
    s, vbus, il, d, dt, esl = c
    res_file = out / "cases" / f"{tag(c)}.json"
    ident = identity(L, overrides)
    if res_file.exists():
        old = json.loads(res_file.read_text())
        if old.get("identity") == ident:
            return old
        # stale: different matrix, deck, model or code -> rerun, never reuse
    p = run_d2.matrix_params(L)
    p.update(VBUS=str(vbus), IL=str(il), DIR=str(d), LESL=f"{esl}n", LSHUNT="2n", DT=f"{dt}n", TRMAX="0.2n")
    p.update(overrides or {})
    r = run_d2.run(deck_for(L), p, keep=out / "runs" / tag(c))
    m = r["meas"]
    off = "ls" if d == 0 else "hs"                     # device turned off at T1
    inc = "hs" if d == 0 else "ls"                     # device turned on after the dead time
    vds = [m.get("vds_ls_die_pk"), m.get("vds_hs_die_pk")]
    vgs = [m.get(k) for k in ("vgs_ls_die_max", "vgs_ls_die_min", "vgs_hs_die_max", "vgs_hs_die_min")]
    row = {"case": s, "vbus": vbus, "il": il, "dir": d, "dt_ns": dt, "esl_nH": esl, "aborted": r["aborted"],
           "vds_pk": max(v for v in vds if v is not None) if all(v is not None for v in vds) else None,
           "vgs_off_max": m.get(f"vgs_{off}_off_max"),
           "vgs_abs_max": max(abs(v) for v in vgs) if all(v is not None for v in vgs) else None,
           "vds_incoming_at_on": m.get(f"vds_{inc}_at_on"),
           "vgs_off_at_partner_cmd": m.get(f"vgs_{off}_at_partner")}
    lim = 585.0 if s == "S2" else 520.0
    row["pass_vds"] = row["vds_pk"] is not None and row["vds_pk"] <= lim
    row["pass_off_gate"] = row["vgs_off_max"] is not None and row["vgs_off_max"] < 3.0
    # Cause, when the off gate fails: still above 3.0 V at the partner's on
    # command = dead time too short (shoot-through); else a later rebound.
    at_cmd = row["vgs_off_at_partner_cmd"]
    row["off_gate_cause"] = (None if row["pass_off_gate"] else
                             "aborted" if r["aborted"] else
                             "unknown" if row["vgs_off_max"] is None or at_cmd is None else
                             "above_limit_at_partner_cmd" if at_cmd >= 3.0 else "later_peak")
    row["pass_vgs_transient"] = row["vgs_abs_max"] is not None and row["vgs_abs_max"] <= 30.0
    row["zvs"] = (row["vds_incoming_at_on"] is not None and row["vds_incoming_at_on"] <= 0.05 * vbus)
    row["stress_pass"] = (not r["aborted"]) and row["pass_vds"] and row["pass_off_gate"] and row["pass_vgs_transient"]
    zvs_required = s == "S1" and dt == NOMINAL_DT
    row["task_pass"] = row["stress_pass"] and (row["zvs"] or not zvs_required)
    row["pass"] = row["task_pass"]
    row["identity"] = ident
    res_file.parent.mkdir(parents=True, exist_ok=True)
    res_file.write_text(json.dumps(row))
    return row


def summarize(rows: list[dict]) -> dict:
    worst = {}
    for key, better in (("vds_pk", max), ("vgs_off_max", max), ("vgs_abs_max", max)):
        vals = [r for r in rows if r.get(key) is not None]
        if vals:
            w = better(vals, key=lambda r: r[key])
            worst[key] = {k: w[k] for k in ("case", "vbus", "il", "dir", "dt_ns", "esl_nH", key)}
    s1n = [r for r in rows if r["case"] == "S1" and r["dt_ns"] == NOMINAL_DT]
    return {"cases": len(rows), "aborted": sum(r["aborted"] for r in rows),
            "task_pass": sum(r["task_pass"] for r in rows), "task_fail": sum(not r["task_pass"] for r in rows),
            "stress_pass": sum(r["stress_pass"] for r in rows), "stress_fail": sum(not r["stress_pass"] for r in rows),
            "fail_by_criterion": {k: sum(not r[k] for r in rows) for k in ("pass_vds", "pass_off_gate", "pass_vgs_transient")},
            "off_gate_fail_causes": {c: sum(r.get("off_gate_cause") == c for r in rows) for c in ("above_limit_at_partner_cmd", "later_peak", "unknown", "aborted")},
            "off_gate_fails_by_dt_ns": {dt: sum((not r["pass_off_gate"]) and r["dt_ns"] == dt for r in rows) for dt in DT},
            "zvs_S1_at_348ns": {"yes": sum(r["zvs"] for r in s1n), "no": sum(not r["zvs"] for r in s1n)},
            "worst": worst}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--matrix", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--only", default=None, help="comma list of S1,S2,S3,S4")
    ap.add_argument("--limit", type=int, default=None, help="run only the first N cases (smoke test)")
    ap.add_argument("--dt", default=None, help="comma list of dead times (ns) to run; default all")
    ap.add_argument("--esl", default=None, help="comma list of capacitor ESL values (nH), replacing the default 5,10,20")
    ap.add_argument("--set", action="append", default=[], metavar="PARAM=VALUE",
                    help="deck parameter override applied after the matrix, e.g. K35=0 (recorded in the identity)")
    a = ap.parse_args()
    overrides = dict(kv.split("=", 1) for kv in a.set)
    bad = sorted(k for k in overrides if k.upper() in SCENARIO_KEYS)
    if bad:
        raise SystemExit(f"--set may not override scenario parameters {bad}; use the case filters instead")
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    L = run_d2.read_L(a.matrix)
    esl = [float(x) if "." in x else int(x) for x in a.esl.split(",")] if a.esl else None
    todo = cases(set(a.only.split(",")) if a.only else None, esl)
    if a.dt:
        todo = [c for c in todo if c[4] in {int(x) for x in a.dt.split(",")}]
    todo = todo[: a.limit]
    (out / "matrix_used.txt").write_text(Path(a.matrix).read_text())
    rows = []
    with ProcessPoolExecutor(a.workers) as ex:
        futs = [ex.submit(one, (c, L, out, overrides)) for c in todo]
        for i, f in enumerate(as_completed(futs), 1):
            r = f.result()
            rows.append(r)
            print(f"PROGRESS {i}/{len(todo)} {r['case']} v{r['vbus']} i{r['il']} d{r['dir']} dt{r['dt_ns']} esl{r['esl_nH']} "
                  f"vds={r['vds_pk']} offgate={r['vgs_off_max']} atcmd={r.get('vgs_off_at_partner_cmd')} cause={r.get('off_gate_cause')} pass={r['pass']}", flush=True)
    with open(out / "results.jsonl", "w") as fh:
        for r in sorted(rows, key=lambda r: (r["case"], r["vbus"], r["il"], r["dir"], r["dt_ns"], r["esl_nH"])):
            fh.write(json.dumps(r) + "\n")
    summ = summarize(rows)
    (out / "summary.json").write_text(json.dumps(summ, indent=1))
    print("RESULT " + json.dumps(summ))


if __name__ == "__main__":
    main()
