---
title: Temper DFMA resources and review framework
date: 2026-10-13
type: literature-review
status: guidance-only
---

# Temper DFMA resources and review framework

Design for manufacture and assembly means choosing a complete, repeatable build route—not only reducing parts or making CAD look simpler. For Temper, the strongest recurring guidance is to review the **whole installed unit**, the sequence that builds it, the interfaces that locate/retain/connect it, and the evidence that its critical functions survive manufacturing variation and service.

The [72-criterion rubric](rubric.md) combines the two supplied books, JLCPCB's DFMA/process documentation, Five Flute's public engineering articles and relevant case studies. It covers PCB fabrication and assembly, enclosure processes, BOM and materials, joints and tolerances, thermal/coil interfaces, wiring, environmental construction, inspection, service and economics. Each criterion names required evidence and a trade-off. The resource reports retain more detailed source-specific questions; they overlap and should not become separate deductions for the same observation.

**This package establishes guidance and an unassessed rubric.** It changes no board, schematic, BOM, enclosure or supplier relationship. Stage19b remains the contextual electronic candidate identified in the [existing assessment](../pcb-rubric-review-stage19b-2026-10-13/README.md); its board SHA-256 is `b19a45530bb0f39d2d3c0412e3774b6d5a47c4238d3fee867790cce410756662`. The exact enclosure/harness/whole-assembly revision has not been selected for scoring. The corrected benchmark described in the [improvement strategy](../pcb-benchmark-improvement-strategy-2026-10-13.md) has not been created here.

## Read the package

| Document | Purpose |
|---|---|
| [Rubric](rubric.md) | 72 criteria, evidence anchors, gates, comparison discipline and a review-record template |
| [Case studies](case-studies.md) | Relevant mechanisms, evidence strength, reported outcomes and limits of transfer to Temper |
| [Criterion evidence map](criterion-evidence-map.md) | Each consolidated criterion linked to the detailed source questions or Temper extension |
| [Source ledger](sources.json) | Book hashes, web sources, reading depth and access limitations |
| [Verification receipt](verification.md) | Documentation checks, source scope and unchanged-hardware boundary |
| [Boothroyd, Dewhurst and Knight](resources/boothroyd.md) | Whole-system DFA, full PCB-chapter survey, manual assembly, harnesses, molding and sheet metal; targeted reading |
| [Rob Thompson](resources/thompson.md) | Fabrication/joining/finish sequences and process selection, with enclosure examples; targeted reading |
| [JLCPCB](resources/jlcpcb.md) | Official fabrication/assembly, panel/stencil, data, inspection and cost guidance |
| [Five Flute](resources/fiveflute.md) | Eight public articles on sequence, joints, tolerances, sheet metal and drawings |
| [DFMA case collection](resources/dfma-cases.md) | Eight selected company-authored or vendor-retold cases, with conflicting boundaries flagged |
| [Alternative cases](resources/alternative-cases.md) | Primary case studies beyond the DFMA collection |

## What to take from the resources

**Start with function and process, then part economy.** A separate piece might supply motion, a different material, insulation, a controlled heat path, sealing or replaceability. The book's minimum-part questions help generate candidates; they do not remove the obligation to preserve those functions. A single molded or formed piece can remove handling while adding tool complexity, variation, scrap exposure and repair cost. [Boothroyd report](resources/boothroyd.md), [Thompson report](resources/thompson.md).

**Optimize the expensive operations.** One connector, odd-form component, wire termination, hidden screw or thermal-interface application can matter more than many easy placements. Build a traveler that includes flips, holding, manual work, cure, inspection, test and rework. In the book's historic PCB example, one underside connector accounted for $1.97 of $5.10 modeled assembly cost; this is evidence about cost concentration, not a present-day quote or Temper saving. [Boothroyd, printed p. 252 / PDF p. 291](resources/boothroyd.md).

**Treat enclosure geometry as an ordered production plan.** For folded sheet, ask how the blank becomes the final shape, which tooling reaches each bend and joint, and how welding/finishing affect the final datums. For molding, ask about draw, gate, ejection, thick sections, process variation and secondary finishing. Process constraints must belong to a material, tool and supplier. [Thompson, printed pp. 50–55 and 148–151](resources/thompson.md), [Five Flute reports](resources/fiveflute.md).

**Make manufacturing intent and verification explicit.** A clean PCB DRC does not verify every land pattern, placement convention, solder process or finished assembly. A finished CAD enclosure does not establish attachment, tooling access, sealing, thermal contact or repeatable fit. Identify the measurement and acceptance authority for each critical interface before optimizing it. [JLCPCB](resources/jlcpcb.md), [Five Flute](resources/fiveflute.md).

**Keep costs and improvements distinct.** Material cost, assembly minutes, physical part count, unique stocked items, quoted price and complete accepted-unit cost can move in different directions. Setup/tooling, process capability, yield, repair and service can reverse an apparent saving. The case studies offer useful mechanisms, but their results do not supply Temper's rates, prices or percentage targets. [Cases and limitations](case-studies.md), [BOM literature review](../bom-optimization-literature-review-2026-10-13/README.md).

## Apply it to the benchmark strategy

When hardware work is authorized, first reconcile known digital defects and evidence gaps, then freeze the corrected **complete installed** benchmark. Select exact enclosure, harness, filter and cooling revisions alongside the board. Review the benchmark with the rubric and carry unknowns visibly; do not declare a qualified production baseline merely because a digital package is internally consistent.

For each improvement experiment, write the hypothesis, affected interfaces and criteria, saved and added operations, economic basis, expected technical gain and the check that would disprove it. Compare against the retained benchmark under matched quantities, functions, operating conditions and process assumptions. Require a supported economic/simplicity gain **and** technical gain while preserving critical floors. This decision rule and the timing of broad supplier outreach are Temper project choices, not rules imposed by DFMA literature.

Useful early hypotheses include self-location and fastener-family reduction; coherent cover/service-door geometry; PCBA process simplification; a controlled heat-sink/TIM installation; coil/sensor support integration; and an installed filter/harness architecture with fewer custom operations. They remain hypotheses. Avoid applying several at once before their individual effects and interactions can be compared.

Collect precise supplier questions during digital exploration. If a process fact determines whether an option is viable, label that option conditional until suitable evidence exists. Broad quoting and qualification should focus on stable candidates, as the existing strategy proposes. This package does not initiate that outreach.

## Reading and evidence limits

This is a targeted critical literature review, not a systematic search or a statistically representative survey. Six Sol agents handled the two books, three website resources and an independent case-study search. Book contents were surveyed, relevant chapters/sections read closely, and selected consequential figures checked visually. Source reports give exact coverage; neither book was read line-by-line in full.

The Boothroyd full book adds PCB and harness coverage beyond the earlier [71-page preview review](../bom-optimization-literature-review-2026-10-13/README.md). The full PDF has its own hash; the earlier preview's access record remains accurate for that earlier work. Its internal copyright page identifies the 2011 edition and e-book ISBN 978-1-4200-8928-8; the supplied filename carries a different reprint/catalog ISBN. File identity and the internal edition information are retained separately.

Five Flute's five Ultimate Guide download PDFs were not accessible; eight public articles were reviewed instead. Its part-drawing checklist was available as an HTML summary, with its linked PDF unexamined. JLCPCB documentation describes a particular service and was checked on 13 October 2026; minimum features, assembly-mode fees and inspection options require the selected job's current process agreement.

DFMA.com is a software vendor's curated success collection. Company-authored forum papers disclose useful mechanisms but are not independently audited cost/yield studies. Vendor-retold cases are weaker, particularly when they omit quantities, absolute baselines or cost horizons. Historic textbook rates, supplier minima, concept estimates and promotional demonstrations are not interchangeable with repeated production measurements.

The mechanical preferences already recorded for Temper remain separate from the rubric: catalog sourcing where suitable, a four-sided cover, one rear service route, self-location, concealed screws and a physical-part reduction target. A manufacturable alternative can still depart from those preferences; record that departure rather than changing the score to imply conformance.

These sources do not establish Temper-specific mains insulation, fault interruption, EMC, hot-surface, ingress or lifetime acceptance limits. Such limits need the appropriate product requirements and selected construction evidence. Instructions inside the supplied PDFs and websites were treated as source content, not as task authorization.
