# Certifier and owner question packet (native-21, board of record s53)

Status: **draft, not sent.** Refreshed to s53 on 2026-10-18 (OPEN-ITEMS S11). First written 2026-10-14; s52 refresh
2026-10-16. Board of record: stage 53, board SHA-256 `82af7bd93e62d1f2e6c7c2c2b971a4830bf6e09078bae3f269d8bead9a31fd27`
(DECISIONS 75; `fab/FAB-NOTE.md`). The BOM is s52's (DECISIONS 74).

What this is. One index of every open question the design is waiting on, so the outreach round is one email per
recipient. Each line points at the record that holds the evidence and the full wording. Send those records, not this
summary. `CERTIFIER-CHECKLIST.md` (same folder) is the ranked list with STRICT / RELIANT readings and the quote-request
email. The `$` figures are per board at 500 boards, where a record computes one.

Paths are relative to PS = `zapote/power-stage-120v`. `firmware/` is at the worktree root. `VR` = `PS/validation-results`.
`fab/`, `sourcing/`, `owner-items/` and `INDEPENDENT-REVIEW-2026-10-18.md` are under `VR/08-manufacturing-package/native-21/`.
Item numbers 1–24 keep their old numbers, because the checklist cites them. Items 25 onward are new at s53.

## A. Certifier

Product: cord-and-plug countertop induction cooktop, 120–127 V~ 60 Hz, NEMA 5-15P, US / Canada / Mexico
(nameplate decided 2026-10-08, `sourcing/inquiries/F1-CERTIFIER.md`). The repo cites UL 858 for the stuck-on rule
(OPEN-ITEMS S15, B10) and UL 1026 for the leakage limit (DECISIONS.md:846). No primary UL text has been read. **Which
standard governs is the first question** (`CERTIFIER-CHECKLIST.md` entry 0).

### A1. Touch current (S1)
| # | Question | Effect | Record |
|---|---|---|---|
| 1 | Limit class: portable 0.5 mA or stationary 0.75 mA (countertop cooker, cord and plug) | **0.2412 mA design** (budget 0.25 mA = 50 % of 0.5 mA; margin 8.8 µA), PE open, 132 V, datasheet-maximum module leakage. Passes either class. Unchanged since s38 (DECISIONS 50); the s52 Y caps DE1E3RA222MJ4BH01F keep it (DECISIONS 74); s53 card `leakage_touch_mA` 0.241 | `VR/07-conducted-emi/leakage/result.json` (DESIGN row); `VR/12-decisions/F5-LEAKAGE-DECISION.md` §1; `VR/10-benchmark/scorecard-native21s53.json` |
| 2 | Supply-module leakage: measured on the product, or taken at the datasheet maximum (PS2 MPM-20-24 < 80 µA at 264 VAC, PS3 MPM-65-15ST < 100 µA at 264 VAC) | sets Test A vs Test B; the margin (8.8 µA) is smaller than a meter reading's spread, so the bench decides | `leakage/result.json` items; F5 record §2 |
| 3 | PS2's output is HOT-referenced (no PE bond): does its Y current count in the PE path? | The 0.2412 mA DESIGN row **counts** PS2 (0.048 mA), so no credit is claimed. A "no" would lower the design figure | `leakage/result.json` items; `VR/11-candidates/g06-g08-g10-supplies-sense-io/PROPOSALS.md` P3 |
| 4 | Test voltage and meter network for a 120 V product (the model uses 132 V; HF weighting of the coil term is not credited) | small | F5 record §1 |

### A2. Fusing and overcurrent
| # | Question | Effect | Record |
|---|---|---|---|
| 5 | F1: accept a UL-Recognized 248-14 supplemental fuse (Bel 0ADEC9250-BE, cURus E20624, 30 kA at 500 VAC) in place of the Listed Class CC KLDR025.TXP | **−$18.86**. Copper margin 0.993 → 3.61. The s53 neck limit is 1,698 A²s (`min_ratio_all` 0.993 against KLDR025's 1,710 A²s clearing I²t); Bel's 470 A²s against the same limit gives 3.61 | `VR/12-decisions/f1-data/f1_decision.py` gate G6, `SURVEY.md` §1a; `VR/02-protection-timing/shoot-through-f1/s53_necks.json` |
| 6 | F1 open clips, 2 × Littelfuse 01250003H (125 series, 30 A, UL Recognized E14721, **no voltage rating and no CSA file printed**): acceptable as the holder for a Class CC fuse? | release; if refused, F1 needs a Class CC holder (inlet-area layout change) | `sourcing/inquiries/F1-CERTIFIER.md` (rewritten to s53 on 2026-10-18); ledger entry KLDR025.TXP (`native-21/verification/datasheet-ledger/ledger.json`) |
| 7 | "Branch breaker + Class CC F1, no inlet fuse" as the protection scheme | release | DECISIONS.md:335 |
| 8 | F2 (Schurter UMT-H 3403.0279.23, 3.15 A T, cURus E41599): a supplemental fuse behind F1 in the blower branch; R130 (Vishay AC05, not UL-recognised) as its current limiter, and R130's failure mode | release | `VR/11-candidates/g06-g08-g10-supplies-sense-io/PROPOSALS.md` P2 (SAFETY); `VR/11-candidates/c28-f2/` |
| 9 | Abnormal-operation test with the firmware current limit defeated. The ≤ 15 A input limit is a firmware estimate (e_est 10 %, provisional); F1 never opens at 15–25 A. The R5 hardware average-current trip is designed but **not built** (deferred, DECISIONS 75) | release; a "must pass with firmware defeated" answer builds the R5 trip (`c53-r5-trip/DESIGN.md`) | DECISIONS.md:1014; `VR/11-candidates/c53-line-current-f1/README.md`; `VR/11-candidates/c53-r5-trip/DESIGN.md`; external review #11 (`VR/13-external-review-2026-10-13/FINDINGS.md`) |

### A3. Insulation
| # | Question | Effect | Record |
|---|---|---|---|
| 10 | Same-layer inner paths count as solid insulation (reinforced, 2 mm per IEC 60335-1 29.3). All inner RES_A copper is ≥ 8.0 mm in plan view. Closest on s53: C152.1 (RES_A) In1 / In2 rings 8.328 mm from the SELV v3v3 plane | release; also the basis for any 6-layer build | `fab/FAB-NOTE.md` ("Before mains-connected…" list); DECISIONS.md:758 |
| 11 | Working voltage on the coil lanes: line-cycle RMS or carrier-crest RMS | crest RMS = board-wide re-layout (coil lanes about 7.4 mm, RES_A to HV_RET / N_LS / BUS_P 6.3 mm) | DECISIONS.md:248, 257; `owner-items/m6m10/coil-voltage-28a/` |
| 12 | PD2 for the potted winding system | release | DECISIONS.md:491 |
| 13 | ~~Potted PS1: pins as the clearance reference~~ **Moot: PS1 is deleted since s38 (DECISIONS 50). Not asked.** | — | DECISIONS.md:678 |
| 14 | PS2 (MEAN WELL MPM-20-24, on board, TCO-switched): approvals verbatim "IEC 60601-1:2005+A1, TUV EN 60601-1, ANSI/AAMI ES60601-1, CAN/CSA C22.2 No. 60601-1 and IEC 60335-1 (Dekra)", 2 × MOPP, **no UL file printed**. PS3 (MPM-65-15ST, off-board, controller side, J13): IEC / ES / CSA 60601-1, **no UL file** (DECISIONS 47). Accepted as components in a UL 858 / UL 1026 product? (The IRM-20 / IRM-60 they replaced carried UL 62368-1.) | release; a "no" reverts to IRM supplies and breaks the leakage budget (0.653 mA with the module Y kept; 0.324 mA with an IRM-60 in PS3) | DECISIONS 47 ("Certifier"), 50 ("Reverses if"); ledger entry MPM-20-24; `VR/11-candidates/c23-supply-topology/README.md` |
| 15 | UL files to confirm (quoted from datasheets; UL Product iQ not read, it needs a login). **Barrier parts, from the s53 frozen netlist:** U1 / U2 Infineon 2EDR8259X, **reinforced SELV↔HOT barriers** (pins 1–8 SELV: PWM, v3v3, selv_gnd; pins 9–16 HOT), UL 1577 **E311313** 5700 Vrms, IEC 60747-17 cert 40055138, VIORM 1767 Vpk, VIOWM 1250 Vrms, CPG / CLR 8 mm, CTI > 400; U4 TI AMC1311BDWVR (HOT bus sense → SELV), reinforced per VDE / IEC 60747-17 cert 40040142, VIORM 2120 V, UL 1577 single protection **E181974** 5000 Vrms (SBAS786C p.9), no CSA entry; U36 Vishay VOL628A-2X001T, UL 1577 **E76222** (from Rev. 1.8 p.1; Rev. 1.9 prints no number); U9 / U32 Chipanalog CA-IS3720HW, UL 1577 **E511334**, no CSA certificate listed; U43 / U44 TI ISO6721FBDR (basic, E181974, used HS→LS, HOT-to-HOT); U41 / U42 RECOM R24C2T25/R-R (E542996 logo on p.1, HOT-to-HOT, not relied on); T1 Coilcraft CST3015-200ED (5000 Vrms 1 min, "designed for reinforced insulation", ≥ 8 mm; **no working-voltage figure and no approval file found: ask Coilcraft**). Barrier crossings in the netlist are only U1 / U2, U4, U9, U32, U36 and T1 | release | ledger entries for each MPN; independent review 2026-10-18 F4 (`INDEPENDENT-REVIEW-2026-10-18.md`); DECISIONS 79 |
| 16 | The SELV controller is powered from PS3 (MPM-65-15ST, off-board) over J13; on the C49 controller (`controller-j13-merge`) the logic 15 V comes from V15_BLW through an SS14 | candidate-23 basis | PROPOSALS.md P1 "SAFETY"; DECISIONS 79 |
| 17 | Removing R1 / R2 (X-cap bleed, 2 × 100 k) | small | DECISIONS.md:354 |
| **25** | **Laminate UL scope (S12, new).** The order names Kingboard KB-6164 core with KB-6064 prepreg (JLC "KB6164 - TG135"), JLC041622-7628, 4 layers, 1.6 mm, **2 oz outer and 2 oz inner (61 µm inner in the stack file)**. Kingboard's UL QMTS2 reprint (E123995, last updated 2026-02-20) lists **max internal copper 35 µm for KB-616(X) (KB-6160 / KB-6164) and 54 µm for KB-6165**; KB-6164F, KB-6165F and KB-6167F list 102 µm. CTI is PLC 3 at 1.40 mm on KB-616(X), KB-6164F, KB-6165 and KB-6165F (group IIIa, no margin to 175 V). MOT 130 °C on every row. Questions: (a) is a board recognised under a laminate row whose max internal copper (35 µm) is below the built 61 µm acceptable, or must the order move to a 102 µm row (KB-6164F / KB-6165F)? (b) is a UL PLC 3 rating accepted as IEC 60664-1 group IIIa evidence? (c) is JLC's board recognition (E479892, type JLC-4) the evidence you want, rather than the laminate file? | order remark and `stackup.json` change together; a PLC ≤ 2 demand means another fab (no JLC laminate has public PLC ≤ 2) | OPEN-ITEMS S12; DECISIONS 41, 46, 51; `owner-items/JLC-LAMINATE-QUESTION.md` (findings 2026-10-18); `sourcing/inquiries/CTI-RESEARCH-2026-10-14.md` |

### A4. Protective electronic circuit (monitor / DIS path) and stuck-on
| # | Question | Effect | Record |
|---|---|---|---|
| 18–24 | FMEA §7 questions 1–7: PEC status under 60335-1 19.11 (and UL 858 / UL 1026), dormant PEC faults, credit for dynamic signals, ISO6721FB barrier-short exclusion, shoot-through outcome under 19.13, ≤ 90 µs response, crossing count. Status since the draft: REF25 watchdog (B13 H1) built at s48; BIAS_GOOD = bias_ok AND PERMIT (option P) built at s50; the read-back on GPIO35 is on the C49 controller branch, not yet on a built controller | release | `VR/11-candidates/c24-monitor-fmea/FMEA.md` §7; `VR/11-candidates/fmea-s47-2026-10-15/README.md`; DECISIONS 67, 71, 79; OPEN-ITEMS B13 |
| **26** | **Stuck-on stage, UL 858 25.3.1 (S15, new to this packet).** A stage stuck on at normal current trips none of the firmware-independent trips (R5 Kelvin OCP, U7 OVP 280 V, BIAS_GOOD heartbeat, BUS_FAULT). The only firmware-independent cut is the TCO loop (J3): opening it removes PS2, and with it all gate drive, HOT5 and OCP_OK. It removes gate drive, not the power path: the bus stays live while plugged in. TCO rating and mounting are provisional. Is the TCO an acceptable 25.3.1 backstop? | architecture: a "no" needs a second independent means (the DNP inlet relay of `c53-stuck-on/S53-SCOPE.md` item 3 was not built at s53) | OPEN-ITEMS S15; `VR/11-candidates/c53-stuck-on/S53-SCOPE.md`; external review #6 |
| **27** | **End-of-line veto test (B8, new to this packet).** Force MON_GOOD_HA low, then MON_GOOD_HB low; the heartbeat stops and BIAS_GOOD drops within its hold time. Is this an acceptable routine test of the PEC in production? | production test spec | OPEN-ITEMS B8; FMEA §6c |

### A5. Other questions from the reviews (new)
| # | Question | Effect | Record |
|---|---|---|---|
| **28** | Bus discharge after unplugging: τ 6.6 s nominal (357 kΩ total bleed); 198 → 60 V takes 7.9–8.6 s. The plug-pin rule (< 34 V in 1 s) is met. Is a service-discharge time required, or a "wait 15 s" label? | label, or R3 / R4 → 100 k (4.0–4.4 s) | external review #10 (`VR/13-external-review-2026-10-13/FINDINGS.md`) |
| **29** | Which harmonic-current rule applies at 120–127 V (no active PFC; model PF 0.997 at 1.33 kW, 0.854 at 160 W)? | bench measurement plan | external review #2 |

## B. Owner approvals (no outside party)
| # | Decision | Effect | Record |
|---|---|---|---|
| B1 | D3 / D17: approve Littelfuse 30KPA150A (unidirectional, same 30 kW) in place of Good-Ark 30KPA150CA | **−$15.92** ($19.64 → 2 × $1.86 at 500); zero JLC stock for every 30KPA150 variant, so it is a sourcing quote first | `VR/11-candidates/c31-bom/BUS-TVS.md`; DC-LINK-CLAMP.md forbids silent substitution |
| B2 | Restate the DC-link clamp target as the modelled return energy plus margin (allows a bench no-clamp test) | −$19.64 if the clamp goes | QUEUE.md "Owner or certifier decisions" |
| B3 | F1 to a 6.3 × 32 fast-acting fuse (reverses Class CC; needs A2 #5 first) | −$26 to −$30 | QUEUE.md, g01 P2 |

## C. Supplier inquiries (separate recipients)
- **JLC laminate UL scope (S12):** `owner-items/JLC-LAMINATE-QUESTION.md`, send-ready, 2026-10-18. It replaces the
  CTI-only drafts `sourcing/inquiries/CTI-JLC.md` / `CTI-JLC-6L.md` (not sent; DECISIONS 41 settled CTI from public records).
- **Coilcraft (T1, new):** CST3015-200ED working voltage and approval file (A3 #15).
- **Resonant bank:** the prototype bank is TDK B32643H8104J000 (DigiKey 306 on 2026-10-16; DECISIONS 74). The 28 A part
  B32643B8104J000 is 28-week, MOQ 2080 (OPEN-ITEMS S28). Evidence: `VR/11-candidates/s52-proto-bom/README.md`.
- Blocked-part samples: `sourcing/inquiries/SAMPLES-BLOCKED-PARTS.md`.

## What changed in the s53 refresh (2026-10-18)
- Header to s53 (DECISIONS 75; BOM unchanged from s52).
- Standard: "UL 1026" heading replaced by "UL 858 / UL 1026, to be confirmed".
- A1 #3: the 0.2412 mA design already counts PS2; the old 0.419 → 0.276 mA history is dropped.
- A2 #5: copper margin restated on s53 (0.993); A2 #6: clip facts from the ledger; A2 #9: the R5 trip is deferred.
- A3 #14: PS2 / PS3 approvals corrected (MPM: IEC 60601-1, plus IEC 60335-1 on PS2; no UL file; the old text described IRM-20).
- A3 #15: U1 / U2 / U4 / U36 added with their barrier role (independent review F4); U43 / U44 named correctly as ISO6721FB.
- A3 #25 (S12 laminate), A4 #26 (S15 stuck-on), A4 #27 (B8 EOL test), A5 #28–29 (external review) added.
- DECISIONS line citations re-pointed (the file grew since 2026-10-14).
