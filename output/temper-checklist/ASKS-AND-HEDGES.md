# External asks, public-source answers, and design hedges (2026-10-20)

Four parts: (1) what public sources already answer, (2) parts that need no approval, (3) design hedges so a "no" costs less, (4) the ledger of every external ask with a fallback. Nothing here is sent or ordered; sending is the owner's. Web results were read through search, not from a certifier or a purchased part, and are marked with a confidence.

## 1. Answers already available from public sources

| Question | What I found | Source | Confidence | Rows |
|---|---|---|---|---|
| Is UL 858 the standard for an induction cooktop? | UL 858 (Household Electric Ranges) has induction-specific clauses: 47.7 (operates only with the recommended vessel, with the small-metal-object test), 47.8 (automatic shutoff when a vessel is removed for more than 30 s, manual reset to re-energise), 59.6 (iron bar 100 × 20 × 2 mm, temperature rise ≤ 35 °C), 25.3.1 (solid-state controls per UL 858A, with an exception if the appliance stays safe with the control totally or partially inoperable). Retailers list portable induction units as "UL 858 certified". This supports UL 858 as the working assumption; whether UL 1026 applies to a portable unit is not answered by these sources | Intertek Standards Update Notices ([2017/2020 revision](https://cdn.intertek.com/www-intertek-com/dms-legacy/UL-858-Rev-2-8-2017-and-11-1-2017-ED-9-1-2020.pdf)); retailer pages are marketing claims | Medium: a lab's summary of changes, not the standard text | CMP-01, CMP-12, TST-10 |
| **New: a cooking-oil ignition test for induction units took effect on 2 August 2026** | Clause 60A applies to each surface unit rated 350 W or more (exception: non-circular induction units). Induction units run 15 minutes; a cast iron reference pan sits at the centre; the active area is the maximum dimension across the coil. 60A.8.4 covers closed-loop cooking: a temperature-limiting device integral to the appliance is evaluated with the specified cast iron pan. Intertek says reports not updated by that date are withdrawn. The clauses describing the test itself (60A.3) are not in the notice | Intertek Standards Update Notice, issued 2024-05-22, for [UL 858 Ed.16 + R:02Aug2023](https://w3inte.intertek.co.th/siteassets/resources/sun/2024/ul-858-sun-rev-8-2-2023-ed-8-2-2026.pdf) | Medium. **The repo has no mention of this test** (searched `zapote`, `docs`, `output` for "oil ignition" and "AHAM ER-2": no matches) | add a row; relates to FW-16, the fry hold and the 308 °C runaway trip |
| Is the manual-reset rule (47.8) compatible with the firmware? | The state table has `NO_PAN` → `PREHEAT` on `PAN_REPLACED_SAME` and → `COOLDOWN` on timeout or a different pan. 47.8 allows 30 s before shutoff but requires a manual reset to re-energise once that has passed. The repo's no-pan window is 2.0 s (FW-16), well inside 30 s. Whether a replaced pan within 30 s may restart without a button is not stated in the notice | `firmware/transition_table.yaml:68-76`; CHECKLIST FW-16 | Medium | FW-16, TST-10 |
| Are the Mean Well MPM-20 / MPM-65 modules UL-approved, and under which standard? | The MPM-20 family datasheet lists "IEC60601-1, EN60601-1, EAC TP TC 004, UL ANSI/AAMI ES60601, CAN/CSA-C22 3rd edition; design refer to 60335-1" and 2×MOPP. A sibling, MPM-65-24, appears in an RS listing with UL 62368-1 among its standards; I found no UL list for the MPM-65-15ST or MPM-20-24 specifically. So the approval is medical (ES60601), which suggests the "IEC-60601-only" worry in CMP-10 is about whether a cooker certifier accepts a medical approval, not about the module lacking a UL file | [MPM-20 spec](https://support.elmark.com.pl/meanwell/products/ac-dc/open_frame/MPM-20/MPM-20-spec.pdf); [RS MPM-65-15ST](https://uk.rs-online.com/web/p/switching-power-supplies/2006213) | Low to medium: distributor pages and a datasheet, no UL file number | CMP-10, CMP-09 |
| Is PTFE heat-shrink rated for the lug sleeve? | Hellermann TFE2 PTFE tubing is rated −65 to +260 °C continuous (shrinks at 330 °C or more, so it needs a heat gun above 330 °C and cannot be applied near the Litz serve without protection). The pages I saw say it is **not UL recognised** | [HellermannTyton TFE2](https://www.hellermanntyton.co.uk/products/heat-shrink-tubing/tfe2-0/336-01209) | Medium | COIL-23, PWR-70 |

## 2. Parts that need no one's approval

**Ring lug.** The conflict is that the power-stage decision requires an insulated lug (bare lugs fail the "most unfavourable position" rule at the 15 mm stud pitch, `PS/DECISIONS.md:245`), while its named candidate (TE 2-34853-1) is a 105 °C vinyl part (`PS/DECISIONS.md:249`) and the winding runs to 130 °C. Options, none ordered:

| Option | Rating | Stock / availability | What is missing |
|---|---|---|---|
| TE PIDG STRATO-THERM 50840 (PTFE, #8) | 288 °C | TE ACTIVE; Digi-Key obsolete; RS UK 22 on one read | Stock confirmation, ring-hole drawing (RS lists 4.0 mm ID, tight for M4) |
| TE 1577639-1 (PEEK, #8, 12–14 AWG) | Not found | Digi-Key: backorder, 24-week lead time | Temperature rating |
| TE DG STRATO-THERM uninsulated, nickel-plated copper, M4, 16–14 AWG ([RS 7187410](https://au.rs-online.com/web/p/ring-terminals/7187410)) | 343 °C per RS | Not read | Needs an insulating sleeve or shroud to meet the decision's contact rule; Litz copper (1.96–2.12 mm²) sits at the top of the 14 AWG barrel |
| Burndy YAV14NK uninsulated nickel-plated, 16–14 AWG ([Hubbell](https://www.hubbell.com/burndy/en/products/yav14nk-uninsulated-ring-terminal-for-16-14-awg-nickel-plated/p/520029)) | 650 °F (343 °C) continuous | Not read | Same; stud size to check |
| 3M Scotchlok MU14-14RHTX non-insulated high-temperature ring | Not given in the result | Not read | Rating, stud size |

The uninsulated route needs a sleeve at 150 °C or more, such as PTFE heat-shrink (260 °C, not UL recognised, needs more than 330 °C to shrink) or a fibreglass/silicone sleeve over the barrel, plus a physical barrier between the J2/J5 lugs. Whether that satisfies the power-stage reasoning is a safety-reviewer question (CMP-15 family), not something I can close. A fallback needing no new part: keep the 50840 as the first choice and buy a few uninsulated STRATO-THERM lugs with PTFE sleeving for a prototype only.

**Stock Litz, ferrite, thermal pad, glass:** the prototype already uses stock parts where the repo can (RM Cybernetics or Elecify Litz, Mouser TDK PC95 plates). The unconfirmed items are stock and temperature class, which are the asks in section 4.

## 3. Design hedges (a "no" costs less if these exist)

| Risk | Hedge | Where it stands |
|---|---|---|
| Certifier rejects a gate-drive-only stuck-on cut (CMP-12) | A power-path cut, such as an inlet relay | The checklist says "the inlet relay (DNP) is not built". **Checked 2026-10-20: s53 has no inlet-relay footprint.** PS/DECISIONS.md:3001 lists "the inlet relay provision" (S53-SCOPE item 3, `11-candidates/c53-stuck-on/S53-SCOPE.md`) as not built in s53, and the R5 hardware trip is deferred to the lab's "defeat the firmware" test. So a certifier "no" on Q4 means a re-layout; decide before the production freeze |
| IEC-60601-only supply modules refused (CMP-10) | A second approved module option for PS2 and PS3 with a similar footprint | Not looked for. The modules were chosen for leakage (0.653 mA budget), so any alternative must keep that. Needs a short search once the certifier says what it will accept |
| Reinforced insulation at the sink (CMP-15) | The AlN tiles are already the insulation (PWR-22); keep a thicker option on the drawing | In progress; tiles unquoted |
| Laminate UL scope refused (PWR-06) | A laminate whose UL row covers 2 oz inner copper, or a stackup change | Named in OPEN-ITEMS S12: the F-suffix rows (KB-6164F, 6165F, 6167F) list 102 µm. Ask JLC whether their TG155 option maps to one of those |
| Oil-ignition test (new, section 1) | Confirm the frying hold (230 °C) and the runaway trip (about 308 °C) leave margin below oil ignition | No analysis in the repo; needs the test text (60A.3) before it can be assessed |
| Single-source custom parts (AlN, Litz class 200, ferrite 20 mm) | Quote two suppliers each and keep a stock fallback for the prototype | Section 4 |

## 4. Ledger of external asks

Each row: who, what, rows gated, what to send, fallback if no answer. "Chaser" is a suggested follow-up interval, not a requirement. All are OWNER-ONLY to send; I can draft each.

| # | To | Ask | Gates | Send | Fallback if slow or "no" | Chaser |
|---|---|---|---|---|---|---|
| A1 | Certifier | Governing standard (UL 858 vs UL 1026) | CMP-01 and everything under it | Product description, rating, one-page block diagram | Proceed on UL 858 (public sources above support it) | 1 week |
| A2 | Certifier | Is a medical-approved module acceptable for PS2/PS3? | CMP-10 | Part numbers, leakage budget, datasheet approvals | Look for a UL 62368 alternative with similar leakage | 1 week |
| A3 | Certifier | Is a gate-drive-only thermal cut-off acceptable as a stuck-on backstop? | CMP-12, PWR-58 | Schematic of the TCO loop, failure analysis | Add a power-path relay | 1 week |
| A4 | Certifier | Reinforced insulation at the sink, working-voltage basis | CMP-14, CMP-15 | Stack-up drawing, AlN data | Thicker insulation option | 1 week |
| A5 | Certifier | Firmware-only protections (line limit, runaway) and software class | CMP-13, FW-34 | Protection list, state machine | Add hardware backup for the weakest | 1 week |
| A6 | Certifier | Is the 60A oil-ignition test applicable, and with which pan and oil? | New row | Coil geometry, power, sensor design | Plan the test with the cast iron pan | 1 week |
| A7 | JLC | Does the TG155 option map to a UL row covering 61 µm inner copper? | PWR-06, PWR-79 | `JLC-LAMINATE-QUESTION.md` (send-ready) | Change the stackup or the laminate | 3 days |
| A8 | UL Product iQ | Check E511334, E542996, E311313, E181974, E76222 and the T1 file | CMP-09 | (a login; no email) | Treat ratings as datasheet-only | none |
| A9 | Inlet EMI module vendor | Module choice | ENC-31, PWR-72, PWR-79 | `MODULE-REQUEST.md` | Write an EMI deviation | 1 week |
| A10 | TE or a distributor | Current 150 °C PTFE lug, stock, ring drawing | COIL-23, PWR-70 | 50840 and 1577639-1 | Uninsulated STRATO-THERM plus sleeve (section 2) | 3 days |
| A11 | RM Cybernetics | Stock, price, class of 1000 × 0.05 Litz | COIL-07 | Part and quantity | Elecify 1050/44 (class unstated) | 3 days |
| A12 | Epoxy Technology | Is EPO-TEK 930-4 (or other) rated 260 °C continuous? | SNS-10 | Bond temperature profile | Duralco 128 (260 °C, no margin) | 1 week |
| A13 | Capillary and insulator suppliers | ≥ 10 MΩ at 300 °C | SNS-11 | Drawing | Quartz capillary not credited, redesign the barrier | 1 week |
| A14 | Conro or another supplier | Thermal compound (HTCP20S, "from 30 December 2026") | PWR-24 | Part number | **No second compound named in the repo** | 1 week |
| A15 | AlN suppliers (Valley, Almath) | Quote for tiles | PWR-23 | Drawing, 4 stacks | None named | 3 days |
| A16 | Glass vendors | RFQ for bored glass | ENC-06 | `QUOTE-REQUEST.md` ("no print") | None | 1 week |
| A17 | Counsel | Patent opinions (Breville, impulse claims) | CMP-23, SNS-39 | `PATENTS.md` | Design rules already in CMP-24 | 2 weeks |
| A18 | Mean Well | UL file numbers for MPM-20-24 and MPM-65-15ST | CMP-09, CMP-10 | Part numbers | Datasheet standards list | 3 days |
| A19 | Lab | EMC pre-scan slot | TST-13 | Unit, schedule | Own LISN and analyser | 1 week |
| A20 | Molex | 430251600 plug drawing | CTL-20 | Part number | Use the header drawing and the conservative bound | 3 days |

## 5. What I would send first
A6 and A1 (the new test and the standard), because they shape everything. A9 and A7 next, because they gate the power order. Drafts: A1–A6 are in `CERTIFIER-EMAILS-A1-A6.md` (one email; recommended lab Intertek, via its contact form); A7 is the existing `JLC-LAMINATE-QUESTION.md` (support@jlcpcb.com); A18 goes to info@meanwellusa.com. The firmware sensor overlay (rows FW/DOC-02) is on local branch `fw/c49-plus-main-sensors` (82e4674f7).

## 6. Firmware overlay status (2026-10-20)
- Branch `fw/c49-plus-main-sensors` (82e4674f7): origin/main's sensor component on C49; host suite 21/21. C45 heatsink gain (0.855072) is already in `hs_ntc.h`.
- **ESP-IDF v5.3.6 build does not run on C49.** The IDF wiring lives in main commits c775e925f and c7044f37d (hal renamed to temper_hal, `partitions.csv`, CMake). Cherry-picking them conflicts in `components/power/CMakeLists.txt`, `control/pll_control.c`, `temper_hal/esp32/hal_pwm_esp32.c`, `main/CMakeLists.txt` and deleted-vs-modified files. Even with those, `components/webui` requires `esp_vfs_fat`, which v5.3.6 does not have (it is under `fatfs`). So the J13 firmware has never been built for the target; this port is a real task, not a quick merge.
