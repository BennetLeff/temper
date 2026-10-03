#!/usr/bin/env python3
"""Isolated-edge evidence only; never silently periodize a transient into EMI."""

import csv
import gzip
import hashlib
import json
import runpy
import sys
import tempfile
from pathlib import Path
import numpy as np
from scipy.signal import find_peaks

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[6]
PS = ROOT / "zapote/power-stage-120v"
D2 = HERE.parent.parent / "d2"
sys.path.insert(0, str(PS / "validation-plan/sim-kit/common"))
from run_ngspice import run, read_raw


def main():
    mod = runpy.run_path(str(D2 / "run_d2.py"))
    base = mod["matrix_params"](mod["read_L"](str(D2 / "legA-h0-best.matrix.txt")))
    source = (
        (D2 / "leg_matrix.cir").read_text().replace(".save v(sw)", ".save i(vbus) i(lbulk) v(sw)")
    )
    source = source.replace(".tran ", ".options itl4=100000\n.tran ", 1)
    deck = HERE / "edge.cir"
    deck.write_text(source)
    rows = []
    rawdir = HERE / "raw"
    rawdir.mkdir(exist_ok=True)
    for bus in (170, 198):
        for current in (2, 37):
            for esl in (1.06, 10):
                for direction in (0, 1):
                    name = f"v{bus}-i{current}-e{esl}-d{direction}"
                    params = {
                        **base,
                        "VBUS": str(bus),
                        "IL": str(current),
                        "DIR": str(direction),
                        "DT": "443n",
                        "LESL": f"{esl}n",
                        "TRMAX": "0.2n",
                    }
                    with tempfile.TemporaryDirectory(prefix="d19-edge-") as directory:
                        tmp = Path(directory)
                        if "--replay" in sys.argv:
                            result = json.loads((rawdir / (name + ".json")).read_text())
                            for filename in ("run.log", "raw_run.log", "params.inc"):
                                (tmp / filename).write_bytes(
                                    (rawdir / (name + "-" + filename)).read_bytes()
                                )
                            with gzip.open(rawdir / (name + ".raw.gz"), "rb") as f:
                                (tmp / "waves.raw").write_bytes(f.read())
                        else:
                            result = run(deck, params, keep=tmp, raw=True)
                        result.pop("run_dir", None)
                        for f in ("run.log", "raw_run.log", "params.inc"):
                            (rawdir / (name + "-" + f)).write_bytes((tmp / f).read_bytes())
                        row = {
                            "case": name,
                            "bus_V": bus,
                            "current_A": current,
                            "esl_nH": esl,
                            "direction": direction,
                            "status": "indeterminate",
                        }
                        if (tmp / "waves.raw").exists() and "--replay" not in sys.argv:
                            with gzip.open(rawdir / (name + ".raw.gz"), "wb") as stream:
                                stream.write((tmp / "waves.raw").read_bytes())
                        if not result["aborted"] and not result["failed"]:
                            waves = read_raw(tmp / "waves.raw")
                            t = np.array(waves["time"])
                            v = np.array(waves["v(sw)"])
                            if t[-1] < 3.243e-6 - 1e-12:
                                raise RuntimeError("truncated raw")
                            if not all(
                                np.isfinite(x).all() for x in map(np.asarray, waves.values())
                            ):
                                raise RuntimeError("nonfinite raw")
                            progress = v / bus if direction == 0 else 1 - v / bus

                            def crossing(fraction):
                                hits = np.flatnonzero(
                                    (t[1:] >= 2e-6)
                                    & (progress[:-1] < fraction)
                                    & (progress[1:] >= fraction)
                                )
                                if not len(hits):
                                    raise RuntimeError("missing edge crossing")
                                k = hits[0]
                                return float(
                                    t[k]
                                    + (fraction - progress[k])
                                    * (t[k + 1] - t[k])
                                    / (progress[k + 1] - progress[k])
                                )

                            t10, t90 = crossing(0.1), crossing(0.9)
                            mask = (t >= 2e-6) & (t <= 3.193e-6)
                            incoming = result["meas"][
                                "vds_hs_at_on" if direction == 0 else "vds_ls_at_on"
                            ]
                            # Diagnostic ringing fit: peaks of abs residual after 90% crossing.
                            endpoint = bus if direction == 0 else 0
                            sel = (t >= t90) & (t <= t90 + 500e-9)
                            tt = t[sel]
                            residual = np.abs(v[sel] - endpoint)
                            peaks, _ = find_peaks(residual, prominence=0.005 * bus)
                            period = None
                            tau = None
                            if len(peaks) >= 3:
                                # abs residual repeats twice per oscillation; report as estimate.
                                period = float(2 * np.median(np.diff(tt[peaks])))
                                slope = float(
                                    np.polyfit(
                                        tt[peaks] - tt[peaks[0]], np.log(residual[peaks]), 1
                                    )[0]
                                )
                                if slope < 0:
                                    tau = -1 / slope
                            row.update(
                                status="complete",
                                edge_10_90_ns=(t90 - t10) * 1e9,
                                mean_10_90_V_per_ns=0.8 * bus / (t90 - t10) / 1e9,
                                max_abs_slope_V_per_ns=float(
                                    np.max(np.abs(np.diff(v[mask]) / np.diff(t[mask])))
                                )
                                / 1e9,
                                incoming_VDS_V=incoming,
                                zvs=abs(incoming) < 5,
                                ring_estimate_MHz=1 / period / 1e6 if period else None,
                                decay_estimate_ns=tau * 1e9 if tau else None,
                                isolated_source_current_peak_A=float(
                                    np.max(np.abs(waves["i(vbus)"]))
                                ),
                                isolated_bulk_path_current_peak_A=float(
                                    np.max(np.abs(waves["i(lbulk)"]))
                                ),
                            )
                        (rawdir / (name + ".json")).write_text(json.dumps(result, indent=2) + "\n")
                        rows.append(row)
                        print(name, row["status"], flush=True)
    (HERE / "edges.json").write_text(json.dumps(rows, indent=2) + "\n")
    fields = list(dict.fromkeys(k for row in rows for k in row))
    with (HERE / "edges.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    paths = [
        Path(__file__).resolve(),
        deck,
        D2 / "leg_matrix.cir",
        D2 / "legA-h0-best.matrix.txt",
        PS / "validation-plan/sim-kit/common/run_ngspice.py",
        PS / "validation-plan/sim-kit/common/options.inc",
    ]
    (HERE / "edge-provenance.json").write_text(
        json.dumps(
            {str(f.relative_to(ROOT)): hashlib.sha256(f.read_bytes()).hexdigest() for f in paths},
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
