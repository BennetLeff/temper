#!/usr/bin/env python3
"""Separate FFT resampling error from D-19's simulator step sensitivity."""

import gzip
import json
from pathlib import Path
import tempfile
import numpy as np
from filter_stage import MODEL, transfer

HERE = Path(__file__).resolve().parent
D19 = HERE.parent / "out-D19"


def main() -> None:
    transfers = transfer(
        "resampling-original-combined", MODEL["SCENARIOS"]["combined_sensitivity"], added=False
    )
    cases = [
        "v170-r2-e1.06-f60000-s2-c48",
        "v170-r2-e1.06-f60000-s0.5-c48",
        "v170-r2-e1.06-f35000-s0.5-c24",
    ]
    rows = []
    spectra = {}
    for tag in cases:
        case = json.loads((D19 / "periodic-runs" / (tag + ".json")).read_text())
        with tempfile.TemporaryDirectory(prefix="d22-resample-") as temp:
            raw = Path(temp) / "waves.raw"
            raw.write_bytes(
                gzip.decompress((D19 / "periodic-runs" / (tag + ".raw.gz")).read_bytes())
            )
            waves = MODEL["read_raw"](raw)
        t = np.asarray(waves["time"])
        period = 1 / case["frequency_Hz"]
        end = 2e-6 + case["cycles"] * period
        data = {k: np.asarray(waves[k]) for k in ("v(swa)", "v(swb)")}
        data["bus_current_A"] = np.asarray(waves["i(v.xla.vfeed)"]) + np.asarray(
            waves["i(v.xlb.vfeed)"]
        )
        reference = None
        for count in (32768, 131072, 524288):
            phase = np.arange(count) / count * period
            index = np.arange(int(30e6 * period) + 1)
            f = index / period
            select = f >= 150e3
            f = f[select]
            signals = {
                key: (2 * np.fft.rfft(np.interp(end - period + phase, t, value)) / count)[
                    index[select]
                ]
                for key, value in data.items()
            }
            if count == 524288:
                full = {
                    key: (2 * np.fft.rfft(np.interp(end - period + phase, t, value)) / count)[index]
                    for key, value in data.items()
                }
                np.savez_compressed(
                    HERE / f"{tag}-full-fft.npz", **full, frequency_Hz=index / period
                )
            outputs = MODEL["combine"](transfers, signals, f)
            level = 20 * np.log10(
                np.maximum(abs(outputs["l_pe"]), abs(outputs["n_pe"])) / np.sqrt(2) / 1e-6
            )
            if reference is None:
                reference = level
            row = {
                "case": tag,
                "samples": count,
                "max_line_delta_from_32768_dB": float(np.max(abs(level - reference))),
            }
            rows.append(row)
            spectra[(tag, count)] = level
            print(row, flush=True)
            np.savez_compressed(HERE / f"{tag}-n{count}-fft.npz", **signals, frequency_Hz=f)
    for count in (32768, 131072, 524288):
        rows.append(
            {
                "comparison": "60kHz 2ns versus 0.5ns",
                "samples": count,
                "max_line_delta_dB": float(
                    np.max(abs(spectra[(cases[0], count)] - spectra[(cases[1], count)]))
                ),
            }
        )
    (HERE / "resampling.json").write_text(json.dumps(rows, indent=2) + "\n")


if __name__ == "__main__":
    main()
