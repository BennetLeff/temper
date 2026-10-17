#!/usr/bin/env python3
"""B3 jet sweep on the supported airflow case (b3-ratings/jet-2026-10-15; OPEN-ITEMS S2 board side (a) and (b)).

    python3 jet_sweep.py solve [--workers 3] [--bays 55,61]   # run_basis.py -> ../../runs/jet-2026-10-15/{main,capjet}/bay<B>
    python3 jet_sweep.py summary                    # -> ../jet-sweep.json (committed), prints the tables
    python3 jet_sweep.py solve-air15 [--workers 3]  # 28 A at bay 55 / 61 with the film_hf default air (bay + 15 K)

Basis note (2026-10-15, after cap-air.json): main and capjet were solved with C38-C41 at bay air, the model of
eabef510a. thermal_body.FILM_HF_AIR_RISE_K then put the cap bodies' air at bay + 15 K. `air15` re-solves the 28 A
points on that default; the c26 rows and the ceiling-vs-h table stay on the bay-air basis (superseded at 28 A by air15).
capjet credits all four caps to the jet region, whose air is the bay, so it does not change.

What is solved (each case at 0.25 and 0.5 mm, the gate's two meshes; every case at its own bay, I_line 13.5 A,
FET tab ties from fet_case, C38-C41 with their body-to-air path):
  main    c26 and c28 x bay 55 and 61 C x h_top 10 / 35 / 60 / 100 W/m2K on run_basis.JET_REGION (the top-face cells
          and the bodies centred in it, air at the bay; every other cell and the bottom face at h 10). C38-C41 are
          centred at y 28.2, outside the region, so their bodies stay at h 10: the conservative reading.
  capjet  the same cases at h_top 35 / 60 / 100 with C38-C41's bodies also at h_top (run_basis --jet-credit-refs):
          the optimistic bound if the spent jet air washes the cap bodies (the jet box ends 1.2 mm from them).
Summary: per case the gated rows (b3_ratings_gate.run); the required h_top per ceiling and bay (smallest h at which every
gated row is >= 0, linear between grid points); the per-row h at zero; the ceiling-vs-h table by the c36 I_trip^2 method
(c39-gate-network/scripts/ceilings.py, here between the c26 (27.3 A trip) and c28 (29.4 A trip) solves); controls.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
STUDY = HERE.parent
B3R = STUDY.parent
UNIT = B3R.parents[3]
sys.path.insert(0, str(B3R))
sys.path.insert(0, str(B3R.parent / "b3-convergence"))
sys.path.insert(0, str(UNIT / "native-21/layout/gates"))
sys.path.insert(0, str(UNIT / "validation-results/11-candidates/c39-gate-network/scripts"))
import b3_ratings_gate as gate  # noqa: E402
import run_basis as rb  # noqa: E402
import jet_strip_height as jsh  # noqa: E402
import ceilings as c36  # noqa: E402

RUNS = B3R / "runs/jet-2026-10-15"
CEILS = (26.0, 28.0)
BAYS = (55.0, 61.0)
H_TOPS = (10.0, 35.0, 60.0, 100.0)
CAPS = ("C38", "C39", "C40", "C41")
# temper-8d airflow-r1 (sensor-c1-impulse-mining:output/temper-airflow-r1/README.md section 1, board-h-sweep.json):
# s42, I_line 11.1 A, film caps lead-only (no body-to-air path), h_top grid 10/20/35/60/100/150.
AIRFLOW_R1 = {"required_h_top": {"c26_bay55": 52.9, "c26_bay61": 82.1, "c28_bay55": 73.2, "c28_bay61": 97.2},
              "ceiling_A": {"bay55": {10: 19.9, 35: 23.9, 60: 26.9, 100: 30.5},
                            "bay61": {10: 18.2, 35: 22.2, 60: 25.0, 100: 28.5}}}


def case(ceil, h_top):
    return f"c{int(ceil)}_h10_jet{int(h_top)}"


def rdir(tag, bay):
    """Run files are named by case, so each bay is solved into its own folder."""
    return RUNS / tag / f"bay{int(bay)}"


def solve(workers, bays):
    for bay in bays:
        main = [f"{case(c, h)}@{bay:g}" for c in CEILS for h in H_TOPS]
        cap = [f"{case(c, h)}@{bay:g}" for c in CEILS for h in H_TOPS if h > 10]
        for tag, cases, extra in (("main", main, []), ("capjet", cap, ["--jet-credit-refs", ",".join(CAPS)])):
            runs = rdir(tag, bay)
            runs.mkdir(parents=True, exist_ok=True)
            cmd = [sys.executable, str(B3R / "run_basis.py"), "--workers", str(workers), "--cases", ",".join(cases),
                   "--runs", str(runs), "--out", str(runs / "margins-jet.json"), *extra]
            print(" ".join(cmd), flush=True)
            r = subprocess.run(cmd)
            if r.returncode not in (0, 1):            # 1 = some gated row < 0, expected at low h_top
                raise SystemExit(f"run_basis failed ({r.returncode}) on {tag} bay {bay:g}")


def solve_air15(workers):
    for bay in BAYS:
        runs = rdir("air15", bay)
        runs.mkdir(parents=True, exist_ok=True)
        cases = [f"{case(28.0, h)}@{bay:g}" for h in H_TOPS]
        r = subprocess.run([sys.executable, str(B3R / "run_basis.py"), "--workers", str(workers), "--cases",
                            ",".join(cases), "--runs", str(runs), "--out", str(runs / "margins-jet.json")])
        if r.returncode not in (0, 1):
            raise SystemExit(f"run_basis failed ({r.returncode}) on air15 bay {bay:g}")


def gated(tag, c, bay):
    # these runs are on 20 C copper (the sweep predates the hot-copper fixed point, OPEN-ITEMS S17): a cold record
    return [r for r in gate.run(rdir(tag, bay), [f"{c}@{bay:g}"], allow_cold_copper=True)["cases"][c] if r["gated"]]


def h_zero(pts):
    """Smallest h at which a margin series [(h, margin)] reaches 0, linear between grid points; None if never."""
    if pts[0][1] >= 0:
        return pts[0][0]
    for (ha, ma), (hb, mb) in zip(pts, pts[1:]):
        if ma < 0 <= mb:
            return round(ha + (hb - ha) * (0 - ma) / (mb - ma), 1)
    return None


def ceiling_pair(m_a, m_b, i_a, i_b):
    """c36's ceilings.ceiling() with the pair's trip currents as arguments (margins linear in I_trip^2)."""
    a, b = i_a ** 2, i_b ** 2
    slope = (m_b - m_a) / (b - a)
    if slope >= 0:
        return None
    x = a - m_a / slope
    return 0.0 if x <= 0 else round((x ** 0.5) / 1.05, 1)


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def summary():
    out = {"scope": __doc__.strip(), "region": {"xy_mm": list(rb.JET_REGION),
                                                "jet_strip_keepout_xy_mm": list(jsh.REGION),
                                                "keepout_contains_region": (jsh.REGION[0] <= rb.JET_REGION[0] and
                                                                            rb.JET_REGION[1] <= jsh.REGION[1] and
                                                                            jsh.REGION[2] <= rb.JET_REGION[2] and
                                                                            rb.JET_REGION[3] <= jsh.REGION[3])},
           "cases": {}, "required_h_top": {}, "per_row_h_zero": {}, "ceiling_by_h": {}, "capjet": {}}
    # ---- controls
    # (1) the c36 ceiling with the pair as arguments reproduces ceilings.ceiling on the c22 / c28 pair
    probe = [(-6.0, -30.0), (1.1, -27.8), (25.0, -5.0)]
    ctl1 = all(ceiling_pair(a, b, c36.I22, c36.I28) == c36.ceiling(a, b) for a, b in probe)
    # (2) a region at h_top 10 is the still-air model: c28_h10_jet10 @ 55 against the committed margins.json c28_h10
    ref = json.loads((B3R / "margins.json").read_text())
    # (the committed margins.json is on the film_hf default air since FILM_HF_AIR_RISE_K: compare it with air15's run)
    ctl_dir = rdir("air15", 55) if (rdir("air15", 55) / f"{case(28, 10)}_p0p5.json").exists() else rdir("main", 55)
    mine = {r["item"]: r["margin_k"] for r in gate.run(ctl_dir, [f"{case(28, 10)}@55"], allow_cold_copper=True)["cases"][case(28, 10)]}
    th = {r["item"]: r["margin_k"] for r in ref["cases"]["c28_h10"]}
    d = [abs(mine[i] - th[i]) for i in th if i in mine]
    out["controls"] = {"ceiling_pair_reproduces_ceilings_py": ctl1,
                       "jet10_vs_margins_json_c28_h10": {"runs": ctl_dir.parent.name, "rows": len(d), "missing": sorted(set(th) - set(mine)),
                                                         "max_abs_diff_K": max(d) if d else None}}
    # ---- per case, required h_top, per-row h at zero
    for tag, hs in (("main", H_TOPS), ("capjet", H_TOPS)):
        for ceil in CEILS:
            for bay in BAYS:
                series, worst_pts = {}, []
                for h in hs:
                    rr = "capjet" if (tag == "capjet" and h > 10) else "main"      # h 10: no jet, the caps alike
                    c = case(ceil, h)
                    g = gated(rr, c, bay)
                    w = min(g, key=lambda r: r["margin_k"])
                    worst_pts.append((h, w["margin_k"]))
                    for r in g:
                        series.setdefault(r["item"], []).append((h, r["margin_k"]))
                    if tag == "main":
                        out["cases"][f"{c}@{bay:g}"] = {"ceil_A": ceil, "bay_c": bay, "h_top": h, "worst_gated": w,
                                                        "caps": {r["item"].split(":")[0]: r["margin_k"] for r in g
                                                                 if r["item"][:3] in CAPS},
                                                        "rows_under_10K": {r["item"]: r["margin_k"] for r in g
                                                                           if r["margin_k"] < 10}}
                key = f"c{int(ceil)}_bay{int(bay)}"
                need = h_zero(worst_pts)
                rec = {"h_top_required": need, "worst_margin_by_h": worst_pts,
                       "note": None if need is not None else f"not reached by h_top {hs[-1]:g}"}
                rows = {item: {"h_zero": h_zero(pts), "margin_h10": pts[0][1], "margin_h_max": pts[-1][1]}
                        for item, pts in sorted(series.items(), key=lambda kv: kv[1][0][1]) if pts[0][1] < 0}
                if tag == "main":
                    out["required_h_top"][key] = rec
                    out["per_row_h_zero"][key] = rows
                else:
                    out["capjet"].setdefault("required_h_top", {})[key] = rec
                    out["capjet"].setdefault("per_row_h_zero", {})[key] = rows
    # ---- ceiling vs h (c36 I_trip^2 method on the c26 / c28 pair)
    for tag in ("main", "capjet"):
        tab = {}
        for bay in BAYS:
            for h in H_TOPS:
                rr = "capjet" if (tag == "capjet" and h > 10) else "main"
                m = {}
                for ceil in CEILS:
                    for r in gated(rr, case(ceil, h), bay):
                        m.setdefault(r["item"], {})[ceil] = r["margin_k"]
                rows = {k: ceiling_pair(v[26.0], v[28.0], 1.05 * 26.0, 1.05 * 28.0) for k, v in m.items() if len(v) == 2}
                rows = {k: v for k, v in rows.items() if v is not None}
                lim = min(rows, key=rows.get)
                tab[f"bay{int(bay)}_h{int(h)}"] = {"all_gated_ceiling_A": rows[lim], "limiting_row": lim,
                                                   "next_rows": dict(sorted(rows.items(), key=lambda kv: kv[1])[:5])}
        if tag == "main":
            out["ceiling_by_h"] = tab
        else:
            out["capjet"]["ceiling_by_h"] = tab
    # ---- 28 A on the film_hf default air (bay + 15 K), if solved
    if all((rdir("air15", b) / f"{case(28.0, 100)}_p0p5.json").exists() for b in BAYS):
        a15 = {"basis": "C38-C41 body air at bay + thermal_body.FILM_HF_AIR_RISE_K (15 K); caps outside the jet region",
               "required_h_top": {}, "per_row_h_zero": {}, "cases": {}}
        for bay in BAYS:
            series, worst_pts = {}, []
            for h in H_TOPS:
                g = gated("air15", case(28.0, h), bay)
                w = min(g, key=lambda r: r["margin_k"])
                worst_pts.append((h, w["margin_k"]))
                a15["cases"][f"{case(28.0, h)}@{bay:g}"] = {"worst_gated": w, "caps": {
                    r["item"].split(":")[0]: r["margin_k"] for r in g if r["item"][:3] in CAPS}}
                for r in g:
                    series.setdefault(r["item"], []).append((h, r["margin_k"]))
            key = f"c28_bay{int(bay)}"
            need = h_zero(worst_pts)
            a15["required_h_top"][key] = {"h_top_required": need, "worst_margin_by_h": worst_pts,
                                          "bay_air_basis": out["required_h_top"][key]["h_top_required"]}
            a15["per_row_h_zero"][key] = {item: {"h_zero": h_zero(pts), "margin_h10": pts[0][1]}
                                          for item, pts in sorted(series.items(), key=lambda kv: kv[1][0][1])
                                          if pts[0][1] < 0}
        out["air15"] = a15
    out["airflow_r1"] = AIRFLOW_R1
    sources = [B3R / "run_basis.py", B3R / "b3_ratings_gate.py", B3R / "fet_case.py", B3R / "margins.json",
               B3R.parent / "b3-convergence/thermal_body.py", B3R.parent / "b3-convergence/body_runs.py",
               B3R.parent / "b3/run_study.py", B3R.parent / "b3/inputs/native21-board-heat-sources-c28.json",
               UNIT / "native-21/layout/gates/jet_strip_height.py", Path(__file__)]
    b25 = json.loads((rdir("main", 55) / f"{case(28, 10)}_p0p25.json").read_text())
    out["provenance"] = {"board_sha256": b25["board_sha256"], "i_line_a": b25["i_line_a"],
                         "git_head": subprocess.run(["git", "-C", str(UNIT), "rev-parse", "HEAD"], capture_output=True,
                                                    text=True).stdout.strip(),
                         "sources_sha256": {str(p.relative_to(UNIT)): sha(p) for p in sources}}
    (STUDY / "jet-sweep.json").write_text(json.dumps(out, indent=1) + "\n")
    if "air15" in out:
        print("air15 required h_top:", {k: (v["h_top_required"], v["bay_air_basis"])
                                        for k, v in out["air15"]["required_h_top"].items()})
    print(json.dumps({"controls": out["controls"],
                      "required_h_top": {k: v["h_top_required"] for k, v in out["required_h_top"].items()},
                      "required_h_top_capjet": {k: v["h_top_required"] for k, v in out["capjet"]["required_h_top"].items()},
                      "ceiling_by_h": {k: (v["all_gated_ceiling_A"], v["limiting_row"]) for k, v in out["ceiling_by_h"].items()},
                      "ceiling_by_h_capjet": {k: (v["all_gated_ceiling_A"], v["limiting_row"])
                                              for k, v in out["capjet"]["ceiling_by_h"].items()}}, indent=1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=("solve", "solve-air15", "summary"))
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--bays", default=",".join(f"{b:g}" for b in BAYS))
    a = ap.parse_args()
    if a.what == "solve-air15":
        solve_air15(a.workers)
    if a.what == "solve":
        solve(a.workers, [float(b) for b in a.bays.split(",")])
    summary()


if __name__ == "__main__":
    main()
