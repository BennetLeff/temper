#!/usr/bin/env python3
"""Controls for s4_edges.py (plain python, no pytest):  python3 -I test_s4_edges.py"""
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("s4_edges", HERE / "s4_edges.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
FAILS = []


def expect(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


def row(case="S4", slew=50.0, status="complete", esl=10, **kw):
    r = dict(case=case, status=status, esl_nH=esl, drv="nom", leg="A", temp_C=27, vbus=280, dir=0, dt_ns=600,
             pass_dvdt96=True, **kw)
    if slew is not None:
        r["slew2080_Vns"] = slew
    return r


def raises(f):
    try:
        f()
    except m.NoEdgeError:
        return True
    return False


GOOD = [row(slew=40.0), row(slew=68.58), row(slew=60.0, esl=1.06), row("S1", None), row("S5", 20.0)]
GAP = GOOD + [row(slew=None)]          # one complete S4 row without an edge

expect("max_slew of a clean grid is its maximum", m.max_slew(GOOD) == 68.58)
expect("max_slew by ESL", m.max_slew(GOOD, esl=1.06) == 60.0)
expect("max_slew refuses a grid with one S4 row without an edge", raises(lambda: m.max_slew(GAP)))
expect("the refusal is not hidden by the max of the other rows (68.58 > the gap's nothing)",
       raises(lambda: m.max_slew(GAP + [row(slew=99.0)])))
expect("an aborted S4 row does not count as a missing edge",
       m.max_slew(GOOD + [row(slew=None, status="aborted")]) == 68.58)
expect("an S1 row without a slew is out of scope", m.counts(GOOD) == {"S4": 0, "S5": 0})
expect("S5 rows are checked too", m.counts(GOOD + [row("S5", None)]) == {"S4": 0, "S5": 1})
expect("require_edges defaults to S4 only", not raises(lambda: m.require_edges(GOOD + [row("S5", None)])))
expect("grid with no S4 rows is refused, not 0", raises(lambda: m.max_slew([row("S1", 10.0)])))
rep = m.grid_report(GAP)
expect("grid_report counts and refuses", rep["no_edge_rows"] == 1 and "slew_refused" in rep)
expect("grid_report on a clean grid has no refusal", m.grid_report(GOOD) == {"no_edge_rows": 0})
expect("round17-era rows (no slew keys at all) are not a slew grid",
       not m.measures_edges([{"case": "S4", "status": "complete", "vds_pk": 300}]))
expect("an all-missing gn grid is still a slew grid (pass_dvdt96 marks it)", m.measures_edges([row(slew=None)]))

# ratchet: synthetic scan against a synthetic registry
reg = {"files": {"a.json": {"counts": {"S4": 1}, "why": "x"}}}
expect("ratchet passes a registered gap at its count", m.ratchet([("a.json", GAP)], reg) == [])
expect("ratchet fails an unregistered gapped file", any("not registered" in e for e in m.ratchet([("b.json", GAP)], reg)))
expect("ratchet fails a count that grew",
       any("!= registered" in e for e in m.ratchet([("a.json", GAP + [row(slew=None)])], reg)))
expect("ratchet fails a registered file that is now clean (ratchet down)",
       any("now has none" in e for e in m.ratchet([("a.json", GOOD)], reg)))
expect("ratchet passes a clean unregistered file", m.ratchet([("c.json", GOOD)], {"files": {}}) == [])

# CLI
with tempfile.TemporaryDirectory() as td:
    g, b = Path(td) / "good.json", Path(td) / "gap.json"
    g.write_text(json.dumps({"rows": GOOD}))
    b.write_text(json.dumps({"rows": GAP}))
    run = lambda *a: subprocess.run([sys.executable, "-I", str(HERE / "s4_edges.py"), *a], capture_output=True, text=True)
    expect("CLI check passes a clean grid", run("check", str(g)).returncode == 0)
    expect("CLI check fails a gapped grid", run("check", str(g), str(b)).returncode == 1)
p = subprocess.run([sys.executable, "-I", str(HERE / "s4_edges.py"), "ratchet"], capture_output=True, text=True)
expect("ratchet on the tracked results passes against s4_edges_known.json", p.returncode == 0)

# the case that started this (c55 section 1.3): the committed CFD7 max-Qrr short-window grid is refused, the long one is not
C55 = HERE.parent / "11-candidates" / "c55-device-trade" / "sims" / "cfd7_c39_tt260"
expect("c55 cfd7_c39_tt260/full (144 S4 rows without an edge) is refused",
       raises(lambda: m.max_slew(m.load_rows(C55 / "full" / "results.json"))))
expect("c55 cfd7_c39_tt260/s4L gives 68.58 V/ns", round(m.max_slew(m.load_rows(C55 / "s4L" / "results.json")), 2) == 68.58)

print(f"\n{len(FAILS)} failure(s)")
sys.exit(1 if FAILS else 0)
