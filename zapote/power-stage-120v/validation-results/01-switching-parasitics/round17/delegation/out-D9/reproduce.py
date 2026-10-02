#!/usr/bin/env python3
"""D9 frozen-head review: production-code fixtures, no FEM or SPICE solves.

Requires NumPy and meshio. Temporary fixtures stay under out-D9. Only expensive
solver calls are stubbed. Synthetic results demonstrate missing guarantees,
not the size of any error in the committed board results.
"""
from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import platform
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

import meshio
import numpy as np

HERE = Path(__file__).resolve().parent
ROUND = HERE.parents[1]
HEAD = "1f09223516cc37d00f73b5e5e6d33a0197d7a30d"
sys.dont_write_bytecode = True


def load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_result(path: Path, data: dict) -> None:
    path.write_text("RESULT " + json.dumps(data) + "\n")


def result(text: str) -> dict:
    return json.loads(next(line[7:] for line in text.splitlines() if line.startswith("RESULT ")))


RUNNER = load("d9_runner", ROUND / "d2/run_d2.py")
with patch.dict(sys.modules, {"run_d2": RUNNER}):
    GRID = load("d9_grid", ROUND / "d2/grid.py")


def grid_checks(root: Path) -> dict:
    options = root / "common/options.inc"
    options.parent.mkdir()
    options.write_text(".options reltol=1e-3\n")
    measurements = {"vds_ls_die_pk": 200., "vds_hs_die_pk": 200., "vgs_ls_die_max": 15.,
                    "vgs_hs_die_max": 15., "vgs_ls_die_min": -1., "vgs_hs_die_min": -1.,
                    "vgs_ls_off_max": 2., "vds_hs_at_on": 100., "vgs_ls_at_partner": 2.}
    calls = []

    def stub(*args: object, **kwargs: object) -> dict:
        calls.append(options.read_text())
        return {"aborted": False, "meas": measurements.copy()}

    case = ("S1", 170, 37, 0, 348, 10)
    with patch.object(RUNNER, "KIT", root), patch.object(RUNNER, "run", stub):
        first = GRID.one((case, np.eye(4).tolist(), root))
        options_before = sha(options)
        options.write_text(".options reltol=1e-6\n")
        options_after = sha(options)
        reused = GRID.one((case, np.eye(4).tolist(), root))
        assert len(calls) == 1 and reused == first and options_before != options_after
        changed = GRID.one((case, (2*np.eye(4)).tolist(), root))
        assert len(calls) == 2 and changed["identity"] != first["identity"]
        assert first["stress_pass"] and not first["task_pass"] and not first["zvs"]
        measurements["vgs_ls_off_max"] = 4.
        del measurements["vgs_ls_at_partner"]
        missing = GRID.one((("S1", 170, 37, 0, 450, 10), np.eye(4).tolist(), root))
        assert missing["off_gate_cause"] == "unknown"
    return {"options_sha_changed": True, "options_change_reused_case": reused == first,
            "identity_keys": sorted(first["identity"]), "changed_matrix_rerun": True,
            "non_zvs_nominal_stress_pass": first["stress_pass"],
            "non_zvs_nominal_task_pass": first["task_pass"],
            "missing_partner_label": missing["off_gate_cause"]}


def campaign_checks(root: Path) -> dict:
    campaign = load("d9_campaign", ROUND / "scripts/campaign.py")
    root.mkdir()
    tag = "legA-h1-e1p0"
    (root / f"{tag}.msh").write_text("synthetic cached mesh; solver calls stubbed\n")
    write_result(root / f"{tag}.log", {"tets": 1, "port_leak_A": [{"leak_A": 0}],
                 "ports": [{"physical": 10, "name": "P1_C38", "direction": [1,0,0], "k_A_per_m": 1}]})
    write_result(root / f"{tag}.columns.txt", {"inner_farfield_triangles": 0})
    write_result(root / f"{tag}.loops.txt", {"ports": [{"closed_loop": True}]})
    (root / f"{tag}-P1_C38.out").write_text(json.dumps({"converged": True,
        "inductance_nH": 20., "last_iteration": 100, "wall_s": 1, "tol": 1e-8}) + "\n")
    commands = []

    def fake_check(cmd: list[str], log: Path) -> int:
        commands.append(cmd)
        write_result(log, {})
        return 0

    def no_solve(*args: object, **kwargs: object) -> int:
        raise AssertionError("cached solve should have been reused in the counterexample")

    snapshots = []
    for tol, ranks, install in (("1e-8", "10", "/synthetic/elmer-a"), ("1e-12", "12", "/synthetic/elmer-b")):
        argv = ["campaign.py", str(root), "--cases", "1:1.0", "--elmer", install, "--tol", tol, "--np", ranks]
        with patch.object(sys, "argv", argv), patch.object(campaign, "run", fake_check), \
             patch.object(campaign, "solve_observed", no_solve), \
             patch.object(campaign.subprocess, "run", return_value=subprocess.CompletedProcess([], 1)), \
             contextlib.redirect_stdout(io.StringIO()):
            campaign.main()
        snapshots.append({"manifest": json.loads((root / "manifest-legA.json").read_text()),
                          "status": json.loads((root / "status.json").read_text())})
    assert snapshots[0]["manifest"] == snapshots[1]["manifest"]
    assert snapshots[1]["status"]["tol"] == 1e-12 and snapshots[1]["status"]["done"][0]["converged"]
    return {"manifest_equal_after_tol_np_elmer_change": True, "solver_calls": 0,
            "declared_tolerances": [s["status"]["tol"] for s in snapshots],
            "declared_ranks": [s["status"]["np"] for s in snapshots],
            "second_status_accepts_cached_converged_solve": True,
            "manifest_keys": sorted(snapshots[0]["manifest"])}


def extraction_checks(root: Path) -> dict:
    root.mkdir()
    msh = root / "declared.msh"
    # Real, but unrelated mesh: emitted provenance hashes this, never compares it
    # with the VTUs. No invalid-file loophole is needed for this demonstration.
    points = np.array([[0.,0.,0.],[1.,0.,0.],[0.,1.,0.],[0.,0.,1.]])
    cells = [("tetra", np.array([[0,1,2,3]]))]
    meshio.write(msh, meshio.Mesh(points * 2, cells), file_format="gmsh22", binary=False)
    write_result(msh.with_suffix(".log"), {"ports": [
        {"physical": 10+i, "name": f"P{i+1}", "direction": [1,0,0], "k_A_per_m": 1} for i in range(2)]})
    paths = []
    for i, vector in enumerate(([1e-6,0.,0.],[.5e-6,1e-6,0.])):
        run = root / f"p{i}"
        (run / "mesh").mkdir(parents=True)
        paths.append(run)
        (run / "case.sif").write_text(f"Boundary Condition 1\n  Target Boundaries(1) = {10+i}\n"
            "  Magnetic Field Strength 1 = Real 1\n  Magnetic Field Strength 2 = Real 0\n  Magnetic Field Strength 3 = Real 0\nEnd\n")
        meshio.write(run / "mesh/case.vtu", meshio.Mesh(points, cells,
            point_data={"magnetic flux density e": np.tile(vector, (4,1))}))
        energy = float(np.dot(vector, vector)) / (6*4e-7*np.pi) * 1e9
        run.with_suffix(".out").write_text(json.dumps({"inductance_nH": energy})+"\n")
    command = [sys.executable, str(ROUND / "scripts/inductance_matrix.py"), str(msh)]
    for i, run in enumerate(paths):
        command += ["--port", str(10+i), str(run)]
    baseline = result(subprocess.run(command, capture_output=True, text=True, check=True).stdout)
    mesh = meshio.read(paths[1] / "mesh/case.vtu")
    mesh.point_data["magnetic flux density e"] *= -1
    meshio.write(paths[1] / "mesh/case.vtu", mesh)
    flipped = result(subprocess.run(command, capture_output=True, text=True, check=True).stdout)
    assert baseline["L_nH"][0][1] == -flipped["L_nH"][0][1]
    assert baseline["port_identity"] == flipped["port_identity"]
    return {"unrelated_mesh_accepted": baseline["mesh_sha256"] == sha(msh),
            "unchanged_sif_reversed_vtu_accepted": True,
            "baseline_mutual_nH": baseline["L_nH"][0][1], "reversed_mutual_nH": flipped["L_nH"][0][1],
            "production_exit_codes": [0,0], "sif_identities_unchanged": True}


def matrix_checks(root: Path) -> dict:
    root.mkdir()
    ex = load("d9_extrapolate", ROUND / "scripts/extrapolate.py")
    names = ["P1_C38", "P2_C39", "P3_gate_high", "P4_gate_low"]
    unlabeled = root / "unlabeled.txt"
    write_result(unlabeled, {"L_nH": np.diag([40.,30.,20.,10.]).tolist()})
    assert RUNNER.read_L(str(unlabeled)) == ex.read_matrix(str(unlabeled), names).tolist()
    for label, value in (("m10", np.eye(4)*10), ("m20", np.eye(4)*10), ("target", np.eye(4)*20)):
        if label == "target":
            value[0,1] = 2  # nonsymmetric, yet symmetric part is positive definite
        write_result(root / f"{label}.txt", {"names": names, "L_nH": value.tolist()})
    cmd = [sys.executable, str(ROUND / "scripts/margin_correct.py")]
    for key in ("m10", "m20", "target", "out"):
        cmd += [f"--{key}", str(root / f"{key}.txt")]
    passed = subprocess.run(cmd, capture_output=True, text=True, check=True)
    accepted = result(passed.stdout)
    output = np.array(accepted["L0_nH"])
    assert not np.allclose(output, output.T)
    m10 = ROUND / "results/matrices/legA-h1-e1p0-m10.matrix.txt"
    m20 = ROUND / "results/matrices/legA-h1-e1p0-m20.matrix.txt"
    target = ROUND / "d2/legA-h0-lin12.matrix.txt"
    realcmd = [sys.executable, str(ROUND / "scripts/margin_correct.py"), "--m10", str(m10),
               "--m20", str(m20), "--target", str(target), "--out", str(root / "actual.txt")]
    actual = result(subprocess.run(realcmd, capture_output=True, text=True, check=True).stdout)
    return {"unlabeled_matrix_accepted_by_both_readers": True,
            "asymmetric_matrix_accepted_by_margin_cli": True,
            "synthetic_max_asymmetry_nH": float(abs(output-output.T).max()),
            "synthetic_symmetrized_min_eigenvalue_nH": accepted["min_eigenvalue_nH"],
            "actual_corrected_matrix_nH": actual["L0_nH"], "actual_correction_nH": actual["margin_correction_nH"],
            "actual_min_eigenvalue_nH": actual["min_eigenvalue_nH"],
            "actual_symmetric": bool(np.allclose(actual["L0_nH"], np.array(actual["L0_nH"]).T))}


def committed_checks() -> dict:
    folder = ROUND / "d2/results/grid-h0-lin12-v2"
    rows = [json.loads(line) for line in (folder / "results.jsonl").read_text().splitlines()]
    summary = GRID.summarize(rows)
    assert json.loads(json.dumps(summary)) == json.loads((folder / "summary.json").read_text())
    assert len({GRID.tag((r["case"], r["vbus"], r["il"], r["dir"], r["dt_ns"], r["esl_nH"])) for r in rows}) == len(rows)
    assert len(rows) == len(GRID.cases(None))
    assert all(json.loads((folder / "cases" / (GRID.tag((r["case"],r["vbus"],r["il"],r["dir"],r["dt_ns"],r["esl_nH"]))+".json")).read_text()) == r for r in rows)
    table = {s: {dt: {"pass": sum(r["task_pass"] for r in rows if r["case"]==s and r["dt_ns"]==dt),
                     "total": sum(r["case"]==s and r["dt_ns"]==dt for r in rows)} for dt in GRID.DT} for s in ("S1","S2","S3","S4")}
    ranges = {}
    for s, dt in (("S1",250),("S1",307),("S1",348),("S2",348),("S3",307),("S4",None)):
        subset = [r for r in rows if r["case"]==s and (dt is None or r["dt_ns"]==dt)]
        ranges[f"{s}_dt{dt}"] = {"offgate_range_V": [min(r["vgs_off_max"] for r in subset),max(r["vgs_off_max"] for r in subset)],
            "VDS_max_V": max(r["vds_pk"] for r in subset), "failure_rows": [r for r in subset if not r["task_pass"]] if s in ("S2","S3") else []}
    matrix = RUNNER.read_L(str(folder / "matrix_used.txt"))
    ident = GRID.identity(matrix)
    matches = {key: all(r["identity"].get(key)==value for r in rows) for key,value in ident.items() if key != "vendor_model"}
    build5 = load("d9_make_deck5", ROUND / "d2/make_deck5.py")
    assert build5.build() == (ROUND / "d2/leg_matrix5.cir").read_text()
    bulk = json.loads((ROUND / "d2/results/bulk-mode/summary.json").read_text())
    values = bulk["cases"]
    return {"summary_matches_saved": True, "all_case_files_match": True, "case_count": len(rows),
            "summary": summary, "pass_table": table, "ranges": ranges,
            "nonvendor_identity_matches_current": matches,
            "distinct_vendor_hashes": sorted({r["identity"]["vendor_model"] for r in rows}),
            "all_task_failures_include_offgate": all(not r["pass_off_gate"] for r in rows if not r["task_pass"]),
            "all_VDS_failures_are_S4": all(r["case"]=="S4" for r in rows if not r["pass_vds"]),
            "generated_5port_deck_matches": True,
            "bulk_slew_range_A_per_ns": [min(r["max_abs_didt_A_per_ns"]["bulk"] for r in values), max(r["max_abs_didt_A_per_ns"]["bulk"] for r in values)],
            "bulk_estimate_range_V": [min(r[g]["bulk_estimate_V"] for r in values for g in ("gate_high","gate_low")), max(r[g]["bulk_estimate_V"] for r in values for g in ("gate_high","gate_low"))]}



def pair_checks(root: Path) -> dict:
    root.mkdir()
    source = (ROUND / "scripts/pair_check.sh").read_text()
    # Execute the production embedded comparator, not the shell's solver/deletes.
    marker = '  python3 - "$TAG" "$i" "$j" "$rd.out" <<' + "'PY'\n"
    comparator = source.split(marker, 1)[1].split("\nPY", 1)[0]
    tag = root / "synthetic"
    write_result(Path(str(tag)+".matrix.txt"), {"ports": ["12","13"], "L_nH": [[20.,-1.],[-1.,20.]]})
    both = root / "both.out"
    both.write_text(json.dumps({"converged": False, "inductance_nH": 42.})+"\n")
    capture = io.StringIO()
    with patch.object(sys, "argv", ["-", str(tag), "12", "13", str(both)]), contextlib.redirect_stdout(capture):
        exec(compile(comparator, "pair_check.sh embedded comparator", "exec"), {})
    data = json.loads(capture.getvalue().split("PAIR ",1)[1])
    assert not data["same_sign"]
    return {"unconverged_opposite_sign_comparison_returns_normally": True,
            "synthetic_L_both_nH": data["L_both_nH"], "synthetic_M_energy_nH": data["M_energy_nH"],
            "synthetic_M_matrix_nH": data["M_matrix_nH"], "same_sign": data["same_sign"]}


def bulk_geometry() -> dict:
    board = ROUND.parents[2] / "native-17/section.kicad_pcb"
    blocks = board.read_text().split('\n\t(footprint ')
    c6 = next(b for b in blocks if '(property "Reference" "C6"' in b)
    match = re.search(r'\n\t\t\(at ([^)]*)\)', c6)
    assert match
    x,y,angle = map(float, match[1].split())
    assert angle == 90.0  # exact cardinal permutation, no trig convention ambiguity
    pads = {}
    for number, at, net in re.findall(r'\(pad "([1-4])"[^\n]*\n\s*\(at ([^)]*)\).*?\(net "([^"\n]*)"\)', c6, re.S):
        dx,dy,*_ = map(float, at.split())
        pads[number] = {"world_mm": [x+dy,y-dx], "net": net}
    closures = json.loads((ROUND/"closures-legA5.json").read_text())
    p5 = next(p for p in closures if p["name"] == "P5_C6_bulk")
    assert p5["a"] == pads["1"]["world_mm"] and p5["b"] == pads["3"]["world_mm"]
    assert pads["1"]["net"] == "bus_p" and pads["3"]["net"] == "hv_ret"
    return {"board_sha256": sha(board), "C6_pads": pads, "P5_matches_inner_pads": True,
            "A5_default_crop_max_x_mm": 174.35+10,
            "outer_pad_centers_outside_default_crop": [k for k,v in pads.items() if v["world_mm"][0] > 174.35+10]}


def main() -> None:
    sources = ["scripts/campaign.py", "scripts/inductance_matrix.py", "scripts/extrapolate.py", "scripts/margin_correct.py",
               "scripts/pair_check.sh", "scripts/mesh25d_hybrid.py", "d2/grid.py", "d2/run_d2.py", "d2/bulk_mode.py",
               "d2/leg_matrix5.cir", "d2/make_deck5.py", "closures-legA5.json", "d2/results/grid-h0-lin12-v2/results.jsonl"]
    with tempfile.TemporaryDirectory(dir=HERE) as tmp:
        root = Path(tmp)
        evidence = {"reviewed_head": HEAD, "scope": "synthetic fixtures plus arithmetic replay; no hardware-error estimate",
                    "runtime": {"python": platform.python_version(), "numpy": np.__version__, "meshio": meshio.__version__},
                    "source_sha256": {name: sha(ROUND/name) for name in sources},
                    "grid": grid_checks(root), "campaign": campaign_checks(root/"campaign"),
                    "extraction": extraction_checks(root/"extract"), "matrices": matrix_checks(root/"matrices"),
                    "committed": committed_checks(), "pair": pair_checks(root/"pair"), "bulk_geometry": bulk_geometry()}
    print(json.dumps(evidence, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
