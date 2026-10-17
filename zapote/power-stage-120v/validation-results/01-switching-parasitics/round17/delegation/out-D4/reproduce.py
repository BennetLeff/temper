#!/usr/bin/env python3
"""D4 review evidence. Executes reviewed functions; never runs FEM or SPICE.

Requires numpy and meshio. Writes only transient fixtures under this folder;
JSON evidence goes to stdout. Synthetic values demonstrate failure modes,
not measured board errors. Run with PYTHONDONTWRITEBYTECODE=1.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import platform
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
sys.dont_write_bytecode = True


def load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def grid_checks() -> dict:
    runner = load("review_run_d2", ROUND / "d2/run_d2.py")
    with patch.dict(sys.modules, {"run_d2": runner}):
        grid = load("review_grid", ROUND / "d2/grid.py")
    measurements = {
        "vds_ls_die_pk": 200.0, "vds_hs_die_pk": 200.0,
        "vgs_ls_die_max": 15.0, "vgs_hs_die_max": 15.0,
        "vgs_ls_die_min": -1.0, "vgs_hs_die_min": -1.0,
        "vgs_ls_off_max": 2.0, "vds_hs_at_on": 100.0,
        "vgs_ls_at_partner": 2.0,
    }
    calls = []

    def fake_run(*args: object, **kwargs: object) -> dict:
        calls.append(True)
        return {"aborted": False, "meas": measurements.copy()}

    case = ("S1", 170, 37, 0, 348, 10)
    with tempfile.TemporaryDirectory(dir=HERE) as tmp, patch.object(runner, "run", fake_run):
        out = Path(tmp)
        first = grid.one((case, np.eye(4).tolist(), out))
        resumed = grid.one((case, (100 * np.eye(4)).tolist(), out))
        measurements["vgs_ls_off_max"] = 4.0
        measurements.pop("vgs_ls_at_partner")
        missing = grid.one((("S1", 170, 37, 0, 450, 10), np.eye(4).tolist(), out))
    assert first["pass"] and not first["zvs"]
    assert resumed == first and len(calls) == 2
    assert missing["off_gate_cause"] == "rebound"
    return {"synthetic_non_zvs_row": first, "different_matrix_cache_hit": resumed == first,
            "simulator_calls_for_two_distinct_cases_and_one_changed_matrix": len(calls),
            "missing_at_partner_measure_cause": missing["off_gate_cause"],
            "case_count": len(grid.cases(None))}


def extrapolation_checks() -> dict:
    ex = load("review_extrapolate", ROUND / "scripts/extrapolate.py")
    actual = ex.extrapolate({h: ex.read_matrix(str(ROUND / f"d2/legA-h{int(h)}-e0p35.matrix.txt")) for h in (1.0, 2.0)})
    # A cubic invisible at every supplied height. All matrices remain SPD.
    def hidden(h: float) -> np.ndarray:
        return np.eye(4) * (30 + 2 * h + (h - 1) * (h - 2) * (h - 3))
    synthetic = ex.extrapolate({h: hidden(h) for h in (1.0, 2.0, 3.0)})
    assert np.allclose(synthetic["L0"], np.eye(4) * 30)
    assert np.allclose(synthetic["high"] - synthetic["low"], 0)
    L = actual["L0"]
    runner = load("review_runner_params", ROUND / "d2/run_d2.py")
    params = runner.matrix_params(L.tolist())
    reconstructed = np.diag([float(params[f"LP{i+1}"][:-1]) for i in range(4)])
    for i in range(4):
        for j in range(i + 1, 4):
            reconstructed[i, j] = reconstructed[j, i] = float(params[f"K{i+1}{j+1}"]) * np.sqrt(L[i,i] * L[j,j])
    # Differentiate a passive shared-source board segment with bulk supplying
    # the incremental current, while local capacitor currents are stationary.
    shared_L_nH, slew_A_per_ns = 5.0, 2.0
    # Smooth SPD scalar family exhibiting mesh/margin/height interaction.
    def model(e: float, margin: float, h: float) -> float:
        return 30 + 2 * h + e + (margin - 10) * (-0.5 + 0.2 * e + 0.1 * h)
    coarse_delta = model(1, 20, 1) - model(1, 10, 1)
    fine_delta = model(.35, 20, 0) - model(.35, 10, 0)
    return {"actual_lin12_L_nH": L.tolist(), "actual_lin12_range_width_max_nH": float(np.max(actual["high"]-actual["low"])),
            "actual_eigenvalues_nH": np.linalg.eigvalsh(L).tolist(),
            "actual_K": {k:v for k,v in params.items() if k.startswith("K")},
            "matrix_spice_roundtrip_max_error_nH": float(np.max(np.abs(reconstructed-L))),
            "synthetic_hidden_cubic": {"estimated_L0_nH": float(synthetic["L0"][0,0]), "true_L0_nH": float(hidden(0)[0,0]),
                "reported_spread_nH": float((synthetic["high"]-synthetic["low"])[0,0])},
            "synthetic_missing_bulk_mode": {"shared_source_nH": shared_L_nH, "slew_A_per_ns": slew_A_per_ns,
                "physical_board_source_voltage_V": shared_L_nH * slew_A_per_ns, "relocated_capacitor_model_board_voltage_V": 0.0},
            "synthetic_margin_interaction": {"coarse_h1_delta_nH": coarse_delta, "fine_h0_delta_nH": fine_delta,
                "correction_error_nH": coarse_delta-fine_delta}}


def reciprocity_checks() -> dict:
    # Same tet, piecewise-constant B, correct energies: sign reversal survives
    # both production gates. The production code also accepts a missing MSH.
    with tempfile.TemporaryDirectory(dir=HERE) as tmp:
        root = Path(tmp)
        vectors = ([1e-6,0.,0.], [.5e-6,1e-6,0.])
        paths = []
        for index, vector in enumerate(vectors):
            run = root / f"p{index}"
            (run / "mesh").mkdir(parents=True)
            paths.append(run)
            field = np.tile(vector, (4,1))
            mesh = meshio.Mesh(np.array([[0.,0.,0.],[1.,0.,0.],[0.,1.,0.],[0.,0.,1.]]),
                               [("tetra", np.array([[0,1,2,3]]))], point_data={"magnetic flux density e": field})
            meshio.write(run / "mesh/case.vtu", mesh)
            energy = float(np.dot(vector,vector)) / (6 * 4e-7 * np.pi) * 1e9
            run.with_suffix(".out").write_text(json.dumps({"inductance_nH": energy}) + "\n")
        command = [sys.executable, str(ROUND / "scripts/inductance_matrix.py"), str(root / "does-not-exist.msh")]
        for index, run in enumerate(paths):
            command.extend(["--port", str(10+index), str(run)])
        def invoke() -> dict:
            completed = subprocess.run(command, text=True, capture_output=True, check=True)
            return json.loads(next(line[7:] for line in completed.stdout.splitlines() if line.startswith("RESULT ")))
        baseline = invoke()
        mesh = meshio.read(paths[1] / "mesh/case.vtu")
        mesh.point_data["magnetic flux density e"] *= -1
        meshio.write(paths[1] / "mesh/case.vtu", mesh)
        flipped = invoke()
    assert baseline["L_nH"][0][1] == -flipped["L_nH"][0][1]
    return {"baseline": baseline, "one_port_orientation_flipped": flipped,
            "both_production_gate_exit_codes": [0,0], "nonexistent_mesh_argument_accepted": True}


def geometry_checks() -> dict:
    closures = json.loads((ROUND / "closures-legA.json").read_text())
    by_name = {c["name"]: c for c in closures}
    # The planar GS segment contains the DS drain pad in each FET.
    crossings = []
    for fet in ("Q2", "Q3"):
        gs, ds = by_name[f"{fet}_GS"], by_name[f"{fet}_DS"]
        assert gs["a"][1] == gs["b"][1] == ds["a"][1]
        crossings.append({"fet": fet, "GS_span_mm": [gs["a"][0], gs["b"][0]], "drain_x_mm": ds["a"][0],
                          "drain_inside_flat_GS_span": gs["a"][0] < ds["a"][0] < gs["b"][0]})
    return {"flat_GS_crossings": crossings, "mesher_minimum_h_mm_exclusive": .1/2+.3,
            "ports": [{"name": c["name"], "a":c["a"], "b":c["b"], "note":c["note"]} for c in closures if c["kind"] == "port" ]}


def main() -> None:
    sources = ["scripts/inductance_matrix.py", "scripts/extrapolate.py", "scripts/mesh25d_hybrid.py", "scripts/campaign.py",
               "d2/leg_matrix.cir", "d2/run_d2.py", "d2/grid.py", "closures-legA.json", "closures-legB.json",
               "d2/legA-h1-e0p35.matrix.txt", "d2/legA-h2-e0p35.matrix.txt"]
    result = {"scope": "review only; synthetic counterexamples are not board measurements",
              "source_revision": "67aec36f8c876a7026c07ce3752105ab34d3ce46", "reviewer": "OpenAI GPT-6 Astra / Codex",
              "runtime": {"python": platform.python_version(), "numpy": np.__version__, "meshio": meshio.__version__},
              "source_sha256": {p: hashlib.sha256((ROUND/p).read_bytes()).hexdigest() for p in sources},
              "grid": grid_checks(), "extrapolation_and_mapping": extrapolation_checks(),
              "reciprocity": reciprocity_checks(), "geometry": geometry_checks()}
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
