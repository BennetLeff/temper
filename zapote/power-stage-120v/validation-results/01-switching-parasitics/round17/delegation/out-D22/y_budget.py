#!/usr/bin/env python3
"""Screen reduced Y capacitance against the same complete source captures."""

import json
import numpy as np
from qualify_filter import HERE, MODEL, exact_transfer, load_sources

rows = []
sources = load_sources()
conditions = json.loads((HERE / "candidate-v2-filter-scenarios.json").read_text())
for name, (added, params) in conditions.items():
    if not added:
        continue
    params = {**params, "CYADD": params["CYADD"] * 0.47}
    for freq in (35000, 60000):
        tr = exact_transfer("reduced-Y-" + name, params, freq, True)
        for case, signals in sources.items():
            if int(round(np.diff(signals["frequency_Hz"])[0])) != freq:
                continue
            f = signals["frequency_Hz"][1:]
            v = MODEL["combine"](tr, {k: val[1:] for k, val in signals.items()}, f)
            _, av, mask = MODEL["limits"](f)
            level = 20 * np.log10(np.maximum(abs(v["l_pe"]), abs(v["n_pe"])) / np.sqrt(2) / 1e-6)
            ix = np.flatnonzero(mask)[np.argmin((av - level)[mask])]
            rows.append(
                {
                    "case": case,
                    "scenario": name,
                    "AV_dB": float((av - level)[ix]),
                    "Hz": float(f[ix]),
                }
            )
(HERE / "reduced-Y-results.json").write_text(json.dumps(rows, indent=2) + "\n")
print(min(rows, key=lambda r: r["AV_dB"]))
