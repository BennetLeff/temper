#!/usr/bin/env python3
"""Verify stored periodic FFTs against compressed raw waveforms; no SPICE run."""

import gzip
import json
from pathlib import Path
import runpy
import tempfile
import numpy as np

HERE = Path(__file__).resolve().parent
runpy.run_path(str(HERE / "prepare.py"))
from run_ngspice import read_raw


def main():
    checked = []
    for path in sorted((HERE / "periodic-runs").glob("*.json")):
        row = json.loads(path.read_text())
        if row["aborted"] or row["failed"]:
            assert row["status"] == "indeterminate"
            continue
        with tempfile.TemporaryDirectory(prefix="d19-replay-") as directory:
            raw = Path(directory) / "waves.raw"
            with gzip.open(path.with_suffix(".raw.gz"), "rb") as stream:
                raw.write_bytes(stream.read())
            waves = read_raw(raw)
        t = np.asarray(waves["time"])
        period = 1 / row["frequency_Hz"]
        end = 2e-6 + row["cycles"] * period
        assert t[-1] >= end - 1e-11
        phase = np.arange(32768) / 32768 * period
        signals = {key: np.asarray(waves[key]) for key in ("v(swa)", "v(swb)")}
        signals["bus_current_A"] = np.asarray(waves["i(v.xla.vfeed)"]) + np.asarray(
            waves["i(v.xlb.vfeed)"]
        )
        repeats = []
        prior_fft = {}
        with np.load(path.parent / (row["tag"] + "-fft.npz")) as saved:
            for key, values in signals.items():
                assert np.isfinite(values).all()
                last = np.interp(end - period + phase, t, values)
                prior = np.interp(end - 2 * period + phase, t, values)
                repeat = float(
                    np.sqrt(np.mean((last - prior) ** 2)) / max(np.sqrt(np.mean(last**2)), 1e-6)
                )
                repeats.append(repeat)
                prior_fft[key] = 2 * np.fft.rfft(prior) / len(prior)
                np.testing.assert_allclose(
                    saved[key], 2 * np.fft.rfft(last) / len(last), rtol=1e-12, atol=1e-12
                )
                assert abs(repeat - row["cycle_relative_RMS_change"][key]) < 1e-12
        assert (max(repeats) < 0.01) == (row["status"] == "complete")
        np.savez_compressed(path.parent / (row["tag"] + "-prior-fft.npz"), **prior_fft)
        checked.append(row["tag"])
    (HERE / "replay-check.json").write_text(
        json.dumps({"status": "PASS", "periodic_waveforms_replayed": checked}, indent=2) + "\n"
    )
    print("PASS:", len(checked), "periodic raw waveforms")


if __name__ == "__main__":
    main()
