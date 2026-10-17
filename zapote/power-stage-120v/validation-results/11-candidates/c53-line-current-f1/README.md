# Certifier provisions on the 20-board prototype: line-current sensing (entries 11, 13) and the F1 holder (entry 9)

Date 2026-10-16. This is a read-only desk study. I wrote files only to this folder. I ran no git, no layout build and no server, and contacted no one.

**Path shorthand**
- PS = `worktrees/ps-integrate/zapote/power-stage-120v`.
- FW = `worktrees/ps-integrate/firmware`.
- BOARD = `worktrees/runs-native21/s51/c51int/section.kicad_pcb`. This is board sha256 `0b0ebcf7…`, as stated in `barrier-gate-rust.json`.

**How the board was read**
- The geometry comes from BOARD through KiCad 10 python (`scripts/dump_fp.py` → `s51_fp.json`) and from the chain's `copper-dump.json`.
- My HOT/SELV classifier reproduces the chain's D5 figures exactly: HOT–SELV is **8.047 mm** and HOT–PE is **8.507 mm** (`scripts/barrier_map.py`).

**Two kinds of numbers**
- Numbers marked *(desk)* are estimates from `scripts/line_current_bounds.py`. They are not committed evidence.
- Stock and prices were read from DigiKey on 2026-10-16 unless marked otherwise.

## Summary

| | Recommendation | Change class | Size | What the bench learns |
|---|---|---|---|---|
| **A. Line current** | **Provide a hardware average-current trip on R5, in the HOT5 domain, as a fitted-or-bypassed footprint now.** Do **not** add the AMC1301 measurement or a CT/Hall sensor now: wait for the lab, or for the airflow ceiling raise. | Layout stage, power board only. No barrier crossing, J4 change, controller change or firmware pin. | 3 small ICs + ~9 × 0603 + a 0 Ω bypass, about 50–70 mm² of HOT5 F.Cu next to the OCP chain. The legal free area is fragmented (§A4), so this needs a placement pass. | (1) The trip point and its margin over the firmware hold, with no nuisance trips at a 13.5 A inlet bound. (2) A dry run of the abnormal test: firmware limit defeated, hardware latches before the cord sees more than 15 A. (3) The ratio of mean R5 current to true-RMS line current over the pan grid. Validating the firmware estimate (e_est) does **not** need any on-board sensor: an external power analyser does it (DECISIONS 2026-10-08 qualification). |
| **B. F1 holder** | **Wait.** Keep KLDR025.TXP in 2 × 01250003H clips for the prototype and ask the lab. No UL PCB-mount Class CC holder exists that fits, or that can be bought in quantity 20. If a layout stage happens anyway (for example A), optionally add a dual-population provision: tab holes under the fuse body so that F1 can be wired out to an off-board Class CC holder. | BOM-only today. The optional provision is part of the same layout stage. The fallback (panel or DIN holder) is an enclosure change in any case. | Holder options are 17.5–44 mm wide modules off-board. On-board, nothing beyond the 45.3 × 13.6 mm F1 slot is free. | Temperature rise of the clips and fuse at 15 A and at the 16.0 A continuous capacity, in the enclosure. Retention of the Class CC rejection end in a non-rejection clip. This is the data the lab will ask for on open clips. |

---------------------------------------------------------------------------------------------------------------------

## A. Hardware line-current measurement (entries 11 and 13)

### A1. How the 15 A limit is computed today (firmware only)

Sources:
- `FW/components/power/input_limits.c` and `include/input_limits.h`;
- `fullbridge_adapter.c`, `energy_supervisor.c`, `n21_binding.c`, `include/tank_freq.h`, `include/n21_signal.h`, `include/blower_aux.h`;
- PS `DECISIONS.md` lines 168–182 and 2043.

**Sensors.** There is no line-current sensor.
- `bus_v` comes from U4 AMC1311 (J4.11/12, ADC1 CH1, GPIO2).
- `tank_rms_a` comes from the T1 CST3015-200ED tank CT. ct_mon goes to J4.14, then GPIO1 / ADC1 CH0, plus the MCP3202 RMS channel.
- `cos_phi` is CT_ZC (J4.13 → GPIO38 capture) measured against the PWM edges.
- `line_rms_v` is derived from the unsmoothed bus peak (`n21_line_rms_from_bus_peak`). Taking the rectifier drop as 0 makes it read conservative.
- Valid inputs: 8 to 48 samples per half line cycle, time-weighted (625 µs slots), with V_line between 100 and 140 V.

**Formula, evaluated per half line cycle.**
- P_inv = mean(0.9003 · V_bus · I_tank,rms · cos φ). The 0.9003 factor is 2√2/π. The mean is floored at 0.
- I_ps = P_inv / η_min / V_line, with η_min = 0.93.
- inlet_bound = I_ps · (1 + e_est) + I_aux, with e_est = 0.10 (provisional).
- I_aux = the blower-scheduled allowance, between aux_min 0.26 A (PS2 + PS3 logic) and aux_max 0.887 A (blower at full). If the allowance is stale or invalid, the firmware uses 0.887 A.

**Limits on that bound.**
- `fullbridge_adapter` and the tank_freq loop **regulate** inlet_bound ≤ `inlet_target_a` = 13.5 A (`n21_binding.c:15`).
- `energy_supervisor` **trips** at `inlet_max_a` = 15 A (`energy_supervisor.c:27,106`).
- So the power stage is held at (13.5 − I_aux)/1.1 = **11.47–12.04 A**, and the firmware trip comes at (15 − I_aux)/1.1 = **12.83–13.40 A** of *estimated* I_ps.
- The checklist quotes "hold 11.1 A, trip 12.45 A". Those figures are the 2026-10-08 values with I_aux = 1.3 A. The code now uses 0.26–0.887 A.

**Every element is firmware.**
- The sampling, estimate, regulation and trip all run on the ESP32-S3.
- The trip acts through `ctrl_run_en_kill` / RUN_EN (GPIO14).

### A2. What hardware limits line current if the firmware limit is defeated *(desk)*

The bridge's hardware trips are:
- the tank-CT comparators: **70.18 A nominal, band 64.55–76.09 A peak** (DECISIONS 551, 851; FAULT-INTERFACE's "≈55 A" is stale);
- the R5 shunt OCP: band 67.7–116.4 A peak (Kelvin gate).

Both are peak trips. Neither limits RMS line current.

Assume a stage held just under the CT trip's low corner, with an |sin| envelope (`scripts/line_current_bounds.py`, output in `line_current_bounds.txt`):

| Pan R_eq | Line current at 64.55 A peak | at 70.18 A |
|---|---|---|
| 1.58 Ω (the "28 A for 1239 W" pan) | 14.7 A | 17.4 A |
| 1.92 Ω (pooled pans, 931 W at 22 A) | 17.9 A | 21.2 A |
| 2.5 Ω | 23.3 A | 27.6 A |

So with the firmware limit defeated, hardware allows roughly **15–28 A** depending on the pan. F1 (25 A, time-delay) does not open in that range (finding #11). This is the case the lab's abnormal test would produce.

### A3. Options

| | Hardware average-current trip on R5 (**recommended**) | AMC1301 on R5 → controller (S13 / temper-8d) | CT or Hall sensor on the AC line | Off-board wire-through CT on the inlet L lead |
|---|---|---|---|---|
| What it is | An inverting zero-drift integrator reads R5's Kelvin signal (ocp_kelvin_n against ocp_kelvin_p, which is HOT5 ground), averaged over ~1 s. A TLV3201 compares it against a ref25 divider. A 2-input AND (SN74LVC1G08) combines it with U6's OCP_OK into U8. | A reinforced isolated amplifier on R5 with a differential output to the controller ADC. | A line-frequency CT on ac_l_in / l_f, or an isolated Hall IC. | A CT on the L wire between the inlet and J1. The secondary is wired to the controller. |
| Hardware trip or measurement | **Hardware trip.** It latches through the existing BUS_FAULT → interlock → PERMIT path, with reset by RESET_N. It needs no firmware, so the "15 A line-current limit: firmware only" row of entry 13 becomes "firmware regulates, hardware backstop". That is the same pattern as the thermal rows (CTRL DECISIONS C6). | **Measurement only.** Firmware still regulates and trips, so it does nothing for entries 11 or 13. If the lab defeats firmware, it is defeated too. | Measurement, unless a trip is added on the SELV side. | Measurement. |
| What it sees | The power stage only. R5 carries the whole bridge current, and the DC-link caps C5/C6/C38–41 return to hv_ret on the rectifier side of R5. PS2 (tco_l) and PS3 (F2, l_filt) tap ahead of BR1. | The same as the trip (power stage only). | The total inlet current, if placed on ac_l_in. | The total inlet current. |
| Nets touched | ocp_kelvin_n (tap at R33, (119.1, 71.0); the Kelvin trace already runs there from R5 (38.5, 12.6)); ocp_kelvin_p; hot5; ref25; ocp_ok_hot (cut between U6.1 and U8.1). | ocp_kelvin_n/p and hot5 on the HOT side; selv_gnd, v3v3 and 2 new outputs on the SELV side. | ac_l_in or l_f plus SELV secondary nets. | None on the power board. |
| Clearance | All HOT5. No D5 crossing. HOT↔HOT group spacing 3.2 mm, tank node 5.0 mm (`section.kicad_dru` rules 1–2). | It must straddle the 8.0 mm D5 barrier facing the **LS / HOT5** domain. That segment is the U32 / U4 / U9 row (x 89.6–118.5, y 115–127), with T1 starting at x 123.2, and it is full. The scan (`amc_spots_relaxed.txt`, `ls_barrier.txt`) finds 440 legal DWV positions on the barrier. All of them face the n_ha / n_hb / sw_b high-side domains, or the hv_ret/bus_p planes at (221.5, 117.5), 180 mm from R5 with no HOT5 supply. **None faces HOT5.** Fitting it means moving T1 or re-cutting the isolator row. | The inlet corner (x 213–289, y 0–58) is all HOT: F1, J1, RV1, C1, C2, L1. SELV copper there would need an 8 mm keep-out, and the SELV trace would run ~250 mm to J4. The Allegro ACS773 (CB package) has **7.2 mm** creepage and clearance per its datasheet (third-party copy), so it **fails D5 8.0** as drawn. SOIC-8 Hall parts have ~4 mm. | Depends on insulation: wire insulation plus the CT case as double insulation is a lab call. |
| Board space | ~50–70 mm². `ls_free_area.txt`: 507 mm² is legal in x 85–140, y 38–100 (no courtyard, ≥ 8 mm from SELV, ≥ 5 mm from res_a, ≥ 3.2 mm from other HOT groups). The largest blobs are 113 mm² (x 116–135.5, y 51–79, beside U3/U8/R32–R35) and 104 mm² (x 113–122.5, y 82–100). The largest legal empty rectangle is 8 × 6 mm (21 positions), so the block must be split or placed around obstacles. | 6.4 × 13 mm body plus ~6 passives, *after* a row re-placement. J4 grows 3 mm (2×8 → 2×9, 43045-1812). | CT ~20–30 mm cube plus SELV keep-out: a re-layout of the inlet corner. | None. |
| J4 / controller pins | **None.** | J4 is full: all 16 pins are used, including 3 × selv_gnd (pins 2, 4, 15). It needs +2 pins, a harness change and a controller mate change. Controller: all 36 GPIOs are used (`FW/test/test_controller_pins.c` asserts `ctrl_pins_count == module`). ADC1 CH0–CH9 are GPIO1–10: CH2 is fan tach (GPIO3), CH3/CH4 are PWM (GPIO4/5), CH9 is RTD_CS_N (GPIO10), and the other six are already ADCs. GPIO35 is RAIL_OK_RB, proposed for BIAS_GOOD (FW/README "BIAS_GOOD read-back"). The TCA9555 has 7 spare bits (P00–P05, P17), but they are digital only. Possible routes: (a) move RTD_CS_N to an expander bit, which frees GPIO10 = ADC1 CH9; or (b) replace the MCP3202 with an MCP3204 on the same SPI2 / CS (GPIO42). Either is a controller layout and firmware change. | Same as AMC1301, plus a rectifier or RMS stage. | Controller ADC as for AMC1301. No J4 change. |
| Stock and cost (qty 20) | OPA333AIDBVR: 2,687 in stock, $1.935 @10. TLV3201 is already on the BOM. SN74LVC1G08 is a commodity part (not checked). Total ≈ $3–4 per board. | AMC1301DWVR: **0 in stock**, 1,000 due 11-Jan-2027, 20 wk, $3.96 @10. AMC1300BDWVR: **0**, due 25-Feb-2027, $4.52 @10. TI lists AMC0300D as the drop-in successor (stock not checked). | Not pursued (D5 fails). | Not pursued. |
| Product value | It turns the abnormal test from a fail into a pass by design. It adds no power. | +7–9 % power at the 15 A hold (`output/temper-coil-driver-r1/input_current_budget.json`). **At the shipping 17.5 A tank ceiling, however, the inlet hold binds only for pans with R_eq > 4.2–4.4 Ω** *(desk)*, so it adds ~0 power until the airflow ceiling raise (S24). It cannot feed a hardware trip. | | |

### A4. Sizing the trip *(desk, for the placement pass; the bench sets the final value)*

**Signal.**
- The OCP divider (R32 10 k to ref25, R33 7.5 k to ocp_kelvin_n; threshold R34/R35 16 k/11 k = 1.019 V) trips at ocp_kelvin_n ≈ −92.6 mV nominal.
- So the Kelvin signal is **negative** with respect to HOT5 ground. The amplifier must be inverting, or must accept a common mode below ground.
- At 14 A mean the signal is −14 mV. A gain of −100 gives 1.4 V. The OPA333's 10 µV offset is 0.07 %.

**Threshold.** The trip should act on the power-stage share. With the regulated maximum true I_ps = 13.5 − aux (12.61–13.24 A, if e_est holds), and I_ps for a 15.0 A total = 14.11–14.74 A:
- a trip at **≈ 14.1 A RMS-equivalent** (12.7 A mean for a sine envelope) leaves 6.5 % over the highest regulated I_ps;
- it caps the total at ≤ 15.0 A with the blower at full.

**Error budget.**
- R5 1 %, resistors 0.1 %, LM4050A ref 0.1 %, OPA333 offset 0.1 %: about ±1.5 % in all.
- The open term is the **form factor**. A mean detector reads 0.900 × RMS for a sine envelope. Burst mode or flat-topped envelopes raise RMS/mean, and RMS is what heats the cord.
- The bench must measure mean(R5)/RMS(line) over the pan grid and burst duties.
- If the ratio spread exceeds about ±3 %, use an RMS-to-DC converter instead. An AD8436 (QSOP-20) is already used SELV-side. That costs more board area.

**Path.**
- The trip output goes into an AND with OCP_OK_HOT ahead of U8 SN74LVC1G10 (3-input NAND, all inputs used).
- Fit a 0 Ω bypass across the AND footprint. Then DNP = today's circuit exactly, and the OCP path is re-qualified only on the boards where the AND is fitted.
- The AND adds ≤ 4.5 ns to the OCP path. The OCP pickup and timing gates must be rerun.

**Recommendation.** Make the trip a layout stage now, with the footprints. Populate the trip on about half the lot (e.g. 10 of 20) and the bypass on the rest. Then the bench can compare the two and run the abnormal-test dry run, while the other boards stay identical to s51's protection behaviour.

### A5. What I would not do now

- **No AMC1301 or CT now.** It does not answer entries 11 or 13. It needs a barrier re-placement, J4 2×9, a harness change and a controller ADC route (three boards). It is out of stock. It buys no power at the 17.5 A ceiling.
- **Revisit it if either:**
  - the airflow route raises the ceiling to 24–28 A, where the +7–9 % matters; or
  - the lab asks for a *measured* inlet current for the rating test.
- **If revisited, prefer an AMC3301-class part** (isolated amplifier with an integrated high-side supply) on a line-side shunt. It measures total inlet current including aux, and needs no HOT5 supply at the barrier spot. That still makes it a full inlet-corner stage.

---------------------------------------------------------------------------------------------------------------------

## B. F1 holder (entry 9)

### B1. The F1 slot on s51

- **F1:** centre (246.35, 7.25). Courtyard x 223.7–269.0, y 0.455–14.05, i.e. **45.3 × 13.6 mm**.
- **Pads:** l_f at 225.47 / 236.27, ac_l_in at 256.43 / 267.23, y 5.4–9.1, 5.4 mm from the rear edge.
- **Hemmed in by:**
  - J3 (x ≤ 222.97);
  - J1 (x ≥ 269.56);
  - R1 (y ≥ 14.74);
  - C1 (x 236–263, y ≥ 14.22);
  - RV1 (x ≥ 264.5, y ≥ 15.98);
  - L1 (y ≥ 28.5).
- **Copper clearances:**
  - ac_l_in → l_f pour: 3.20 mm (the HOT group floor);
  - l_f → J3 tco_l/l_filt pads: 5.73 / 5.83 mm;
  - F1 → nearest PE copper: 93.5 mm.
- **Enclosure (`PS/validation-plan/enclosure-fit`, R4 catalogue, `scripts/f1_headroom.py`):**
  - the gate envelope for F1 is 20 mm;
  - the first R4 hit above F1's courtyard is `coil_support_flat_routed_plate` at **56.5 mm** above the board (both poses, translate and mirror-legacy);
  - growing the courtyard 30 mm into the board at 25 mm height gives no hits.
- **So height and enclosure are not the constraint. Board area at the inlet is.**

### B2. Candidates

| Part | Type | Rating / agency | Size | Fits F1 slot? | Stock for 20 |
|---|---|---|---|---|---|
| **Littelfuse 01250003H** × 2 (today) | Open PCB clip, 13/32 in | 30 A. UR E14721 (cell ambiguous). Voltage not on the datasheet. | 41.76 mm outer span, 18.5 mm tall | Yes (as built) | DigiKey 9,223, $3.249 @10, 14 wk |
| Schurter CSO 0751.0507 × 2 | Open PCB clip, 10.3 × 38 | **32 A, 1500 V, UL Recognized E39328**, designed to UL 4248-1 / CSA 4248.1 | Pins Ø2.35 at 15 mm, 45 mm span, 24.8 mm tall; courtyard ~50 × 14.8 mm (F1-RECOMMENDATION §4.1) | Tight. It overlaps R1 and C1 more, the RV1 gap is 0.95 mm, and the J3 pad gap falls to ~4.1 mm *(desk)*. Needs a footprint change. | DigiKey 1,145, $1.507 @10, 28 wk |
| Keystone 3566 × 2 | Open clip with end stops | "UL" 30 A (Keystone: clips without end stops are not UL) | 5AG pattern | Footprint change. Fit with the Class CC rejection cap is unverified. | 49,315 (SURVEY 2026-10-14) |
| Littelfuse **L60030M3PCB** + SPL001PCB covers | **PCB-mount block, 3-pole, midget (non-rejection)**, open face with snap covers | 600 V, 30 A, UL Recognized E14721 (L600 PCB datasheet Rev 4-B-080113, via manualsdir) | 18 holes Ø1.47 at 2.54 mm. Drawing callouts 41.61 × 46.99 × 22.86 mm (unlabelled). | **No.** It is three poles wide, and needs about 41.6 × 47 mm against the free 45.3 × 13.6 mm. It is also not a Class CC holder. | DigiKey **0**, 22 wk, $37.80 @1 / $28.93 @10 |
| Littelfuse **LPSC001** (/ID indicating) | DIN-rail modular, **Class CC rejection** | 600 V, 30 A, UL Listed E14721 (distributor) | 17.8 W × 77.7 H × 59.2 D mm (0.7 × 3.06 × 2.33 in) | Off-board (DIN rail on the chassis) | Not checked |
| Bussmann **CHCC1DU** (/DIU indicating) | DIN-rail modular, Class CC | 600 V, 30 A, 200 kA SCCR, UL Listed E14853 / IZLT | 17.5 W × 73 H × 87 D mm (Eaton catalogue page) | Off-board | Not checked |
| Littelfuse **5710CC** (057100CCL) | Panel-mount, Class CC rejection | 600 V, 30 A. UL Recognized E14721 **for branch-circuit protection**. CSA LR7316. | Ø22.6 mm cut-out + 2 × Ø4.37 on 33.3 mm; 34.0 mm behind the panel, 19.3 mm in front (F1-RECOMMENDATION §6.1) | Off-board (enclosure end face); wired to the board | DigiKey **0**, 50 due 14-Dec-2026, 9 wk, $18.87 @10 |

**No single-pole, enclosed or covered, UL PCB-mount Class CC holder was found.** That agrees with `PS/validation-results/12-decisions/f1-data/SURVEY.md` §3: "No enclosed PCB holder for 10 × 38 rated ≥ 25 A / ≥ 250 VAC". The LPSC and CHCC families have no PCB variant. They are DIN-rail modules.

### B3. Dual footprint

- **Clips + PCB holder: not feasible.** No candidate fits, and none is stocked.
- **01250003H + CSO clips: geometrically possible.**
  - CSO pins would sit at 223.85 / 238.85 / 253.85 / 268.85, against slots at 225.47 / 236.27 / 256.43 / 267.23. The centres are 1.62 and 2.58 mm apart and the copper overlaps, so each pair would merge into one elongated slot.
  - Its value is only the agency file and voltage rating on the clip. It is still an open clip.
- **Clips + "wire-out", the useful one:**
  - Add two ≥ 25 A PCB terminals (e.g. 6.3 mm quick-connect tabs; rating not verified) under the fuse body: l_f near x ≈ 240, ac_l_in near x ≈ 252. The free strip between the inner pads is x 237.47–255.23, 17.8 mm long.
  - The 3.2 mm ac_l_in↔l_f spacing is kept.
  - Then the same board takes either clips + KLDR025, or two leads to an off-board 5710CC / CHCC holder. The enclosure supplies the holder if the lab refuses open clips.
  - This is cheap only if a layout stage happens anyway. On its own it is a small inlet-corner stage: pours and antipads.

### B4. Recommendation for B

- **Wait.** Keep the clips for the prototype. They are what the lab would test against, and the lab will ask for the temperature-rise data that only the bench can give.
- **Why open clips are plausible:**
  - F1 acts as supplementary protection behind the branch breaker (entry 9: "branch breaker plus Class CC F1, no inlet fuse");
  - NEC 240.60(B) rejection applies to field-installed branch fuses (my reading; not verified against the end-product standard).
- **If the lab refuses open clips**, the realistic answers are off-board (5710CC or a DIN module). Either way that is an enclosure change. The board change is the wire-out above.
- **Optional:** fold the wire-out tabs into the A layout stage at near-zero extra cost.
- **Not worth doing:** a CSO footprint, unless the lab's objection is specifically to the 01250003H's missing voltage rating or agency file. Even then it is a footprint change, not BOM-only.

**What the bench learns (B):**
- F1 + clip temperature rise at 15 A and 16.0 A in the 61 °C bay (the release basis is 16.0 A continuous);
- retention and seating of the Class CC rejection tip in non-rejection clips (F1-RECOMMENDATION §4.1);
- clip-to-l_f-strip air gap ≥ 3.2 mm (open item, F1-RECOMMENDATION §5.3).

---------------------------------------------------------------------------------------------------------------------

## Files in this folder

| File | What |
|---|---|
| `scripts/dump_fp.py` → `s51_fp.json` | Footprints, pads, nets from BOARD (KiCad python, `-I`). |
| `scripts/barrier_map.py` → `barrier_map.npz`, `barrier_map.npz.selv.json` | HOT / SELV / PE plan-view raster. Reproduces D5 8.047 / 8.507 mm. |
| `scripts/amc_spots.py`, `amc_spots_relaxed.py` → `amc_spots_relaxed.txt` | Legal DWV-SOIC-8 barrier positions (440). None faces HOT5. |
| `scripts/spot_nets.py` | Nets either side of each candidate spot. |
| `scripts/ls_barrier.py` → `ls_barrier.txt` | Where LS / HOT5 copper faces SELV (the isolator row, U1/U2 inputs, U36). |
| `scripts/hot5_spots.py`, `ls_free_area.py` → `ls_free_area.txt` | Legal free HOT5 area for the trip block. |
| `scripts/f1_headroom.py` → `f1_headroom.txt` | R4 enclosure headroom over F1: 56.0 mm. |
| `scripts/line_current_bounds.py` → `line_current_bounds.txt` | Desk bounds for A2 / A4. |

**Rerun:** `python3 -I scripts/<name>.py`, with `barrier_map.npz` / `s51_fp.json` as arguments where the script takes them. `dump_fp.py` runs under KiCad's python: `.../KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3 -I scripts/dump_fp.py BOARD s51_fp.json`.

## Not verified

- L600 PCB dimensions are drawing callouts without labels. The Littelfuse PDF returned 403, so I read a manualsdir copy.
- The LPSC E14721 file comes from a distributor listing.
- CHCC dimensions come from distributor and Eaton catalogue pages, not the datasheet.
- ACS773 creepage comes from a third-party copy of its datasheet.
- Not checked: quick-connect tab current ratings, SN74LVC1G08 stock, AMC0300D stock, LCSC and Mouser stock.
- The A2 / A4 figures are a first-harmonic, fixed-frequency model. They are not a simulation.
- Whether UL 1026 / UL 858 accept a Class CC fuse in open clips (entry 9), and whether a hardware average trip satisfies the lab's abnormal test (entry 11), are lab questions. This study only removes the firmware dependency.
