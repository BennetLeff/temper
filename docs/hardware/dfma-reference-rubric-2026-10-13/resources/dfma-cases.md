# DFMA.com case-study review for the Temper rubric

Scope: eight selected cases from [Boothroyd Dewhurst's case-study collection](https://www.dfma.com/resources/studies.asp), accessed 2026-10-13. The collection is a vendor-curated success set, not a representative sample or evidence that the advertised percentages transfer to Temper. The three first-person conference papers below are stronger on mechanisms than the vendor summaries, but still lack independently audited production-cost ledgers. Figures are always scoped to the reported assembly or product, never to a hypothetical Temper result. PDF page citations use one-based PDF pages. No hardware was assessed or changed.

## 1. Dynisco: PCBA architecture and should-cost inputs

**Source and depth.** James McDonough, JM Engineering Consulting, “Using DFM to Understand Printed Circuit Board Assembly Costs,” DFMA Forum 2016, [six-page first-person paper](https://www.dfma.com/forum/2016pdf/McDonoughPaper.pdf), read PDF pp. 2–5; [vendor case page](https://www.dfma.com/resources/pcb-assembly-costs.asp), read full. The author consulted for Dynisco and other Roper businesses; this is a company project account in a software-vendor forum.

**Mechanism and outcome.** A Pareto study put PCB assemblies at **24% of the total cost of one Dynisco product** (PDF p. 2). For a sensor refresh, merging two connected boards into one produced **12% savings**, but the paper does not specify whether this means sensor unit cost, PCBA cost, or some other denominator (pp. 2–3). A separate high-volume sensor used a model to renegotiate its PCBA price by **8%, worth $13,000 per year** (p. 3). The paper's 2 × 0.4 inch example shows why a model cannot be trusted without actual inputs: a software default of 400 holes versus 33 actual holes changed modeled process cost by **$7.50** (p. 3). The mechanism is architecture choice plus material, setup, processing, reject, tooling, placement, solder and test inputs (pp. 3–5). There are no unit volumes, quote ledger, supplier terms, or test results.

**Transferable rubric question.** For any board merge/split or part change, compare total installed cost at the same build volume and process assumptions. Enter the actual hole count, board geometry, layer count, placement population, unique feeders, hand steps, test and reject assumptions. Ask whether a connector/harness removed from the board BOM simply reappears in enclosure assembly. A supplier price negotiation is a distinct outcome from a design simplification; label it as such. The **12% and 8% are Dynisco-only reports**, not Temper targets.

## 2. CNH Industrial: large DFA gains, small total-package cost gain

**Source and depth.** Kapil Kumar, Michael Freisleben, V. Pavan K. Reddy and Mayank Chaturvedi, “Cost-Effective Product Development: Boothroyd Software's DFA Approach to Tractor Cooling Design,” [four-page company-authored DFMA Forum 2024 paper](https://www.dfma.com/forum/2024pdf/freislebenpaper24.pdf), read PDF pp. 1–4; [vendor case page](https://www.dfma.com/resources/tractor-cooling-package.asp), read full.

**Mechanism and outcome.** In a **concept design** of a tractor cooling package, the team combined parts, removed some fasteners through alternate joints, and retained functional foam seals and panels. It reports **352→294 parts**, **18% lower modeled assembly process time**, DFA index **9.93→11.53**, and an **estimated ~1.2% lower total cooling-package cost** (PDF pp. 1, 3–4). Ten improvement points were identified, with two examples described (PDF p. 3). This is a proposal/model at concept phase; the paper does not show production-run times, tooling amortization, lifetime joint tests, field failure rates, or the exact cost breakdown.

**Transferable rubric question.** Record physical part count, operation time, and **whole-subassembly cost as separate metrics**. Functional sealing and heat transfer can justify a separate part even when part count would decrease without it. A fastener deletion needs attachment strength, tolerance and service evidence; a snap or weld is not automatically cheaper or better for Temper. The large count reduction produced a modest reported total-cost estimate, a useful guard against treating counts as savings.

## 3. BAIC: enclosure structure, self-location, material change

**Source and depth.** Wan Ni, Beijing Automotive Technology Center, “Re-design on Vehicle Front Support Structure Using DFMA,” [seven-page first-person paper](https://www.dfma.com/pdf/wanpaper.pdf), read PDF pp. 1–6; 2017 project described, **publication date not stated**; [vendor case page](https://www.dfma.com/resources/vehicle-front-support.asp), read full.

**Mechanism and outcome.** The original grille/horn support reused legacy mounting geometry with weakly located mounts and 24 fasteners; parts required hand-holding while circular holes found position (PDF pp. 3–4). The proposal integrates **six metal stampings into one PP-GF30 injection-molded part**, revises locating features, reduces fastener types, and preserves selected interfaces for platform reuse (pp. 4–5). The abstract reports **76% less manufacture time**, **30% lower manufacturing cost**, and **24% lower weight** for the support (p. 1); these align with the source's Figure 3 comparison, which labels original/redesign/savings but leaves measurement procedure unstated (p. 6). Figure 3 counts **30→10 parts**, or 20 removed. The adjacent narrative instead says **35→12 independent parts**, while retaining the “20 removed” statement. The two count boundaries are **unexplained**; the narrative difference would be 23. It also claims **70% greater assembly efficiency** without defining that metric. Unit volume, tool cost, stiffness test results, thermal/creep/aging results, and the source of Figure 3's times and costs are absent. A cross-functional review judged the concept feasible; that is weaker than pilot capability.

**Transferable rubric question.** An enclosure wall, support or bracket may integrate mounts **only after** the chosen process and material meet actual loads, heat, chemical exposure, electrical insulation, tolerance and service needs. Score locating datum quality separately from number of screws. Require exact part-boundary definitions when a Figure 3 count and the accompanying prose disagree.

## 4. IDEXX: access-door subassembly and fastener labor

**Source and depth.** Boothroyd Dewhurst, “[IDEXX: Simplifying a Veterinary Device](https://www.dfma.com/resources/idexx.asp),” vendor case page, read full; no publication date or first-person technical paper linked. Named engineer: Justin Griffin. Access depth is a detailed vendor narrative, **not a production report**.

**Mechanism and outcome.** A Catalyst Dx analyzer **Maintenance Access Door subassembly**, originally a sheet-metal assembly, required torqueing and marking many fasteners. The page reports **183→31 parts**, **63→0 fasteners**, and **45→11 minutes assembly time** for that subassembly. It says cost, weight and service targets were met but provides no cost denominator, price or test data. Tooling, mold feasibility, latch life, service cycles and repair damage are not described.

**Transferable rubric question.** At each access cover and board mount, count not only fasteners but torque specifications, markings, tool changes, retained hardware, damage on reopening and service sequence. Verify any snap/clip alternative against heat, fatigue and repeated access. **The numbers apply to a maintenance-door assembly, not the whole analyzer.**

## 5. Anonymous laptop platform: test before closure and harness motion

**Source and depth.** Boothroyd Dewhurst, “[Laptop Development Using Concurrent Costing](https://www.dfma.com/blog/dfma-case-study-redesigned-laptop.asp),” vendor blog, 2025-08-15, read full. The OEM, production period, paper and raw trial data are undisclosed.

**Mechanism and outcome.** A modular main/video-board assembly could be tested **before** enclosure installation, avoiding some tear-down after finding board defects. A flexible cable around a hinge replaced discrete wiring, with a smaller pass-through and claimed lower chafe risk. The article reports **72% lower total assembly time**, **70% fewer assembly hours per unit**, **63% less unit-test time**, **75% less PWB assembly time**. Absolute baselines, denominators across test stages, production volume and field reliability are absent. The 70%/72% metrics may overlap and must not be added.

**Transferable rubric question.** Write the assembly/test sequence, including when each PCB and thermal path becomes testable and whether failure requires destructive or laborious reopening. For wires across a moving or removable interface, capture bend radius, restraint, chafe, strain relief, connector access and replacement path. Applying this to Temper is a hypothesis until the candidate's harness and enclosure sequence are demonstrated.

## 6. Anonymous computer mouse: separate mechanical, electrical and process counts

**Source and depth.** Boothroyd Dewhurst, “[Computer Mouse Redesign](https://www.dfma.com/blog/dfma-case-study-redesigned-pc-mouse.asp),” vendor blog, 2025-05-27, read full; client unnamed, no source drawings/ledger or first-person report.

**Mechanism and outcome.** A stackable screwless architecture reports **31→16 unique mechanical parts**, **30→28 electrical parts**, **17→6 min assembly per mouse**, **83→56 assembly operations**, **10–11→0 adjustments**, **10→0 screws**, and **40% lower material cost per mouse**. “31→16” is specifically mechanical parts, not the total BOM. Automation is described as a possibility, not an observed production outcome. Supplier availability, tooling amortization, assembly repeatability and service-cycle data are omitted.

**Transferable rubric question.** Define count units before comparing candidates: quantity of physical pieces, unique procurement IDs, electrical components, operations, adjustments, fasteners, feeders, tools and process types can move independently. A self-locating assembly may improve both build and service, but quantify how the joints survive appliance heat and cleaning.

## 7. NCR Voyix 2760 terminal: beware conflicting boundaries in a success story

**Source and depth.** Boothroyd Dewhurst, “[NCR Voyix POS terminal](https://www.dfma.com/resources/ncr-voyix-pos-terminal.asp)” and “[Redesigned POS Terminal](https://www.dfma.com/blog/dfma-case-study-redesigned-POS-terminal.asp),” detailed vendor case and retrospective blog dated 2025-05-19; full pages read. No NCR first-person paper or ledger linked.

**Mechanism and outcome.** The case page gives **326→48 parts**, **53→13 min assembly**, **69→24 suppliers**, and **$2.5M→$1.4M manufacturing labor cost** for the terminal redesign. It reports that screws and some cables/harnesses were eliminated. A separate promotional demonstration assembled **15 pieces in under two minutes**. The pages do not reconcile the 48-part product count with 15 demo pieces, or 13-minute regular assembly with the demo time. Production duration/volume and whether the labor figures are annual or lifetime are not specified; a blog calls the $1.1M difference “savings” without a clear horizon. Other “millions” are not supported by a ledger.

**Transferable rubric question.** When comparing a benchmark and an improved Temper candidate, put exact assembly boundary, station definition, build volume, labor rate, cost horizon, source evidence and test inclusion beside every metric. Never substitute a staged demonstration for a timed repeatable build. Treat harness removal as a reliability *hypothesis* until faults and replacements are measured.

## 8. Truck instrument panel: a modelled concept, not a field-proven redesign

**Source and depth.** Boothroyd Dewhurst, “[Evaluation of Truck Instrument Panel Designs for Cost and Environmental Impact](https://www.dfma.com/resources/panel.asp),” vendor case page summarizing Peter Dewhurst's university study; no original paper linked from page and no publication date given. Read full vendor page only. **Limited evidence depth.**

**Mechanism and outcome.** The analysis replaced a many-piece steel panel concept with structural moldings and reports **482→121 predicted main/subassembly steps** and **$35.60 projected reduction per panel** in assembly plus main-structure manufacturing cost. The page explicitly calls it an alternative concept rather than a finished panel. Its recyclability claim is qualitative; there are no production measurements, vehicle-impact validation, tooling costs or confirmed recovery yields. It should be treated as a *design-space example*, not achieved savings.

**Transferable rubric question.** Mark every Temper variant as concept, detailed design, prototype, pilot or production and prevent a modeled labor saving from being presented as repeatable cycle time. Include tool investment, recyclability/separability, and end-of-life handling in the comparison when material/process choices change.

## Cross-case rubric additions (original synthesis)

These are proposed review questions inferred from the cases above; they are **not** case-study claims or acceptance limits.

1. **Boundary and provenance.** For every before/after claim, record exact board or enclosure revision, assembly boundary, denominator, unit, volume, labor rate, quote date, production horizon, model versus measured status, and source page. Flag arithmetic contradictions and overlapping metrics. (Dynisco, CNH, BAIC, NCR.)
2. **Architecture trade.** For board merging/splitting and enclosure integration, account for connectors, harnesses, fasteners, fixtures, tooling, testing, field replacement and process yield in *whole installed cost*, while preserving electrical, thermal and mechanical requirements. (Dynisco, BAIC, laptop.)
3. **Real assembly path.** Trace component presentation, orientation, self-location, hands/tool access, fastening, adjustment, inspection, test-before-closure, rework and service. Demonstrate repeated builds; a single demo is not a cycle-time sample. (NCR, mouse, IDEXX, laptop.)
4. **Functional-part veto.** Keep a separate part when it is required for motion, material separation, thermal contact, sealing, isolation, service or independent replacement. Fewer parts cannot override these functions. (CNH, BAIC, IDEXX.)
5. **Process-cost sensitivity.** Replace defaults with actual fabrication and assembly features; vary build volume and reject assumptions. Call out quotations, should-cost models, theoretical DFA time and observed cycle time as different evidence types. (Dynisco, CNH, truck panel.)
6. **Service and durability.** A snap, weld, flex circuit or reduced harness may simplify initial build but add heat-aging, fatigue, replacement or inspection costs. Ask for qualification and service-cycle evidence before crediting savings. (IDEXX, laptop, BAIC.)

## Evidence caution for the parent synthesis

The vendor collection itself claims “billions” and broad typical part reductions; it does not publish a sampling frame, all attempts, auditing method or common denominator. Do not quote those as expected Temper results. The **CNH and Dynisco papers** are especially useful because they disclose a cost boundary and a modeling trap. The **BAIC paper** is useful for locating and process integration but presents **30→10 parts in Figure 3 and 35→12 independent parts in prose**, without explaining their boundaries. **NCR** has a 48-parts/15-demo-pieces and 13-min/two-min-demo boundary mismatch. The truck panel is concept modeling. Count first-person company papers and vendor-retold cases separately when describing evidence strength.

## Primary-PDF visual verification, 2026-10-13

The claims below were inspected in Chrome's rendered PDF pages in addition to extracted text. This verification checks **what the source page actually prints**; it does not independently verify factory outcomes.

- **Dynisco:** rendered PDF page 3 shows the 8% PCBA price renegotiation and $13K/year for the high-volume sensor; rendered PDF pp. 3–4 show the example's 400 default holes, 33 actual holes, and $7.50 *modeled process-cost* difference, with the sentence crossing the page break. The 12% board-merge claim is printed at the page 2–3 break. No source table of realized costs was supplied.
- **CNH:** rendered PDF page 1 abstract shows 352→294 parts, 18% lower assembly process time, DFA index 9.93→11.53, and 1.2% *total cooling-package* cost reduction. Rendered PDF page 4 results labels the ~1.2% figure as **estimated**; the same page repeats 352→294 and 18%. These are concept-stage reports.
- **BAIC:** rendered PDF page 1 abstract shows the 66%, 76%, 30% and 24% headline reductions. Rendered PDF page 6 Figure 3 visibly lists **30→10 parts** (20 removed), while adjacent prose gives **35→12 independent parts** and still says 20 removed. Figure 3 also gives 552→131 seconds, RMB 42.41→29.62 manufacturing cost, and 1.28→0.97 kg, consistent with the rounded abstract percentages. The count-boundary disagreement remains unexplained. The Figure 3 label “Actual time” does not disclose a timing study, so it is **not** proof of repeatable production cycle time.

All other case accounts above were checked against accessible **HTML text only**, not visually verified primary drawings or cost records. Browser-rendered PDF pages were not saved or redistributed.
