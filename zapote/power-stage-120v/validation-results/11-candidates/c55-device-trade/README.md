# c55: production device trade for the bridge switches

Analysis lane, 2026-10-27/28. Board of record native-21 s53; branch `codex/power-stage-integration`. Nothing outside
this folder was edited: no DECISIONS, ledger, BOM or board file. Nothing was built and nothing was ordered. Every number
below comes from a script in `scripts/` and its file in `results/`, or from a cited datasheet page. [EST] marks an
estimate; [VEN, 2026-10-27] marks a DigiKey list-price read (not a quote).

## Answer

**Recommended production device: Infineon IMW65R026M2H (650 V CoolSiC G2, 26 mΩ) on the board's +15 / −1.6 V
rails, with the gate network back to R_on 8.2 Ω / Cgs 1 nF and the dead time cut to 200 ns (R9 / R17 49.9 k →
20.0 kΩ).** It is the only candidate that closes S14. It fits the same TO-247-3 G-D-S footprint with no rail change,
and it is **$12.35 per board cheaper at 500 boards** [VEN, 2026-10-27]. The price is heat: the four switches
dissipate 35.3 W at 17.5 A instead of 18.7 W, and 93.3 W at 28 A instead of 53.8 W. Junctions stay far inside the
175 °C rating (S8 82.5 / 125.6 °C), but the sink runs 5–13 K hotter. It is a recommendation for the prototype lot
to confirm, not a release claim.

A FET-only swap (s42 network kept, only R9 / R17 changed) also passes every screen (640/640, S4 3.85 V/ns), but its
slow turn-on keeps the 4.3 V body diode conducting longer: S8 86.7 / 133.4 °C and a bench sink of 90.9 °C, 7 K under
the trip. The 8.2 Ω / 1 nF network is worth its two value changes.

**S14 (S4 reverse-diode dv/dt at maximum Qrr) is fixed only by the SiC parts.** Neither CoolMOS can do it within
the turn-on time the ZVS loop allows: the CFD7 as built sits at 68.58 V/ns (0.98 of its 70 V/ns rating), the best
CM8 network at 66.4 V/ns (0.95). Both are under the rating and over the 56 V/ns (80 %) screen.

### Ranked table

S8 = production sink, 13 CFM, 50 °C inlet; bench = Wakefield 511-3M in still air at 30 °C. Tj and loss at the worst of
35 / 50 / 60 kHz. Loss is the four switches together. Prices are DigiKey list prices, 4 parts per board, at 80 / 2,000
pieces (20 / 500 boards).

| # | Candidate | S14: S4 dv/dt at max Qrr | Decision grid (c25 screens) | S8 Tj 17.5 / 28 A (limit) | Loss 17.5 / 28 A | Bench 17.5 A: Tj / sink | $/board 20 / 500 (Δ at 500) | DigiKey stock | Forced changes |
|---|---|---|---|---|---|---|---|---|---|
| **1** | **IMW65R026M2H, 8.2 Ω / 1 nF, DT 200 ns** | **closed: 11.8 V/ns** (no diode rating; 0.06 of the 200 V/ns MOSFET rating) | 640/640; ZVS to 5 A at 170 ns | 82.5 / 125.6 (175) | 35.3 / 93.3 W | 115.8 / 86.1 °C | 33.50 / 28.35 (**−12.35**) | 270, no backorders | 4 FETs; R10/R12/R18/R20 68 → 8.2 Ω; C55/C56/C62/C63 4.7 → 1 nF; R9 / R17 → 20.0 kΩ; ledger; B3 re-solve |
| 1' | same part, FET-only (s42 network kept), DT 200 ns | closed: 3.85 V/ns | 640/640 | 86.7 / 133.4 (175) | 41.0 / 103.5 W | 124.8 / 90.9 °C | as 1 | as 1 | 4 FETs; R9 / R17 → 20.0 kΩ |
| 2 | IPW65R018CFD7 as built (s42+) | open: 68.58 V/ns, 0.98 | 640/640 | 68.4 / 91.2 (150) | 18.7 / 53.8 W | 88.5 / 73.5 °C | 45.68 / 40.70 | 459, 8 wk | none |
| 3 | IPW65R018CM8, 100 Ω / 1 nF | open: 66.4 V/ns, 0.95 | 640/640 at max Qrr | 68.4 / 90.0 (150) | 19.0 / 52.7 W | 88.7 / 73.7 °C | 39.06 / 33.93 (−6.77) | **2**, 24 wk | R_on 68 → 100 Ω, Cgs 4.7 → 1 nF; never a FET-only swap (S2 608 V) |
| 4 | C3M0025065D [EST: no model] | expected closed (Qrr 0.26–0.31 µC) | not simulated; 1.8 V threshold vs −1.6 V off | 79.8 / 114.1 [EST] | 34.0 / 83.6 W [EST] | 111.6 / 84.8 °C [EST] | 31.73 / 26.60 (−14.10) | 430, 22 wk | model (terms click), off-gate check, maybe a −4 V rail |
| 5 | IHW40N65R6, retuned 20–30 kHz (4b) | not simulable (model aborts at the diode recovery); Qrr 2.2–3.8 µC, no rating | loss grid; S2 rows | 93.9 / 127.4 (175) | 49.9 / 94.1 W | 144.3 / **100.8** °C (over trip) | 8.62 / 5.46 (−35.24) | 104, 36 wk | coil +15 % turns, bank 5 → 12–13 caps, firmware window and tables |
| 6 | IHW40N65R6, drop-in 35–60 kHz (4a) | as 5 | as 5 | 98.4 / 136.4 (175) | 55.9 / 105.9 W | 159.3 / **108.7** °C (over trip) | 8.62 / 5.46 (−35.24) | 104, 36 wk | bench sink trips at 17.5 A |
| 7 | NTHL032N065M3S [EST: no model] | expected closed | not simulated | 95.4 / 157.8 [EST] | 51.2 / 132.4 W [EST] | 146.4 / **101.6** °C | 22.42 / 17.17 (−23.53) | 845 (+5,850 factory) | **5.56 mm lead pitch: layout change** |
| – | TP65H035G4WS GaN (reference) | – | not drop-in (G-S-D, tab S); no model | – | – | – | 28.56 / 23.50 | 803, 16 wk | footprint, gate drive |

The trip in the bench column is the 98.3 °C sink-trip low corner (DECISIONS 14). The IGBT rows' bench result means
the bench rig would trip on sink temperature at the 17.5 A release ceiling.

### Why this order

- **SiC first** because it removes S14 by physics rather than by slowing the gate. Its body diode stores ~0.1 µC,
  against 2.3–4.6 µC for the CFD7. It turns on in tens of ns (0.22 µs even on the slow s42 network, CFD7 0.94 µs),
  so the ZVS lag margin grows, and its gate charge is 61 nC against 383 nC, so the binding R10 row sheds most of its
  gate heat (R_on 0.022 W against 0.217 W).
  Its costs: double RDS(on) (34 mΩ typ at 15 V, 46 mΩ at 175 °C) and a 4.3 V body diode, so more heat; a 0.66 K/W
  RthJC; constrained supply; and a 15 V drive below Infineon's recommended 18 V (the 15 V RDS(on) has no maximum in
  the datasheet, so its maximum is an [EST]).
- **CFD7 second:** no change and proven parts, but S14 stays open and it is the most expensive.
- **CM8 third:** same S14 status as the CFD7, $6.77 cheaper, but 2 pieces in DigiKey stock and a 24-week lead. Its
  1 Ω internal gate resistance also makes it unsafe on today's 4.7 nF network.
- **C3M0025065D** may beat the G2 on heat and price, but nothing about its switching is simulated and its threshold
  is low for a −1.6 V off rail. Worth one terms-of-use click (the owner's call) to get its model.
- **RC-IGBTs** are $35 per board cheaper but need a new tank (4b) or run 3× the loss (4a), and both overheat the bench
  sink at 17.5 A.

### Prototype lot (prepared, not ordered)

- **Lot:** 20 boards, two SMD variants so the bench can compare the parts on one design:
  - **S (SiC), 14 boards:** s53 BOM with Q2 / Q3 / Q5 / Q6 = IMW65R026M2HXKSA1, R10 / R12 / R18 / R20 = 8.2 Ω on
    the 2512 pads (0.022 W each, so any 2512 part; MPN still to pick), C55 / C56 / C62 / C63 = 1 nF C0G 0603 (the
    s29–s41 value), R9 / R17 = 20.0 kΩ 0603 0.1 %. The PMEG + 1 Ω turn-off path stays.
  - **C (CFD7), 6 boards:** the s53 BOM unchanged. It cannot share the SiC SMD values: its t_trans is 190 ns, so a
    170 ns dead-time edge would lose ZVS, and 8.2 Ω would bring back the 85.8 V/ns S4 edge.
  - The TO-247s are through-hole and fitted by hand; the SMD variants are two JLC orders (14 + 6), or one order of
    the S variant if a single order matters more than the comparison.
- **Parts to buy:** about 64 IMW65R026M2H (56 + 8 spares; DigiKey 270 in stock, $8.38 at the 60 break) and about
  28 CFD7 (24 + 4). Ask Infineon / a distributor for a 2,000-piece quote and lead time for the SiC before committing
  production; DigiKey takes no backorders on it.
- **Bench plan:** D-8 double pulse (S4 hard commutation at 280 V, the binding case) on both variants: S4 dv/dt,
  diF/dt, Irr and die-side VDS. Then the bench-sink run at 17.5 A with thermocouples on the FET tabs and the sink:
  the SiC sink is predicted at 86.1 °C against the 98.3 °C trip (CFD7 73.5 °C).

### What to change before the prototype order

1. Pick the variant(s) above. For SiC: Q2 / Q3 / Q5 / Q6 → IMW65R026M2HXKSA1, R_on → 8.2 Ω 2512, Cgs → 1 nF,
   R9 / R17 → 20.0 kΩ. Firmware needs no change: its PWM input dead time is already 200 ns
   (`firmware/components/power/n21_binding.c:14`), and the 2EDR's DTC sets the floor (t_dt = 10 ns × R_DTC[kΩ],
   2EDR8259X Rev 1.7 p.3, p.8).
2. Ledger: add IMW65R026M2H (no reverse-diode dv/dt or diF/dt rating: check S4 against the 200 V/ns MOSFET dv/dt
   rating and record the gap); its Tj limit is 175 °C. Re-solve B3 with the SiC gate heat (R_on 0.022 W instead of
   0.217 W, bias channel 26.6 instead of 49.5 mA) and the SiC device loss.
3. Either way: raise the CFD7 S4 bounding value in the ledger from 68.16 to **68.58 V/ns** (section 1.3), and add a
   gate that refuses an S4 result with rows lacking a commutation edge.
4. Never fit a CM8 on the s42 network: with 4.7 nF its S2 die VDS reaches 607.9 V (6.8 nF: 660.9 V, over 650 V).
5. Get quotes: no part has 2,000 pieces at DigiKey; Mouser was not read.

## 1. Method

### 1.1 Switching (S1 / S2 / S4 / S5 screens)

- **Deck.** Every candidate runs on the committed as-built switching deck, built by the gate-network study's own
  `build_deck()` (c25 F6 deck, c33 board switch-node C, 2EDR8259X output model, PMEG6030EP + 1 Ω turn-off branch,
  matrices A/B). `scripts/devlib.py` only swaps the device model and the turn-on network. The study harnesses are
  imported read-only (`scripts/common.py`).
- **Grids** (`scripts/trade.py`): `full` = the gate-network study's 640-run decision grid (S1 ZVS at DT 340 / 408 ns,
  S2 fault turn-off at 71 A, S4 hard commutation of the partner's body diode, S5 first edge; legs A/B; 27/100/150 °C;
  nominal/weak/strong driver; ESL 10 / 1.06 nH). `s4b` = its 42-run binding S4 set. `s2q` = the 56 S2 rows.
  `s4bL` / `fullL` / `s4L` = the same rows in the 3.75 µs window (see 1.3).
- **Screens** (unchanged from c25 / gate-network study): die VDS 520 V in S4, 585 V in S2; off-gate < 3.0 V and
  < 1.9 V hot; diode dv/dt ≤ 0.8 × the part's reverse-diode dv/dt rating (the ledger's 80 % rule); diF/dt ≤ 0.8 ×
  rating. Summaries: `scripts/c20_switching.py` → `results/switching.json`, `results/switching.md`.
- **Recovery charge.** The vendor CoolMOS models understate Qrr. As in the gate-network study, the body-diode transit
  time TT is raised until the model's Qrr in the datasheet test (400 V, 100 A/µs, 25 °C) meets the datasheet value
  (`scripts/c05_qrr.py` → `results/qrr.json`):
  - CFD7: TT 125 / 260 ns = 2.3 / 4.6 µC typical / maximum (the study's own values; controls reproduce them).
  - CM8 (Infineon's 650 V model): TT 102 / 177 ns = 1.54 / 2.31 µC typical / maximum (Rev 2.1 Table 7). Runs use
    TT 100 / 180 ns.
  - SiC and RC-IGBT: their models' own diodes. The RC-IGBT fixture rows did not converge in the D3 recovery fixture
    (`qrr.json` `wrapped_rows`, "timestep too small"), so the IGBT recovery is taken from the datasheet only.

### 1.2 Loss and junction temperature

`scripts/c50_loss_thermal.py` → `results/loss_thermal.json`, `results/loss_thermal.md`.

- **Conduction:** I_t² / 2 × RDS(on),max(25 °C) × the datasheet's typical RDS(Tj)/RDS(25 °C) (device study basis D).
  RC-IGBT: V0 + r·I fits of the datasheet VCE(sat) and VF points, scaled to the 25 °C max/typ ratio, with the
  half-wave split into diode (first 60°) and IGBT (rest) parts.
- **Switching and dead time:** each candidate's own deck energy grid (V 20–198 V, I 2–60 A, Tj 100 / 150 °C, DT
  569 ns, both directions), integrated over the line cycle by the device study's `p_switch_leg()` (turn-off current
  2 I_t |sin| sin 60°). The energy is the die's v·i in excess of steady conduction, so it holds the turn-off, the
  IGBT tail, the dead-time diode or third-quadrant drop, and any slow turn-on penalty.
- **Sinks:** S8 production (device study `thermal.solve()`, 13 CFM, 50 °C inlet, 120 V) and the bench sink
  (bench-sink-r1 `bench_thermal.solve()`, Wakefield 511-3M in still air, SIL PAD 2000, 30 °C, 132 V). Currents: tank
  RMS at the 1.05 × trip, 18.375 A (17.5 A release ceiling) and 29.4 A (28 A route). Worst of 35 / 50 / 60 kHz.
- **Gate drive heat:** `scripts/c40_gate_heat.py` → `results/gate_heat.json`, the B3 heat file's charge split
  replicated (R_on resistor R10/R12/R18/R20, driver, bias channel current) with each part's own gate charge.

### 1.3 A measurement gap found and closed: S4 edges outside the 0.75 µs window

The S4 slew is measured inside a 0.75 µs window after the on command. With a slow turn-on network the commutation
edge can fall after the window. The row then has no 20–80 % edge, and its slew is simply missing; the summary does not
flag it.

- On the adopted CFD7 network (68 Ω / 4.7 nF) at maximum Qrr, 144 of the 336 S4 rows (all at 27 °C) have no edge in
  the window. The committed S6 / ledger value 68.16 V/ns comes from the other 192.
- Re-run in the 3.75 µs window (`s4L`, all 336 rows): **68.58 V/ns** (0.980 of 70; ESL 1.06: 67.76). At typical Qrr
  all 336 rows give 49.70 V/ns, the committed value exactly.
- For slower networks the gap hides the whole answer: CFD7 + 68 Ω / 6.8 nF reads "0 V/ns, 42/42 pass" in the short
  window and **63.76 V/ns** in the long one.
- `c20_switching.py` now reports `no_edge_rows` per grid. Every S4 number in this README comes from a grid with 0
  such rows.

## 2. Controls (all pass; `results/controls.json`, `results/qrr.json`, `results/loss_thermal.json`)

Independent re-check, 2026-10-28: `c20`, `c40`, `c50`, `c60`, `c70` and `c90` re-run gave byte-identical `results/`;
`trade.py s4b --dev sic26_15_r8p2` re-run from scratch gave 42/42 rows identical to the stored grid.

| # | Control | Result |
|---|---|---|
| K1 | Device-study repro grid (128 runs) on this harness | 128/128 bit-identical to the committed rows |
| K2 | Device-study ZVS grid (672 runs), leg A / B worst t_trans and thresholds | 188.9 / 190.36 ns, 9.11 / 9.14 A: identical |
| K3 | Device-study thermal (C1/C2 and all 120 thermal.json rows) | Δ 0.0 °C |
| K4 | Bias module loss (ALT-BIAS 3.2) | 0.983 / 1.091 / 1.706 W: identical |
| K5 | CFD7 price row (2026-10-15 snapshot) | $10.17612 at 510: identical |
| K6 | Gate-network study's 320-row repro on the control-era deck | 318/320 within 1 mV (study reported 317), S4 85.78 / 81.87 V/ns exact |
| K7 | Adopted c39 network, full 640-run grid at typical Qrr | 49.7 / 49.15 V/ns, 244 A/µs, S4 347.2 V, S2 435.0 V, t_trans 190.2 ns, off-gate +0.497 V: identical |
| K8 | Same network at maximum Qrr (S6 study) | 68.16 V/ns, 640/640: identical |
| K9 | B3 gate charge on the as-built 8.2 Ω deck | 382.6 nC (= B3 Q_DECK); c40 R10 0.217 W (= s53 B3 row) |
| K10 | Qrr fixture: CFD7 TT 50 / 125 ns, C8 600 V rows | 1.739 / 2.356 µC and the C8 rows: equal to the committed qrr.json |
| C1/C2 | Loss path through S8 and the bench tool with the device-study grid | Δ 0.0 °C against DS thermal.json and bench-sink-r1 thermal.json |
| C3 | This study's generic die-energy measure (long window) on the 8.2 Ω deck vs the device study's vendor heat channels | S8 Tj within 0.084 K |
| R1 | Coil model, R1 with its own constants | equal to the committed system.json summaries |

K6 note: the current `gn.py` deck carries par() measures added after the study's controls ran. ngspice turns them into
B-sources and moves rows by up to 0.46 V / 0.17 V/ns. With them stripped the deck reproduces the study; every grid in
this study uses the gn deck as it is now, and K7/K8 show that deck reproduces the committed decision grids exactly.

## 3. Candidate 1: IPW65R018CFD7 (today's part)

**As built (s42 on: R_on 68 Ω 2512 + Cgs 4.7 nF, PMEG + 1 Ω turn-off).**

- **S4 diode dv/dt (S14):** 49.70 V/ns at typical Qrr (0.71 of 70, pass) and **68.58 V/ns at maximum Qrr (0.98 of
  70)**, all 336 S4 rows in the long window (`sims/cfd7_c39_tt125/s4L`, `cfd7_c39_tt260/s4L`). Under the rating,
  over the 56 V/ns 80 % screen. **S14 stays open on the maximum-Qrr basis.** The ledger's bounding value 68.16 V/ns is
  0.42 V/ns low (section 1.3).
- diF/dt 244 A/µs (0.19 of 1,300). S4 die VDS 383.9 V. S2 435.0 V. ZVS 80/80, worst t_trans 190.2 ns (150 ns margin
  to the 340 ns audit edge). Off-gate +1.57 V at maximum Qrr. 640/640 rows pass the c25 screens.
- **A bigger Cgs does not close it.** 68 Ω + 6.8 nF gives 63.76 V/ns at maximum Qrr (0.91; `cfd7_r68c6p8_tt260/s4bL`),
  still over 56, and turns on slower.
- **Loss and Tj** (worst of 35/50/60 kHz, 60 kHz binds): S8 68.4 °C at 17.5 A, 91.2 °C at 28 A (limit 150 °C);
  4.7 / 13.7 W per device, of which switching and dead time 0.41 / 1.0 W. Bench sink 88.5 °C at 17.5 A.
  The adopted network's slow turn-on costs about +0.2 W per device at 17.5 A and +0.5 W at 28 A against the as-built
  8.2 Ω deck (67.8 / 89.8 °C), from the same measure (control C3).
- **Gate drive:** 382.6 nC + 61 nC (Cgs) per edge, R_on 0.217 W at 60 kHz (the binding B3 row, +1.3 K at 17.5 A).
- **Market [VEN, 2026-10-27]:** $11.42 / $10.18 each at 80 / 2,000 pcs, $45.68 / $40.70 per board at 20 / 500
  boards; DigiKey 459 in stock, 8 weeks.

## 4. Candidate 2: IPW65R018CM8 (650 V CoolMOS 8)

**New input: Infineon now publishes a model of this exact part** (650 V CoolMOS 8 SPICE library v01_00, 2025-05-07;
`IFX_C8_650V.lib`, sha256 `b9d1c19e…345f`). It replaces DECISIONS 54's proxy (the 600 V IPW60R016CM8 model).
Its body diode gives 1.10 µC at the datasheet test, under the datasheet's 1.54 µC typical, so TT 100 / 180 ns is used
for typical / maximum (section 1.1). Package U06 sits inside the CFD7 footprint tolerances (DECISIONS 49); same
G-D-S pinout.

**The DECISIONS 54 route (CM8 + 39 Ω, Cgs 1 nF) fails S4 once Qrr is put on the datasheet.**

| Qrr basis | S4 dv/dt V/ns (ratio to 70) | S4 die VDS | diF/dt A/µs |
|---|---|---|---|
| model's own (1.10 µC) | 39.94 (0.57) | 371.8 V | 563 |
| datasheet typical (1.54 µC) | **68.69 (0.98)** | 513.7 V | 563 |
| datasheet maximum (2.31 µC) | **95.74 (1.37)** | **525.8 V** (1 row over 520) | 563 |

The proxy's 40.6 V/ns matches the first row; the proxy study never forced Qrr up to the datasheet.

**No network tried both closes S14 at maximum Qrr and stays inside the turn-on budget.** All rows below are at maximum
Qrr (TT 180); "turn-on" is the incoming gate voltage 1 / 2 µs after its on command in the gate-network study's
`slowgate` rows (its criterion: the current zero comes ≥ 2.08 µs after switching at 60 kHz and 45° lag). The adopted
CFD7 network is the budget: 4.37 / 9.04 V (control, equal to the committed values).

| CM8 network | S4 dv/dt max Qrr (typ) | other screens | turn-on 1 / 2 µs |
|---|---|---|---|
| 39 Ω / 1 nF | 95.7 (68.7) | full grid 639/640: one S4 row at 525.8 V (screen 520) | 10.78 / 13.98 V |
| 68 Ω / 1 nF | 75.4 (58.1) | S4 set and S2 rows pass | 6.85 / 11.57 V |
| 82 Ω / 1 nF | 72.0 (46.8) | S4 set passes | – |
| **100 Ω / 1 nF** | **66.4 (45.3)** | full grid 640/640 at max Qrr: S2 488.5 V, S4 371.5 V, off-gate +1.33 V, t_trans 116.4 ns | **3.76 / 9.00 V** (at the budget) |
| 120 Ω / 1 nF | 59.4 | S4 set passes | 2.51 / 7.65 V (too slow) |
| 150 Ω / 1 nF | **50.0** | full grid 640/640 | 1.10 / 5.93 V (too slow) |
| 47–82 Ω / 2.2 nF | 65.8–78.5 | off-gate 2.2–2.6 V at 150 °C (hot screen 1.9 V); S2 539–541 V | – |
| 68 Ω / 4.7 nF (s42 network, FET swap only) | 59.7 (39.3) | **S2 607.9 V** (screen 585); off-gate up to 4.2 V; 301/640 hot pass | 6.25 / 10.74 V |
| 68 Ω / 6.8 nF | 50.8 (30.5) | **S2 660.9 V** (over the 650 V rating); off-gate 4.2 V; 484/640 | – |

- **Why Cgs hurts the CM8 and not the CFD7:** the CM8's internal gate resistance is 1 Ω (model 0.86 Ω) against the
  CFD7's 2.7 Ω. With a large external Cgs at the pins, the die gate loop is poorly damped. In the S2 row (weak driver,
  27 °C, 280 V, 71 A) the gate re-rises during the fast turn-off and the die sees 660.9 V; the same row with 1 nF
  peaks at 472.5 V (`results/waveforms/`, `scripts/c26_waveform.py`). So a CM8 swap onto today's s42 board is not
  safe: Cgs must go back to 1 nF.
- **Best CM8 inside the budget: 100 Ω / 1 nF.** Maximum Qrr 66.4 V/ns (0.95 of 70), typical 45.3 V/ns (0.65).
  This is the same status as the CFD7 (0.98): under the rating, over the 80 % screen. CM8 does not fix S14.
- **Loss and Tj (100 Ω / 1 nF, `sims/cm8_r100/energy`):** S8 68.4 °C at 17.5 A, 90.0 °C at 28 A (limit 150 °C;
  175 °C for ≤ 50 h); four-device loss 19.0 / 52.7 W. Bench 88.7 °C at 17.5 A. The same as the CFD7 within 1.2 K:
  equal RDS(on), slightly lower RthJC (0.24 against 0.28 K/W), slightly more slow-turn-on loss.
- **Gate drive (c40):** 288.0 nC per edge on the B3 basis (worst S2 charge on the 8.2 Ω deck; CFD7 382.6 nC), and no
  extra Cgs charge. R_on 0.145 W against 0.217 W, bias channel 40.2 against 49.5 mA. R10's derating limit rises
  by at least 7.7 K, to about +9.0 K at 17.5 A [EST, lower bound on R10 only].
- **Market [VEN, 2026-10-27]:** $9.77 / $8.48 each, $39.06 / $33.93 per board: **−$6.62 / −$6.77 per board** at
  20 / 500 boards. **DigiKey stock: 2 pieces, 24 weeks.** That alone rules it out for a prototype lot this quarter.

## 5. Candidate 3: 650 V SiC MOSFETs

Three parts were chosen from DigiKey stock (all TO-247-3, G-D-S, 5.44 mm pitch except onsemi's 5.56 mm). Only the
Infineon part has a usable model here.

| | IMW65R026M2H (CoolSiC G2) | C3M0025065D (Wolfspeed) | NTHL032N065M3S (onsemi) |
|---|---|---|---|
| RDS(on) 25 °C | 26 / 33 mΩ typ / max at 18 V; 34 typ at 15 V (p.6) | 25 / 34 at 15 V (p.2) | 32 / 44 at 18 V; 41 typ at 15 V (p.2) |
| RDS(on) hot / 25 °C | 1.35 (15 V) / 1.65 (18 V) at 175 °C (p.10, figures) | 1.31 at 175 °C (p.4) | 1.27 at 175 °C, 15 V (p.2) |
| RthJC | 0.66 K/W max (p.4) | 0.46 typ (p.3) | 0.75 (p.2) |
| Gate | rec. 18 / 0 V; −7 / +23 V static (p.3, p.5) | rec. 15 / −4 V; −8 / +19 V (p.1–2) | rec. 18 / −5…−3 V; −10 / +22.6 V (p.1–2) |
| VGS(th) min | 3.5 V (25 °C) | **1.8 V; 1.9 V typ at 175 °C** | 2.0 V |
| Body diode | VSD 4.3 V; Qfr 129 nC (p.7) | VSD 5.0 V; Qrr 261–309 nC at 175 °C | VSD 4.5 V; Qrr 67 nC |
| dv/dt rating | MOSFET 200 V/ns; no diode rating | none | none |
| SC / avalanche | none / EAS 200 mJ | none / none | none / EAS 139 mJ |
| Model | Infineon G2 library v1380 (used) | behind a terms-of-use click (not accepted) | none published |

**IMW65R026M2H, simulated** (board rails +15 / −1.6 V, R_on 8.2 Ω / Cgs 1 nF, i.e. the s29–s41 values):

- **S14 is closed by the device itself.** The SiC body diode stores almost no charge (model 0.08–0.16 µC against the
  CFD7's 2.3–4.6 µC; `qrr.json`). S4 slew is **11.8 V/ns** on the full grid (`sims/sic26_15_r8p2/full`), 0.06 of the
  200 V/ns MOSFET rating. The datasheet gives no reverse-diode dv/dt or diF/dt rating, so the 80 % rule has nothing
  to bind; the S4 di/dt is 2,227 A/µs with a 13.3 A recovery peak.
- Full grid 640/640: S2 433.4 V, S4 339.0 V, off-gate max +0.45 V, ZVS 80/80, worst t_trans **42.4 ns** (CFD7 190 ns).
  At +18 V (s4b set): 11.5 V/ns, S4 387.6 V, off-gate −0.23 V.
- **Loss.** RDS(on) is about twice the CFD7's, and the 4.3 V third-quadrant drop during dead time adds
  2.1–3.4 W per device at the 569 ns dead-time edge. With the dead time as built, the four devices dissipate
  40.5 W at 17.5 A against 18.7 W (S8, 60 kHz), and 101 W at 28 A against 54 W.
- **Shorter dead time.** t_trans is 42 ns, so DT can drop to 200 ns (R9 / R17 49.9 k → 20 kΩ; 2EDR8259X
  t_dt = 10 ns × R_DTC[kΩ], Rev 1.7 p.3, p.8). That cuts the dead-time part from 2.13 to 0.87 W at 17.5 A.
  ZVS holds at the dead time's −15 % edge (170 ns) down to 5 A: 48/48 rows at 5, 8, 12, 20 and 37 A, 14/48 at 3 A
  (`sims/sic26_15_r8p2/zvs170`, 288 runs, worst t_trans 161.6 ns at 5 A). The CFD7 needs 11.65 A at 340 ns (K2).
- **Tj** (S8, worst of 35–60 kHz, DT 200 ns): **82.5 °C at 17.5 A, 125.6 °C at 28 A** (limit 175 °C; CFD7 68.4 /
  91.2 °C against 150 °C). Four-device loss 35.3 / 93.3 W (CFD7 18.7 / 53.8 W). The S8 sink base rises to 67.1 /
  84.8 °C (CFD7 62.0 / 72.8 °C) in the device-study model; DECISIONS 14 quotes a 98.3 °C sink-trip low corner.
  Bench sink at 17.5 A: Tj 115.8 °C, sink 86.1 °C (CFD7 88.5 / 73.5 °C), 12 K under that trip at 30 °C ambient.
- **+18 V drive** buys 4.2 K at 17.5 A and 8.6 K at 28 A (78.3 / 117.0 °C at DT 200 ns) but needs a new bias rail:
  VDD would be 19.6 V across the 2EDR8259X, whose operating maximum is 21 V; today's span-OV corner is 18.64 V at
  16.6 V nominal (DECISIONS 62), so an 18 V drive would sit over 21 V at its upper corner. Not worth it.
- **Gate drive:** 61.3 nC per edge (CFD7 382.6), R_on 0.022 W, bias channel 26.6 mA against 49.5 mA. R10 stops being
  the binding release row (its derating limit rises by about 21 K [EST, lower bound]); the next B3 rows (laminate at
  the R12 gate pad +3.8 K, R20 +4.2 K) then bind until B3 is re-solved with the lower gate heat.
- **Market [VEN, 2026-10-27]:** $8.38 / $7.09 each; $33.50 / $28.35 per board, **−$12.18 / −$12.35 per board** at
  20 / 500 boards. DigiKey 270 in stock, "no backorders" (constrained supply).

**IMW65R026M2H on the s42 network unchanged (68 Ω / 4.7 nF, the FET-only swap; `sims/sic26_15_r68c4p7`):**

- Full grid 640/640: S4 **3.85 V/ns**, diF/dt 168 A/µs, S2 457.9 V, off-gate −0.88 V, t_trans 56.5 ns. Gate at
  12.7 / 14.4 V 1 / 2 µs after the on command (CFD7 4.37 / 9.04 V): no turn-on-delay issue.
- Loss at DT 200 ns: S8 86.7 / 133.4 °C, four-device 41.0 / 103.5 W, bench 124.8 °C with the sink at 90.9 °C. The
  slower turn-on leaves the body diode carrying the current longer (dead-time part 2.25 W against 0.87 W per
  device at 17.5 A). R_on 0.061 W.
- With the dead time left as built (R9 / R17 49.9 kΩ, 569 ns edge) the FET-only swap runs S8 90.6 / 139.4 °C and the
  bench sink reaches 95.8 °C, 2.5 K from the trip. The dead-time change is needed with any SiC part.
- ZVS at the 170 ns dead-time edge: 48/48 rows from 8 A up, 43/48 at 5 A, 0/48 at 3 A (`zvs170`; 8.2 Ω / 1 nF:
  48/48 at 5 A). The 4.7 nF Cgs slows the outgoing device's turn-off a little (t_trans 56.5 against 42.4 ns at 37 A).

**C3M0025065D and NTHL032N065M3S (datasheet only, IMW65R026M2H switching grid as stand-in [EST]):**

- C3M0025065D runs cooler (S8 79.8 / 114.1 °C at 17.5 / 28 A, DT 569 ns) because of its 0.46 K/W RthJC, and is
  cheaper ($26.60 per board at 500). But its 1.8 V threshold (1.9 V typ hot) sits at the board's 1.9 V hot off-gate
  screen with only −1.6 V off-bias; Wolfspeed recommends −4 V. It needs its model (one terms-of-use click by the
  owner) and an off-gate re-run before it can be ranked above the G2.
- NTHL032N065M3S is the cheapest SiC ($17.17 per board at 500) and has the most stock (845 + 5,850 at the factory),
  but at 15 V it is hot (95.4 / 157.8 °C) and its 5.56 mm lead pitch does not fit the 5.44 mm footprint without a
  layout change.

## 6. Candidate 4: 650 V reverse-conducting IGBTs

Parts: Infineon IHW40N65R6 (RC-H6, made for induction cooking) and IHW40N65R5 (RC-H5). Same TO-247-3 G-C-E pinout
and 5.44 mm pitch as today (R5 p.13; R6 p.13 uses the CFD7's own outline drawing, Z8B00003327 rev 06). Neither
states a short-circuit rating (neither does the CFD7). Simulated with Infineon's L1 models on the board's 8.2 Ω /
1 nF network and the as-built 1 nF snubber.

**4a: drop-in at 35–60 kHz.**

- **Conduction dominates.** The IGBT's ~1 V knee costs 11.1 W per device at 17.5 A (CFD7 4.3 W) and 21.2 W at 28 A
  (CFD7 12.7 W), from the datasheet VCE(sat) / VF fits (R6 p.3, p.5, p.8, scaled to the 25 °C max/typ ratio).
- **Turn-off tail:** 189 µJ per edge at 40 A, 170 V, 150 °C (CFD7 33 µJ), from the R6 model (`sims/rch6_r8p2/eAs`).
  The datasheet's soft-switching value, 0.22 mJ at 162 V, 40 A, Cr 30 nF, 175 °C (R6 p.5), is the same size.
  It adds 2.9 W per device at 17.5 A and 5.5 W at 28 A at 60 kHz.
- **Tj (R6, S8):** 98.4 °C at 17.5 A, 136.4 °C at 28 A (limit 175 °C); the diode region runs a further 5.8 / 11.0 K
  hotter through its 2.77 K/W RthJC (R6 p.6) against 0.71 K/W for the IGBT (p.5) [EST]. Four-device loss
  **55.9 / 105.9 W** (CFD7 18.7 / 53.8 W).
- **Bench sink at 17.5 A: 108.7 °C**, over the 98.3 °C sink-trip low corner (DECISIONS 14): the bench rig would trip.
- ZVS holds at every energy-grid row from 5 A (t_trans ≤ 157 ns at DT 569 ns).
- **S4 (the S14 case) could not be simulated.** The R6 model aborts at its diode's hard recovery: the first 19 S4
  rows all stopped with "timestep too small" in the model's diode, as the c05 recovery fixture did. The datasheet
  gives the RC diode 2.16 µC at 25 °C and 3.77 µC at 175 °C (400 V, 40 A, 1,000 A/µs; R6 p.6), about the CFD7's
  charge, and no dv/dt or diF/dt rating. So the IGBT does not remove the S14 mechanism, and nothing rates it.
- **IHW40N65R5:** its L1 model's loss grid did not finish. 16 of 216 rows (all at the 20 V bus) aborted with
  "timestep too small", and their 0.1 ns retries hit the 30 min ngspice timeout (`sims/run_all.log`). Its datasheet
  VCE(sat) and VF are higher than the R6's (1.35 / 1.7 V against 1.29 / 1.6 V typ / max at 40 A; VF 1.7 against
  1.5 V) and it gives only hard-switched Eoff, so it would run at least as hot as the R6. Not ranked separately.

**4b: retuned to 20–30 kHz** (coil study system model, `scripts/c60_retune.py` → `results/retune.md`).

- The tank must resonate lower: today's R1 coil (81 µH) with the 0.5 µF bank resonates at 27–41 kHz on the pans, so
  a 20–30 kHz window needs about 1.0–1.25 µF (10–13 B32643 caps instead of 5) and ideally ~15 % more turns.
- Power coverage at the 17.5 A release ceiling (share of the FEM pan set reaching the 1,239 W hold):

  | Coil / bank / window | full power, 17.5 A | operable, 17.5 A | full power, 28 A | P min / median |
  |---|---|---|---|---|
  | R1 / 0.5 µF / 35–60 kHz (today) | 24 % | 99 % | 63 % | 780 / 1,041 W |
  | R1 / 1.25 µF / 20–30 kHz | 22 % | 48 % | 55 % | 1,029 / 1,286 W |
  | R43 (87.7 µH) / 1.0 µF / 20–30 kHz | 35 % | 47 % | 43 % | 1,003 / 1,359 W |
  | R1 × 1.15 turns [EST] / 1.25 µF / 20–30 kHz | 25 % | 81 % | 72 % | 693 / 1,105 W |

  With both the coil and the bank changed, the full-power share matches today's (25 against 24 %), but 19 % of the
  pans still cannot be driven at all (today 1 %). Without the turns change, about half cannot.
- **Loss at 20–30 kHz (R6):** the tail halves (1.5 W per device at 17.5 A), conduction does not change. S8 Tj 93.9 /
  127.4 °C; four-device loss 49.9 / 94.1 W; bench sink 100.8 °C at 17.5 A, still over the 98.3 °C trip.
- **Forced changes:** coil rewind (+15 % turns), bank 5 → 12–13 capacitors, firmware frequency window and the
  pan-detect / lag tables, new dead time, bench and S8 thermal re-runs, and 20 kHz is at the edge of hearing.
- **Market [VEN, 2026-10-27]:** $2.15 / $1.37 each; **$8.62 / $5.46 per board** (−$37.06 / −$35.24 at 20 / 500
  boards). DigiKey 104 (R6) and 239 (R5) in stock, 36 weeks. IHW30N65R5 is last-time-buy (2027-03-15).
  The extra bank capacitors and the coil change eat part of the saving (not priced here).

## 7. Candidate 5 (reference): GaN

Renesas TP65H035G4WS (35 mΩ cascode GaN, DigiKey 803 in stock, $5.88 at 510 [VEN, 2026-10-27]): its pinout is
G-S-D with the tab on source, so it does not fit the G-D-S footprint, and no SPICE model was found. Not simulated.
A GaN switch would also need the gate network, the snubber and the heatsink insulation redone. Reference only.

## 8. Footprint and pin compatibility

| Part | Package | Pinout | Lead pitch | Drop-in? |
|---|---|---|---|---|
| IPW65R018CFD7 | PG-TO247-3 | G-D-S, tab D | 5.44 | today |
| IPW65R018CM8 | PG-TO247-3-U06 | G-D-S, tab D | 5.44 | yes (DECISIONS 49) |
| IMW65R026M2H | PG-TO247-3-40 | G-D-S, tab D | 5.44 | yes |
| C3M0025065D | TO-247-3 | G-D-S, tab D | 5.44 | yes |
| NTHL032N065M3S | TO-247-3LD | G-D-S, tab D | **5.56** | lead pitch differs |
| IHW40N65R6 / R5 | PG-TO247-3 | G-C-E (tab not stated; same outline as the CFD7) | 5.44 | yes |
| TP65H035G4WS | TO-247-3 | **G-S-D, tab S** | not read | no |

## 9. Scripts, results, re-running

Vendor files live outside git in `C55_DL` (default `worktrees/runs-native21/c55-dl`), sha256-checked on load
(`scripts/wrappers.py`). `sims/` decks and per-grid `results.json` are committed (about 20 MB) so the summaries can be
regenerated without re-running the grids; the run logs and the dialect copies of vendor libraries are gitignored. The
decks `.include` the vendor libraries from `C55_DL` and contain no vendor model text.
No cargo, make, chain or router run; ngspice and Python only, on the Mac.

| Script | Does | Output |
|---|---|---|
| `c00_controls.py` | K1–K7 reproduction controls | `results/controls.json` |
| `c05_qrr.py` | recovery-charge fixture, TT calibration | `results/qrr.json` |
| `trade.py <grid> --dev <config>` | one grid for one configuration (`devices.py`, `wrappers.py`, `devlib.py`) | `sims/<config>/<grid>/results.json` |
| `run_all.sh`, `run_cm8_net*.sh`, `run_cm8_sel.sh`, `run_cm8_typ.sh`, `run_s4long.sh`, `run_s4full_long.sh`, `run_slowgate.sh`, `run_sic_dt.sh`, `run_sic_s42.sh` | the queues actually run (skip-if-done) | `sims/` |
| `c20_switching.py` | switching summaries against each part's ratings (`device_data.json`) | `results/switching.json`, `.md` |
| `c26_waveform.py` | one row with waveforms | `results/waveforms/` |
| `c40_gate_heat.py` | B3 gate-heat split per candidate | `results/gate_heat.json` |
| `c50_loss_thermal.py` | loss, S8 and bench Tj (controls C1–C3 asserted first) | `results/loss_thermal.json`, `.md` |
| `c60_retune.py` | 4b tank retune on the coil model | `results/retune.json`, `.md` |
| `c70_cost.py` | per-board cost from the DigiKey read | `results/cost.json` |
| `c90_summary.py` | one row per candidate from the files above | `results/summary.json`, `.md` |

Market evidence: `market/` (`SOURCES.md` how it was read, `distributor-2026-10-27.csv`, `datasheets.json` with
page numbers, `models.json`).

## 10. Datasheets and models (outside git)

| File | URL | sha256 |
|---|---|---|
| IPW65R018CFD7 datasheet Rev 2.0 | infineon.com/assets/row/public/documents/24/49/infineon-ipw65r018cfd7-datasheet-en.pdf | c364050a04a434bd173da6486fd51f4baf540ee9e4e1ebbe07aed57e279943f2 |
| IPW65R018CM8 datasheet Rev 2.1 | infineon.com/assets/row/public/documents/24/49/infineon-ipw65r018cm8-datasheet-en.pdf | 426b5d3147287c70318c4d05782bf4704d4e50081aee50c45cc8aae5868d97c7 |
| 650 V CoolMOS 8 library (IFX_C8_650V.lib) | infineon.com/content/dam/infineon/row/public/documents/24/50/infineon-spice-model-library-650-v-coolmos-8-simulationmodels-en.zip | lib b9d1c19ea90cf886d758b46b732951d925464b147f0294e1e91439a77998345f |
| IMW65R026M2H datasheet Rev 2.0 | infineon.com/assets/row/public/documents/24/49/infineon-imw65r026m2h-datasheet-en.pdf | 7b810f06dbeae3a35f9511c146d7bffca83aee6496d836bef73d58031075316c |
| CoolSiC G2 650 V library v1380 | infineon.com/content/dam/infineon/row/public/documents/24/50/infineon-coolsic-mosfet-g2-650-v-g2-spice-simulationmodels-en.zip | lib 60a00c18f31246d6dcc2ed81050bd875ba601dc8f40d914e6d9a00dd86b28f43 |
| C3M0025065D datasheet Rev 04 | assets.wolfspeed.com/uploads/2024/01/Wolfspeed_C3M0025065D_data_sheet.pdf | 7ba816685b21fce5f26e2b59df96956d91cbb380277489722b28aadcc8b944f2 |
| NTHL032N065M3S datasheet Rev 9 | onsemi.com/download/data-sheet/pdf/nthl032n065m3s-d.pdf | 9528955794b5939c091b9b94ae5ce23bf63cdbf5eb48948976782981ad830e50 |
| IHW40N65R6 datasheet Rev 1.20 | infineon.com/assets/row/public/documents/24/49/infineon-ihw40n65r6-datasheet-en.pdf | 66ee1cfb5a9c0afdc33c968f877604c48887f812fae3997f89782ffbe2e585c9 |
| RC-H6 L1 library | infineon.com/content/dam/infineon/row/public/documents/24/50/infineon-spice-l1-igbt-650v-trenchstop5-r6-simulationmodels-en.zip | lib 35c3b4215348929aba2889f060f0945b575ef590e2afecd349e68810c14ee9e3 |
| IHW40N65R5 datasheet Rev 2.3 | infineon.com/assets/row/public/documents/24/49/infineon-ihw40n65r5-datasheet-en.pdf | f58f5442c631a7cd338842a6c7f107c7a93c43c26925af73a11a37baf690dcae |
| RC-H5 L1 library | infineon.com/content/dam/infineon/row/public/documents/24/50/infineon-spice-l1-igbt-650v-trenchstop5-r5-simulationmodels-en.zip | lib b54e89a2215278201e8b24a20e12c5a2c4b8dc30301ea1a7c263bed65f5eca55 |
| TP65H035G4WS datasheet | renesas.com/en/document/dst/tp65h035g4ws-datasheet | 6cd26bbd035c7907ba359abcb8ec1a429863d9b07a20d1bd52b4547f562a91fc |
| 2EDR8259X datasheet Rev 1.7 | infineon.com/assets/row/public/documents/24/49/infineon-eicedriver-2edr8259h-2edrx259x-2edrx258x-datasheet-en.pdf | f49391ca00e15397076dfc7482f56b0a1ea794a5249f1d14a1a60bb5ef33ae33 |

ngspice dialect copies (written outside git by `wrappers.py`, rebuilt from the vendor file on every run): the G2
library's one `.FUNC VGCHAN` line (PSpice `ARCTAN` and `=`), and the RC-IGBT libraries' `TJ={TEMP}` default.

## 11. Limits

- Switching results rest on vendor SPICE models. For CoolMOS the Qrr is forced to the datasheet value through TT,
  which is the gate-network study's method, not a measurement. The D-8 double pulse is still the arbiter.
- The S4 diode limits are judged at the datasheet maximum Qrr at 25 °C, as the S6 study did. Qrr grows with Tj.
- SiC third-quadrant and IGBT tail losses come from the vendor models' own dynamics; neither was checked against a
  measurement here.
- C3M0025065D and NTHL032N065M3S have no model in this study (Wolfspeed's needs a terms-of-use click that was not
  given; onsemi publishes none for 650 V M3S). Their loss uses their own datasheet RDS(on) and RthJC with the
  IMW65R026M2H switching grid as a stand-in [EST].
- The RC-IGBT conduction fits use typical curve points scaled by the 25 °C max/typ ratio; the diode V0 (0.9 V) is an
  [EST]. The diode region is treated with the IGBT RthJC, and the extra rise of the diode region is given separately.
- The retune (4b) uses the coil study's first-harmonic system model on its FEM pans; the turns-scaled coils are an
  [EST] trend, not an FEM solve.
- Prices are DigiKey list prices read on 2026-10-27; Mouser served a bot check and was not read. No part has 2,000
  pieces in DigiKey stock. Quotes are still owed.
- The R10 margin change from gate charge is a lower bound on the R10 row only; the next B3 rows were not re-solved.
- The RC-IGBT S2 rows (`trade.py s2q --dev rch6_r8p2__q`) were stopped unfinished: the vendor model aborts or runs past
  the 30-minute row timeout, as in its S4 and R5 eAs grids. The IGBT therefore has no simulated gate charge or S2 VDS,
  and the gate-heat table has no row for it. This does not change the ranking, since the IGBT fails on loss first.
