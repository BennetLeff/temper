# native-21 device cost study: MOSFET frontier (Task A) and HS bias supply (Task B)

Study date 2026-10-15. Board of record s32 (DECISIONS 40), as-built F6 gate drive (2EDR8259X, Rg 8.2 ohm, -1.6 V off,
PMEG clamp), Q2/Q3/Q5/Q6 = IPW65R018CFD7, HS bias U41/U42 = RECOM R24C2T25/R-R.
Everything here re-runs from `scripts/`; the repo is only read. Datasheet PDFs and text extracts stay in `dl/` (outside
the repo) and are identified below by URL, revision and sha256.

## Re-run

```
cd scripts
./run_device.sh IPW65R018CFD7_L1 repro energy edge zvs edge2     # as-built (controls first)
./run_device.sh IPW65R029CFD7_L1 energy edge zvs edge2 cm8rg cm8rg2 # CFD7 029 model = 029 itself and the CM8 proxy
./run_device.sh IPW65R041CFD7_L1 energy                          # 041 itself and the IPZA65R025CM8 proxy
python3 -I analyze.py    # -> results/switching.json  (controls: repro block)
python3 -I thermal.py    # -> results/thermal.json/.md (controls C1, C2 asserted before any row)
python3 -I bias.py       # -> results/bias.json/.md   (control asserted before any row)
```
`run_all.sh` + `run_more.sh` are the chains used on 2026-10-15 (8 ngspice workers, ~2.5 h on a loaded Mac).

## Method

* `harness.py` builds the as-built deck by importing the committed c33 adoption script read-only
  (`validation-results/11-candidates/c33-six-layer/adoption/zvs/zvs_node_c.py` -> c25 `d2_c25.py`), sha-checking the c25
  `F6.cir`, c33 board-cap ADD and c25 PROBES, and swapping every `IPW65R018CFD7_L1` instance for the candidate's vendor
  subckt from the same `IFX_CFD7_650V.lib`. Added: gate-loop charge `.meas` on i(l_p3)/i(l_p4) (no elements); for the
  energy grid only, B-sources that integrate the vendor model's own heat channels.
* Modes: `repro` (128 committed c33 s32 ZVS rows), `zvs` (S1 sweep, 672 runs, c33 method), `edge` (S1/S2/S4/S5 at DT
  340/408/600 ns, ESL 10 nH, 612 runs), `edge2` (S2/S4/S5 at ESL 1.06 nH), `cm8rg` (CM8 proxy with corrected gate
  resistance: deck RG = R_ext + 1.0 ohm CM8 Rg,int - 3.8 ohm 029 Rg,int; R_ext 8.2/10 in `cm8rg`, 12/15 in `cm8rg2`),
  `energy` (V 20-198, IL 2-60 A, Tj 100/150, DT 569 ns).
  Pass rule = c25 `d2_c25.py` unchanged: die VDS <= 520 V (585 V S2), |VGS| <= 30 V, off-gate < 3.0 V and < the 018
  model screen, ZVS on S1; "hot" adds off-gate < 1.9 V. The 018 model screen is conservative for CM8 (Vth min 3.7 vs 3.5 V).
* `thermal.py` = R33 `requirement.py` solve() + round6 `board_side.py` fets(), parametrised by device (RDS(T), RthJC,
  switching heat). Bases: A = D-18 switching proxy (hard-switched, conservative), B' = conduction + 0.33 W ZVS estimate,
  D = conduction + deck energy grid averaged over the line cycle (phi 60 deg). Sinks S8 (R_SA 0.29) and K1 (0.214
  substituted into the S8 13 CFM model; DECISIONS item 15's K1 Tj 123.8/128.7 is NOT reproduced by this substitution).
* `bias.py` = committed `bias_sizing.py` channel-current formula + ALT-BIAS module-loss model, fed with the deck's gate
  charge; discrete UCC25800-Q1 option modelled per channel.
* No CM8 vendor SPICE model could be obtained (Infineon pages script-rendered; guessed zip URL 404). CM8 switching is
  represented by the CFD7 029 model (Co(tr) 2584 vs 2702 pF, Co(er) 247 vs 245 pF, Eoss 19.8 vs 19.6 uJ); conduction and
  RthJC use the CM8 datasheet. This is the main model gap and a bench item.

## Controls (all pass)

| control | reference | result |
|---|---|---|
| deck reproduction (`repro`) | 128 committed c33 s32 ZVS rows | 128/128; max abs delta 2.6 uV incoming VDS, 0.7 mV die VDS, 0 ns t_trans |
| as-built ZVS sweep (`zvs`, 672 runs) | committed c33 s32 summary | reproduced: leg A worst t_trans 188.9 ns (margin 219.4 / 151.1 ns at DT 408 / 340), threshold 9.11 / 11.65 A; leg B 190.36 ns (217.9 / 149.6), 9.14 / 11.73 A |
| thermal C1 | R33 `requirement.py` solve() | max abs delta 0.0 C |
| thermal C2 | round6 `board-side-fets.csv` basis A and B (28 A, 40/45/50 kHz) | max abs delta 0.0 C (15 rows) |
| bias | `bias-sizing.json` channel currents; ALT-BIAS 3.2 module loss 0.98 / 1.09 / 1.71 W | 0.0 A; 0.983 / 1.091 / 1.706 W |
| price | IPW65R018CFD7 recorded price | Digi-Key $10.17612 @510 reproduced |

## Results

### Task A: frontier (4 devices/board, Digi-Key 2026-10-15, largest break <= 2000)

| device | pkg | RDS max 25 C | price @break | stock / lead | $/board vs as-built | worst-FET Tj S8, deck basis D: nominal / c28 50 kHz / trip 29.4 A | same, basis A (D-18 proxy) | verdict |
|---|---|---|---|---|---|---|---|---|
| IPW65R018CFD7 (as-built) | TO-247-3 | 18 mOhm | $10.17612 @510 | 459 / 8 wk | 0 | 72.1 / 85.8 / 89.5 C | 105.3 / 140.1 / 144.7 C | control |
| **IPW65R018CM8** | TO-247-3 (PG-TO247-3-U06) | 18 | $8.48325 @510 | 482 / 24 wk | **-6.77** | 71.9 / 85.8 / 89.5 | 104.5 / 138.5 / 143.0 | **recommended, with R_ext 8.2 -> 12 ohm** |
| IPW65R029CFD7 | TO-247-3 | 29 | $6.82825 @510 | 110 / 21 wk | -13.39 | 85.1 / 114.3 / 123.0 | 122.8 / 179.7 / 190.7 | reject (2 K to 125 C at trip on the optimistic basis; sink 105-118 W) |
| IPZA65R025CM8 | TO-247-4 | 25 | $6.533 @510 | 183 / 52 wk | -14.57 | 79.2 / 101.0 / 107.3 (041 model proxy) | 113.9 / 159.1 / 166.7 | re-spin option only (4-pin footprint, FEM, 52 wk) |
| IPW65R041CFD7 | TO-247-3 | 41 | $4.78498 @510 | 112 / 50 wk | -21.56 | 104.2 / 164.6 / 185.7 | 148.3 / 250.1 / 277.5 | reject |
| SiHG026N65E | TO-247AC | 26 | $7.44624 @500 | 500 / 34 wk | -10.92 | not run | | reject: body diode dv/dt 10 V/ns, Qrr 15/30 uC |
| SiHG041N65SF | TO-247AC | 43 | $3.21 @500 ($3.00 @1500) | 464 / 45 wk | | not run | | reject: 43 mOhm > ceiling; Vth min 3.0 V |
| others (CFD7A 022/035, C7, 600 V P7, onsemi, ST, Toshiba, SiC) | | | see `scripts/candidates.json` | | | | | reject (reasons in candidates.json) |

RDS(on),max(25 C) ceiling for worst-FET Tj <= 125 C (superjunction, RDS(150)/RDS(25) 2.2, RthJC 0.28, ZVS basis):
nominal 59.5 / 69.2 mOhm (S8 / K1), c28 35.0 / 40.7, trip 31.7 / 36.9. Basis A already puts the as-built at 140 C at c28
50 kHz (S8) - that is the D-18 hard-switching proxy and is the reason the frontier stops at 18 mOhm.

### Task A: switching margins (deck, s32 caps; CM8 = CFD7 029 model with CM8 gate resistance)

| quantity | as-built 018CFD7, Rg 8.2 | 029 model, deck Rg 8.2 (Rg tot 12.0) | CM8 proxy R_ext 8.2 (tot 9.2) | CM8 proxy R_ext 10 (tot 11.0) | **CM8 proxy R_ext 12 (tot 13.0)** | CM8 proxy R_ext 15 |
|---|---|---|---|---|---|---|
| S1 37 A worst t_trans (leg A/B) | 188.9 / 190.4 ns | 144.0 / 145.5 | | | | |
| ZVS margin at DT 408 / 340 (worst leg) | 217.9 / 149.6 ns | 262.8 / 194.5 | | | | |
| ZVS current threshold at DT 408 / 340 | 9.14 / 11.73 A | 5.97 / 7.52 A | | | | |
| S1 ZVS (edge grid) | 136/136 | 136/136 | 64/64 | 64/64 | 16/16 (DT 340, weak) | 16/16 |
| S2 max die VDS, ESL 10 / 1.06 (585 V screen) | 398.0 / 401.4 V | 411.4 / 423.7 | 436.3 / 449.9 | 418.3 / 431.0 | not run (Rg up lowers it) | |
| S4 max die VDS, ESL 10 / 1.06 (520 V screen) | 478.9 / 479.0 V | 450.6 / 432.4 | **528.4 FAIL (3 rows)** / 511.0 | 445.5 / 461.0 | 440.3 / 418.5 | 422.9 / 426.3 |
| S4 max 20-80 slew, ESL 10 / 1.06 | 85.8 / 81.9 V/ns | 91.8 / 87.4 | **108.3 / 108.3** | 96.7 / 96.3 | **85.3 / 80.1** | 67.3 / 62.2 |
| S5 max die VDS / slew (ESL 10) | 442.2 V / 72.3 V/ns | 410.7 / 50.4 | 431.8 / 64.0 | 413.0 / 53.0 | | |
| max off-gate (all cases; 3.0 V stop, 1.9 V hot) | -0.18 V | +0.015 V | +0.72 V | +0.011 V | -0.34 V (S1/S4 run only) | -1.01 V (S1/S4 run only) |
| max abs VGS (+/-20 V static) | 15.04 V | 15.87 | 16.17 | 15.98 | 15.06 | 15.05 |
| gate-loop charge per edge | 359-383 nC | 231-244 nC | 252 nC | 249 nC | (charge is set by the die) | |

Pass counts: as-built 612/612 (ESL 10) + 392/392 (ESL 1.06); 029 model 612/612 + 392/392; CM8 R_ext 8.2: 509/512
(3 S4 rows, leg A, 198 V, falling, ESL 10, die VDS 524-528 V); R_ext 10: 512/512; R_ext 12 and 15: 304/304 each.
Rules: dv/dt <= 80 % of 120 V/ns = 96 V/ns (ledger); 2EDR8259X CMTI 150 V/ns / 1.5 = 100 V/ns.

### Task B: HS bias (per high-side channel, U41 or U42; `results/bias.md`)

| gate charge basis | Q/edge | P_out at 33 / 50 / 80 kHz | % of 2 W knee at 50 kHz | RECOM loss 45 % / 53 % eff at 50 kHz | discrete UCC25800 loss (own IC) at 50 kHz |
|---|---|---|---|---|---|
| allocation (as-built sizing) | 740 nC | 0.804 / 1.018 / 1.396 W | 50.9 | 1.245 / 0.903 W | 0.664 W |
| as-built deck, worst edge (S2) | 382.6 nC | 0.604 / 0.715 / 0.910 W | 35.7 | 0.873 / 0.634 W | 0.566 W |
| CM8 estimate (029 deck x 173/145) | 285.4 nC | 0.549 / 0.632 / 0.777 W | 31.6 | 0.772 / 0.560 W | 0.539 W |

Discrete option (per channel): UCC25800AQDGNRQ1 ($2.18178 @500, 0 stock, 1595 due 15-Dec-2026) + WE 750319833
($2.59352 @250, 231 stock) + voltage doubler + LP2951ACDR2G ($0.25425 @2500 / $0.57 CT) + passives ~ $5.8/channel,
~$11.6/board (own IC each) or ~$10.5 (shared IC) vs RECOM 2 x $7.18188 = $14.36 at the 750 T&R break.


## Datasheets (dl/, not in repo)

| part | document, revision | URL | sha256 (PDF) |
|---|---|---|---|
| IPW65R018CFD7 | Infineon datasheet Rev 2.0 2021-04-19 | repo copy validation-results/03-loss-thermal-budget/round3/sources/ipw65r018cfd7.pdf (https://www.infineon.com/dgdl/Infineon-IPW65R018CFD7-DataSheet-v02_00-EN.pdf) | repo file |
| IPW65R018CM8 | Infineon datasheet Rev 2.1 2025-03-07 | https://www.infineon.com/assets/row/public/documents/24/49/infineon-ipw65r018cm8-datasheet-en.pdf | 426b5d3147287c70318c4d05782bf4704d4e50081aee50c45cc8aae5868d97c7 |
| IPW65R029CFD7 | Infineon Final Data Sheet Rev 2.1 2020-07-31 | https://www.infineon.com/assets/row/public/documents/24/49/infineon-ipw65r029cfd7-datasheet-en.pdf | fa72aea91fc780dba81db496110ccb0e4dec0444a5c2d1453ea3cb240dc88e07 |
| IPW65R041CFD7 | Infineon Final Data Sheet Rev 2.1 2020-08-12 | https://www.infineon.com/assets/row/public/documents/24/49/infineon-ipw65r041cfd7-datasheet-en.pdf | 414a154a79ad7560104db7ef1061bce3e93878b2417d1468695e20e383889fe3 |
| IPZA65R025CM8 | Infineon datasheet Rev 2.1 2025-03-06 | https://www.infineon.com/assets/row/public/documents/24/49/infineon-ipza65r025cm8-datasheet-en.pdf | 679ab46a42f0b7966dc2c65d25169c486bf042d52184dc11887542d78a1ae348 |
| SiHG026N65E | Vishay S25-0553 Rev A 26-May-2025 (doc 92599) | https://www.vishay.com/docs/92599/sihg026n65e.pdf | 6da14cd87eefb79cd0de38785f5f81092de5bffaea029fb11f0c1e4fb6c47423 |
| SiHG041N65SF | Vishay S25-0012 Rev A 13-Jan-2025 (doc 92571) | https://www.vishay.com/docs/92571/sihg041n65sf.pdf | 0e068aefe37096ee287801a05c82328e264481373a6a2883e235f77a2a130505 |
| 2EDR8259X | Infineon EiceDRIVER 2EDR8259H/2EDRx259X/2EDRx258X Rev 1.7 2026-04-09 | https://www.infineon.com/assets/row/public/documents/24/49/infineon-eicedriver-2edr8259h-2edrx259x-2edrx258x-datasheet-en.pdf | f49391ca00e15397076dfc7482f56b0a1ea794a5249f1d14a1a60bb5ef33ae33 |
| 2EP1xxR | Infineon 2EP1xxR datasheet v1.01 2026-07-31 (VDD 4.5-20 V operating) | https://www.infineon.com/assets/row/public/documents/24/49/infineon-2ep1xxr-datasheet-en.pdf | abc93561ae9b6f65e1b07cfb2f32a1a10cafaea1836ce11d76bb60e86cd6bdc4 |
| UCC25800-Q1 | TI SLUSDX3C (Aug 2023) | https://www.ti.com/lit/ds/symlink/ucc25800-q1.pdf | f7365400cfb82fe60596ea087fa4b2610d5df8151e8cd8f9d0b61736c510994f |
| WE 750319833 | Wurth Rev 002.000 2024-06-28 | https://www.we-online.com/components/products/datasheet/750319833.pdf | 739a22b3c1ece360cdb8f876a265ae04610f000f773cf6f5ff487099e6d0c202 |
| WE 750319177 | Wurth Rev 001.004 2024-06-10 | https://www.we-online.com/components/products/datasheet/750319177.pdf | 5716164e2fd01240a6b13f203b7301cf7c7b11c4763cc5d53fab8a996173df55 |
| LP2951 | onsemi LP2950/D Rev 35 Feb 2023 | https://www.onsemi.com/pdf/datasheet/lp2950-d.pdf | ac0a99a8f58914ffa05fcd9b1eb016ee0b184d00eae235d0637db3796fbb2ea6 |

Prices: Digi-Key product/search pages read 2026-10-15 without account or cart (`market/mosfets.csv`, `market/bias.csv`,
URL per row). Price = unit price at the largest break <= 2000 pcs (4/board x 500 boards).

## Findings

1. **Recommend IPW65R018CM8 as a drop-in for Q2/Q3/Q5/Q6, with the four gate resistors raised from 8.2 to 12 ohm.**
   Saves 4 x $1.69287 = $6.77/board ($3,386 per 500 boards). Same RDS(on) 15/18 mOhm, RthJC 0.24 vs 0.28, Qg 173 vs
   234 nC, Co(tr) 2702 vs 4144 pF, fast body diode (Qrr 1.54/2.31 uC), same 120 V/ns and 70 V/ns diode ratings,
   ID(100 C) 73 vs 67 A. PG-TO247-3-U06 dimensions sit inside the CFD7 Z8B00003327 tolerances (footprint, M11 tab stack and
   clamp unchanged). Thermal identical within 0.3 K on the deck basis, 1.5 K better on basis A.
   The gate-resistor change matters: CM8 Rg,int is 1 ohm (Rev 2.1 p.5) against 2.7 ohm on the CFD7 018 (Rev 2.0 p.5), so
   a straight swap drops total gate R from 10.9 to 9.2 ohm; the proxy then fails the 520 V screen on S4 (528 V) and
   runs 108 V/ns, above both 96 V/ns (80 % of 120) and 100 V/ns (2EDR CMTI / 1.5). At 12 ohm the proxy gives S4
   440/419 V and 85/80 V/ns, matching the as-built 479 V / 86 V/ns, with S1 ZVS intact.
   The ZVS margin improves with the smaller Coss: worst t_trans 145 ns vs 190 ns (+45 ns), threshold 7.5 A vs 11.7 A
   at DT 340 (029 model, total gate R 12 ohm).
2. Lower RDS(on) parts are not cheaper, and higher RDS(on) parts break the thermal budget. 029CFD7 reaches 114 / 123 C (c28 /
   trip) on the optimistic deck basis and 180 / 191 C on basis A. IPZA65R025CM8 ($14.57/board less) is thermally
   plausible (101 / 107 C on basis D), but it needs a 4-pin footprint and re-extraction, and has a 52 wk lead time. Keep it as a re-spin option.
3. **Bias: keep the RECOM R24C2T25/R-R.** The real worst HS load is 0.715 W out at 50 kHz (36 % of the 2 W knee),
   0.63 W with CM8. A discrete UCC25800-Q1 supply saves only about $2.8-3.9/board for a layout re-spin. Against it: the
   driver IC has zero stock, the transformer has 231 in stock, Cww is typical only (2 pF, no max; ALT-BIAS needs a max of 4 pF
   or less), basic insulation is 800 Vpk (520/800 = 65 % against the ledger's 50 % rule), and the rails and startup need
   requalifying. Buy RECOM on T&R at the 750 break ($7.18188): -$0.38/board.
   It also runs cooler than assumed: module loss is 0.63-0.87 W at 50 kHz on the measured charge, against 1.71 W at the 80 kHz allocation.
4. Combined: -$6.77 (CM8) - $0.38 (RECOM T&R break) = **-$7.15/board**. Each RECOM module dissipates about 0.08-0.10 W
   less with CM8 (lower gate charge).

## Flags for the ledger / B3 (not fixed here)

* The ledger compares the RECOM module LOSS at 80 kHz (1.71 W) with the 2 W OUTPUT knee ("85.5 %"). Output at the 80 kHz
  allocation is 1.396 W (69.8 %); 0.715 W (35.7 %) at 50 kHz on the deck charge.
* The ledger's IPW65R018CFD7 entry has no reverse-diode dv/dt rating: 70 V/ns (VDS 0-400 V, ISD <= 58 A, Tj 25 C;
  Rev 2.0 p.3 Table 2). S4 (IL -20 A, partner body diode conducting = hard diode commutation) runs 82-86 V/ns on the
  as-built deck, so it exceeds the rating outright as well as 80 % of it (56 V/ns). CM8 has the same 70 V/ns rating
  (Rev 2.1 p.3). In the proxy, R_ext 15 ohm brings S4 to 62-67 V/ns.
* B3 module heat 1.09 W/module is conservative against 0.53-0.73 W at 33 kHz on the deck charge.
* K1 in thermal.py = R_SA 0.214 substituted into the S8 13 CFM model; it does not reproduce DECISIONS item 15's 123.8 / 128.7 C.

## Bench confirmation needed

* CM8 has no vendor SPICE model here, so its switching runs on the 029 model. On the bench: S4/S5 dv/dt and die VDS with CM8 at R_ext 12 ohm
  (target <= 96 V/ns and <= 520 V), off-gate, ZVS t_trans at 37 A / DT 340, and case temperature at 28 A / 50 kHz.
  If Infineon's CM8 model zip can be obtained, rerun `cm8rg`/`cm8rg2` with it in place of the proxy.
* RECOM U41/U42 case temperature, startup and EMI with CM8 (the lower charge should reduce all three).
* If the discrete bias option is ever pursued: measure Cww max, startup time against the 16 ms timeout, and the rail.
