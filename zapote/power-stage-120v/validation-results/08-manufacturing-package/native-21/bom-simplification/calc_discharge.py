#!/usr/bin/env python3
"""X-capacitor bleed R1/R2 (120k+120k -> 100k+100k Basic) and bus bleed R3/R4 (220k+220k) options.
X caps: C1+C2 = 2 x 1 uF R463N410000N1M (+/-20 %, 'M'). Criterion used by the repo (out-D22 PARTS.md): 198 V crest
(140 Vrms) below 34 V within 1 s. Board bleed alone (ignores IRM-20 inputs and the 66 k line-ZC string, which only help).
Bus: C5+C6+C38..C41 = 5.8 uF; parallel bus divider 4 x 470k + 15.8k."""
import math, json, os
from pathlib import Path
V0, VT = 140 * math.sqrt(2), 34.0
out = {}
for r in (120e3, 100e3):
    rs = 2 * r
    for capf, tag in ((1.0, "nominal"), (1.2, "+20 % C, +1 % R")):
        tau = rs * (1.01 if capf > 1 else 1) * 2e-6 * capf
        out[f"X bleed {r/1e3:.0f}k x2, {tag}"] = {"tau_s": round(tau, 3), "t_to_34V_s": round(tau * math.log(V0 / VT), 3)}
    out[f"X bleed {r/1e3:.0f}k x2 power"] = {"total_mW_140Vrms": round(140**2 / rs * 1e3, 1), "per_res_mW": round(140**2 / rs / 2 * 1e3, 1),
                                             "per_res_peak_V": round(V0 / 2, 1), "rating": "250 mW / 200 V (1206)"}
div = 4 * 470e3 + 15.8e3
for r in (220e3, 100e3, 470e3):
    rp = 1 / (1 / (2 * r) + 1 / div)
    tau = rp * 5.8e-6
    out[f"bus bleed {r/1e3:.0f}k x2"] = {"tau_s": round(tau, 2), "t_198_to_60V_s": round(tau * math.log(V0 / 60), 2),
                                        "per_res_mW_at_198V": round((V0 / 2) ** 2 / r * 1e3, 1)}
os.makedirs(Path(__file__).parent / "out", exist_ok=True)
(Path(__file__).parent / "out/discharge.json").write_text(json.dumps(out, indent=1) + "\n")
for k, v in out.items(): print(k, v)
