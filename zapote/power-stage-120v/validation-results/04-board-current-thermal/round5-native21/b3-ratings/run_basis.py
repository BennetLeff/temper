#!/usr/bin/env python3
"""Compute the B3 ratings-gate basis solves on the current board and write margins.json for scorecard.py.

    python3 run_basis.py [--workers 4]     # about 9 min: three cases x (0.25 mm, 0.5 mm) body-level solves
        -> runs/<case>_p0p25.json, runs/<case>_p0p5.json (gitignored), margins.json, exit = gate exit
    python3 run_basis.py --cases c22_h10@61,c28_h10@61 --runs DIR --out FILE   # other cases / bays (a study)
    python3 run_basis.py --bay-c 61 --runs DIR --out FILE   # the pre-2026-10-15 form: c22 and c28 at one bay
    python3 run_basis.py --cases c28_h10_jet100@61,c28_h10_jet100a50@61 --runs DIR --out FILE   # airflow cases
    python3 run_basis.py --film-lead-only ...   # C38-C41 without their body-to-air path (the model to 2026-10-15)

Airflow cases (b3-ratings/jet-2026-10-15): CASE = c<ceiling>_h<h>_jet<h_top>[a<air C>] puts h_top on the top-face cells
of JET_REGION (below) and on the package networks centred in it, air at <air C> (default: the case's bay); the rest of
the board stays at h. The gate labels them role "airflow"; they never decide the release verdict. The default BASIS
has none.

The cases and their bays are b3_ratings_gate.BASIS (2026-10-15, after DECISIONS 55):
  c18_h10 at bay 61 C   the release case - the 18.0 A release ceiling at its 1.05 x trip (18.9 A), the enclosure's
                        worst bay with B3 heat; the b3_ratings release gate is this case's verdict;
  c22_h10, c28_h10 at bay 55 C   the ratchet cases (b3_laminate_margin_K / b3_rated_part_margin_K), kept so cards stay
                        comparable with s32 onward.
Each case is the c28 heat file with the tank-current rows (body_runs.TANK_ROWS) scaled by (1.05 ceiling / 29.4)^2 - the
construction of body_runs.op_inputs('der14') - and the A4 copper cases at run_study.cases() for that I_t.
Line current: every case at run_study.I_LINE_A (13.5 A, the firmware inlet bound; line-hold-2026-10-15), which moves
three inputs exactly as line-hold-2026-10-15/scripts/line_hold.py: the ac_l / ac_n copper (run_study.cases), L1's heat
row x (I_LINE_A / 11.1)^2 (the c28 file builds it at 11.1 A, make_heat_sources.C28_SCALE) and BR1's sink share in
fet_case.t_case(i_line=).
FET drain-lead path (thermal-refine 2026-10-15): each TO-247's drain pad is tied to its tab at the fet_case.t_case()
central case temperature through thermal_body.drain_lead_conductance() (IPW65R018CFD7 p.12 drawing, mid values). The tie
temperature is relative to the bay air, so each case is solved at its own bay, not shifted, and the gate checks that.
HF film caps C38-C41 (jet-2026-10-15): body-to-air path at the local h (thermal_body.film_body_g_air) with the weak 50 K/W
lead tie in the solve; the gated Top row is the strong-tie bound (thermal_body.FILM_HF_STRONG). --film-lead-only
reproduces the model before it (no body-to-air path).
Uses the committed body-level model in place (../b3-convergence/thermal_body.py + body_runs.py, fill-fraction copper and
datasheet package networks) on run_study.GEOM (the chain's current copper).
Note: b3-convergence/inputs/part-bodies.json is the stage-19b extraction; it carries to the s32 board unchanged in
footprint and position (checked 2026-10-15 against fab/positions-kicad.csv) - re-run extract_bodies.py if parts move.
"""
import argparse
import json
import os
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
CONV = HERE.parent / "b3-convergence"
sys.path.insert(0, str(CONV))
sys.path.insert(0, str(HERE))
import b3_ratings_gate as gate  # noqa: E402
import body_runs as br  # noqa: E402
import fet_case  # noqa: E402
import thermal_body as tb  # noqa: E402

rs = br.rs
RUNS = HERE / "runs"
I_LINE_A = rs.I_LINE_A                             # 13.5 A firmware inlet bound (run_study.py)
HEAT_C28_I_LINE_A = 11.1                           # the c28 heat file's L1 row is built at 11.1 A (make_heat_sources)
LEAD_G = tb.drain_lead_conductance()
# The jet region, the one definition every B3 airflow case uses: model / KiCad frame (y down), x 0-90, y 7.0-23.5 mm,
# inclusive, on cell centres and on the heat-row centres of the part bodies - the open top copper between the TO-247 front
# faces and the HF film-cap bodies, under temper-8d airflow-r1's jet box (sensor-c1-impulse-mining:output/
# temper-airflow-r1/board_h_sweep.py REGIONS["channel"]; README section 1, HANDOFF item 1: 8 x 3 mm jets, floor 6.0 mm
# above the board). native-21/layout/gates/jet_strip_height.py keeps the same rectangle clear of parts taller than 4 mm
# (its REGION; the jet-2026-10-15 study checks that the keep-out contains this region).
JET_REGION = (0.0, 90.0, 7.0, 23.5)
# legacy names kept for importers (line-hold-2026-10-15, c36 scripts): the ratchet pair and its bay
CASES = {c: (f"c{int(b['ceiling_a'])}", b["h"]) for c, b in gate.BASIS.items() if b["role"] == "ratchet"}
CEIL = {f"c{int(b['ceiling_a'])}": b["ceiling_a"] for b in gate.BASIS.values()}
BAY_C = 55.0


def i_trip(ceil):
    return 29.4 if ceil == 28.0 else 1.05 * ceil


def inputs(op, ceil, runs):
    """(A4 case string, heat json path, heat mode) for the ceiling `ceil` at I_LINE_A, written to runs/heat_<op>.json."""
    it = i_trip(ceil)
    rs.OPS[op] = {"I_t": it, "I_line": I_LINE_A, "parts": "nominal", "heat": "c28"}
    heat = json.loads(rs.HEAT_C28.read_text())
    k_t, k_l = (it / 29.4) ** 2, (I_LINE_A / HEAT_C28_I_LINE_A) ** 2
    for p in heat["parts"]:
        k = k_t if p["ref"] in br.TANK_ROWS else k_l if p["ref"] == "L1" else 1.0
        p["watts_nominal"] *= k
        p["watts_worst"] *= k
    path = Path(runs) / f"heat_{op}.json"
    tmp = path.with_name(f".{path.name}.{os.getpid()}")      # parallel jobs of one ceiling share this file: replace it
    tmp.write_text(json.dumps(heat))                          # atomically so no reader sees it half-written
    os.replace(tmp, path)
    return rs.cases(op), path, "nominal"


def region_for(case, bay, credit_refs=()):
    """thermal_body.TopRegion for an airflow case (None for still air): JET_REGION at h_top, air at air_c or the bay.
    credit_refs: bodies credited at h_top although centred outside JET_REGION (a sensitivity; --jet-credit-refs)."""
    jet = gate.case_jet(case)
    if jet is None:
        return None
    air = bay if jet["air_c"] is None else jet["air_c"]
    return tb.TopRegion(JET_REGION, jet["h_top"], air - bay, name="jet", credit_refs=credit_refs)


def one(job):
    name, case, ceil, h, bay, pitch, runs, sens, credit_refs = job
    op = case.split("_")[0]
    c = inputs(op, ceil, runs)
    br.op_inputs = lambda _op, _c=c: _c
    brd = tb.Board(rs.GEOM, RUNS / "cache")
    leads = {"pad": "2", "g": LEAD_G,
             "t_rise": {r: t - bay for r, t in fet_case.t_case(ceil, i_line=I_LINE_A).items()}}
    region = region_for(case, bay, credit_refs)
    res = br.run_case(brd, op, h, pitch, "fraction", "network", dict(sens), None, None, True, True, label=name,
                      leads=leads, region=region)
    res["board_sha256"] = brd.data["board_sha256"]
    res.update(bay_c=bay, i_line_a=I_LINE_A, i_t_a=i_trip(ceil), ceiling_a=ceil)
    if region is not None:
        res["region"]["air_c"] = bay + region.t_air_rise
    (Path(runs) / f"{name}.json").write_text(json.dumps(res, indent=1) + "\n")
    return name


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--cases", help="comma list of CASE[@BAY], CASE = c<ceiling>_h<h>[_jet<h_top>[a<air C>]] "
                                    "(default: gate.BASIS)")
    ap.add_argument("--bay-c", type=float, help="legacy: c22_h10 and c28_h10 at this bay (no release case)")
    ap.add_argument("--runs", default=str(RUNS))
    ap.add_argument("--out", default=str(HERE / "margins.json"))
    ap.add_argument("--film-lead-only", action="store_true",
                    help="C38-C41 without their body-to-air path (the model to 2026-10-15; a control)")
    ap.add_argument("--jet-credit-refs", default="",
                    help="comma list of part bodies credited at h_top in airflow cases although centred outside "
                         "JET_REGION (a sensitivity, e.g. C38,C39,C40,C41; recorded in the run files)")
    a = ap.parse_args()
    sens = {"film_lead_only": True} if a.film_lead_only else {}
    credit = tuple(r for r in a.jet_credit_refs.split(",") if r)
    if a.cases and a.bay_c is not None:
        raise SystemExit("run_basis: give --cases (with @bay) or --bay-c, not both")
    spec = a.cases or (f"c22_h10@{a.bay_c:g},c28_h10@{a.bay_c:g}" if a.bay_c is not None else
                       ",".join(f"{c}@{b['bay_c']:g}" for c, b in gate.BASIS.items()))
    cases = gate.parse_cases(spec, None)
    runs = Path(a.runs)
    # the task-04 heat fields are gitignored: after a merge they can belong to another board (DECISIONS 51)
    sys.path.insert(0, str(HERE.parent))
    import a4_fields
    if not a4_fields.check():
        raise SystemExit(2)
    RUNS.mkdir(exist_ok=True)
    runs.mkdir(parents=True, exist_ok=True)
    tb.Board(rs.GEOM, RUNS / "cache").fine()
    jobs = []
    for c, bay in cases.items():
        ceil, h = gate.case_ceiling_h(c)
        jobs += [(f"{c}_p{str(p).replace('.', 'p')}", c, ceil, h, bay, p, str(runs), sens, credit) for p in (0.25, 0.5)]
    with ProcessPoolExecutor(max_workers=max(1, min(a.workers, 4))) as ex:      # shared machine: at most 4
        for n in ex.map(one, jobs):
            print("  solved", n, flush=True)
    r = subprocess.run([sys.executable, str(HERE / "b3_ratings_gate.py"), "--runs", str(runs), "--out", a.out,
                        "--cases", ",".join(f"{c}@{b:g}" for c, b in cases.items())])
    raise SystemExit(r.returncode)


if __name__ == "__main__":
    main()
