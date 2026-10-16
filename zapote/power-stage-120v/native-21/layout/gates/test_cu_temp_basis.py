#!/usr/bin/env python3
"""Controls for cu_temp_basis.py.

    python3 -I native-21/layout/gates/test_cu_temp_basis.py

Synthetic trees (a temp directory) exercise each failure mode; the last cases run the real tree with the real registry
(must pass) and the real tree plus one injected unregistered consumer (must fail).
"""
import copy
import importlib.util
import json
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("cu_temp_basis", HERE / "cu_temp_basis.py")
g = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)

fails = 0


def check(ok, name, detail=""):
    global fails
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"   {detail}"))
    fails += 0 if ok else 1


TODAY = "2026-10-15"
SCAN = {"include": ["*.py"], "exclude": [], "a4_modules": ["thermal"]}
SOLVER_HDR = "import importlib.util\nspec = importlib.util.spec_from_file_location('kit', 'sheet_solver.py')\n"


def run(files, consumers=(), **kw):
    with tempfile.TemporaryDirectory() as td:
        for n, t in files.items():
            (Path(td) / n).write_text(t)
        reg = {"defaults": {"hot_floor_c": 100.0, "cold_ceil_c": 25.0}, "scan": SCAN, "consumers": list(consumers)}
        return g.check(td, reg, today=TODAY, **kw)


def entry(file, **kw):
    e = {"id": "T-1", "consumer": "synthetic", "file": file, "kinds": ["net"], "basis_temp_c": 125.0,
         "direction": "hot is conservative", "justification": "test"}
    e.update(kw)
    return e


def n_err(r, needle=""):
    return sum(needle in e for e in r["errors"])


# ---- the three finders, unregistered
r = run({"a.py": SOLVER_HDR + "net = kit.Net(pitch_mm=0.25)\n"})
check(n_err(r, "UNREGISTERED") == 1 and "[net]" in r["errors"][0], "synthetic unregistered Net() with no temp_c fails", r["errors"])
r = run({"a.py": SOLVER_HDR + "net = kit.Net(pitch_mm=0.25, temp_c=20.0)\n"})
check(n_err(r, "UNREGISTERED") == 1, "Net(temp_c=20.0) is not an explicit hot basis", r["errors"])
r = run({"a.py": SOLVER_HDR + "net = kit.Net(pitch_mm=0.25, temp_c=100.0)\n"})
check(not r["errors"], "Net(temp_c=100.0) is explicit and passes without an entry", r["errors"])
r = run({"a.py": SOLVER_HDR + "T = 90\nnet = kit.Net(0.25, temp_c=T)\n"})
check(not r["errors"], "Net(temp_c=<variable>) counts as explicit", r["errors"])
r = run({"a.py": "def f(i):\n    return i * i * 1.68e-8 * 0.05\n"})
check(n_err(r, "[rho]") == 1, "I2R with a bare 1.68e-8 fails", r["errors"])
r = run({"a.py": "RHO_CU = 1.72e-8\ndef f(i):\n    return i * i * RHO_CU\n"})
check(n_err(r, "[rho]") == 1, "RHO_CU constant without a TCR term fails", r["errors"])
r = run({"a.py": "RHO = 1.72e-8 * (1 + 0.00393 * 75)\n"})
check(not r["errors"], "resistivity with a 0.00393 TCR term in the same statement is explicit", r["errors"])
r = run({"a.py": "AIR_RHO = 1.2\nRHO_AL = 2700.0\nRHO_CP = {'cu': 3.4e6}\n"})
check(not r["errors"], "air / aluminium / heat-capacity densities are not copper resistivity", r["errors"])
r = run({"a.py": "import numpy as np\nnp.load('hv_dc-p00625-pl18-heat.npz')\n"})
check(n_err(r, "[a4field]") == 1, "a reader of the A4 heat npz fails", r["errors"])
r = run({"a.py": "import thermal\n"})
check(n_err(r, "[a4field]") == 1, "an import of an A4-reading module fails", r["errors"])
r = run({"a.py": "k = 0.048\ndef w(i, d):\n    return (i / (k * d ** 0.44)) ** (1 / 0.725)\n"})
check(n_err(r, "[ipc]") == 1, "IPC-2221 formula without a registry entry fails", r["errors"])
r = run({"a.py": "print(1)\n"})
check(not r["errors"], "a file with no copper-temperature use passes", r["errors"])

# ---- S17 closed: basis 'solved', reference fields, dated records
A4 = "import thermal\n"
r = run({"a.py": A4 + "ALPHA = 0.00393\n"}, [entry("a.py", kinds=["a4field"], basis_temp_c="solved", pin="ALPHA")])
check(not r["errors"], "basis 'solved' with a matching TCR pin passes", r["errors"])
r = run({"a.py": A4}, [entry("a.py", kinds=["a4field"], basis_temp_c="solved")])
check(n_err(r, "needs a `pin`") == 1, "basis 'solved' without a pin fails", r["errors"])
r = run({"a.py": A4}, [entry("a.py", kinds=["a4field"], basis_temp_c="solved", pin="ALPHA")])
check(n_err(r, "no longer matches") == 1, "basis 'solved' whose pin no longer matches (TCR code removed) fails", r["errors"])
sol = entry("s.py", id="T-S", kinds=["a4field"], basis_temp_c="solved", pin="ALPHA")
r = run({"s.py": A4 + "ALPHA = 0.00393\n", "a.py": A4},
        [sol, entry("a.py", id="T-R", kinds=["a4field"], basis_temp_c=20, direction="reference (corrected downstream)", corrected_by="T-S")])
check(not r["errors"], "a reference field corrected by a 'solved' entry passes", r["errors"])
r = run({"s.py": A4 + "ALPHA = 0.00393\n", "a.py": A4},
        [dict(sol, basis_temp_c=125.0), entry("a.py", id="T-R", kinds=["a4field"], basis_temp_c=20,
                                                direction="reference (corrected downstream)", corrected_by="T-S")])
check(n_err(r, "corrected_by") == 1, "a reference field whose corrector is not 'solved' fails", r["errors"])
with tempfile.TemporaryDirectory() as td:
    (Path(td) / "st-2026-10-15").mkdir()
    (Path(td) / "st-2026-10-15" / "a.py").write_text(A4)
    (Path(td) / "b.py").write_text(A4)
    reg = {"defaults": {}, "scan": {"include": ["*.py", "*/*.py"], "exclude": [], "a4_modules": ["thermal"]},
           "consumers": [entry("st-2026-10-15/a.py", id="T-D", kinds=["a4field"], basis_temp_c=20, direction="not a claim (dated record)"),
                         entry("b.py", id="T-E", kinds=["a4field"], basis_temp_c=20, direction="not a claim (dated record)")]}
    r = g.check(td, reg, today=TODAY)
check(n_err(r, "dated study folder") == 1 and not any("st-2026-10-15/a.py" in e for e in r["errors"]),
      "'dated record' passes in a dated folder and fails outside one", r["errors"])

# ---- superseded records: a live, unwaived superseder, and no live file may load the record
SOLVED_F = A4 + "ALPHA = 0.00393\n"
sup = lambda **kw: entry("old.py", **{"id": "T-O", "kinds": ["a4field"], "basis_temp_c": 20,
                                      "direction": "superseded (record)", "superseded_by": "T-S", **kw})
r = run({"s.py": SOLVED_F, "old.py": A4}, [sol, sup()])
check(not r["errors"], "a superseded record with a live 'solved' superseder and no live loader passes", r["errors"])
r = run({"s.py": SOLVED_F + "import old\n", "old.py": A4}, [sol, sup()])
check(n_err(r, "names it") == 1, "a live file that imports the superseded record fails", r["errors"])
r = run({"s.py": SOLVED_F + "spec = importlib.util.spec_from_file_location('o', '../x/old.py')\n", "old.py": A4}, [sol, sup()])
check(n_err(r, "names it") == 1, "a live file that loads the record by path (importlib) fails", r["errors"])
r = run({"s.py": '"""Same command line as ../old.py."""\n' + SOLVED_F + "old = 3  # cf. old.py\n", "old.py": A4}, [sol, sup()])
check(not r["errors"], "a docstring / comment citation or a same-named local is not a dependency", r["errors"])
r = run({"s.py": SOLVED_F, "old.py": A4}, [sol, sup(superseded_by="T-X")])
check(n_err(r, "superseded_by") == 1, "a superseded record with no such superseder fails", r["errors"])
r = run({"s.py": SOLVED_F, "old.py": A4},
        [dict(sol, basis_temp_c=20, waiver={"id": "W", "reason": "r", "expires": "2099-01-01"}), sup()])
check(n_err(r, "superseded_by") == 1, "a superseded record whose superseder is waived fails", r["errors"])
with tempfile.TemporaryDirectory() as td:
    for n, t in {"s.py": SOLVED_F, "old.py": A4, "chain.sh": "# python3 old.py was retired\npython3 old.py\n"}.items():
        (Path(td) / n).write_text(t)
    reg = {"defaults": {}, "scan": dict(SCAN, live_roots=["chain.sh"]), "consumers": [sol, sup()]}
    r = g.check(td, reg, today=TODAY)
    check(n_err(r, "live file chain.sh") == 1, "a live root (chain) that runs the record fails", r["errors"])
    (Path(td) / "chain.sh").write_text("# python3 old.py was retired\n")
    r = g.check(td, reg, today=TODAY)
    check(not r["errors"], "a live root that only mentions the record in a comment passes", r["errors"])

# ---- registry rules
code = SOLVER_HDR + "net = kit.Net(pitch_mm=0.25)\n"
r = run({"a.py": code}, [entry("a.py", basis_temp_c=125.0)])
check(not r["errors"], "registered hot basis 125 C passes", r["errors"])
r = run({"a.py": code}, [entry("a.py", basis_temp_c=20.0)])
check(n_err(r, "NON-conservative") == 1, "'hot is conservative' at 20 C fails (the S17 class)", r["errors"])
w = {"id": "S17", "reason": "fix in B3 lane", "expires": "2026-11-30"}
r = run({"a.py": code}, [entry("a.py", basis_temp_c=20.0, waiver=w)])
check(not r["errors"] and len(r["warnings"]) == 1, "the same with an unexpired waiver passes and warns", (r["errors"], r["warnings"]))
r = run({"a.py": code}, [entry("a.py", basis_temp_c=20.0, waiver=dict(w, expires="2026-10-01"))])
check(n_err(r, "expired") == 1, "an expired waiver fails", r["errors"])
r = run({"a.py": code}, [entry("a.py", basis_temp_c=20.0, waiver=w)], fail_waived=True)
check(n_err(r, "still open") == 1, "--fail-waived fails while a waiver is open", r["errors"])
r = run({"a.py": code}, [entry("a.py", basis_temp_c=None)])
check(n_err(r, "numeric basis_temp_c") == 1, "a hot-conservative entry without a numeric basis fails", r["errors"])
r = run({"a.py": code}, [entry("a.py", direction="cold is conservative", basis_temp_c=20.0)])
check(not r["errors"], "'cold is conservative' at 20 C passes", r["errors"])
r = run({"a.py": code}, [entry("a.py", direction="cold is conservative", basis_temp_c=105.0)])
check(n_err(r, "NON-conservative") == 1, "'cold is conservative' at 105 C fails", r["errors"])
r = run({"a.py": code}, [entry("a.py", direction="sideways")])
check(n_err(r, "direction") == 1, "an unknown direction fails", r["errors"])
r = run({"a.py": code}, [entry("a.py", justification="")])
check(n_err(r, "justification") >= 1, "an entry without a justification fails", r["errors"])

# ---- both corners
both = SOLVER_HDR + "cold = kit.Net(pitch_mm=0.25)   # CORNER_COLD\nhot = kit.Net(pitch_mm=0.25, temp_c=125)   # CORNER_HOT\n"
e = entry("a.py", direction="both corners", markers=["CORNER_COLD", "CORNER_HOT"])
r = run({"a.py": both}, [e])
check(not r["errors"], "'both corners' that evaluates both passes", r["errors"])
r = run({"a.py": both.replace("# CORNER_COLD", "")}, [e])
check(n_err(r, "CORNER_COLD") == 1, "'both corners' that lost its cold evaluation fails", r["errors"])
r = run({"a.py": both}, [entry("a.py", direction="both corners", markers=["CORNER_HOT"])])
check(n_err(r, ">= 2") == 1, "'both corners' with fewer than two markers fails", r["errors"])

# ---- pins, stale entries, groups, derived
r = run({"a.py": code + "TEMP = 125.0\n"}, [entry("a.py", pin=r"TEMP = 125\.0")])
check(not r["errors"], "pin that matches passes", r["errors"])
r = run({"a.py": code + "TEMP = 100.0\n"}, [entry("a.py", pin=r"TEMP = 125\.0")])
check(n_err(r, "pin") == 1, "pin that no longer matches (basis drifted) fails", r["errors"])
r = run({"a.py": "print(1)\n"}, [entry("a.py")])
check(n_err(r, "none of the registered kinds") == 1, "an entry whose finding disappeared is stale and fails", r["errors"])
r = run({}, [entry("gone.py")])
check(n_err(r, "file is gone") == 1, "an entry for a missing file fails", r["errors"])
r = run({"a.py": code, "b.py": code}, [entry("a.py", files=["a.py", "b.py"])])
check(not r["errors"], "an entry with a `files` list covers several files", r["errors"])
r = run({"a.py": code, "b.py": code}, [entry("a.py"), entry("b.py", id="T-2"), dict(entry("a.py"), id="T-3")])
check(n_err(r, "two registry entries") + n_err(r, "covered by two") >= 1, "two entries on one file fail", r["errors"])
r = run({"d.py": "import json\nplane = json.load(open(f'plane-{tag}.json'))\n"},
        [entry("d.py", kinds=["derived"], pin=r"plane-\{tag\}\.json")])
check(not r["errors"], "a derived consumer with a matching pin passes", r["errors"])
r = run({"d.py": "import json\n"}, [entry("d.py", kinds=["derived"], pin=r"plane-\{tag\}\.json")])
check(n_err(r, "pin") == 1, "a derived consumer whose pin is gone fails", r["errors"])
r = run({"a.py": code + "x = 1.72e-8\n"}, [entry("a.py")])
check(n_err(r, "new non-explicit finding") == 1, "a new finding kind in a registered file fails", r["errors"])

# ---- real tree (CU_TEMP_ROOT overrides the unit root, for running a proposed copy outside the repo)
import os
ROOT = os.environ.get("CU_TEMP_ROOT") or g.UNIT
real_reg = json.loads((HERE / "cu_temp_registry.json").read_text())
r = g.check(ROOT, real_reg, today=TODAY)
check(not r["errors"] and r["n_files_scanned"] > 50,
      f"real tree + real registry passes ({r['n_files_scanned']} files, {r['n_registered']} registered, {len(r['warnings'])} waived)", r["errors"][:3])
# S17 waivers retired (DECISIONS 61 / 63): no waiver is left to expire, and the chain runs --fail-waived
check(not any(e.get("waiver") for e in real_reg["consumers"]), "real registry carries no waivers")
r = g.check(ROOT, real_reg, today="2027-01-01", fail_waived=True)
check(not r["errors"] and not r["warnings"], "real tree passes under --fail-waived, also after 2027-01-01", r["errors"][:3])
found = g.scan_source(SOLVER_HDR + "net = kit.Net(pitch_mm=0.1)\n")
check(found.get("net", {}).get("explicit") is False, "an injected Net() is flagged by the scanner the gate uses on the real tree")
reg4 = copy.deepcopy(real_reg)
reg4["consumers"] = [c for c in reg4["consumers"] if c["id"] != "CU-04"]
r = g.check(ROOT, reg4, today=TODAY)
check(any("run_board.py" in e and "UNREGISTERED" in e for e in r["errors"]), "real tree minus the run_board.py entry fails on run_board.py", r["errors"][:2])
reg5 = copy.deepcopy(real_reg)
for c in reg5["consumers"]:
    if c["id"] == "CU-06":
        c["markers"] = ["TA_HOT\\s*=\\s*105\\.0", "NO_SUCH_COLD_CORNER"]
r = g.check(ROOT, reg5, today=TODAY)
check(any("NO_SUCH_COLD_CORNER" in e for e in r["errors"]), "real f1_containment as 'both corners' fails when a corner marker is absent")
reg6 = copy.deepcopy(real_reg)
for c in reg6["consumers"]:
    if c["id"] == "CU-08":
        c["pin"] = "TEMP = 85\\.0"
r = g.check(ROOT, reg6, today=TODAY)
check(any("kelvin_plane.py" in e and "pin" in e for e in r["errors"]), "real kelvin_plane pinned to the wrong basis (85 C) fails")

print("\n%s" % ("all controls passed" if not fails else f"{fails} control(s) FAILED"))
sys.exit(1 if fails else 0)
