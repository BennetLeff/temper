#!/usr/bin/env python3
"""Coherent harmonic pre-check; line amplitudes are not receiver detector results."""

from pathlib import Path
import csv
import gzip
import json
import re
import runpy
import subprocess
import tempfile
import numpy as np

HERE = Path(__file__).resolve().parent
PREP = runpy.run_path(str(HERE / "prepare.py"))
from run_ngspice import read_raw

SCENARIOS = {
    "r3_nominal": {},
    "proposal_dm36u_x2p2u": {"LDM": 36e-6, "CX": 2.2e-6},
    "proposal_dm36u_x4p7u": {"LDM": 36e-6, "CX": 4.7e-6},
    "l1_minus30": {"LCM": 1.12e-3},
    "l1_plus50": {"LCM": 2.4e-3},
    "coil10p": {"CCOILA": 5e-12, "CCOILB": 5e-12},
    "coil100p": {"CCOILA": 50e-12, "CCOILB": 50e-12},
    "tabs20pct": {"CTABA": 50.4e-12, "CTABB": 33.6e-12},
    "combined_sensitivity": {
        "LCM": 1.12e-3,
        "CCOILA": 50e-12,
        "CCOILB": 50e-12,
        "CTABA": 50.4e-12,
        "CTABB": 33.6e-12,
    },
}


def limits(f):
    """47 CFR 18.307(a): tighter boundary value; 18.307(e)/18.301 exclusions."""
    f = np.asarray(f)
    qp = np.where(
        f < 500e3, 66 - 10 * np.log(f / 150e3) / np.log(500 / 150), np.where(f <= 5e6, 56.0, 60.0)
    )
    av = qp - 10
    mask = (f >= 150e3) & (f <= 30e6)
    for center, width in ((6.78e6, 15e3), (13.56e6, 7e3), (27.12e6, 163e3)):
        mask &= abs(f - center) > width
    return qp, av, mask


def transfer(name, params):
    folder = HERE / "transfer"
    folder.mkdir(exist_ok=True)
    result = {}
    for source in ("A", "B", "DM"):
        tag = name + "-" + source
        saved = folder / (tag + ".npz")
        deck = (PREP["R3"] / "scripts/emi_topology.cir").read_text()
        excitation = {f"EXC_{key}": int(key == source) for key in ("A", "B", "DM")}
        for key, value in {**params, **excitation}.items():
            deck, count = re.subn(
                rf"(?m)^([.]param .*\b{key}=)([^\s]+)", lambda m: m[1] + str(value), deck
            )
            if count != 1:
                raise ValueError(key)
        if saved.exists():
            if (folder / (tag + ".cir")).read_text() != deck:
                raise ValueError(f"AC cache inputs changed: {tag}; rerun in a fresh output folder")
            with np.load(saved) as data:
                result[source] = {key: data[key] for key in data.files}
            continue
        with tempfile.TemporaryDirectory(prefix="d19-transfer-") as directory:
            tmp = Path(directory)
            (tmp / "case.cir").write_text(deck)
            (tmp / ".spiceinit").write_text("set filetype=ascii\n")
            run = subprocess.run(
                ["/opt/homebrew/bin/ngspice", "-b", "-r", "waves.raw", "case.cir"],
                cwd=tmp,
                text=True,
                capture_output=True,
                check=True,
            )
            (folder / (tag + ".log")).write_text(run.stdout + run.stderr)
            w = {
                k: np.asarray(v)
                for k, v in read_raw(tmp / "waves.raw").items()
                if k in ("frequency", "v(lisn_l)", "v(lisn_n)", "v(pe)")
            }
        if len(w["frequency"]) != 30000 or not all(np.isfinite(a).all() for a in w.values()):
            raise ValueError("bad AC waveform")
        (folder / (tag + ".cir")).write_text(deck)
        np.savez_compressed(saved, **w)
        result[source] = w
    return result


def combine(transfers, signals, f):
    outputs = {}
    for terminal in ("l", "n"):
        for reference in ("pe", "earth"):
            v = np.zeros(len(f), complex)
            for source, key in (("A", "v(swa)"), ("B", "v(swb)"), ("DM", "bus_current_A")):
                w = transfers[source]
                h = w[f"v(lisn_{terminal})"] - (w["v(pe)"] if reference == "pe" else 0)
                h = np.interp(f, w["frequency"].real, h.real) + 1j * np.interp(
                    f, w["frequency"].real, h.imag
                )
                v += h * signals[key]
            outputs[terminal + "_" + reference] = v
    return outputs


def main():
    alltransfers = {name: transfer(name, p) for name, p in SCENARIOS.items()}
    cases = [json.loads(p.read_text()) for p in sorted((HERE / "periodic-runs").glob("*.json"))]
    summaries = []
    folder = HERE / "spectra"
    folder.mkdir(exist_ok=True)
    for case in cases:
        if case["status"] != "complete":
            continue
        tag = case["tag"]
        freq = case["frequency_Hz"]
        with np.load(HERE / "periodic-runs" / (tag + "-fft.npz")) as data:
            harmonics = np.arange(len(data["v(swa)"]))
            f = harmonics * freq
            select = (f >= 150e3) & (f <= 30e6)
            f = f[select]
            signals = {key: data[key][select] for key in data.files}
        prior_path = HERE / "periodic-runs" / (tag + "-prior-fft.npz")
        if not prior_path.exists():
            raise RuntimeError("Run replay_periodic.py before spectrum.py")
        with np.load(prior_path) as data:
            prior_signals = {key: data[key][select] for key in data.files}
        qp, av, regulated = limits(f)
        for name, transfers in alltransfers.items():
            outputs = combine(transfers, signals, f)
            levels = {
                key: 20 * np.log10(np.maximum(abs(v) / np.sqrt(2), 1e-30) / 1e-6)
                for key, v in outputs.items()
            }
            worst = np.maximum(levels["l_pe"], levels["n_pe"])
            headroom = av - worst
            index = np.flatnonzero(regulated)[np.argmin(headroom[regulated])]
            summary = {
                "case": tag,
                "scenario": name,
                "frequency_Hz": float(f[index]),
                "terminal": "L" if levels["l_pe"][index] >= levels["n_pe"][index] else "N",
                "rms_line_dBuV": float(worst[index]),
                "AV_line_headroom_dB": float(headroom[index]),
                "QP_line_headroom_dB": float(qp[index] - worst[index]),
                "peak_line_vs_AV_dB": float(headroom[index] - 10 * np.log10(2)),
                "old_earth_reference_min_AV_dB": float(
                    np.min((av - np.maximum(levels["l_earth"], levels["n_earth"]))[regulated])
                ),
            }
            prior = combine(transfers, prior_signals, f)
            prior_worst = 20 * np.log10(
                np.maximum(np.maximum(abs(prior["l_pe"]), abs(prior["n_pe"])) / np.sqrt(2), 1e-30)
                / 1e-6
            )
            summary["prior_cycle_min_AV_dB"] = float(np.min((av - prior_worst)[regulated]))
            summary["min_AV_cycle_change_dB"] = (
                summary["AV_line_headroom_dB"] - summary["prior_cycle_min_AV_dB"]
            )
            summaries.append(summary)
            cm = (outputs["l_pe"] + outputs["n_pe"]) / 2
            dm = (outputs["l_pe"] - outputs["n_pe"]) / 2
            with gzip.open(folder / (tag + "-" + name + ".csv.gz"), "wt") as stream:
                writer = csv.writer(stream)
                writer.writerow(
                    [
                        "Hz",
                        "L_rms_dBuV",
                        "N_rms_dBuV",
                        "CM_rms_dBuV",
                        "DM_rms_dBuV",
                        "QP_limit",
                        "AV_limit",
                        "regulated",
                        "AV_line_headroom_dB",
                        "L_earth_rms_dBuV",
                        "N_earth_rms_dBuV",
                    ]
                )
                writer.writerows(
                    zip(
                        f,
                        levels["l_pe"],
                        levels["n_pe"],
                        20 * np.log10(np.maximum(abs(cm) / np.sqrt(2), 1e-30) / 1e-6),
                        20 * np.log10(np.maximum(abs(dm) / np.sqrt(2), 1e-30) / 1e-6),
                        qp,
                        av,
                        regulated,
                        headroom,
                        levels["l_earth"],
                        levels["n_earth"],
                    )
                )
    (HERE / "margin-results.json").write_text(json.dumps(summaries, indent=2) + "\n")
    if summaries:
        with (HERE / "margins.csv").open("w") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(summaries[0]))
            writer.writeheader()
            writer.writerows(summaries)
    print(
        json.dumps(
            {
                "settled_cases": sum(c["status"] == "complete" for c in cases),
                "worst": min(summaries, key=lambda r: r["AV_line_headroom_dB"])
                if summaries
                else None,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
