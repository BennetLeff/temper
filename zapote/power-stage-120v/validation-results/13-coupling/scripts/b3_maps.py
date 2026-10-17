#!/usr/bin/env python3
"""Stage inputs: the root's board file, and the legacy B3 heat maps (thermal.py heat_w / rise_k on 1 mm cells) that physics.py attributes to groups.

    python3 -I validation-results/13-coupling/scripts/b3_maps.py [--stage TAG --root DIR ...]   (common.init options)

For each B3 run the stage registry names (stages.STAGES[TAG]['b3']):
* source 'committed': the stage's own B3 output (ROOT b3/outputs/<run>.json); its npz is gitignored in the repo, so the
  copy in the stage's B3 dir is checked by sha256 and against the JSON (heat total = source watts, peak = peak);
* source 'regenerate': ROOT's b3/thermal.py is re-run, unchanged, into the stage's B3 dir (default
  13-coupling/cache/TAG/b3, not committed) on the stage's all-copper dump and A4 fields:
    c28 - run_study.cases('c28') and the c28 heat file, exactly as b3/run_study.py runs it;
    c18 - the release case (DECISIONS 56): b3-ratings/run_basis.inputs('c18', 18.0) builds its heat file (tank rows
          x (18.9 / 29.4)^2, L1 x (13.5 / 11.1)^2) and copper case (I_t 18.9 A, I_line 13.5 A), as the ratings gate does.
  A run whose recorded inputs (case, heat file, geometry, thermal.py, A4 field hashes) are unchanged is not re-solved.
  thermal.py convects to a fixed 50 C ambient; only the deposited heat (heat_w) feeds the coupling screen, which is
  ambient-independent (the body-level ratings model, not this map, sets the release margins).
Controls: the root's board file is the stage's board; every map is on the stage's board; heat total = the run's source watts; a regenerated run with a committed
counterpart reproduces its board, peak and source watts; a named npz matches its sha256; the c18 heat file is the c28
file with exactly the tank and L1 rows rescaled.
"""
import gzip
import hashlib
import importlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402
import stages as STG  # noqa: E402


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def basis_inputs(op, ceiling, out):
    """(case string, heat file name in `out`) for a ratings-basis case, from ROOT's own run_basis.inputs."""
    r5 = C.VR / "04-board-current-thermal/round5-native21"
    for p in (r5 / "b3", r5 / "b3-convergence", r5 / "b3-ratings"):
        sys.path.insert(0, str(p))
    rb = importlib.import_module("run_basis")
    case, path, mode = rb.inputs(op, ceiling, out)
    assert mode == "nominal"
    return case, Path(path).name, rb


def main():
    C.init()
    ctl = C.Controls()
    ctl.check(f"root's native-21/section.kicad_pcb is the stage-{C.N} board (rules21 reads its nets)",
              sha(C.N21 / "section.kicad_pcb") == C.BOARD_SHA, str(C.PS))
    B3 = C.VR / STG.B3_DIR
    out = C.B3RUNS
    out.mkdir(parents=True, exist_ok=True)
    geom = C.DUMP
    a4 = C.VR / "04-board-current-thermal/round5-native21/outputs"
    for spec in C.ST["b3"]:
        run = spec["run"]
        js, npz = out / f"{run}.json", out / f"{run}.npz"
        if spec["source"] == "committed":
            js = B3 / f"outputs/{run}.json"
        else:
            if spec["op"] == "c28":
                sys.path.insert(0, str(B3))
                rs = importlib.import_module("run_study")
                case = rs.cases("c28")
                shutil.copyfile(rs.HEAT_C28, out / "heat_c28.json")
                heat_name = "heat_c28.json"
            else:
                case, heat_name, rb = basis_inputs(spec["op"], spec["ceiling_a"], out)
                base = {p["ref"]: p for p in json.loads(rb.rs.HEAT_C28.read_text())["parts"]}
                new = {p["ref"]: p for p in json.loads((out / heat_name).read_text())["parts"]}
                k_t, k_l = (1.05 * spec["ceiling_a"] / 29.4) ** 2, (rb.I_LINE_A / rb.HEAT_C28_I_LINE_A) ** 2
                bad = [r for r in base if abs(new[r]["watts_nominal"] - base[r]["watts_nominal"] *
                                              (k_t if r in rb.br.TANK_ROWS else k_l if r == "L1" else 1.0)) > 1e-12]
                ctl.check(f"[{run}] heat file = c28 file with tank rows x {k_t:.4f} and L1 x {k_l:.4f}, others unchanged",
                          not bad and set(base) == set(new), f"{len(new)} rows; tank rows {sorted(rb.br.TANK_ROWS)}")
            a4_hash = hashlib.sha256("".join(sha(p) for p in sorted(a4.glob("*-heat.npz"))).encode()).hexdigest()
            rec = {"run": run, "case": case, "h": spec["h"], "pitch_mm": spec["pitch"], "heat_file": heat_name,
                   "heat_file_sha256": sha(out / heat_name), "geometry_sha256": sha(geom),
                   "thermal_py_sha256": sha(B3 / "thermal.py"), "a4_fields_sha256": a4_hash}
            man = out / f"{run}.inputs.json"
            if not (js.exists() and npz.exists() and man.exists() and json.loads(man.read_text()) == rec):
                subprocess.run([sys.executable, "-B", str(B3 / "thermal.py"), "--geometry", str(geom), "--case", case,
                                "--pitch-mm", str(spec["pitch"]), "--h", str(spec["h"]), "--a6-heat", str(out / heat_name),
                                "--a6-mode", "nominal", "--output", str(js)], check=True, stdout=subprocess.DEVNULL)
                man.write_text(json.dumps(rec, indent=1, sort_keys=True) + "\n")
            ref = B3 / f"outputs/{run}.json"
            if ref.exists():
                r0, r1 = json.loads(ref.read_text()), json.loads(js.read_text())
                ctl.check(f"[{run}] regenerated run reproduces the stage's committed B3 output (board, case, peak, source W)",
                          r0["board_sha256"] == r1["board_sha256"] and r0["case"] == r1["case"] and r0["peak"] == r1["peak"]
                          and r0["balance"]["source_w"] == r1["balance"]["source_w"],
                          f"peak {r1['peak']['temperature_c']:.2f} C, source {r1['balance']['source_w']:.3f} W")
        r = json.loads(js.read_text())
        z = np.load(npz)
        ctl.check(f"[{run}] heat map on the stage-{C.N} board", r["board_sha256"] == C.BOARD_SHA, r["board_sha256"][:8])
        ctl.check(f"[{run}] heat map total = the run's source watts", abs(float(z["heat_w"].sum()) - r["balance"]["source_w"]) < 1e-6,
                  f"{float(z['heat_w'].sum()):.6f} vs {r['balance']['source_w']:.6f} W")
        ctl.check(f"[{run}] map peak = the run's peak", abs(float(z["rise_k"].max()) + r["ambient_c"] - r["peak"]["temperature_c"]) < 1e-9,
                  f"{r['peak']['temperature_c']:.2f} C")
        if spec.get("npz_sha256"):
            ctl.check(f"[{run}] npz is the named one (sha256 {spec['npz_sha256'][:12]})", sha(npz) == spec["npz_sha256"], str(npz))
        print(f"{run}: {spec['source']}, source {r['balance']['source_w']:.3f} W, peak {r['peak']['temperature_c']:.2f} C")
    ctl.finish()


if __name__ == "__main__":
    main()
