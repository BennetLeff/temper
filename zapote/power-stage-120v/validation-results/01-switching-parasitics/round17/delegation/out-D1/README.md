# D1 — fitted UCC21550 dead time

**The board's guaranteed minimum dead time is not established by the published datasheet: the fitted 39 kΩ network gives 348.4 ns nominal and an estimated 307.185–391.220 ns range, so this review cannot prove that 250 ns is unreachable.**

Do not remove the existing D2 stress corners on this evidence. The estimate is useful for an additional sensitivity sweep; it is not a production tolerance specification or a shoot-through clearance.

## Circuit checked

Source revision: `67aec36f8c876a7026c07ce3752105ab34d3ce46`. Paths below are relative to the repository root unless stated otherwise. [dead_time.py](dead_time.py) reads the actual frozen BOM/netlist and native board, checks the connections, and records input hashes in [dead_time.txt](dead_time.txt). This is a standard-library evidence calculation, not a new workspace engineering rule.

| Leg | Driver / DT pin | Programming network | Other components on DT net |
| --- | --- | --- | --- |
| A | U1 UCC21550BDWKR, pin 6 | `leg_a.driver-dt`: R9 pin 1; R9 pin 2 to `selv_gnd`, also U1 pin 4 | None |
| B | U2 UCC21550BDWKR, pin 6 | `leg_b.driver-dt`: R17 pin 1; R17 pin 2 to `selv_gnd`, also U2 pin 4 | None |

Both resistors are **Yageo RC0603FR-0739KL**, 39 kΩ, ±1%, ±100 ppm/°C. The part identity comes from `zapote/power-stage-120v/frozen/default.csv` (R9/R17 row) and `frozen/default.net` (components R9/R17 and DT nets). The electrical value, tolerance and TCR come from Yageo's [part-specific specsheet](https://yageogroup.com/component-documentation/download/specsheet/RC0603FR-0739KL), generated May 2, 2026, page 1, Specifications. That sheet has no revision code. Its rated resistor temperature range covers the temperature scenarios below.

There is no fitted DT capacitor, VCCI pull-up or connection to DIS. DIS is pin 5, a separate `leg_a-dis` / `leg_b-dis` net with Q1.3/R8.1 / Q4.3/R16.1. The board's pad net assignments match these netlist memberships. This checks assigned connectivity, not fabricated copper continuity or assembly population. No contradiction was found between this DT network, its frozen netlist and TI's recommended resistor connection.

The controller supplies four independent PWM nets through J4: pins 5/6 connect directly to U1 INA/INB (pins 1/2), and pins 7/8 to U2 INA/INB. `docs/hardware/power-section-120v/POWER-SECTION.md` §§1,3,4 describes full-bridge phase-shift control. `zapote/power-stage-120v/validation-plan/06-controller-interface.md`, check 7, explicitly leaves PWM dead-time ownership as a check to perform. Neither cited document establishes an implemented controller dead-time setting, its tolerance, or edge skew for this board. This report does not import a timer value from another controller/board.

## TI specification and what it does not guarantee

Source: **TI UCC21550, SLUSE89C, May 2023 / revised August 2024**, [official datasheet](https://www.ti.com/lit/ds/symlink/ucc21550.pdf), also committed as `datasheets/ucc21550.pdf` (hash in the output).

- Page 25, §7.4.2.2, equation (1): `tDT ≈ 8.6 × RDT + 13`, with ns and kΩ, valid for programming resistors from 1.7 to 100 kΩ. This is an approximate programming equation, not separate guaranteed slope/intercept tolerances.
- Page 10, §5.8: min/typ/max timing is specified at the resistance test points below, over junction temperature −40 to +150 °C. Conditions include VCCI = 3.3 or 5 V, the B variant's VDD = 12 V, and no output load. These are full-temperature limits; there are no distinct cold/hot guaranteed DTS rows.

| RDT (kΩ) | Min (ns) | Typ (ns) | Max (ns) |
| --- | --- | --- | --- |
| 10 | 86 | 99 | 112 |
| 20 | 167 | 185 | 203 |
| 50 | 399 | 443 | 487 |

There is **no 39 kΩ min/max row and no general ±10% accuracy guarantee**. Linear interpolation between guaranteed points is still an assumption, not a guarantee between those points. Page 17, Figures 5-28/5-29 are typical temperature curves, not production limits. They cannot fill this gap.

Page 25, §7.4.2.2 and page 26, Figure 7-4 describe the interaction with PWM: a falling input edge starts the opposite channel's dead-time timer. A requested turn-on waits for that timer if necessary; a longer input non-overlap interval dominates. It does not add a complete programmed dead time to an already longer input gap. Both-high input overlap forces both outputs low. The resistor therefore enforces non-overlap during ordinary complementary switching as well as handling input overlap.

Page 33, §8.2.2.8 and page 19, Figure 6-4 define DTS between **90% of the falling driver output and 10% of the rising opposite output**. This is not the interval between MOSFET gate threshold crossings. External gate impedance, transistor capacitances and switching conditions still determine the latter.

## Calculation, explicitly estimated

For each resistor-body temperature T, assume the resistance tolerance is referenced to 25 °C and stack initial tolerance and TCR multiplicatively:

```
Rmin = 39 × (1 − 0.01) × (1 − 100e−6 × |T − 25|)
Rmax = 39 × (1 + 0.01) × (1 + 100e−6 × |T − 25|)
DTmin_est = 167 + (Rmin − 20) × (399 − 167) / (50 − 20)
DTmax_est = 203 + (Rmax − 20) × (487 − 203) / (50 − 20)
DTnom_fit = 8.6 × 39 + 13
```

| Resistor body T (°C) | Rmin (kΩ) | Rmax (kΩ) | Min estimate (ns) | Nominal fit (ns) | Max estimate (ns) |
| --- | --- | --- | --- | --- | --- |
| −40 | 38.359035 | 39.646035 | 308.977 | 348.400 | 388.982 |
| 25 | 38.610000 | 39.390000 | 310.917 | 348.400 | 386.559 |
| 150 | 38.127375 | 39.882375 | 307.185 | 348.400 | 391.220 |

These scenarios use driver limits spanning the full specified junction-temperature range in every row. They do not assume the driver and resistor must have equal temperatures; the left column is the resistor-body temperature. The nominal column is the equation evaluated at nominal resistance, not a prediction of typical temperature drift. Aging, assembly-induced resistance changes, DT-pin noise, real supply/load effects and a characterized accuracy envelope at the fitted resistance remain unqualified. The board's gate supply differs from the DTS table's B-variant test supply, another reason not to label these board-level bounds.

## Channel delay and D2 decision

TI page 10, §5.9 specifies same-edge channel matching `tDM` of at most 6.5 ns from −40 to −10 °C and 5 ns from −10 to +150 °C, plus same-channel pulse-width distortion `tPWD` at most 5 ns. Individual rising/falling propagation delays are 26/33/45 ns min/typ/max. These switching specifications use DT disabled and the stated test conditions.

For **input-dominated** ordinary PWM, opposite-edge skew is bounded conditionally by the triangle inequality: `|tPDLH(incoming) − tPDHL(outgoing)| ≤ tDM + tPWD`. Thus the input gap can shift by up to 11.5 ns in the colder band or 10 ns in the warmer band under those conditions. Using only tDM misses the rising-versus-falling mismatch. Do not subtract this again from TI's DTS rows: those rows already measure an output-to-output interval.

The estimated programmed-DT table assumes the controller's input gap is shorter than the driver's programmed interval, with normal enabled supplies and alternating complementary commands. If firmware imposes a longer gap, its actual value and skew are needed for the maximum effective dead time; the resistor alone cannot establish that maximum.

In `round17/d2/leg_matrix.cir`, DT spaces the starts of two opposite control ramps. Its behavioral driver has no programmed interlock or specified propagation-delay tolerance. Before transferring output timing to that control parameter, correlate driver-output threshold timing; a control-ramp gap is not automatically a measured driver-output gap under gate load.

**Recommendation:** retain 250/348/450 ns as explicitly provisional stress cases. Add the calculated estimated endpoints and nominal point for sensitivity, but do not replace 250/450 with them or reclassify the failed 250 ns cases as impossible. Obtain TI confirmation of min/max timing at the fitted resistance, supply and temperature range, plus input PWM timing and driver-output correlation, before claiming a guaranteed replacement interval. D1 establishes nominal timing and an estimated range; it leaves the exclusion of 250 ns unresolved.

## Reproduce

From repository root:

```sh
python3 zapote/power-stage-120v/validation-results/01-switching-parasitics/round17/delegation/out-D1/dead_time.py
```

Compare stdout with [dead_time.txt](dead_time.txt), allowing the reported Python version to vary. The script fails on DT part or relevant pad-net mismatches. The recorded run used the system Python shown in its output and no native/workspace builds. Review by GPT-6 Astra / OpenAI. No design files or D2 simulations were changed.

Publishing validation: `PYTHONPATH=packages/temper-placer/src .venv/bin/python scripts/import_linter_gate.py` passed ([log](import-check.txt)); `python3 scripts/regen_derived.py --check` passed ([log](regen-check.txt)). The private tooling environment required `import-linter` and `pyyaml`; the initial missing-tool and missing-YAML attempts failed before a complete gate result. No dependency synchronization or workspace/native builds were run. The report-only regeneration check found all derived artifacts consistent, so none needed regeneration. Firmware was unchanged and its build/test was not run under the brief's no-build instruction.
