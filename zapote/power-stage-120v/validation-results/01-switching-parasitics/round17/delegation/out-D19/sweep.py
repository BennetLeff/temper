#!/usr/bin/env python3
"""Conditional two-leg periodic RLC source sweep, not physical EMI qualification."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import gzip
import json
import runpy
import tempfile
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
d = runpy.run_path(str(HERE / "prepare.py"))
from run_ngspice import read_raw

mod = runpy.run_path(str(d["D2"] / "run_d2.py"))
BASE = mod["matrix_params"](mod["read_L"](str(d["D2"] / "legA-h0-best.matrix.txt")))


def case(config):
    bus, resistance, esl, freq, step, cycles = config
    tag = f"v{bus}-r{resistance}-e{esl}-f{freq}-s{step}-c{cycles}"
    folder = HERE / "periodic-runs"
    folder.mkdir(exist_ok=True)
    output = folder / (tag + ".json")
    if output.exists():
        return json.loads(output.read_text())
    params = {
        **BASE,
        "VBUS": str(bus),
        "RTANK": str(resistance),
        "FREQ": str(freq),
        "DT": "443n",
        "LESL": f"{esl}n",
        "TRMAX": f"{step}n",
        "CYCLES": str(cycles),
    }
    with tempfile.TemporaryDirectory(prefix="d19-periodic-sweep-") as directory:
        tmp = Path(directory)
        result = d["run"](HERE / "periodic-sweep.cir", params, keep=tmp, raw=True)
        result.pop("run_dir", None)
        for name in ("run.log", "raw_run.log", "params.inc"):
            (folder / (tag + "-" + name)).write_bytes((tmp / name).read_bytes())
        if (tmp / "waves.raw").exists():
            with gzip.open(folder / (tag + ".raw.gz"), "wb") as f:
                f.write((tmp / "waves.raw").read_bytes())
        result.update(
            tag=tag,
            bus_V=bus,
            tank_R_ohm=resistance,
            esl_nH=esl,
            frequency_Hz=freq,
            step_ns=step,
            cycles=cycles,
            status="indeterminate",
        )
        if not result["aborted"] and not result["failed"]:
            w = read_raw(tmp / "waves.raw")
            t = np.asarray(w["time"])
            period = 1 / freq
            end = 2e-6 + cycles * period
            if t[-1] < end - 1e-11:
                raise RuntimeError("truncated waveform")
            phase = np.arange(32768) / 32768 * period
            signals = {key: np.asarray(w[key]) for key in ("v(swa)", "v(swb)")}
            signals["bus_current_A"] = np.asarray(w["i(v.xla.vfeed)"]) + np.asarray(
                w["i(v.xlb.vfeed)"]
            )
            repeat = {}
            fft = {}
            for key, values in signals.items():
                if not np.isfinite(values).all():
                    raise RuntimeError("nonfinite waveform")
                last = np.interp(end - period + phase, t, values)
                prior = np.interp(end - 2 * period + phase, t, values)
                norm = max(np.sqrt(np.mean(last**2)), 1e-6)
                repeat[key] = float(np.sqrt(np.mean((last - prior) ** 2)) / norm)
                fft[key] = 2 * np.fft.rfft(last) / len(last)
            result["cycle_relative_RMS_change"] = repeat
            result["mean_bus_current_A"] = float(fft["bus_current_A"][0].real / 2)
            result["mean_input_power_estimate_W"] = result["mean_bus_current_A"] * bus
            result["status"] = "complete" if max(repeat.values()) < 0.01 else "not_settled"
            np.savez_compressed(folder / (tag + "-fft.npz"), **fft)
    output.write_text(json.dumps(result, indent=2) + "\n")
    print(tag, result["status"], flush=True)
    return result


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--fine", action="store_true")
    a.add_argument("--repairs", action="store_true")
    args = a.parse_args()
    source = (
        (HERE / "periodic-tank.cir")
        .read_text()
        .replace("prescribed tank current", "series RLC load")
        .replace(
            ".tran {TRMAX} {T1+CYCLES/FREQ} 0 {TRMAX}",
            ".tran {TRMAX} {T1+CYCLES/FREQ} {T1+(CYCLES-2)/FREQ} {TRMAX}",
        )
    )
    (HERE / "periodic-sweep.cir").write_text(source)
    configs = [
        (bus, res, esl, freq, 2, 12)
        for bus in (170, 198)
        for res in (2, 100)
        for esl in (1.06, 10)
        for freq in (35000, 60000)
    ]
    if args.fine:
        configs = [(170, 2, 1.06, 60000, 0.5, 48)]
    if args.repairs:
        configs = [(170, 2, 1.06, 60000, 2, 48), (170, 2, 1.06, 35000, 0.5, 24)]
    with ThreadPoolExecutor(max_workers=2) as pool:
        rows = list(pool.map(case, configs))
    (
        HERE
        / (
            "periodic-fine.json"
            if args.fine
            else "periodic-repairs.json"
            if args.repairs
            else "periodic-results.json"
        )
    ).write_text(json.dumps(rows, indent=2) + "\n")


if __name__ == "__main__":
    main()
