#!/usr/bin/env python3
"""Exact-harmonic AC solution, complex mode separation, and retained line evidence."""

from concurrent.futures import ThreadPoolExecutor
import csv
import gzip
import itertools
import json
from pathlib import Path
import subprocess
import tempfile
import numpy as np
from filter_stage import MODEL, deck_text

HERE = Path(__file__).resolve().parent
NOMINAL = {
    "LCMADD": 1.6e-3,
    "LDMADD": 18e-6,
    "LNEW": 0,
    "CXIN": 2.2e-6,
    "CYHF": 2.2e-9,
    "ESLYHF": 10e-9,
    "CYADD": 4.7e-9,
    "ESLYADD": 15e-9,
    "ESRYADD": 0.1,
    "LRDAMP": 500e-9,
}
MEASURE = (
    "i(ldamp)",
    "i(lnewx)",
    "i(lxin)",
    "i(lcmaddl)",
    "i(lcmaddn)",
    "i(lyaddl)",
    "i(lyaddn)",
    "v(line_mid)",
    "v(neut_mid)",
)


def scenarios():
    rows = {
        "original_nominal": (False, {}),
        "original_combined": (False, MODEL["SCENARIOS"]["combined_sensitivity"]),
        "proposed_nominal": (True, NOMINAL),
    }
    # Finite sensitivity grid, not a guaranteed component or mathematical bound.
    for old_l, new_l, coil, leak in itertools.product(
        (1.12e-3, 2.4e-3), (1.12e-3, 2.4e-3), (5e-12, 50e-12), (9e-6, 27e-6)
    ):
        name = f"corner-old{old_l:g}-new{new_l:g}-coil{coil:g}-leak{leak:g}"
        p = {
            **NOMINAL,
            "LCM": old_l,
            "LCMADD": new_l,
            "CCOILA": coil,
            "CCOILB": coil,
            "LDMADD": leak,
            "CTABA": 50.4e-12,
            "CTABB": 33.6e-12,
            "CXIN": 1.98e-6,
            "CYHF": 1.76e-9,
            "CXNEW": 4.23e-6,
            "CDAMP": 4.23e-6,
            "CYADD": 3.76e-9,
            "RCH": 6e-3,
            "RCMADD": 6e-3,
            "RDAMP": 4.095,
        }
        rows[name] = (True, p)
    stress = rows["corner-old0.00112-new0.00112-coil5e-11-leak9e-06"][1]
    rows.update(
        {
            "high_caps": (
                True,
                {
                    **stress,
                    "CXIN": 2.42e-6,
                    "CYHF": 2.64e-9,
                    "CXNEW": 5.17e-6,
                    "CDAMP": 5.17e-6,
                    "CYADD": 5.64e-9,
                },
            ),
            "high_parasitics": (
                True,
                {
                    **stress,
                    "ESLC": 40e-9,
                    "ESLYADD": 50e-9,
                    "ESLYHF": 25e-9,
                    "LRDAMP": 2e-6,
                    "CCH": 22.156e-12,
                    "CCMADD": 22.156e-12,
                },
            ),
            "low_parasitics": (
                True,
                {
                    **stress,
                    "ESLC": 10e-9,
                    "ESLYADD": 5e-9,
                    "ESLYHF": 5e-9,
                    "LRDAMP": 100e-9,
                    "CCH": 5.539e-12,
                    "CCMADD": 5.539e-12,
                },
            ),
            "low_damping": (True, {**stress, "RDAMP": 3.705, "ESRC": 0.0175, "ESRYADD": 0.05}),
            "high_RF_loss": (
                True,
                {**stress, "ESRC": 0.07, "ESRYADD": 0.2, "RLOSSCH": 6345.5, "RLCMADD": 6345.5},
            ),
            "low_RF_loss": (True, {**stress, "RLOSSCH": 25382, "RLCMADD": 25382}),
            "old_low_leakage": (True, {**stress, "LDM": 9e-6, "CX": 0.8e-6, "CY": 1.76e-9}),
            "all_high_parasitics": (
                True,
                {
                    **stress,
                    "LDM": 9e-6,
                    "CX": 0.8e-6,
                    "CY": 1.76e-9,
                    "ESLC": 40e-9,
                    "ESLX": 25e-9,
                    "ESLYADD": 50e-9,
                    "ESLYHF": 25e-9,
                    "LRDAMP": 2e-6,
                    "CCH": 22.156e-12,
                    "CCMADD": 22.156e-12,
                    "LPE": 200e-9,
                },
            ),
            "tabs_reversed": (True, {**stress, "CTABA": 33.6e-12, "CTABB": 50.4e-12}),
        }
    )
    return rows


def exact_transfer(name, params, freq, added=True):
    folder = HERE / "harmonic-transfer-v3"
    folder.mkdir(exist_ok=True)
    result = {}
    n = int(30e6 / freq)
    for source in ("A", "B", "DM"):
        tag = f"{name}-f{freq}-{source}"
        saved = folder / (tag + ".npz")
        deck = deck_text(params, source, added).replace(
            ".ac lin 30000 150k 30meg", f".ac lin {n} {freq} {n * freq}"
        )
        if added:
            deck = deck.replace(".ac lin", ".save " + " ".join(MEASURE) + "\n.ac lin")
        if saved.exists():
            if (folder / (tag + ".cir")).read_text() != deck:
                raise ValueError(f"AC cache mismatch: {tag}")
            with np.load(saved) as data:
                result[source] = dict(data)
            continue
        with tempfile.TemporaryDirectory(prefix="d22-harmonic-") as directory:
            temp = Path(directory)
            (temp / "case.cir").write_text(deck)
            (temp / ".spiceinit").write_text("set filetype=ascii\n")
            proc = subprocess.run(
                ["/opt/homebrew/bin/ngspice", "-b", "-r", "waves.raw", "case.cir"],
                cwd=temp,
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            (folder / (tag + ".log")).write_text(proc.stdout + proc.stderr)
            if proc.returncode:
                raise RuntimeError(tag)
            keep = ("frequency", "v(lisn_l)", "v(lisn_n)", "v(pe)") + (MEASURE if added else ())
            waves = {
                k: np.asarray(v)
                for k, v in MODEL["read_raw"](temp / "waves.raw").items()
                if k in keep
            }
        if (
            len(waves) != len(keep)
            or len(waves["frequency"]) != n
            or not all(np.isfinite(a).all() for a in waves.values())
        ):
            raise ValueError("Invalid AC capture")
        np.testing.assert_allclose(waves["frequency"].real, np.arange(1, n + 1) * freq, rtol=1e-12)
        (folder / (tag + ".cir")).write_text(deck)
        np.savez_compressed(saved, **waves)
        result[source] = waves
    return result


def load_sources():
    sources = {}
    for tag in ("v170-r2-e1.06-f35000-s0.5-c24", "v170-r2-e1.06-f60000-s0.5-c48"):
        with np.load(HERE / (tag + "-full-fft.npz")) as data:
            sources["d19-" + tag] = dict(data)
    for path in sorted((HERE / "periodic-runs").glob("envelope-*/result.json")):
        row = json.loads(path.read_text())
        if row["status"] == "complete":
            with np.load(path.parent / "fft.npz") as data:
                sources[path.parent.name] = dict(data)
    return sources


def transformed(transfers, signals, f, key):
    value = np.zeros(len(f), complex)
    for source, signal in (("A", "v(swa)"), ("B", "v(swb)"), ("DM", "bus_current_A")):
        w = transfers[source]
        h = w[key]
        grid = w["frequency"].real
        value += (np.interp(f, grid, h.real) + 1j * np.interp(f, grid, h.imag)) * signals[signal]
    return value


def main():
    sources = load_sources()
    conditions = scenarios()
    jobs = list(itertools.product(conditions, (35000, 60000)))

    def run(job):
        name, freq = job
        added, params = conditions[name]
        return job, exact_transfer(name, params, freq, added)

    with ThreadPoolExecutor(max_workers=4) as pool:
        transfers = dict(pool.map(run, jobs))
    rows = []
    losses = []
    folder = HERE / "qualified-spectra"
    folder.mkdir(exist_ok=True)
    for case, signals in sources.items():
        freq = int(round(np.diff(signals["frequency_Hz"])[0]))
        select = signals["frequency_Hz"] > 0
        signals = {k: v[select] for k, v in signals.items()}
        f = signals["frequency_Hz"]
        qp, av, regulated = MODEL["limits"](f)
        for name, (added, params) in conditions.items():
            tr = transfers[name, freq]
            v = MODEL["combine"](tr, signals, f)
            levels = {
                key: 20 * np.log10(np.maximum(abs(signal), 1e-30) / np.sqrt(2) / 1e-6)
                for key, signal in {
                    "L": v["l_pe"],
                    "N": v["n_pe"],
                    "CM": (v["l_pe"] + v["n_pe"]) / 2,
                    "DM": (v["l_pe"] - v["n_pe"]) / 2,
                }.items()
            }
            levels["terminal"] = np.maximum(levels["L"], levels["N"])
            for mode, level in levels.items():
                i = np.flatnonzero(regulated)[np.argmin((av - level)[regulated])]
                rows.append(
                    {
                        "case": case,
                        "scenario": name,
                        "mode": mode,
                        "AV_dB": float((av - level)[i]),
                        "QP_dB": float((qp - level)[i]),
                        "Hz": float(f[i]),
                    }
                )
            with gzip.open(folder / (case + "-" + name + ".csv.gz"), "wt") as stream:
                writer = csv.writer(stream)
                writer.writerow(
                    [
                        "Hz",
                        "regulated",
                        "QP_limit_dBuV",
                        "AV_limit_dBuV",
                        *[k + "_dBuV" for k in levels],
                        "terminal_AV_margin_dB",
                    ]
                )
                writer.writerows(
                    zip(f, regulated, qp, av, *levels.values(), av - levels["terminal"])
                )
            if added and f[0] == freq:
                current = {
                    key: float(np.sqrt(np.sum(abs(transformed(tr, signals, f, key)) ** 2) / 2))
                    for key in MEASURE
                    if key.startswith("i(")
                }
                losses.append(
                    {
                        "case": case,
                        "scenario": name,
                        "harmonic_current_RMS_A": current,
                        "damping_HF_W": current["i(ldamp)"] ** 2 * params.get("RDAMP", 3.9),
                        "added_choke_HF_copper_W": sum(
                            current[k] ** 2 for k in ("i(lcmaddl)", "i(lcmaddn)")
                        )
                        * params.get("RCMADD", 0.0045),
                    }
                )
    (HERE / "filter-scenarios.json").write_text(json.dumps(conditions, indent=2) + "\n")
    (HERE / "qualified-margin-results.json").write_text(json.dumps(rows, indent=2) + "\n")
    (HERE / "harmonic-loss-results.json").write_text(json.dumps(losses, indent=2) + "\n")
    for case in sources:
        selected = [
            r
            for r in rows
            if r["case"] == case
            and r["mode"] == "terminal"
            and r["scenario"].startswith(
                ("proposed", "corner", "high", "low", "tabs", "old_low", "all_high")
            )
        ]
        print(min(selected, key=lambda r: r["AV_dB"]), flush=True)


if __name__ == "__main__":
    main()
