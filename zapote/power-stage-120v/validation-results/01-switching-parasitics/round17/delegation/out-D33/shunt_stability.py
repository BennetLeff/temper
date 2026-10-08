"""Candidate split-rail model checks; no claim of component qualification.

The linear calculation uses SLVM672's active-region transconductance and
two control poles. It is an external circuit calculation, not a temperature
model. The transient runs the complete manufacturer behavioural model.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

import rail_campaign as campaign

HERE = Path(__file__).resolve().parent


def loop_margin(cap: float) -> dict:
    frequency = np.geomspace(1, 1e7, 100000)
    s = 2j*np.pi*frequency
    y = 1/4990 + 1/16120
    y = y + 1/(.02+s*.5e-9+1/(s*cap)) + 1/(.05+s*.1e-9+1/(s*100e-9))
    loop = (4*10000/16120)/((1+s*159e-6)*(1+s*80e-9)*y)
    i = int(np.nonzero(abs(loop) <= 1)[0][0])
    return {"effective_C_F": cap, "unity_gain_Hz": float(frequency[i]),
            "phase_margin_deg": 180+float(np.angle(loop[i], deg=True))}


def main() -> None:
    rows = []
    for cap_u in (2.2, 10, 22):
        for frequency in (33000, 80000):
            # Each pulse integrates to 4 A * (99.25 ns + 5 ns) = 417 nC.
            period = 1/frequency
            name = f"shunt-{cap_u}u-{frequency}Hz"
            text = f"""* D33 candidate shunt, paired 417nC pull-up/discharge pulses
.include {campaign.model()}
.include ../common/options.inc
.include params.inc
Vspan raw n 17
Rsp raw p 1
Cspan p n 47u
Rbleed p 0 4.99k
Rtop 0 fb 6.12k
Rbot fb n 10k
Xsh n 0 fb TLVH431
Lneg n ne 0.5n
Rneg ne nc 20m
Cneg nc 0 {cap_u}u
Lhf n he 0.1n
Rhf he hc 50m
Chf hc 0 100n
Ipull p 0 PULSE(0 4 1m 5n 5n 99.25n {period})
Idump 0 n PULSE(0 4 {1e-3+period/2} 5n 5n 99.25n {period})
.tran 5n 2m 0 5n
.meas tran negmax MAX v(n) from=1m to=2m
.meas tran negmin MIN v(n) from=1m to=2m
.meas tran negstart FIND v(n) AT=0.9m
.end
"""
            folder = HERE / "stability"
            folder.mkdir(exist_ok=True)
            deck = folder / f"{name}.cir"
            deck.write_text(text)
            run = campaign.f6.run_d2.run(deck, {}, keep=HERE/"runs"/name)
            (HERE/"runs"/name/"IFX_CFD7_650V.lib").unlink(missing_ok=True)
            rows.append({"case": name, "aborted": run["aborted"], "measurements": run["meas"],
                         "loop": loop_margin(cap_u*1e-6)})
            print(name, rows[-1], flush=True)
    (HERE/"shunt-stability.json").write_text(json.dumps(rows, indent=2)+"\n")


if __name__ == "__main__":
    main()
