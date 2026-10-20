# c54-ct-band: the CT trip band against the firmware peak-trip cap (OPEN-ITEMS S29)

Board: native-21 stage 53, the board of record (board `82af7bd9…`, copper key `b7a0bc5790b9`). Branch
`codex/power-stage-integration`. This is an analysis only. Nothing outside this folder was changed. The proposed edits
are in `patches/`.

## Decision

**Fix chosen: both a BOM change and a firmware constant.**

1. **BOM (patch 01): change R44 and R45 from 10 kΩ to 11 kΩ.**
   - New part: RT0603BRD0711KL (Yageo 0.1 %, 25 ppm/°C), LCSC C728581.
   - This line is already on the BOM (R35 uses it). JLC had 10,027 in stock on 2026-10-15 (`sourcing/SNAPSHOT-2026-10-15.csv`).
   - Same 0603 footprint, same nets, no layout change. The BOM keeps the same number of lines.
   - CT band: **64.55–76.09 A → 67.36–79.32 A** (nominal 70.18 → 73.19 A).
2. **Firmware (patch 02): `TANK_PEAK_TRIP_MAX_A` 64.5 → 62.5 A.**
   - The derived trips already stop at `TANK_PEAK_TRIP_CAP_A` 62 A, so this changes no behaviour at any ceiling.
   - The constant now names the highest trip the firmware can actually reach, so B17 checks the real worst case.
   - It holds on every board: 2.05 A of margin on 10 k boards, 4.86 A on 11 k boards.
   - `commissioning_board_table.py` B17 now requires max(1 A, 2 %), not just "below". The negative control fails on 64.5 A.

**New margins** (all reproduced by `scripts/ct_band.py`):

| Quantity | As built (s53) | Chosen |
|---|---|---|
| B9 band (engine model, −10 / 85 °C uniform) | 64.55–76.09 A | **67.36–79.32 A** |
| Band at the s53 B3 temperatures (extended model) | 64.61–76.02 A | 67.42–79.25 A |
| Band at 85 °C, extended model (CMRR, 3 sense inputs, host load) | 64.43–76.23 A | 67.23–79.46 A |
| B17: CT low corner − config cap | **0.05 A** (64.5) | **4.86 A** (62.5; 7.8 %) |
| Firmware first at the 62 A cap (28 A, B-bank board), with the ADC error (E1), B9 extended | +0.51 A | **+3.31 A** (5.3 %) |
| Same at the s53 ladder stop (24 A, 55.08 A trip) | +7.28 A | +10.08 A |
| E2 (E1 + v3v3 drift since the zero trim) at 24 A / at 62 A | +2.78 / −3.99 A | +5.51 / −1.26 A |
| 64.17 A floor (28 A envelope 59.17 + 3 A pickup + 2 A), B9 extended | +0.26 A | **+3.06 A** |
| 65.34 A floor (with a 4.17 A pickup; commission-s53 open question 1) | −0.91 A | **+1.89 A** |
| Uniform network temperature at which the floor fails | 100.4 °C | 268.8 °C |
| High corner, with half the typical hysteresis | 76.27 A | 79.50 A |
| Bank peak at the high corner (35 kHz, 0.475 µF) / T1 secondary volt-time | 730 V / 10.4 V·µs | 761 V (VC 1500 V) / 10.8 V·µs (limit 1276) |

The rule I set, and how the chosen fix scores against it:

- **The rule:**
  - The ordering margin with the firmware's ADC error (E1) must be at least max(1 A, 2 % of the trip) at every firmware trip the firmware can reach (up to 62 A).
  - B17 must meet the same max(1 A, 2 %) rule.
  - The CT low corner must be at least 1 A above the 64.17 A floor.
  - E2 must be at least 0 at the ladder stop of the board of record (24 A).
- **Only the chosen fix meets every part of the rule:**
  - Firmware alone (C1) leaves E1 at 62 A at 0.51 A and the floor margin at 0.26 A.
  - Lowering the firmware cap to 58 A (C2) does not move the floor, and it clips the 26 A step.
- **Other BOM options:**
  - R43 / R46 → 2.00 k (C4) gives about the same margins, but needs a new BOM line.
  - R43 / R46 → 2.10 k (C5) gives less margin and also needs a new line.

Why max(1 A, 2 %):

- It is larger than everything the model leaves out or approximates:
  - the extended-model terms, 0.12 A;
  - the 25 °C qualifier on the ESP32-S3 ADC figure;
  - the estimator error in the B3 temperature: the corner moves about 0.016 A/K with the whole network, mostly through R39's 200 ppm/K, which cancels in the ordering.
- It is resolvable on the bench: the step-3 test winding measures trip current to better than 1 %.

## 1. Requirement: which trip must act first, and by how much

- **The firmware trip must act at or below the hardware CT trip.** Sources:
  - `tank_freq.h:103`: "below the … CT band low corner … so the firmware trip stays under the hardware trip".
  - COMMISSIONING step 3 item 1: the firmware supplementary trip "must latch `N21_FAULT_TANK_PEAK` before or at the hardware trip … it is not a qualified protection".
  - DECISIONS 13 rejected the stage-14 board because "its CT corner at 50.56 A sits under the 50.7 A firmware peak trip".
  - The hardware comparators (U10 / U11 → U13 → BUS_FAULT) are the qualified backstop.
- **What the firmware actually reaches.** `config_ok` (`n21_binding.c:103-105`) requires `tank_peak_trip_a ≤ tank_peak_trip_for(ceiling) = min(2.17 c + 3, 62)` **and** `< TANK_PEAK_TRIP_MAX_A`. So the highest reachable trip is 62 A (28 A ceiling). On the s53 bank, whose ladder stops at 24 A, it is 55.08 A. S29's 64.5 A was a check that never binds.
- **The firmware's own measurement error.** The firmware compares `(mV − zero) / 15 mV/A` against the trip (`n21_signal.c:28`). It reads the same node the comparators see (ct_sense_mon → R47 → J4.14 → TLV9062 follower → ESP32-S3 ADC1 ATTEN3). So T1's ratio and R39 cancel in the ordering, and the margin is computed in volts at that node.
  - **The error terms:**
    - **E1 (the rule):** the ADC error, ±50 mV (ESP32-S3 Series Datasheet v2.2 p.66, Table 5-6, ATTEN3), which is 3.3 A.
    - **E1s:** the same error counted at both the zero trim and the trip level, 100 mV.
    - **E2:** E1 plus the drift of v3v3 since the CT_MON zero trim. The bias (R40 / R41) and the references both follow v3v3, but the ADC does not. The TPS62933 VFB window is 792–808 mV at 25 °C and 788–812 mV over 0–85 °C (SLUSEA4D p.6), so up to 2.5 %, which is 70 mV at the node. The untrimmed zero error (36.9 mV) is smaller.
  - **Sampling:** at 20 kS/s the samples are asynchronous, so the firmware can only read *low*. Firmware-first is therefore a statement about thresholds, and the bench records the hit rate (COMMISSIONING step 3.1).

## 2. 64.55 A reproduced

`scripts/ct_band.py` sets up the round-3 engine exactly as `commissioning_board_table.py` does:

- parts from the frozen BOM;
- R39 scaled to the 1:200 CT;
- `validate_inputs`;
- `exact_corners` at −10 and 85 °C.

It gets **64.55–76.09 A** (exact 64.5539 A). The low corner is at 85 °C on the negative polarity. The script asserts the result against COMMISSIONING.md B9. Its own per-part enumerator reproduces the engine to 1.4e-14 A. It then adds the terms the engine leaves out:

- **TLV3201 CMRR** at the actual common mode: ≥ 56 dB, SBOS561C p.6.
- **Two more comparator inputs on the sense node.** U11 and U12 each draw IIB ≤ 5 nA (pp.5 / 6) through R42.
- **The controller follower's 10 MΩ load:** 0.35 µA through R42.

Datasheet limits used in the model:

| Part | Limit | Source |
|---|---|---|
| TLV3201 | VIO ±4 mV over −40..125 °C | SBOS561C p.5 / p.6 |
| TLV3201 | hysteresis 1.2 mV typ, no max | SBOS561C p.5 / p.6. It raises a rising trip, so it is applied only to the high corner |
| R39 RC1206 | ±200 ppm/°C (≤ 10 Ω) | Yageo RC1206 V.2 p.4 (`05-resonant-tank-envelope/sources/rc1206.pdf`) |
| R40–R46 RT0603BRD07 | ±0.1 %, ±25 ppm/°C | `round3/sources/README.md` row. The page was not re-read here |
| BAS116H | 80 nA leakage → ±80 µV | the engine's term |

## 3. Temperature bound without a new solve

- **Where the s53 temperatures come from.**
  - The s53 BASIS run files (`b3-ratings/runs/*_p0p25/p0p5.json`, board 82af7bd9, chain d0095b17e) carry pad-copper probes for every ref.
  - The gate's own estimator (`b3_ratings_gate.est`: Q25 + 3 |Q25 − Q50| + bay − 50, at the BASIS bays) gives the CT network's temperatures.
  - For R40–R46 the self-heat P × 46.3 K/W is added on top. The 46.3 K/W is derived for 0603 the same way thermal_body derives chip1206. P is at most 3.0 mW.
- **Results:**

| Ref | c17.5 @ 61 | c22 @ 55 | c28 @ 55 | worst |
|---|---|---|---|---|
| R39 (body element, heat row) | 70.3 | 69.4 | 78.1 | 78.1 °C |
| R40 / R41 | 62.2 / 62.7 | 56.4 / 57.2 | 56.8 / 57.9 | 62.7 °C |
| R43 / R44 / R45 / R46 | 62.1–62.2 | 56.3–56.5 | 56.7–56.9 | 62.2 °C |

- **Where the parts are.** R40 and R43–R46 sit at x 3.5–18.1 mm, y 132.9 mm, beside U10 / U11 (bottom-left edge). That is 115–130 mm from T1 / R39 (135, 111–130). R41 sits at (86.1, 128.8).
- **Cross-check against s52.** The temp-ratings-2026-10-15 study (s52 run files) gives the same numbers to 0.05 K. s53 moved no part.
- **Conservative bounds.** The band was also run with the whole network at a uniform temperature:
  - at the hottest CT-part estimate, 78.1 °C;
  - at the hottest probe within 25 mm of R40–R46, 83.9 °C (U4, c28);
  - at the c28 board laminate peak, 180.8 °C, an absurd bound.
  - The as-built floor holds at the first two and fails at 180.8 °C. The break is at a uniform 100.4 °C. With 11 k the floor holds at 180.8 °C (+1.44 A), and the break moves to 268.8 °C.
- **Answer to S29's worry:** "a hotter network lowers the corner". The network runs at most 62.7 °C (R39 at 78.1 °C), not 85 °C. So the B3 basis *raises* the as-built corner slightly, to 64.61 A. S29 was a missing-evidence problem, not a temperature problem. The real gaps were the firmware ADC error and the 0.38 A floor margin.
- **Finding: R39's B3 heat row is stale.** `b3/make_heat_sources.py:106,178` still computes `(I/100)² × 1.5 Ω` (the 1:100 CT). The fitted part is 1:200 with 3 Ω, which dissipates half as much (DECISIONS 23). So R39's 78.1 °C is conservative. Patch 04 corrects it.
- **Finding: R39's existing margins.json row is not gated.** It is `gated: False`, "1206 thick film (unverified)", limit 155 °C. Patch 03 adds the gated CT rows.

## 4. Constraints checked for the chosen fix

The same network sets these; each one checked:

- **28 A hardware rule (floor 64.17 A, kelvin_budget FLOOR):** +3.06 A, extended model.
  - This also closes commission-s53 open question 1 on the CT side: with a 4.17 A pickup, 65.34 A is cleared by +1.89 A.
- **OCP / Kelvin band:** not set by R40–R46. The shunt divider R32–R35 is unchanged, so 69.18–114.57 A and the 69.13 A bound are untouched.
- **Commissioned ladder:**
  - **Firmware trips:** the 22 / 24 A trips (50.74 / 55.08 A) and the round-6 envelope peaks (47.74 / 51.61 A) are unchanged. The firmware cap still allows 62 A, so no ladder step is clipped.
  - **Hardware trip vs every step:** the hardware trip sits ≥ 12.3 A above the 24 A step's firmware trip, and ≥ 5.4 A above the 62 A cap.
- **CT_MON and comparator input range:**
  - The hi-ref node is 2.813 V at v3v3 3.367 V, the top of the controller band. That is under the firmware's 2.85 V over-range.
  - It reaches 2.85 V only for v3v3 > 3.41 V, which is the TPS3703 OV window: RAIL_FAULT takes PERMIT low there (controller DECISIONS row "v3v3 slow out of window").
  - TLV3201 VCM stays ≤ VCC + 0.2 V.
  - The lo-ref node stays ≥ 0.519 V.
- **Stress at the higher trip:**
  - bank 761 V against 1500 V (VC at Top,max, B3264\*H p.15);
  - FET I_D,pulse 495 A;
  - T1 1276 V·µs;
  - R44 dissipation falls from 0.805 to 0.757 mW.
- **Gates touched by the BOM change (all in patch 01):**
  - `audit.rs` part table, plus a new test that fails the s53 10 k parts;
  - the ato module;
  - `thresholds.validate_inputs` overrides in the table tool;
  - the table-tool test string, which becomes 67.36–79.32 A, nominal 73.19 A.

## 5. B3 rows for R40–R46 (patches 03 and 04, not applied)

The chain runs `b3/make_heat_sources.py` and then `b3-ratings/run_basis.py` (which calls the gate) on every thermal run (`native-21/layout/gates/chain.sh:154,200`). So these patches take effect on the next chain run.

- **`b3/make_heat_sources.py`:**
  - adds heat rows for R40 / R41 / R43 / R44 / R45 / R46;
  - each row is the divider's static dissipation at v3v3 3.465 V, with values read from the frozen BOM;
  - R40 / R41: 3.002 mW each; R44 / R45: 0.805 mW; R43 / R46: 0.178 mW;
  - the heat-file schema is unchanged: ref, watts, board fraction, basis "estimate", note, position.
- **`b3-convergence/thermal_body.py`:** adds a `chip0603` package spec (46.3 K/W, derived as for chip1206) and maps RT0603 0603s to it. Without this, the body model raises "no package spec" on a 0603 heat row.
- **`b3-ratings/b3_ratings_gate.py`:** adds `ct_rows()`, gated rows for R39–R46.
  - **Estimate:** the body element where the part has a heat row, otherwise pad copper + P × Rth.
  - **Limit:** the band's **85 °C** basis. A row above 85 °C means "re-run B9 at that temperature", not "the band failed".
  - **Checks:** each ref is checked against its nets, and the parts against their MPN family.
  - **Verified on the committed s53 runs** (`results/verify-patches.txt`): all 104 existing rows and every metric are identical. The new rows are R39 +14.7 / +15.6 / +6.9 K, and R40–R46 ≥ +22.3 K.
- **Patch 04:** corrects R39's heat to (I/200)² × 3 Ω: 129.7 → 64.8 mW at the 29.4 A trip. The note is taken from the BOM.

## 6. Residual risks

1. **E2 at 28 A is −1.26 A.**
   - This applies only on a B-bank board, at a 28 A ceiling: if v3v3 drifts more than about 1.8 % from the zero trim, the hardware latches before the firmware.
   - It fails safe (a BUS_FAULT latch, operator reset).
   - It is visible at bench step 3.1, and the s53 H bank stops at 24 A, where E2 is +5.51 A.
   - Firmware could remove it by tracking the zero (the CT_MON mean over a half line cycle). That is not proposed here.
2. **The ADC figure is the 25 °C datasheet value.** Counted twice (E1s, error at the zero and at the trip), the 62 A margin is +0.14 A. At 24 A it is +6.92 A.
3. **The firmware trip is asynchronously sampled.** It can miss crests near the phase-lock frequencies (e.g. 40 kHz). Firmware-first is a threshold property only (COMMISSIONING: "not a qualified protection").
4. **The B3 temperatures are estimates.** They are the gate's still-air estimator on pad copper, with no 0603 bodies until patch 03 lands. R39's heat row is 2× high, which is conservative. The 85 °C gated rows will flag any future move.
5. **The CT trips about 3.2 A later in a hard fault.**
   - The stress at the new high corner is still well inside the ratings (section 4).
   - The shunt OCP (69.18–114.57 A) is unchanged and may now act first in some faults. Both paths latch.
6. **Not modelled:** T1 magnetising current and the C42 burden RC (−0.6 % at 60 kHz). Both raise the true trip, which is conservative for the floor and neutral for ordering.
7. **Not re-read:** the RT0603 TCR page. Without network access the Yageo RT datasheet was not available here, so the ±25 ppm/°C comes from the ordering code.
8. **Not compiled or run:** the firmware and audit.rs test edits. Builds and cargo were out of scope.
9. **Integration work for patch 01:**
   - Patch 01 is a BOM-only stage (s54, the s52 pattern).
   - Rebuild the frozen BOM and netlist, and the unit-level `frozen/` copy.
   - Add `STAGE_FACTS["54"]`.
   - Run `commissioning_board_table.py --write`: B9, B17 and, after patch 02, the B17 wording.
   - In the ledger, R44 / R45 move to the RT0603BRD0711KL entry.
   - Commission-s53's H14 then closes.

## Proposed text (not applied)

- **OPEN-ITEMS S29:** patch 05. The status becomes Candidate, with the numbers above.
- **DECISIONS draft:**

  > CT band re-reference (S29, c54-ct-band): R44 / R45 10 k → 11 k (RT0603BRD0711KL, existing line), band 67.36–79.32 A; `TANK_PEAK_TRIP_MAX_A` 64.5 → 62.5 A. B17 0.05 → 4.86 A; firmware-first at the 62 A cap with the ADC error 0.51 → 3.31 A; floor 0.38 → 3.19 A. R39–R46 become gated B3 rows at the band's 85 °C basis. Reverses if: a measured CT trip on the bench sits under 67.36 A at 25 °C, or the network's B3 rows exceed 85 °C.

- **COMMISSIONING H14:** "Closed by c54-ct-band. B17 is 4.86 A (2.05 A on 10 k boards with the firmware patch alone). R39–R46 are gated B3 rows at 85 °C."

## Reproduce

```sh
cd zapote/power-stage-120v/validation-results/11-candidates/c54-ct-band
python3 -I scripts/ct_band.py          # results/ct_band.{json,md}; --check: byte-identical re-run
python3 -I scripts/verify_patches.py   # results/verify-patches.txt; --check
```

- **Files:** `scripts/ct_band.py`, `scripts/verify_patches.py`, `results/ct_band.json`, `results/ct_band.md`, `results/verify-patches.txt`, and `patches/01`–`05`.
- **Patch order:** 01, 02, 03 and 05 each apply on their own to the working tree. Patch 04 applies on top of 03.
