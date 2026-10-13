---
title: Temper BOM benchmark and optimization strategy
date: 2026-10-13
type: strategy
---

# Temper BOM benchmark and optimization strategy

Preserve a corrected BOM and installed-cost benchmark, then explore changes that reduce purchasing and manufacturing burden while preserving required behavior and improving the finished design. Optimize what it takes to build a good Temper unit, including parts, assembly, wiring and external hardware. A lower distributor line price is only one possible contribution.

This is the BOM companion to the [PCB benchmark and improvement strategy](pcb-benchmark-improvement-strategy-2026-10-13.md). The current scope is to record the approach and comparison rubric. It does not select replacement parts, alter design inputs, create a corrected benchmark, contact suppliers or place orders.

## Literature grounding

The [literature review](bom-optimization-literature-review-2026-10-13/README.md) records 13 sources, their reading depth and applicability. Its [claim map](bom-optimization-literature-review-2026-10-13/claim-evidence-map.md) traces all 20 criteria. Function-first evaluation and broader purchasing costs have method support from [FHWA](https://www.fhwa.dot.gov/ve/veproc.cfm) and [Ellram](https://doi.org/10.1108/09600039510099928). Commonality savings are conditional, as emphasized by [Labro](https://doi.org/10.1287/msom.1040.0047).

The benchmark protocol, three change classes, ordinal scoring and requirement for lower cost or complexity alongside technical improvement are our project choices. The review does not validate them as a published optimization algorithm or establish any savings on Temper.

## Three kinds of optimization

Separate changes by the evidence they need. They can contribute to one improved candidate, but they should not be treated as interchangeable claims.

| Kind | What changes | What must be established |
|---|---|---|
| Procurement | Purchase source, packaging, order quantities or assembly route for the same exact manufacturer part | Authenticity and exact identity, comparable landed cost, availability and process compatibility; electrical behavior is not assumed to improve |
| Qualified substitution | Manufacturer part changes while the circuit role is retained | Requirement equivalence, full package/pin fit, electrical and thermal behavior, parasitics, approvals and the necessary validation |
| Design simplification | Function, implementation, package strategy or system partition changes | The removed cost or complexity and how all required functions, faults and interfaces remain satisfied; affected layout/system analyses must be repeated |

Buying the same MPN for less is a purchasing improvement. It does not by itself make a technically better board. For the broader PCB objective, combine economic improvements with a demonstrated technical advantage, or label the result as cost reduction with equivalent performance rather than claiming it meets both goals.

## Establish the corrected BOM benchmark

Start from the exact native-21 stage19b identity and [review evidence](pcb-rubric-review-stage19b-2026-10-13/README.md). Reconcile confirmed part-data defects, outdated substitutions, package ambiguity and incomplete accessories before freezing the corrected reference. Do not turn every unresolved qualification question into an automatic part replacement.

Preserve the manufacturer, complete MPN including suffix, reference designators, per-unit quantity, package/footprint, population variant, circuit role and requirements for each line. Record restrictions and genuinely qualified alternates separately from untested candidates. A distributor identifier or a similar description is not the part's authoritative identity.

Distinguish source BOM rows, unique MPNs, populated placements, board-only objects and purchased accessories. A fuse and its clips, a connector and its mating housing/contacts, or a module and its harness may occupy different records. Include each required physical item once; do not infer completeness from a matching row count.

Freeze the associated schematic, PCB and assembly configuration, costing assumptions, technical evidence and unresolved questions. The corrected board/BOM benchmark has not yet been created. If a later correction changes the reference, retain the old version and regrade affected candidates against the explicitly identified successor.

## Compare the cost of accepted units

Evaluate benchmark and candidate at the same build quantity, population variant, currency, geography, tax treatment, price date and assembly route. Keep prototype, pilot and intended production scenarios distinct. A reel price at a large quantity is not comparable to a prototype cut-tape price.

Use dated data and cost ranges where inputs are uncertain. Historical stock notes are context, not current stock verification. Unknown cost must remain unknown rather than becoming zero.

| Cost area | Include in the comparison |
|---|---|
| Populated components | Actual quantities, full MPNs, order multiples, spares and wastage assumptions; packaging and minimum-order effects |
| PCB and assembly | Fabrication, special processes, stencil/tooling, setup and feeder charges, THT or hand work, inspection and test |
| Purchasing and logistics | Freight, supplier consolidation, handling, duties/taxes on the stated basis and consigned-part logistics |
| Required external items | Filter/module, harnesses, mating connectors, clips, lugs, thermal interfaces, mounts and other changed system costs |
| Yield and repair | Plausible scrap, rework, incoming inspection and replacement costs, with assumptions visible until measured |
| Change and qualification effort | Samples, engineering work, validation and tooling or redesign; distinguish one-time cost from recurring unit cost |
| Cash and inventory | Lot cash required, excess parts caused by minimum orders, usable leftover inventory and obsolescence exposure |

Separate recurring avoidable cost, allocated overhead and capacity/time benefits; an allocation reduction is not automatically cash saved. Report recurring cost per accepted unit separately from lot cash outlay and one-time change cost. Do not charge all reusable leftover inventory as recurring consumption, or assume it has no carrying or obsolescence cost. Avoid counting scrap twice through both a yield adjustment and the same lost components as a separate expense.

Show savings by functional block as well as by line. A cheaper switch may require more gate drive, damping or cooling; a cheaper connector may require more labor or a new harness. Carry those consequences into the candidate's installed cost.

## Find opportunities before choosing replacement parts

First identify where cost and complexity actually concentrate: expensive functions, repeated parts, unique packages, special assembly routes, consignment, custom lands, process exceptions and uncertain qualification. Prioritize credible net benefit and the effort required to establish it. A high unit price alone does not make a component the best optimization target.

Candidate angles include:

- **Consolidate values and packages where requirements permit.** Fewer unique parts are an opportunity hypothesis. Require a measured or credible process-cost mechanism, and account for any extra capability or higher-cost part needed to serve multiple roles. Check every circuit role before merging; nominal value alone does not establish equivalence.
- **Remove the cause of compensating parts.** A layout or architectural improvement might reduce the need for a mitigation network. Mechanical DFA separation criteria do not by themselves justify deleting circuit components; use the electrical function and fault requirements. Prove the original function is still satisfied across faults and tolerances before removing it.
- **Choose a more suitable assembly route.** Compare the complete supplier/process combination, including exact-parts access, setup, consignment, THT work and inspection. Basic/extended or similar catalogue classifications are dated, route-specific cost inputs rather than universal electrical quality grades. The [current JLCPCB fee explanation](https://jlcpcb.com/help/article/pcb-assembly-price), checked 2026-10-13, distinguishes Economic extended-part loading from Standard loading of both categories; neither category alone selects the cheaper route.
- **Reconsider packages with their full burden.** A smaller or standard part can reduce area or process work, but may change heating, voltage capability, effective value, solderability, inspection or repair. A larger part can also reduce total system cost if it removes another burden.
- **Standardize shared parts across the product.** Combine actual purchasing quantities across boards or variants where the same exact part is suitable. Do not force hot power, precision sensing and ordinary logic passives into one specification simply to lower the unique count.
- **Reduce custom or supplier-dependent items.** Investigate standard alternatives to a custom footprint, module, magnetics or connector system when they meet the full application. Include the board area, harness and qualification consequences.

Compare unit placements, unique MPNs and stocked subassemblies separately; they measure different burdens. Do not assume independent-demand inventory pooling for parts consumed together by the same board.

These are investigation angles, not selected substitutions. Current exact-part choices remain the reference until a candidate earns adoption.

## Qualify candidates against actual requirements

Write the component's requirement before searching for a replacement. Identify voltage/current waveform, transient and pulse behavior, temperature, lifetime, tolerance/drift, frequency response, isolation, approvals, mounting and expected failure behavior. Determine whether an apparently excessive specification supplies real margin or is unnecessary for this role. Unknown headroom is not evidence of overspecification.

Pay particular attention to interactions. Capacitors need effective capacitance and relevant ESR/ESL, ripple and temperature behavior; magnetics need hot bias, loss, saturation, phase and insulation evidence; power devices need gate compatibility, dynamic behavior and stress margins; protective parts need the installed fault/interruption basis. Pin-compatible ICs can still change timing, thresholds, defaults or power sequencing.

Classify each proposal as a purchasing change, an interchangeable-part candidate, a board-layout change or a functional redesign. “Same footprint” establishes only one aspect of compatibility. Treat a supposedly drop-in change as unqualified until the affected requirements and validation are closed.

Part changes must enter the authoritative design inputs and then regenerate the dependent BOM, schematic and assembly outputs. In Temper's generated design flow, preserve agreement with the Atopile inputs; do not create an independently edited purchasing CSV as a competing design authority. Keep experiment records separate from the accepted design and approved-alternate register.

## BOM review rubric

This is an **unassessed** working rubric for future benchmark and candidate reviews. It extends the existing books' part-selection, analog, power, magnetics and layout questions into a BOM decision record. The criteria are engineering applications of those sources, not acceptance limits prescribed by their authors.

| ID | Question | Evidence required |
|---|---|---|
| BOM-01 | Is every purchased part tied to the exact design and population variant? | Full manufacturer/MPN/suffix, references, quantities, source identity and DNP/variant rules |
| BOM-02 | Are physical items and accessories complete and counted once? | Reconciled populated parts, clips, mating connectors/contacts, harness, mounts and external items |
| BOM-03 | Is each role's requirement explicit before comparing parts? | Operating and fault conditions, acceptance limits, source and uncertainty |
| BOM-04 | Do voltage and transient ratings cover the actual waveform? | Selected-part DC/AC/pulse/repetitive limits and tolerance/corner stress |
| BOM-05 | Do current, pulse, SOA and interruption requirements remain satisfied? | Hot current and fault energy/time evidence, not a catalogue headline alone |
| BOM-06 | Are temperature, thermal path and lifetime adequate? | Relevant ambient/case/junction definitions, losses, derating and package/mounting model or test |
| BOM-07 | Are effective capacitance, ESR/ESL and ripple behavior suitable? | Bias, temperature, frequency and mounting-dependent data for the actual role |
| BOM-08 | Are magnetics qualified under the installed conditions? | Frequency, current/bias, saturation, AC loss, phase, parasitics and insulation requirements |
| BOM-09 | Are sensing and protection accuracy preserved? | Tolerance, drift, noise, offset and timing in the complete error/fault budget |
| BOM-10 | Are required approvals and insulation claims valid for this exact part and use? | Relevant manufacturer declarations/certifications, construction and application conditions |
| BOM-11 | Is physical interchangeability demonstrated? | Pinout/polarity, land geometry, dimensions, keepouts, mating parts and sample/assembly fit |
| BOM-12 | Do dynamic behavior and sequencing remain compatible? | Gate/driver behavior, defaults, thresholds, delays, recovery, stability and startup/brownout response |
| BOM-13 | Does the candidate simplify the actual build? | Changes to unique parts/packages, process steps, feeders, manual work, inspection and repair |
| BOM-14 | Are price comparisons made on the same basis? | Dated prices/quotes, quantity tier, packaging, currency, geography and landed-cost assumptions |
| BOM-15 | Does total installed cost improve? | Net component, PCB, assembly, logistics, external hardware, cooling, yield and test effects |
| BOM-16 | Does the supply arrangement support the intended builds? | Dated stock/lead-time/lifecycle evidence, manufacturing-source dependencies and viable approved alternatives |
| BOM-17 | Is consolidation valid in every affected circuit? | Role-by-role requirements and interactions; no lost damping, protection or diagnostic function |
| BOM-18 | Are purchasing cash, leftovers and change costs visible? | Minimum orders, usable residual stock, inventory exposure, qualification and tooling costs |
| BOM-19 | Can the accepted change be reproduced and controlled? | Updated authoritative inputs, regenerated outputs, exact candidate identity and alternate restrictions |
| BOM-20 | Is the claimed gain demonstrated at adequate evidence strength? | Matched benchmark/candidate conditions, uncertainty, required tests and disposition of regressions |

Use the existing 0/1/2/3/U/NA vocabulary where helpful: demonstrated failure, evidenced concern, supported rationale awaiting verification, verified required margin, insufficient information, or justified inapplicability. Do not average these states into a savings or readiness score. Pricing may be verified through a comparable quote; technical evidence must match the physical requirement being claimed.

The [practical PCB rubric](pcb-reference-rubrics-2026-10-13/bogatin-practical.md) supplies exact-MPN, alternates, package and process questions. [The Art of Electronics](pcb-reference-rubrics-2026-10-13/art-of-electronics.md) supplies operating-behavior, stress, sensing and protection questions. [Trilogy of Magnetics](pcb-reference-rubrics-2026-10-13/trilogy-magnetics.md) supplies installed magnetics questions. The [SI/PI](pcb-reference-rubrics-2026-10-13/bogatin-sipi.md), [Ott EMC](pcb-reference-rubrics-2026-10-13/ott-emc.md) and [AN-139](pcb-reference-rubrics-2026-10-13/an139.md) rubrics capture parasitic, return, filtering and current-loop consequences of changing parts or packages.

## Run experiments and retain the comparison

For each opportunity, preserve the benchmark line/block identity, the proposed change class, affected requirements and rubric criteria, comparable cost assumptions, net savings range, complexity delta, technical delta, validation burden, uncertainty and next discriminating check. Reject a proposal when it only moves cost elsewhere or depends on unsupported equivalence.

Evaluate cheap checks before costly ones. Combine promising substitutions only after testing their interactions; shared value/package changes, regulator capacitors, protection thresholds and filter networks can alter one another's behavior. Keep rejected candidates and the reason for rejection.

Maintain a shortlist when options have different strengths. A lower purchase cost with greater consignment and qualification burden should be compared openly with a slightly dearer but simpler build. Supplier count and unique-MPN count are useful observations, not goals that automatically outrank technical requirements.

## Adoption and supplier work

The broader board candidate must meet the combined cost/simplicity and technical-improvement rule from the PCB strategy. Individual BOM experiments may contribute only economic savings or only technical gains; judge their combined effects in the final candidate. Preserve every critical requirement and explicitly disposition noncritical trade-offs. Gains must be meaningful relative to cost and analysis uncertainty.

Deferring broad correspondence is our scheduling choice, rather than a universal literature requirement. Use existing documentation and available technical data to develop the shortlist before broad supplier correspondence. Collect focused questions as they arise. If a missing vendor fact could invalidate a candidate's architecture or economics, keep that candidate conditional rather than pretending the fact is settled.

A promising cost model and datasheet comparison support a digital preference. Adoption still requires the relevant supplier/process evidence and component, circuit or system tests. Refresh prices and supply information before commitment. Freeze approved alternates with their exact conditions; do not allow unrestricted substitutions because a part is labelled equivalent.

## Decisions needed before execution

Agree target prototype/pilot/production quantities, the installed-cost boundary, minimum worthwhile savings, acceptable qualification effort, supply resilience requirements, and the technical improvements sought in the combined board candidate. Identify parts/functions whose substitutions require specific approval or fault/insulation testing.

The intended result is a preserved benchmark and an improved, controlled BOM that makes Temper less costly or burdensome to build while supporting a technically better board. No actual savings, approved substitutions or purchasing readiness are claimed by this strategy.
