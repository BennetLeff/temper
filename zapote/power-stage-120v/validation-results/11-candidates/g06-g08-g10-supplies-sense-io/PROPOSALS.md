# G06 / G08 / G10 proposals (supplies, sense and protect, SELV interface), 2026-10-13

Benchmark: native-21 stage 19c, board SHA-256 `3d3a2c69c07a2102...`. Every number below comes from a script in this folder (rerun with `python3 -I`, listed per proposal) or from a cited source. Nothing outside this folder was modified.

## Ranking (cost at 500 units, DK basis of the stock sheet unless stated)

| # | Proposal | Cost / lines | Metric effect | Interfaces | Risk, effort |
|---|---|---|---|---|---|
| P1 | Delete PS1; controller logic runs from PS3 (J13) | -$8.40 (PS1) | leakage 0.974 -> 0.831 mA; board heat -1.52 W (B3 value); 3 -> 2 mains modules; J4 loses its V15 pin | J4 pin 1, controller J13/rail, PS3 load 66 -> 74 %, enclosure PS3 bay | med, schematic + placement + controller change. **SAFETY** (supply topology) |
| P2 | F2: UMT 250 -> Littelfuse 02153.15MXP 5x20 in clips, plus 0.15 ohm series | -$1.69 for the fuse line, +clips (placeholder $1.4/pair); net P1+P2 -$8.69 to -$9.39 | F4 FAIL -> margin 1.9x on the 1.5 kA rating at every corner (bound, no copper credit) | J11/blw_l, area where PS1 was | med, re-layout of the J11 corner (free after P1). **SAFETY** (fusing) |
| P3 | Reclassify PS2's Y leakage as not reaching PE | $0 | leakage a further -0.143 mA (0.688 mA with P1) | none | low on the board, **SAFETY**: needs bench/certifier |
| P4 | F8: KELVIN_N under KELVIN_P + C30/C31 at U6 pins | 0 | any-phase +50 % stack at 60 kHz, 59.2 A: 8.71 -> 0.97 A (pan); gate <= 6.5 A | R5/U6 corridor, G02/G03 neighbours (copper only) | low-med, copper patch |
| P5 | J4 re-pin with interleaved grounds (4 GND after P1) | 0 | crosstalk proxy -72/-77 %, loop proxy -13/-15 % | controller J4 mating connector, harness | low, but controller must change in step |
| P6 | Price/stock refresh (BOM only) | PS1 $6.35, PS2 $6.37, R5 $0.31 on LCSC vs DK basis | none | none | none |

P1 + P2 + P3 together: Y leakage 0.974 -> 0.688 mA. That still fails the 0.25 mA (50 % of 0.5 mA) budget; see "F5 conclusion".

## P1: delete PS1, run the controller from PS3 (the "fewer modules" angle)

**Change.**
- Delete PS1 (Mean Well IRM-20-15, `ps_selv`, at (255.8, 136.4), pads x 209.3..257.3, y 114.1..137.9) and net `v15_selv` (internal to G10: PS1.VP to J4.1 only), about 250 mm of track.
- J4.1 stops carrying V15 (re-pin in P5).
- PS3 (IRM-60-15ST, chassis, already specified) powers the blower buck and, new, the controller logic 15 V rail. Controller side, to be done by the controller owner:
  1. Join J13 15 V (V15_BLW) to the logic 15 V rail through a Schottky or ferrite bead plus a bulk cap, so a blower start or stall transient cannot pull the logic rail (the reason PS3 exists, DECISIONS 15/16, is kept by this local isolation).
  2. Remove the J4.1 15 V input path.
  3. The "PS3 absent" logic (BLW_PG on P16, "NO BLOWER PWR") becomes moot: PS3 absent means no controller. The result is fail-safe (PERMIT and PWM drop with the controller).
  4. Re-check the J13 pair: PS3 output current rises from 2.72 A to 2.97 A (44.5 W / 15 V), within the JST VH / 18 AWG rating used by the enclosure check.

**Mechanism.** Mean Well's PS1 serves 4.83 W (controller verify `ps1.p_total_W`, PLAN-16 sec 1.1) from a 21 W module and PS3 serves 39.7 W from a 60 W module. One module is enough for both: PS3 at 44.5 W is 74 % of 60 W. The mains-side modules go from three to two (PS2 on TCO_L is kept: DECISIONS 2026-10-06 revised, the TCO must cut the gate bias, and the bias must be HOT-referenced). PS1 is also the only part of G10 that straddles the SELV barrier; deleting it removes the "potted-PS1 courtyard" certifier question (DECISIONS 16, R43 entry).

**Evidence.** `supplies/supply_budget.py` (-> `supplies/result.json`):
- PS1 today: 23 % load, max ambient 78.4 C (the script reproduces DECISIONS 16's ~78 C figure for PS1).
- PS3 now: 66.2 %, max ambient 63.7 C. After P1: 74.2 %, max ambient 60.3 C (IRM-60 derating 100 % to 50 C, 75 % at 60 C, 15 % at 85 C, as read in PLAN-16). The PS3 shelf in the enclosure must be at or below about 58 C air to keep 2 K of margin: **temper-f7 must supply the PS3 bay air temperature; I could not verify it.**
- Board heat: B3 carries PS1 at 1.524 W; its real loss at 4.83 W is 0.92 W. Removing it takes the carried 1.52 W off the board; the PS3 loss increases by about 0.5 W in the chassis.
- Leakage: `leakage/leakage_variants.py`: 0.974 -> 0.831 mA (one fewer module charged to the PE path).

**BOM.** Remove IRM-20-15, LCSC C6211072 (JLC Extended). LCSC stock 1,498 and $6.3537 (page fetched 2026-10-13, https://www.lcsc.com/product-detail/C6211072.html); BOM basis (DK) $8.40 at 500. The "zero stock" flag is DigiKey only. JLC stock 1,568 per the BOM of 2026-10-08.

**Effect on the scorecard.** `leakage_touch_mA` 0.974 -> 0.831 (still FAIL); heat -1.52 W on the B3 input (a small improvement of `b3_c28_h25_peak_C`, not computed: needs the chain); `return_path_*` metrics: J4.1 and the PS1 return disappear, needs the chain. Input-current budget (D-33/aux): the 1.3 A allowance covered both IRM-20 at full load; the real PS1 draw at 4.83 W is below that, so the budget does not get worse.

**Interfaces disturbed.** J4.1 (controller), J13 (controller rail merge), selv_gnd copper that PS1.VN fed, PS3 bay (enclosure), BLW_PG firmware path, R38 unchanged. G07/G09 do not use v15_selv.

**SAFETY.** Supply topology and the number of mains-connected modules change, nothing about insulation: PS3 already provides reinforced isolation (4.2 kVac I/O withstand, IRM-60-SPEC p.2) and is already in the design. The new single point of failure is PS3/F2/J11: loss of any of them now powers down the controller as well as the blower. All outputs fail to their safe state when the controller loses power (the PWM safe state, D-25). Certifier to confirm that a SELV controller powered from a chassis-mounted Class II module through a 292 mm harness is acceptable (the harness already exists for the blower).

**Risk class.** Medium. Effort: schematic + placement (G10) and a controller change (not mine).

**Reverses if** the PS3 bay air is above about 58 C, or the bench shows the blower start pulling the logic rail below its brown-out threshold through the J13 decoupling; then keep PS1 and take only P2 to P6.

## P2: F2 breaking capacity (F4)

**Change.** Replace F2 (Schurter UMT 250 3403.0171, $1.80, no LCSC code, consigned) with Littelfuse 02153.15MXP (5x20 mm ceramic HBC, T3.15 A, 250 V, 1.5 kA) in two PCB clips, **plus a 0.15 ohm series resistor** (1 W class, flame-proof or wirewound) in blw_l. Fuse: LCSC C142723, 3,780 in stock, $0.1099 at 500 (page fetched 2026-10-13, https://www.lcsc.com/product-detail/C142723.html; 1.5 kA at 250 VAC listed). Clips: Littelfuse 100 series 5x20 clip (RS lists it, https://nz.rs-online.com/web/p/fuse-clips/8949562); I found no LCSC clip listing with price, so the clip cost is a placeholder. Courtyard about 26 x 9 mm and 8-10 mm tall (F4 study); P1 frees PS1's 48 x 24 mm area beside F2 (266.5, 118.4) and J11 (262.5, 125.3).

**Mechanism and numbers.** The F4 study's fault current is 1.09-1.45 kA with the copper counted and up to 3.75 kA with zero copper (stiff source, bolted fault at J11); the 02153.15MXP alone is 3 % inside its rating at the stiff corner with copper and outside it with zero copper. A series resistor bounds the current independent of the source and copper: Ik <= 139.7 V / (0.0283 + R). `f2/f2_variants.py` -> `f2/result.json`:
- R = 0.15 ohm: Ik <= 784 A, margin 1.91x on 1.5 kA at every corner. Loss at the P1 load: I_in 1.42 A at 108 V -> 0.30 W; 0.20 W at 132 V.
- R = 0.22 ohm: 563 A (2.67x), 0.45 W.
- The input current is scaled from IRM-60-SPEC p.2 (1.8 A typ at 115 V, 60 W), linearly in load and 1/V: an estimate.
- Not yet known: the 02153.15MXP clearing I2t at 784 A, which sets the resistor's pulse energy (R x I2t). It must be read from the Littelfuse datasheet, which returned 403 to the F4 study. Also unverified: the 1.5 kA figure on the agency certificate (the F4 study's own caveat).

**Rejected variant (kept for the record):** keeping the SMD UMT 250 and adding a series resistor to get Ik < 200 A needs 0.7 ohm minimum (1.0 ohm for 1.57x): 1.6-2.0 W continuous at 108 V, 4.5 W at 2.2 ohm (`f2_variants.py`). That is board heat and a drop to PS3's input; not recommended.

**Alternative that removes F2 from the board:** an in-line holder in the J11 harness at PS3's end, on the temper-f7 chassis. It does not protect the board tracks or the J11 lead between the board and the fuse, so the 02153.15MXP at the tap stays preferred.

**Scorecard.** F4 FAIL -> pass (bound 1.91x margin); cost -$1.69 on the fuse line before clips; assembly: F2 leaves the consign list (the line removed), the 5x20 fuse and clips are THT/hand parts.

**SAFETY (fusing).** Needs the certifier: (a) the 1.5 kA rating on the approval, (b) whether a supplemental fuse behind F1 in this branch is acceptable (F4 study question), (c) the 0.15 ohm resistor's failure mode (it must fail open or stay intact; an unfused short of it only returns to the F4 FAIL case, not worse). **Risk class** med; effort re-layout of the J11 corner (a bounded area).

## P3: PS2's Y leakage does not reach PE (F5)

PS2 (IRM-20-24) has its output negative on N_LS / LEG_RET, the bridge-referenced HOT domain, with no PE bond. Current from L through its Y capacitor returns to N through the rectifier bridge. It reaches PE only through HOT-to-PE parasitics (coil 31 pF, FET tab to the sink), which are in series with it. PS1 and PS3 are different: their output negative is SELV GND, bonded to PE by R38, so their leakage is in the PE path. The F5 study charged all three modules at the datasheet maximum to the PE path.

`leakage/leakage_variants.py` (control: reproduces 0.974 mA):

| Case | Touch current, mA (PE open, 132 V, 60 Hz, +20 % Y, datasheet maxima) |
|---|---|
| F5 study (3 modules charged) | 0.974 |
| PS2 reclassified | 0.831 |
| P1 (PS1 gone), PS2 still charged | 0.831 |
| P1 + PS2 reclassified | 0.688 |
| and typical-measured module leakage (Simpex report, informational) | 0.555 |

**This is a measurement claim, not a design change:** SAFETY, needs a bench touch-current test with PS2 powered (UL 1026 open-PE) and the certifier's reading. I did not verify it by measurement.

## F5 conclusion

- One module's datasheet maximum (0.143 mA at 132 V) is already 57 % of the 0.25 mA budget. With three modules charged, no value of Y capacitance passes the 50 % budget: allowed nominal Y is 0 nF; even against the full 0.5 mA limit only 1.16 nF per line is left.
- With P1 and P3 (one module in the PE path) the allowed nominal Y per line is 1.76 nF at the 0.25 mA budget and 5.95 nF at the 0.5 mA limit, against 9.1 nF today (board 2.2 + D-22 module 6.9).
- So the supply count is the first-order lever in my groups; the rest of F5 is G01's (D-22 module Y, C3/C4). Cutting from three to one charged module gains 0.286 mA and moves the required Y cut from "impossible" to "about 3.2 nF at the full limit, 7.3 nF at the budget".
- I did not find a lower-leakage Mean Well alternative with a verified datasheet; not proposed.

## P4: F8 rerun on 19c copper and the Kelvin patch

Scripts: `f8-pickup/` (copied from `02-protection-timing/coil-pickup/`, edited for 19c: copper and pad data read from `native21s19c-all-copper.json.gz`, field re-solved at 31/35/45/60 kHz by `field_phase.py` with study 06's FEM, outputs committed as `field_phase_<kHz>kHz.json`). Rerun: `python3 -I run_ocp.py` (writes `result.json`, `run_ocp.log`). `field_phase.py` needs `/Users/bennet/Desktop/temper/output/temper-r32-studies/06-emi-strayfield` (outside the repo); the committed JSON makes the loop script self-contained.

**Control.** At 31 kHz and 31.1 A the 19c copper gives the 13b report's numbers: node and threshold loops within 3 % (0.345 / 0.068 mV against 0.35 / 0.07), the Kelvin loop 12 % lower (1.01 against 1.14 mV; area 205.5 against 213.7 mm2 because R5 moved 1.5 mm), any-phase +50 % stack 2.80 A against 3.00 A. The Kelvin, node and threshold routing in 19c is otherwise the 13b geometry (same vias and runs).

**Result at 59.2 A peak** (any-phase +50 % stack = 1.5 x sum of the sub-loop magnitudes; gate <= 6.5 A; "peak shift" = time-domain shift of the apparent peak current for the FEM phase, gate <= 1 A nominal). From `f8-pickup/result.json`:

| Variant | pan 35 kHz | pan 45 kHz | pan 60 kHz | no-pan 60 kHz | peak shift pan 60 kHz |
|---|---|---|---|---|---|
| 19c as built | 5.83 | 7.04 | **8.71 FAIL** | 24.6 | 0.60 A |
| Kelvin move (idealised, my closure) | 3.17 | 3.82 | 4.73 | 13.6 | 0.37 A |
| Kelvin move at the 13b report's -56 % only | n/a | 4.85 | 6.00 | 16.9 | 0.07 A |
| Kelvin move + C30/C31 at U6 pins (idealised) | 0.66 | 0.79 | **0.97** | **3.16** | 0.25 A |
| Kelvin move at -56 % + C30/C31 at U6 pins | n/a | 1.81 | 2.24 | 6.39 | 0.55 A |

Meaning:
- **As built fails the gate** at 45 and 60 kHz (7.04 and 8.71 A against 6.5 A), by a margin the 13b report predicted (3.7x scaling). The nominal peak shift (0.60 A) passes.
- The Kelvin move alone fixes the pan case but not the no-pan bound (13.6-16.9 A). The no-pan any-phase number is the one the 13b report called non-physical (without a lossy load the field phase cannot rotate; the FEM phase puts no-pan pickup in quadrature, peak shift 0.1 A), so I would accept it, but a strict reading of the F8 gate is met only with the second change.
- **Recommended patch (both):** (1) from the pour-entry height (106.6, 53.5), run KELVIN_N on In2 straight under the In1 KELVIN_P pour line to the R33.2 end, instead of the In1 run x = 106.6, y 43.4 -> 72.4 then y = 72.4 to R33.2 (119.95, 71.0); (2) put C30 beside U6.3 (101.96, 58.69) and C31 beside U6.4 (their placements are 15 mm away today, which is the node/threshold loops' area). All rows then pass at every frequency and phase assumption, including the conservative -56 % Kelvin number (max 6.39 A, no-pan any-phase, just under 6.5).
- Caveat: with the cluster loops removed, the cancellation between the Kelvin and node terms disappears; the pan nominal |dI| goes to 0.62 A (idealised) or 1.47 A (-56 % case), above 1 A as a magnitude but with a peak shift of 0.25-0.55 A. If the owner reads "nominal <= 1 A" as the phasor magnitude, only the idealised closure passes.
- Not rerun (G09's): CT comparator and LINE_ZC loops. From the old results scaled by 3.7: the worst CT case 0.35 A -> about 1.3 A of tank current against a 50.56-60 A band: still negligible; stated, not computed.
- Limits: board-copper eddy currents are not solved; the field's frequency dependence comes from the 2D axisymmetric FEM; the 59.2 A is applied as the field peak (conservative: 28 A rms tank is 39.6 A peak). Self-field and dv/dt injection (RESOLUTION-PLAN F8 step 4) are not done.

**Interfaces.** The patch moves copper on In1/In2 in the R5 -> R33 corridor next to the G02/G03 HV_RET necks; it adds no net, but the In1 KELVIN_P pour must stay continuous over the new In2 run. G02/G03 owners must check clearance to the In1 HV_RET edge at y about 43. **Risk** low-med, copper patch only.

## P5: J4 re-pin (F11)

`j4/j4_pinmap.py` (seeded annealing over both rows, heuristic proxy, controls pass; `j4/result.json`). Current map: pins 1-8 = V15, GND, V3V3, GND, PWM_HA, PWM_LA, PWM_HB, PWM_LB; pins 9-16 (opposite pin n-8) = PERMIT, BUS_FAULT, VBUS_P, VBUS_N, CT_ZC, CT_MON, GND, LINE_ZC. CT_MON (14) is opposite PWM_LA (6) and CT_ZC (13) opposite PWM_HA (5), as F11 says. Proxy cost (crosstalk, return-loop): current 4.98 / 9.87.

**Case A (PS1 kept, 3 GND):** crosstalk 1.41 (-72 %), loop 8.63 (-13 %)

| pin | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
|---|---|---|---|---|---|---|---|---|
| row 1 | V3V3 | PWM_LB | PWM_HB | GND | VBUS_P | VBUS_N | GND | CT_MON |
| pin | 9 | 10 | 11 | 12 | 13 | 14 | 15 | 16 |
| row 2 | PWM_LA | GND | PWM_HA | V15 | BUS_FAULT | PERMIT | CT_ZC | LINE_ZC |

**Case B (PS1 deleted, 4 GND), the one to use with P1:** crosstalk 1.15 (-77 %), loop 8.38 (-15 %)

| pin | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
|---|---|---|---|---|---|---|---|---|
| row 1 | GND | CT_MON | CT_ZC | BUS_FAULT | V3V3 | PWM_LA | PWM_HA | GND |
| pin | 9 | 10 | 11 | 12 | 13 | 14 | 15 | 16 |
| row 2 | VBUS_P | VBUS_N | GND | PERMIT | LINE_ZC | GND | PWM_HB | PWM_LB |

**Controller-side change needed** (the controller owner, in step): the mating J4 (Micro-Fit 3.0 2x8 receptacle) net-to-pin assignment of the 16 pins changes to the table above; the harness wires and any footprint-level pin names move with it; nothing else on the controller changes except what P1 requires (J4.1 no longer a V15 input). The power-board side is a netlist re-pin of `j_selv.p1..p16` in `power_stage_120v.ato` and a re-route of the 15 signal stubs at J4 (pad pitch and row spacing are unchanged: 3.0 mm x 3.0 mm, pads at y 180.08 / 183.08). This does not remove the "unfiltered PWM" item: C153-C156 (19b/19c) are the only filter; an RC at each PWM input needs the controller.
Limits: the proxy is geometry-only (no harness twisting, no field solve); it ranks maps, it does not predict a noise voltage. **Risk** low, effort schematic + re-route; requires a controller change, so it is a re-spin item.

## P6: price and stock refresh (BOM only)

The "zero stock" flags on R5 and PS1 are DigiKey-only:
- R5 CSS2H-2512R-1L00F, LCSC C4175647: 1,482 in stock, $0.3147 at 500 (https://www.lcsc.com/product-detail/C4175647.html) against the sheet's $0.501.
- PS1 IRM-20-15, LCSC C6211072: 1,498, $6.3537 (single tier listed).
- PS2 IRM-20-24, LCSC C194964: 6,455, $6.3676 (single tier listed, https://www.lcsc.com/product-detail/C194964.html).
- F2 02153.15MXP: see P2.
If the scorecard's cost basis moves to LCSC pricing, these lines fall by about $0.19 + $2.05 + $2.03 at 500. I did not change any basis; the lead decides.

R5 alternatives (DECISIONS 14/17): none needed, the part is in stock. Only a Cyntec SCMM2512S5-R001F (5 W, 1 mOhm, 2-terminal, DK stock listed with a 24-week lead conflict, https://www.digikey.com/en/products/detail/delta-electronics-cyntec/SCMM2512S5-R001F/9762028) came up as a stocked 5 W 1 mOhm 2512; it has no sense terminals, so the Kelvin land and the G6 derating story (0.208 / 0.473 W bound at the pad temperature) would have to be redone. Rejected.

## F12 (thermal ratings of PS1/PS2)

`supplies/supply_budget.py`: PS2 carries 5.9-9.6 W (27-44 % of 21.6 W, 33-80 kHz, `bias_sizing.py`). The IRM-20 "OTHERS" derating (100 % to 50 C, straight to 5 % at 85 C, read from IRM-20-SPEC p.3) allows ambient air of 76.7 / 75.8 / 70.5 C at those loads. The "13 K over 85 C" in F12 compares a modelled case temperature with the datasheet's ambient limit; the right test is local air against about 70-76 C. PS1 allows 78.4 C at 4.83 W. Neither is a failure on the data in hand, but local-air numbers from B3 or bench IR are needed to close it (not available to me). No change proposed.

## Considered and rejected

- **PS2 powers the blower** (one module fewer): PS2 is TCO-switched (the TCO must cut gate bias, DECISIONS 2026-10-06 revised), HOT-referenced, 21.6 W against the 33.5-39.7 W blower budget; the blower would die on a TCO trip and sit on a HOT rail.
- **PS3 on the board** (no J11, no F2, no harness): IRM-60-15 PCB is 87 x 52 mm (PLAN-16 table); PS1's freed 48 x 24 mm does not hold it, and it moves 5-6 W of heat from the chassis onto the board. Stage 16 already rejected upsizing PS1 for room.
- **Blower from PS1 (no PS3, no tap):** 40.8 W against 21 W (PLAN-16); the owner asked for the split.
- **HOT-side isolated DC-DC for SELV** (puts the IRM leakage into the HOT domain): needs a reinforced 6 W-class converter plus still the blower supply; cost goes up, not down.
- **Series resistor of 0.7-2.2 ohm with the UMT 250:** 1.1-4.5 W continuous (see P2).
- **Merging PS2 into the SELV supply:** the TCO cut and the HOT reference both forbid it.
- **Lower-leakage module swap:** no verified datasheet found; not proposed.

## Interfaces and hand-offs

- **Leakage (G01):** after P1 + P3 the module Y and C3/C4 must total at most 5.95 nF nominal per line at the 0.5 mA limit (1.76 nF at the 0.25 mA budget), against 9.1 nF.
- **Bias rails (G05/G07):** PS2 unchanged. **Kelvin (G02/G03):** P4 copper corridor. **Controller:** P1 (J13 merge, J4.1) and P5 (pin table). 
- **Enclosure (temper-f7, not contacted):** PS3 bay air at or below about 58 C at 28 A; J13 pair carries 2.97 A; PS3 shelf and J13 barrier unchanged; the PS1 courtyard and its certifier question disappear; F2's new 5x20 fuse (about 8-10 mm tall) needs the height envelope near (266.5, 118.4) and operator access if it is to be user-replaceable (not claimed).

## What I could not verify

- PS3 bay air temperature, and the PS3 derating curve beyond PLAN-16's reading.
- The 02153.15MXP datasheet (clearing I2t at 784 A, the 1.5 kA on the approval): the Littelfuse PDF was not read; only the LCSC listing.
- The clip price (placeholder) and any LCSC clip stock.
- P3 is an argument, not a measurement.
- The J4 proxy is a heuristic; the FEM field's frequency scaling is 2D axisymmetric.
- The `field_phase.py` regeneration depends on a path outside the repo; the 31 kHz output reproduced the 13b report within the stated limits, not bit for bit (R5 moved).
- The module Y of P1's PS3 at the PE-open touch current is still the datasheet maximum (no measurement).
