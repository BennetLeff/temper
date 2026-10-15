> **Committed 2026-10-15 by the integration session (DECISIONS 54).** Not committed: `sims/` (27 MB of decks and
> phase logs) and `dl/` (vendor models and datasheets; sha256 listed below). The scripts keep the absolute scratch paths
> they ran with; they are a record, and re-running them needs `dl/` restored beside `scripts/`.

# Gate network for the S4 reverse-diode dv/dt (DECISIONS 49, candidate 39): study 2026-10-15

The PS repo (`worktrees/ps-integrate/zapote/power-stage-120v`, branch codex/power-stage-integration) was only read.
Every number below comes from `scripts/` and the result files in `results/`. `scripts/run_all.sh` re-runs the whole
chain (4 ngspice workers, about 6 h on a loaded Mac). The `run_phase*.sh` scripts are the queues that were actually
used.

## 0. The as-built network is already split

`elec/src/power_stage_120v.ato:159-188` defines the network, and the deck models it:
- `r_gh` / `r_gl` (R10/R12/R18/R20, RS-06L8R20FT 8.2 ohm 1206) run from the driver OUT to the gate;
- `doff` is a PMEG6030EP whose anode is at the gate;
- `roff` (R53/R54/R57/R58) is 1 ohm 1206W4F100KT5E, from the diode cathode to OUT;
- Cgs is 1 nF C0G.

The c25/device-study deck has the same branch (`XDoffl gdl3 offl PMEG6030EP`, `Roffl offl gdl 1.34482758621`). The
only difference is the deck's 1.345 ohm against the BOM's 1 ohm, which is a D6 leftover (3.9 || 1.345 = 1). Control:
1 ohm against 1.345 ohm moves S4 by at most 0.42 V/ns and 0.75 V.

So option (b) needs no new parts. It is the existing network with a larger turn-on resistor; the PMEG + 1 ohm
turn-off path and its diode stay as they are.

## 1. Baseline (as-built deck, 2EDR8259X, 8.2 ohm, ESL 10 / 1.06 nH)

**Reproduction control:** `sims/asbuilt/repro` is checked against 320 committed device-study edge/edge2 rows.
- 317/320 rows agree within 1 mV.
- The largest difference is 0.2 V die VDS on one S4 row, and 0.0004 V/ns on slew.
- 8/8 energy rows reproduce exactly.
- S4 max slew is **85.78 / 81.87 V/ns**, identical to the committed rows.

**diF/dt of the commutated body diode:** measured on the die drain current, as a chord from 75 % to 25 % of IF.

| case | S4 slew 20-80 % ESL 10 / 1.06 | S4 diF/dt 75-25 % (50-0 %) | S4 Irr peak | S4 rows at or under 1,040 A/us | S5 slew |
|---|---|---|---|---|---|
| as-built, full grid (640 runs) | 85.8 / 81.9 V/ns | **2,101 A/us** (2,538) | 98 A | 0/336 | 72.0 / 71.8 V/ns |

S5 (0 A) has no diode conduction before the edge, so diF/dt does not apply there. The partner sees only Coss
displacement and ringing (up to 76 A peak).

The as-built network therefore breaks both diode limits:
- dv/dt: 70 V/ns rating, 56 V/ns at 80 %;
- **diF/dt: 1,300 A/us rating, 1,040 A/us at 80 %.** The diF/dt limit is broken by 1.6x of the rating and 2.0x of
  the 80 % limit.

## 2. Mechanism, and the model's recovery charge

The S4 edge is the body diode's recovery snap: Irr is driven into Coss. It is not the Miller plateau. The evidence:
- R_off has no effect;
- an external Cgd of 47 pF moves the slew by only 3-8 V/ns;
- the 20-80 % slew follows Irr.

Two consequences:
- The dv/dt falls only when the channel di/dt, and with it Irr, falls.
- The dv/dt depends directly on how much charge the model's diode stores.

`scripts/qrr.py` measures each model's recovery in the round-17 D3 datasheet fixture (400 V, 100 A/us):

| model | Qrr in the model | datasheet typ / max | note |
|---|---|---|---|
| IPW65R018CFD7_L1 (vendor, TT 50 ns) | 1.739 uC (control: D-24 1.73882) | 2.30 / 4.60 uC | 24 % under typical |
| same, TT 125 ns | 2.356 uC (control: D-24 2.35560) | | about typical |
| IPW60R016CM8_L1 (C8 vendor, TT 25 ns) | ~1.21 uC at 100 A/us | 1.54 / 2.31 uC (IPW65R018CM8 Rev 2.1 is identical) | 21 % under typical |
| same, TT 60 / 80 ns | ~1.35 / ~1.47 uC | | TT 80 ns is about typical |

Both vendor models therefore recover with less charge than the datasheet typical. This study rates the networks on two
bases, the vendor model and typical Qrr. Nothing tested meets the limit at maximum Qrr (TT 260 ns: 106-112 V/ns).

## 3. Options on IPW65R018CFD7

Detailed tables are in `results/s4screen.md`, `s4b.md`, `full.md`, `ron_power.md` and `summary.json`.

Grids used:
- **s4screen:** 280 V only.
- **s4b:** the binding S4 set: leg A, HS turning on, 170/198/280 V, every driver and temperature corner, both ESL,
  DT 600.
- **full:** 640 runs per configuration: S1 at DT 340 and 408, S2, S4 and S5 at both ESL, legs A and B, 3 temperatures
  plus the weak and strong driver corners.

The 280 V screen is not conservative once R_on rises. Above about 30 ohm the worst S4 row moves to **198 V / 27 C /
leg A**. Decisions use the s4b and full grids only.

- **(a) Symmetric R, diode branch deleted (10-22 ohm): rejected.**
  - The off-gate reaches 2.0-5.8 V; S4 hot passes are 0/56 at 12 ohm and above.
  - ZVS turn-off loss explodes (15 ohm: E_off at S1 37 A is 238 uJ against 9.2).
  - At 22 ohm the 33 V/ns slew is a false turn-on of the partner, not a fix.
  - Control: the split deck with the diode shorted and R_on = R_off = 2R matches symmetric R within 0.02 V/ns
    (12 and 22 ohm). The 1-Gohm "open" fallback matches the deleted branch within 0.013 V/ns.
- **(a') R_ext only, the device study's convention (as-built branch kept), 10-22 ohm:** 83.0 -> 70.2 V/ns. Not enough.
- **(b) R_on 15-47 ohm with R_off 1 / 4.7 / 8.2 ohm:**
  - R_off moves the slew by 0.4 V/ns or less, but raises the off-gate from -1.4 V to +0.46 V. Keep 1 ohm.
  - Full grid, vendor Qrr: 39 ohm gives 55.9 / 55.5 V/ns; 47 ohm gives 53.3 / 52.5 V/ns. diF/dt is 556 and 478 A/us.
    Every screen passes (640/640).
  - At typical Qrr: 39 ohm gives 80.1 and 47 ohm gives 72.0 V/ns. Both fail.
- **(c) Cgs 2.2 / 4.7 nF (C55/C56/C62/C63 value change), at typical Qrr:**
  - 56 ohm + 4.7 nF: 54.8 / 54.2 V/ns, full grid at TT 125 is 640/640.
  - 68 ohm + 4.7 nF: 49.7 / 49.2 V/ns, full grid at TT 125 is 640/640 (section 3b).
  - 100 ohm alone: 51.1 V/ns, full grid at TT 125 is 640/640, but the gate is only 3 V at 1 us.
  - The off-gate rises because of the slower tail (up to +0.76 V), still under 1.9 V.
- **(d) External Cgd 10-47 pF (drain to gate): rejected.** It gives 3-8 V/ns for a 650 V part on the gate.

### 3a. Pareto set (CFD7)

| network | S4 V/ns, vendor Qrr (full) | S4 V/ns, typical Qrr | diF/dt A/us | S1 worst t_trans / ZVS | E_off S1 37 A | gate V at 1 / 2 us (S1) | conduction penalty per edge, S1 37 A (3.75 us window) | R_on power at 60 kHz | change |
|---|---|---|---|---|---|---|---|---|---|
| as-built 8.2 ohm | 85.8 | 109-112 (VDS 620 V, fails) | 2,101 | 190 ns / 80/80 | 9.2 uJ | 14.9 / 14.5 | 0 | 0.192 W | - |
| 39 ohm | 55.9 | 80.1 | 556 | 186 ns / 80/80 | 8.7 | 9.1 / 13.0 | +2.2 uJ | 0.215 W | R value + 2512 |
| 47 ohm | 53.3 | 72.0 | 478 | 186 / 80/80 | 8.7 | 7.9 / 12.2 | +2.9 uJ | 0.208 W | R value + 2512 |
| 56 ohm + Cgs 4.7 nF | (lower) | **54.8 (full, 640/640)** | 278 | 190 / 80/80 | 9.0 | 6.1 / 10.4 | +4.1 uJ | ~0.18 W at 444 nC | R + Cgs value |
| 68 ohm + Cgs 4.7 nF | (lower) | **49.7 / 49.2 (full, 640/640)** | 244 | 190 / 80/80 | 9.0 | 4.8 / 9.3 | +5.2 uJ | ~0.17 W at 444 nC | R + Cgs value |
| 100 ohm | (lower) | 51.1 (full, 640/640) | 274 | 186 / 80/80 | 8.8 | 3.1 / 7.6 | +7.4 uJ | ~0.18 W | R value + 2512 |

Notes on the table:
- **Conduction penalty:** constant 37 A in the diode direction, so it is an upper bound. At 60 kHz, +2.2 uJ is
  +0.13 W per FET.
- **R_on power:**
  - It is simulated per cycle (S1 turn-on plus turn-off edge, worst corner) and scaled to Q = 383 nC.
  - With 4.7 nF the charge is +61 nC, so it is scaled to 444 nC. The 100 ohm figure is also scaled up, because its
    charging is not finished within the 3.75 us window.
- **Turn-off unchanged:** in every split network the ZVS turn-off loss is unchanged (8.7-9.0 uJ at 37 A) and t_trans
  is unchanged, because turn-off still runs through the PMEG + 1 ohm path. The S4 hard turn-on loss rises from 1.01
  to 1.18-1.20 mJ (39 / 47 ohm loss grid), but S4 is a fault edge.
- **Turn-on delay:** large R_on slows the turn-on, which spends ZVS current-lag margin. With the loop's 45 deg minimum
  lag, the current zero falls at 2.08 us or later at 60 kHz. That leaves about 1 us after the gate reaches 4.8-6 V
  (Cgs routes), and too little at 100 ohm.

### 3b. Full grid of 68 ohm + 4.7 nF at typical Qrr
Row `split68_1_cgs4p7_tt125` in `results/full.md`, every screen 640/640:
- S4 49.7 / 49.15 V/ns, diF/dt 244 A/us, Irr 50.8 A, die VDS 347 V;
- S5 22.1 / 20.6 V/ns;
- S1 worst t_trans 190.2 ns (margin 150 / 218 ns at DT 340 / 408), ZVS 80/80;
- S2 VDS 435 V;
- worst off-gate +0.50 V (screen 1.9 V);
- gate charge per turn-on 153 nC, measured inside the window and not yet complete.

## 4. IPW65R018CM8

- **Public SPICE model.** Infineon publishes no 650 V CM8 SPICE library; its page lists only PLECS, and guessed URLs
  return 404. It does publish the **600 V C8** library (`infineon-600-v-coolmos-8-simulationmodels-en.zip`, v1336,
  2025-11-13, sha256 32050b46...).
  - IPW60R016CM8 is the datasheet twin of IPW65R018CM8: Vth, RG 1 ohm, Coss 91 pF and Qg 171/173 nC match; the diode
    Qrr 1.54/2.31 uC, trr 180/225 ns and Irrm 16.4 A are identical; so are the 70 V/ns and 1,300 A/us limits.
  - Differences: Co(er) 286 vs 245 pF, Co(tr) 2,976 vs 2,702 pF, Ciss 7,545 vs 8,290 pF, Qgd 61 vs 54 nC.
  - It is used as **proxy B**, the vendor C8 technology. **Proxy A** is the 029 CFD7 model with Rg,int 1 ohm inside
    the package.
- **Re-checking the device study's CM8 conclusions:**
  - Its proxy (RG corrected outside the package, 029 die) is reproduced: 107.8 V/ns and 493 V at R_ext 8.2. It matches
    the committed rows within 0.24 V/ns and 3.4 V.
  - On Infineon's own C8 model, a straight swap gives S4 die VDS **423 V (passes 520)**. The "528 V fail" was a proxy
    artefact.
  - S4 slew is **82 V/ns** (worst row 198 V) and diF/dt is 2,165 A/us. CM8 at 8.2 ohm therefore breaks the diode limits
    just as CFD7 does, and "12 ohm matches the as-built" does not fix the rating.
  - ZVS is better: worst t_trans is 120 ns (C8) or 107 ns (proxy A), against 190 ns. The margin at DT 340 is 218-233 ns.
  - 14 of the 640 straight-swap rows aborted, all at 8.2 ohm.
- **R_on 39 ohm on CM8 (full grid, both proxies 640/640):**
  - S4 slew: 40.6 / 39.1 V/ns on proxy B; 55.6 / 54.5 V/ns on proxy A.
  - At near-typical Qrr (C8 TT 80 ns): 48.8 V/ns.
  - diF/dt 554-648 A/us; off-gate -0.83 V or lower.
  - E_off at S1 37 A: 3.7 uJ (B) and 5.7 uJ (A).
  - Gate 11-12 V at 1 us; R_on power 0.185-0.21 W at 60 kHz.
  - 27 ohm passes on B (43.4; 55.1 at TT 80) but fails on A (61.7).

## 5. When S4 happens

See `results/S4-EVENTS.md`. In short:
- S4 is not a steady-state point. The firmware (written, never run on hardware) keeps lag >= 45 deg and
  f >= 1.05 f_res.
- It is a fault or transient that arrives in bursts. Examples: an aluminium or non-magnetic pan at the 35 kHz floor
  (the floor probe shows that load capacitive), a restart within ~250 ms, or a CT_ZC calibration error.
- Once the tank goes capacitive, every edge of both legs is an S4 edge until the 5 deg software latch removes the gates.
  That is up to ~10.6 ms, about 740 edges per leg at 35 kHz. There is no hardware phase detector.
- No record gives an event rate.
- The diode-commutation limit is a per-edge ruggedness limit, so S4 stays a design case for the rating.

## 6. Recommendation

1. **Preferred: CM8 with R_on 39 ohm 2512**
   - Change R10/R12/R18/R20 from 8.2 ohm 1206 to Uniroyal **25121WF390JT4E** (39 ohm 1 % 1 W 2512, JLC C109426,
     extended, 15,328 in stock, $0.0322 at 1,000). Second source: Yageo RC2512FK-0739RL (C724015, 6,867, $0.0517).
   - Keep PMEG6030EP + 1 ohm and Cgs 1 nF.
   - It meets 56 V/ns and 1,040 A/us at every S4 corner on Infineon's own C8 model, with margin even at typical Qrr.
     It passes every screen on both proxies, and ZVS improves.
   - It stacks with the device study's -$6.77/board. The open CM8 issues are unchanged: DigiKey stock 482 against
     2,000 needed, 24-week lead.
2. **If CFD7 stays: R_on 68 ohm 2512 (25121WF680JT4E, C50371, 3,131 in stock, $0.0294) + Cgs 4.7 nF C0G 0603
   (Murata GRM1885C1H472JA01D, C85980, 76,738 in stock, $0.0172).**
   - This is the only sourceable network meeting 56 V/ns at typical Qrr; 56 ohm 1 % 2512 has no JLC stock.
   - It costs a slower turn-on (gate 4.8 V at 1 us) and +61 nC of gate charge per edge (+16 % on the RECOM load).
   - At the vendor model's Qrr, 39 ohm alone meets the limit (55.9 V/ns). That is a 0.1 V/ns margin on a model whose
     diode stores 24 % less charge than typical. Do not claim compliance on that basis.
3. **Package: 2512 is required, at both values.**
   - R_on dissipation at 60 kHz is 0.19 W as built and 0.18-0.22 W for every candidate.
   - The derating line (1 W at 70 C to 0 W at 155 C; Uniohm spec JLC-01-010 Ed.1 2016-09-23) gives a terminal limit of
     about 136 C at 0.215 W. For 2010 it is about 130 C, for 1206 about 82 C.
   - The B3 margins quoted by the coordinator (+8.5 K for 2512, +3.6 K for 2010 at ~21 A) were for the 8.2 ohm power.
     At 39 ohm they fall by ~2-3 K, which leaves 2010 marginal.
4. **Bench (D-8 double pulse):**
   - Run S4 at 198 V and 280 V, -20 A, leg A with the HS turning on. Measure both the 20-80 % dv/dt and diF/dt.
   - Bracket R_on 39 / 68 / 100 ohm on the 2512 pads, with Cgs 1 and 4.7 nF. Then run a repeated-pulse test of a few
     hundred consecutive S4 edges.
   - The model's Qrr basis is the open risk, and the bench sets it.

## 7. Parts, cost and layout (4 gates)

| item | as-built | CM8 route | CFD7 route |
|---|---|---|---|
| R10/R12/R18/R20 | RS-06L8R20FT 8.2 ohm 1206 (C323355, $0.0098) | 25121WF390JT4E 39 ohm 2512 (C109426, $0.0322) | 25121WF680JT4E 68 ohm 2512 (C50371, $0.0294) |
| C55/C56/C62/C63 | C0603C102J5GACTU 1 nF (shared line) | unchanged | GRM1885C1H472JA01D 4.7 nF C0G 0603 (C85980, $0.0172; a new BOM line) |
| D6-D9, R53/R54/R57/R58 | PMEG6030EP + 1 ohm | unchanged | unchanged |
| cost per board (JLC parts) | - | +$0.09 | +$0.08 R, +$0.03 C = +$0.11 |
| placements | - | 0 | 0 |
| unique extended parts | - | 0 (one line swapped for another) | +1 (the Cgs line) |

**Layout:** `scripts/fit_rg.py` checks the board-of-record pads, F.Cu tracks and vias against the clearance classes in
the committed `section.kicad_dru`.
- A 2512 sits **in place** of each R_on. Same centre, same vertical axis, between the TO-247 gate pin (y 4.2) and the
  PMEG / 1 ohm row (y 17.9), at the FET end of the driver-to-gate run.
- It keeps at least 0.199 mm above the board rules. The binding item is the bus_p / sw snubber track at the
  3.2 mm functional class.
- Condition: re-route the resistor's own gate trace locally. It runs beside the resistor (x 61.25 for R10) to D6 / C55.
- The R11 (0603 gate pull-down) courtyard ends ~0.04 mm from the 2512 courtyard, by hand estimate; move R11 0.5 mm.
- The FEM gate-loop ports sit at the driver pins and the resistor pads are closures, so the 3 mm longer body changes
  the loop only marginally. With R_on of 39 ohm or more, the gate loop is heavily damped.

**Sourcing flag (existing parts):** JLC lists 3 pcs of the Nexperia PMEG6030EP,115. The JSMSEMI "-JSM" clone
(C53114006) is not qualified.

## 8. Controls (`results/controls.json`)

| control | result |
|---|---|
| as-built against 320 committed device-study rows | 317/320 within 1 mV; max 0.2 V die VDS, 0.0004 V/ns slew, 0.01 ns t_trans |
| as-built energy rows | 8/8, max delta 3e-21 J |
| split, diode shorted, R_on = R_off = 2R, against symmetric R (12 / 22 ohm) | <= 0.02 V/ns, <= 0.022 V die VDS |
| 1-Gohm open fallback against the deleted branch | <= 0.013 V/ns |
| renamed TT-50 model copy against the vendor model | <= 0.14 V/ns |
| device-study CM8 proxy (cm8rg/cm8rg2) | rows match within 0.24 V/ns (3.4 V die VDS at R_ext 8.2) |
| D3 recovery fixture | Qrr 1.739 / 2.356 uC = D-24 map |

## Files
- `scripts/gn.py`: harness. It imports the device-study harness read-only; configs and grids are in `configs()` and
  `grid()`.
- `scripts/analyze.py`: tables, controls and Pareto.
- `scripts/qrr.py`: the diode recovery fixture.
- `scripts/fit_rg.py`: the 2512 / 2010 fit check.
- `scripts/jlc_fetch.py`: JLC public API reads; the cache is in `dl/jlc-raw`.
- `scripts/run_all.sh`: the whole chain.
- `results/`: summary.json, full.md, s4screen.md, s4b.md, ron_power.md/json, pareto.json, controls.json, qrr.json,
  fit_rg.json, S4-EVENTS.md.
- `sims/<config>/<grid>/results.json` and `deck*.cir`: every simulated row, with sha256 identities of the decks,
  scripts, models and matrices.
- `dl/`: downloads.
  - `cm8/` C8 600 V library: https://www.infineon.com/assets/row/public/documents/24/50/infineon-600-v-coolmos-8-simulationmodels-en.zip
  - `ipw60r016cm8/` datasheet Rev 2.1 2024-03-21: https://www.infineon.com/assets/row/public/documents/24/49/infineon-ipw60r016cm8-datasheet-en.pdf
    (sha256 69328a2f...)
  - `uniroyal2512/` Uniohm thick-film spec JLC-01-010 (sha256 bc6df4ca...)
  - `jlc-raw/` JLC records.
