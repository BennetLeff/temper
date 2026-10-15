#!/usr/bin/env python3
"""Board-face heat-transfer coefficient that native-21 needs at 26 A and 28 A (temper-airflow-r1, step 1).

    python3 board_h_sweep.py [--workers 5]       # about 60 min on 4 cores -> runs/*.json, board-h-sweep.json

Drives the power-stage session's own B3 ratings model, unmodified, from a snapshot of codex/power-stage-integration at
c8665ceb0 (DECISIONS 55, board of record s42 = candidate 39), extracted with `git archive` into .ps-snapshot/ (gitignored;
`python3 board_h_sweep.py --snapshot` rebuilds it and copies the gitignored task-04 heat fields, which a4_fields.check()
then verifies against the snapshot's cache.json). The live worktree moved from s41 to s42 during the first attempt of
this run, so nothing is imported from the live tree:
  * b3-convergence/body_runs.run_case + thermal_body (body-level networks, fill-fraction copper, FET drain-lead ties)
    on run_study.GEOM (the s42 copper), the committed c28 heat file and the task-04 heat fields (a4_fields.check());
  * b3-ratings/fet_case.t_case for the FET tab temperatures (sink at the 88.6 C fan setpoint);
  * b3-ratings/b3_ratings_gate.run for the margins (estimate = Q(0.25) + 3|Q(0.25) - Q(0.5)| + (bay - 50)).
It reproduces their margins.json first (control: c22_h10 and c28_h10 at bay 55).

The one change, made by wrapping two functions in this process only (no file outside this folder is written):
  * forced convection on the TOP face (F.Cu side, z = 0) over a REGION: those cells get h_top instead of the
    still-air h 10; every other cell and the whole bottom face stay at 10;
  * the package networks of parts whose centre lies in the region (R5, the 2512 R_on gate resistors R10/R12/R18/R20,
    the 1206 pull-downs R53/R54/R57/R58) get their
    body-to-air conductance at h_top. The HF film caps C38-C41 keep the model's no-body-to-air path (an upper bound),
    so the airflow only reaches them through the board.
REGION "channel" = model x 0-90, y 7.0-23.5 mm: the open copper between the TO-247 bodies (front face y 6.9) and the
film-cap bodies (inner face y 23.7). That is the duct the change set builds; copper under part bodies gets no credit.

The air over the region is taken at bay-air temperature (55 or 61 C). The duct air is fresh push-hood air, which is
cooler than the bay, so this is conservative on the air temperature (delivery.py gives the air rise).
Bay 61: the FET tabs are pinned at the absolute setpoint temperature. Solves are made for each bay with the tab ties
relative to that bay (as run_basis.py does for 55).
Ceiling construction = run_basis.op_c22 with 26 A: I_t = 1.05 x ceiling, the TANK_ROWS of the c28 heat file scaled by
(I_t / 29.4)^2, I_line 11.1 A (run_basis's basis; OPEN-ITEMS S2 says 13.5 A moves gated rows <= 0.1 K).
Every gated row counts, including the 2512 gate-resistor terminal derating (candidate 39 is on the board now).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
PS = REPO / "worktrees/ps-integrate"               # git objects only (git archive), never the working tree
PS_COMMIT = "c8665ceb09c756582797fb3279d7a3db468ad0bc"
SNAP = HERE / ".ps-snapshot"
UNIT = SNAP / "zapote/power-stage-120v"
R5D = UNIT / "validation-results/04-board-current-thermal/round5-native21"
SNAP_PATHS = ["zapote/power-stage-120v/validation-results/04-board-current-thermal/round5-native21",
              "zapote/power-stage-120v/native-21/verification/native21s42-all-copper.json.gz",
              "zapote/power-stage-120v/native-21/stackup.json",
              "zapote/power-stage-120v/validation-results/05-resonant-tank-envelope/round6-full-power/scripts/board_side.py",
              "firmware/components/control/thermal_mgmt.h"]


def snapshot():
    """Rebuild .ps-snapshot from git objects at PS_COMMIT plus the gitignored task-04 fields (checked after)."""
    import shutil
    if SNAP.exists():
        shutil.rmtree(SNAP)
    SNAP.mkdir()
    arc = subprocess.run(["git", "-C", str(PS), "archive", PS_COMMIT, *SNAP_PATHS], capture_output=True, check=True).stdout
    subprocess.run(["tar", "-x", "-C", str(SNAP)], input=arc, check=True)
    src = PS / SNAP_PATHS[0] / "outputs"
    for f in src.glob("*.npz"):
        shutil.copy2(f, R5D / "outputs" / f.name)


if __name__ == "__main__" and ("--snapshot" in sys.argv or not SNAP.exists()):
    snapshot()

sys.path.insert(0, str(R5D / "b3-convergence"))
sys.path.insert(0, str(R5D / "b3-ratings"))
sys.path.insert(0, str(R5D))
import body_runs as br  # noqa: E402
import thermal_body as tb  # noqa: E402
import fet_case  # noqa: E402
import b3_ratings_gate as gate  # noqa: E402

RUNS = HERE / "runs"
H_STILL = 10.0
REGIONS = {"channel": (0.0, 90.0, 7.0, 23.5)}
H_TOPS = (10.0, 20.0, 35.0, 60.0, 100.0, 150.0)
CEILS = (26.0, 28.0)
BAYS = (55.0, 61.0)
C39_FIXED = ()                                # s42 carries candidate 39's 2512 gate resistors: every gated row counts
SOURCES = [R5D / "b3-convergence/thermal_body.py", R5D / "b3-convergence/body_runs.py",
           R5D / "b3-convergence/inputs/part-bodies.json", R5D / "b3/run_study.py", R5D / "b3/thermal.py",
           R5D / "b3/inputs/native21-board-heat-sources-c28.json", R5D / "b3-ratings/fet_case.py",
           R5D / "b3-ratings/b3_ratings_gate.py", R5D / "b3-ratings/run_basis.py", R5D / "b3-ratings/margins.json",
           R5D / "a4_fields.py", R5D / "outputs/cache.json",
           UNIT / "native-21/verification/native21s42-all-copper.json.gz",
           UNIT / "validation-results/05-resonant-tank-envelope/round6-full-power/scripts/board_side.py",
           SNAP / "firmware/components/control/thermal_mgmt.h"]

# ---------------------------------------------------------------- the two wrapped model functions (this process only)
_CTX: dict = {}
_assemble = tb.assemble
_build_parts = tb.build_network_parts
_OP_INPUTS = br.op_inputs


def assemble(board, k, thk_m, h, pitch_m, links):
    rows, cols, vals, diag, ids, conv = _assemble(board, k, thk_m, h, pitch_m, links)
    m = _CTX.get("mask")
    if m is not None:
        np_ = __import__("numpy")
        sel = ids[0][m & board]
        np_.add.at(diag, sel, (_CTX["h_top"] - h) * pitch_m * pitch_m)
    return rows, cols, vals, diag, ids, conv


def build_network_parts(*a, **kw):
    parts, omitted = _build_parts(*a, **kw)
    if _CTX.get("region"):
        x0, x1, y0, y1 = _CTX["region"]
        for p in parts:
            if p.g_air > 0 and x0 <= p.meta["x"] <= x1 and y0 <= p.meta["y"] <= y1:
                p.g_air = 1.0 / (p.r_top + 1.0 / (_CTX["h_top"] * p.meta["body_area_mm2"] * 1e-6))
                _CTX["credited"].append(p.ref)
    return parts, omitted


tb.assemble = assemble
tb.build_network_parts = build_network_parts


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def op_for(ceil: float) -> str:
    """c28 is the committed case; other ceilings follow run_basis.op_c22 with the heat file written here."""
    br.op_inputs = _OP_INPUTS                     # a reused worker may hold another ceiling's override
    if ceil == 28.0:
        return "c28"
    rs = br.rs
    name = f"c{int(ceil)}"
    i_t = 1.05 * ceil
    rs.OPS[name] = {"I_t": i_t, "I_line": 11.1, "parts": "nominal", "heat": "c28"}
    heat = json.loads(rs.HEAT_C28.read_text())
    k = (i_t / 29.4) ** 2
    for p in heat["parts"]:
        if p["ref"] in br.TANK_ROWS:
            p["watts_nominal"] *= k
            p["watts_worst"] *= k
    path = RUNS / f"heat_{name}.json"
    path.write_text(json.dumps(heat))
    c = (rs.cases(name), path, "nominal")
    br.op_inputs = lambda _op, _c=c: _c
    return name


def case_name(ceil, region, h_top, bay):
    return f"c{int(ceil)}_{region}_h{int(h_top)}_bay{int(bay)}"


def one(job):
    import numpy as np
    ceil, region, h_top, bay, pitch = job
    name = case_name(ceil, region, h_top, bay)
    op = op_for(ceil)
    brd = tb.Board(br.rs.GEOM, RUNS / "cache")
    nxg, nyg = brd.grid_n(pitch)
    xs = brd.xmin + (np.arange(nxg) + 0.5) * pitch
    ys = brd.ymin + (np.arange(nyg) + 0.5) * pitch
    x0, x1, y0, y1 = REGIONS[region]
    mask = ((xs >= x0) & (xs <= x1))[:, None] & ((ys >= y0) & (ys <= y1))[None, :]
    _CTX.clear()
    if h_top != H_STILL:
        _CTX.update(mask=mask, h_top=h_top, region=REGIONS[region], credited=[])
    leads = {"pad": "2", "g": tb.drain_lead_conductance(),
             "t_rise": {r: t - bay for r, t in fet_case.t_case(ceil).items()}}
    res, rise = br.run_case(brd, op, H_STILL, pitch, "fraction", "network", {}, None, None, True, True,
                            label=name, leads=leads, return_rise=True)
    board, _ = brd.window_arrays(pitch, 0, nxg, 0, nyg)
    extra_w = float((h_top - H_STILL) * (pitch * 1e-3) ** 2 * rise[0][mask & board].sum()) if h_top != H_STILL else 0.0
    b = res["balance"]
    b["convection_w"] += extra_w
    b["balance_w"] = b["source_w"] - (b["convection_w"] + b["body_air_w"] + b["boundary_flux_w"] + b["lead_sink_w"])
    b["balance_rel"] = b["balance_w"] / b["source_w"]
    res["board_sha256"] = brd.data["board_sha256"]
    res["airflow"] = {"region": region, "region_xy_mm": REGIONS[region], "h_top": h_top, "h_rest": H_STILL,
                      "region_cells_top": int((mask & board).sum()), "region_area_mm2": float((mask & board).sum() * pitch ** 2),
                      "region_top_convection_w": float(h_top * (pitch * 1e-3) ** 2 * rise[0][mask & board].sum()),
                      "region_mean_top_rise_k": float(rise[0][mask & board].mean()),
                      "body_air_credited": sorted(set(_CTX.get("credited", []))), "bay_c": bay,
                      "fet_tab_c": fet_case.t_case(ceil)}
    tag = f"{name}_p{str(pitch).replace('.', 'p')}"
    (RUNS / f"{tag}.json").write_text(json.dumps(res, indent=1) + "\n")
    return tag, round(b["balance_rel"], 12), res["runtime_s"]


def gated(rows, drop_c39=True):
    rows = [r for r in rows if r["gated"]]
    if drop_c39:
        rows = [r for r in rows if not r["item"].startswith(C39_FIXED)]
    return rows


def h_zero(pts):
    """Smallest h at which a margin series [(h, margin)] reaches 0, by linear interpolation; None if never."""
    if pts[0][1] >= 0:
        return H_STILL
    for (ha, ma), (hb, mb) in zip(pts, pts[1:]):
        if ma < 0 <= mb:
            return round(ha + (hb - ha) * (0 - ma) / (mb - ma), 1)
    return None


def summarise():
    out = {"cases": {}, "required_h_top": {}, "per_row_h_zero": {}}
    for ceil in CEILS:
        for bay in BAYS:
            series = {}
            for h in H_TOPS:
                c = case_name(ceil, "channel", h, bay)
                g = gated(gate.run(RUNS, [c], bay)["cases"][c])
                worst = min(g, key=lambda r: r["margin_k"])
                out["cases"][c] = {"ceil_A": ceil, "bay_c": bay, "h_top": h, "worst_gated": worst,
                                   "rows_under_25K": {r["item"]: r["margin_k"] for r in g if r["margin_k"] < 25},
                                   "balance_rel": json.loads((RUNS / f"{c}_p0p25.json").read_text())["balance"]["balance_rel"]}
                for r in g:
                    series.setdefault(r["item"], []).append((h, r["margin_k"]))
            key = f"c{int(ceil)}_bay{int(bay)}"
            worst_pts = [(h, out["cases"][case_name(ceil, "channel", h, bay)]["worst_gated"]["margin_k"]) for h in H_TOPS]
            need = h_zero(worst_pts)
            out["required_h_top"][key] = {"h_top_required": need, "worst_margin_by_h": worst_pts,
                                          "note": None if need else f"not reached by h_top {H_TOPS[-1]}"}
            out["per_row_h_zero"][key] = {item: {"h_zero": h_zero(pts), "margin_h10": pts[0][1], "margin_h_max": pts[-1][1]}
                                          for item, pts in sorted(series.items(), key=lambda kv: kv[1][0][1])
                                          if pts[0][1] < 0}
    out["ceiling_by_h"] = ceiling_map()
    return out


def ceiling_map():
    """The power stage's ceiling method (c39-gate-network/scripts/ceilings.py: margins linear in I_trip^2, zero crossing
    / 1.05) applied between this sweep's c26 (27.3 A trip) and c28 (29.4 A trip) solves at each h_top and bay.
    Below 26 A it is an extrapolation along the same line (the power stage interpolates c22-c28)."""
    a, b = (1.05 * 26.0) ** 2, (1.05 * 28.0) ** 2
    res = {}
    for bay in BAYS:
        for h in H_TOPS:
            m = {}
            for ceil, x in ((26.0, a), (28.0, b)):
                c = case_name(ceil, "channel", h, bay)
                for r in gated(gate.run(RUNS, [c], bay)["cases"][c]):
                    m.setdefault(r["item"], {})[x] = r["margin_k"]
            ceil_rows = {}
            for item, v in m.items():
                if len(v) != 2:
                    continue
                slope = (v[b] - v[a]) / (b - a)
                if slope >= 0:
                    continue
                x0 = a - v[a] / slope
                ceil_rows[item] = 0.0 if x0 <= 0 else round(x0 ** 0.5 / 1.05, 1)
            lim = min(ceil_rows, key=ceil_rows.get)
            res[f"bay{int(bay)}_h{int(h)}"] = {"all_gated_ceiling_A": ceil_rows[lim], "limiting_row": lim,
                                               "next_rows": dict(sorted(ceil_rows.items(), key=lambda kv: kv[1])[:5])}
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--summary-only", action="store_true")
    ap.add_argument("--snapshot", action="store_true", help="rebuild .ps-snapshot from git, then run")
    a = ap.parse_args()
    RUNS.mkdir(exist_ok=True)
    import a4_fields
    prov = {"ps_commit": PS_COMMIT, "branch": "codex/power-stage-integration", "board": "s42 (DECISIONS 55)",
            "sources_sha256": {str(p.relative_to(SNAP)): sha(p) for p in SOURCES},
            "sources_match_commit": all(subprocess.run(["git", "-C", str(PS), "cat-file", "-p",
                                                        f"{PS_COMMIT}:{p.relative_to(SNAP)}"], capture_output=True).stdout
                                        == p.read_bytes() for p in SOURCES)}
    if not a.summary_only:
        if not a4_fields.check():
            raise SystemExit(2)
        tb.Board(br.rs.GEOM, RUNS / "cache").fine()
        jobs = [(28.0, "channel", 10.0, 55.0, p) for p in (0.25, 0.5)]
        jobs = [(22.0, "channel", 10.0, 55.0, p) for p in (0.25, 0.5)] + jobs
        jobs += [(c, "channel", h, bay, p) for bay in BAYS for c in CEILS for h in H_TOPS for p in (0.25, 0.5)
                 if not (c == 28.0 and h == 10.0 and bay == 55.0)]
        jobs.sort(key=lambda j: j[4])                      # the slow 0.25 mm solves first
        with ProcessPoolExecutor(max_workers=a.workers) as ex:
            for tag, bal, rt in ex.map(one, jobs):
                print(f"  solved {tag}  balance_rel {bal:.1e}  {rt} s", flush=True)
    # control: reproduce the power stage's margins.json (c22_h10, c28_h10 at bay 55) from our own solves
    ref = json.loads((R5D / "b3-ratings/margins.json").read_text())
    ctrl = {}
    for ours, theirs in (("c22_channel_h10_bay55", "c22_h10"), ("c28_channel_h10_bay55", "c28_h10")):
        mine = {r["item"]: r["margin_k"] for r in gate.run(RUNS, [ours], 55.0)["cases"][ours]}
        th = {r["item"]: r["margin_k"] for r in ref["cases"][theirs]}
        diffs = [abs(mine[i] - th[i]) for i in th if i in mine]
        ctrl[theirs] = {"rows_compared": len(diffs), "max_abs_diff_K": max(diffs) if diffs else None,
                        "missing": [i for i in th if i not in mine][:5]}
    res = {"scope": __doc__.strip(), "provenance": prov, "control_vs_margins_json": ctrl, **summarise()}
    (HERE / "board-h-sweep.json").write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps({"control": ctrl, "required_h_top": {k: v["h_top_required"] for k, v in res["required_h_top"].items()}},
                     indent=1))


if __name__ == "__main__":
    main()
