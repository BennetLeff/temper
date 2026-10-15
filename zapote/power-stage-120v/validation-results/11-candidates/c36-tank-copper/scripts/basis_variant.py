"""run_basis.py for a what-if variant: same four solves and gate, with the A4 maps from A4DIR and (optionally) another
stackup, written to RUNSDIR (nothing in the study tree is touched).
  B3_A4_DIR=... NATIVE21_STACKUP=... python3 basis_variant.py GEOM RUNSDIR [--r5 0.5]"""
import json, os, subprocess, sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
R = Path(__file__).resolve().parents[4] / "validation-results/04-board-current-thermal/round5-native21"
GEOM, RUNS = Path(sys.argv[1]), Path(sys.argv[2])
R5X = float(sys.argv[sys.argv.index("--r5") + 1]) if "--r5" in sys.argv else 1.0
sys.path.insert(0, str(R / "b3-convergence")); sys.path.insert(0, str(R / "b3-ratings"))
import body_runs as br, fet_case, thermal_body as tb
br.rs.GEOM = GEOM
BAY = 55.0
CEIL = {"c22": 22.0, "c28": 28.0}


def heat_for(op):
    heat = json.loads(br.rs.HEAT_C28.read_text())
    k = (1.05 * 22.0 / 29.4) ** 2 if op == "c22" else 1.0
    for p in heat["parts"]:
        if p["ref"] in br.TANK_ROWS:
            p["watts_nominal"] *= k; p["watts_worst"] *= k
        if p["ref"] == "R5":
            p["watts_nominal"] *= R5X; p["watts_worst"] *= R5X
    path = RUNS / f"heat_{op}.json"; path.write_text(json.dumps(heat))
    return path


def one(job):
    name, op, h, pitch = job
    if op == "c22":
        br.rs.OPS["c22"] = {"I_t": 1.05 * 22.0, "I_line": 11.1, "parts": "nominal", "heat": "c28"}
    hp = heat_for(op)
    br.op_inputs = lambda _op: (br.rs.cases(op), hp, "nominal")
    brd = tb.Board(GEOM, RUNS / "cache")
    leads = {"pad": "2", "g": tb.drain_lead_conductance(), "t_rise": {r: t - BAY for r, t in fet_case.t_case(CEIL[op]).items()}}
    res = br.run_case(brd, op, h, pitch, "fraction", "network", {}, None, None, True, True, label=name, leads=leads)
    res["board_sha256"] = brd.data["board_sha256"]
    (RUNS / f"{name}.json").write_text(json.dumps(res, indent=1) + "\n")
    return name


if __name__ == "__main__":
    RUNS.mkdir(parents=True, exist_ok=True)
    tb.Board(GEOM, RUNS / "cache").fine()
    jobs = [(f"{c}_h10_p{str(p).replace('.', 'p')}", c, 10, p) for c in ("c22", "c28") for p in (0.25, 0.5)]
    with ProcessPoolExecutor(max_workers=4) as ex:
        for n in ex.map(one, jobs):
            print("  solved", n, flush=True)
    r = subprocess.run([sys.executable, str(R / "b3-ratings/b3_ratings_gate.py"), "--runs", str(RUNS),
                        "--out", str(RUNS / "margins.json"), "--bay-c", str(BAY)])
    print("gate exit", r.returncode)
