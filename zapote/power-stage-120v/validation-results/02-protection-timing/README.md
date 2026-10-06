# 02 Protection timing — detector desk checks (partial result)

- Board: native-11 (`2fec2924…` electrical / `05141028…` presentation); source `frozen/` at 135 parts
- Date: 2026-09-27. Operator: Claude Opus 5.5
- Evidence class: **bounded calculation**. Datasheet values are cited in
  `scripts/detector_chain.py`, and the files are hashed in
  `sources/datasheets.json`. The trip bands come from the Rust corner model.
  This is not SPICE; the full ngspice work in [task 02](../../validation-plan/02-protection-timing.md)
  is still to do.
- **Verdict: two design findings, both fixed in native-12/13** (owner approved
  2026-09-27; part-number swaps only). The other detector items are bounded
  and acceptable, subject to bench confirmation. In `detector_chain.json`,
  "as_built" is the previous native-11 values and "improved" is native-13.

## Summary

| Item | Result |
| --- | --- |
| CT accuracy vs frequency | Gain error ≤ 0.15 % to 60 kHz. **Phase lag 1.5° at 33 kHz, 3.1° at 60 kHz**, from C42 across the burden; this is fixed and can be corrected in firmware. Flux demand at 88 A is 25.5 V·µs per half-cycle against the 638 V·µs limit (25× margin) |
| **Clamp leakage when hot** | **FINDING.** BAT54H reverse leakage (Nexperia Fig. 2, typical) is about 30 µA at 85 °C and about 300 µA at 125 °C. Net leakage flows through R42 and the 500 Ω bias source. With 2× typical as the bound, the trip band widens to **45–65 A at ~85 °C** and becomes meaningless at ~125 °C (−9 to 120 A). Reducing R42 does not fix it (27–83 A). **Fix: swap D4/D5 to BAS116H** (Nexperia low-leakage, same SOD123F package and pinning, ≤ 80 nA at 150 °C). The band then stays at the 25 °C 50.9–59.5 A |
| Comparator hysteresis/offset | TLV3201 offset ≤ 4 mV over temperature, which is ≤ 0.27 A equivalent at 15 mV/A; already in the trip model. Hysteresis is 1.2 mV **typical only**, no min/max |
| Zero-cross at idle | With no tank current, U12's input difference is at most about ±4 mV of static offset. CT_ZC therefore rests at an **undefined but static level**, and may chatter on noise because the hysteresis isn't guaranteed. The controller must ignore CT_ZC when not switching. Phase error from the offset: 7.7° at 2 A peak, 3.1° at 5 A, 1.5° at 10 A, 0.4° at 37 A |
| **Trip-to-gate-off timing** | **FINDING.** The as-built chain is **4.1 µs (tank CT) and 4.5 µs (shunt OCP)**, worst-case sum. 3.5 µs of that is the PERMIT → DIS link: R14/R6 (1 kΩ) drive the AO3400A gate, and R16/R8 (10 kΩ) pull DIS up against the FET's output capacitance. **Fix: R14/R6 → 100 Ω and R16/R8 → 1 kΩ** (same 0603 footprints). That gives **1.0 µs / 1.3 µs** |
| Tank over-current peak at gate-off | Worst trip (59.5 A) plus the current ramp during the chain delay, at 198 V/70 µH (2.8 A/µs) and 280 V (4.0 A/µs): **71–76 A as built** and **62–63 A with the fix**. Both are below T1's 88 A |
| Hard shoot-through | Blocked at the driver. With RDT = 39 kΩ, UCC21550 "If both inputs are high simultaneously, both outputs will immediately be set low" (SLUSE89C, programmable dead time). The 4 µs chain could not stop a shoot-through that reaches tens of A per ns. Dv/dt-induced false turn-on is task 01 |

## Assumptions (all in the script)

- **AO3400A capacitances:** Ciss 900 pF and Coss 150 pF at low drain voltage.
  These are assumed bounds; the datasheet gives 630 and 75 pF at 15 V.
  - DIS pin plus trace: 10 pF (assumed).
  - The DIS threshold is the UCC21550 maximum of 2.3 V; the rail is 3.135 V
    (−5 %).
- **CD74HC30 at 3.3 V:** bounded by its 2 V, 125 °C maximum of 110 ns.
- **Harness:** 5 ns (assumed).
- **MOSFET gate discharge:** 150 ns (assumed; task 01 will replace it).
- **Clamp leakage:** twice the typical graph value is used as the "max"
  estimate. Nexperia gives only a 25 °C maximum for BAT54H.
- **Comparator overdrive:** delay is taken at 20 mV overdrive. The delay
  below that isn't specified.
- **Summing:** delays are summed as worst-case links, with no statistical
  combination.

## Fixes (applied in native-12/13, 2026-09-27)

Both are part-number swaps on existing footprints, so there's no placement or
copper change:

1. D4, D5: BAT54H,115 → **BAS116H** (Nexperia, SOD123F, pin 1 K / 2 A, as now).
2. R14/R6: 1 kΩ → **100 Ω**. R16/R8: 10 kΩ → **1 kΩ**. The DIS pull-up then
   draws 3.3 mA while PERMIT is high. The interlock's PERMIT output drives a
   100 Ω + gate-charge load. The permit pulldowns (R15/R7, 100 kΩ) and the
   fail-safe states are unchanged.

## Bench items that remain

- CT leakage inductance and interwinding capacitance above 100 kHz.
- Actual clamp leakage vs temperature, after the swap.
- Comparator hysteresis and chatter at idle.
- The measured shutdown chain with injected primary current (the D4 condition 2 bench item).

## Reproduce

```sh
python3 validation-results/02-protection-timing/scripts/detector_chain.py
cd tools/ct_detector && sed 's/{ 4e-6 } else { -4e-6 }/{ 60e-6 } else { -60e-6 }/' ct_detector_model.rs > /tmp/m.rs \
  && rustc -O /tmp/m.rs -o /tmp/m && /tmp/m      # repeat with 600e-6 and/or sense_series_ohm: 100.0
```

## Round-17 closure on native-19 (D-31, 2026-10-05)

The device-survival part of the BLOCKED verdict below is **closed for fault turn-off**. Gate-off timing, FC1 on DC, precharge and contactors remain open. Evidence is in [`01-switching-parasitics/round17/delegation/out-D31/`](../01-switching-parasitics/round17/delegation/out-D31/README.md):

- **Gate-off chain:** at most 787.5 ns (CT path) and 814.9 ns (shunt path) from comparator output to completed DIS response. The figure is ALLOCATION-dominated: the DIS RC alone is 360.8 ns. Bench edge captures must confirm the allocations.
- **Fault turn-off at 60–330 A:** die VDS ≤ 350 V on the native-19 best matrix, against the 520 V screen and the 650 V rating.
- **Shoot-through:** not survivable through this chain. It stays prevention-only: driver interlock, dead time, FC1 and the catch circuit.
- **Decision B (R34):** no resistor-only value meets both criteria. R34 = 10.6 kΩ was chosen (DECISIONS.md 2026-10-05), giving a 49.73–97.98 A band.

## SPICE continuation on native-13 (partial, 2026-09-27)

**Verdict: BLOCKED for the complete protection and device-survival decision.**
The preceding bounded report is retained as historical calculation evidence;
its native-11 board identity and `as_built` figures refer to the earlier
version. This continuation uses `native-13/section.kicad_pcb`, SHA-256
`8056fc952675bc6987bcc9d32c12a88eebc4cec9bc3696f8cbd4876700a39129`,
at kit commit `36ba41f249eea0b9c78c9d7bdd6e38ea04bb37f9`. ngspice 45.2
passed all 16 kit smoke checks (`outputs/smoke_test.txt`). The verified
ignored vendor library is SHA-256
`02ac6634f47c25be04e8de3c6eec4ec8cf403b659001b7f176c8f98bb6e9ce3b`;
the archive is `5a6341084202debb0f8f230b8809c090434ea9526c8e0defe3d2e07a832ff48d`.
Neither vendor file is committed. The CT and shunt decks do not instantiate
the Infineon MOSFET library.

Evidence class: **simulation/model-based** for the analog front ends;
**bounded calculation with stated assumptions** for the retained digital
links. The scripts verify ngspice exit status, full-log failure signatures,
required measures and raw waveform end time. The raw crossing checks also
interpolate waveform thresholds independently of `.meas`.

| Path | Completed cases | Result | Comparison with old sum |
| --- | ---: | --- | --- |
| CT, 33 kHz and 37 A starting amplitude | 12 of the requested 108 | First `|Iprimary| = 55.17 A` to OR output: **103–297 ns** over 1/3 MA/s, ±4 mV and 45/55 ns model delays. Both positive and negative half-cycles won cases. Zero-cross lag: **170–206 ns**, or **2.02–2.44°**. | At 3 MA/s, 0 mV, 55 ns the delay is 247 ns, versus 236 ns for the old CT analog + OR sum. The 192 ns zero-cross lag at this point is consistent with the runbook's ≈194 ns reference; C42's ≈1.5° phase lag plus comparator delay explains the larger total angle. |
| Shunt OCP | All five requested slopes, with ±4 mV datasheet and ±5 mV runbook stress: 20 cases | The exact resistor network gives an ideal trip of **60.976 A − 2000·VOS**. At 3 MA/s, the ±4 mV corners detect at **54.64/70.64 A**, about **555 ns** after their *own* thresholds. At 100 MA/s the −4 mV corner detects at **119.35 A**. | The old 500 ns RC + 55 ns comparator link tracks the 3 MA/s model after referring to the offset-adjusted threshold. The raw difference from the fixed 61 A reference can be negative, because offset shifts the trip itself. |

`outputs/frontend_sweep.json` has every completed parameter, original `.meas`
result and log digest; the full ngspice transcripts are retained as `.txt`
files in `outputs/logs/`. `outputs/raw_crossing_checks.json` records four
independent waveform checks and compares `.meas`
with the raw waveforms at both CT polarities and the shunt; differences are
under one 5 ns CT step or one 2 ns OCP step. The original CT deck's
`RISE=3` zero-cross ordinals misalign by one full cycle at +4 mV: the
comparator acquires an extra first-cycle rising edge. The sweep pairs each
output edge with the nearest primary rising zero; the +4 mV raw waveform
confirms the pairing. The task-owned copied CT deck adds only the negative
primary threshold measure; `t_or` is referenced to the *earlier* positive or
negative `55.17 A` crossing.

The new `outputs/delay_budget.csv` and `outputs/chain_review.json` preserve
all native-13 downstream links from `detector_chain.json`. Their sums to
the **driver output** are 572.2 ns (CT) and 602.7 ns (shunt), after the
modeled front end. The model therefore suggests 675–869 ns (completed CT
subset) and 854–1158 ns (datasheet ±4 mV shunt corners) from the chosen
threshold crossing to the driver output. **These are not maximum
trip-to-MOSFET-off times.** The old 150 ns MOSFET gate-discharge term is
still an assumption, and task 01 could not provide valid board-inductance
corners or a turn-off waveform. No VDS or T1/device survival verdict follows.

The complete CT sweep is blocked by reproducible ngspice stalls. The first
10 MA/s case (33 kHz, 37 A, −4 mV, 45 ns), one 10 A light-load case
(33 kHz, 1 MA/s, 0 mV, 55 ns), and the first 39 kHz case (37 A, 1 MA/s,
−4 mV, 45 ns) did not complete within the bounded run. ngspice repeated
`Reference value` lines while transient time barely advanced. Default and
neighboring cases complete. `outputs/blocked_cases.json` holds those exact
parameters and last log lines; no solver options were loosened. The 60 kHz,
light-load and 10 MA/s CT corners therefore have no result here.

There are further limits to the model. Its CT clamp is a generic diode,
not a characterized BAS116H temperature model. It fixes the shunt and
reference at nominal values and gives the comparator an ideal tanh decision
plus a constant 45/55 ns delay. [TI TLV3201 SBOS561C Rev. C, p. 5,
§§6.5–6.6](https://www.ti.com/lit/ds/symlink/tlv3201.pdf) specifies **4 mV**
maximum offset across temperature at 5 V and a **55 ns** maximum propagation
delay at **20 mV input overdrive**. The runbook's ±5 mV is conservative
stress, not that datasheet maximum. At a 3 MA/s shunt ramp the differential
input changes only about 0.083 mV in 55 ns, so the 20 mV delay condition is
unmet near threshold. No worst-case small-overdrive delay was established.
The PDF SHA-256 recorded in `sources/datasheets.json` is
`1777bba814c74772bb54c6f1f56702985039043ce2fb2affaf996a83eaf1076e`.
The CT's 3.2 mH, 1.5 Ω, 1:100, 638 V·µs and 88 A entries come from
[Coilcraft's CST3015-100ED Specifications table](https://www.coilcraft.com/en-us/products/transformers/power-transformers/current-sensing/cst3015/cst3015-100e/)
(HTML page, no printed revision/page), captured and hashed in
`docs/evidence/2026-08-13-tank-fault-sizing-inputs.md`. The previous F1
driver-interlock citation is [TI UCC21550 SLUSE89C Rev. C, p. 23,
Table 7-3](https://www.ti.com/lit/ds/symlink/ucc21550.pdf), hash
`5f80a86ae72418d7d538067f3f0438907b9692b74554a8d7aa6866c2f6ffc7ba`
in the same source manifest.

F2 current at **actual gate-off**, F3 returned-energy voltage, F4/F5
power-loss behavior, threshold tolerance/Monte Carlo, MOSFET pulse-current
and VDS limits, and the injected-current bench test remain open. The
existing bounded CT trip band and digital delay assumptions are preserved,
not upgraded to physical evidence by this partial analog run.

Reproduce the fast completed subset from this directory:

```sh
python3 scripts/sweep_frontends.py
python3 scripts/review_delay_budget.py
python3 scripts/probe_blocked_cases.py
```
