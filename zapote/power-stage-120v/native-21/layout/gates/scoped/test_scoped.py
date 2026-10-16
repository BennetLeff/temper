#!/usr/bin/env python3
"""Controls for the scoped-chain planner (scoped_lib.plan) and the path classifier.

    python3 -I test_scoped.py
"""
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import scoped_lib as L  # noqa: E402

R5 = "validation-results/04-board-current-thermal/round5-native21"
SAME = {s: "k" for s in L.KEYED + ["necks", "ocp_pickup", "audit_rs", "core_barrier"]}


def keys(**diff):
    k = dict(SAME)
    k.update(diff)
    return k


def run(paths, cand=None, rebuilt=True, tag=None):
    pl = L.plan(paths, SAME, cand or SAME, None, rebuilt_board_differs=rebuilt, cand_tag=tag)
    return pl["mode"], {s: d["do"] for s, d in pl["steps"].items()}


CASES = []


def case(f):
    CASES.append(f)
    return f


@case
def unknown_path_is_full():
    m, _ = run(["native-21/some-new-dir/x.json"])
    assert m == "FULL", m


@case
def stackup_is_full():
    assert run(["native-21/stackup.json"])[0] == "FULL"


@case
def chain_change_is_full():
    assert run(["native-21/layout/gates/chain.sh"])[0] == "FULL"


@case
def copper_rebuilds_and_reruns_safety_gates():
    m, d = run(["native-21/layout/copper.json"], cand=keys(task04="x", b3_study="x", ceiling_sweep="x", b3_ratings="x"))
    assert m == "REBUILD" and all(d[s] == "RUN" for s in ("build", "d5", "core_barrier", "task04", "b3_study", "b3_ratings")), d


@case
def parts_only_reuses_thermal_by_key():
    m, d = run(["native-21/frozen/default.csv", "native-21/frozen/resolved-components.json"])
    assert m == "REBUILD" and d["build"] == "RUN" and d["core_barrier"] == "RUN", d
    assert all(d[s] == "REUSE" for s in ("task04", "b3_study", "ceiling_sweep", "b3_ratings")), d


@case
def ratings_script_runs_ratings_only():
    m, d = run([f"{R5}/b3-ratings/b3_ratings_gate.py"], rebuilt=False)
    assert m == "REUSE-BUILD" and d["b3_ratings"] == "RUN" and d["task04"] == "REUSE" and d["b3_study"] == "REUSE", d
    assert d["build"] == "REUSE" and d["core_barrier"] == "REUSE" and d["fab"] == "RUN", d


@case
def firmware_fan_law_reaches_ratings():
    _, d = run(["@repo/firmware/components/control/thermal_mgmt.h"], rebuilt=False)
    assert d["b3_ratings"] == "RUN" and d["task04"] == "REUSE", d


@case
def other_firmware_runs_nothing_expensive():
    m, d = run(["@repo/firmware/main/state_handlers.c"], rebuilt=False)
    assert m == "REUSE-BUILD" and all(d[s] == "REUSE" for s in L.KEYED), d


@case
def task04_rerun_propagates():
    _, d = run([f"{R5}/run_cases.py"], rebuilt=False)
    assert all(d[s] == "RUN" for s in ("task04", "b3_study", "ceiling_sweep", "b3_ratings")), d


@case
def b3_on_rebuilt_board_forces_task04():
    _, d = run(["native-21/frozen/default.csv", f"{R5}/b3/thermal.py"])
    assert d["b3_study"] == "RUN" and d["task04"] == "RUN", d


@case
def b3_on_same_board_keeps_task04():
    _, d = run([f"{R5}/b3/thermal.py"], rebuilt=False)
    assert d["b3_study"] == "RUN" and d["b3_ratings"] == "RUN" and d["task04"] == "REUSE", d


@case
def key_change_alone_reruns():
    _, d = run(["native-21/frozen/default.csv"], cand=keys(b3_ratings="other"))
    assert d["b3_ratings"] == "RUN" and d["task04"] == "REUSE", d


@case
def docs_and_records_run_cheap_steps_only():
    m, d = run(["DECISIONS.md", "validation-results/11-candidates/c99-x/README.md", "validation-results/13-coupling/results/x.json"], rebuilt=False)
    assert m == "REUSE-BUILD" and d["card"] == "RUN" and all(d[s] == "REUSE" for s in L.KEYED + ["build", "core_barrier", "d5"]), d


@case
def manual_step_stale_unless_provided_or_key_holds():
    _, d = run(["validation-results/02-protection-timing/shoot-through-f1/f1_containment.py"], rebuilt=False)
    assert d["necks"] == "STALE", d
    _, d = run(["validation-results/02-protection-timing/shoot-through-f1/s44_necks.json"], rebuilt=False, tag="native21s44")
    assert d["necks"] == "RUN", d
    _, d = run(["native-21/layout/copper.json"], cand=keys(necks="moved"))
    assert d["necks"] == "STALE" and d["ocp_pickup"] == "REUSE", d


@case
def globs():
    assert L.classify_path("validation-plan/enclosure-fit/native21-jet-strip.json")["class"] == "output"
    assert L.classify_path(f"{R5}/b3-ratings/margins.json")["class"] == "output"
    assert L.classify_path(f"{R5}/b3-ratings/refine-2026-10-15/scripts/common.py")["class"] == "not_read"
    assert L.classify_path("native-21/layout/gates/test_spine_lock.py")["class"] == "test"
    assert L.classify_path("native-21/layout/gates/new_gate.py")["class"] == "unknown"


@case
def run_study_tag_rewrite_is_not_a_change():
    a = b'GEOM = UNIT / "native-21/verification/native21s42-all-copper.json.gz"\n'
    b = b'GEOM = UNIT / "native-21/verification/native21s43-all-copper.json.gz"\n'
    p = f"{R5}/b3/run_study.py"
    assert L._normalised(p, a) == L._normalised(p, b)


fails = 0
for f in CASES:
    try:
        f()
        print("PASS", f.__name__)
    except AssertionError as e:
        fails += 1
        print("FAIL", f.__name__, str(e)[:300])
print(f"{len(CASES) - fails} / {len(CASES)} controls pass")
raise SystemExit(1 if fails else 0)
