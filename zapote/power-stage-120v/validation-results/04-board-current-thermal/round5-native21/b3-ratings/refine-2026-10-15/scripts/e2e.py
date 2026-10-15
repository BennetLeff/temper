#!/usr/bin/env python3
"""End-to-end check of the patch set as the integration session would apply it: a scratch copy of frozen/<board>/
(APFS clone) + patches/*.diff (patch -p1), then the repo's own entry points in that copy:
  1. b3/make_heat_sources.py  (patched: c28 rows at 60 kHz, deck gate charge)  -> its c28 heat file must equal
     runs*/heat/heat-c28-corrected-deck.json row for row;
  2. b3-ratings/run_basis.py  (patched: drain-lead path, BAY_C 55)             -> margins.json;
  3. the patched b3_ratings_gate.py on this study's record solves (runs*/HLdeck_central_b55) -> must give the same rows
     as 2 (same model, heat and lead path; the only differences are rounding of the tie temperature).
    THERMAL_REFINE_BOARD=s38 python3 e2e.py  ->  results*/e2e.json (exit 1 on a mismatch)
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import BOARD, FROZEN, HEAT_DIR, JOB, RESULTS, RUNS  # noqa: E402

R5 = "zapote/power-stage-120v/validation-results/04-board-current-thermal/round5-native21"
PATCHES = ("lead-path.diff", "heat-c28-60khz.diff", "gate-proposed-rows.diff", "run-basis-lead.diff")


def main():
    scratch = JOB / "work" / f"e2e-{BOARD}"
    if not (scratch / ".patched").exists():
        assert not scratch.exists(), f"{scratch} exists without .patched: inspect it"
        scratch.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["cp", "-c", "-R", str(FROZEN), str(scratch)], check=True)
        for p in PATCHES:
            subprocess.run(["patch", "-p1", "-s", "-d", str(scratch), "-i", str(JOB / "patches" / p)], check=True)
        (scratch / ".patched").write_text("\n".join(PATCHES) + "\n")
    r5 = scratch / R5
    subprocess.run([sys.executable, str(r5 / "b3/make_heat_sources.py")], check=True, cwd=r5 / "b3")
    theirs = json.loads((r5 / "b3/inputs/native21-board-heat-sources-c28.json").read_text())["parts"]
    mine = json.loads((HEAT_DIR / "heat-c28-corrected-deck.json").read_text())["parts"]
    heat_diff = max(abs(a["watts_nominal"] - b["watts_nominal"]) for a, b in zip(theirs, mine))
    assert [a["ref"] for a in theirs] == [b["ref"] for b in mine]
    done = scratch / ".run_basis_done"          # margins.json is committed, so its presence says nothing
    if not done.exists() or "--resolve" in sys.argv:
        subprocess.run([sys.executable, str(r5 / "b3-ratings/run_basis.py"), "--workers", "4"], cwd=r5 / "b3-ratings")
        done.write_text("run_basis.py ran on the patched scratch copy\n")
    basis = json.loads((r5 / "b3-ratings/margins.json").read_text())
    mine_out = RUNS / "e2e-gate-on-HLdeck_central_b55.json"
    subprocess.run([sys.executable, str(r5 / "b3-ratings/b3_ratings_gate.py"), "--runs", str(RUNS / "HLdeck_central_b55"),
                    "--out", str(mine_out), "--bay-c", "55"])
    ours = json.loads(mine_out.read_text())
    worst, missing = 0.0, []
    for case, rows in basis["cases"].items():
        o = {r["item"].split(" at ")[0]: r for r in ours["cases"][case]}
        for r in rows:
            k = r["item"].split(" at ")[0]
            if k not in o:
                missing.append(f"{case}: {k}")
                continue
            worst = max(worst, abs(r["est_c"] - o[k]["est_c"]))
    res = {"board": BOARD, "scratch": str(scratch), "heat_c28_max_abs_W": heat_diff, "margins_rows_max_abs_est_K": worst,
           "rows_missing": missing, "run_basis_metrics": basis.get("metrics"), "gate_on_record_metrics": ours.get("metrics"),
           "pass": heat_diff < 1e-12 and worst <= 0.1 + 1e-9 and not missing}
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "e2e.json").write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps(res, indent=1))
    raise SystemExit(0 if res["pass"] else 1)


if __name__ == "__main__":
    main()
