# Bench procedure: the board-face h that the enclosure delivers to native-21, in B3's form (S24, DECISIONS 66)

2026-10-16. Analysis lane; nothing written to any git worktree.

- **Unit:** native-21, PS = `worktrees/ps-integrate/zapote/power-stage-120v`, HEAD 05a3d9138, board of record s48
  (2b46d90e, gerbers ad165685).
- **Model:** a byte copy of PS HEAD's B3 tree and the files it reads, at `bench-h/snap/` (`SNAPSHOT.txt`: git status
  clean, A4 field set hash = `outputs/cache.json`).
- **Scripts:** `bench-h/scripts/` (`snapshot.py`, `bench_h_fit.py`, `s48_check.py`). Results: `bench-h/results/`.

## 0. Answer

1. **Method: (b), the real board under DC copper heating, as the release evidence. (c) confirms it per step; (a) is for
   enclosure development only.**
   - The board is unpowered. A bench supply drives I from BR1.1 to BR1.4 through one bridge diagonal, its two FETs
     jumpered drain to source on the solder side, through T1, a J2–J5 strap and the bank (linked C.1–C.2).
   - Every heated copper segment is an existing A4 DC case with the same source and sink pads. B3 already knows the
     heat; h is the only unknown.
   - No switching, no gate drive, no bias, no mains, no firmware: the board sits at ≤ 1 V.
   - Run both diagonals (diag1: Q2 + Q6; diag2: Q5 + Q3).
   - **A heater on the heatsink holds each FET tab at its drain-pad temperature.** B3's drain-lead tie spans
     0.020–0.280 W/K across the TO-247 drawing range. Without the guard that band becomes a ±10 % h error (§6.3).
2. **Reduction is B3 itself** (`scripts/bench_h_fit.py`, on a byte-copy snapshot of PS HEAD).
   - It solves the bench case with the as-measured heat (I, the R5 Kelvin power, the tab, cable and air temperatures,
     the bench links as nodes).
   - It sweeps h, interpolated in 1/h, and fits the measured ΔT at the binding FET-row / R5 strip (LAM_R5.4, R12, R10,
     R20, R18, R5.1, FETROW_B, Q2S_F / B) by weighted least squares, finishing on 0.25 mm.
   - It fits the tank path separately and checks the loss against the Kelvin loop power.
   - **Selftest** (synthetic truth with model settings the fit is not told):
     - face flow at h 31: **31.6 ± 2.4 (U95 7.5 %)**;
     - base flow at h 16: **15.4 ± 0.9 (6.0 %)**;
     - both recovered inside U95.
3. **Pass / fail per step:**
   - **gate A:** h_L95 in the worst sample-plan condition ≥ h_req;
   - **gate B:** h at the nominal condition ≥ 1.2 × h_req (1.25 × the base h for jets + base).
   - **At 61 °C hot-corner air**, the ceiling is the highest step whose gates both pass (h_L95,worst / h_nom):

     | Step | 18 A | 20 A | 22 A | 24 A | 26 A | 28 A | 28 A, jets + base |
     |---|---|---|---|---|---|---|---|
     | h_L95,worst / h_nom | 11 / 13.2 | 13 / 15.6 | 17 / 20.4 | 20 / 24 | 25 / 30 | 31 / 37.2 | base 16 / 20, with the jets' h_top ≥ 100 measured |

   - **At 55 °C:** 10 / 12, 11 / 13.2, 14 / 16.8, 17 / 20.4, 22 / 26.4, 27 / 32.4, jets 12 / 15.
   - **Above 61 °C:** 17.5 A.
   - **On s48 the c28 brackets re-solve unchanged** (31 / 27, 16 / 12). Each step is still closed by COMMISSIONING
     gate 0: B3 re-run at floor(h_L95,worst) on the board fitted.
4. **Sample plan:**
   - one TTV board, moved between ≥ 3 enclosure + fan sets;
   - per set: nominal (both diagonals plus a re-seat), D-18 / face-fan drive sweep, clogged filter, aged fan (−15 %
     rpm), both combined, orientation, and hot inlet at 55 / 61 °C;
   - the 78 °C stacked bay is measured but grants nothing.
   About 1.5 days for the first set and 0.5 day for each other.
5. **Conflicts** (§11):
   - the airflow28 README names a heated plate / IR bench as the release method;
   - COMMISSIONING gate 0 still cites the superseded cold-copper ENCLOSURE-REQUEST;
   - OPEN-ITEMS S2 still carries the s42 / jet-strip state;
   - the airflow-r1 jet bench's PASS line and ceiling output are cold-copper and strip-only;
   - the 78 °C stacked bay is outside the ladder, with no air sensor in the firmware;
   - the firmware has no face-fan stall clamp and no per-ceiling minimum fan drive.

---

## 1. The quantity, and why the method

### 1.1 What "h" means in B3

B3 has one film coefficient, `h`:
- `thermal_body.assemble` puts `conv = h·A_cell` on the top and the bottom sheet of every board cell;
- `build_network_parts` gives every heated part body the same h on its air path (generic bodies `r_top + 1/(h·A)`,
  C38–C41 the `film_body_g_air(h)` fin, PS2 `h·5246 mm²`);
- the air is the bay (`@<bay>`, solved at absolute temperature on hot copper), except C38–C41 and PS2, which see
  bay + 15 K unless a region credits them.

It lumps convection and radiation (h 10 is still air, radiation included; `audit-2026-10-15`). It is a **model
parameter**, not a local physical coefficient. The ladder in airflow28 §3 is a statement about that parameter: "with
this h in B3, every gated row at step N is ≥ 0".

So the release evidence has to be **the h that makes B3 reproduce the real board's temperatures at the binding
locations, in the real enclosure.** That is an inversion of B3 on the real board.

### 1.2 The three candidates

| | (a) heated FR-4 coupon | **(b) real board, DC copper heating (primary)** | (c) in-situ thermocouples at stepped ceilings |
|---|---|---|---|
| What it measures | Smooth-surface local h of a coupon | B3's own h on the real board, real parts, real enclosure | B3's h, but confounded with the switching heat |
| Heat known to | ±1–2 % (heater V·I) | ±2–3 % (the A4 DC fields are DC experiments from the same pads; R5 and the loop power are measured) | ±20 % or worse: switching loss basis A vs B, the R_on 0.217 W bound, bank and coil heat |
| Flow around tall parts (TO-247 21 mm, film caps 17.5, bank 26.5, PS2 24) | Absent unless replicated | Real | Real |
| Transfer to B3 | Needs a model of the transfer (the quantity is different) | None: the fit *is* B3 | None |
| Hazard | None | None: ≤ 1 V on the board, no mains, no bias | HOT side at line potential, switch nodes at 50 V/ns |
| When it can run | Before boards exist | As soon as one assembled board and an enclosure exist | Only at a ceiling already allowed: circular for the step being decided |
| Role here | Enclosure development and a model-free cross-check | **Release evidence for every ladder step** | Confirmation at each step after it is allowed; closes the heat-basis items (b) cannot |

**Recommendation: (b) as the primary method, (c) as confirmation, (a) only as an enclosure-development tool.**
- (a) is not release evidence:
  - it measures a different quantity, and the transfer from a smooth coupon to a populated board is exactly the
    uncertainty the measurement is meant to remove;
  - the airflow-r1 jet bench rejected an FR-4 coupon for the same reason (its DECISIONS J1: spreading length
    16.7 mm, local h smeared, plate spread up to 41 % of the rise).
- (c) cannot decide a step:
  - the step must already be allowed before it can be run;
  - at operating heat, a 20 % heat-basis error reads as a 20 % h error.
- (b) isolates convection:
  - every heated board-copper segment is an **existing A4 DC case**, solved from the same source and sink pads the bench
    drives (`outputs/*.json` source_pad / sink_pad), so no new field solve is needed;
  - the only unknown left is h;
  - the bench hot spot lands on the same 1 mm block as the operating c28 hot spot (38.5, 15.5) F.Cu (§6.1).
- The airflow28 README (§5.4) says the release needs "a measured h … from a heated-plate or IR bench". This procedure
  departs from that on purpose (§11, item 2).

### 1.3 Method (b1): jumpered diagonal, no switching, no drive

The board is unpowered. A DC bench supply drives a known current I from BR1.1 to BR1.4 through one diagonal of the
bridge. The two TO-247s of that diagonal are bridged drain to source on the solder side, so no gate drive is needed.
The path runs through T1's primary, J2 → a strap → J5 (in place of the coil), and the five bank positions, each
bridged C.1 → C.2.

| Config | Path | A4 cases heated (at (I / I_ref)², whole time) |
|---|---|---|
| **diag1** (Q2 + Q6 jumpered) | BR1.1 → Q2.2 \| Q2.3 → sw_a → T1.1 \| T1.2 → J2 → strap → J5 → res_a → C\*.1 \| C\*.2 → sw_b → Q6.2 \| Q6.3 → leg_ret → R5 → hv_ret → BR1.4 | bus_dc_q2, sw_a, coil_feed, res_a, sw_b_low, leg_b, hv_dc |
| **diag2** (Q5 + Q3 jumpered) | BR1.1 → Q5.2 \| Q5.3 → sw_b → C\*.2 \| C\*.1 → res_a → J5 → strap → J2 → T1.2 \| T1.1 → sw_a → Q3.2 \| Q3.3 → leg_ret → R5 → BR1.4 | bus_dc_q5, sw_b_high, res_a, coil_feed, sw_a_low, leg_a, hv_dc |
| alt (optional) | An external commutator (two contactor pairs, or an external MOSFET bank) alternates diag1 / diag2 at ≤ 1 Hz, 50 / 50 | B3's own half-path weighting (sw_* at 0.5, coil_feed and res_a at 1) |

- **Run diag1 and diag2 both.** Each gives an independent fit with the jumpers at different FETs. Agreement within the
  combined U95 shows that the jumpers do not bias the fit (§6.3).
- **Variant b2 (gate-driven):** the product's drivers hold the diagonals at ≤ 1 Hz. It removes the FET-row jumpers and
  heats the sink the way operation does. The cost:
  - the bias chain must be live, which means mains on PS2 with BR1 lifted;
  - a firmware bench mode is needed, with the CT-based faults masked, since DC through T1 trips `N21_FAULT_CT_ZC_STALE`.
  The same script fits it (`config: alt`, attachments without the FET jumpers). Use b2 only if that bench mode exists.

---

## 2. Requirement and thresholds being tested

From airflow28 §3 / §4.4 / §7, both faces and the whole board, hot copper. The ladder is solved on s47 (83355da5);
§2.1 checks the c28 brackets on s48.

| Tank ceiling (trip) | 18 A (18.9) | 20 A (21.0) | 22 A (23.1) | 24 A (25.2) | 26 A (27.3) | 28 A (29.4) |
|---|---|---|---|---|---|---|
| h_req at ≤ 61 °C air (solved pass) | 11 | 13 | 17 | 20 | 25 | 31 |
| h_req at ≤ 55 °C air | 10 | 11 | 14 | 17 | 22 | 27 |
| **h_design = 1.2 × h_req at 61 °C** | 13.2 | 15.6 | 20.4 | 24.0 | 30.0 | 37.2 |
| h_design at 55 °C | 12.0 | 13.2 | 16.8 | 20.4 | 26.4 | 32.4 |
| Binding row at the pass (s47) | R10 | R10 / laminate | laminate block | R12 | R12 | laminate block / R12 |

**Jets route, 28 A only:**
- base h_req is 16 at 61 °C and 12 at 55 °C;
- the design base is ×1.25, so 20 / 15;
- the jets must deliver **h_top ≥ 100** on `JET_REGION` (x 0–90, y 7–23.5).

Below 28 A, a jets + base set that passes 28 A passes every lower step, since B3 is monotone in the tank current.
Otherwise the no-jet column applies, which is conservative.

**Air** is the hot-corner leading-edge air, the "bay" in B3.
- Between 55 and 61 °C, interpolate.
- Below 55 °C, hold the 55 °C column (the 50 °C column exists only at 28 A: 24).
- **Above 61 °C nothing is solved, so the ceiling stays at 17.5 A.**

### 2.1 The c28 brackets on s48

`scripts/s48_check.py`: the snapshot's own `run_basis.py`, gate cases, both meshes and the gate estimator →
`results/ladder-s48-check.json`.

| Case | s48 worst gated (K) | Row | s47 (airflow28) |
|---|---|---|---|
| c28_h30 @ 61 | −0.9 | laminate 1 mm block | fail |
| **c28_h31 @ 61** | **+0.3** | laminate 1 mm block | pass (block +0.3, R12 +0.6) |
| c28_h26 @ 55 | −0.6 | laminate 1 mm block | fail |
| **c28_h27 @ 55** | **+0.9** | laminate 1 mm block | pass (block +0.9, R12 +1.1) |
| c28_h15_jet100 @ 61 | −0.7 | FET-row copper | −0.7 |
| **c28_h16_jet100 @ 61** | **+0.7** | FET-row copper | +0.7 |
| c28_h10_jet100 @ 55 | −4.0 | FET-row copper | −4.0 |
| **c28_h12_jet100 @ 55** | **+0.4** | FET-row copper | +0.4 |
| Control: c28_h10 @ 55 against the s48 chain's own run files | −51.2 | R12 | 0.0 K on the 1 mm block and on all part tj, at both meshes |

**On s48 the c28 brackets are unchanged: 31 / 27 face flow, 16 / 12 base under the jets.** The stage-48 changes (C176–C178,
U3 heat copper, EN dividers) are outside the FET-row / R5 strip. The lower steps were not re-solved. The gate-0 run on
the fitted h (§7) covers each of them on the board fitted.

---

## 3. The test vehicle (TTV) and its preparation

One fully assembled s48 board with **every part fitted**: the bodies shape the flow. It is a dedicated thermal test
vehicle. After the DC runs it is not powered at mains until COMMISSIONING step 3 (CT trip) has been re-measured on it,
because DC saturates T1 and may leave remanence.

Steps (photograph each and record the measured values in `RUN.json`):

1. **Record** the board serial number, revision and lot. Weigh it. Photograph both faces.
2. **FET jumpers (solder side):**
   - for diag1, Q2 and Q6; for diag2, Q5 and Q3;
   - one 2.5 mm² (13 AWG) bare copper link per FET, from the pin-2 (drain) lead tail to the pin-3 (source) lead tail,
     5.45 mm apart, ≤ 10 mm long, soldered along the fillet;
   - measure each link 4-wire at room temperature (≈ 0.05–0.1 mΩ);
   - leave the gates on the board's own gate network, with the drivers unpowered.
3. **Bank links (solder side):**
   - for each of C21, C22, C23, C151 and C152, one 1.5 mm² link between its two lead tails (27.5 mm pitch);
   - make all five the same length, ±1 mm;
   - measure each link 4-wire;
   - the caps stay fitted.
4. **Coil strap:**
   - J2 to J5, made of the product's coil-lead cable at its product length, lugs and torque, joined at a bolted splice
     where the coil would sit;
   - the coil itself is not connected;
   - measure the strap's resistance 4-wire.
5. **Supply leads:**
   - 10 mm² flexible leads soldered onto the BR1.1 (+) and BR1.4 (−) lead tails on the solder side;
   - run them straight away from the board for ≥ 100 mm, out of the face-flow path;
   - put one TC on each lead 20 mm from its joint (this is the "tie" in the model);
   - BR1 stays fitted and clamped: it is reverse-biased at < 1 V and carries no current.
6. **Kelvin taps:**
   - fine wires on R5's sense pads, R5.2 / R5.3, for P_R5 = V_R5 · I;
   - a separate pair on the BR1.1 / BR1.4 pads, for V_loop.
7. **J1:** unplugged and capped. **No mains anywhere on this bench.**
8. **Sink guard heater:**
   - two aluminium-housed wirewound resistors, 100 W each, on thermal compound, bolted to the heatsink base outside the
     FET / BR1 clamp footprint, placed symmetrically about the FET row;
   - fed from a 0–60 V / 5 A supply.
   - **Why:** B3's drain-lead tie spans **0.020 to 0.280 W/K** across the IPW65R018CFD7 drawing range
     (`drain_lead_conductance`, central 0.084). With unheated FETs the tabs would sit 20–40 K below the drain pads, and
     the four leads would carry 2–6 W of uncertain heat out of the FET row.
   - The guard holds tab = drain pad, so the lead heat is ≈ 0 whatever g is.
9. **Fit the board in the enclosure** exactly as in production: standoffs, nylon fixings (BRINGUP-PROBES table),
   harnesses dressed as built, lid closed. Route the TC harness out through the downstream edge (§4.1).

---

## 4. Instrumentation

### 4.1 Board thermocouples

- **Type:**
  - type K (or T), **40 AWG (0.08 mm), PFA-insulated, special-limits grade**, all from one spool;
  - welded bead ≤ 0.3 mm;
  - relative offsets are removed by the in-situ zero (§5, step 3), to ≤ 0.1 K.
- **Attachment:**
  - the bead goes into a ≤ 0.5 mm dot of thermally conductive, electrically insulating epoxy (Omegabond-101 class);
  - it sits on the solder fillet at the outer end of the terminal (2512 / 1206 / R5), or on the soldermask over the
    copper (copper points);
  - the first 15 mm of lead lies flat on the board along the local isotherm, tacked with one 3 × 5 mm patch of 25 µm
    polyimide tape that is not over the bead;
  - the lead then leaves along the board's downstream direction.
  - Solder is not used, so the same harness can later go onto HOT pads in (c).
- **Placement:**
  - photograph each bead with a scale and record its actual (x, y) to ±0.3 mm (`tc[].x_mm/y_mm`);
  - the fit's placement term is the model's own temperature spread within ±0.5 mm of the site (or across the pad);
  - the dominant placement terms are at R12 (±1.1–1.6 K) and LAM_R5.4 (±1.3 K) (§6.3).
- **Harness:** the summed TC wire cross-section in any face gap stays ≤ 1 % of the gap's cross-section. No wire crosses
  upstream of a site.

**Sites** (`results/sites.json`; model / KiCad frame, mm, y down; the net is from the s48 copper):

| Site | Cluster | x, y | Layer | Net | Why |
|---|---|---|---|---|---|
| LAM_R5.4 | C1 | 38.5, 15.5 | F | hv_ret | laminate 1 mm block, binding at 22 / 28 A |
| R12.1 / R12.2 | C1 | 44.6, 9.44 / 15.36 | F | leg_a-out_l / gate_l | 2512 terminal, binding at 24–28 A |
| R10.1 / R10.2 | C1 | 62.6, 9.44 / 15.36 | F | leg_a-out_h / gate_h | 2512 terminal, binding at 18–20 A |
| R20.1 / R20.2, R18.2 | C1 | 22.5 / 4.5, 9.44–15.36 | F | leg_b gate nets | 2512 terminals |
| R5.1 | C1 | 38.5, 10.0 | F | leg_ret | R5 current terminal |
| FETROW_B | C1 | 44.5, 19.5 | B | sw_b | FET-row copper on the solder side (binds top-only flow) |
| Q2S_F / Q2S_B | C1 | 73.5, 7.5 | F / B | sw_a | bus / BR1 edge, both faces (the In2 hot spot at 73.5, 4.5 is inner) |
| TANK_T1.1, J2.1, J5.1 | C2 | 140.6, 98.5; 132, 85.5 / 70.5 | F | sw_a; coil terminals | tank path |
| BANK_C152.1, BANK_C21.2 | C2 | 163, 111.5; 190.5, 53.2 | F | res_a; sw_b | bank column |
| C40.2, U26.21 | D | 39.2, 28.2; 115.4, 81.05 | F | hv_ret; n_ls | diagnostics (U26: bead on the body top) |
| Q2.2, Q3.2, Q5.2, Q6.2 | G | drain-pin fillets | B | bus_p / sw_a / bus_p / sw_b | **guard pairs** with a TC on each FET tab |
| tab Q2–Q6 | G | TO-247 tab, exposed metal above the clamp | — | drain | tie temperature |
| sink | — | sink base between Q3 and Q6 | — | — | guard-heater loop |
| leads | tie | supply leads, 20 mm from each joint | — | — | supply-cable tie |

### 4.2 Air temperature

- **Probes:** shielded fine-wire beads, 40 AWG K, each centred in a 4 mm bore × 15 mm polished-aluminium (or
  aluminized-Mylar) tube with its axis along the local flow.

| Probe | Where | Use |
|---|---|---|
| A1 | Enclosure intake | Inlet air; the 0.6–0.7 W/m²K per K credit for kitchen air (airflow28 §5.2) |
| **A2 / A3** | **Hot-corner leading edge, 5 mm above the top face / 5 mm below the bottom face, at the flow's entry to the FET-row region** | **T_air,ref = mean(A2, A3): B3's bay** |
| A4 / A5 | Mid-board (x 125, y 60), top / bottom | Pickup along the board (2–5 K expected, §5.3 there) |
| A6 / A7 | Exit of the tank path (x 195, y 100), top / bottom | Whether the flow reaches the tank path |
| A8 | 5 mm off C40's side, 9 mm high | Measured film-cap air → `film_air_rise_k` (B3's +15 K rule) |
| A9 / A10 | S18's TC2 (5 mm off PS2's long side, 12 mm high) / TC3 (bay, ≥ 50 mm from parts) | PS2 local-air rule (S18); `module_air_rise_k` |

### 4.3 Velocity

- **Instrument:** a thermal (hot-wire or hot-film) anemometer, ≤ 6 mm head, 0.1–20 m/s, ±(3 % + 0.05 m/s) class.
- **Fixed reference probe:** one stays in the inlet duct for every run, as the day-to-day repeatability check (±5 %).
- **Traverses:** before the h runs, never during them, because the probe blocks the gap:
  - 5 points across the flow × 2 heights in each face gap, at the hot-corner entry, at mid-board and at the tank path;
  - record the mean and the turbulence intensity.
- **What they are for:** documentation, the flat-plate cross-check against `delivery.py`'s `parallel_flow_alternative`
  (turbulent 0.037 Re^0.8 Pr^1/3; laminar 0.664 Re^0.5 Pr^1/3), and evidence that the flow reaches the tank path and
  J1. **Not a release quantity.**
- **Inlet Δp:** a differential-pressure sensor across the inlet / filter (SDP810 class) sets the clogged-filter
  condition.

### 4.4 Power

| Quantity | Instrument | Into the fit |
|---|---|---|
| I (loop) | 50 A / 50 mV shunt, 0.1 %, 4-wire; a 6½-digit DMM or a logger channel at ≥ 1 Hz | `i_dc_a`: every A4 case at (I / I_ref)² |
| V_R5 (Kelvin, ≈ 28 mV at 28 A) | DMM | `p_r5_w` = V_R5 · I |
| V_loop (BR1.1–BR1.4 Kelvin) | DMM | Loss check: V·I − I²·R_offboard against the model's hot-copper loss |
| Each bank link's current | DC clamp meter (±1 % at 5 A) | Split check: each within ±15 % of I / 5 (A4 assumes equal shares) |
| Guard heater V·I | Supply readback | Record |
| D-18 drive (PWM duty), tach rpm, V, I; face fan likewise | Logger / controller telemetry | Condition record |

### 4.5 Logger and the hazardous-voltage rule

- **In (b1) nothing on the board is above 1 V:** no mains, no bias, and J1 is capped. The logger choice is set by
  (c), which reuses the harness.
- **Why (c) is hazardous.** S18 §6 says PS2 is at hazardous voltage on every pin (pins 1 and 2 are mains, and the output
  is HOT-referenced with no PE bond), and it calls for insulated fine-wire K thermocouples and an isolated logger, or
  IR through a port. BRINGUP-PROBES says HOT domains float at bus / switch-node potential.
- **The logger for (c), and therefore here:**
  - every channel isolated, channel to channel and channel to earth;
  - a working-voltage rating of at least twice the 287.6 V OVP band top;
  - battery-powered or fibre-linked to the PC;
  - check its ratings on its own datasheet before (c).
  - D-8's equipment table lists "isolated temperature measurement" as a prerequisite.
- **The TC wire's PFA and the epoxy dot are functional insulation, not a barrier.** In (c), treat the harness and the
  logger as HOT: enclosed, no touching while energised, and connected or disconnected only with the bus proven dead
  (D-8 meter procedure).
- **Site classes for (c)**, by net:

| Class | Nets | Sites | In (c) |
|---|---|---|---|
| Line-frequency only | hv_ret, leg_ret, bus_p, n_ls | LAM_R5.4, R5.1, C40.2, Q2.2 / Q5.2, U26 | Isolated TC |
| 17 V HF swing on leg_ret | leg_a / leg_b low-side gate nets | R12.x, R20.x | Isolated TC, if the logger's CMRR is shown on a dummy channel |
| Switch node / HS gate / tank node: 0–170 V at 35–60 kHz, 50 V/ns edges; res_a ≈ ±255 V at 35 kHz | sw_a, sw_b, leg_*-gate_h / out_h, res_a | R10.x, R18.2, FETROW_B, Q2S, T1.1, the bank, Q3 / Q6 tabs | Fibre-optic (GaAs) probes or IR through a port only |

---

## 5. Bench day: step list

Times are wall-clock estimates. Each run is one steady state. At 28 A the board loss is about 15 W in diag1 (14.2 W hot copper plus R5 and the
links, h 16).

1. **Pre-checks (30 min).**
   - All 4-wire resistances recorded.
   - The logger reads every TC.
   - The anemometer is zeroed.
   - The shunt is checked against the DMM at 10 A.
   - `python3 -I bench_h_fit.py sites` prints the site table for this board revision.
2. **Plan the current (5 min).** Fill `RUN.json` with the condition and the expected air, then run
   `bench_h_fit.py plan --run RUN.json`.
   - Choose I so the predicted peak is ≤ 100 °C at the lowest h expected.
   - diag2 carries the two high-resistance half-paths (sw_b_high 6.54 mΩ and sw_a_low 6.37 mΩ at 20 °C, against sw_a
     3.75 mΩ in diag1). At the same current it runs much hotter: 24 W and 143 °C at 28 A / h 16, against diag1's 15 W
     and 82.5 °C.
   - **Guide:**
     - diag1: 28 A down to h ≈ 16;
     - diag2: ≈ 20 A at h 16, 24 A at h ≥ 25;
     - in 55–61 °C chamber air, about 4 A less.
3. **In-situ zero (overnight, ≥ 90 min accepted).**
   - Everything off, the enclosure covered against drafts, reference: A10.
   - Accept when the reference drifts ≤ 0.1 K/h over the last hour. The per-TC offsets go into `RUN.json`.
   - The airflow-r1 kit's `fit.py zero` rule is the same: a blower-on zero is not isothermal.
4. **Set the condition.**
   - Set the fan drives (D-18 PWM, face fan) and the inlet restriction (Δp target) for the condition (§8).
   - Record the tach readings.
   - Take one anemometer traverse, then remove the probe and keep only the duct reference.
5. **Ramp the current** at ≤ 5 A/s to I.
   - DC saturates T1; a slow ramp keeps the secondary transient on its burden small.
   - Never interrupt the current with the strap or a jumper: switch off at the supply.
6. **Guard null.**
   - Trim the sink heater until mean(T_tab − T_drain-pad) is within ±1 K, and each FET within ±2 K.
   - Expect 60–150 W, depending on the sink branch's drive.
7. **Steady state: the run is accepted when, over the last 10 min** (after reduction it also needs χ²/dof ≤ 2, the
   per-site h within ±8 % of the fit, and the loss check within ±3 %):
   - every C1 / C2 TC has |dT/dt| ≤ 0.02 K/min;
   - T_air,ref is stable to ±0.2 K;
   - I is stable to ±0.1 %;
   - the guard null holds.
   Expect 45–75 min per condition, set by the sink.
8. **Record a 10 min mean** of every channel, plus V_R5, V_loop, the bank-link currents, the heater power, the fan
   telemetry and the room conditions, into `RUN.json` (format: `runs/plan-diag1.json` plus the `tc` list; §6.1).
9. **Optional lead calibration** (once per enclosure).
   - Offset the guard by +10 K and −10 K, 30 min each.
   - With h fixed from step 8, the change at the drain pads fits the drain-lead g directly: B3's 0.020–0.280 W/K is
     otherwise unmeasured. Use `lead_g` in `RUN.json` and a fit at fixed h.
10. **Next condition:** change one thing at a time. The order within a day is in §8.
11. **Re-seat check** (once per enclosure).
    - Remove the board, refit it and repeat the nominal condition.
    - The two fits' difference is the mounting scatter (§6.3).
12. **Swap the jumpers** for the other diagonal (half a day) and repeat the nominal condition.
13. **Reduce.**
    - `bench_h_fit.py fit --run RUN.json` for each run;
    - `fit2` for the nominal runs (face split);
    - `verdict` over the set (§7).
    File the `RUN.json` files, the `fit-*.json` files and the photographs.

---

## 6. Data reduction: backing out h with B3 itself

### 6.1 The forward model (`bench_h_fit.py solve`)

The B3 hot-copper body-level solve, `body_runs.run_case` from the snapshot, exactly as run_basis calls it:

- **Copper heat:** the configuration's A4 cases at (I / I_ref)², times `cu_scale` when the loss check calls for it,
  solved as the hot-copper fixed point at the measured T_air,ref. At 28 A that is 12.09 W at 20 °C and 14.2 W hot at
  h 16 (×1.17).
- **Part heat:**
  - R5 at the measured V_R5·I;
  - every other heat row at 1 µW. Zero would drop the part's network node and its body-to-air path, so the bench model
    would no longer have B3's operating structure.
  - `part_watts` can add any deliberate bench heater.
- **Bench hardware as nodes** (`attachments`):
  - each jumper and bank link is a node carrying its measured I²R, tied to both pads by its Wiedemann–Franz conductance
    L0·T / R;
  - each supply lead is a fixed-temperature tie at its lead TC (g = kA / 20 mm).
- **FET drain leads:** run_basis's `LeadLink`, to the **measured tab temperatures**.
- **h:** uniform on both faces and every body (run_basis's knob). `film_air_rise_k` / `module_air_rise_k` come from A8 /
  A9 minus T_air,ref (default 0 under forced flow).
- **Sampling:** a pt site is the mean over a 0.75 mm-radius bead footprint; a pad site is the pad-copper area mean.
  Both are read at T_air,ref + rise.

**Sanity (plan, diag1, 28 A, 25 °C air, tabs 60 °C):**

| h | Peak (1 mm block) | LAM_R5.4 | R12.2 | R10.2 | FETROW_B |
|---|---|---|---|---|---|
| 16 | 82.5 °C at (38.5, 15.5) F | 82.5 | 75.0 | 67.7 | 81.0 |
| 31 | 68.8 °C at (38.5, 15.5) F | 68.8 | 61.1 | 53.2 | 66.2 |

- The bench peak is the same block as the operating c28 binding row.
- Rises over the air run 25–57 K, so TC errors of 0.3 K are 1 % of the signal.
- T1.1 / J2 rise 21–33 K, so the tank path can be fitted too (cluster C2).

### 6.2 The fit (`bench_h_fit.py fit`)

1. **Clusters.** Fit cluster C1 (the FET-row / R5 strip: LAM_R5.4, R12, R10, R20, R18, R5.1, FETROW_B, Q2S_F / B) for
   the release h; fit C2 (tank path) separately.
2. **Solve.** Solve at 0.7, 1.0 and 1.4 × the expected h, at 0.5 mm.
3. **Interpolate.** Each site's T is a quadratic in x = 1/h, through the three solved points nearest the estimate.
   Rises go nearly as 1/h.
4. **Fit.** h is the weighted least-squares zero over the cluster:
   - σ_i = √(σ_TC² + placement_i²), where placement_i is the model's own spread at the site;
   - re-solve at the estimate until it is bracketed and within 3 % of a solved point (2–4 extra solves at about 25 s
     each).
5. **Re-fit on 0.25 mm.** Three solves at 0.88 / 1.0 / 1.14 × h, about 5 min each. That fit is the result, and
   |h(0.25) − h(0.5)| is the mesh term.
6. **Statistics.** σ_stat comes from the χ² curvature, inflated by the Birge ratio √(χ²/dof) when > 1.
7. **Systematics.** Each is one perturbed 0.5 mm solve at the fitted h, re-fitted (the table in §6.3).
8. **Result.** `h`, `U95` = 2·√Σu², `h_L95` = h − U95, per-site h and residuals, χ²/dof, and the loss check.
9. **Face split** (`fit2`, a diagnostic):
   - h_top (the whole top face and every body) and h_bottom, linearised about the uniform fit, from three 0.25 mm solves;
   - if the split is significant (> 2 σ), judge the step with B3 at (h_top, h_bottom), not with the uniform ladder:
     `airflow_search.py point --mode top --cases c<N>_h<h_bottom>_jet<h_top>@<air>`, region = whole outline;
   - the ladder assumes equal faces, and airflow28 §4.1 shows that a W/m²K on the bottom is worth about 0.75 of one on
     the top;
   - its resolution is coarse (§6.3).
10. **Jets route.**
    - Fit the base h with the jet bleed capped (jets off, `mode: uniform`).
    - Then, with the jets on, fit the jets' h_top on `JET_REGION` at that fixed base: `mode: jetfit`, `h_base` = the
      jets-off fit; the swept h is h_top.
    - **The in-situ h_top is weakly resolved.** At base 16 / diag1 / 28 A, h_top 60 → 100 moves LAM_R5.4 by only
      70.4 → 63.7 °C, about 0.17 K per W/m²K, and the peak moves to the In2 bus edge (68.5, 6.5)
      (`runs/plan-jetfit.json`).
    - **So the airflow-r1 guarded plate is the primary h_top instrument.** Its `fit.py` measures h_top directly; use
      its h only, not its verdict (§11). The in-situ fit is the cross-check.
    - **If the measured h_top is below 100,** the base requirement rises. Re-solve it with
      `airflow_search.py point --mode jetmix --cases c28_h<base>_jet<h_top>@<T>`.
11. **Transfer to operation** (`transfer_to_operation`). A room-temperature fit becomes h_op = h_bench × F, with F the
    fixed-velocity property ratio k ν^−0.8 Pr^1/3 (turbulent; Incropera A.4):
    - **F = 0.935** for film 45 → 85 °C and **0.92** for 45 → 95 °C;
    - laminar it would be 0.995, so the turbulent F is the conservative one;
    - F is applied to the whole fitted h, radiation included. Radiation rises with temperature (about 6.4 → 9.5 W/m²K ×
      view factor), so this is conservative too.
    - A run made in hot inlet air (§8, HOT55 / HOT61) replaces F with the measured ratio.

### 6.3 Uncertainty budget

`bench_h_fit.py selftest` makes synthetic bench days with a known truth:
- the truth is solved at 0.25 mm with model settings **the fit is not told**: the drain-lead g at a drawing extreme,
  attachment g ×1.3, film air +1 K, a guard error of ±0.5 K;
- measurements = truth + bead placement (uniform within the site's spread) + TC noise N(0, 0.3 K) + a common offset
  N(0, 0.1 K) + air-reference error N(0, 0.2 K) + tab-TC noise N(0, 0.3 K) + V_loop noise 0.3 %;
- the fit then runs exactly as on a bench day.

Files: `results/selftest-st2_face31_diag1.json` and `results/selftest-st2_base16_diag2.json`. The face-split
diagnostic is `results/fit2-st2_face31_diag1-C1.json`.

| Term (1 σ, W/m²K) | Face flow: truth 31, diag1, 28 A, 25 °C | Base flow: truth 16, diag2, 20 A, 25 °C | How it is held down |
|---|---|---|---|
| Statistical (12 C1 TCs, placement, Birge) | 0.25 (0.8 %) | 0.08 (0.5 %) | 12 sites. Photographed bead positions (`tc[].x_mm/y_mm`) move the model sample to the bead |
| Mesh (0.25 vs 0.5 mm fit) | 0.08 (0.3 %) | 0.09 (0.6 %) | Final fit on 0.25 mm |
| Copper loss (±1.5 % with V_loop; ±3 % without) | 0.50 (1.6 %) | 0.31 (2.0 %) | Kelvin V_loop at the BR1 pads; the loss check ratio was 1.002 / 0.995 |
| Drain-lead g over the drawing range 0.020–0.280 W/K, at a ±0.5 K guard | 0.71 (2.2 %) | 0.17 (1.1 %) | **The sink guard.** With the guard ≈ 20 K off (v1 below) this term is the error |
| Tab TC offset +0.5 K | 0.23 (0.7 %) | 0.10 (0.6 %) | Tab and drain-pad TCs from the same spool, zeroed together |
| Bench attachments (WF g ×0.5 … ×1.5) | 0.19 (0.6 %) | 0.00 | Short links measured 4-wire |
| Film / module air rise ±1.5 K | 0.19 (0.6 %) | 0.10 (0.6 %) | A8 / A9 measured |
| Air reference ±0.3 K | 0.56 (1.8 %) | 0.20 (1.3 %) | A2 / A3 shielded, zeroed in situ |
| TC common offset ±0.2 K | 0.37 (1.2 %) | 0.13 (0.8 %) | In-situ zero |
| **U95** | **2.37 (7.5 %)** | **0.92 (6.0 %)** | |
| **Recovered vs truth** | **31.59 vs 31.0** (+1.9 %, inside U95), χ²/dof 0.72 | **15.42 vs 16.0** (−3.6 %, inside U95, 1.3 σ), χ²/dof 0.67 | |
| C2 (tank path) fit, 0.5 mm | 30.7 ± 0.9 (1 σ) | 15.0 ± 0.5 | Separate cluster |

- **Sensitivity:**
  - at h 31, every C1 site moves 0.41–0.64 K per W/m²K, on rises of 15–46 K;
  - at h 16 (diag2, 20 A) it is 1.35–1.66 K per W/m²K on rises of 35–53 K.
  - That is about 2× the 1/h scaling: hot copper adds to it.
- **The per-site h agree** within ±4 % in both cases (30.4–32.5 and 15.1–15.8). A site outside that band on a real
  bench is a TC problem or a non-uniform flow.
- **Face split (`fit2`, linearised, 3 solves on 0.25 mm, about 4 min):**
  - for the face-flow case it returns h_top 30.3 ± 2.4 and h_bottom 33.4 ± 3.8, with correlation −0.99;
  - the split is 0.5 σ, so not significant.
  - **The C1 thermocouples cannot separate the faces finely** (the 1.6 mm board couples them; airflow28 §4.1). The
    diagnostic catches only gross asymmetry, such as a top-only flow (47 / 10). The bottom-face TCs (FETROW_B, Q2S_B)
    carry what resolution there is.
- **What happens without the guard (selftest v1, `results/selftest-v1-guard-unconverged.json`):**
  - the synthetic guard was set once from a far first guess, which left the tabs about 20 K below the drain pads at
    g_lo, and diag2 ran at 28 A (143 °C peak);
  - the fit read 14.3 against a truth of 16 (−10 %);
  - χ²/dof was 3.1, and the drain-lead term rose to 1.7 W/m²K;
  - **χ² flags it.** The acceptance limit is χ²/dof ≤ 2 (§5, step 7; §6.2).

**Not in U95.** These are carried by the design margin, the sample plan or (c):
- **unit-to-unit and re-seat scatter:** measured in §8 and used through the minimum, or the tolerance bound, over units;
- **the property transfer** room → operation: F 0.92–0.94, conservative, and replaced by the HOT55 / HOT61 measured
  ratio;
- **the structural transfer** from DC copper heat to operating heat: no gate-resistor heat on the bench, and a
  switching-loss distribution that differs from the B3 basis. That is the ×1.2 / ×1.25 of gate B, confirmed per step by
  (c).

---

## 7. Pass / fail per ladder step, and the firmware ceiling for each measured h

**Inputs for each enclosure unit:**
- **h_nom:** the fit at the nominal condition (clean filter, new fans, the drive the fan law holds at that step,
  product orientation). For a room-air run, transferred by F.
- **h_L95,worst:** the lowest h_L95 over that unit's degraded conditions (clogged filter, aged fan, the minimum drive
  allowed at the step, the worst allowed orientation), transferred.
- **T_air,worst:** the hot-corner leading-edge air in the enclosure's worst qualified operating case: kitchen 40 °C, the
  D-18 50 °C hood basis, at the ceiling under test. It comes from the enclosure soak, not from this bench.

**Step N passes when both gates hold:**
- **Gate A:** h_L95,worst ≥ h_req(N, T_air,worst). The measured lower bound clears the solved minimum in the worst case.
- **Gate B:** h_nom ≥ m × h_req(N, T_air,worst), with **m = 1.2** for face flow and **m = 1.25** on the base h for jets +
  base. This is the design margin. It covers what a measurement on n units does not:
  - the production spread beyond the units tested;
  - the R_on 0.217 W heat-basis bound and the B3 structural transfer from DC copper heat to operating heat;
  - dust between filter services.
  Airflow28 justified the factor by the correlation spread. With a measured h that term is gone, but these remain.
- **Across units:** apply both gates to the lowest unit.

**The firmware ceiling is the highest step whose gates both pass, with no skipped step.** At 61 °C T_air,worst (at
55 °C use the second line):

| Measured (transferred) | h_L95,worst ≥ | and h_nom ≥ | Allowed `TANK_CEILING_DA` |
|---|---|---|---|
| — | — | — | 175 (still air, ships) |
| 18 A | 11 (10) | 13.2 (12.0) | 180 |
| 20 A | 13 (11) | 15.6 (13.2) | 200 |
| 22 A | 17 (14) | 20.4 (16.8) | 220 |
| 24 A | 20 (17) | 24.0 (20.4) | 240 |
| 26 A | 25 (22) | 30.0 (26.4) | 260 |
| 28 A, face flow | 31 (27) | 37.2 (32.4) | 280 |
| 28 A, jets + base | base 16 (12), with the jets' h_top ≥ 100 measured | base 20 (15) | 280 |

`bench_h_fit.py verdict --fits <nominal>,<worst...> --air-op <T> [--route jetmix]` prints this for a set of fits
(or use `--h-nominal / --h-l95-worst`).
- **The jets route** is solved at 28 A only. B3 is monotone in the tank current at fixed airflow and air, so a jets +
  base set that passes 28 A passes every lower step.
- A set that does not pass 28 A falls back to the no-jet column for the lower steps.

**Then, per COMMISSIONING gate 0** ("the hot-copper B3 basis re-run at the airflow fitted"):
- run `run_basis.py --cases c<N>_h<floor(h_L95,worst)>@<T_air,worst>` on the board of record, or
  `airflow_search.py point --mode jetmix --cases c<N>_h<base>_jet<h_top>@<T>` for the jets route;
- it must PASS before the reviewed change sets `TEMPER_POWER_TANK_CEILING_DA` = 10 N.
- The ladder table is the search result. The gate run on the fitted value is the evidence that goes in the record.

**Firmware conditions that come with any step above 17.5 A:**
- **The fan drive at that ceiling is pinned at or above the lowest drive whose measured h passes the step.** The fan
  law (`thermal_mgmt.h`, PI on sink 88.6 °C / coil 140 °C) must not command less while the ceiling is above 17.5 A.
- **A face fan needs its own tach and stall detection,** clamping the ceiling to 17.5 A as the blower's stall cap does.
  It acts within seconds; the board's time constant is minutes.
- **The firmware measures no air temperature.** The column used must be the qualified worst case, and a product
  condition with board air above 61 °C (§8, the 78 °C stacked bay) grants nothing above 17.5 A.
- **Each other gate of the step still applies** (bank ΔT, coil, switching loss, trips, pickup, loop: COMMISSIONING 1–7).
  This procedure closes gate 0's airflow input only.

---

## 8. Sample plan

**Units.** h belongs to the enclosure, its air movers and the board's fitted geometry, not to the board's copper. The
spread comes from the enclosure build (gaps, seals, board height on its standoffs), fan unit-to-unit variation and
harness dressing.
- **The TTV:** one board, moved between enclosures.
- **For release:** at least **3 enclosure + fan sets** (production-intent parts, independently assembled), with gates A
  and B applied to the lowest unit.
- **If the unit-to-unit spread (max − min) / mean exceeds 10 %:** extend to n = 5 and use the one-sided 90 % / 95 %
  normal tolerance bound in place of the minimum: mean − 3.41 s at n = 5, mean − 2.36 s at n = 10.
- **(c) confirmation:** 2 production units.

**Conditions** (each one steady state; diag1 unless noted):

| # | Condition | Unit 1 | Units 2–3 | Notes |
|---|---|---|---|---|
| N0 | Nominal: product orientation, clean filter, new fans, the drive the fan law holds at the step | diag1 **and** diag2, plus a re-seat repeat | diag1 | Sets h_nom. diag1 / diag2 agreement checks the jumpers. Re-seat gives the mounting scatter |
| F1–F3 | D-18 drive at floor 0.458 / 0.55 / 1.0 (and the face fan at min / nominal / max if separate) | ✓ | min only | Gives h(drive), so the firmware's minimum drive per step can be set |
| CL | **Clogged filter:** the inlet restricted to the enclosure's end-of-service filter Δp (if none is specified, 50 % of the inlet area blocked with mesh, and flag it) | ✓ | ✓ | |
| AG | **Aged fan:** the supply trimmed to −15 % rpm at the same command, each fan (or the fan maker's end-of-life spec) | ✓ | ✓ | |
| CL+AG | Both, at the minimum drive allowed at the step | ✓ | ✓ | **Sets h_L95,worst** |
| OR | Orientation: the installed one, plus the extreme the installation instructions allow (or inverted), at the minimum drive | ✓ | — | Base flow near 2 m/s has Ri ≈ Gr/Re² ≈ 0.08–0.12, so buoyancy is worth up to about 10 %. Release uses the lowest allowed orientation |
| HOT55 / HOT61 | Inlet air heated to 55 / 61 °C (chamber or heated inlet duct), at N0 and CL+AG, current reduced to about 22 A | ✓ | HOT61 at N0 | Replaces the property transfer F with a measured ratio. Records A8 / A9 (the cap and PS2 +15 K rules) |
| HOT78 | **The 78 °C stacked bay** (S18; airflow28 §5.2) | ✓ | — | **No ceiling can be granted:** B3 is not solved above 61 °C, and PS2's local air is 93 °C there (over its 85 °C) at any h. Measure h(78 °C) and the PS2 local air (S18 TC2 position) to settle whether the stacked case is reachable at the board; that is the owner's decision (§11) |
| J0 / J1 | Jets route only: bleed capped (base h) / jets on (h_top) | at N0, F1, CL+AG | N0 | |

**Time.** About 1.5 days for unit 1, at 45–75 min per steady state plus the overnight zero; about 0.5 day each for
units 2–3. One TTV.

---

## 9. Confirmation in operation (method c), at each step after it is allowed

- **The run.** At step N: 30 min at N A on the worst pan of COMMISSIONING gate 7, with the airflow at the condition
  under test. Isolated TCs only on the line-frequency sites (LAM_R5.4, R5.1, C40.2, Q2.2 / Q5.2), and R12 / R20 if the
  CMRR is shown; fibre-optic probes or IR for anything on a switch node (§4.5). Log the line and tank currents, the
  sink and the air (A2 / A3).
- **The inversion.** Use B3 itself: the c<N> case built as run_basis does, with the measured I_t (1.05 × N, or the
  measured half-cycle RMS), I_line, tab temperatures and air, and the bench h. Compare the measured LAM_R5.4 / R5.1 /
  C40.2 / R12 against the model.
- **Pass:** every measured site ≤ the model + 2 K (the TC and placement terms). Equivalently, the h inverted from (c) is
  ≥ h_bench − U95.
- **A miss** means the operating heat is larger than B3's (R_on, gate charge or bank). The bench h stands, but step N
  is withdrawn until the heat basis is corrected. That is the ×1.2 margin being used, and it must be recorded.
- **S18 and S2.** S18's PS2 checks (TC1–TC4, output ≤ 7.1 W) and S2's "bay air and board copper at R5" belong to this
  run, not to (b1), where PS2 is unpowered.

---

## 10. Safety

- **(b1):**
  - ≤ 6 V compliance, 30 A, no mains (J1 capped), no bias;
  - the supply leads are rated for 50 A;
  - switch the current off at the supply, never at a jumper;
  - guard heater at ≤ 60 V, with a 120 °C bimetal cut-out on the sink in series with it;
  - never let the board exceed 110 °C (stop at 105 °C on any TC).
- **Chamber runs:** the board limit holds at hot air; use the reduced current (plan step).
- **(c):** the D-8 / BRINGUP-PROBES rules apply in full (isolated or differential probes, no floating scope, PE-bonded
  enclosure, bus proven dead before touching). A TC harness on a HOT pad is a HOT conductor.

---

## 11. Records that conflict with this procedure, or that it changes

1. **The ladder is on s47; the board of record is s48.**
   - airflow28 solved every bracket on s47 (83355da5, copper key 387b3e2d).
   - DECISIONS 67 made s48 (2b46d90e) the board of record. It added C176–C178, U3 heat copper and the EN dividers, and
     it re-based S21 with a new c28 still-air gap, U26 −0.5 K.
   - §2.1 re-solves the c28 brackets on s48 (unchanged: 31 / 27 face flow, 16 / 12 jets + base; control 0.0 K against the s48 chain run files).
   - The lower ladder steps were not re-solved. The gate-0 run on the fitted h (§7) is solved on the board fitted and
     closes that for each step.
2. **The record names a different release method.**
   - airflow28 §5.4 says "the release needs a measured h … from a heated-plate or IR bench, plus the board
     thermocouples DECISIONS 66 lists".
   - This procedure makes the B3 inversion on the real board (b1) the release evidence. A plate or coupon becomes an
     enclosure-development tool.
   - Reason: B3's h is a lumped model parameter. A smooth plate measures a different quantity, and the transfer is the
     uncertainty the bench is meant to remove (§1.2).
   - This should be recorded as a decision (DECISIONS) if adopted.
3. **COMMISSIONING.md gate 0 (lines 286–288) points the airflow route at `b3-ratings/ENCLOSURE-REQUEST.md`.**
   - airflow28 §8 calls that file's numbers cold-copper and pre-refine: it said "h 15 / 20 gives −27 / −42 K at R5.4",
     where hot copper moves the worst row 49 K between h 10 and h 25.
   - The section still quotes the s45 still-air numbers.
   - It names no measured-h evidence, no per-ceiling minimum fan drive and no face-fan stall clamp.
   - It should cite airflow28 §3 / §7 and this procedure's §7.
   - The "Precondition for any raise" list has the bench R_on reading but no bench-h item.
4. **OPEN-ITEMS S2 is stale.** It still says:
   - the s42 / DECISIONS 55 state: release ceiling 18.0 A, still-air ceiling 20.0 / 18.3 A;
   - "the board needs h_top 73 / 97 W/m²K at 28 A";
   - "no ceiling raise until the jet h is measured on the bench".
   On hot copper the release is 17.5 A (DECISIONS 61), and the jet strip alone does not carry 28 A at any h (S24).
   S24 corrects only S2(d) (U26). What is now needed is the board-face h of this procedure, plus the jets' h_top for the
   jets route.
5. **The airflow-r1 jet bench kit** (`sensor-c1-impulse-mining:output/temper-airflow-r1/bench/`, 343a72070) is built
   on the superseded strip-only, cold-copper requirement.
   - Its PASS line (h_top ≥ 97.2 at c28 / 61 °C) and its `fit.py` "ceiling the lower bound supports" (`ceiling_by_h`)
     come from `board-h-sweep.json`.
   - The guarded plate is still the right instrument for the jets' **h_top** behind the jets + base route's
     "h_top 100" (Martin × 0.6, used outside its Re range). **Its verdict table and ceiling output must not be used.**
   - Its J13 still names an 18 A loss-of-airflow clamp. The still-air release is now 17.5 A.
6. **The 78 °C stacked bay is outside the ladder** (S18 residual 2; airflow28 §5.2).
   - B3 is not solved above 61 °C, and PS2's local air is 93 °C there at any h.
   - The firmware measures no air temperature (`thermal_mgmt.h` has the sink, coil and rim sensors and the blower tach).
   - So the ladder can be applied only if the enclosure's qualification shows the hot-corner air ≤ 61 °C in every
     product condition the owner keeps. Otherwise B3 and PS2 must be re-based at 78 °C.
   - This is an owner decision. The bench's HOT78 run measures the data for it but grants nothing.
7. **The firmware has no second air mover.**
   - `thermal_mgmt.h` carries the D-18 blower's tach, stall detection and power cap.
   - airflow28's recommended route adds a 40–80 mm face fan. It needs its own tach and stall clamp to 17.5 A.
   - Because h depends on drive (§8, F1–F3), the fan law needs a per-ceiling minimum drive. Today it is PI on the sink
     at 88.6 °C and the coil at 140 °C, with no floor tied to the tank ceiling.
8. **The drain-lead path is a ×14 band in B3** that the operating basis carries at its central value.
   - `drain_lead_conductance` over the IPW65R018CFD7 drawing range spans 0.020–0.280 W/K (central 0.084); run_basis
     uses the central value.
   - The bench's sink guard makes the h fit insensitive to it.
   - Step 9 (±10 K guard offsets) can measure it on the real part stack, which would also tighten the operating B3
     basis at the binding FET row.
9. **S18's PS2 checks and S2's "bay air and board copper at R5" need a powered soak.**
   - S18 §6 calls for TC1–TC4 and the output-power log at the c17.5-equivalent operating point.
   - In (b1) PS2 is unpowered, so those checks ride on the (c) runs (§9), not on this bench.
   - The bench does measure the local air the +15 K film-cap / PS2 rule stands for, under forced flow (A8 / A9). That can
     confirm or retire the rule's conservatism; airflow28 §8 notes the rule is conservative under forced flow.
10. **The airflow28 requirement and this procedure use the same air.**
    - airflow28 §5.2 says B3's "bay" is "the air that reaches the board face", and the requirement is a pair, (h, air at
      the hot corner).
    - This procedure defines T_air,ref as the hot-corner leading-edge air (A2 / A3) and fits h against it.
    - The downstream pickup (2–5 K) is therefore inside h_eff, which is conservative.
    - The firmware column must use the same point's worst-case air from the enclosure soak. The intake air (A1) is not
      the same thing: the 0.6–0.7 W/m²K per K credit for kitchen air applies only if the measured A2 / A3 show it.


---

## 12. Files and reproduce

```
cd bench-h
python3 -I scripts/snapshot.py                       # snap/ from PS HEAD (refuses if PS paths are dirty)
python3 -I scripts/bench_h_fit.py sites              # results/sites.json
python3 -I scripts/bench_h_fit.py plan --run runs/plan-diag1.json
python3 -I scripts/bench_h_fit.py selftest [--only st2_face31_diag1|st2_base16_diag2]   # results/selftest-*.json
python3 -I scripts/s48_check.py                      # results/ladder-s48-check.json
python3 -I scripts/bench_h_fit.py fit  --run RUN.json        # results/fit-<run_id>-C1.json
python3 -I scripts/bench_h_fit.py fit2 --run RUN.json        # face split (after fit)
python3 -I scripts/bench_h_fit.py verdict --fits A.json,B.json --air-op 61 [--route jetmix]
```

- **`RUN.json`:** `run_id`, `config` (diag1 | diag2 | alt), `i_dc_a`, `p_r5_w`, `t_air_ref_c`, `t_tab_c` {Q2, Q3, Q5,
  Q6}, `tc` [{site, t_c, sigma_k}], optionally `v_loop_v`, `r_offboard_ohm`, `attachments`, `film_air_rise_k`,
  `module_air_rise_k`, `mode` (uniform | jetmix with `h_top` | jetfit with `h_base`), `h_guess`, `sigma_*`.
- **The attachment defaults are placeholders:** enter the measured link resistances.
- **Work files** (solve cache, heat files) are under `bench-h/work/`.
