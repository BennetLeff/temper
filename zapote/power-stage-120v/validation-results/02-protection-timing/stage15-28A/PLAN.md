# Native-21 stage 15 plan: size the hardware for a 28 A RMS tank ceiling

> **As built (stage 15, DECISIONS item 13, 2026-10-10).** This is the plan as written. Three things differ in the build:
> - **P-A1** starts at y 55: the R22 → C21 res_a tap runs at x 156.5 down to y 50.
> - **P-B2 is not taken:** its l_filt trim at x 112–114 cuts that mains pour in two.
> - **The §6 B3 gate (≤ 105 °C)** is below the model's own nominal peak (133 °C at h 25). It was replaced by a relative gate: no new hot spot above nominal (`../../04-board-current-thermal/round5-native21/b3/ceiling_sweep.py`). That gate supports 26 A; at 28 A the FET-row copper reaches 142.0 °C.

> **Planning only. ASSUMED / bounded calculations, pre-measurement.** Nothing under the unit or the repo was changed.
> - **Decision:** DECISIONS.md entry 10, 2026-10-10. The hardware is sized for 28 A. Firmware ships with a 22 A ceiling.
> - **Unit:** `zapote/power-stage-120v` at `18318042c`.
> - **Copper basis:** the newest routed dump, `scratchpad/v14e/i2/copper-dump.json` (sha256 `842bdbe5…`), with its `section.kicad_pcb` (`37f96150…`). Both passes report 0 unconnected, 0 barrier violations and 0 errors.
> - **Line references:** the unit's working tree carries the writer's uncommitted stage-14 edits (139 files, none touching R34/R35/R43–R46). File:line references are to that working tree as read on 2026-10-10. Re-locate them by symbol if lines have moved.
> - **Reproducibility:** every number below comes from a script in this folder (`sh run_all.sh <UNIT> <dump> <pcb>`, outputs in `out/`), or from a cited committed file or datasheet page. Curve readings taken by eye are labelled as such.

## 0. Summary of calls

| Item | Today | Stage 15 | Evidence |
|---|---|---|---|
| Shunt OCP divider R34 / R35 | 12.4 k / 11.7 k (band 47.33–97.77 A after Kelvin) | **R34 → 12.6 k, Yageo RT0603BRD0712K6L** (0.1 %, 25 ppm; LCSC C861103, 1,202 in stock at JLC 2026-10-10). **R35 stays** TNPW060311K7BEEA. | `ocp_bands.py` |
| Shunt band after the Kelvin shift | 47.33–97.77 A | **66.30–118.74 A** (Kelvin bound; 66.37 with the census); nominal 92.59 A | `out/ocp_bands.json` |
| CT trip references R43 / R46 | 3.32 k (band 50.56–60.01 A) | **2.21 k, RT0603BRD072K21L** (C705758, 4,358 in stock). R44 / R45 stay 10 k. | `ocp_bands.py` |
| CT trip band (both polarities) | 50.56–60.01 A | **64.55–76.09 A** | same |
| Firmware peak trip | 45 A, `config_ok()` cap < 50.9 A | Derived from the ceiling: min(2.17 × ceiling + 3, 62) A. **62 A at 28 A**, 50.7 A at 22 A. Cap moves to < 64.5 A. | §4 |
| Firmware RMS trip | 23.1 A per AD8436 sample | 1.05 × ceiling on the **half-cycle RMS** (29.4 A at 28 A). Per-sample guard at 1.5 × ceiling. | §4 |
| FETs at the new shunt high corner | — | **PASS.** Worst turn-off current is 178 A, against I_D,pulse 495 A (2.78×) and D-31's tested 330 A. | `fault_check.py` |
| SW_A copper | 7.0 mm (J5 bite), 9.6 mm leg | **Feasible.** Outline box P-A1 gives 10.79 mm minimum. | `sw_widths.py`, `proposals.py` |
| SW_B copper away from the FETs | 9.49 / 9.6 / 4.6–7.9 mm | **Feasible.** P-B1/B1b/B2/B3 give 10.0 / 10.09 mm; two necks of ≤ 2 mm remain. | same |
| SW_B copper beside the FETs, x 31–76 | 3.1–9.6 mm | **Not feasible without moving parts** (hard blockers listed in §5). **No part move in stage 15**; gated on B3 at 28 A. | same, `neck_fin.py` |

## 1. Shunt OCP divider (Kelvin path)

**Method.** The calculation mirrors the committed chain without changing it:
- `02-protection-timing/round3/thresholds.py`, `exact_corners()` at −10 °C and +85 °C with R5 at +50 °C. It is imported read-only and `PARTS` is patched in memory, as `08-manufacturing-package/native-21/bom-simplification/calc_protection_bands.py` does.
- The Kelvin shift is e_th × dI/de_th, with dI/de_th = −2(1−k)/R5 (kelvin README). e_th comes from `kelvin/budget-native21s14.json`: 2.1358 mV census, 2.2001 mV all-at-max-transfer bound. The bound is applied.
- The LM4040 minimum cathode current is checked with `audit.rs::min_reference_cathode_current_ua`.
- **Reproduction check:** 12.4 k / 11.7 k gives 49.53–97.77 A before the shift and 47.33 A after (census). This matches `budget-native21s14.json` exactly.

**Requirement (floor for the low corner after the Kelvin shift).** Envelope peak at 28 A is 59.17 A (`board-side-protection.csv`), plus the pickup stack, plus 2 A margin (round-6 rule):

| Basis | Pickup at 28 A | Floor |
|---|---|---|
| A. DECISIONS item 9 as written: 3.0 A, the 22 A / 31 kHz value | 3.00 A | **64.17 A** |
| B. FEM-phase stack, scaled to 28 A and the real operating frequency | 3.99 A | **65.16 A** |
| C. Arbitrary-phase "most pessimistic" stack, scaled | 9.31 A | **70.48 A** |

- **New finding: the coil-pickup stack was evaluated at 31 kHz.** EMF = jωΦ, so it scales with I_pk × f. Round 6 runs at up to 51–56 kHz.
  - The largest I_pk·f in the 28 A grid is enamelled steel, low corner, 140 V, 260 mm pan: 58.6 A at 51.13 kHz. That is **×3.107** the PICKUP.md basis (31.1 A at 31 kHz).
  - At 22 A it is already ×2.733, so the any-phase stack is 8.19 A on today's board.
  - Physically, pan B lags i_tank by about 21°. That is why basis B, not C, is the realistic one.

**Candidates (stocked 0.1 %, R35 kept unless noted; after the Kelvin bound):**

| R34 / R35 | Band after shift | Meets A / B / C | Bank peak, no growth | Note |
|---|---|---|---|---|
| 12.4 k / 11.7 k (today) | 47.26–97.77 | – / – / – | 1247 V | |
| **12.6 k / 11.7 k** | **66.30–118.74** | Y / Y / – | **1514 V** | single part change, E192 |
| 12.7 k / 11.7 k (E96) | 75.70–129.09 | Y / Y / Y | 1646 V > 1600 V | |
| 11.3 k / 10.5 k (E96 pair) | 65.50–117.84 | Y / Y / – | 1502 V | two part changes |

**Call: R34 = 12.6 k.**
- It clears bases A and B: margin 2.13 A over A, 1.14 A over B.
- It is the only single-part option that keeps the bank under its 1600 Vdc rating in a CT-failed fault without envelope growth (§2).
- Choosing 12.7 k to cover basis C would put the bank over its rating instead. A nuisance OCP trip latches safe; a bank over-voltage does not.
- Basis C is closed on the bench instead: PICKUP.md's U6 INP−INN measurement, now at 45–55 kHz and 28 A.
- The optional Kelvin-hook re-route in PICKUP.md (−56 % Kelvin EMF) is listed as stage 15b.
- **Other values:**
  - Thevenin resistance 6067 Ω; the C31 filter is essentially unchanged.
  - LM4040 minimum current 140.0 µA (≥ 80 µA).
  - R34 + R35 = 24.3 k for `ocp_threshold_load`.
  - The high corner of 118.7 A stays below audit.rs's 150 A loading corner.

**What sets the band width** (`band_contrib.py`, 12.6 k): 50.2 A as committed.
- An ideal comparator gives 33.9 A.
- Ideal R32/R33 gives 37.2 A; ideal R34/R35 gives 37.7 A.
- All four at 0.05 % / 10 ppm gives 35.9 A; an ideal R5 gives 43.2 A.
- No single cheap change halves the band, so tightening is not pursued.

## 2. FET check (IPW65R018CFD7, Q2/Q3/Q5/Q6 per `frozen/default.csv`)

**Datasheet, Infineon Rev. 2.0, 2021-04-19:**
- p.3 Table 2: I_D,pulse **495 A** (T_C 25 °C, t_p limited by T_j,max); T_j max 150 °C.
- p.4: R_thJC 0.28 °C/W.
- p.5: R_DS(on) 0.033 Ω typ at 150 °C. It is scaled ×18/15 to a maximum estimate.
- p.7 Diagram 3 (SOA, T_C 80 °C) and Diagram 4 (Z_thJC): read by eye, conservative side. The 1 µs line at 400 V reads ≥ 100 A; Z_th single-pulse at 100 µs reads ≤ 0.02 °C/W.

**Turn-off current.** `fault_check.py` bounds it in a CT-failed fault, where the shunt is the only trip:
- I_off ≤ I_hi + min(ΔA_half-cycle, t_d × di/dt).
- ΔA = V_bus / (π L f_res) at f_res,min 25.1 kHz (L +10 %, C +10 %).
- di/dt ≤ (V_bus + Z0·A) / L_min.
- t_d = 2.267 µs. It sums 555 ns front end (task 02 SPICE), 573.2 ns chain (D-31 after the DIS stiffening), the Q1/Q4 charge bound less its allocation (0.988 µs) and 150 ns gate.

| R34 12.6 k | 198 V bus | 280 V bus (OVP screen) |
|---|---|---|
| I_off max | 160.7 A | 178.1 A |
| I_D,pulse margin | 3.08× | 2.78× |
| Inside D-31 survival range (60–330 A, die V_DS ≤ 350 V) | yes | yes |
| T_j after a 100 µs pulse, from basis-A 140.1 °C | 145.2 °C | 146.4 °C |
| E_off estimate (350 V, 50 ns overlap) vs the derated 1 µs SOA energy | 1.41 vs 5.66 mJ | 1.56 vs 5.66 mJ |

- **Verdict: PASS**, with ≥ 2.78× on the pulsed rating and ≥ 3.6× on SOA energy, against stacked conservative terms.
- In the CT-working single fault, the CT trips at ≤ 76.09 A.
- **Confirm with D-31's own tool:** `survival.py --currents 160,180` is a value-only rerun (the existing points bracket it at 120 and 200 A).

**Bank voltage in the same double fault.** This is a new check, not in the brief.
- V_C,pk ≈ Z0·A, with Z0,max = 12.75 Ω.
- Without growth it is 1514 V at 12.6 k, against **1600 Vdc** (DECISIONS 2026-10-09 bank entry, B3265*A pp. 3, 22).
- With one half-cycle of undamped growth at resonance it is 2049–2271 V. **Today's board is already 1782–2003 V in that case.**
- This is a pre-existing double-fault exposure, not introduced by stage 15. It is recorded as a blocker for owner and vendor:
  - TDK's single-event over-voltage capability for B32654A1104;
  - or a resonant-node clamp.

**CT T1 at the new band.**
- Flux: 16.1 V·µs at 59.17 A / 35 kHz, 20.8 at 76.09 A, 46.3 at a 160 A fault, against 638 V·µs.
- CT_SENSE_MON at the high corner is 2.791 V, below V3V3 min 3.135 V, so it is not clamped before the trip.
- RMS is 0.318× of 88 A. **T1 unchanged.**

## 3. CT band

- **The band is set by** R43/R44 (REF_HI) and R45/R46 (REF_LO) against the 1.65 V midpoint (R40/R41) and the 1.5 Ω burden at 1:100 (15 mV/A).
- **New values:** R43 = R46 = **2.21 k**, giving REF_HI 2.7027 V and a band of **64.55–76.09 A** on both polarities (exact-corner model, rail 3.135–3.465 V).
- **Floor check:**
  - 64.55 A ≥ the round-6 rule's 64.17 A;
  - ≥ 62.26 A = 59.17 + the scaled CT pickup worst case (0.35 A × 3.107 = 1.09 A) + 2 A.
- **Why not 2.26 k:** it gives a 63.87 A low corner, which fails 64.17 A.
- **Unchanged:** the BAS116H clamps and the burden.

## 4. Firmware (`/Users/bennet/Desktop/temper/worktrees/ps-integrate/firmware/`, outside the unit)

| Where | Today | Change |
|---|---|---|
| `components/power/input_limits.c:7` | `.tank_limit_a = 22.0f` | Keep 22.0 as the shipping default. Source it from a new Kconfig `TEMPER_POWER_TANK_CEILING_DA` (range 100–280 dA, default 220), applied in `n21_hw_esp32.c` `config_from_kconfig()` (~l.524). |
| `input_limits.c:14` | `tank_limit_a <= 44.0f` | Change to `<= 28.0f`, the hardware sizing basis (DECISIONS 10). |
| `n21_binding.c:21` | `.tank_rms_trip_a = 23.1f, .tank_peak_trip_a = 45.0f` | Derive both in `n21_binding_init()` from `limits.tank_limit_a`: RMS trip = 1.05 × ceiling; peak trip = `fminf(2.17f * ceiling + 3.0f, 62.0f)`. 2.17 is round 6's largest peak/RMS (`board-side-protection.csv`, 22 A row). |
| `n21_binding.c:62` | `tank_peak_trip_a < 50.9f` | `< N21_PEAK_TRIP_MAX_A` = **64.5f**, which is CT band low (64.55 A) and keeps the firmware trip below the hardware trip. CT_MON ADC range is 80 A (62 A → 2.58 V < 2.85 V); ADC accuracy is ±3.33 A. |
| `n21_binding.c:61` | RMS trip ≤ 1.1 × limit | Keep. |
| `n21_binding.c:152-158` | per-sample `rms > tank_rms_trip_a` → `N21_FAULT_TANK_RMS` | Becomes a crest guard at 1.5 × ceiling (crest sample ≈ 1.41 × line RMS; the chain reads 2.495 V at 1.05 × 28 A crest, against 3.135 V full scale). Add the real trip after `n21_half_close()` (l.119-124): `if (r.est.tank_rms_a > cfg.tank_rms_trip_a) latch(TANK_RMS)`. |
| `n21_binding.c:142-144` | instantaneous `|ct_a| > tank_peak_trip_a` | Keep as the sampled backstop at the new trip. |
| `include/n21_binding.h:42,52,53` | fixed `frequency_hz`; comments "22 A × 1.05", "below the 50.9 A band" | `frequency_hz` becomes `f_max_hz` (60000). Add `f_min_hz` (35000) and `f_step_hz` (e.g. 250 Hz per half cycle, so 60 → 35 kHz in about 0.8 s). Update the comments. |
| new pure function `tank_freq_step()` (`components/power/tank_freq.c`), called once per closed half cycle | — | Steps f **down** from 60 kHz while all of these hold: f − step ≥ max(35 kHz, 1.05 f_res); half-cycle RMS ≤ ceiling; `est.inlet_bound_a` ≤ `inlet_target_a` (11.1 A power-stage share); estimated peak ≤ peak trip − 3 A. Steps **up** when any is violated. Above 60 kHz, burst (disabled today: hold at 60 kHz). |
| f_res and peak estimates | — | **f_res:** from CT_ZC phase at two adjacent steps, using the series-RLC FHA with C at its +10 % corner. Keep `min_lag_deg` as a hard floor. **Peak:** max(2.17 × half-cycle RMS, √2 × max per-sample AD8436 reading × 1.05), until bench calibration. |
| `fullbridge_adapter.c:166` | `bridge_plan_cycle(..., b->cfg.frequency_hz, ...)` | Use the loop's live `b->freq_hz`. The capture checks (l.143-157) already compare against `b->cycle`. |
| `n21_binding.c:261-270` `apply_cycle()` | only the fixed init plan; refuses `pwm_program` while pads are live | Accept any plan from `bridge_plan_cycle` within [f_min, f_max]. Program period and compare values through MCPWM shadow registers at timer zero (TEZ). |
| `power_service.c:107-111` `power_service_frequency()` | only `hz == config.frequency_hz` | Retire, or accept [f_min, f_max]. Round 6 also says to retire the old 44–50 kHz PLL table. |
| `components/safety/pwm_guard.h:25-27` | MIN 25k / MAX 60k / TARGET 38k ±1 % | Unused by the n21 path (grep). Retire it, or drop the TARGET-mismatch rule before anyone wires it in. |
| `components/power/Kconfig:35-39` | `TEMPER_POWER_FREQUENCY_HZ` 0–60000 | Becomes F_MAX (default 60000); add F_MIN (35000). |
| tests | `test/test_n21_binding.c:404` (60 A refused), `:454` (26 A > 23.1 A), `test/test_input_limits.c:47` | 404: peak trip 65 A refused, 62 A accepted. 454: inject over 1.05 × ceiling on the half-cycle RMS, not per sample. Add `test_tank_freq.c` for the step rules and the f_res floor. |

## 5. Copper (SW_A, SW_B)

**Method (`sw_widths.py`).**
- The net's copper on its layer is cut every 0.5 mm across the flow. Width is the total copper on the cut inside the run's window.
- "Available" adds the free area: the board inset by 0.5 mm, minus every other-net item buffered by `native-21/layout/rules21.py`. Those clearances are 8.0 SELV/PE↔HOT, 5.0 around res_a / crbleed, 3.2 between HOT groups and 0.2 otherwise. SELV/PE copper on any layer is also buffered by 8.0 (plan-view barrier).
- "hard" ignores other-net pours; "all" keeps them as filled today.
- Requirement: 9.77 mm (IPC-2221, 70 µm, 20 K, 28 A).

**Measured today (v14e/i2):**

| Run | Today min | Avail hard / all | Verdict |
|---|---|---|---|
| SW_A F.Cu leg to T1 (x 139–148.6, y 48–101) | **6.99** (J5 5 mm bite, y 63–78) / 9.6 elsewhere; IPC 34.7 K | 15.27 / 15.20 | widen right: P-A1 |
| SW_A F.Cu corner (x 103.6–110, y 30.4–37.2) | 6.40 over 5.5 mm | 14.70 / 7.28 | fin +0.8 K at 28 A; P-A2 optional (gets 6.7) |
| SW_A F.Cu other runs | ≥ 10.05 | — | OK |
| **SW_A B.Cu leg-A link, Q3 → Q2 (y 0.6–12.5)** | **2.83** over Q3.S and Q2.D pads (3.2 mm holes), 8 mm each | 5.34 / 2.85 | carries Q3's half: 19.8 A. Fin +3.2 K. Accept, and gate on B3 (new case, §6). |
| SW_B B.Cu, x 31–50 | **3.1–7.6** | 3.51 / 3.12 | infeasible in place (blockers below). Fin +15.3 K at 28 A. |
| SW_B B.Cu, x 57.5–76.5 | 6.89–9.6 | 7.52 / 7.19 | infeasible in place. Fin +5.9 K. |
| SW_B B.Cu, x 84–100 | 4.57–7.90 | 11.76 / 5.69 | pour-limited (l_filt): P-B3 |
| SW_B B.Cu drop (x 100.5–110) | 9.49 | 18.18 / 9.51 | P-B2 |
| SW_B B.Cu to the bank (x 150–188, y 37.2–46.8) | 9.60 over 37.5 mm (IPC 20.6 K) | 11.11 / 9.81 | P-B1 + P-B1b |
| SW_B bank strip | ≥ 12.29 | — | OK |
| SW_B on F.Cu as a parallel path, x 31–76 | — | **0.0** | no room |

**Hard blockers beside the FETs** (from `sw_widths.json` blockers and the pad/via census):
- **x 35–42:** R5's in-pad hv_ret via field (y ≤ 15.5) and the ocp_kelvin_n via at (41.3, 15.2) push the top to y ≈ 19.1–19.4. C40's hv_ret pad at (39.2, 28.2) pushes the bottom to y ≈ 23.8.
- **x 43–50:** the C56 leg_ret gate-return via at (46.38, 23.3) sits in the lane, with its 3.5 mm keep-out. It goes F.Cu C56.2 → In1 track to the leg_ret pour at y 12.2. C38's hv_ret pad is at (46.0, 28.2).
- **x 58–76:** C38 / C39 bus pads at y 28.2, Q2's gate and drain pads, and the SW_A leg-A link pour (y ≤ 12.5 + 3.2), which is itself a tank path.

**SW_B beside the FETs: not feasible at 9.8 mm without moving parts.**
- To reach it, the leg bus capacitors C38/C40 would have to move ≥ 5 mm south and R5 with its via fields north. That re-opens task 01's power-loop FEM and F6, D-31 and the Kelvin chain.
- **Call: no part move in stage 15.** These are short, fin-limited spans between wide copper. The 1-D fin estimate (`neck_fin.py`: no heat loss, isothermal ends) gives +15.3 K (x 31–50) and +5.9 K (x 57.5–76.5) at 28 A.
- **Gate:** B3 at 28 A (§6).
- **If B3 fails, least change first:**
  1. Move the C56 return via out of the lane, routing C56.2 on F.Cu to R13.2 (leg_ret, 41.9, 11.3). x 43–50 goes from 3.1–4.5 to about 8.1 mm. Cost: F6 loop re-extraction (task 01 round 17 d2) for leg A low side only.
  2. Only then, R5 + vias about 3 mm north, which needs task 01, task 04 R5 vias and a Kelvin rerun.

**Patches21-style outline edits** (boxes in board mm; union for "add", difference for "trim"; KiCad refills). They were checked with `proposals.py` against the clearances above on the v14e dump, including the barrier.

| ID | Edit | Clipped by (refill keeps the rest) | Result |
|---|---|---|---|
| P-A1 | sw_a F.Cu **add** (148.6, 37.2, 152.4, 101.5) | R22 res_a pad and track (5 mm tank rule) | leg minimum 6.99 → **10.79 mm** |
| P-A2 (optional) | sw_a F.Cu add (100.0, 30.4, 103.6, 37.2); trim n_filt F.Cu (96.0, 26.0, 103.6, 41.0) | C127 n_ls pad and vias | corner 6.4 → 6.7 mm (fin-limited anyway) |
| P-B1 | sw_b B.Cu **add** (150.0, 46.8, 188.0, 50.0), i.e. restore stage 13's SWB_BAND_TRIM where the res_a 5 mm rule allows | res_a strip / C21 pad | survives for x ≳ 169 |
| P-B1b | sw_b B.Cu add (150.0, 36.8, 188.0, 37.2); trim l_filt B.Cu (150.0, 33.4, 188.0, 34.2) | l_filt track | run to the bank 9.60 → **10.00 mm** |
| P-B2 | sw_b B.Cu add (110.0, 19.7, 110.6, 37.2); trim l_filt B.Cu (112.0, 9.0, 114.0, 37.0) | none | drop 9.49 → **10.09 mm** |
| P-B3 | sw_b B.Cu add (83.7, 15.6, 100.5, 19.4); trim l_filt B.Cu (83.0, 12.4, 101.0, 17.0) | l_filt track | x 84–100: 4.57–7.90 → ≥ 8.37 mm, except necks at x 84–86 (C39 pad) and a 1.5 mm corner at x 98.5–100 |

- **These are outline edits on the stage-14 copper,** applied through `incr21.py` like stage 6's SWB_RAISE. There is no reroute.
- **The l_filt trims are 0.4–4.6 mm off a mains pour that has a large area.** Re-run task 04's ac_l/ac_n cases.
- **P-B3 trims l_filt to y ≤ 12.4 over x 83–101.** BR1's pads (y 2.6–6.6) stay covered.

## 6. Thermal at 28 A (B3 / task 04)

`thermal_scale.py` reads the committed B3 inputs:
- **R5:** 0.784 W at 28 A and 0.864 W at the 29.4 A RMS trip, against its 1 W rating. The B3 row is 0.461 W, which is 21.47² × 1 mΩ.
- **R39:** 0.118 / 0.130 W.
- **Tank copper:** ×1.70 / ×1.88 over B3 nominal. The run_study case scale (I/18.7)² is 2.24 / 2.47.
- **Bank: B3 is stale.** `make_heat_sources.py` still carries task 03's CDE 942C rows for C21–C23 and has no C151/C152. Round 6's worst part carries 6.55 A at 28 A.
- **What does not scale:** gate drive, bias, AUX. They depend on f, not on the ceiling.

**B3 needs a 28 A case. Add these to `b3/run_study.py`:**
- `OPS["c28"] = {"I_t": 29.4, "I_line": 11.1, "parts": "c28"}`. 29.4 A is the firmware RMS trip, the highest sustained current; 11.1 A is the inlet hold.
- **In `cases()`, add an `sw_a_low` row** and weight SW_A 0.5 / 0.5 the way SW_B already is. The A-low path (Q3.2 → leg-A link → T1.1) is **not in task 04 today**: `run_cases.py:41` has only `sw_a` from Q2.3.
- **New A4 case in `run_cases.py`:** `('sw_a_low', 'sw_a', ['Q3.2:18.7'], [], ['T1.1'], ...)` at the fine 0.0625 mm pitch.
- **`make_heat_sources.py`:**
  - add a `c28` mode with R5 = I²·1 mΩ and R39 = (I/100)²·1.5;
  - give each of the five TDK parts P = I_part² × ESR(f), with I_part = 6.55 × 29.4/28 A. ESR or tan δ at 40–50 kHz must be read from TDK's B3265*A data sheet; it is not in any committed file today;
  - replace the CDE rows.
- **Pass criterion,** proposed and to be recorded in DECISIONS: copper and pad cells ≤ 105 °C at 50 °C ambient, h 10 and h 25, at 0.5 mm pitch. This gives a 25 K FR-4 margin below a 130 °C class.

## 7. Gates, records and the writer's ordered steps

**Value-only, with no copper change and no reroute.** R34 12.6 k, R43/R46 2.21 k (same 0603 footprints) and firmware.

**Incremental copper.** P-A1, P-B1, P-B1b, P-B2, P-B3 (and optionally P-A2) go into a new `patches21.py` stage-15 block plus an `incr21.py` pass. Parts don't move and the copper isn't rerouted.

**Full reroute: none.** One is needed only for the B3-fail fallback (part moves).

Ordered steps:
1. **Source** (value-only):
   - `elec/src/parts.ato`: add `R12k6Thin` (RT0603BRD0712K6L) and `R2k21Thin` (RT0603BRD072K21L); retire `R12k4Thin` and `R3k32Thin`, which are used only by r_th_top and R43/R46.
   - `power_stage_120v.ato` l.551-556 and l.766-781: values and comments (trip ~93 A nominal, band 66.3–118.7 A; CT ~70 A, band 64.6–76.1 A).
   - Rebuild with ato. Refresh `frozen/` and `native-21/frozen/` (both must stay byte-identical, `verify_source.py`).
2. **audit.rs:**
   - l.321 `r_th_top` → RT0603BRD0712K6L; l.342/345 `r_ct_hi_top` / `r_ct_lo_bot` → RT0603BRD072K21L;
   - l.576-577: `24_300.0`, with the comment updated;
   - the l.320 comment ("~61 A") and l.1060 ("3.32");
   - Add tests: the CT references must be 2.21 k (a 3.32 k part fails), and r_th_top 12.4 k fails.
   - `selected_reference_bias_covers_shunt_loading_corner` still holds (140.0 µA).
   - Single-file rustc of audit.rs; expect 66 + 2 tests.
3. **`native-21/verification/verify_source.py:21`:** assert `RT0603BRD0712K6L`, plus R43/R46 2.21 k. The component count stays 351.
4. **Copper:**
   - stage-15 block in `patches21.py` (the boxes in §5);
   - `incr21.py` on the final stage-14 board, then DRC 0/0/parity 0, barrier gates 0;
   - D5 audit (`d5-audit.json`): P-A1 approaches no SELV; confirm 8.047 / 8.507 unchanged or better;
   - DFM and Gerber review;
   - enclosure fit, which should be unchanged because no part moves (rerun for the record);
   - a new `native21s15-all-copper.json.gz` export.
5. **Kelvin chain:**
   - `kelvin_plane.py <s15 export> native21s15` with `DIVIDER["native21s15"] = (12.6e3, 11.7e3)` (l.47);
   - `kelvin_budget.py native21s15` with `BAND_BEFORE["native21s15"] = (68.58, 118.74)`;
   - change the `meets_44A_min` floor to the stage-15 floor 64.17 A. Expect about 66.3–118.74 A;
   - README stage-15 paragraph.
6. **Task 02:**
   - add the 12.6 k and CT 2.21 k rows to `calc_protection_bands.py` (or a stage-15 copy);
   - rerun `tools/ct_detector` with the new references;
   - rerun D-31 `retune.py` and `survival.py --currents 160,180`;
   - coil-pickup: add an `(I_pk, f)` scale argument to `sensitivity.py`; this folder's `ocp_bands.py` shows the numbers.
7. **Task 04:**
   - `run_cases.py`: add `sw_a_low`;
   - rerun the copper screen on the s15 export, then `sw_widths.py` + `neck_fin.py` from this folder (needs the copper-dump format);
   - **B3:** the `c28` case and the bank-row fix (§6);
   - **This is the gate for the SW_B FET-region necks.**
8. **Firmware** (§4):
   - in `worktrees/ps-integrate/firmware/`, with host unit tests: `test_n21_binding`, `test_input_limits`, new `test_tank_freq`;
   - the commissioning procedure gets the stepped-ceiling rule: 22 → 24 → 26 → 28 A, each step only after the bench items below.
9. **Records:**
   - DECISIONS.md: a stage-15 entry with values, floors (A/B/C) and the double-fault bank finding;
   - BOM / ORDER package (two new MPN lines, two retired);
   - BRINGUP-PROBES (new trip levels for the injected-current test);
   - ECO.md / PART-CHANGES.md.

**Release gates for raising the commissioned ceiling** (unchanged from round 6, plus two from this plan):
- bank hot-spot at 26–28 A;
- coil R_ac ≤ 0.23 Ω and winding temperature;
- switching loss (basis A vs B, sink);
- measured CT and shunt trip points after the divider change;
- **pickup at U6 INP−INN at 45–55 kHz** (closes basis C);
- **B3 28 A pass**.

## Blockers and open items

1. **Bank over-voltage in a CT-failed fault.** It exists today (1782–2003 V with one half-cycle of growth). Stage 15 at 12.6 k: 1514 V without growth, 2049–2271 V with growth, against 1600 Vdc. Needs TDK's single-event over-voltage figure, or a resonant-node clamp study. This is a double fault, and it is not a stage-15 regression.
2. **Pickup basis C.** 12.6 k misses it by 4.18 A. It closes on the bench pickup measurement, or with the optional PICKUP.md Kelvin re-route (stage 15b).
3. **SW_B FET-region necks** (3.1–7.6 mm, x 31–50) and the **SW_A leg-A link** (2.83 mm over two pads, never modelled in task 04). Both are gated on B3 c28 with the new `sw_a_low` case.
4. **B3 bank rows are stale** (CDE parts, no C151/C152). TDK ESR or tan δ at 40–50 kHz must be cited from the data sheet first.
5. **The firmware frequency loop needs live MCPWM period updates.** This is new code on the safety path, so the host tests and a bench step plan are required before commissioning above 22 A.

## Files

| Script | Output |
|---|---|
| `ocp_bands.py [UNIT]` | `out/ocp_bands.json`: requirement floors, pickup scaling, Kelvin, shunt and CT candidates |
| `band_contrib.py [UNIT] [R34] [R35]` | `out/band_contrib.json`: what sets the shunt band width |
| `fault_check.py [UNIT]` | `out/fault_check.json`: FET, bank, CT flux, sense headroom |
| `thermal_scale.py [UNIT]` | `out/thermal_scale.json`: B3 source scaling |
| `sw_widths.py <dump> <pcb> [UNIT]` | `out/sw_widths.json`: cut widths and availability with blockers |
| `neck_fin.py` | `out/neck_fin.json`: 1-D fin excess per narrow span (estimate) |
| `proposals.py <dump> <pcb> [UNIT]` | `out/proposals.json`: clearance-checked outline edits and widths after them |
| `sw_region_plot.py <dump> <png> [x0 y0 x1 y1]` | `out/sw*.png` |
| `jlc_lookup.py` | Stock lookups, a copy of the bom-simplification helper; it caches in `raw/` here |
| `run_all.sh <UNIT> <dump> <pcb>` | Runs all of the above |
