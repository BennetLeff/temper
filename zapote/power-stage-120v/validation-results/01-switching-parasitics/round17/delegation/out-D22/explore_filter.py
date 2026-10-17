#!/usr/bin/env python3
"""Bounded topology exploration, retaining unsuccessful sensitivities."""

import json
from pathlib import Path
import numpy as np
from filter_stage import MODEL, transfer

HERE = Path(__file__).resolve().parent


def main() -> None:
    rows = []
    dominant = MODEL["SCENARIOS"]["combined_sensitivity"]
    scenarios = {"original_combined": (False, dominant)}
    for cap in (1e-6, 4.7e-6):
        for ycap in (2.2e-9, 4.7e-9, 10e-9):
            name = f"pi_x{cap:g}_y{ycap:g}"
            scenarios[name] = (True, {**dominant, "CXIN": cap, "CYADD": ycap})
    for ycap in (2.2e-9, 4.7e-9, 10e-9):
        scenarios[f"cm_pi_y{ycap:g}"] = (
            True,
            {**dominant, "CXIN": 1e-6, "CYADD": ycap, "LCMADD": 1.12e-3},
        )
    for leakage in (18e-6, 9e-6):
        scenarios[f"coupled_only_ldm{leakage:g}"] = (
            True,
            {
                **dominant,
                "CXIN": 1e-6,
                "CYADD": 10e-9,
                "LCMADD": 1.12e-3,
                "LDMADD": leakage,
                "LNEW": 0,
            },
        )
    for name, (added, params) in scenarios.items():
        tr = transfer(name, params, added)
        for tag in ["v170-r2-e1.06-f35000-s0.5-c24", "v170-r2-e1.06-f60000-s0.5-c48"]:
            with np.load(HERE / (tag + "-n524288-fft.npz")) as data:
                f = data["frequency_Hz"]
                signals = {key: data[key] for key in ("v(swa)", "v(swb)", "bus_current_A")}
            output = MODEL["combine"](tr, signals, f)
            _, av, regulated = MODEL["limits"](f)
            for mode, signal in [
                ("terminal", np.maximum(abs(output["l_pe"]), abs(output["n_pe"]))),
                ("CM", (output["l_pe"] + output["n_pe"]) / 2),
                ("DM", (output["l_pe"] - output["n_pe"]) / 2),
            ]:
                level = 20 * np.log10(np.maximum(abs(signal), 1e-30) / np.sqrt(2) / 1e-6)
                index = np.flatnonzero(regulated)[np.argmin((av - level)[regulated])]
                row = {
                    "scenario": name,
                    "case": tag,
                    "mode": mode,
                    "AV_dB": float((av - level)[index]),
                    "Hz": float(f[index]),
                }
                rows.append(row)
                if mode == "terminal":
                    print(row, flush=True)
    (HERE / "filter-topology-exploration.json").write_text(json.dumps(rows, indent=2) + "\n")


if __name__ == "__main__":
    main()
