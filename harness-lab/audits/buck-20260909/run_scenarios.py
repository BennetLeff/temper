"""Snapshot and run exploratory ngspice scenarios; native .meas computes results."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCENARIOS = ("startup", "input_variation", "load_variation", "datasheet_holdout")
CONTROL = """
.control
set filetype=binary
run
let pin = -v(in)*i(vin)
let pout = v(out)*i(v_load)
let gate_overlap = v(x_u1.gh)*v(x_u1.gl)/25
meas tran vout_avg AVG v(out) from=10m to=12m
meas tran vout_min MIN v(out) from=10m to=12m
meas tran vout_max MAX v(out) from=10m to=12m
meas tran il_avg AVG i(l_out) from=10m to=12m
meas tran il_min MIN i(l_out) from=10m to=12m
meas tran il_max MAX i(l_out) from=10m to=12m
meas tran pin_avg AVG pin from=10m to=12m
meas tran pout_avg AVG pout from=10m to=12m
meas tran gate_overlap_max MAX gate_overlap from=0 to=12m
meas tran vout_before AVG v(out) from=5m to=5.9m
meas tran vout_loaded AVG v(out) from=7.5m to=8.5m
meas tran transition_low MIN v(out) from=6m to=6.5m
meas tran transition_high MAX v(out) from=9m to=9.5m
meas tran switching_span TRIG v(x_u1.gh) val=2.5 rise=1 td=10m TARG v(x_u1.gh) val=2.5 rise=101 td=10m
write waveform.raw all
quit
.endc
"""
MEASUREMENT_NAMES = tuple(re.findall(r"^meas\s+tran\s+(\S+)", CONTROL, flags=re.MULTILINE))
MEASUREMENT_RESULT = re.compile(r"^\s*(\S+)\s*=\s*(\S+)")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def measurement_results(log: Path) -> tuple[dict[str, float], list[str]]:
    """Parse native .meas output and report absent/non-finite measurements."""
    results: dict[str, float] = {}
    for line in log.read_text(errors="replace").splitlines():
        match = MEASUREMENT_RESULT.match(line)
        if not match or match.group(1) not in MEASUREMENT_NAMES:
            continue
        try:
            value = float(match.group(2))
        except ValueError:
            continue
        if math.isfinite(value):
            results[match.group(1)] = value
    missing = [name for name in MEASUREMENT_NAMES if name not in results]
    return results, missing


def run(output: Path, scenarios: list[str], max_step_ns: int) -> None:
    if not 1 <= max_step_ns <= 200:
        raise ValueError("max step must be 1–200 ns")
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    simulator = shutil.which("ngspice")
    if simulator is None:
        raise FileNotFoundError("ngspice is required")
    model = ROOT / "sources/model/LMR51430XDDCR_datasheet_approx.lib"
    shutil.copyfile(model, output / "model.lib")
    receipt = {
        "kind": "exploratory-model-runs/v1",
        "qualified": False,
        "simulator": simulator,
        "version": subprocess.run(
            [simulator, "--version"], capture_output=True, text=True, check=True
        ).stdout,
        "model_sha256": sha(output / "model.lib"),
        "datasheet_sha256": sha(ROOT / "sources/ti-lmr51430.pdf"),
        "max_step_ns": max_step_ns,
        "runs": [],
    }
    for name in scenarios:
        directory = output / name
        directory.mkdir()
        source = ROOT / "scenarios" / f"{name}.cir"
        deck = source.read_text().replace(
            "../sources/model/LMR51430XDDCR_datasheet_approx.lib", "../model.lib"
        )
        deck = deck.replace(
            ".tran 20n 12m 0 20n uic", f".tran {max_step_ns}n 12m 0 {max_step_ns}n uic"
        )
        deck = deck.replace(".end\n", CONTROL + "\n.end\n")
        (directory / "bench.cir").write_text(deck)
        timed_out = False
        try:
            with (directory / "simulator.log").open("w") as log:
                proc = subprocess.run(
                    [simulator, "-b", "bench.cir"],
                    cwd=directory,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    timeout=300,
                    check=False,
                )
        except subprocess.TimeoutExpired:
            timed_out = True
            proc = None
        raw = directory / "waveform.raw"
        measurements, missing_measurements = measurement_results(directory / "simulator.log")
        item = {
            "scenario": name,
            "returncode": proc.returncode if proc is not None else None,
            "timed_out": timed_out,
            "source_deck_sha256": sha(source),
            "executed_deck_sha256": sha(directory / "bench.cir"),
            "log_sha256": sha(directory / "simulator.log"),
            "raw_sha256": sha(raw) if raw.is_file() else None,
            "measurements": measurements,
            "missing_measurements": missing_measurements,
        }
        failures = []
        if timed_out:
            failures.append("simulator timeout")
        if proc is not None and proc.returncode:
            failures.append(f"simulator exit status {proc.returncode}")
        if not raw.is_file():
            failures.append("waveform.raw was not produced")
        if missing_measurements:
            failures.append("missing or non-finite native measurements")
        if failures:
            item["failures"] = failures
        receipt["runs"].append(item)
        (output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
        print(json.dumps(item), flush=True)
        if failures:
            raise RuntimeError(f"{name} failed; inspect {directory / 'simulator.log'}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--scenarios", nargs="+", choices=SCENARIOS, default=list(SCENARIOS))
    parser.add_argument("--max-step-ns", type=int, default=20)
    args = parser.parse_args()
    run(args.output, args.scenarios, args.max_step_ns)
