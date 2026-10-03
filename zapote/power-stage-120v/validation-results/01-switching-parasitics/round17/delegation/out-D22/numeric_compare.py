#!/usr/bin/env python3
"""Compare source runs through the same receiver, preserving each terminal's complex phase."""

import csv
import gzip
import json
from pathlib import Path
import numpy as np
from qualify_filter import MODEL, exact_transfer, scenarios

HERE = Path(__file__).resolve().parent


def compare(a_path, b_path, label):
    with np.load(a_path) as data:
        a = dict(data)
    with np.load(b_path) as data:
        b = dict(data)
    np.testing.assert_allclose(a["frequency_Hz"], b["frequency_Hz"], rtol=1e-12)
    select = (a["frequency_Hz"] >= 150e3) & (a["frequency_Hz"] <= 30e6)
    a = {k: v[select] for k, v in a.items()}
    b = {k: v[select] for k, v in b.items()}
    f = a["frequency_Hz"]
    freq = int(round(np.diff(f)[0]))
    _, av, regulated = MODEL["limits"](f)
    floor = 10 ** ((av - 40) / 20) * 1e-6 * np.sqrt(2)
    rows = []
    line_rows = []
    for name in scenarios():
        added, params = scenarios()[name]
        tr = exact_transfer(name, params, freq, added)
        va = MODEL["combine"](tr, a, f)
        vb = MODEL["combine"](tr, b, f)
        for terminal in ("l_pe", "n_pe"):
            aa = abs(va[terminal])
            ab = abs(vb[terminal])
            difference = abs(va[terminal] - vb[terminal])
            da = 20 * np.log10(np.maximum(aa, 1e-30) / np.sqrt(2) / 1e-6)
            db = 20 * np.log10(np.maximum(ab, 1e-30) / np.sqrt(2) / 1e-6)
            significant = regulated & (np.maximum(aa, ab) >= floor)
            delta = abs(da - db)
            idx = (
                np.flatnonzero(significant)[np.argmax(delta[significant])]
                if significant.any()
                else 0
            )
            weak = regulated & ~significant
            row = {
                "comparison": label,
                "scenario": name,
                "terminal": terminal,
                "significant_lines": int(significant.sum()),
                "maximum_significant_line_change_dB": float(np.max(delta[significant]))
                if significant.any()
                else 0.0,
                "worst_Hz": float(f[idx]),
                "level_a_dBuV": float(da[idx]),
                "level_b_dBuV": float(db[idx]),
                "maximum_weak_complex_difference_relative_to_floor": float(
                    np.max((difference / floor)[weak])
                )
                if weak.any()
                else 0.0,
                "minimum_AV_a_dB": float(np.min((av - da)[regulated])),
                "minimum_AV_b_dB": float(np.min((av - db)[regulated])),
            }
            row["passes_0p2dB_target"] = (
                row["maximum_significant_line_change_dB"] <= 0.2
                and row["maximum_weak_complex_difference_relative_to_floor"] <= 10 ** (0.2 / 20) - 1
            )
            rows.append(row)
            line_rows.extend(
                zip(
                    [name] * len(f),
                    [terminal] * len(f),
                    f,
                    regulated,
                    significant,
                    da,
                    db,
                    delta,
                    difference,
                    difference / floor,
                )
            )
    folder = HERE / "convergence"
    folder.mkdir(exist_ok=True)
    with gzip.open(folder / (label + ".csv.gz"), "wt") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            [
                "scenario",
                "terminal",
                "Hz",
                "regulated",
                "significant",
                "a_dBuV",
                "b_dBuV",
                "abs_delta_dB",
                "complex_difference_peak_V",
                "difference_over_floor",
            ]
        )
        writer.writerows(line_rows)
    (folder / (label + ".json")).write_text(json.dumps(rows, indent=2) + "\n")
    return rows


def main():
    rows = compare(
        HERE / "v170-r2-e1.06-f60000-s2-c48-full-fft.npz",
        HERE / "v170-r2-e1.06-f60000-s0.5-c48-full-fft.npz",
        "d19-60k-2ns-to-0p5ns",
    )
    for step, previous in (("0.25", "0.5"), ("0.125", "0.25"), ("0.0625", "0.125")):
        for path in sorted((HERE / "periodic-runs").glob(f"envelope-*-s{step}/result.json")):
            fine = json.loads(path.read_text())
            coarse = path.parent.with_name(
                path.parent.name.removesuffix(f"-s{step}") + f"-s{previous}"
            )
            if not (coarse / "result.json").exists():
                continue
            if (
                fine["status"] != "complete"
                or json.loads((coarse / "result.json").read_text())["status"] != "complete"
            ):
                continue
            rows += compare(coarse / "fft.npz", path.parent / "fft.npz", path.parent.name + "-step")
            rows += compare(
                path.parent / "prior-fft.npz", path.parent / "fft.npz", path.parent.name + "-cycle"
            )
    # Preserve a larger-gap diagnostic when an intermediate tier aborted.
    # It does not enter the adjacent-tier acceptance gate.
    for path in sorted((HERE / "periodic-runs").glob("envelope-*-s0.125/result.json")):
        fine = json.loads(path.read_text())
        prefix = path.parent.name.removesuffix("-s0.125")
        middle = path.parent.with_name(prefix + "-s0.25")
        coarse = path.parent.with_name(prefix + "-s0.5")
        if fine["status"] != "complete" or not (middle / "result.json").exists():
            continue
        if json.loads((middle / "result.json").read_text())["status"] == "complete":
            continue
        if json.loads((coarse / "result.json").read_text())["status"] == "complete":
            rows += compare(coarse / "fft.npz", path.parent / "fft.npz", "diagnostic-" + prefix + "-0p5-to-0p125-gap")
            rows += compare(path.parent / "prior-fft.npz", path.parent / "fft.npz", "diagnostic-" + prefix + "-0p125-cycle")
    diagnostic = HERE / "periodic-runs/trap-v170-f35000-r2-e10-s0.5"
    reference = HERE / "periodic-runs/envelope-v170-f35000-r2-e10-s0.5"
    if (diagnostic / "result.json").exists() and json.loads((diagnostic / "result.json").read_text())["status"] == "complete":
        rows += compare(reference / "fft.npz", diagnostic / "fft.npz", "diagnostic-gear-to-trapezoidal-0p5ns")
    (HERE / "convergence-summary.json").write_text(json.dumps(rows, indent=2) + "\n")
    for label in sorted(set(r["comparison"] for r in rows)):
        selected = [r for r in rows if r["comparison"] == label]
        print(
            label,
            max(r["maximum_significant_line_change_dB"] for r in selected),
            all(r["passes_0p2dB_target"] for r in selected),
            flush=True,
        )


if __name__ == "__main__":
    main()
