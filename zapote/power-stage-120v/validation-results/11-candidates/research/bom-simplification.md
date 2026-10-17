# BOM simplification study, native-21 stage 19c (read-only research, 2026-10-13)

Baseline: `08-manufacturing-package/native-21/fab/bom-jlcpcb.csv` (92 lines, 357 placements, as built: 21 Basic, 60 Extended by the BOM text, 11 consigned/hand/substitute). Per-change rows are in `bom-simplification.csv` (21 rows; ids A = swap, H = hand-assembly, X = removal).

Method: every `LCSC Part #` in the BOM, and every candidate, was read live from JLC's public part endpoints on 2026-10-13 (the same endpoints `native-21/bom-simplification/jlc.py` uses): library type (`base` = Basic, `expand` = Extended), stock and the spec string. The Basic list was enumerated through the same API (`componentLibraryType=base`, 1206 resistors, MLCCs, diodes, comparators, logic). Human-readable pages: <https://jlcpcb.com/parts/basic_parts> and `https://www.lcsc.com/product-detail/<Cxxxx>.html`. Those pages are JavaScript, so I could not cite them as fetched evidence; the API record is the evidence. Scripts and raw JSON are in the session scratchpad only (the repo's `bom-simplification/raw/` is untouched). Nothing in the repo was modified except these two files.

## Headline: the cheap Extended-to-Basic work was already done

The 2026-10-09 study (`native-21/bom-simplification/PROPOSAL.md`, 25 safe items) already moved every commodity 0603/1206 resistor, the 100 nF/100 pF/1 uF/330 pF MLCCs, 1N4148W and MMBT3904 onto Basic parts, and those are in this BOM. What is left on Extended are parts for which JLC's Basic library has no equal-or-better member: the 0.1 % thin-film dividers, TL431/TLV431/LM4040/LM339/TLV3201 and the SN74LVC1G family (JLC Basic holds no TL431, LM339 or LVC1G part; only LM393, LM358 and 74HC logic), 1206 values off the Basic list (Basic 1206 is 0, 0.1, 1, 10, 20, 22, 100, 120, 300 ohm and 1, 2, 4.7, 10, 100 k, 1 M only), the 1210 10 uF/50 V MLCC, the C0G parts, the polymer cap, power and safety parts. So the realistic remaining saving is small and mostly needs a check.

## Totals (per order, one extended fee of $3 per line; part-price deltas not claimed because the commodity prices in the sourcing survey are class-default estimates)

| Risk class | Rows | Lines saved | Extended lines saved | $ at 5 boards | $ at 500 boards |
| --- | --- | ---: | ---: | ---: | ---: |
| low | A1, A2 | 0 | 2 (1 is a stale label, so 1 real) | $3 real (A1 is $0) | $3 real |
| med | A3-A7, A11 | 3 | 6 | $18 | $18 |
| high (protection, gate-drive or re-spin) | A8-A10, A12-A14 | 4 | 6 | $18 | $18 |
| all swaps | 14 | 7 | 14 (13 real) | $39 | $39 |
| hand-assembly removal (H1-H3) | 3 | 0 | -3 (adds 3 fees) | -$9 | n/a past stock |

Hand/consigned lines that become JLC-assemblable: 3 of the 11 (H1 J3/J11, H2 C1/C2 for 5-board lots, H3 U1/U2 if the -Q1 certificate holds). Removals: X1 (J7-J10, 4 placements, about $68 at 5 boards and $5,460 at 500 on the survey's own estimates), X2, X3, X4 are not in the totals.

Worst-case honest summary: **1 line and about $3 with no real risk, plus about $36 more per order if the six "med" checks pass.** The high-risk ideas are design studies and need the scorecard.

## 1. Extended to Basic (rows A1-A14)

Low risk:
- **A1 C8/C10/C15/C17 (C49678).** The BOM text says Extended; JLC's live record says Basic (22 M in stock). The fee is not actually charged, so the saving is a scorecard label only. Fix the class source in `scripts/apply_lcsc.py`.
- **A2 R59/R63/R65 2.2 k to 2 k 1206 (C17944).** Reference bias resistor of each rail monitor's TL431AI. Current 10 % higher, 128 mW of 250 mW, reference moves under 1 mV. The monitor thresholds are ratios of this reference, so it is protection-adjacent: rerun the `audit.rs` reference-current corner and the D33 rail qualification.

Medium (checks named in the CSV):
- **A3 R3/R4 220 k to 100 k (C17900, merges with R1/R2).** Faster bleed (1.25 s vs 2.47 s to 60 V), 98 mW per part. Safety-relevant, but the change moves the discharge in the safe direction. Check local derating beside D3/C5.
- **A4 nine 1 uF 25 V X7R 0603 to CL10A105KB8NNNC (C15849).** 50 V rating keeps more capacitance at 17 V; X5R has an 85 C limit. DC-bias curve not read (unverified).
- **A5 C11/C18 10 uF 25 V X7R to GRM21BR61H106KE43L (C440198, 10 uF 50 V X5R 0805).** Same caveat.
- **A6 R51/R52/R55/R56 0.68 to 1.0 ohm (C17928, merges with Gate1R).** Reservoir damping; the 0.68 value came from Yageo's catalogue, not a derivation. Rerun the D33 loop/periodic/hot-load campaigns.
- **A7 R67-R70 16.5 k to 10 k 1206 (C17902).** The line zero-cross string; LED current 2.6 to 4.2 mA, ZC phase error smaller. Needs the opto datasheet and lab sign-off (mains-connected).
- **A11 U22/U23 OR gate to the 3-input OR (C43368).** Saves a line but changes SOT-23-5 to -6, a copper change.

High (flagged, not recommended without evidence): A8 (1 nF C0G to X7R: only pays if the four gate-source caps also change), A9 (R40/R41 CT bias is a protection threshold; the prior band figures are stale), A10 (BAS116H low-leakage clamps to 1N4148W), A12 (gate-off Schottky D6-D9 to B5819W, re-spin), A13 (LM4040 to TL431 reference: threshold accuracy), A14 (NAND3 to OR3 with comparator polarity swapped, re-spin).

**Rejected with numbers.**
- **R9/R17 dead-time resistor 49.9 k 0.1 % to 51 k 1 % Basic (C23196).** Using the audit's own `dead_time_window_ns` (tolerance and TCR over 125 K), 51 k at 1 %/100 ppm gives 398-507 ns against the simulated window 391-498 ns, so it fails at the upper edge. 47 k fails the lower edge (368 ns). There is no Basic value that fits.
- **R22-R29 470 k 1206.** No Basic 470 k in 1206; 1 M would need the bus-sense bottom (0.1 % 33.3 k, Extended) and slows the C_res bleed to about 2 s tau.
- **R10/R12/R18/R20 gate 3.9 ohm.** No Basic 3.9 ohm in 1206; changing the value changes switching energy and dv/dt (high risk, no study proposed).
- **1210 10 uF/50 V (24 placements, C386167).** No Basic 1210 part; 0805/50 V X5R (C440198) would be a layout change.
- **Compared and kept: TL431AI, TLVH431, LM4040, LM339BIDR, TLV3201, SN74LVC1G17/G10/G332, TPS3700, BAS116H.** No Basic equivalent; LM393 (C7955, dual, 0-70 C) is not an LM339B equivalent and the rail monitor uses all four comparators of the quad.

## 2. Value consolidation

No near-identical values remain that tolerate merging, except the three done in the table (R3/R4 onto 100 k, rdamp onto 1 ohm, R40/R41 onto 1 k if the owner accepts it). Observations:
- 28 x 10 k 0.1 % (C95204) and 13 x 10 k 1 % (C25804): most of the 28 are the bottoms of the monitor, OCP, OVP and CT ratio dividers. Only `r_hot5_uv_pull` is a plain pull-up; moving it to 1 % saves a few cents, not a line.
- 4.42 k, 7.68 k, 120 k, 133 k, 6.2 k, 11 k, 63.4 k, 2.21 k, 12.6 k, 11.7 k, 105 k, 140 k, 15.8 k: each is a threshold or feedback value with a recorded margin (the rail OV margin is 0.071 V). No merge without re-deriving thresholds. Not touched.

## 3. Candidates for removal (none is claimed in the totals)

| Part | What it does | Cost of removing it | Evidence needed |
| --- | --- | --- | --- |
| R3/R4 bleed (X3) | DC-bus discharge and midpoint of the two series 30KPA150CA | Discharge to 60 V goes to about 20 s through the divider only; TVS voltage sharing loses its equaliser. | Discharge analysis against the touch-voltage requirement, TVS leakage-sharing model; **certifier sign-off required (safety)**. A3 is the safer alternative. |
| R1/R2 X-cap discharge (X2) | C1/C2 to < 34 V in <= 1 s | Line-ZC string (4 x 16.5 k + opto LED) gives tau about 0.13 s, but it makes a signal circuit the discharge element. | **Certifier sign-off required (safety).** Only a Basic line, so no fee saving. |
| J7-J10 bring-up studs (X1) | Floating-DC bring-up links | None for production; 4 placements and 4 of the 6 REDCUBE parts (JLC stock 0). | Production re-spin after the prototype lot; copper change. About $68 at 5 boards, $5,460 at 500 (survey prices). |
| 3-input OR merge U22/U23 (A11) | Per-driver DIS OR | Package change SOT-23-5 to -6. | Re-spin. |
| C24 10 uF (X4) | Parallel with C99/C100 on the TPS7A4700 | Placement only. | LDO stability and layout check. |
| TLV3201 pairs to TLV3202 duals (BOM-REVIEW item 5) | OCP/OVP and CT comparators | Not re-examined here; no Basic route; layout touch. | Low value, as the BOM review said. |
| Gate-off diodes D6-D9, snubbers C12/C13/C19/C20, TVS D3/D17 | Turn-off path, dv/dt snubbing, bus clamp | Performance and protection; no simulation bounds their absence. | Not proposed. |

## 4. Hand, consigned and THT parts

JLC's THT line items already cover J1, RV1, L1, C3/C4, BR1, Q2-Q6, J2/J5/J7-J10, PS1/PS2, J4, J6, C38-C41. The 11 non-JLC lines:
- **J3/J11 JST VH (H1): `C160745` exists, 13,983 in stock.** The BOM's "not on LCSC" is wrong. Moves hand assembly to JLC for one extended fee.
- **C1/C2 KEMET R463 (H2): `C3299886`, 46 in stock.** Enough for 5-board lots only; leads need a trim step.
- **U1/U2 UCC21550 (H3): -Q1 variant `C42216738`, 10 in stock.** Unverified certificate and pinout (prior N3).
- **No JLC alternative found:** F1 KLDR025.TXP (C187688, stock 0), F1 clip 01250003H (C223911, stock 1), F2 3403.0171 (C19190930, stock 0; Littelfuse 0452003 is a 125 V 3 A fast part, not an equal), C5/C6 B32676G1905K000 (C3802167, stock 0), C21-C23/C151/C152 B32654A1104K000 (C3811101, stock 0), D3/D17 30KPA150CA (C19111562, stock 0), T1 CST3015-100ED (only the -200ED, 1:200, which is not equivalent), U41/U42 R24C2T25 (zero stock).
- The existing BOM could also carry LCSC codes for C5/C6, C21-C23, D3/D17, F1 (they exist but have zero stock) so the quote tool lists them.

## Flags and unverified items

- DC-bias retention for A4/A5 and X5R's 85 C limit are not checked against datasheet curves.
- A2, A3, A6, A7 need small rechecks (named above) and `audit.rs` IDENTITY edits; A3 is also a safety-adjacent component.
- A9, A10, A13, A8 touch protection thresholds or gate-drive behaviour and are not recommended without a recomputed band or sim.
- JLC stock figures are for 2026-10-13 and move daily (AMC1311 stock moved 663 to 6,318 in five days); H2/H3 are limited by stock.
- Per-unit part-price deltas were not used: commodity prices in the sourcing survey are class defaults. Only extended-fee savings ($3 per line per order) are counted, assuming one order at 5 and one at 500 boards.
- JLC's basic-parts page is JavaScript-rendered, so Basic status comes from the API record at read time.
