# Certifier and owner question packet (native-21), 2026-10-14

Status: **draft, not sent. Refreshed to s52 on 2026-10-16** (board of record, DECISIONS 74; the original text is 2026-10-14). The
touch-current, PS1 / PS2 / PS3, U44 and bank figures below are the s52 ones; `CERTIFIER-CHECKLIST.md` is the ranked list.
 One index of every open question the design is waiting on, so the outreach round is one
email per recipient. Each line points at the record that holds the evidence and the full wording; send those, not this
summary. The `$` column is the per-board effect at 500 where a record computes one.

## A. Certifier (UL 1026 appliance, 120 V~ 60 Hz nameplate)

### A1. Touch current (F5), which decides how far candidate 23 must go
| # | Question | Effect | Record |
|---|---|---|---|
| 1 | Limit class: portable 0.5 mA or stationary 0.75 mA (countertop cooker, cord and plug) | **0.2412 mA as built since s38** (budget 0.25, margin 8.8 µA; S1, DECISIONS 50; s52 Y caps DE1E3RA222MJ4BH01F keep it) passes either | `validation-results/12-decisions/F5-LEAKAGE-DECISION.md` §1 |
| 2 | Supply-module leakage: measured on the product, or taken at the datasheet maximum (< 0.25 mA / 277 Vac) | sets Test A vs Test B | same, §2 |
| 3 | PS2's output is HOT-referenced (no PE bond): does its Y current count in the PE path? | was 0.419 -> 0.276 mA at the 2026-10-14 draft; 0.2412 mA total as built | `11-candidates/g06-g08-g10-supplies-sense-io/PROPOSALS.md` P3 |
| 4 | Test voltage and meter network for a 120 V product (model uses 132 V; HF weighting would help the coil term) | small | F5 record §1 |

### A2. Fusing
| # | Question | Effect | Record |
|---|---|---|---|
| 5 | F1: accept a UL-Recognized 248-14 supplemental fuse (Bel 0ADEC9250-BE) in place of the Listed Class CC KLDR025 | **-$18.86**, copper margin 0.99 -> 3.61 | `12-decisions/f1-data/f1_decision.py` gate G6; DECISIONS.md:1090-1092 |
| 6 | F1 open clips (Littelfuse 01250003H): voltage rating and agency file acceptance | release | `08-manufacturing-package/native-21/sourcing/inquiries/F1-CERTIFIER.md` (header notes the KLDR change; rewrite before sending) |
| 7 | "Branch breaker + Class CC F1, no inlet fuse" as the protection scheme | release | DECISIONS.md:335 |
| 8 | F2 (UMT-H 1.5 kA): rating on the approval, a supplemental fuse behind F1 in the blower branch, and R130's failure mode | release | `11-candidates/g06-g08-g10-supplies-sense-io/PROPOSALS.md` P2 (SAFETY); `c28-f2/` |
| 9 | Abnormal-operation test with the firmware current limit defeated | release | DECISIONS.md:1012 |

### A3. Insulation
| # | Question | Effect | Record |
|---|---|---|---|
| 10 | Same-layer inner paths count as solid insulation (reinforced, 2 mm per IEC 60335-1 29.3); all inner RES_A copper is >= 8.0 mm in plan view | release; also the basis for any 6-layer build | `fab/FAB-NOTE.md:22`; DECISIONS.md:756 |
| 11 | Working voltage on the coil lanes: line-cycle RMS or carrier-crest RMS | crest RMS = board-wide re-layout | DECISIONS.md:255, 489 |
| 12 | PD2 for the potted winding system | release | DECISIONS.md:489 |
| 13 | Potted PS1 (**PS1 is deleted since s38; no longer asked**): pins and joints as the clearance reference instead of the courtyard | **moot if candidate 23 lands** | DECISIONS.md:676 |
| 14 | **New:** PS2 (MEAN WELL MPM-20-24, on board) and PS3 (MPM-65-15ST, off-board, controller side; formerly IRM-20 / IRM-60) are approved to UL 62368-1 / IEC 61558 (OVC II under 62368), not to an appliance standard: accepted as components in a UL 1026 product? | release | IRM-20-SPEC 2025-11-21 p.2 "SAFETY STANDARDS"; ledger entries IRM-20-15 / IRM-20-24 |
| 15 | UL files from datasheets, not yet looked up: Chipanalog E511334 (U9 / U32; U44 is a second ISO6721FB since DECISIONS stage 40), RECOM E542996 (U41 / U42) | release | DECISIONS.md:1163; `11-candidates/c31-bom/README.md` |
| 16 | A SELV controller powered from a chassis Class II module (PS3) through a 292 mm harness | candidate 23 | PROPOSALS.md P1 "SAFETY" |
| 17 | Removing R1 / R2 | small | DECISIONS.md:352 |

### A4. Protective electronic circuit (monitor / DIS path)
| 18-24 | FMEA §7 questions 1-7: PEC status under 60335-1 19.11 (and UL 1026 / 858), dormant PEC faults, credit for dynamic signals, ISO6721FB barrier fault exclusion, shoot-through outcome under 19.13, <= 90 us response, crossing count | release | `11-candidates/c24-monitor-fmea/FMEA.md` §7 |

## B. Owner approvals (no outside party)
| # | Decision | Effect | Record |
|---|---|---|---|
| B1 | D3 / D17: approve Littelfuse 30KPA150A (unidirectional, same 30 kW) in place of Good-Ark 30KPA150CA | **-$15.92** ($19.64 -> 2 x $1.86 at 500); zero JLC stock for every 30KPA150 variant, so it is a sourcing quote first | `11-candidates/c31-bom/BUS-TVS.md`; DC-LINK-CLAMP.md forbids silent substitution |
| B2 | Restate the DC-link clamp target as the modelled return energy plus margin (allows a bench no-clamp test) | -$19.64 if the clamp goes | QUEUE.md "Owner or certifier decisions" |
| B3 | F1 to a 6.3 x 32 fast-acting fuse (reverses Class CC; needs A2 first) | -$26 to -$30 | QUEUE.md, g01 P2 |

## C. Supplier inquiries already drafted (separate recipients)
- JLC laminate / CTI: `08-manufacturing-package/native-21/sourcing/inquiries/CTI-JLC.md`. It names the 4-layer stack
  JLC041622-7628; if the six-layer study is adopted, re-ask for the 6-layer stack.
- Resonant bank (candidate 34): TDK B32643B8104J000 stock, lead time and taped MOQ for 2,500 pcs (5 per board x 500); JLC C3781430 and Avnet show 0, MOQ 2,080 untaped. Evidence: `11-candidates/c34-bank-margin/README.md`.
- Blocked-part samples: `08-manufacturing-package/native-21/sourcing/inquiries/SAMPLES-BLOCKED-PARTS.md`.
