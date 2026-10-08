#!/usr/bin/env python3
"""Native-21 conducted-EMI screen: do the new parts add common-mode paths to PE? (2026-10-06)

The D-22 / round-3 EMI topology (`round3/scripts/emi_topology.cir`) couples each switch
node to PE through the low-side tab pad (CTABA/B = 42 pF) and the coil (CCOILA/B = 25 pF),
and bus_n through CBRN = 10 pF. Native-21 adds, per the ECO:
- HS-A/HS-B rail-monitor ISO7710: barrier capacitance ~0.4 pF (SLLSER9E p.8, typical)
  from each switch-node bias domain to SELV, which R38 bonds to PE  -> new sw -> PE path;
- LS rail-monitor ISO7710: ~0.4 pF from the n_ls domain (~bus_n) to SELV/PE;
- line zero-cross VOL628A across L_FILT/N_FILT to SELV/PE: ~0.5 pF (allocation; datasheet
  isolation capacitance not taken) in parallel with the existing 2.2 nF Y capacitors;
- HS bias transformers: 3 pF typical interwinding sw -> HOT bias primary (N_LS): this is
  inside the bridge (sw -> bus_n), in parallel with Coss and the 1 nF snubbers, not to PE;
- SN6507 + IRM-20-24: behind the certified IRM module's own input filter (class B module).
The CM drive scales with the total sw -> PE capacitance; the change in dB is reported.
"""
import json
import math
from pathlib import Path

EXISTING_SW_PE_PF = 42.0 + 25.0
ADDED = {"sw_a/sw_b -> PE via HS ISO7710": 0.4, "bus_n -> PE via LS ISO7710 (vs CBRN 10 pF)": 0.4}
res = {
    "switch_node_CM_change_dB": round(20 * math.log10((EXISTING_SW_PE_PF + 0.4) / EXISTING_SW_PE_PF), 3),
    "bus_n_CM_change_dB": round(20 * math.log10((10.0 + 0.4) / 10.0), 3),
    "line_ZC_vs_Y_caps_ratio": 0.5 / 2200.0,
    "transformer_sw_to_bus_n_pF": 3.0,
    "verdict": "No new material CM path; D-22's 16-case margins (>= 8.28 dB after reserve) stand for native-21. Re-run D-22 only if layout adds sw-node copper/metal area near PE (sink, chassis) beyond the 42 pF tab allocation.",
}
(Path(__file__).parent / "cm_screen.json").write_text(json.dumps(res, indent=1) + "\n")
print(json.dumps(res, indent=1))
