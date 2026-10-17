#!/usr/bin/env python3
"""Replay fixtures and prepare a checked round17 matching baseline."""

import json
import runpy
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[6]
PS = ROOT / "zapote/power-stage-120v"
R3 = PS / "validation-results/07-conducted-emi/round3"
D2 = HERE.parent.parent / "d2"
sys.path.insert(0, str(PS / "validation-plan/sim-kit/common"))
from run_ngspice import run


def main():
    fixture = runpy.run_path(str(R3 / "scripts/check_topology.py"))
    fixture["main"].__globals__["OUTPUT"] = HERE / "fixture.json"
    fixture["main"]()
    old = json.loads((R3 / "outputs/topology_fixture.json").read_text())
    new = json.loads((HERE / "fixture.json").read_text())
    assert old == new, "round3 fixture changed"
    mod = runpy.run_path(str(D2 / "run_d2.py"))
    params = mod["matrix_params"](mod["read_L"](str(D2 / "legA-h0-best.matrix.txt")))
    params.update(VBUS="170", IL="37", DIR="0", DT="443n", LESL="10n", TRMAX="0.2n")
    with tempfile.TemporaryDirectory(prefix="d19-baseline-") as tmp:
        out = run(D2 / "leg_matrix.cir", params, keep=Path(tmp), raw=True)
        for name in ("run.log", "raw_run.log", "params.inc"):
            (HERE / ("baseline-" + name)).write_bytes((Path(tmp) / name).read_bytes())
        import gzip

        with gzip.open(HERE / "baseline.raw.gz", "wb") as f:
            f.write((Path(tmp) / "waves.raw").read_bytes())
    out.pop("run_dir", None)
    (HERE / "baseline.json").write_text(json.dumps(out, indent=2) + "\n")
    assert not out["aborted"] and not out["failed"]
    rows = [
        json.loads(line)
        for line in (D2 / "results/grid-best-longdt/results.jsonl").read_text().splitlines()
    ]
    expected = next(
        r
        for r in rows
        if r["vbus"] == 170
        and r["il"] == 37
        and r["dir"] == 0
        and r["dt_ns"] == 443
        and r["esl_nH"] == 10
    )
    actual = {
        "vds_pk": max(out["meas"]["vds_ls_die_pk"], out["meas"]["vds_hs_die_pk"]),
        "vgs_off_max": out["meas"]["vgs_ls_off_max"],
        "vds_incoming_at_on": out["meas"]["vds_hs_at_on"],
    }
    assert all(
        abs(value - expected[key]) <= 1e-6 * max(1, abs(value)) for key, value in actual.items()
    )
    (HERE / "baseline-comparison.json").write_text(
        json.dumps({"expected": expected, "actual": actual, "pass": True}, indent=2) + "\n"
    )
    print("BASELINE COMPLETE")


if __name__ == "__main__":
    main()
