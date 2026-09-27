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
