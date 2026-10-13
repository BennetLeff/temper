---
title: DFMA case studies relevant to Temper
date: 2026-10-13
type: case-study-review
---

# DFMA case studies relevant to Temper

These **15 external case accounts and four book examples** were selected for PCB assembly, power electronics, enclosure, wiring, cooling or appliance service relevance. They are not 19 independent controlled redesign experiments. The detailed [DFMA-collection review](resources/dfma-cases.md) and [alternative-case review](resources/alternative-cases.md) retain reported figures, their denominators, source links and reading coverage. Read their qualifications with the numbers.

The best starting cases are Dynisco for PCBA architecture and cost-model inputs; CNH for the distinction between parts, time and whole-package cost; the stove paper for tooling and integration trade-offs; the heatsink paper for assembly-defect observability; Thompson's folded enclosure for bend/tool sequence; and the negative molded ECU account for inspection state. Others are useful analogies with weaker or narrower evidence.

## External cases and how to use them

Every Temper question below is our inference. The source is evidence about its own product or process, not a recommended Temper implementation or predicted saving. Criterion IDs refer to the [rubric](rubric.md).

| Case and primary account | Evidence and transfer limit | Question to bring to Temper | Criteria |
|---|---|---|---|
| [Dynisco PCBA architecture and should-cost](https://www.dfma.com/forum/2016pdf/McDonoughPaper.pdf), 2016 | First-person consulting paper. Board consolidation and model-input sensitivity; one savings denominator is unspecified. Negotiated price is distinct from engineering savings. | Are actual holes, feeders, manual work and test entered in a complete installed-cost comparison? | 01, 03, 13–24, 43, 67–68 |
| [CNH cooling package](https://www.dfma.com/forum/2024pdf/freislebenpaper24.pdf), 2024 | Company-authored concept study. Substantial modeled part/time reductions accompany only about 1.2% estimated package-cost reduction. | Do eliminated fasteners actually save accepted-unit cost while retaining seals and thermal function? | 02, 31–42, 49–54, 67–68 |
| [BAIC front support](https://www.dfma.com/pdf/wanpaper.pdf), project described in 2017 | Proposed formed-metal-to-polymer integration and better location. Figure and prose use unexplained different part-count boundaries; qualification and tool-cost detail absent. | Can a consolidated support meet heat, load, variation and service needs with unambiguous counted scope? | 02–04, 25–36, 49–52 |
| [IDEXX maintenance access door](https://www.dfma.com/resources/idexx.asp), undated | Vendor-retold subassembly case; fastener and time reductions reported, no detailed cost or life data. | Count torque/mark/tool operations and test repeated access before replacing screws with clips. | 34–36, 49–52, 69–70 |
| [Laptop architecture and pre-closure testing](https://www.dfma.com/blog/dfma-case-study-redesigned-laptop.asp), 2025 retrospective | Anonymous vendor story; overlapping percentage metrics, absolute baselines and build period missing. | At which build stage can faults be found without dismantling the product? | 43–46, 49, 61–64, 69 |
| [Computer mouse redesign](https://www.dfma.com/blog/dfma-case-study-redesigned-pc-mouse.asp), 2025 retrospective | Anonymous vendor story; mechanical, electrical and operation counts differ. Automation is prospective. | Are reduced physical pieces, electrical parts, procurement items and adjustments kept as separate metrics? | 02, 06, 49–53, 67 |
| [NCR terminal](https://www.dfma.com/resources/ncr-voyix-pos-terminal.asp), undated case | Vendor story. Full-product counts/build time differ from a staged small-piece demonstration; labor-cost horizon unclear. | Is the benchmark comparison a matched build boundary with test, labor and quantity disclosed? | 01, 49, 64–68, 71 |
| [Truck instrument-panel alternative](https://www.dfma.com/resources/panel.asp), undated summary | Modeled concept reported by vendor; original technical paper not available from the page. | Does every claim identify concept versus prototype versus repeated production evidence? | 03–04, 29, 67–68, 72 |
| [Gas-stove redesign](https://www.mdpi.com/2411-9660/6/5/88), 2022 | Original open paper, modeled DFA/cost/FEA. Integration raises tooling allocation and mass; no observed production or field reliability. | Does enclosure integration still win with tooling amortized at realistic volume and load/function preserved? | 02–04, 25–36, 67–68, 71 |
| [Pin-in-paste PCBA process](https://www.mdpi.com/2504-4494/10/8/276), 2026 | Original production-process account for a very high-volume sensor. The large saving is a tracked process scope; life tests remain open. | Can eligible exact THT items share reflow without compromising joint fill, part survival or service? | 19, 21–24, 63, 65, 67–68 |
| [Power-electronics heatsink test](https://iris.polito.it/retrieve/e384c432-00b7-d4b2-e053-9f05fe0a1d67/electronics-09-01020.pdf), 2020 | Original electrothermal fault-injection simulation. Regulated external output can mask poor thermal contact. This is not a production sensitivity measurement. | Can inspection/test detect wrong TIM, clamp or contact conditions—not merely deliver nominal output? | 37–39, 42, 53, 61–63 |
| [AMtec harness-to-busbar redesign](https://amtec1.com/mini-case-study-design-for-manufacturing/), undated | Firsthand vendor account; labor/material reductions have different denominators and no audited ledger. | Would power-distribution integration remove whole-system work while retaining insulation, cooling, fault behavior and repair? | 03, 43–48, 49, 67, 71 |
| [N&H catalog versus custom housing](https://www.nh-technology.de/en/standardgehaeuse-oder-kundenspezifische-gehaeuseloesung/), undated | Vendor forecast with tooling and unit prices. Volume determines its crossover; functions also change. | At what plausible quantity would custom tooling pay back, including changes, yield and qualification? | 04–05, 29–30, 67–68 |
| [Abery molded ECU housing failure](https://www.a-mold.com/case-studies/jcb-ecu-housing-nylon-gf-warpage-case-study.html), 2026 retrospective of a reported 2011 event | Firsthand negative vendor account, uncorroborated. Fixtured sample approval concealed free-state warpage. | Is acceptance measured in the state delivered to assembly, with fixtures explicit? | 29, 32–33, 61, 64–66 |
| [Coffee-maker disassembly comparison](https://pubs.acs.org/doi/10.1021/acssusresmgt.5c00012), 2025 | Publisher abstract only for an original physical teardown study; full paper unexamined. A lead, not a full review. | Measure replacement of specific likely-failure modules and restoration, not only complete teardown time. | 51, 69–70 |

## Four useful textbook examples

| Example and locator | What the source supports | Temper application and limit |
|---|---|---|
| Boothroyd connector board, printed p. 252 / PDF p. 291 | One underside connector can concentrate manual insertion/solder cost. | Classify odd-form and underside operations before changing packages. Historic modeled rates cannot predict today's EMS cost. |
| Boothroyd power supply, printed pp. 253–255 / PDF pp. 292–294 | Its modeled manual operations concentrate in jumpers, radial insertions and large component mounting; Figure 6.16 was visually checked. | Look for expensive operation families, preserving high-current and thermal function. It is a cost-model example, not a validated induction-power design. |
| Thompson Pedalite electronics housing, printed pp. 52–55 / PDF pp. 28–29 | Molding feedback, a precision post-drilled locator and planned releasable joints coexist. | A controlled secondary operation may beat forcing one process to deliver every fit. Its exposure and load differ from Temper's. |
| Thompson aluminum enclosure, printed pp. 150–151 / PDF p. 77 | Flat preparation, ordered bends, special tool access, weld/grind/paint are a complete route. | Check cover geometry against actual bend and seam access. The example does not prove a universal wall thickness or cost. |

Page-specific detail is retained in the [Boothroyd](resources/boothroyd.md) and [Thompson](resources/thompson.md) reports.

## Decide what evidence an analogy can provide

The transfer test is **mechanism → relevant interface → changed operation → potential benefit → new failure mode → discriminating evidence**. A screwless cover example can motivate a fastening experiment; only Temper load, heat, repeated-service and sealing evidence can justify its adoption. A pin-in-paste paper can motivate a process-route question; the exact Temper parts, solder geometry and assembler must support it.

Keep these evidence classes separate:

- **Measured or reported process change:** useful on its stated line and scope; verify what was actually measured, the denominator and unresolved life/quality evidence.
- **Model or concept:** useful for hypotheses and sensitivity; preserve tool/labor/material assumptions and validate consequential predictions.
- **Firsthand vendor account:** useful for failure mechanisms and process details, with commercial selection and incomplete corroboration visible.
- **Vendor-retold success:** a weaker analogy; do not infer cost, reliability or repeatability absent disclosed evidence.
- **Abstract-only lead:** can identify a relevant method or question; cannot support unseen procedures or detailed results.

No reviewed case is a fully comparable induction-cooker redesign with matched mains/fault, EMC, coil/pan, thermal, liquid-exposure, production and service evidence. **No cross-case average saving, predicted Temper percentage, or universal tooling crossover is inferred.**

## Evidence checks and remaining access limits

The collection agent visually checked Dynisco's hole/model-cost and negotiation figures, CNH's part/time/estimated package cost, and BAIC's conflicting Figure 3/prose counts against primary PDFs. The book agents checked the specified power-supply and enclosure/molding pages. Other vendor cases were read as HTML text. The alternative papers were read through available original indexed text or the author repository; direct MDPI opens returned access errors. The heatsink tables were checked against repository text; attempted browser screenshots failed, so they are not described as visually verified.

The alternative search retained two further leads without full review: [electric-oven disassembly comparison](https://doi.org/10.1016/j.procir.2022.02.099) and [PCBA setup-time reduction](https://doi.org/10.1111/j.1937-5956.2005.tb00019.x). They are not counted among the 15 external cases. The coffee-maker case remains expressly abstract-only. Detailed source-access records are in [sources.json](sources.json).
