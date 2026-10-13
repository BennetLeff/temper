# G01 mains_emi_rectifier: proposals (2026-10-13)

Scope: J1, F1, RV1, C1/C2, R1/R2, L1, C3/C4, BR1, J6 plus the off-board D-22 inlet module. Nothing outside this folder was edited. All numbers come from the scripts here (rerun with `python3 -I <script>`) or from the cited pages; `(est)` and `UNVERIFIED` mark what is not data.

Scripts and outputs:

| Script | Computes | Time |
|---|---|---|
| `emi_g01.py` -> `emi_g01_results.json` | Calls the unmodified `07-conducted-emi/s19b/emi_s19b.py` model with candidate filter parts. Baseline reproduces 10.5 dB nominal / 6.5 dB sensitivity minimum. Same 6 dB rule, 3 configs (170 V 22 A, 198 V 28 A pan, 198 V 22 A no-pan), fs 35-60 kHz at 1 kHz, 8 one-at-a-time sensitivities | `--step 1 --sens`: about 40 s per candidate |
| `yscan_g01.py`, `yscan_sens_g01.py` | Y cliff scan and full sensitivities for the recommended filter | ~1-3 min |
| `f10_fsfloor_g01.py` | F10: DM inductor value vs the controller's lowest fs | ~3 min |
| `leakage_g01.py` | Leakage vs Y split, supply assumption, limit class (same formulas as `leakage_budget.py`) | 1 s |
| `fuse_br1_g01.py` | F1 options vs BR1 and copper-neck criteria (reads the F2 containment result.json) | 1 s |

## Key findings first

1. **F5 cannot pass the repo's 0.25 mA budget by cutting Y alone.** The three IRM supplies at their datasheet maximum contribute 0.4285 mA by themselves (`leakage_g01.py`), above the 0.25 mA (50 % of 0.5 mA) budget with zero Y. The "Y <= 5.0 nF/line" figure in F5 is the capacity with supplies at 0. With supplies at the Simpex-typical value (0.030 mA for three, one unit measured, informational) the Y allowance is 3.66 nF/line. So F5 is a **G06/G10 supply-leakage question first** (lower-leakage supplies, or measured values, or the 0.75 mA stationary class), and a G01 Y question second.
2. **A cheaper-to-build, stock-backed filter that halves Y and improves EMI margin exists (P1).**
3. **A lower-I2t fuse is the only lever that moves F2's copper ask by 4-8x (P2), but it is a SAFETY/certifier change and its key datum (clearing I2t) is not in any document I could read.** No BR1 swap can fix F2 alone (P4 rejected).

## P1. Filter re-balance: Kemet SC-20-201 for L1 and module CM choke, Y 9.1 -> 4.4 nF/line  (SAFETY)

**Change** (BOM + footprint; module is off-board):
- L1: TDK B82726S2203A020 (0 stock all sources, 29 wk, $9.88 at 500) -> **KEMET SC-20-201** (2 mH @ 10 kHz, 20 A, 10 mohm max, 250 VAC, Mn-Zn ferrite toroid, 49 mm dia x 30 mm max, 108 g, leads S = 10 / S1 = 22 mm, 75 K rise at rated current; KEMET spec sheet generated 2026-10-13, https://search.kemet.com/download/specsheet/SC-20-201). DigiKey: 399-SC-20-201-ND, 57 in stock on 2026-10-13 (DigiKey FR page; Avnet showed 0 on a search snippet, so stock is thin), 11 wk factory lead, EUR 5.37 at 510 (EUR 9.11 at 1) (https://www.digikey.fr/en/products/detail/kemet/SC-20-201/10385030). At about 1.16 USD/EUR (my assumption) that is about $6.2 at 500, **-$3.7 per board**. No LCSC code found: hand/consign like L1 today (L1 is C1534260 with zero stock).
- Module CM choke (same 1.6 mH TDK part in D-22): -> SC-20-201 (-$3.6 on the module line, same caveats).
- Y caps: **C3/C4 stay 2.2 nF (board, unchanged), module drops its 4.7 nF Y pair, keeps 2.2 nF HF Y.** Total Y per line 2.2 + 2.2 = **4.4 nF (was 9.1)**.
- Module DM inductors unchanged (see P3).
- Fallback if SC-20-201 is out: M1 in the table below keeps TDK L1 and puts only the module choke on SC-20-201 (11.1 / 6.9 dB).

**Mechanism.** s19b already found the 60 kHz CM line is the binding term and the CM resonance depends on L_cm x C_y. A 2 mH choke at 2.2 + 2.2 nF keeps the resonance out of the 35-60 kHz band, while the 4.7 nF module pair was only adding leakage. The cliff is real: Y 1.0 nF board + 2.2 module gives 6.6 dB, 0.5 nF gives 0.1 dB (`yscan_g01.py`); 4.4 nF is 1.8x the cliff and 2.2 nF board Y is the only value I verified through all sensitivities (7.5 dB). Board Y 1.8 nF just passes (6.0), 1.5 nF fails (3.1).

**Scorecard effect** (`emi_g01_results.json`, `yscan_*`; model margin, not measurement):

| Case | Nominal dB | Sens. min dB | Pan-earthed INFO dB | Y nF/line | Open-PE touch mA (datasheet-max / typical supplies) |
|---|---|---|---|---|---|
| Baseline (as built) | 10.5 | 6.5 | 2.6 | 9.1 | 0.974 / 0.575 |
| **M2: L1 + module choke both SC-20-201, Y 4.4** | **12.0** | **7.5** | **4.3** | 4.4 | **0.693 / 0.294** |
| M1: TDK L1 kept, module choke SC-20-201, Y 4.4 | 11.1 | 6.9 | 4.4 | 4.4 | 0.693 / 0.294 |
| M5/M6 (Y 6.9, module 4.7 kept) | 11.1 / 10.8 | 7.0 / 6.5 | 4.6 / 1.5 | 6.9 | 0.843 / 0.444 |

- `emi_min_margin_dB` 10.5 -> 12.0 (+1.5); worst sensitivity 6.5 -> 7.5.
- `leakage_touch_mA` 0.974 -> 0.693 (-29 %). **Still FAIL** under the repo rule (0.25 mA). It passes the full 0.5 mA limit only if the supplies are at typical, not datasheet max: with typical supplies 0.294 mA passes 80 % and 100 % of 0.5 mA, not 50 %. Allowed Y (nominal, per line) by rule is in `leakage_g01_results.json`: 0 / 0 / 1.16 nF with datasheet-max supplies (50 % / 80 % / 100 % of 0.5 mA), 3.66 / 6.17 / 7.84 nF with typical supplies.
- `b3_c28_h25_peak_C`: L1 heat rises. DCR 10 mohm vs 4.5 mohm per winding: 1.23 W (scorecard basis) -> about 2.7 W (scaling by DCR, est), real 15 A: 2.0 W -> 4.5 W. Needs the chain (B3) to quantify near C5/C6/PS2.
- Parts cost -$3.7 (board) and -$3.6 (module). Stock risk traded for a single-source KEMET part (57 pcs).

**Interfaces disturbed.** l_filt / n_filt (to G06 PS1/PS2/PS3, G09 zero-cross, G10) electrical path unchanged; **footprint and keepout change** (49 mm dia x 30 mm vs 45 x 25.5 x 41 mm; leads at 10 / 22 mm) = re-layout of the L1 zone and its L1->BR1 AC1 neck (1,747 A2s, F2 study) and F1->L1 route. Heat +1.5 W near G02/G06. Weight 108 g: BP-07 restraint. G10/G06: PS leakage term is untouched, see key finding 1; they must report measured leakage. G04: coil-PE CM margin better, not worse, in the model.

**SAFETY.** Touch-current reduction is safety-positive, but (a) the SC-20-201 250 VAC rating, hipot and agency recognition were not read (spec sheet gives voltage only); L1 sits on the mains side with no isolation duty, but the lab must accept it; (b) the DM leakage inductance (assumed 20 uH = 1 % of 2 mH) is NOT in the sheet. At 10 uH the same filter drops to 0.9 dB sensitivity (`L1_SC-20-201_2mH_leak10uH`, with the stock module) - the margin depends on that unmeasured value, so **bench-measure leakage inductance on a sample before committing**. (c) the pass hinges on resonance placement: the M3 case (board Y 1.0) fails by 14 dB in sensitivities. Needs certifier for the Y reduction (touch current) and a bench EMI/leakage run.

**Risk** med. **Effort** re-layout (L1 footprint) + BOM. **Rank:** -$7.3 per system with module, availability fix for L1, leakage -29 %, EMI +1 dB; 0 lines saved.

## P2. F1: 6.3 x 32 fast-acting 25 A (Littelfuse 0505025.MXP) instead of KLDR025  (SAFETY, needs certifier)

**Change.** F1 KLDR025.TXP ($29.41 at 500, hand-assembled, no LCSC code, 10 x 38 clips 01250003H 2 x $3.25) -> Littelfuse **0505025.MXP**, 6.3 x 32 mm, fast-acting, 25 A, 500 V, 5 mohm; Newark lists the MXEP sibling at $2.85 at 1000 (1+ $4.24) (https://mexico.newark.com/en-MX/littelfuse/0505025-mxep/cartridge-fuse-fast-acting-25a/dp/01P9419); I did not find an LCSC code or the MXP price, so assume about $3 (est). The earlier 6.3 x 32 footprint with Littelfuse 01220088Z clips (30 A) is the fit (DECISIONS M8; the board moved to a 10 x 38 clip footprint in stage 12, so F1 reverts: ECO, F1 position and C1/pours revert). Saving about $26-30 per board before the clip price difference (unpriced). One hand line stays (clips).

**Mechanism / numbers** (`fuse_br1_g01.py`):
- The scorecard `fuse_copper_fusing_ratio` = 355 A2s (HV_RET neck) / F1 clearing. KLDR025 clears 1,710 A2s (datasheet p.5) -> 0.208. For 0505025: melting I2t 145 A2s, from a third-party catalogue text only (Littelfuse PDF returns 403) - UNVERIFIED. **Clearing I2t at 127-140 V is not published in anything I read.** Assuming clearing = 1.5 / 2 / 3 x melting (est): 218 / 290 / 435 A2s -> ratio **1.63 / 1.23 / 0.82** (vs 0.208), copper target at 2x 435 / 580 / 870 A2s (vs 3,420), and BR1 (510 A2s, half = 255) survives in the 1.5x case only. Of the F2 study's real necks, only the HV_RET isthmus (355) still fails the 2x target; J8->Q2/Q5 (884), Q3->R5 (2,080) and L1->BR1 (1,747) pass.
- Carrying: 25 A x 0.75 x 0.95 (assumed derate) = 17.8 A >= 15 A. Inrush 0.7 % and a 1 kA line-to-line surge 8.4 % of 145 A2s melt (using the F1-RECOMMENDATION 3.4 pulse estimates): fast-acting is electrically fine.
- Considered and worse: KLKR020 Class CC fast-acting (clearing 900 A2s, Littelfuse KLKR datasheet table via distributor copies) carries only 13.5 A; KLKR025 would sit between 900 and 1,720 (1,244 interpolated, est, 27 % better, ratio 0.29, no row published) - not worth a certifier trip.
- F4 is not helped: 145 / 11.6 (F2 pre-arc) = 12.5x, F2 still opens first; its fix remains the F2 HBC replacement.

**Interfaces.** F1 footprint/position (J1 and J3 neighbours, C1/R1 and the l_f/ac_l_in pours); G02/G08 copper neck ask drops from 3,420 to 435-870 A2s; G10 F2 coordination unchanged.

**SAFETY - not safe to adopt without the lab.** This reverses the 2026-10-09 decision that chose Class CC (UL 248-4, 200 kA, listed branch-circuit) to settle the 120-127 V interrupting-rating question for UL/CSA/NOM. 0505025 is a supplemental fuse, 500 V / 20 kA (rating not confirmed for the 25 A MXP; one source says 30 kA for the 30 A) which does cover the 4.7-8.4 kA cord-limited bound, but acceptance of a Recognized supplemental fuse is the same open certifier item that killed MDA-25-R. What is new vs that decision: F2 shows Class CC leaves the board with an unfixable-by-routing containment gap (necks 355/884 A2s vs 3,420 target; BR1 6.7x over), and the Class CC line is $36 with clips. Before any adoption: read the 505 datasheet in a browser (clearing I2t, 25 A interrupting rating, agency file), and obtain clearing I2t by test at 4.7 and 8.4 kA prospective. **Risk high. Effort schematic + placement. Rank: -$26 to -$30 per board, ratio 0.21 -> 0.8-1.6 (est), 0 lines saved, 1 hand line (F1) -> hand clips only.**

## P3. F10: what the module DM inductors must be (no MPN found)

`emi_g01.py` sweeps the module DM inductor per leg (LNEW) with the P1/REC2-class filter. Required to keep the 6 dB sensitivity rule (K2 filter, `F10_K2_*`): 32 uH per leg (plus the choke's own leakage): nominal / sens-min dB = 1.9 / -2.6 (0 uH), 5.9 / 1.6 (10), 8.7 / 4.4 (20), 11.0 / 6.9 (32). **Spec: >= 32 uH per leg, >= 80 % of that at 15 A rms (21 A peak), DCR <= 8 mohm, 250 VAC rated.** I searched for a 47 uH / 20 A through-hole toroid in stock (Bourns, Wurth, Murata, KEMET, Ferrocore): none found (best: Bourns 2209-V-RC 6.7 A, out of stock). **This stays an unresolved F10 item**; a custom wound part is the realistic route, so keep the module as a bench item.

Cheaper lever via firmware/G04/G09 (needs the chain to confirm ZVS and power): the DM line that decides the margin is 2 x fs at the lowest fs. Raising the fs floor from 35 to 40 kHz makes a module with **no** discrete DM inductor reach 6.7 dB nominal (0 uH), and 10 uH reaches 10.6 dB; a 45 kHz floor gives 14.5 dB with 0 uH (`f10_fsfloor_g01_results.json`, nominal only, no sensitivities). If G04/firmware can hold fs >= 40-45 kHz, F10 reduces to a cheap or absent inductor. Tank gain at higher fs and power at low line are not evaluated here.

## P4. BR1 and F2 containment: considered, rejected

- No standard single-phase bridge reaches the 3,420 A2s that survives KLDR025 clearing. Best I found: KBPC5010 (50 A) MDD newer revision IFSM 500 A / 1,038 A2s, older 664 A2s; GBJ3510 374 A2s; GBJ2510 (as built) 510 (search summary text, per-datasheet check needed). A 1,038 A2s part survives only a fuse clearing <= 519 A2s, which is the P2 regime, not the KLDR regime. KBPC is a chassis wire-in part (no JLC assembly); GBJ2510-F is $4.02 with 1,589 JLC stock and multi-source. **Keep GBJ2510; BR1 remains sacrificial under KLDR025 (agrees with DECISIONS).**
- Paralleling two bridges for 4x I2t depends on current sharing; rejected for safety unpredictability.
- A DC-side fast fuse (FC1) in the strap path is the F1-study recommendation (b); it belongs to G02/G03, not G01.

## Considered and rejected

- **Drop L1 and rely on the module:** -9.9 dB nominal (`L1_removed_module_only`).
- **Remove board Y only / module Y only without compensation:** Y1 board removed 9.7 / 5.1 dB; Y2 module 4.7 removed 9.4 / 3.3; Y4 board 1.0 + module 2.2: -1.1 dB. Y-only cuts without a bigger choke fail the sensitivity rule.
- **Kemet SC-20-104 (1 mH, 8 mohm, DK 83 in stock on some regions; conflicting 0 elsewhere) or Wurth WE-CMB 1.3 mH 20 A 4.7 mohm (RS stock 72, MPN not read) as L1:** 5.4 / 1.0 and 7.9 / 3.6 dB. Fail the 6 dB sensitivity rule. WE-CMB has the best heat (4.7 mohm) if a 1.3 mH choke is acceptable, so it is a candidate only with the bigger module choke (M4: 8.1 / 3.8, still fails).
- **Larger module choke 3.2 mH (REC2) with the Y cuts:** needs a 3.2 mH / 20 A part that I could not find (the model case K0-K6 passes with board Y 2.2 + module 2.2: 11.0 / 6.9, but only 2.0 mH is a real stocked part). 6.4 mH: 8.9 / 4.3.
- **Drop RV1 or the C1/C2 X2 pair:** RV1 is the line-to-line surge clamp protecting BR1/C5/C6 and F1's surge budget (12.2 A2s at 1 kA). I did not run the surge side with fewer X capacitors; X caps -20 % is already the tightest sensitivity in the EMI table (6.5-7.9 dB), so removing X is not supportable.
- **J6 (Phoenix 1704004, 0 stock, $2.37):** an in-stock PE terminal is a layout item (F11, Y-cap PE path 75-81 mm); I did not research alternates.
- **F1 time-lag 20 A:** carries 13.5-14.4 A < 15 A (repo derating); rejected by the F1 recommendation.

## What I could not verify

- Littelfuse 505 datasheet (403): clearing I2t, 25 A interrupting rating, agency file, derating; Kemet SC-20-201 leakage inductance, hipot, agency listing; Kemet stock beyond the one DigiKey page.
- The USD price of the 0505025.MXP (used MXEP at $2.85) and the clip delta; the EUR/USD rate.
- IRM supply leakage beyond the datasheet maximum (drives F5).
- All EMI numbers are model margins (same s19b model, same caveats), no measurement; the P1 filter depends on a CM resonance, so bench-measure before ordering.
