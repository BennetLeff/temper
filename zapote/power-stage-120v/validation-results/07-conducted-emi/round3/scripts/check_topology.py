#!/usr/bin/env python3
"""Reproduce opposed-leg and single-leg AC fixtures for the EMI deck."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
DECK = ROOT / "scripts/emi_topology.cir"
OUTPUT = ROOT / "outputs/topology_fixture.json"
KIT_COMMON = ROOT.parents[2] / "validation-plan/sim-kit/common"
sys.path.insert(0, str(KIT_COMMON))
from run_ngspice import read_raw  # noqa: E402


def run_case(params: dict[str, float]) -> dict[str, np.ndarray]:
    deck = DECK.read_text()
    for name, value in params.items():
        pattern = rf"(?m)^([.]param .*\b{name}=)([^\s]+)"
        deck, count = re.subn(pattern, lambda match: match.group(1) + str(value), deck)
        if count != 1:
            raise ValueError(f"expected one parameter {name}, found {count}")
    with tempfile.TemporaryDirectory(prefix="emi-a7-") as directory:
        place = Path(directory)
        (place / DECK.name).write_text(deck)
        (place / ".spiceinit").write_text("set filetype=ascii\n")
        process = subprocess.run(
            ["/opt/homebrew/bin/ngspice", "-b", "-r", "waves.raw", DECK.name],
            cwd=place, text=True, capture_output=True, check=False,
        )
        if process.returncode or "No. of Data Rows : 30000" not in process.stdout:
            raise RuntimeError(process.stdout + process.stderr)
        waves = read_raw(place / "waves.raw")
    if len(waves["frequency"]) != 30000:
        raise RuntimeError("AC raw waveform point count mismatch")
    return {key: np.asarray(values) for key, values in waves.items()}


def at(waves: dict[str, np.ndarray], frequency_hz: float, key: str) -> complex:
    frequencies = np.real(waves["frequency"])
    i = int(np.argmin(abs(frequencies - frequency_hz)))
    return complex(waves[key][i])


def main() -> None:
    single = run_case({"EXC_A": 1, "EXC_B": 0})
    other = run_case({"EXC_A": 0, "EXC_B": 1})
    opposed = run_case({"EXC_A": 1, "EXC_B": -1})
    mismatch = run_case({"EXC_A": 1, "EXC_B": -1, "CTABA": 50.4e-12, "CTABB": 33.6e-12})
    rows = []
    for frequency in (150e3, 1e6, 10e6, 30e6):
        row: dict[str, float] = {"frequency_hz": frequency}
        for name, waves in (("single", single), ("opposed", opposed), ("mismatch", mismatch)):
            line = at(waves, frequency, "v(lisn_l)")
            neutral = at(waves, frequency, "v(lisn_n)")
            row[f"{name}_terminal_cm_v"] = abs((line + neutral) / 2)
            row[f"{name}_terminal_dm_v"] = abs((line - neutral) / 2)
        # The lone Q3 tab current has a closed-form answer at the actual
        # solved node voltage: I = j*omega*C*(Vsw_a - Vpe). The 0-V probe in
        # the deck gives an independent SPICE current to compare with it.
        sampled_frequency = at(single, frequency, "frequency").real
        expected = 1j * 2 * np.pi * sampled_frequency * 42e-12 * (
            at(single, frequency, "v(sw_a)") - at(single, frequency, "v(pe)")
        )
        observed = at(single, frequency, "i(vtabsensea)")
        row["q3_tab_current_analytic_a"] = abs(expected)
        row["q3_tab_current_spice_a"] = abs(observed)
        row["q3_tab_current_rel_error"] = abs(observed - expected) / abs(expected)
        if row["q3_tab_current_rel_error"] > 1e-8:
            raise AssertionError(f"single-leg tab-current law failed: {row}")
        rows.append(row)
    # Linear superposition at every frequency checks the actual netlist, not
    # just a cancellation impression at a single sampled frequency.
    residual = max(
        float(np.max(abs(opposed[key] - (single[key] - other[key]))))
        for key in ("v(lisn_l)", "v(lisn_n)")
    )
    scale = max(
        float(np.max(abs(single["v(lisn_l)"]))),
        float(np.max(abs(single["v(lisn_n)"]))),
    )
    if residual > max(1e-9, scale * 1e-7):
        raise AssertionError(f"superposition failed: {residual} vs {scale}")
    # Symmetric drives/pads/coil capacitances must cancel substantially, even
    # with asymmetric rectifier crest conduction. A ±20% pad split must restore
    # a measurable terminal signal.
    for row in rows:
        if row["opposed_terminal_cm_v"] > row["single_terminal_cm_v"] * 0.01 + 1e-12:
            raise AssertionError(f"opposed CM did not cancel: {row}")
        if row["mismatch_terminal_cm_v"] <= row["opposed_terminal_cm_v"] * 10:
            raise AssertionError(f"pad asymmetry did not restore CM: {row}")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps({"checks": "PASS", "superposition_max_abs_v": residual,
                                  "rows": rows}, indent=2) + "\n")
    print(OUTPUT.read_text())


if __name__ == "__main__":
    main()
