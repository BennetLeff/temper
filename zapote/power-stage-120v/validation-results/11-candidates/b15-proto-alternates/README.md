# Prototype stock-gate alternates: L1, C3/C4, D6-D9 (OPEN-ITEMS B15)

Read date **2026-10-16** (JLC parts API 18:59-19:16 UTC; Octopart public pages 19:12-19:13 UTC; DigiKey page for
7448052502 via a browser-class fetch). Board of record: native-21 stage 50, `runs-native21/s50/c50int/section.kicad_pcb`
(sha256 e842d9c8...). The PS repo was only read. Nothing was ordered, no supplier was contacted, and no bot check was
bypassed (nexperia.com and we-online.com refuse scripted reads with 403; the Würth PDF arrived through a normal fetch).

Gate (DECISIONS 72 addendum): qty x 20 boards at JLC, or at **one** authorised non-broker distributor. The aim here is
2x that need. Needs: L1 20, C3/C4 40, D6-D9 80.

## Verdict

| Line | Fitted part today | Recommended for the 20-board lot | Change type | Status |
|---|---|---|---|---|
| **L1** | B82726S2203A020: 0 authorised anywhere (brokers only) | **B82726S2243A020** (Mouser 62, DigiKey 29), **only with the off-board inlet module's DM inductors raised from 41 µH to >= 100 µH per line** | BOM only on the board. The condition is a module spec change. | **No unconditional qualified alternate.** As a pure drop-in, EMI goes from PASS (12.37 / 8.19 dB) to INCONCLUSIVE (6.03 / 1.57 dB) |
| **C3/C4** | DE1E3RA222MA4BP01F: JLC 6, but **Mouser 773, Newark 507, DigiKey 173** | **Keep the fitted MPN.** It already passes the gate through Mouser. For JLC's own stock, use **DE1E3RA222MJ4BH01F** (JLC 104, Mouser 6,002) | none, or BOM only | Not short: the 10-15 snapshot read JLC only for this line (B2 read gap) |
| **D6-D9** | PMEG6030EP,115: **JLC 9,298 today** (the snapshot read 7 on 10-15) | **Keep the fitted MPN.** Backup: **PMEG6030EP-QX** (JLC 2,763, identical datasheet tables) | none, or BOM only | Not short. The c39 re-run with a bounding diode model passes 640/640 |

Stock and price snapshot: `snapshots/STOCK-2026-10-16.csv` (rebuilt offline by `scripts/build_stock_snapshot.py`).
Raw reads: `snapshots/jlc-raw/` and `snapshots/octopart/`, parsed into `snapshots/octopart-2026-10-16.json`.

## 1. L1 (mains common-mode choke)

### 1a. B82726S2243A020, the same-series part

| Item | Requirement / fitted 2203 | B82726S2243A020 | Margin / note |
|---|---|---|---|
| Datasheet | TDK B82726S22*3A020, May 2026 (sha256 e8002bfe..., the ledger's copy) | same sheet | same drawing IND2421-G-E |
| Footprint | `B82726S2_ReviewOnly`: pins 10 x 25 mm, drill 2.5 mm, pad 4 mm; L1 at (232.0, 31.0) | same drawing: 45 x 25 mm max, pins ø2 on 10 x 25 mm | **drop-in**, so BOM only |
| I_R | 2203: 20 A at TR 60 °C | 24 A at TR 60 °C, same derating curve | ledger check at 15 A: 0.625 at ≤ 60 °C and 0.630 at the 61 °C release bay (2203: 0.750 / 0.755). The 80 % rule holds to **82.5 °C** local air (2203: 67.8 °C, ledger 67.7) |
| At the 13.5 A firmware line bound (B3) | — | 0.567 at 61 °C | the 80 % rule holds to 89.0 °C; IR alone holds to 98.7 °C |
| Copper loss | 2203: 2.03 W at 15 A, 1.64 W at 13.5 A | 1.44 W / 1.17 W (3.2 mΩ) | L1's B3 body temperature can only fall; B3 not re-run |
| Voltage | line high 139.7 V ≤ 0.8 x VR | VR 250 V AC, test 1500 V AC | 0.559 (unchanged) |
| Climatic | 125 °C | 40/125/56 | unchanged |
| Approval basis | EN 60938-2 design compliance, UL 94 V-0 materials, no UL/CSA file (ledger certifier gap) | identical | unchanged certifier item |
| Electrical | 1.6 mH, Lstray 18 µH, 4.5 mΩ | **0.75 mH (-30/+50 %), Lstray 8 µH**, 3.2 mΩ | p.5 vector fit per winding: 5.07 pF / 4.40 kΩ (control 2203: 11.02 pF / 12.73 kΩ; round 3 has 11.078 / 12.691) |
| Stock (2026-10-16) | need 20 | JLC C7084710 0; **Mouser 62**; DigiKey 29; brokers excluded | gate PASS on Mouser (3.1x the need) |
| Price | 2203 JLC $5.65 | Mouser $11.70 at 10+ ($14.22 at 1); JLC list $14.08 (no stock) | +~$6 per board |

**EMI re-run (`scripts/run_emi_l1.py`).** The repo's stage-38 model of record is `07-conducted-emi/s19b/emi_s19b.py`
with `MODULE_S38`. It supersedes c29's `c29_emi.py` and D-22 rev B's `revb_check.py`, and it writes the
scorecard's EMI number. The wrapper imports it read-only and swaps only the board-L1 keys in the nominal parameter
set. The D-22 / round-3 / closed-form controls still build from the untouched BASE and pass unchanged. The
part-value sensitivities stay relative, so L1 -30 % and winding C x2 apply to the new part. The criterion is
unchanged: ≥ 6 dB nominal and in every sensitivity.

| Run | Nominal min | Sensitivity min (which) | 22 A sens min | Verdict |
|---|---:|---|---:|---|
| control (unchanged) = committed s38 | 12.374 | 8.186 (coil +board 51 pF) | 9.512 | PASS (bit-identical to results.json) |
| **B82726S2243A020** | **6.029** | **1.574 (X caps -20 %)** | 3.466 | **INCONCLUSIVE** |
| same, winding C/R from the 10 kHz-3 MHz fit | 6.029 | 1.574 | 3.466 | INCONCLUSIVE (insensitive to the fit) |
| attribution: fitted 2203 with only Lstray 18 → 8 µH | 6.052 | 1.589 | 3.480 | INCONCLUSIVE |
| 2243 + module DM 49.7 µH (DECISIONS 32 WE-HCFT 74437636355602 at 21 A) | 7.061 | 2.620 | 4.511 | INCONCLUSIVE |
| 2243 + module DM 82 µH | 10.059 | 5.657 (X -20 %) | 7.549 | INCONCLUSIVE |
| **2243 + module DM 100 µH** | **11.139** | **6.951** (coil +board 51 pF) | 8.277 | **PASS** |
| 2243 + module DM 120 µH | 11.152 | 6.963 | 8.289 | PASS |

- **Mechanism.** The binding line moves from 180 kHz (CM, 150 k-30 M AV) to **70 kHz: the 2nd harmonic of fs =
  35 kHz, bus-ripple DM, 9-150 kHz QP.** At 170 V / 28 A: 80.8 dBµV against the 86.9 dBµV limit.
- **The cause is L1's stray inductance alone.** L1's 18 µH stray with C2 is a DM pole on the board, and the
  attribution run reproduces the whole loss from 18 → 8 µH. Halving the CM inductance costs nothing measurable here.
- The aux-supply CM bound changes only from 27.3 to 26.1 dB.
- **What restores PASS.** About 10 µH of DM inductance has to come back somewhere. The cheapest place is the off-board
  inlet module. `MODULE-REQUEST.md` still lists its 2 x 41 µH DM inductors without an MPN.
  - **≥ 100 µH per line (at 21 A bias) passes**, and so does 120 µH.
  - The "module DM 80 µH" sensitivity in this model is -24 % of nominal, so 100 µH nominal covers saturation down to
    about 76 µH.
  - The DECISIONS 32 part (49.7 µH at 21 A) is not enough with the 2243.
  - No 100 µH / 21 A DM inductor was selected, and its heat against the module allowance (3.6 W for both inductors) is
    open.

### 1b. Other chokes (survey: JLC parametric search, Octopart)

| Part | Stock 10-16 | Fit | Verdict |
|---|---|---|---|
| B82726S2183N020 (TDK, 18 A, 1.3 mH, 5 mΩ) | Mouser 229, DigiKey 120, JLC 28 | N020 series, TR +50 °C (series sheet) | **rejected**: 15 / 18 = 0.83 fails the ledger's 80 % rule even at TR |
| Würth 7448052502 (WE-CMBNC nanocrystalline, 2.5 mH at 10 kHz, 25 A at 70 °C, 2.2 mΩ, 300 V AC, **ENEC10 / VDE 40048238**, AEC-Q200) | **DigiKey 981, Mouser 281, JLC 281** ($12.14 at 10+ JLC) | 36 x 23 x 34 mm fits the ~46 x 32.8 mm slot, but the pin grid is **15 x 25 mm, ø2.9 holes**, against 10 x 25 / 2.5 mm | **layout change** (L1 footprint only, inside its own slot). Its p.2 Z(diff) curve, about 100 Ω near 1.5 MHz, implies roughly 10 µH DM stray: the same order as the 2243, so expect the same 70 kHz DM line. Not digitised or run. Better approval basis than the TDK parts |
| KEMET SC-20-201 (2 mH, 20 A, 10 mΩ) | DigiKey 57, Mouser 12 | different footprint | not qualified: 4.5 W copper at 15 A (2.2x the 2203); stray unpublished |
| TDK B82726E6203B041 (20 A, 2.7 mH, 600 V) | DigiKey 169 | different housing, no sheet reachable | not qualified |
| No other part with the IND2421-G-E 10 x 25 mm drawing is in authorised stock | | | |

**Recommendation (decided).** For the 20-board prototype lot, fit **B82726S2243A020**: Mouser 62 covers the lot 3x,
and it is BOM only on the board. Raise the inlet-module DM requirement to **≥ 100 µH per line at 21 A**, which makes
the model PASS (11.14 / 6.95 dB).
- If the prototype module cannot carry that, the lot runs at nominal 6.03 dB, with an INCONCLUSIVE sensitivity set
  (X caps -20 % reads 1.57 dB). Record that as a prototype-only deviation and keep the 2203 pre-order (29 weeks) for
  production.
- Brokers stay excluded for this safety part.

## 2. C3 / C4 (line-to-PE Y1 capacitors)

**Role (netlist and ledger).**
- C3: L_FILT to PE; C4: N_FILT to PE. Both sit on the load side of L1.
- Footprint `Murata_DE1E3RA222MA4BP01F_P10.0_Pad1.5_ReviewOnly`: P10, drill 0.9 mm. C3 at (225.0, 102.8), C4 at
  (225.0, 109.1); the courtyards are 0.71 mm apart.
- They are the board's only Y capacitance (the D-22 module Y was removed at s38), so they set S1 together with the
  supplies.
- Class: SAFETY, Y1. Approvals: UL/cUL UL60384-14 / CSA E60384-14 file **E37921**, ENEC (VDE) EN60384-14
  **40043033**, CQC **CQC16001138225**.

| Candidate | Spec / approvals | Rating vs stress | Body / leads | S1 (132 V, +tol, record method) | Stock 10-16 | Price at 40 |
|---|---|---|---|---|---|---|
| **DE1E3RA222MA4BP01F (fitted)** | Murata Type RA, P01F: Y1 300 / X1 440 V AC, DC 1 kV, -40..125 °C; certificates above | 139.7 / 300 = 0.466 (rule 0.8); surge 2.2 / 8 kV | D 9.0, T 4.0, F 10.0, d 0.6, A4 long leads | 0.2412 mA, margin 8.8 µA | **Mouser 773, Newark 507, DigiKey 173**, JLC 6 | Mouser $0.545 |
| **DE1E3RA222MJ4BH01F** | Type RA, H01F: **Y1 400** / X1 440 V AC, DC 1 kV; same E37921 / 40043033 / CQC16001138225; 8 kV impulse life test, AC 4 kV dielectric | 139.7 / 400 = **0.349** | **identical body** D 9.0, T 4.0, F 10.0 ±0.8, d 0.6; J4 short crimp (3.5 +1.0/-0.5 mm below the crimp) | 2200 pF ±20 %: **0.2412 mA, unchanged** | **JLC C7170908 104**, Mouser 6,002, DigiKey 5,409 | JLC $0.85; Mouser $0.51 |
| DE1E3RA222MN4AP01F | the **same P01F spec** as fitted (Y1 300 V) | as fitted | same body, N4 taped leads | unchanged | JLC 74 (1.85x the need), Rutronik 48,600 (MOQ 600) | JLC $0.069 |
| DE1E3RA222MA4BQ01F | Q01F: Y1 500 / X1 500 V AC, same certificates | 0.279 | **D 11.0, T 6.0**: the C3-C4 body gap falls to about 0.3 mm | unchanged | JLC 147, Mouser 7,643 | JLC $0.22 |
| Vishay VY1222M47Y5UQ6TV0 | VY1: Y1 500 / X1 760 V AC; UL 60384-14, CQC (approval list not fully read) | 0.279 | **D 12.0**, F 10, d 0.6 | unchanged | JLC 11,977, Newark 56,249 | JLC $0.22 |

- **S1 method** (`scripts/s1_leakage_alt.py`): imports the record's `leakage_budget.py` (its `main()` is not called) and
  replaces the C3/C4 row with each part's nominal x (1 + tolerance).
  - Every candidate is 2200 pF ±20 % (2.64 nF maximum), so S1 stays **0.24123 mA with an 8.77 µA margin**.
  - Control: ±30 % gives 0.2522 mA and FAILs.
  - The S1 budget leaves no room for any part above 2.64 nF maximum, so only 2.2 nF ±20 % (or less) parts qualify.
- **Creepage.** The same P10 pads and drill give the same 8.5 mm copper gap between L_FILT/N_FILT and PE. Each
  candidate's own insulation is a certified Y1 body. Same-body parts change nothing. The 11-12 mm discs leave C3 and C4
  bodies about 0.3-1 mm apart (`results/board_fit.json`): mechanically tight, so they are not preferred.
- **Lead trim** (ASSEMBLY.md: ≤ 2.5 mm below the board). J4 leads protrude 1.35-2.85 mm from a 1.65 mm board, so trim
  the upper tolerance, as with today's A4 long leads.
- **Recommendation.** No change is needed: the fitted MPN passes the gate on Mouser alone (19x the need), and JLC
  Global Sourcing or a consigned buy covers it. If JLC's own stock is preferred, **DE1E3RA222MJ4BH01F** is a BOM-only
  swap with the same body and certificates and a higher Y1 rating.
  - Ledger edits needed: Y1 rating 300 → 400 V, and the H01F spec reference (Murata, Jun 2023, LCSC copy sha256
    c959488a...).

## 3. D6-D9 (gate turn-off diodes)

**Role.**
- `power_stage_120v.ato` turn-off branch: the PMEG6030EP anode at the gate, the cathode through R53/R54/R57/R58 (1 Ω)
  to the driver OUT. It runs in parallel with the 68 Ω 2512 turn-on resistor, and Cgs is 4.7 nF C0G (stage 42,
  candidate 39).
- The diode sets the turn-off speed and the off-state hold (Miller clamp) against the partner's dv/dt.
- Stresses from the records:
  - VR up to 15.5 V for about 1 µs per cycle;
  - turn-off peak current of several amps;
  - 443.6 nC per turn-off at 60 kHz, about 14 mW of heat;
  - D7 at 113.1 °C in the release case (B3 estimate) against Tj 150 °C;
  - Schottky, so no recovery charge.

**Candidates** (datasheets in `sources/diode-*`, values in `results/diode_bounds.json`). All are in SOD-128 /
CFP5-class flat-lead packages, the same `D_SOD-128` footprint (pads 1.4 x 2.1 mm at 4.4 mm).

| Part | VRRM (vs 15.5 V) | IF(AV) / IFSM | VF max 25 °C | Cd typ 1 V | Tj | JLC 10-16 | Price at 80 |
|---|---|---|---|---|---|---|---|
| **PMEG6030EP,115 (fitted)** | 60 V (3.9x) | 3 A / 50 A | 0.33 / 0.44 / 0.53 V at 0.1 / 1 / 3 A | 360 pF | 150 °C | **9,298** (C456127) | $0.318 |
| **PMEG6030EP-QX** | 60 V | 3 A / 50 A | identical table | 360 pF | 150 °C | **2,763** (C5829108) | $0.325 |
| PMEG4030EP,115 | 40 V (2.6x) | 3 A / 50 A | 0.32 / 0.42 / 0.49 V | 350 pF | 150 °C | 28,255 | $0.227 |
| PMEG6020EP,115 | 60 V | 2 A / 50 A | 0.34 / 0.46 / 0.53 (2 A) | 240 pF | 150 °C | 4,787 | $0.148 |
| PMEG6030ELPX | 60 V | 3 A / 70 A | 0.50 (0.1 A) / 0.67 (3 A) | 315 pF | 175 °C | 1,260 | $0.277 |
| ROHM RBR3LAM60B / RB050LAM-60 | 60 V | 3 A / 75-80 A | 0.56 V at 3 A | curve only | 150 °C | 4,977 / 1,724 | $0.11 / $0.20 |
| ST STPS360AFY (SOD128Flat) | 60 V | 3 A / 65 A | 0.61 V at 3 A | not read | 175 °C | 339 | — |

**c39 re-run (`scripts/c39_diode_rerun.py`).**
- What runs: the gate-network-2026-10-15 harness, `gn.py` imported read-only and writing to `results/c39-sims/`, on
  the adopted network `split68_1_cgs4p7_tt125`, full grid of 640 runs (S1 ZVS, S2, S4, S5, both ESL, legs A/B, every
  driver/temperature corner, typical Qrr).
- The diode model is swapped. Nexperia's SPICE files are behind a 403, so the alternates are covered by bounding models:
  - **vfhi** (IS / 4000): VF 0.50 / 0.59 / 0.68 V at 0.1 / 1 / 3 A. That is at or above the 25 °C maximum of every
    candidate (the ELP's 0.50 / 0.67 V is the highest).
  - **cjhi** (CJO x 1.6): 535 pF at 1 V, against the 360 pF maximum typical.

| Metric (screen) | committed | control (vendor model) | vfhi | cjhi |
|---|---:|---:|---:|---:|
| max off-gate, all cases (1.9 V) → Miller-clamp margin | 0.497 | 0.497 → **1.403 V** | 0.871 → **1.029 V** | 0.502 → **1.398 V** |
| S4 slew ESL 10 / 1.06 nH (56 V/ns) | 49.7 / 49.15 | 49.7 / 49.15 | 49.68 / 49.15 | 49.51 / 48.99 |
| S4 diF/dt (1,040 A/µs) | 244 | 244 | 243 | 242 |
| S1 worst t_trans (DT 340 ns) → turn-off margin | 190.2 | 190.2 → **149.8 ns** | 194.3 → **145.7 ns** | 190.2 → **149.8 ns** |
| S1 ZVS | 80/80 | 80/80 | 80/80 | 80/80 |
| S5 off-gate | -0.219 | -0.219 | +0.016 | -0.221 |
| all screens | 640/640 | 640/640 | 640/640 | 640/640 |
| E_off S1 37 A, worst of the 40-run loss grid | 9.0 µJ (README 3a) | 9.02 µJ | 9.95 µJ (+0.9) | 9.02 µJ |
| S1 37 A conduction penalty E_extra | — | 5.44 µJ | 6.27 µJ | 5.45 µJ |

The control reproduces the committed `results/full.md` row exactly (max |Δ| = 0.0 on every metric).

**Recommendation.** No change: the fitted part has 9,298 at JLC (116x the need). If it drops again, fit
**PMEG6030EP-QX**, a BOM-only swap with the same tables, Rth and package, so the control run covers it. Any other
listed part with VF and Cd inside the bounds also passes on this model: PMEG4030EP, PMEG6020EP, PMEG6030ELP. The ROHM
and ST parts are covered on VF only, because their capacitance is published as a curve.
- The JSMSEMI clone stays unqualified.

## Bench checks still needed

- **L1 = 2243:**
  - measure a sample's stray inductance (8 µH typical; the 70 kHz DM line depends on it);
  - run a 9-150 kHz QP pre-compliance at fs = 35 kHz with the actual inlet module (BENCH-PRECOMPLIANCE);
  - check L1 local air (the existing DECISIONS.md:836 item; the margin rises to 82.5 °C).
- **Inlet module:** bench L at 21 A DC for whichever ≥ 100 µH DM inductor is chosen, and its heat against the module
  allowance.
- **C3/C4 (if H01F):** none beyond today's items: surface temperature ≤ 125 °C, and the measured touch current, which
  is unchanged.
- **D6-D9:** none new. The D-8 double-pulse bench already measures the off-gate at the S4 edge. With a non-Nexperia
  part, also check its Cd at 1-15 V against the 535 pF bound.

## Notes on the repo records

- **The scorecard's B15 counts for C3/C4 and D6-D9 are snapshot artefacts.**
  - C3/C4: the 2026-10-15 snapshot read no distributors for this line (`octopart_read` False), but Mouser held 773.
  - D6-D9: JLC read 7 on 10-15 and 9,298 on 10-16.
  - Re-taking the snapshot clears both lines without any MPN change.
- `s19b/README.md` §4 says the D-22 control reproduces "Δ = 9×10⁻¹⁰ dB", but the committed `results.json` (and this
  re-run) has 0.207 dB and a transfer-parity error of 1.17. Both are within the asserted 1 dB limit; the README text is
  stale since the BASE coil capacitances changed (study 16).

## Files

- `scripts/` (run with `python3 -I`, numpy/scipy from Miniforge; `board_fit.py` with KiCad's bundled python3 -I):
  - `fit_b82726_curves.py`: vector digitisation of the TDK p.5 curves and the R||L||C fit (→ `results/b82726_fit.json`);
  - `run_emi_l1.py`, `emi_compare.py`: the EMI re-runs (`results/emi-*/results.json`, `results/emi_compare.json`);
  - `l1_rating.py`: L1 current / temperature margins;
  - `s1_leakage_alt.py`: the S1 touch current;
  - `diode_bounds.py`, `c39_diode_rerun.py`, `c39_summary.py`: the D6-D9 bounds and the c39 re-run
    (`results/c39-sims/`, `results/c39_summary.json`);
  - `board_fit.py`: read-only footprint and courtyard check on e842d9c8;
  - `jlc_fetch.py`, `octopart_fetch.sh`, `octopart_parse.py`: copied from the repo with their caches redirected here;
    `fetch_lcsc_ds.py` fetches datasheets; `build_stock_snapshot.py` builds the snapshot.
- `sources/`: the datasheets read, with their sha256 values in `source.json` or as quoted above. They are untrusted
  data and were only read with pdftotext.
- `snapshots/`: the raw JLC and Octopart reads, `octopart-2026-10-16.json`, and `STOCK-2026-10-16.csv`.
