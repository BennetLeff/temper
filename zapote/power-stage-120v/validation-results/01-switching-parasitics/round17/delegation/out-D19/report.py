#!/usr/bin/env python3
"""Generate numeric report tables and source-provenance manifest."""

import gzip
import hashlib
import json
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
PREP = runpy.run_path(str(HERE / "prepare.py"))


def main():
    edges = json.loads((HERE / "edges.json").read_text())
    rows = [
        "| Bus V | Current A | ESL nH | Direction | 10–90 ns | Mean V/ns | Max V/ns | Ring MHz estimate | Decay ns estimate | Incoming VDS V | ZVS |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in edges:
        values = (
            [r["bus_V"], r["current_A"], r["esl_nH"], r["direction"]]
            + [
                f"{r[k]:.2f}" if r[k] is not None else "unresolved"
                for k in (
                    "edge_10_90_ns",
                    "mean_10_90_V_per_ns",
                    "max_abs_slope_V_per_ns",
                    "ring_estimate_MHz",
                    "decay_estimate_ns",
                    "incoming_VDS_V",
                )
            ]
            + [str(r["zvs"])]
        )
        rows.append("| " + " | ".join(map(str, values)) + " |")
    (HERE / "edge-table.md").write_text("\n".join(rows) + "\n")
    cases = [json.loads(p.read_text()) for p in sorted((HERE / "periodic-runs").glob("*.json"))]
    rows = [
        "| Case | Status | Maximum cycle RMS change % | Estimated input W |",
        "|---|---|---|---|",
    ]
    for r in cases:
        change = max(r.get("cycle_relative_RMS_change", {}).values(), default=float("nan")) * 100
        rows.append(
            f"| {r['tag']} | {r['status']} | {change:.3f} | {r.get('mean_input_power_estimate_W', float('nan')):.2f} |"
        )
    (HERE / "periodic-table.md").write_text("\n".join(rows).replace("nan", "—") + "\n")
    margins = json.loads((HERE / "margin-results.json").read_text())
    rows = [
        "| Case | Filter scenario | Worst terminal / MHz | RMS line dBµV | AV-line headroom dB | QP-line headroom dB | Old earth-reference AV dB |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in margins:
        rows.append(
            f"| {r['case']} | {r['scenario']} | {r['terminal']} / {r['frequency_Hz'] / 1e6:.3f} | {r['rms_line_dBuV']:.2f} | {r['AV_line_headroom_dB']:.2f} | {r['QP_line_headroom_dB']:.2f} | {r['old_earth_reference_min_AV_dB']:.2f} |"
        )
    (HERE / "margin-table.md").write_text("\n".join(rows) + "\n")
    if margins:
        worst = min(margins, key=lambda r: r["AV_line_headroom_dB"])
        fig, axes = plt.subplots(2, 1, figsize=(11, 8), sharex=True)
        for name in ("r3_nominal", "l1_minus30", "coil100p", "tabs20pct", "combined_sensitivity"):
            path = HERE / "spectra" / (worst["case"] + "-" + name + ".csv.gz")
            with gzip.open(path, "rt") as stream:
                data = np.genfromtxt(stream, delimiter=",", names=True)
            f = data["Hz"] / 1e6
            axes[0].plot(
                f,
                np.maximum(data["L_rms_dBuV"], data["N_rms_dBuV"]),
                label=name,
                lw=0,
                marker=".",
                markersize=3,
            )
        axes[0].plot(f, data["AV_limit"], "k--", label="AV limit (line comparison only)")
        axes[0].plot(f, data["QP_limit"], "k:", label="QP limit (line comparison only)")
        for key in ("CM_rms_dBuV", "DM_rms_dBuV"):
            axes[1].plot(f, data[key], label=key, lw=0, marker=".", markersize=3)
        for ax in axes:
            ax.set_xscale("log")
            ax.grid(alpha=0.2)
            ax.legend(fontsize=8)
            ax.set_ylabel("RMS harmonic line dBµV")
        axes[1].set_xlabel("Frequency MHz; discrete harmonic amplitudes, not a broadband envelope")
        fig.suptitle("Conditional RLC source: " + worst["case"])
        fig.tight_layout()
        fig.savefig(HERE / "spectrum.png", dpi=160)
        plt.close(fig)
    sourcepaths = [p for p in HERE.iterdir() if p.suffix in (".py", ".cir")]
    sourcepaths += [
        PREP["D2"] / "legA-h0-best.matrix.txt",
        PREP["D2"] / "leg_matrix.cir",
        PREP["R3"] / "scripts/emi_topology.cir",
        PREP["R3"] / "scripts/check_topology.py",
        PREP["PS"] / "validation-plan/sim-kit/common/run_ngspice.py",
        PREP["PS"] / "validation-plan/sim-kit/common/options.inc",
    ]
    vendor = PREP["PS"] / "validation-plan/sim-kit/models/vendor/IFX_CFD7_650V.lib"
    vendor_sha = hashlib.sha256(vendor.read_bytes()).hexdigest()
    assert vendor_sha == "02ac6634f47c25be04e8de3c6eec4ec8cf403b659001b7f176c8f98bb6e9ce3b"
    simulator = Path(shutil.which("ngspice"))
    runtime = {
        "python": sys.version,
        "numpy": np.__version__,
        "ngspice_sha256": hashlib.sha256(simulator.read_bytes()).hexdigest(),
        "ngspice_version": subprocess.run(
            [str(simulator), "--version"], text=True, capture_output=True, check=True
        ).stdout,
        "vendor_library_sha256": vendor_sha,
    }
    manifest = {
        str(p.relative_to(PREP["ROOT"])): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(sourcepaths)
    }
    (HERE / "provenance.json").write_text(
        json.dumps(
            {
                "base_commit": "b30b3ae35a4bd3ad5c22d8c300c4640986e1232a",
                "source_sha256": manifest,
                "runtime": runtime,
                "periodic_status_counts": {
                    status: sum(r["status"] == status for r in cases)
                    for status in ("complete", "not_settled", "indeterminate")
                },
                "worst_model_line": min(margins, key=lambda r: r["AV_line_headroom_dB"])
                if margins
                else None,
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
