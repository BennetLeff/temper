#!/usr/bin/env python3
"""Added RC branch effect on the passive DC-port impedance (not a loop-stability proof)."""

import json
from pathlib import Path
import subprocess
import tempfile
import numpy as np
from filter_stage import MODEL, deck_text
from qualify_filter import scenarios

HERE = Path(__file__).resolve().parent


def main():
    rows = []
    folder = HERE / "damping"
    folder.mkdir(exist_ok=True)
    for case in ("proposed_nominal", "old_low_leakage", "all_high_parasitics"):
        for damped in (False, True):
            _, params = scenarios()[case]
            params = {**params}
            if not damped:
                params["RDAMP"] = 1e12
            tag = case + ("-damped" if damped else "-open-damper")
            deck = deck_text(params, "DM").replace(
                ".ac lin 30000 150k 30meg", ".ac dec 400 100 150k"
            )
            (folder / (tag + ".cir")).write_text(deck)
            with tempfile.TemporaryDirectory(prefix="d22-damping-") as directory:
                temp = Path(directory)
                (temp / "case.cir").write_text(deck)
                (temp / ".spiceinit").write_text("set filetype=ascii\n")
                proc = subprocess.run(
                    ["/opt/homebrew/bin/ngspice", "-b", "-r", "waves.raw", "case.cir"],
                    cwd=temp,
                    capture_output=True,
                    text=True,
                    timeout=60,
                    check=True,
                )
                (folder / (tag + ".log")).write_text(proc.stdout + proc.stderr)
                waves = MODEL["read_raw"](temp / "waves.raw")
            f = np.asarray(waves["frequency"]).real
            z = np.asarray(waves["v(bus_p)"]) - np.asarray(waves["v(bus_n)"])
            np.savez_compressed(folder / (tag + ".npz"), frequency_Hz=f, dc_port_impedance_Ohm=z)
            i = np.argmax(abs(z))
            rows.append(
                {
                    "scenario": case,
                    "damped": damped,
                    "peak_DC_port_impedance_Ohm": float(abs(z[i])),
                    "Hz": float(f[i]),
                }
            )
    (HERE / "damping-results.json").write_text(json.dumps(rows, indent=2) + "\n")
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
