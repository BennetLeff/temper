#!/usr/bin/env python3
"""Audit complete derated grid and refine reported peak extrema to 25 ns."""
from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

TASK = Path(__file__).resolve().parents[1]
UNIT = TASK.parents[3]
KIT = UNIT / "validation-plan/sim-kit"
OUT = TASK / "outputs"
sys.path.insert(0, str(KIT / "common"))
from run_ngspice import run  # noqa: E402

MEAS = ("i_rms", "i_pk", "vc_pk", "vc_rms", "p_avg")
# These are the original simulation inputs, not hashes of this post-review guard.
FROZEN_SIM_INPUTS = {
    "common/options.inc": "ae752d460d50fdbbcaaf03b29871b3b039cf27f018707efe4aa50d0fc3529330",
    "common/run_ngspice.py": "e518996d3c4050f3fbbb109abbf116a23b010612dd073bea860d3db613f758b0",
    "models/vendor/IFX_CFD7_650V.lib": "02ac6634f47c25be04e8de3c6eec4ec8cf403b659001b7f176c8f98bb6e9ce3b",
}
FROZEN_DECKS = {
    "tank-halfstep.cir": "4a504d85ff048027fa494ca732553f1b1e9b0379c818ebff7ce612182eec3f49",
    "tank-quarterstep.cir": "ad25da7279fa5b657ff2dca3e86e41751b682c7150c92f00b6bb2b1937c6c95d",
}
FROZEN_NGSPICE = "** ngspice-45.2 : Circuit level simulation program"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_numerical_cache(folder: Path, deck: Path, params: dict[str, str], result: dict) -> None:
    """Fail closed if the saved solve or any original simulator input changed."""
    for name, expected in FROZEN_SIM_INPUTS.items():
        if digest(KIT / name) != expected:
            raise RuntimeError(f"frozen simulator input changed: {name}")
    if digest(deck) != FROZEN_DECKS[deck.name]:
        raise RuntimeError(f"frozen numerical deck changed: {deck}")
    version = next(line.strip() for line in subprocess.check_output(
        ["ngspice", "-v"], text=True, stderr=subprocess.STDOUT).splitlines()
        if "ngspice-" in line)
    if version != FROZEN_NGSPICE:
        raise RuntimeError(f"ngspice version changed: {version}")
    saved_deck = (folder / deck.name).read_text()
    normalized_deck = re.sub(
        r"\S*/validation-plan/sim-kit/common/", "../common/", saved_deck
    )
    if normalized_deck != deck.read_text():
        raise RuntimeError(f"cached numerical deck differs from frozen source: {folder}")
    expected_params = "".join(f".param {key}={value}\n" for key, value in params.items())
    if ((folder / "params.inc").read_text() != expected_params
            or (folder / ".spiceinit").read_text() != "set ngbehavior=psa\nset filetype=ascii\n"):
        raise RuntimeError(f"cached numerical parameters/options differ: {folder}")
    if not (folder / "run.log").is_file() or result["params"] != params:
        raise RuntimeError(f"incomplete or stale numerical result: {folder}")
    if (result["aborted"] or result["failed"] or result["returncode"] != 0
            or any(key not in result["meas"] or not math.isfinite(result["meas"][key])
                   for key in MEAS)):
        raise RuntimeError(f"invalid cached numerical result: {folder}")


def load_cases() -> list[dict[str, str]]:
    with (OUT / "derated_cases.csv").open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != 270 or len({(r["ceiling_a"], r["run_id"]) for r in rows}) != 270:
        raise RuntimeError("expected 270 unique ceiling/case rows")
    return rows


def main() -> None:
    rows = load_cases()
    with (OUT / "switching-events.csv").open(newline="") as stream:
        events = list(csv.DictReader(stream))
    with (OUT / "shunt-grid.csv").open(newline="") as stream:
        shunts = list(csv.DictReader(stream))
    accepted = [r for r in rows if r["status"] != "needs_burst_or_phase_shift"]
    expected = {(r["ceiling_a"], r["run_id"]) for r in accepted}
    if {(r["ceiling_a"], r["run_id"]) for r in shunts} != expected:
        raise RuntimeError("R5 shunt file does not cover all and only accepted cases")
    event_keys = Counter((r["ceiling_a"], r["run_id"]) for r in events)
    if set(event_keys) != expected or not all(event_keys.values()):
        raise RuntimeError("event file does not cover all and only accepted cases")
    checks = {"case_count": len(rows), "accepted_case_count": len(accepted),
              "event_count": len(events), "shunt_case_count": len(shunts),
              "time_step_limit": "reported peaks refine 50 ns to 25 ns; <2% difference",
              "halfstep": [], "replay": [], "refined_above_ceiling": []}
    for r in rows:
        ceiling = float(r["ceiling_a"])
        peak = float(r["i_pk_a"])
        f = float(r["frequency_hz"])
        if f > 60000.000001:
            raise RuntimeError("frequency exceeded 60 kHz")
        if r["status"] == "retained":
            if f != float(r["round3_frequency_hz"]):
                raise RuntimeError("retained frequency changed")
            if peak > ceiling:
                raise RuntimeError("retained case exceeds ceiling")
        elif r["status"] == "derated":
            if not (f > float(r["round3_frequency_hz"]) and 0 <= ceiling - peak <= 0.2):
                raise RuntimeError("derated case not safely at ceiling +/-0.2A")
            case = json.loads((TASK / r["run_dir"] / "case.json").read_text())
            search = case["search"]
            target = ceiling - search.get("target_margin_a", 0.)
            if search["unsafe_lower_peak_a"] <= target or search["safe_upper_peak_a"] > target:
                raise RuntimeError("invalid frequency/current bisection bracket")
        elif r["status"] == "needs_burst_or_phase_shift":
            if f != 60000 or peak <= ceiling:
                raise RuntimeError("invalid needs-burst classification")
        else:
            raise RuntimeError(f"unexpected status {r['status']}")
    extremum_keys = set()
    for ceiling in (42.0, 40.45):
        group = [r for r in accepted if float(r["ceiling_a"]) == ceiling]
        for field in ("i_pk_a", "vc_pk_v", "i_rms_a"):
            r = max(group, key=lambda row: float(row[field]))
            extremum_keys.add((r["ceiling_a"], r["run_id"]))
    for index, r in enumerate(accepted, 1):
        label = f"{float(r['ceiling_a']):g}a-{r['run_id']}-{float(r['frequency_hz']):.6f}hz"
        params = {"VRMS": r["vrms_v"], "FREQ": r["frequency_hz"],
                  "LLOAD": r["l_load_h"], "RPAN40": r["r_pan_40_ohm"],
                  "RCOIL": r["r_coil_ohm"]}
        directory = OUT / "runs/numerical" / label
        saved = directory / "result.json"
        if saved.is_file():
            result = json.loads(saved.read_text())
            verify_numerical_cache(directory, TASK / "scripts/tank-halfstep.cir", params, result)
        else:
            result = run(TASK / "scripts/tank-halfstep.cir", params, keep=directory)
            (directory / "IFX_CFD7_650V.lib").unlink(missing_ok=True)
            saved.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
        if result["aborted"] or result["failed"] or any(m not in result["meas"] for m in MEAS):
            raise RuntimeError(f"halfstep failed {label}: {result}")
        original = json.loads((TASK / r["run_dir"] / "result.json").read_text())
        comparison = {"ceiling_a": float(r["ceiling_a"]), "run_id": r["run_id"],
                      "extremum_case": (r["ceiling_a"], r["run_id"]) in extremum_keys,
                      "nominal_max_step_ns": 50, "refined_max_step_ns": 25,
                      "metrics": {}}
        for key in MEAS:
            base = original["meas"][key]
            refined = result["meas"][key]
            relative = abs(refined - base) / max(abs(base), 1e-12)
            comparison["metrics"][key] = {"base": base, "refined": refined,
                                           "relative_change": relative}
            if key in ("i_pk", "vc_pk") and relative >= .02:
                raise RuntimeError(f"peak timestep difference >=2%: {label} {key}: {relative}")
        checks["halfstep"].append(comparison)
        if result["meas"]["i_pk"] > float(r["ceiling_a"]):
            checks["refined_above_ceiling"].append({"ceiling_a": float(r["ceiling_a"]),
                "run_id": r["run_id"], "nominal_i_pk_a": original["meas"]["i_pk"],
                "refined_i_pk_a": result["meas"]["i_pk"]})
        if index % 25 == 0:
            print(json.dumps({"halfstep_progress": index, "of": len(accepted),
                              "above_ceiling": len(checks["refined_above_ceiling"])}), flush=True)
    # Independently replay the nominal maximum-current case for each ceiling.
    for ceiling in (42.0, 40.45):
        group = [r for r in accepted if float(r["ceiling_a"]) == ceiling]
        r = max(group, key=lambda row: float(row["i_pk_a"]))
        directory = TASK / r["run_dir"]
        proc = subprocess.run(["ngspice", "-b", "tank.cir"], cwd=directory,
                              capture_output=True, text=True, timeout=1800)
        log = proc.stdout + proc.stderr
        (directory / "replay.log").write_text(log)
        replay = {m.group(1): float(m.group(2)) for line in log.splitlines()
                  if (m := re.match(r"^\s*([a-z_]+)\s*=\s*([-+\d.eE]+)", line))}
        original = json.loads((directory / "result.json").read_text())
        if proc.returncode != 0 or any(key not in replay for key in MEAS):
            raise RuntimeError(f"replay failed {r['run_id']}")
        relative = {key: abs(replay[key] - original["meas"][key]) /
                    max(abs(original["meas"][key]), 1e-12) for key in MEAS}
        if any(value > 1e-4 for value in relative.values()):
            raise RuntimeError(f"replay mismatch {r['run_id']}: {relative}")
        checks["replay"].append({"ceiling_a": ceiling, "run_id": r["run_id"],
                                 "relative_change": relative})
    (OUT / "numerical-checks.json").write_text(json.dumps(checks, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"cases": len(rows), "accepted": len(accepted),
                      "events": len(events), "halfstep_cases": len(checks["halfstep"]),
                      "replay_cases": len(checks["replay"]),
                      "refined_above_ceiling": len(checks["refined_above_ceiling"])}))


if __name__ == "__main__":
    main()
