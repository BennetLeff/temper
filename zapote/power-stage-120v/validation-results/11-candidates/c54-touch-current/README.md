# c54: touch current (OPEN-ITEMS S1): governing limit, contributors, and the C3/C4 trade

Desk study, 2026-10-18. Nothing outside this folder was edited, and nothing was committed. Every number below comes
from the `python3 -I` scripts in `scripts/` (section 8). The proposed edits are patch files in `results/`.

## 0. Answer

| Question | Result |
|---|---|
| Governing limit | **0.5 mA**, UL limit for a grounded (3-wire) **portable** cord-connected appliance, measured with the ground open in both polarities. It applies through **UL 1026**. Confidence: **high in the value, medium in the clause and classification**: the UL 1026 clause text was not read, and the certifier could class the unit as stationary or as UL 858 counter-mounted, which would give 0.75 mA. |
| Margin at the 60 Hz DESIGN row (0.2412 mA) | **0.259 mA (52 %) to 0.5 mA**; 0.509 mA to 0.75 mA. Against the self-imposed 0.25 mA budget it is still 8.8 µA (3.5 %). |
| Contributors at 132 V / 60 Hz | C3/C4 Y 0.1314 mA (54.5 %), PS3 MPM-65-15ST 0.0600 (24.9 %), PS2 MPM-20-24 0.0480 (19.9 %), coil 31 pF 0.0019 (0.8 %), SCF31X 0 (no PE terminal). Every term is already a bound: Y +20 %, 132 V, datasheet-maximum supplies ×1.2. |
| C3/C4 → 1.5 nF / 1.0 nF | 60 Hz: 0.1994 / 0.1696 mA. **EMI on the board of record: sensitivity minimum 3.62 / −0.30 dB, both INCONCLUSIVE**, against the ≥ 6 dB rule and today's 6.95 dB. The scorecard nominal goes from 11.14 to 7.79 / 4.24 dB. |
| Remove one Y | **No change** (0.2412 mA). UL tests both polarities, and the worst polarity still sees the remaining capacitor. |
| **Decision** | **No BOM change: C3/C4 stay DE1E3RA222MJ4BH01F 2.2 nF.** The 50 % budget row stays as it is and still passes. Add a stricter-scope check: the estimated lab reading, 60 Hz plus the 35–60 kHz term at the worst tolerance corner, must be ≤ 0.375 mA (75 % of 0.5 mA). Today it is **0.306 mA (61 % of 0.5 mA)**. |
| Patches | `results/bom-patch.json` (no change, stock re-read, alternates with the reason each was rejected); `results/ledger.patch` (C3/C4 entry; `gate.py` PASS on the patched copy); `results/open-items.patch` (row S1). Both patches pass `git apply --check` from the repo root. |

Why 25 % below the 0.25 mA budget (≤ 0.19 mA) is the wrong target here:
1. **No same-footprint part reaches it and keeps EMI.** Only 1.0 nF gets the 60 Hz row to 0.17 mA, and its EMI minimum is −0.30 dB.
2. **Lowering Y moves current into the switching-frequency term**, which the lab's meter also reads. At 1.5 nF the 60 Hz row drops by 42 µA, but the estimated reading barely moves: 0.249 → 0.241 mA nominal, 0.306 → 0.302 mA at the worst corner.
3. **The row's 8.8 µA is not a safety margin.** It is the gap to a 2× factor applied on top of stacked bounds. The margin to the limit is 0.26 mA. The open risks are the HF term, the classification, and cold-capacitor tolerance (section 6). Each is now checked or flagged on its own, not hidden inside the 2× factor.

## 1. Governing limit and basis

| Item | Text / finding | Status |
|---|---|---|
| UL limit values | "the maximum leakage current for a 50 or 60 hertz source cannot exceed 0.5 mA for portable two-wire and three-wire cord and plug-connected appliances, and 0.75 mA for three-wire cord and plug-connected fixed or stationary appliances". Test: "connected to a power source with an open ground", correct and reverse polarity. Metal-sheathed heating elements are allowed 2.5 mA for 5 min. (IAEI, "UL Question Corner: Leakage current", Feb 2019) | Secondary source written by UL staff; names no clause |
| UL household-appliance clause wording | UL 982, 4th ed., sec. 23, as quoted in Chroma AN 19071/19073 p.3: "The leakage current of a cord-connected appliance rated for a nominal 120 V supply when tested with 23.3 – 23.7 shall not be more than: a) 0.5mA for an ungrounded (2-wire) portable, stationary, or fixed appliance b) 0.5mA for an ungrounded [sic, grounded] (3-wire) portable appliances, and c) 0.75mA for a grounded (3-wire) stationary or fixed appliance employing a standard attachment plug rated 20A or less" | Verbatim, but from a sibling standard. The same pattern is expected in UL 1026 (**not confirmed**) |
| Second independent source | AAFES TM H-13: 0.5 mA grounded portable, 0.75 mA grounded stationary/fixed; the chassis ground is detached at the plug | Secondary source |
| UL 1026 scope (6th ed., 1.1, read) | "household electric cooking and food serving appliances, rated at 250 V or less … for use in ordinary locations". 1.2 excludes "household electric ranges" and skillets, woks and fryers, but not hot plates or cooktops. Retail portable induction hot plates claim UL 1026 (retailer listings only) | Read on shopulstandards.com |
| UL 858 scope (16th ed., 1.1, read) | "household cooking equipment that is floor or cabinet supported, wall-mounted, counter mounted, or combinations thereof … for installation in accordance with the National Electrical Code"; 1.5: counter-mounted means "intended for mounting in or on a counter". The table of contents has **sec. 55 "Leakage Current Test for Cord-Connected Appliances Rated 120 V, 1.75 kW or Less"** (UL catalog; Intertek lists it as sec. 51); its limits were not read | Scope read; sec. 55 limit **not confirmed** |
| Classification | A countertop cooker that is not mounted and can be picked up is a UL 1026 portable appliance, so the limit is 0.5 mA. If Temper is certified as installed / counter-mounted under UL 858 (the project's S15 cites UL 858 25.3.1), sec. 55 governs, likely at 0.75 mA as a grounded stationary unit. **0.5 mA is the conservative reading in both cases.** | Certifier question (CERTIFIER-CHECKLIST entry 0) |
| Meter | UL-style 1500 Ω ∥ 0.15 µF, frequency response to 100 kHz (Compliance West LCB-UL product page; Simpson 229-2: ANSI C39.5 network). The UL appliance clause wording for it was not read | Secondary source |
| Test voltage | Not read for UL. The Chroma line-leakage figure shows "+10 % (120 VAC + 12 V)". The model uses 132 V; corners run to 139.7 V | Basis kept |

Margins on the DESIGN row (0.2412 mA): 0.259 mA to 0.5 mA (48.2 % of the limit), 0.509 mA to 0.75 mA (32.2 %), and
8.8 µA (3.5 %) to the 0.25 mA budget. With the 60 kHz estimate at its worst corner (0.306 mA), the margins are
0.194 mA to 0.5 mA and 0.069 mA to the new 0.375 mA check.

## 2. What makes up 0.2412 mA (`leakage_c54.py`, imports the committed `leakage_budget.py` read-only)

The touch current per polarity is the hot line's Y capacitance plus each supply's datasheet maximum. The script reproduces the committed result.json value to 1e-12.

| Contributor | Basis value (132 V, Y +20 %, ×1.2) | Share | Nominal Y, supplies ×1.0 | Source |
|---|---|---|---|---|
| C3 (or C4) 2.2 nF Y1 | 0.1314 mA | 54.5 % | 0.1095 | Murata EGD08G p.9: 2200 pF ±20 % |
| PS3 MPM-65-15ST (chassis, SELV bonded to PE through R38) | 0.0600 | 24.9 % | 0.0500 | MPM-65-SPEC p.2: < 100 µA / 264 VAC, primary to DC output |
| PS2 MPM-20-24 (board) | 0.0480 | 19.9 % | 0.0400 | MPM-20-SPEC p.2: < 80 µA / 264 VAC |
| Coil to PE, 31 pF +20 % | 0.0019 | 0.8 % | 0.0019 | DECISIONS item 20 |
| SCF31X inlet CM choke | 0 | 0 | 0 | Series element with no PE terminal; the module's four Y caps were removed at s38 |
| *HV nodes to PE, outside the committed model* (CBRP/CBRN 10 + 10, tabs 14.0, sw_a 8.4, sw_b 9.1 = 51.5 pF) | *+0.0026 (bound at full line V)* | | | s19b BASE and the scorecard EMI nominal params |

Corners (`summary.json → corners`):

| Case | mA | % of 0.5 |
|---|---|---|
| 120 V, nominal Y, supplies ×1.0 | 0.183 | 36.6 |
| 132 V, Y +20 %, ×1.0 (supplies tested at 60 Hz) | 0.2232 | 44.6 |
| **132 V, Y +20 %, ×1.2 (committed basis)** | **0.2412** | **48.2** |
| 134.6 V (1.06 × 127), Y +20 %, ×1.2 | 0.2460 | 49.2 |
| 139.7 V (127 + 10 %), Y +20 %, ×1.2 | 0.2553 | 51.1 |

The budget row is a ceiling on adding capacitance to PE: it allows 0.147 nF more per line, or supply leakage ×1.081.
It is not a measure of distance from the limit.

## 3. Options

EMI comes from `emi_y.py`, which runs the committed s19b model of record with nominal-key patches only. Board of record means L1 B82726S2243A020 with module DM 100 µH, the scorecard EMI source. Production means L1 2203 with module DM 41 µH.

HF comes from `hf_y.py`, the committed co-design `hf_touch.py` estimator pointed at the current s19b model and the board of record. It uses line-crest sources, the UL-style meter, and the worst of the corners nominal, chokes −30 %, Y ±20 % and coil + board 51 pF.

| Option | 60 Hz mA | vs budget | EMI board of record: nominal / sensitivity min (dB) | EMI production | HF UL-meter estimate, nominal / worst (mA) | Lab-reading estimate, nominal / worst (mA) |
|---|---|---|---|---|---|---|
| **O0 as built, 2.2 nF** | 0.2412 | +8.8 µA | **11.14 / 6.95 PASS** | 12.37 / 8.19 PASS | 0.062 / 0.188 (chokes −30 %) | 0.249 / **0.306** |
| O1 1.5 nF DE1E3RA152MJ4BH01F | 0.1994 | +50.6 µA (20 %) | 7.79 / **3.62** INCONCLUSIVE | 9.03 / 4.86 INCONCLUSIVE | 0.136 / 0.226 (coil 51 pF) | 0.241 / 0.302 |
| O2 1.0 nF DE1E3RA102MJ4BH01F | 0.1696 | +80.4 µA (32 %) | 4.24 / **−0.30** INCONCLUSIVE | not run | 0.092 / 0.154 | 0.193 / 0.229 |
| O3 delete C4 | 0.2412 | +8.8 µA | not run (unbalanced) | | | |
| O4 no Y | 0.1099 | | not run; −19.6 dB nominal even with L1 and module both SCF31X (co-design WRITEUP §3) | | | |

Readings:
- **The binding line in every Y case is CM at 180 kHz**, the 3rd harmonic of the 60 kHz window top, at 198 V / 28 A. The worst sensitivity is coil + board 51 pF. At 1.0 nF the chokes −30 % corner takes over at 52 kHz in the 9–150 kHz band.
- Y costs about 3.35 dB per 0.7 nF here, so no 2.2 → 1.5 nF step keeps 6 dB, let alone the scorecard's 11.1 − 0.5 dB.
- The production L1 gives the same verdict, matching the co-design study's 9.03 / 4.86 dB.
- The HF estimate does not fall monotonically as Y falls, because the filter's CM resonances move through the harmonics. At 1.5 nF it cancels the 60 Hz gain. At 1.0 nF it does not, but there EMI is near FAIL.
- **Lever not chosen: cap the firmware window top below 50 kHz.** Below 50 kHz the 3rd harmonic falls under 150 kHz, where the limit is looser. In this folder's nominal per-fs data at 1.5 nF, the 198 V / 28 A and 170 V / 22 A rows hold 16.7 dB or more (150 k–30 M) and 11.2 dB (9–150 k) for fs < 50 kHz. That is about today's 11.14 dB nominal.
  - It is a controller and product change: the minimum continuous power at the window top rises, and burst mode (H12) is open.
  - Only two of the six configurations were checked, and no sensitivities were run.
  - It would also ease S18 (PS2's rating sets the 60 kHz top). Use it only if the controller lane wants it for its own reasons, with a full verdict rerun.
- **Basis evidence that costs nothing:**
  - If MEAN WELL confirms the MPM touch-current test is at 60 Hz, the row is 0.2232 mA.
  - A measured supply leakage (F5 Test B) shrinks the 0.108 mA supply share. The one public IRM measurement is 6 % of its maximum.
  - Both are evidence, not design changes. They are listed in the S1 patch.

## 4. Decision

**Keep C3/C4 at 2.2 nF, Murata DE1E3RA222MJ4BH01F. No BOM, layout or firmware change.** Re-base S1 on the governing limit:

1. **The 60 Hz DESIGN row stays ≤ 0.25 mA** (50 % of 0.5 mA), unchanged; 0.2412 passes. It is read as a ceiling on capacitance to PE, not as a margin.
2. **New check: the lab-reading estimate is ≤ 0.375 mA** (75 % of 0.5 mA). The estimate is the 60 Hz row combined in quadrature with the worst-corner switching-frequency estimate on the UL meter. Today: 0.306 mA, ratio 0.612.
   - The remaining 25 % covers the meter and test-voltage reading (not read), the crest-to-cycle-RMS overstatement of the HF estimate (×≤ 1.41, conservative), and the E-characteristic cold excursion (section 6).
   - It is added to the ledger as a `gap`-severity check, so it marks PARTIAL rather than VIOLATION while it is an estimate.
3. **The first article settles it.** Measure the open-PE touch current at 132 V in both polarities with the 1500 Ω ∥ 0.15 µF meter. Expect ≤ 0.25 mA; release at ≤ 0.375 mA.
   - If the reading is above 0.25 mA, first replace the datasheet supply maxima with measured values (F5 Test B).
   - If the HF term dominates, the robust variant (L1 → SCF31X, co-design: HF ≤ 0.036 mA, which also re-enables 1.5 nF) or a coil-side shield is the lever. Both are re-layout or enclosure changes, not BOM swaps.

This is not a loosened gate. The 0.25 mA row is kept and still binds any added capacitance. The new check adds the HF term, which the 60 Hz row never covered, against a stated fraction of the real limit.

## 5. Patches (apply from the repo root; nothing applied)

- `results/bom-patch.json`: the decision (keep), and the fitted part's stock re-read:
  - JLC C7170908: 104 (2026-10-19T04:01Z).
  - Authorised distributors: Mouser 6,002, DigiKey 5,409, Newark 3,350, Future 500 (Octopart read 2026-10-19T04:06Z, each offer's own update date kept).
  - The datasheet basis with page numbers.
  - The rejected alternates, each with LCSC code, stock and reason:
    - 1.5 nF DE1E3RA152MJ4BH01F C6601328: JLC 0, Mouser 466, DigiKey 130.
    - 1.0 nF DE1E3RA102MJ4BH01F C6601326: JLC 0, DigiKey 4,758, Newark 493.
    - 1.0 nF DE1E3RA102MA4BP01F C6224759: JLC 3,980.
    - Delete-C4.
  - All the Murata codes are in the same EGD08G specification: p.6 UL/cUL UL60384-14 / CSA E60384-14 file **E37921**, Y1 AC400 V; p.9 part list. A swap would not have changed the approval basis.
- `results/ledger.patch`: `DE1E3RA222MJ4BH01F` (SAFETY). The UL file E37921 basis is unchanged.
  - New requirement row: 0.5 mA limit, with its basis and confidence.
  - The budget row re-sourced to this README.
  - New stress: HF-inclusive estimate 0.3059 mA.
  - New check `touch total`: 0.612 against 0.75, severity gap.
  - The first gap is rewritten (classification, meter, the HF bench item, "C3/C4 cannot be reduced"), plus a new datasheet gap (char. E cold excursion).
  - Verified: `gate.py --ledger results/ledger-patched.json` → RESULT: PASS.
- `results/open-items.patch`: row S1 rewritten with the limit, margins, decision, new check and bench items.

Proposed DECISIONS text (the owner numbers it):
> **S1 touch current re-based (c54, 2026-10-18).** The governing limit is UL's 0.5 mA for grounded portable
> cord-connected appliances (via UL 1026; value high confidence, clause unread; 0.75 mA if certified stationary or UL 858
> §55). C3/C4 stay 2.2 nF. The 1.5 / 1.0 nF same-footprint codes take the board-of-record EMI sensitivity minimum to 3.62 /
> −0.30 dB, and at 1.5 nF the switching-frequency touch estimate absorbs the 60 Hz gain. The 0.25 mA 60 Hz row stays (0.2412,
> a capacitance ceiling). New check: 60 Hz ⊕ worst-corner HF estimate (UL meter) ≤ 0.375 mA, now 0.306 mA. The first article
> measures it. Reverses if: the certifier's meter or test voltage puts the estimate above 0.375 mA, or the bench reads
> > 0.25 mA after measured supply values replace the datasheet maxima.

## 6. Residual risks

1. **Classification and clause unread.** The 0.5 mA limit is the conservative reading; neither UL 1026 nor UL 858 §55 text was read. Certifier entry 0.
2. **HF term.** It is an estimate: line-crest sources, a meter network from secondary sources, and the corner set of s19b. At the chokes −30 % corner it is 0.188 mA. The first-article reading is the evidence.
3. **Cold Y capacitance.** Char. E allows +20/−55 % over −25..85 °C on top of ±20 % tolerance (EGD08G p.11 item 7), and the spec gives no curve. The bound 1.44 × 2.2 nF gives 0.2675 mA at 60 Hz: over the 0.25 budget row, 53.5 % of 0.5 mA. The lab works at 15–35 °C room conditions. Added as a ledger gap.
4. **Supplies.** The 0.108 mA share rests on MEAN WELL maxima at an assumed 50 Hz test. The MPM parts list IEC 60601-1 / 60335-1 approvals and **no UL file** (S1 certifier item, unchanged).
5. **Off-board dependencies (unchanged):**
   - the D-22 module Y removal (with module Y kept: 0.653 mA);
   - PS3 = MPM-65-15ST;
   - for EMI, the ≥ 100 µH module DM inductors with the 2243 L1 (MODULE-REQUEST item 3, no part selected).
6. Parasitic HV-node capacitance (≤ 2.6 µA) and PS3 bracket capacitance (no data) are not in the committed rule.

## 7. Files

- `scripts/leakage_c54.py`: breakdown, corners, options, controls → `results/summary.json`.
- `scripts/emi_y.py`: committed s19b EMI model with patched C3/C4 (and L1 / module for the board of record) → `results/emi-{bor,prod}-Y*/results.json` and logs.
- `scripts/hf_y.py`: switching-frequency touch estimate → `results/hf_touch.json`.
- `scripts/make_patches.py`: writes `results/bom-patch.json`, `ledger.patch` (+ `ledger-patched.json`), `open-items.patch`.
- `scripts/jlc_fetch.py`, `octopart_fetch.sh`, `octopart_parse.py` (copied from b15, online): `results/jlc-raw/`, `results/octopart/_fetch.log`, `results/octopart-2026-10-18.json`. The 2 MB HTML pages were parsed and then deleted.
- `results/inputs/copper-dump-s19b-summary.json`: s19b's own copper cache, written by `hf_y.py`'s import.

## 8. Reproduce

From `zapote/power-stage-120v/validation-results/11-candidates/c54-touch-current`, with Miniforge numpy:

    python3 -I scripts/emi_y.py bor 2.2 results/emi-bor-Y2.2     # control: 11.139424 / 6.951316 dB (scorecard source)
    python3 -I scripts/emi_y.py bor 1.5 results/emi-bor-Y1.5
    python3 -I scripts/emi_y.py bor 1.0 results/emi-bor-Y1.0
    python3 -I scripts/emi_y.py prod 2.2 results/emi-prod-Y2.2   # control: 12.374474 / 8.186315 dB (s19b results.json)
    python3 -I scripts/emi_y.py prod 1.5 results/emi-prod-Y1.5
    python3 -I scripts/hf_y.py
    python3 -I scripts/leakage_c54.py      # exit 1 if a control fails (DESIGN row, EMI controls, one-Y polarity)
    python3 -I scripts/make_patches.py

Each EMI run takes a few minutes with 2 BLAS threads. The verdict-excluded scenarios (REC*, STACKED, INFO_*,
board_only …) are skipped, which does not change nominal_min or sensitivity_min. Both controls reproduce to < 1e-6 dB.

## 9. Sources

- IAEI, UL Question Corner: Leakage current: https://iaeimagazine.org/columns/ul-question-corner/ul-question-corner-leakage-current/
- Chroma AN 19071/19073, Tutorial on Safety Standard Compliance for Hipot Testing (UL 982 sec. 23 quote, p.3): http://www.chromausa.com/pdf/app-notes/AN%20-%2019071,%2019073%20-%20Tutorial%20on%20Safety%20Standard%20Compliance%20for%20Hipot%20Testing%20-%2004052013.pdf
- AAFES TM H-13: https://www.aafes.com/qualityassurance/TM_H-13.htm
- UL 1026 scope: https://www.shopulstandards.com/ProductDetail.aspx?productId=UL1026 ; UL 858 scope: https://www.shopulstandards.com/ProductDetail.aspx?productId=UL858 ; UL 858 sec. 55 title: standardscatalog.ul.com/standards/en/standard_858_16 (search result; the page did not resolve) and Intertek Inform (sec. 51)
- Meter network: Compliance West LCB-UL (https://www.tequipment.net/Compliance/00-LCB-UL/Leakage-Detectors/), Simpson 229-2
- Murata EGD08G Type RA reference specification, Jun. 2023 (LCSC copy, sha256 c959488a2523ac21…, the same file for C6601328 and C7170908)
- Repo: `07-conducted-emi/leakage/` (README, leakage_budget.py, co-design-2026-10-15/WRITEUP.md), `07-conducted-emi/s19b/emi_s19b.py`, `11-candidates/b15-proto-alternates/`, `12-decisions/F5-LEAKAGE-DECISION.md`
