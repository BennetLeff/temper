# F5 decision record: touch-current limit, measurement basis and design budget

Date 2026-10-13. Desk study, nothing built or sent. Numbers: `f5_leakage_basis.py` (`python3 -I`, writes `f5_result.json`). It is a copy of the model in `07-conducted-emi/leakage/leakage_budget.py` (not edited, not imported) with variant and basis switches. Controls reproduce the repo's 0.974 (benchmark), 0.693 (G01 P1), 0.831 (G06 P1), 0.688 (G06 P1 + P3) and 0.575 (typical supplies) mA at 132 V; exit 1 if they fail.
`[UNVERIFIED]` = not read from a primary document.

## Recommendation

1. **Limit:** design to **0.5 mA** (UL "portable" class, open-PE, both polarities). Treat 0.75 mA as the upside if the lab classes the cooker as stationary or if the NOM/IEC route applies. A countertop cooker you can pick up is the portable case.
2. **Basis:** a two-test design rule, because the datasheet maximum is a guaranteed bound but the lab measures the unit:
   - **Test A (release gate on paper):** touch current ≤ **0.5 mA** at 132 V with every Y capacitor at +20 % and every IRM supply at its **datasheet maximum**.
   - **Test B (accepted if A fails):** ≤ **0.40 mA (80 %)** with supplies at **5 × the measured typical** (about 0.05 mA each at 132 V / 60 Hz) and a first-article measurement that confirms it.
3. **Option:** adopt **G01 P1 (module Y 6.9 → 2.2 nF) + G06 P1 (delete PS1)**, and claim **G06 P3 (PS2 is not in the PE path)** only as a measurement to be proved. Result: 0.408 mA with all three (82 % of 0.5 mA; passes Test A, 54 % of 0.75 mA). Without P3 it is 0.551 mA at datasheet max (110 %, fails Test A) and 0.364 mA at 5 × typical (73 %, passes Test B).
4. **Do not** leave the benchmark as is (0.974 mA = 195 % of 0.5 mA on the max basis, 139 % even at 5 × typical) and do not count on G01 P1 or G06 P1 alone.

Facts this rests on:
1. UL's own column gives 0.5 mA (portable) and 0.75 mA (stationary) three-wire cord-connected, with the plug on "an open ground" and both polarities (IAEI, Feb 2019). Not tied to a UL 1026 clause in the source.
2. MEAN WELL's IRM-20 and IRM-60 specs give only "< 0.25 mA / 277 Vac"; the one public test report found (IRM-20-15) measured 0.015 mA at 240 Vac, 6 % of the limit, one unit. The datasheet maximum is a limit, not a typical.
3. Module leakage must be assessed on the end product, not summed from datasheets (supporting manufacturer notes, not a certifier rule).
4. The sum is dominated by Y capacitors: board 2.2 nF + module 6.9 nF = 0.543 mA at +20 %, before any supply.
5. P3's physics: PS2's output is HOT-referenced, so its Y current returns through the rectifier to N and reaches PE only through tens-of-pF parasitics (~5 µA at 100 pF, 132 V); this is an argument, not yet a measurement.

## 1. Which limit applies

| Item | Finding | Source |
| --- | --- | --- |
| UL appliance limits | "cannot exceed 0.5 mA for portable two-wire and three-wire cord and plug-connected appliances", "0.75 mA for three-wire … fixed or stationary appliances"; metal-sheathed heating elements up to 2.5 mA for five minutes during heat-up and cool-down. The text names no standard or clause. | IAEI, "UL Question Corner: Leakage current", Feb 2019 (read): https://iaeimagazine.org/columns/ul-question-corner/ul-question-corner-leakage-current/ |
| Test method | Plug connected "with an open ground", correct and reverse polarity; measured between accessible parts and ground; foil on non-metallic enclosures. Test voltage and meter network are **not** given there. | same |
| Second source | AAFES test method H-13: 0.5 mA ungrounded or grounded-portable, 0.75 mA grounded stationary/fixed; step "detach chassis grounding conductor at attachment plug"; supply "120 or 240 volts, depending on appliance rating"; Simpson 229-2 meter; portable and stationary are **not defined**. Not a UL document. | https://www.aafes.com/qualityassurance/TM_H-13.htm (read) |
| Is the cooker "portable"? | No definition found. UL 1026 (and UL 858 if it applies) clause numbers for leakage, the heating-element exception, and whether a countertop cooker is hand-carried: not found, paywalled. Treat as portable (0.5 mA). | [UNVERIFIED] |
| Test voltage | UL: not found. IEC 60335-1: I believe 1.06 × rated voltage for leakage at operating temperature (cl. 13.2) and 1.15 × rated power for heating appliances; searches did not return the clause text. For a 120–127 V range the upper limit would apply: 127 × 1.06 = 134.6 V. The model also runs 127 V and 134.6 V (below). | [UNVERIFIED] |
| IEC 60335-1 limits | Table summaries: Class I **portable 0.75 mA**, stationary motor-operated 3.5 mA. For stationary Class I heating appliances an older VDE 0700-1 summary gives "0.75 mA or 0.75 mA/kW, max 5 mA" (≈ 1.28 mA at 1.71 kW); IEC Table 4 text not read. | Comparison summaries (Bel Fuse and Cosel pages, search results): https://www.belfuse.com/resource-library/blog/iec-60335-1-explained-safety-standards-for-household-appliances ; clause text [UNVERIFIED] |
| NOM relevance | NOM-003-SCFI-2014 → NMX-J-521/1-ANCE-2012 (general) and NMX-J-521-2-6-ANCE-2017 (cooking, modified IEC 60335-2-6). Profeco tested 127 V~ portable induction hobs to those. The IEC 0.75 mA portable Class I number is therefore the relevant Mexican reference. The NMX leakage clause text and any national deviation were not found. | Profeco June 2023 (read): https://www.gob.mx/cms/uploads/attachment/file/830636/ESTUDIO_CALIDAD_PARRILLAS_ELECTRICAS_DE_INDUCCION.pdf |
| Measuring network | UL's meter network is not in the sources; the IEC 60990 weighting suppresses HF, which would help the 35–60 kHz coil-to-PE term. Unconfirmed; treat as an advantage only after the lab says so. | [UNVERIFIED] |

Reading of the three limit cases: 0.5 mA binds for UL portable. For NOM/IEC the portable Class I value is 0.75 mA, which is looser than the UL number, so a design that meets 0.5 mA meets both.

## 2. How certifiers treat module leakage

- **Measured on the product.** The UL test is a measurement of accessible parts to earth on the finished appliance (IAEI). No certifier text saying "datasheet maxima are not summed" was found, but the following manufacturer notes say the same in practice:
  - Beckhoff on a DIN-rail supply: the module's leakage "depends on the input voltage ripple and must be investigated in the final application" (https://infosys.beckhoff.com/content/1033/ps9421-4840-0000/9955760011.html).
  - TDK-Lambda: leakage contributions are additive and limits are shared between supplies (https://www.us.lambda.tdk.com/resources/blogs/201008.html; medical context, so a principle, not the rule here).
- **MEAN WELL numbers** (both datasheets read, PDF p.2 spec table, row LEAKAGE CURRENT): IRM-20 "< 0.25mA/277Vac" (2025/2024 spec); IRM-60 "< 0.25mA/277Vac" in the file I read, but other copies of the IRM-60 and IRM-30 sheets say 240 Vac. The datasheets give no test frequency.
- **Measured typical:** Simpex test report for IRM-20-15 (read): "L-FG 0.015 mA, N-FG 0.015 mA" at 240 Vac, min load, 25 °C, one unit (https://simpex.ch/wp-content/uploads/2021/07/IRM-20-15-rpt.pdf). Scaled to 277 V it is 6.9 % of the maximum, a 14 × gap. **No measurement exists in public sources for IRM-60, IRM-20-24, or any unit spread.** A test report line "L-FG" on a Class II module with no FG pin is also unexplained (what "FG" is in that setup) [UNVERIFIED].

## 3. Budget basis and results

Model: open-PE touch current per polarity = ω·C·V for the hot line's Y capacitance (board Y + module Y at +20 %, plus 31 pF coil at +20 %) plus supply terms. Supply term at the datasheet maximum is 0.25 mA × (V/277) × 1.2 (60/50 Hz) = 0.143 mA each at 132 V. The measured-typical term is k × 0.015 mA × (V/240) × 1.2 = 0.0099 mA × k at 132 V. Variants follow `g01-mains` P1 and `g06-g08-g10` P1/P3.

**132 V, +20 % Y. Touch current mA (percent of 0.5 mA / of 0.75 mA):**

| Variant | datasheet max | typical × 3 | typical × 5 | typical × 10 |
| --- | --- | --- | --- | --- |
| Benchmark 19c (Y 9.1 nF, 3 supplies) | 0.974 (195 / 130) | 0.634 (127 / 85) | 0.694 (139 / 93) | 0.842 (168 / 112) |
| G01 P1 (Y 4.4 nF) | 0.693 (139 / 92) | 0.354 (71 / 47) | 0.413 (83 / 55) | 0.562 (112 / 75) |
| G06 P1 (delete PS1) | 0.831 (166 / 111) | 0.605 (121 / 81) | 0.644 (129 / 86) | 0.743 (149 / 99) |
| G06 P1 + P3 | 0.688 (138 / 92) | 0.575 (115 / 77) | 0.595 (119 / 79) | 0.644 (129 / 86) |
| G01 P1 + G06 P1 | 0.551 (110 / 73) | 0.324 (65 / 43) | 0.364 (73 / 48) | 0.463 (93 / 62) |
| **G01 P1 + G06 P1 + P3** | **0.408 (82 / 54)** | 0.294 (59 / 39) | 0.314 (63 / 42) | 0.364 (73 / 48) |

Voltage sensitivity of the recommended combination (datasheet max): 127 V 0.392 mA, 132 V 0.408, 134.6 V 0.416 (the IEC-style 1.06 × 127). The conclusion does not change across them. Full grid, including 127 V and 134.6 V for every variant, is in `f5_result.json`.

Allowed total Y per line (nominal, with the coil term, 132 V): 1.16 nF with three supplies at datasheet max for 0.5 mA, 5.95 nF with one supply; with three supplies at 5 × typical, 5.86 nF at 100 % and 4.18 nF at 80 % of 0.5 mA. At the 0.75 mA limit and 80 %, three max-supplies allow 2.83 nF.

Reading the grid:
- The benchmark fails every basis that includes the Y at +20 %, except typical × 1 (0.575, still 115 %). The 0.5 mA failure is real, not an artefact of the max-basis.
- G01 P1 alone passes only on a measured-typical basis (up to × 5) and fails at the datasheet max (139 %).
- G06 P1 alone does not pass anything at 0.5 mA, since PS1's 0.143 mA is a small part of the Y-dominated sum. Its value is the removal of a courtyard and a certifier question, not leakage.
- The module Y cut (G01 P1) is the main lever (−0.28 mA). It costs EMI margin per the G01 study (Y 4.4 nF keeps 12 dB nominal / 7.5 dB sensitivity in the model); that trade is G01's.
- P3 is worth −0.143 mA at the datasheet max but is only a claim until PS2 is powered on a bench touch-current test.

Why not "datasheet max only": it is a guaranteed bound on production units, so it is the rigorous worst case, but it multiplies a limit by three supplies and adds +20 % on every Y at once. Why not "typical only": one unit of one model is not a distribution. The two-test rule (A or B) uses each only where it is defensible. A factor of 5 on typical keeps each supply at about a third of its guaranteed maximum and is an engineering margin, not a statistic [UNVERIFIED]; it should be re-derived from ≥ 3 measured units of each of IRM-20-15, IRM-20-24 and IRM-60-15ST.

## 4. First-article confirmations (lab and bench)

1. Standard and clause for leakage (UL 1026 vs UL 858; CSA C22.2 No. 64; NMX-J-521/1 and /2-6), edition, and whether a countertop induction cooker is "portable" (0.5 mA) or "stationary" (0.75 mA).
2. Test voltage (rated, 1.06 or 1.1 × rated, or 127 V upper limit of the range), measuring network, and whether HF coil-to-PE current is weighted or included.
3. Open-PE, both polarities, on the first article with each configuration: benchmark, G01 P1 Y, with and without PS1, PS2 powered. Record each supply's contribution by removing it (PS1 delete is a direct measurement; PS2 is the P3 test).
4. Whether the 2.5 mA / 5 min heating-element exception is open to an induction cooker (it is stated for metal-sheathed elements only); do not plan on it.
5. Y-capacitor tolerance and the actual capacitance of the built board (X/Y ±20 % assumed everywhere).
6. PE-intact conductor current (1.95 mA benchmark, 0.8 mA with the recommended set at max basis ×2) for GFCI nuisance trips, which is not a pass criterion in the sources found.

## 5. What I could not verify

- Any UL 1026, UL 858, UL 60335-1, CSA C22.2 No. 64 or NMX-J-521 clause text (leakage limits, test voltage, network, portable/stationary definition).
- That IEC 60335-1 uses 1.06 × / 1.15 × for leakage, and the stationary heating formula.
- Any certifier statement on datasheet-vs-measured leakage for built-in supplies.
- IRM-60 or IRM-20-24 measured leakage; unit-to-unit spread; what "FG" means for Class II modules in the Simpex report.
- Capacitive coupling of the HOT domain to PE (the P3 premise): estimated, not measured.

## Sources

- IAEI UL Question Corner (Feb 2019): https://iaeimagazine.org/columns/ul-question-corner/ul-question-corner-leakage-current/
- AAFES H-13: https://www.aafes.com/qualityassurance/TM_H-13.htm
- MEAN WELL IRM-20-SPEC and IRM-60-SPEC: https://www.meanwell.com/Upload/PDF/IRM-20/IRM-20-SPEC.PDF , https://www.meanwell.com/Upload/PDF/IRM-60/IRM-60-SPEC.PDF
- Simpex IRM-20-15 test report: https://simpex.ch/wp-content/uploads/2021/07/IRM-20-15-rpt.pdf
- Profeco induction hob study (NMX-J-521 references): https://www.gob.mx/cms/uploads/attachment/file/830636/ESTUDIO_CALIDAD_PARRILLAS_ELECTRICAS_DE_INDUCCION.pdf
- Repo: `07-conducted-emi/leakage/README.md` and `leakage_budget.py`; `11-candidates/g01-mains/PROPOSALS.md` P1; `11-candidates/g06-g08-g10-supplies-sense-io/PROPOSALS.md` P1, P3.
