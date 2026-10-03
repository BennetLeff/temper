#!/usr/bin/env python3
"""Recorded single-pass periodic runs; source physics is copied from D-19."""

from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor
import gzip
import hashlib
import json
from pathlib import Path
import re
import runpy
import shutil
import subprocess
import tempfile
import time
import numpy as np

HERE = Path(__file__).resolve().parent
D19 = HERE.parent / "out-D19"
DONOR = runpy.run_path(str(D19 / "sweep.py"))
KIT = DONOR["d"]["PS"] / "validation-plan/sim-kit"
VENDOR = KIT / "models/vendor/IFX_CFD7_650V.lib"
NGSPICE = Path("/opt/homebrew/bin/ngspice")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_binary(raw: bytes) -> dict[str, np.ndarray]:
    header, payload = raw.split(b"Binary:\n", 1)
    text = header.decode("utf-8")
    variable_count = re.search(r"No. Variables:\s+(\d+)", text)
    point_count = re.search(r"No. Points:\s+(\d+)", text)
    if (
        variable_count is None
        or point_count is None
        or "Flags: real" not in text
        or "Variables:\n" not in text
    ):
        raise ValueError("missing transient raw header fields")
    nvars = int(variable_count[1])
    npoints = int(point_count[1])
    names = [line.split()[1].lower() for line in text.split("Variables:\n")[1].splitlines()]
    values = np.frombuffer(payload, dtype=np.float64)
    if (
        npoints < 2
        or not names
        or names[0] != "time"
        or len(set(names)) != len(names)
        or len(names) != nvars
        or values.size != npoints * nvars
    ):
        raise ValueError("truncated or inconsistent binary raw file")
    values = values.reshape(npoints, nvars)
    return {name: values[:, i] for i, name in enumerate(names)}


def analyze(waves: dict[str, np.ndarray], params: dict[str, str], folder: Path) -> dict:
    freq = float(params["FREQ"])
    cycles = int(params["CYCLES"])
    end = 2e-6 + cycles / freq
    t = waves["time"]
    if len(t) < 2 or not np.isfinite(t).all() or t[-1] < end - 1e-11:
        raise ValueError("missing transient endpoint")
    if t[0] > end - 2 / freq + 1e-11 or np.any(np.diff(t) < 0):
        raise ValueError("missing first cycle or nonmonotonic time")
    data = {key: waves[key] for key in ("v(swa)", "v(swb)")}
    data["bus_current_A"] = waves["i(v.xla.vfeed)"] + waves["i(v.xlb.vfeed)"]
    phase = np.arange(524288) / 524288 / freq
    repeat, last_fft, prior_fft = {}, {}, {}
    harmonics = np.arange(int(30e6 / freq) + 1)
    for key, value in data.items():
        if not np.isfinite(value).all():
            raise ValueError("nonfinite signal")
        last = np.interp(end - 1 / freq + phase, t, value)
        prior = np.interp(end - 2 / freq + phase, t, value)
        repeat[key] = float(
            np.sqrt(np.mean((last - prior) ** 2)) / max(np.sqrt(np.mean(last**2)), 1e-6)
        )
        last_fft[key] = (2 * np.fft.rfft(last) / len(last))[harmonics]
        prior_fft[key] = (2 * np.fft.rfft(prior) / len(prior))[harmonics]
    np.savez_compressed(folder / "fft.npz", **last_fft, frequency_Hz=harmonics * freq)
    np.savez_compressed(folder / "prior-fft.npz", **prior_fft, frequency_Hz=harmonics * freq)
    return {
        "status": "complete" if max(repeat.values()) < 0.001 else "not_settled",
        "cycle_relative_RMS_change": repeat,
        "end_time_s": float(t[-1]),
        "points": len(t),
        "input_power_estimate_W": float(
            last_fft["bus_current_A"][0].real / 2 * float(params["VBUS"])
        ),
    }


def run_case(config: dict, label: str, runs_dir: Path = HERE / "periodic-runs") -> dict:
    folder = runs_dir / label
    folder.mkdir(parents=True, exist_ok=True)
    params = {
        **DONOR["BASE"],
        "VBUS": str(config["bus"]),
        "RTANK": str(config["resistance"]),
        "FREQ": str(config["freq"]),
        "DT": "443n",
        "LESL": f"{config['esl']}n",
        "TRMAX": f"{config['step']}n",
        "CYCLES": str(config["cycles"]),
    }
    options = config.get("options", "")
    deck = (D19 / "periodic-sweep.cir").read_text().replace("../common/", str(KIT / "common") + "/")
    if options:
        deck = deck.replace(".param RTANK=2", f".options {options}\n.param RTANK=2")
    identity = {
        "config": config,
        "deck_sha256": hashlib.sha256(deck.encode()).hexdigest(),
        "vendor_sha256": digest(VENDOR),
        "common_options_sha256": digest(KIT / "common/options.inc"),
        "simulator_sha256": digest(NGSPICE),
        "params": params,
    }
    saved = folder / "result.json"
    if saved.exists():
        row = json.loads(saved.read_text())
        if row["identity"] != identity:
            raise ValueError(f"cache mismatch {label}")
        return row
    (folder / "source.cir").write_text(deck)
    (folder / "params.inc").write_text(
        "".join(f".param {key}={value}\n" for key, value in params.items())
    )
    row = {"label": label, "identity": identity, "status": "indeterminate"}
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="d22-periodic-") as directory:
        temp = Path(directory)
        shutil.copyfile(folder / "source.cir", temp / "source.cir")
        shutil.copyfile(folder / "params.inc", temp / "params.inc")
        shutil.copyfile(VENDOR, temp / VENDOR.name)
        (temp / ".spiceinit").write_text("set ngbehavior=psa\nset filetype=binary\n")
        with (folder / "run.log").open("wb") as log:
            try:
                proc = subprocess.run(
                    [str(NGSPICE), "-b", "-r", "waves.raw", "source.cir"],
                    cwd=temp,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    timeout=config.get("timeout", 1800),
                    check=False,
                )
                row["returncode"] = proc.returncode
            except subprocess.TimeoutExpired:
                row["timeout"] = True
        raw = temp / "waves.raw"
        if raw.exists():
            payload = raw.read_bytes()
            with gzip.open(folder / "waves.raw.gz", "wb") as output:
                output.write(payload)
            log = (folder / "run.log").read_text(errors="replace")
            if row.get("returncode") == 0 and not re.search(
                r"timestep too small|simulation\(s\) aborted|fatal error", log, re.I
            ):
                try:
                    row.update(analyze(read_binary(payload), params, folder))
                except ValueError as error:
                    row["analysis_error"] = str(error)
    row["elapsed_seconds"] = time.monotonic() - started
    saved.write_text(json.dumps(row, indent=2) + "\n")
    print(label, row["status"], round(row["elapsed_seconds"], 1), flush=True)
    return row


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("campaign", type=Path)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument(
        "--runs-dir",
        type=Path,
        default=HERE / "periodic-runs",
        help="Use a fresh directory to repeat the campaign without replacing committed evidence.",
    )
    args = parser.parse_args()
    reproduction = json.loads((HERE / "reproduction.json").read_text())
    assert len(reproduction) == 2 and all(row["pass"] for row in reproduction)
    cases = json.loads(args.campaign.read_text())
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        rows = list(
            pool.map(lambda entry: run_case(entry["config"], entry["label"], args.runs_dir), cases)
        )
    summary = (
        HERE / (args.campaign.stem + "-results.json")
        if args.runs_dir == HERE / "periodic-runs"
        else args.runs_dir / "campaign-results.json"
    )
    summary.write_text(json.dumps(rows, indent=2) + "\n")


if __name__ == "__main__":
    main()
