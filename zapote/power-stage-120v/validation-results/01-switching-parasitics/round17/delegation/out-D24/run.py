#!/usr/bin/env python3
"""D24 recovery sensitivity, using unchanged D3/D2 fixtures and kit runner.

Only out-D24 is written. Vendor derivatives stay in ignored cache. Parameter
variants are model sensitivities, not manufacturer statistical corners.
"""

from __future__ import annotations

import argparse
import contextlib
import gzip
import hashlib
import importlib.util
import io
import itertools
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
R17 = HERE.parents[1]
POWER = R17.parents[2]
KIT = POWER / "validation-plan/sim-kit"
CACHE = HERE / "cache"
CACHE.mkdir(exist_ok=True)
tempfile.tempdir = str(CACHE)
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
os.environ["MPLCONFIGDIR"] = str(CACHE / "matplotlib")
sys.path.insert(0, str(KIT / "common"))
import run_ngspice  # noqa: E402

ORIGINAL = CACHE / "vendor/IFX_CFD7_650V.lib"
VENDOR_SHA = "02ac6634f47c25be04e8de3c6eec4ec8cf403b659001b7f176c8f98bb6e9ce3b"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


def model(tt_ns: float) -> Path:
    if sha(ORIGINAL) != VENDOR_SHA:
        raise RuntimeError("STOP: vendor hash mismatch")
    if tt_ns == 50:
        return ORIGINAL
    # One value substitution only. Do not copy licensed equations into outputs.
    text, count = re.subn(
        r"(?im)^(\.PARAM\s+fpar20=)50e-9\s*$", lambda m: f"{m[1]}{tt_ns:g}e-9", ORIGINAL.read_text()
    )
    if count != 1:
        raise RuntimeError(f"expected one fpar20, found {count}")
    dest = CACHE / f"tt-{tt_ns:g}" / ORIGINAL.name
    dest.parent.mkdir(exist_ok=True)
    dest.write_text(text)
    return dest


def execute(
    tag: str, deck: Path, params: dict[str, str], tt_ns: float, kind: str, step_ns: float = 0.2
) -> dict:
    dest = HERE / "results" / tag
    dest.mkdir(parents=True, exist_ok=True)
    run_ngspice.VENDOR = model(tt_ns)
    ident = {
        "deck_sha256": sha(deck),
        "vendor_sha256": sha(run_ngspice.VENDOR),
        "params": params,
        "kind": kind,
        "tt_ns": tt_ns,
        "step_ns": step_ns,
        "runner_sha256": sha(Path(__file__)),
        "kit_runner_sha256": sha(KIT / "common/run_ngspice.py"),
    }
    result_file = dest / "result.json"
    if result_file.exists():
        old = json.loads(result_file.read_text())
        if old.get("identity") == ident:
            return old
    with tempfile.TemporaryDirectory(prefix="run-", dir=CACHE) as tmp:
        work = Path(tmp)
        try:
            result = run_ngspice.run(deck, params, keep=work, raw=True)
            for name in ("run.log", "raw_run.log", "params.inc", ".spiceinit"):
                if (work / name).exists():
                    shutil.copy(work / name, dest / name)
            row = {
                "tag": tag,
                "identity": ident,
                "aborted": result["aborted"],
                "returncode": result["returncode"],
                "raw_returncode": result["raw_returncode"],
                "failed_measures": result["failed"],
                "meas": result["meas"],
            }
            if result["aborted"] or result["failed"]:
                row["status"] = "INDETERMINATE"
            else:
                w = run_ngspice.read_raw(work / "waves.raw")
                t = np.array(w["time"])
                final = 12e-6 if kind == "recovery" else 3.243e-6
                row["final_time_s"] = float(t[-1])
                if t[-1] < final - 1e-12:
                    row["status"] = "INDETERMINATE"
                    row["reason"] = "incomplete transient"
                else:
                    row["status"] = "COMPLETE"
                    if kind == "recovery":
                        row.update(d3.metrics(w))
                        mask = (t > row["zero_s"] - 0.3e-6) & (t < row["end_s"] + 0.3e-6)
                    else:
                        m = result["meas"]
                        row["vds_pk_V"] = max(m["vds_ls_die_pk"], m["vds_hs_die_pk"])
                        off = "ls" if params["DIR"] == "0" else "hs"
                        row["vgs_off_max_V"] = m[f"vgs_{off}_off_max"]
                        row["pass_vds"] = row["vds_pk_V"] <= 520
                        row["pass_off_gate_hot"] = row["vgs_off_max_V"] < 1.9
                        row["status"] = (
                            "PASS" if row["pass_vds"] and row["pass_off_gate_hot"] else "FAIL"
                        )
                        mask = t > 2e-6
                    # Full adaptive resolution transition output; no decimation.
                    names = list(w)
                    with gzip.open(dest / "waves.csv.gz", "wt") as fh:
                        np.savetxt(
                            fh,
                            np.column_stack([np.array(w[n])[mask] for n in names]),
                            delimiter=",",
                            header=",".join(names),
                            comments="",
                            fmt="%.12g",
                        )
        except (subprocess.TimeoutExpired, ValueError, KeyError) as exc:
            row = {
                "tag": tag,
                "identity": ident,
                "status": "INDETERMINATE",
                "aborted": True,
                "reason": str(exc),
            }
    result_file.write_text(json.dumps(row, indent=2) + "\n")
    print(
        tag,
        row["status"],
        {
            k: row[k]
            for k in (
                "Qrr_uC",
                "trr_ns",
                "Irrm_A",
                "softness_tb10_over_ta",
                "vds_pk_V",
                "vgs_off_max_V",
            )
            if k in row
        },
        flush=True,
    )
    return row


def smoke() -> None:
    run_ngspice.VENDOR = model(50)
    original = run_ngspice.run

    def scoped_run(deck, params, keep=None, raw=False):
        if keep is not None:
            return original(deck, params, keep, raw)
        with tempfile.TemporaryDirectory(dir=CACHE) as tmp:
            return original(deck, params, Path(tmp), raw)

    run_ngspice.run = scoped_run
    smoke_module = module("kit_smoke", KIT / "smoke_test.py")
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = smoke_module.main()
    (HERE / "smoke-test.log").write_text(out.getvalue())
    print(out.getvalue(), end="")
    run_ngspice.run = original
    if code:
        raise RuntimeError("STOP: smoke failed")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=("smoke", "map", "sweep"))
    ap.add_argument("--tt", default="0,25,50,100,200,400,800")
    ap.add_argument("--step", type=float, default=0.2)
    args = ap.parse_args()
    if args.mode == "smoke":
        smoke()
        return
    tt_values = [float(x) for x in args.tt.split(",")]
    rows = []
    if args.mode == "map":
        deck = R17 / "delegation/out-D3/recovery.cir"
        for tt, tj in itertools.product(tt_values, (25, 150)):
            params = {"RG": "730", "TJ": str(tj), "STEP": f"{args.step:g}n"}
            rows.append(
                execute(
                    f"map_tt{tt:g}_tj{tj}_step{args.step:g}",
                    deck,
                    params,
                    tt,
                    "recovery",
                    args.step,
                )
            )
    else:
        deck = HERE / "s4.cir"
        text = (
            (R17 / "d2/leg_matrix.cir")
            .read_text()
            .replace(".include params.inc", ".param TJ=27\n.include params.inc\n.temp {TJ}")
        )
        deck.write_text(text)
        base = d2.matrix_params(d2.read_L(str(R17 / "d2/legA-h0-best.matrix.txt")))
        for tt, vb, direction, esl, tj in itertools.product(
            tt_values, (198, 280), (0, 1), (1.06, 10), (27, 150)
        ):
            params = base | {
                "VBUS": str(vb),
                "IL": "-20",
                "DIR": str(direction),
                "DT": "443n",
                "LESL": f"{esl:g}n",
                "LSHUNT": "2n",
                "TJ": str(tj),
                "TRMAX": f"{args.step:g}n",
            }
            rows.append(
                execute(
                    f"s4_tt{tt:g}_v{vb}_d{direction}_esl{esl:g}_tj{tj}_step{args.step:g}",
                    deck,
                    params,
                    tt,
                    "s4",
                    args.step,
                )
            )
    label = f"{args.mode}-tt{args.tt}-step{args.step:g}"
    (HERE / f"{label}.json").write_text(json.dumps(rows, indent=2) + "\n")
    files = [
        Path(__file__),
        ORIGINAL,
        R17 / "d2/legA-h0-best.matrix.txt",
        R17 / "d2/leg_matrix.cir",
        R17 / "d2/run_d2.py",
        R17 / "delegation/out-D3/recovery.cir",
        R17 / "delegation/out-D3/run.py",
        KIT / "common/options.inc",
        KIT / "common/run_ngspice.py",
    ]
    provenance = {
        "base_revision": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "model": "GPT-6 Astra",
        "python": sys.version,
        "ngspice": subprocess.check_output(["ngspice", "--version"], text=True),
        "inputs_sha256": {str(f.relative_to(POWER)): sha(f) for f in files},
        "parameter_edits": [
            {
                "parameter": "cool_tech_w3.fpar20",
                "before_ns": 50,
                "after_ns": tt,
                "library_sha256": sha(model(tt)),
            }
            for tt in tt_values
        ],
    }
    (HERE / f"{label}-provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")


d2 = module("d2_runner", R17 / "d2/run_d2.py")
d3 = module("d3_runner", R17 / "delegation/out-D3/run.py")
if __name__ == "__main__":
    main()
