# Bank over-voltage in a CT-failed double fault

Status: **INCONCLUSIVE** (worst case 1702 V against 1600 V DC rated; TDK gives no single-event over-voltage figure). Evidence class: bounded calculation plus a closed-form time-domain model, ASSUMED basis (no measured coil, pan or bank).

## Question

DECISIONS.md item 13, open: with the current-transformer (CT) trips failed, can the resonant bank (5 x TDK B32654A1104K000, 0.50 uF) exceed its voltage rating before the remaining protection (shunt OCP, band 66.30-118.74 A after the Kelvin bound) stops the bridge?

## Pass criterion (fixed before the first run; it is coded in `study()`)

Let V_gov be the largest bank peak voltage over all modelled cases of the double fault below (inductance, capacitance, resistance and bus corners; the four cases listed under Method).
- **PASS:** V_gov <= 1600 V (the rated DC voltage V_R, which is the only continuous peak-voltage rating on the sheet).
- **INCONCLUSIVE:** 1600 V < V_gov <= 2560 V (1.6 x V_R, the factory 2 s DC proof level, p.35). Above V_R, and the datasheet gives no single-event over-voltage figure, so the study can neither pass nor fail it.
- **FAIL:** V_gov > 2560 V.

## Double fault (definition)

1. **Fault 1: the CT trips are dead** (CT open, shorted, or its secondary or comparators failed). Justification from the protection architecture:
   - The hardware CT trip (band 64.55-76.09 A, DECISIONS 13) is gone by definition.
   - The firmware peak trip (62 A) and half-cycle RMS trip read tank current from the same T1 CT through `ct_mon` (stage-15 PLAN s4: "tank current from the T1 CT (ct_mon)"). I treat them as blind too. I did not trace the AD8436 RMS chain's source on the schematic. If any of them survives, it only helps (see the context row in the results).
   - The only tank-current trip left is the **shunt OCP** (R5 / Kelvin / comparator, independent of the CT), upper corner **118.74 A**. Its delay is the committed bound T_D = 2.267 us (`stage15-28A/fault_check.py`: 555 ns front end, 573.2 ns chain, 0.988 us Q1/Q4 charge excess, 150 ns gate).
   - The bank cannot be protected by the shunt before the current reaches its trip level; no CT-independent voltage sense exists on the bank.
2. **Fault 2: something drives tank current to the shunt band**, two variants:
   - **F1, frequency-loop runaway toward and through resonance.** The drive frequency is open-loop and can be anywhere in 15-80 kHz, below resonance included. The firmware floor (f >= max(35 kHz, 1.05 f_res), DECISIONS 10) is itself part of the loop that failed.
   - **F2, pan-removal or low-load step with the loop intact.** The load resistance falls and the drive frequency stays at f >= max(35 kHz, 1.05 f_res).

   Why these two: the stage-15 firmware tracks power with a per-pan frequency loop, so the realistic ways to reach 118 A (2x the 59.17 A envelope peak) are the loop driving f onto resonance, or R collapsing at a fixed f. DECISIONS 10 already records the no-pan clamp at 22 A as firmware-only, so a CT-blind controller loses it.

Bus 198 V (140 V line crest) is the main basis. 280 V (the U7 OVP screen used by D-31 and `fault_check.py`) is a sensitivity row, since it is a third fault.

## Method

Script `bank_ov_double_fault.py`; run it from the repository root. Square-wave drive of a series R-L-C tank; exact closed-form segment solutions (underdamped), no randomness, numpy only.

- **Bank:** 5 x 0.10 uF, K tolerance = +/-10 % (ordering code B32654A1104**K**000; TDK p.22 ordering table). Corners: L 59.85 / 66.5 / 73.15 uH and C 0.45 / 0.50 / 0.55 uF (the round-6 MC basis in `fault_check.py`). Five (L,C) corner pairs.
- **R levels (total tank series resistance):** 0.05, 0.15, 0.60, 1.60 ohm. 0.15 ohm is a low-load floor: the coil's lowest R_ac 116 mohm (DECISIONS 12) plus about 30 mohm for two FETs plus the bank ESR. 0.05 ohm is an explicit bound below any physical value. 1.60 ohm is roughly the loaded 28 A / 1.24 kW point.
- **Case A, time-domain trip (F1 and F2):** bridge at fixed f from rest; the shunt trips at |i| = 118.74 A; the bridge turns off T_D later; the tank free-wheels through the body diodes (bus clamps the coil) until i = 0. V_C peak is the maximum over the pre-trip drive, the delay, and the free-wheel. f grid: 35 offsets (0 to +/-20 %) around each corner's f_0.
- **Case B, quasi-steady just under the trip:** drive that holds the current at the band edge without tripping. V_C = I_pk x X_C at the drive frequency, maximised over f (the requested I_peak x X_C form). Evaluated with no f floor and with a 35 kHz floor.
- **Models are cross-checked** (controls below).

### Inputs (all committed; unit `zapote/power-stage-120v` at commit `3b515aade`)

| Input | Source |
|---|---|
| Shunt band 66.30-118.74 A (R34 12.6 k) | `validation-results/02-protection-timing/stage15-28A/out/ocp_bands.json` (`shunt_candidates`, `band_after_bound_A`) |
| T_D 2.267 us, f_res,min 25.09 kHz, Z0,max 12.75 ohm, committed I_off and bank bounds | `.../stage15-28A/out/fault_check.json`; constants in `.../stage15-28A/fault_check.py` |
| Envelope peak 59.17 A; bank V_C,pk 483.72 V at 28 A | `validation-results/05-resonant-tank-envelope/round6-full-power/outputs/board-side-protection.csv` (28 A row) |
| Bank part, count, value | `elec/src/parts.ato` (`ResB32654`), `elec/src/power_stage_120v.ato` (c_res1..5, "5 x 0.10 uF = 0.50 uF"), `validation-results/04-board-current-thermal/round5-native21/b3/make_heat_sources.py` (BANK = C21, C22, C23, C151, C152) |
| Datasheet (not committed) | TDK "Film capacitors, B3265*A/G/J/T", `MKP_B32651_658.pdf`, edition 6/26, SHA-256 `c32e3754787fa19b2e256e007c98a24755ae18eb52830cce430ffd6b177afdd3`, from `https://www.tdk-electronics.tdk.com/inf/20/20/db/fc_2009/MKP_B32651_658.pdf` (retrieved 2026-10-12) |

### Datasheet facts used (B32654A1104K000)

| Quantity | Value | Page |
|---|---|---|
| Rated DC voltage V_R / V_RMS (f <= 1 kHz) | 1600 V DC / 500 V AC (707 V peak equivalent) | p.22 |
| Capacitance tolerance | K = +/-10 % | p.22 (ordering code) |
| Factory DC test between terminals | 1.6 x V_R, 2 s (2560 V) | p.35 |
| Service life / failure rate | 200 000 h at 1.0 x V_R, 85 C; 1 fit at 0.5 x V_R, 40 C | p.35 |
| dV/dt limit, 27.5 mm, 1600 V / 500 V (non-sinusoidal) | 1000 V/us | p.36 |
| Permissible V_RMS vs f (sine, continuous, self-heating <= 20 K) | graph only, falls above about 10 kHz | p.44 |
| **Single-event / transient over-voltage** | **none given.** The only over-voltage statement is a footnote on p.12: "for pulse loads (pulse width > 1000 s) a peak voltage of 1400 Up can be permitted", attached to the 1250 V / 10 mm table, not to this 1600 V part. The sheet has no short-time, surge or transient over-voltage rating for B32654. | p.12, whole sheet searched |

The k0 table (p.36, 4 000 000 for this part) has a unit inconsistency in the sheet (V^2/s printed); it is not used.

## Results (`results.json`)

Governing figure: the quasi-steady case at the upper band edge with no f floor (V_gov = **1702.4 V**).

| Case | Worst bank peak (V) | Where |
|---|---:|---|
| Committed bound, no overshoot, 198 V (Z0,max x 118.74 A) | 1514 | `fault_check.py`, reproduced |
| Committed bound with one half-cycle of undamped growth, 198 V / 280 V | 2049 / 2271 | `fault_check.py`, reproduced |
| **A. F1 runaway, time-domain trip + overshoot** | **1688.8** | 280 V, R 0.60, L max, C min, f = 0.85 f_0 (23.6 kHz); at 198 V the worst is 1656.0 (R 0.60) |
| A. F2 pan removal, loop intact, time-domain | 1494.8 | 280 V, R 0.05, L min, C min, f = 1.15 f_0 (35.3 kHz); 198 V worst 1359.1 |
| **B. Just under the trip, no f floor** | **1702.4** | 280 V, R 0.05, L max, C min, I = 118.73 A at 24.67 kHz, X_C = 14.34 ohm; at 198 V and R 0.15: 1643.7 |
| B. Just under the trip, 35 kHz floor | 1178.4 | 280 V, R 0.05, L min, C min |

Other figures:
- **Overshoot is small.** Largest turn-off current in any simulated run 155.4 A (inside the committed 160.7 A / 178.1 A bounds, which the script asserts). The committed 2049-2271 V "with growth" figures are therefore loose.
- **Ratios for V_gov = 1702.4 V:** 1.064 x V_R; 0.665 x the 2560 V proof level; 2.41 x the 707 V sustained AC peak equivalent of the 500 V rating (that rating is for f <= 1 kHz and is thermal-limited at 25-60 kHz, p.44); 3.52 x the 483.72 V normal operating peak at 28 A.
- **Frequency floor needed.** If the drive frequency cannot go below the given floor in the fault, worst case over all corners, time-domain / quasi-steady: 25 kHz 1664.6 / 1671.9 V; 30 kHz 1629.6 / 1397.2 V; **35 kHz 1494.8 / 1178.4 V** (under V_R).
- **What each trip level is worth** (quasi-steady, no floor, same corners): shunt high corner 118.74 A gives 1702.4 V; CT band high corner 76.09 A gives 1164.5 V; the 62 A firmware peak trip gives 988.5 V. So with any of them alive the bank stays under V_R; the exposure exists only because the shunt, at 118.74 A, is the single remaining trip.
- **dV/dt:** at the largest I_off, 345.4 V/us on 0.45 uF, under the 1000 V/us non-sinusoidal limit (p.36).
- **Energy a clamp would absorb** (single event, bank at V_gov, C min): 0.652 J; coil energy at I_off 155.4 A, L max: 0.884 J.

### Controls (all asserted in the script)

- Envelope peak 59.17 A, shunt band 66.30-118.74 A and the 483.72 V bank peak at 28 A match the committed files.
- `fault_check.json` reproduced: T_D 2.267 us, f_res,min 25092 Hz, Z0,max 12.75 ohm, I_off 160.7 / 178.1 A, bank 1514 / 2049 / 2271 V.
- Time-domain model against the sine fundamental on three long non-tripping runs: current within 1.2-1.8 %, V_C within 1 % of I x X_C.
- Time-domain overshoot never exceeds the committed I_off bound.

## Verdict: INCONCLUSIVE

V_gov = 1702.4 V is 6.4 % over the 1600 V DC rating and 33 % under the factory proof level, so by the pre-set criterion it neither passes nor fails. Reading the table honestly:
- **Over V_R only if the drive frequency can run below 35 kHz** (down to about 0.85-1.0 x f_0 in the low-C, high-L corners; 30 kHz still gives 1629.6 V) with the bridge still driven, in a CT-blind controller. A frequency floor enforced outside the failed loop (35 kHz) brings every case under 1600 V (1494.8 V).
- The excess over 1600 V is a few percent at 198 V and R >= 0.15 (1656 V), so it sits inside the uncertainty of the model: loss R and L / C corner pairs are ASSUMED, and the drive is open-loop.
- The pre-existing conclusion in DECISIONS (a double-fault exposure "present before stage 15") stands but is smaller than the committed "with growth" 2049-2271 V.

## Limitations

- No bench or SPICE: closed-form series-RLC, ideal switches, dead time and ZVS ignored, constant bus (the real bus is unfiltered), frequency fixed during the build-up.
- R basis is assumed; the coil R_ac, the pan load and the hot FET R_DS(on) are not measured.
- L / C corners are the committed +/-10 % basis. A pan that moves L further than that, or a coil above 70 uH (the 80 / 90 uH round-6 alternatives), is not covered; higher L raises Z0 and the exposure.
- The shunt is taken at its committed corner, 118.74 A, delay 2.267 us (the D-31 bound with a 0.988 us Q1/Q4 allocation excess). With a measured shorter chain the overshoot falls.
- The CT-dead premise assumes the firmware peak and RMS trips share the CT; unverified for the AD8436 chain.
- The comparison is against a DC rating. A 1-3 half-cycle event at 24-35 kHz may stress the dielectric differently (partial discharge on the AC peak, self-healing events); TDK is silent.
- The datasheet is read from a text extraction and one page image (p.44); the V_RMS(f) graph values were not digitized.

## Recommendation (proposal only; no schematic, board or copper edit made)

1. **Close it in firmware first, independent of the CT:** a hard f_min >= 35 kHz in the bridge timer / MCPWM compare limits (not in the frequency loop), so a runaway cannot drive the tank below resonance in the low-C, high-L corners. In this model that alone brings the double fault to 1494.8 V (below V_R).
2. **Ask TDK** (application engineering, part B32654A1104K000) for the single-event / surge over-voltage rating, in V and number of half-cycles at 25-60 kHz. If it is >= 1.1 x V_R for a few half-cycles, the verdict becomes PASS.
3. **If neither is available, size a clamp study** on these inputs: a resonant-node clamp across RES_A to SW_B (or a bank-side TVS pair) must conduct from about 1.3 kV, absorb about 0.65 J (bank at 1702 V) to 0.9 J (coil at 155 A) in about 1-5 half-cycles, cap the bank at <= 1600 V, and not conduct at the 483.72 V operating peak. Study inputs: the I_off range 120-160 A, the bus 198-280 V, f 23-60 kHz and the L / C corners in `results.json`.
4. **Bench:** with the CT disconnected and the OCP forced, a ramped open-loop drive at 24-35 kHz on a current-limited supply, measuring V across the bank with a 1.5 kV differential probe.

## Reproduce

```sh
python3 zapote/power-stage-120v/validation-results/02-protection-timing/bank-ov-double-fault/bank_ov_double_fault.py
```

Writes `results.json` beside the script (deterministic; about 2 s). The script asserts the controls and exits nonzero if any fails.
