# F1 decision record: mains fuse for a 120–127 V~ cord-connected induction board

Date 2026-10-13. Desk study, no hardware, nothing ordered or sent. Numbers: `f1_fuse_options.py` (`python3 -I`, writes `f1_result.json`; exits 1 if its controls fail; controls reproduce the repo's 0.208 copper ratio, the 16.9 A carrying figure, the BR1 FAIL and the MDA-25-R FAIL).
`[UNVERIFIED]` = not read from a primary document. "Read" = I opened the PDF text myself.

## Recommendation

**Keep F1 = Littelfuse KLDR025.TXP (UL Class CC, 25 A time-delay, 600 Vac / 200 kA).** Do not switch to the 6.3 × 32 fast-acting Littelfuse 0505025.MXP now. It is the cheapest candidate that can be permissible (≈ $26–29 per board), but it is permissible only if the certification lab accepts a Recognized supplemental fuse and a short-circuit test, and its key datum (clearing I²t) is not published in anything I could read. Revisit only through the gate in section 5.

Five facts this rests on:

1. **No source I could read says an internal fuse in a cord-connected appliance must be a Listed branch-circuit (Class CC) fuse.** UL's Code Authority newsletter (2008) says supplemental fuses "may be Listed or Component Recognized", investigated "for factory installation in Listed products". Class CC is therefore sufficient, not demonstrably required. (Section 1.)
2. **The end-product short-circuit clause for UL 1026 / UL 858 / CSA C22.2 No. 64 / NMX-J-521 could not be read** (paywalled), so the available-current basis for testing F1 is unknown to me. A 200 kA-rated Listed fuse is the only option that makes that test uninteresting, with 23.8 × margin over the 8.4 kA bound.
3. **The 0505025's only primary-ish data is a mirror of the 2023 505 datasheet**: "500 VAC/500 VDC … 20,000 A" (2.4 × the 8.4 kA bound), approvals "UL/CSA/NMX 248-1 and 248-14", file E10480. Its melting I²t is 145 A²s on Littelfuse's product page but 210 A²s in the mirrored table, and no clearing I²t exists. Both are [UNVERIFIED] (Littelfuse blocks automated reads).
4. **Even the best case for the 505 does not fix F2.** With clearing = 1.5–3 × melting (assumption), the copper ratio goes from 0.208 to 0.56–1.63, but the two 355 A²s necks (HV_RET isthmus, R5 to J10) still fail the 2 × target in every scenario, and BR1's half-I²t rule (clearing < 255 A²s) holds only in the single most optimistic case. The F2 fix remains a DC fuse in the normal build (`02-protection-timing/shoot-through-f1/README.md`).
5. **KLDR025's published let-through helps F4/F2 coordination**: about 540–630 A apparent RMS at 4.7–8.4 kA (interpolated, KLDR p.6), 2.4 × under F2's 1.5 kA rating. No let-through data was found for the 505.

## 1. What the standards require of an internal overcurrent device

| Question | What I could establish | Source |
| --- | --- | --- |
| Must it be a branch-circuit fuse? | No requirement found. By NEC definition, supplementary protection is "in addition to" the branch-circuit device and "cannot be used as a substitute" for it. The building breaker is the branch device; F1 is internal. | UL Code Authority, "Supplementary Protection or Branch Circuit Overcurrent Device", Issue 1 2008, pp.1–2 (read): https://code-authorities.ul.com/wp-content/uploads/2014/04/ul_OvercurrentProtectionSupplementary.pdf |
| Listed vs Recognized | "Supplemental fuses may be Listed or Component Recognized by UL"; Recognized parts are "investigated for factory installation in Listed products where UL has investigated the suitability of the combination". | same, p.1 |
| Short-circuit test, device level | Listed branch fuses "must open the circuit without damage"; branch devices are "rated for at least 5,000 amperes". Recognized supplementary protectors "typically have only been tested at 5,000 amperes or less" and are "generally short circuit tested with upstream branch circuit protection". This describes protectors; it is the closest public statement for fuses too. | same, pp.1–2 |
| Short-circuit test, end product (UL 1026 / 858 / 60335-1 US text, CSA C22.2 No. 64, NMX-J-521) | **Not found.** The "1 kA / 5 kA / 10 kA" levels in the brief are from memory of other UL standards, not from a document I read. | none. Searches returned scope pages only |
| Which end-product standard | UL 1026 covers household cooking appliances ≤ 250 V but "does not cover household electric ranges" or "appliances … covered in individual requirements". UL 858 covers cooking equipment that is "counter mounted" (units "intended for mounting in or on a counter"). A cord-and-plug countertop unit is more naturally UL 1026, but no source names hot plates or induction cookers. The True Induction built-in/portable units are marketed as UL 858. Product format decides; [UNVERIFIED]. | Search-result quotations of UL scopes (UL 1026 §1.2, UL 858 §1.1): https://standardscatalog.ul.com/standards/en/standard_1026 (not fetched); marketing: https://www.lowes.com/pd/-/1002936836 |
| NOM side | NOM-003-SCFI-2014 points to NMX-J-521/1-ANCE-2012 (general) and, for cooking, NMX-J-521-2-6-ANCE-2017 (modified IEC 60335-2-6, "aparatos estacionarios de cocimiento"). Profeco's 2023 study tested portable induction hobs rated up to 127 V~ against exactly those two. | Profeco, Revista del Consumidor, June 2023 (read): https://www.gob.mx/cms/uploads/attachment/file/830636/ESTUDIO_CALIDAD_PARRILLAS_ELECTRICAS_DE_INDUCCION.pdf ; NMX-J-521-2-6 catalogue page https://platiica.economia.gob.mx/normalizacion/?p=45792 |
| Fuse-standard side | UL 248-1 is the tri-national text (NMX-J-009/248/1-ANCE, CSA C22.2 No. 248.1); interrupting tests use recovery voltage "rated voltage + 5 percent, - 0 percent"; preferred AC voltage ratings 125, 250, 300, 480, 600 V. A 125 V rating says nothing about a 127–132 V circuit. | UL 248-1 2nd ed. 2000, cl. 5.2, Table 5 (read earlier; `F1-CERTIFIER.md`) |

Consequence: the real gate is the lab's short-circuit test of the finished product with F1 in circuit, at the product's rated voltage (127 V) and the available current they choose. That is why the choice reduces to "does F1 clearly cover 8.4 kA at 127–140 V on its own rating?"

## 2. Candidates

All with F1 in 25 A, 15 A continuous, prospective 4.7–8.4 kA at 139.7 V.

| Part | Class / size | AC rating, AIR | Agency | Melt / clearing I²t (A²s) | 15 A at 50 °C | Price | Source and status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **Littelfuse KLDR025.TXP** (plan) | Class CC, TD, 10.3 × 38 | 600 V, **200 kA** (23.8 ×) | UL Listed E81895, CSA LR29862; **no NMX mark printed** | 226 / **1,710** | 25 × 0.75 × 0.90 = 16.9 A | DK $29.41 @500 (repo); web $22.55 (North Coast, 10-pack), $26.54 (Steiner); Platt $65 (0 stock) | Read: Rev 092821 pp.1,2,5,6 (https://static.chipdip.ru/lib/254/DOC027254593.pdf). Distributor prices are web prices, not quotes |
| Littelfuse KLKR025.T | Class CC, fast | 600 V, 200 kA | UL E81895, CSA LR29862 | **25 A row not published** (20 A = 900, 30 A = 1,720 total clearing at 200 kA; interp. ≈ 1,244) | derating curve not read; 20 A part carries only 13.5 A, so 25 A is the size | not found | Read: KLKR Rev 062218 (https://static.chipdip.ru/lib/545/DOC011545067.pdf). Saves ≤ 27 % of I²t; not worth a certifier trip (repo G01 P2 agrees) |
| Eaton Bussmann LP-CC-25 / FNQ-R-25 (TD), KTK-R-25 (fast) | Class CC | 600 V, 200 kA | UL Listed 248-4 (LP-CC: E4273, CSA 53787 per repo) | not on any sheet I could open [UNVERIFIED] | [UNVERIFIED] | US web: KTK-R-25 $41–53, FNQ-R-25 $48–53 | Distributor pages only (e.g. https://www.crescentelectric.com/product/46264/…). More expensive than KLDR; LP-CC let-through 870 A at 10 kA is from repo's read of Eaton DS 1023 |
| Mersen ATDR25 (TD) / ATMR25 (fast) | Class CC | 600 V, 200 kA | UL 248-4 / CSA 248.4 (distributor text) | no I²t found | [UNVERIFIED] | web $5.95–13.59 (surplus/ unclear), $58 (Sydist ATMR25) | Distributor listings only (https://www.gerrie.com/Product/Mersen-ATDR25). Unreliable prices; get a real quote before counting on it |
| **Littelfuse 0505025.MXP** | Supplemental, fast, 6.3 × 32 (3AB) | **500 V, 20 kA** (2.4 ×); one listing says 30 kA for the 30 A part | "UL/CSA/NMX 248-1 and 248-14", E10480, row mapping unclear | melt **145** (product page) or **210** (datasheet mirror); clearing **unpublished** | derating not read; needs ≤ 20 % loss at 50 °C for 0.75 rule, ≤ 40 % with no margin | ≈ $3 (est; Newark MXEP sibling $2.85 @1000 per repo; eBay 5-pack $25) | Mirror of rev 10/16/23: https://pdf.jiepei.com/0505010.-45698391.html ; Littelfuse page returned 403 |
| Eaton MDA-25-R (previous) | Supplemental TD, 6.3 × 32 | 125/250 V; 10 kA only @125 V, **1.5 kA @250 V** | cULus Recognized E19180 | 734.7 melt | n/a | n/a | Repo `F1-CERTIFIER.md`; fails 4.7 kA floor at ≥ 127 V |
| Littelfuse 314/324/326, Eaton ABC/MDA, Schurter/Bel 6.3 × 32 and 10 × 38 supplemental | 6.3 × 32 / 10 × 38 | typically 1.5 kA @250 V (6.3 × 32 families) | | | | | Checked only through the repo's earlier search (F1-RECOMMENDATION §3.1): none found at 25 A with ≥ 5 kA above 125 V except the 505 and 10 × 38 midget FNM/FNQ/FLQ (10 kA @ 250/500 V, 1.2 × margin, [UNVERIFIED]). I did not find a Schurter or Bel 25 A, ≥ 250 V, ≥ 8.4 kA part in this pass |

Not found anywhere: a time-delay 6.3 × 32, 25 A, ≥ 5 kA at 250 V fuse.

## 3. Decision rule and result

A candidate is **permissible** if all hold:

- **R1** one AC rating ≥ 140 V with AIR ≥ 8.4 kA at that rating (no split 125 V / 250 V rating).
- **R2** carries 15 A continuous at 50 °C after the maker's derating (and 0.75 continuous margin if the lab applies it).
- **R3** agency status the lab will accept for an internal fuse: Listed (248-4/248-14) accepted outright, Recognized only on the lab's say-so.
- **R4** no pulse failure (inrush 0.4–0.7 %, 1 kA surge 5–8 % of melt I²t, repo F1-RECOMMENDATION §3.4).

| Option | R1 | R2 | R3 | Permissible without lab judgment? |
| --- | --- | --- | --- | --- |
| KLDR025 | yes (23.8 ×) | yes (16.9 A) | Listed | **yes** |
| KLKR025 / LP-CC / FNQ-R / KTK-R / Mersen | yes | KLKR/others [UNVERIFIED] | Listed | yes, but dearer or without I²t data |
| 0505025 | yes (2.4 ×; mapping of the 25 A rating unclear) | [UNVERIFIED] | Recognized | **no**: needs lab acceptance |
| MDA-25-R | **no** (1.5 kA @250 V) | | Recognized | no |

**Cheapest permissible: KLDR025 unless the lab accepts a Recognized fuse, then 0505025.** Cheaper sourcing of the Class CC itself is a small lever: web prices of $22.55–26.54 against DK's $29.41 at 500 would save $3–7 per board; request quotes (Mouser, Newark, Arrow, Littelfuse distributors) before counting it.

### Effect on fuse_copper_fusing_ratio (copper target = 2 × clearing; narrowest neck 355 A²s)

| F1 | clearing | ratio | 2× target | BR1 half-rule (< 255) | necks still failing the target |
| --- | --- | --- | --- | --- | --- |
| KLDR025 | 1,710 | 0.208 | 3,420 | fails | all five |
| KLKR025 (interp.) | ≈ 1,244 | 0.285 | ≈ 2,490 | fails | all five |
| 0505025, melt 145 × 1.5 / 2 / 3 | 218 / 290 / 435 | 1.63 / 1.22 / 0.82 | 435 / 580 / 870 | passes only at ×1.5 | HV_RET isthmus, R5 to J10 |
| 0505025, melt 210 × 1.5 / 2 / 3 | 315 / 420 / 630 | 1.13 / 0.85 / 0.56 | 630 / 840 / 1,260 | fails | same two (three at ×3) |

The ×1.5/2/3 multipliers are assumptions. The 505 improves the ratio 2.7–7.8 × on paper but cannot reach pass on the copper necks or BR1 with confidence; the datasheet I²t values for Class CC are totals at 200 kA, so real clearing at 4.7–8.4 kA is probably lower for every candidate. A let-through test at 5 and 8 kA prospective on the chosen fuse would give the number the scorecard needs.

### F2/F4 coordination

- F1 melt over F2 pre-arc (11.6 A²s): KLDR025 19.5 ×, 505 12–18 ×. F2 opens first on faults in its own range with either.
- F4: with KLDR025, the published peak-let-through data gives ≈ 540 A (4.7 kA, clamped to the 5 kA row) to ≈ 630 A (8.4 kA) apparent RMS, against F2's 1.5 kA rating: 2.4 ×. This is a series-rating style argument the lab must accept; no equivalent data exists for the 505.
- Repo conclusion unchanged: the F2 HBC replacement and a DC fuse remain the real containment answers.

## 4. What the certification lab must still confirm (first article)

1. Which end-product standard (UL 1026 vs UL 858; CSA C22.2 No. 64; NMX-J-521/1 and /2-6) and the clause and available-current basis of the short-circuit test with F1 in circuit.
2. That a Listed Class CC fuse as an internal fuse is acceptable under CSA and NOM (the KLDR datasheet prints UL and CSA files only; whether ANCE/NYCE needs an NMX mark on the component or accepts the tri-national listing is [UNVERIFIED]).
3. The open clips (Littelfuse 01250003H, 250 V per product page [UNVERIFIED], file E14721 ambiguous): agency category, voltage rating, temperature rise of fuse plus clips at 15 A continuous, marking of the fuse rating near the holder.
4. Whether 15 A at a 127 V +10 % high-line corner is evaluated at 1.06 / 1.10 × rated voltage, and whether the derating curve (≈ 10 % at 50 °C, read off the plot) is accepted.
5. If the 505 is ever pursued: Recognized supplemental fuse acceptance (JDYX2-type conditions), the 25 A interrupting rating at 127–140 V, and a clearing I²t measured at 4.7 and 8.4 kA.

## 5. Gate for reopening the 505 option

Switch only if all are true: (a) the lab states in writing that a Recognized 248-14 fuse with a 500 V / 20 kA rating satisfies the short-circuit test for UL, CSA and NOM; (b) Littelfuse (or a bench test) supplies the 25 A rating's interrupting rating, clearing I²t at 5 and 8.4 kA and the 50 °C derating; (c) the F2 containment plan (DC fuse) is decided independently, so the switch is justified by cost and 3 of 5 necks, not by F2. Then the saving is about $26–29 per board less the clip difference (01220088Z pair unpriced), the footprint reverts to the 6.3 × 32 pattern, and C1 and the pours revert (reverses the 2026-10-09 ECO).

## 6. What I could not verify

- Any end-product clause text (UL 1026, UL 858, UL 60335-1, CSA C22.2 No. 64, NMX-J-521): paywalled. UL 1026 / UL 858 scope wording comes from search-result quotations.
- Littelfuse 505 datasheet from Littelfuse itself (403): mapping of 20/30/50 kA to ratings, 25 A AIR, clearing I²t, derating, price and stock; the 145 vs 210 A²s conflict.
- Eaton LP-CC, FNQ-R, KTK-R I²t tables, Mersen datasheets; any real quote at 5 or 500 pieces; DigiKey/Mouser live prices and stock for every part.
- NMX component-acceptance practice, and whether NMX-J-009/248/4 exists as the Class CC tri-national.
- KLDR derating at 50 °C from the plot (repo reading); KLKR derating.
- Browser automation was unavailable, so no manufacturer page that blocks scripted fetches was read.

## Sources

- UL Code Authority, Issue 1, 2008: https://code-authorities.ul.com/wp-content/uploads/2014/04/ul_OvercurrentProtectionSupplementary.pdf
- Littelfuse KLDR Rev 092821: https://static.chipdip.ru/lib/254/DOC027254593.pdf
- Littelfuse KLKR Rev 062218: https://static.chipdip.ru/lib/545/DOC011545067.pdf
- Littelfuse 505 (mirror, rev 10/16/23): https://pdf.jiepei.com/0505010.-45698391.html ; product page https://www.littelfuse.com/products/fuses-overcurrent-protection/fuses/cartridge-fuses/3ab-3ag-6-3x32mm-fuses-cartridge-fuses/505/0505025
- Profeco study: https://www.gob.mx/cms/uploads/attachment/file/830636/ESTUDIO_CALIDAD_PARRILLAS_ELECTRICAS_DE_INDUCCION.pdf
- Repo: `DECISIONS.md` 2026-10-08/09 F1 entries; `08-manufacturing-package/native-21/owner-items/f1cc/F1-RECOMMENDATION.md`; `.../sourcing/inquiries/F1-CERTIFIER.md`; `02-protection-timing/shoot-through-f1/README.md`; `11-candidates/g01-mains/PROPOSALS.md` P2.
