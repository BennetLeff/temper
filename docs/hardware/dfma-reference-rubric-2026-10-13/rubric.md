---
title: Temper design for manufacturing and assembly rubric
date: 2026-10-13
type: rubric
status: unassessed
---

# Temper design for manufacturing and assembly rubric

Use these 72 criteria to compare complete Temper builds: PCB fabrication and assembly, enclosure, bought hardware, coil, cooling, wiring, final assembly, inspection and service. Each question is an original Temper review requirement informed by the cited resources. It is not a manufacturer's specification, a reproduction of a textbook grading system, or a score for the current board.

This rubric complements the existing 179 electrical/layout criteria; it does not replace their operating, fault, thermal or EMC checks. The source reports supply page-specific mechanisms and reading coverage. **B** means [Boothroyd, Dewhurst and Knight](resources/boothroyd.md); **T**, [Thompson](resources/thompson.md); **J**, [JLCPCB](resources/jlcpcb.md); **F**, [Five Flute](resources/fiveflute.md). **P** means a Temper requirement or extension from the [benchmark strategy](../pcb-benchmark-improvement-strategy-2026-10-13.md), [BOM strategy](../bom-benchmark-optimization-strategy-2026-10-13.md), or existing manufacturing-review method. Source letters indicate supporting methods, not authors' approval of Temper-specific acceptance limits. [Case studies](case-studies.md) supply examples and counterexamples.

## Record evidence before assigning a score

For each applicable criterion record: exact design/part/process revision; product requirement and its authority; build quantity and manufacturing route; evidence location and date; method and uncertainty; result against acceptance; consequence; owner and next discriminating check. Mark evidence as source-confirmed design, fresh calculation, simulation, supplier-supported process, physical measurement, inherited result with identity checked, or unknown. A screenshot, supplier capability webpage and repeated build establish different things.

| Score | Meaning for the explicitly named build stage |
|---|---|
| U | Essential information is missing. Record what is unknown; it is not a demonstrated defect. |
| 0 | Applicable requirement demonstrably fails, or the proposed manufacturing/assembly operation is demonstrably impossible. |
| 1 | Evidence identifies a material concern; the design or closure method remains inadequate. |
| 2 | Coherent design and rationale exist; a consequential check required for this stage remains open. |
| 3 | The stated requirement is verified with suitable evidence for this stage and representative conditions. |
| NA | Inapplicable, with a reason fixed before comparing alternatives. |

Use the highest supported anchor; do not turn missing evidence into either failure or success. Stage must be named: cold fit sample, engineering prototype, pilot build, or production. A cold fit pass cannot be inherited as a powered qualification pass. Record coverage and score distributions by category; **do not average scores into release readiness**. A repeated physical test is not necessary for every drawing check, but geometry alone cannot verify an operating or production-yield claim.

The tables identify required records and typical trade-offs. Numerical limits come from agreed Temper requirements, exact part/material data, the selected process and supplier, and applicable product obligations. Textbook examples and web-shop rules do not set universal limits.

## A. Product architecture and manufacturing assumptions

| ID | Review requirement | Required evidence and acceptance basis | Trade-off to expose | Basis |
|---|---|---|---|---|
| DFMA-01 | Define the complete unit and build route being optimized. | Revision manifest covering electronics, enclosure, filter, harness, cooling and bought parts; intended quantity, rate, region and stage. Compare the same boundary. | A PCB saving can increase final-assembly cost. | B, P |
| DFMA-02 | Assign every separate physical part a necessary function. | Function map; identify relative motion, distinct material/isolation, assembly or service reasons; preserve electrical and thermal functions before proposing integration. | Fewer parts can remove isolation, repair access or thermal accommodation. | B, P |
| DFMA-03 | Challenge board splits, carriers, housings and brackets as architectures. | Alternative function/interface maps and installed BOMs; mounting, wiring, shielding, insulation and cooling requirements traced. | Integration reduces joins but increases scrap exposure and replacement scope. | B, T, P |
| DFMA-04 | Match process choice to quantity, life, material and tolerance. | Compare feasible low-volume and production routes; tooling, setup, cycle, secondary operations, finish and first-article requirements. | Cheapest tooling need not give cheapest accepted units. | B, T |
| DFMA-05 | Establish make-or-buy and custom-part exceptions. | Exact catalog mating drawings for bought items; function-based reason for custom parts; process and supplier assumptions for each. | Catalog parts simplify supply but may impose awkward packaging. | B, T, P |
| DFMA-06 | Standardize only where all applications remain suitable. | Per-use electrical/mechanical ratings, package interfaces and demand; physical instances, unique MPNs, stocked IDs and operations counted separately. | Commonality can add material cost or coupled supply risk. | B, P |

## B. BOM, materials and controlled substitutions

| ID | Review requirement | Required evidence and acceptance basis | Trade-off to expose | Basis |
|---|---|---|---|---|
| DFMA-07 | Make every ordered item unambiguous. | Manufacturer/order code, package, quantity, material/finish, populated/DNP state and revision; reconciliation with assembly drawings and source design. | A shorter description may hide materially different parts. | J, P |
| DFMA-08 | Resolve package and geometry against actual selected parts. | Datasheet land pattern, pin mapping, body/lead envelope, tolerances, height and connector mating model; mark approximations. | Smaller nominal bodies may have less solder/inspection margin. | J, F, P |
| DFMA-09 | State material properties that control manufacture and use. | Alloy/temper, polymer grade, laminate, coating and adhesive identity; relevant heat, electrical, environmental and process requirements. | A nominal material family does not guarantee equivalent performance. | B, T, P |
| DFMA-10 | Qualify alternatives by their controlling functions. | Exact substitute-to-reference comparison and affected-test list; electrical stress, package, soldering, material, interface and thermal differences. | Purchasing flexibility can increase verification and traceability effort. | J, P |
| DFMA-11 | Preserve part and material condition through storage and processing. | Selected-part handling, moisture/storage, shelf life, contamination and ESD requirements; batch/reel/lot controls where consequential. | Inventory pooling saves setup but can increase aging and handling exposure. | J, T, P |
| DFMA-12 | Identify procurement constraints before claiming a cost reduction. | Dated price basis, quantity tier, pack size, MOQ, excess stock, availability, lead time and qualification assumptions. | A low line price may require unusable inventory or a process exception. | J, P |

## C. Bare PCB fabrication

| ID | Review requirement | Required evidence and acceptance basis | Trade-off to expose | Basis |
|---|---|---|---|---|
| DFMA-13 | Specify a reproducible board construction. | Stackup, finished thickness, copper, laminate, finish, mask and necessary impedance/insulation properties; fabricator agreement for intended route. | Less complex stackup may constrain returns, current paths or insulation. | B, J, P |
| DFMA-14 | Match copper and drilled features to the actual process. | Finished trace/space/hole/annular-ring requirements; drill/via types, plating and aspect ratio; tolerance-sensitive features reviewed at process corners. | Reduced vias/layers can increase routing difficulty or thermal resistance. | B, J |
| DFMA-15 | Verify outline, slots, cutouts and edge clearances as manufactured. | Closed fabrication geometry, cutter/drill access, radii, hole-to-edge tolerance and mounted fit; tool-specific limitations. | Smaller outlines may reduce panel yield or make edge features fragile. | J, P |
| DFMA-16 | Preserve insulation under the chosen construction and assembly. | Explicit insulation requirement and material/process authority; copper, slots, contamination, coating and fasteners considered in the finished unit. | A slot or coating changes fabrication, cleaning and inspection burdens. | J, P |
| DFMA-17 | Design the manufacturing panel and separation route deliberately. | Rails, tooling/fiducials, support, separation geometry, panel utilization and component/trace setbacks; feasible depaneling fixture and access. | Aggressive packing can increase handling damage and unusable panel area. | B, J |
| DFMA-18 | Close the fabrication package and critical inspection points. | Revision-matched outputs, drill/layer definitions and drawing notes; dimensional/material acceptance for first articles and recurring lots. | Over-specified controls add cost; omitted controlling features add escape risk. | J, P |

## D. PCB assembly and soldering

| ID | Review requirement | Required evidence and acceptance basis | Trade-off to expose | Basis |
|---|---|---|---|---|
| DFMA-19 | Verify footprints as component and process interfaces. | Datasheet dimensions/pin functions versus footprint; paste/mask/copper and custom lands checked; representative samples for consequential uncertainty. | Dense/custom pads may improve electrical geometry but complicate assembly. | B, J, P |
| DFMA-20 | Reconcile BOM, placement files and assembly preview. | Exact Gerber/BOM/CPL identity; side, datum, rotation and polarity interpretation; flagged placements dispositioned in assembler preview. | A convention difference requires interpretation before calling it a defect. | J, P |
| DFMA-21 | Define a compatible solder/stencil/reflow route. | Component process limits, paste/stencil apertures, thermal mass, profile and hidden-joint inspection plan; selected process evidence. | Heavy copper and large thermal pads can challenge a common reflow window. | B, J |
| DFMA-22 | Account for every nonstandard or manual assembly operation. | THT, hand solder, press fit, staking, potting, high-current leads and fixtures listed with sequence, access and inspection. | Fewer PCB placements can create more final hand work. | B, J, P |
| DFMA-23 | Ensure placement, soldering and inspection access. | Body/lead heights, nozzle clearance, board support, polarity visibility and AOI/X-ray access as applicable; adjacent parts checked. | Minimal spacing can obstruct inspection and selective repair. | B, J |
| DFMA-24 | Plan repair and depaneling without damaging retained functions. | Tool/heat access, allowable rework, stress-sensitive components and cleanliness; evidence for critical joints after handling/rework. | Removable modules help repair but add connectors and retention. | B, J, P |

## E. Enclosure fabrication and finish

| ID | Review requirement | Required evidence and acceptance basis | Trade-off to expose | Basis |
|---|---|---|---|---|
| DFMA-25 | Design the shell for its chosen forming route. | Sheet material/thickness, bend tooling, minimum feasible flanges, bend order, springback assumptions and final datums; shop-specific confirmation. | A four-sided wrap can reduce seams but complicate tooling and corner closure. | B, T, F |
| DFMA-26 | Resolve cutouts and edges relative to bends and tools. | Hole/cut-to-bend references, reliefs, remaining webs, edge condition and distortion tolerance; actual die/punch/laser requirements. | Moving openings away from bends may impair connector access or airflow. | T, F |
| DFMA-27 | Reconcile flat pattern, formed geometry and joins. | Bend allowance method, flat and formed revisions, corner/seam geometry, weld/adhesive/fastener route and fixture datums. | A clean CAD solid can conceal an unbuildable corner or inaccessible join. | B, T, F |
| DFMA-28 | Limit machining and casting to justified features and setups. | Tool reach, stock/blank, fixture grip, setups, internal radii, draft/parting as applicable and post-processing acceptance. | Consolidation may demand expensive tooling or difficult finish machining. | B, T |
| DFMA-29 | Give custom polymer parts a credible intended-volume process. | Material grade, molding draw/draft, walls/ribs, ejection, gates and undercuts; or explicit alternative process and limitations. | Printed fit samples do not establish molded part variation or economics. | B, T, F |
| DFMA-30 | Specify finish with its functional and dimensional consequences. | Preparation, coating/plating/anodizing, mask regions, thickness buildup, corrosion and cosmetic acceptance; grounding and bond lands preserved. | Cosmetic finishes may change fit, electrical contact and repair behavior. | T, F, P |

## F. Location, retention and tolerance

| ID | Review requirement | Required evidence and acceptance basis | Trade-off to expose | Basis |
|---|---|---|---|---|
| DFMA-31 | Trace every required part's attachment and structural load path. | Part → locating interface → retainer → support → chassis; load, access and actual mating geometry including PCB, glass, coil, fan and controls. | A retaining feature can increase part count while eliminating assembly uncertainty. | B, F, P |
| DFMA-32 | Use explicit datums and nonconflicting constraints. | Primary/secondary/tertiary location and compliance; assembly variation and thermal motion; identify slots, tabs, pins and clamping roles. | Tight location improves repeatability but can overconstrain a hot assembly. | B, T, F |
| DFMA-33 | Budget critical fit across parts, joins and processes. | Named critical characteristic, contributors, finish and assembly effects; worst-case or justified statistical model including correlation/mean shift. | Broad tolerances reduce fabrication cost but may increase fixture or adjustment work. | B, F, P |
| DFMA-34 | Verify fastener and thread stacks at tolerance extremes. | Actual grip/engagement, bottoming, insert/parent material, preload or torque method, locking and service cycle requirements. | One screw family can simplify handling yet be unsuitable for every stack. | B, F, P |
| DFMA-35 | Separate location from clamping where beneficial. | Lead-ins/seats/shoulders and retained clamp force; no dependence on loose screw clearance to position consequential interfaces. | Self-locating features can add tool operations or interfere with service. | B, F |
| DFMA-36 | Verify restraint under heat, load and repeated assembly. | Thermal expansion, shock/vibration and intended service/use cycles; joint movement, wear and crack/creep criteria where relevant. | Rigid integration can move stress into glass, solder joints or polymers. | T, F, P |

## G. Thermal, coil and airflow interfaces

| ID | Review requirement | Required evidence and acceptance basis | Trade-off to expose | Basis |
|---|---|---|---|---|
| DFMA-37 | Define the complete heat path for consequential sources. | Source → interface → spreader/sink → air or chassis; actual materials/contact areas and boundary conditions; correlate consequential models physically. | Simplifying supports can interrupt heat flow or electrical separation. | T, P |
| DFMA-38 | Control thermal-interface preparation and application. | TIM identity, bondline/compression/coverage, surfaces, cleaning and dispense/inspection method; tolerance limits and aging conditions. | Thin interfaces may conduct well but be sensitive to flatness and assembly variation. | T, P |
| DFMA-39 | Verify clamping as both a mechanical and thermal operation. | Device/package force limits, load distribution, retention and tolerance stack; contact repeatability before/after service. | Stronger clamping can damage packages or insulating interfaces. | B, P |
| DFMA-40 | Mount coil, ferrite, glass and sensors without untracked functional changes. | Selected part envelopes, locating/preload/clearance stack, heat movement and harness; acceptance tied to actual coupling and sensing requirements. | Integrated carriers reduce parts but may couple alignment, stress and heat. | B, T, P |
| DFMA-41 | Preserve airflow in the fully assembled unit. | Fan/duct/filter/vent and cable obstruction geometry; installed fan behavior, local inlet conditions and contamination/cleaning assumptions. | Smaller housings and hidden joins can restrict cooling or trap grease. | T, P |
| DFMA-42 | Verify assembly variation does not invalidate thermal limits. | Representative interface, airflow and component variation; operating/fault corners and service-restored state; targeted physical correlation. | A narrow nominal margin may demand tighter process controls or a less compact design. | P |

## H. Wiring, connectors and electrical interfaces

| ID | Review requirement | Required evidence and acceptance basis | Trade-off to expose | Basis |
|---|---|---|---|---|
| DFMA-43 | Treat off-board electrical modules and harnesses as manufactured parts. | Complete installed filter/inlet/module/harness BOM, mounting, wiring drawing, termination and inspection requirements. | Moving a function off-board does not eliminate its cost or assembly operations. | B, P |
| DFMA-44 | Select usable, retained connector mating interfaces. | Both halves and terminals, keying, lock, cable exit, clearances and hand/tool reach; actual plug/unplug sequence. | Lower connector count may make final assembly or servicing awkward. | B, F, P |
| DFMA-45 | Define repeatable wire and high-current terminations. | Gauge/material, cut/strip, crimp/solder/torque process, tool and terminal identity; current/temperature and joint acceptance evidence. | Commodity terminals reduce custom work but impose packaging and tooling requirements. | B, P |
| DFMA-46 | Control harness routing, support and strain. | Length/tolerance, bend radius, strain relief, abrasion, heat and moving-part separation; installation clips and service slack. | Extra slack eases assembly but can obstruct airflow or change EMI coupling. | B, F, P |
| DFMA-47 | Preserve electrical reference, shielding and filter topology through assembly. | Harness geometry and return/bond paths; source/load separation and defined shield termination; sensitivity and installed EMI evidence. | Fewer clips or connectors can worsen coupling or return-path repeatability. | P |
| DFMA-48 | Make protective bonds deliberate and inspectable. | Selected construction's protective-earth/bond requirements, joint/finish treatment, retention and continuity verification after assembly/service. | Cosmetic coating and removable panels can complicate continuity and inspection. | T, P |

## I. Assembly sequence and error prevention

| ID | Review requirement | Required evidence and acceptance basis | Trade-off to expose | Basis |
|---|---|---|---|---|
| DFMA-49 | Demonstrate a feasible whole-product build sequence. | Numbered operations including orientation changes, wire routing, hidden joints, cure, tests and closures; no cyclic insertion dependencies. | A lower part count can still produce a slower assembly sequence. | B, F |
| DFMA-50 | Reduce handling and orientation difficulty where worthwhile. | Part presentation, grasp/reach, symmetry, lead-ins and visibility; observed handling trials for troublesome parts. | Added asymmetric/keyed features may increase fabrication complexity. | B, F |
| DFMA-51 | Demonstrate actual tool and hand access. | Driver/nozzle/probe/hand envelopes at each operation, extraction directions and fixture clearance, including bottom-only visible screws/rear service access. | Concealed screws improve appearance but can add inversions or trapped parts. | B, F, P |
| DFMA-52 | Minimize loose hardware and repeated operation families deliberately. | Physical fastener count, screw/tool families, captive features, torque changes and joining sequence; retention remains adequate. | Snap fits/integral tabs can restrict repair and require tighter tooling. | B, T, F |
| DFMA-53 | Prevent or detect consequential assembly mistakes. | Keying/polarity/labeling, mix-up prevention, sequence constraints and inspection for reversed, omitted or misrouted items; verify the mechanism. | Visual labels are cheaper than keying but depend more on operators. | B, J, F |
| DFMA-54 | Control adhesive, sealant and cure operations. | Compound/lot, storage, surface preparation, dose/location, fixture, open/cure time and inspection; downstream solder/finish compatibility. | Replacing screws with bonding can add cure delay and destructive service. | T, P |

## J. Environmental construction and user interfaces

| ID | Review requirement | Required evidence and acceptance basis | Trade-off to expose | Basis |
|---|---|---|---|---|
| DFMA-55 | Define actual liquid-entry and cleaning exposure paths. | Seams, vents, controls, connectors and service openings inventoried; seal, drain or controlled path plus exposure requirement and test. | Fewer seams may help ingress but make heat removal or cleaning harder. | T, F, P |
| DFMA-56 | Specify seal compression, seating and restoration. | Compound, land/gland, finish, tolerance endpoints, clamp distribution and replaceability; installed hot/aged/service-restored checks. | More preload can damage parts; hidden seal contact prevents inspection. | T, P |
| DFMA-57 | Verify knob, probe and sensor interfaces as complete mechanisms. | Location/retention, actuation travel, stops, contact, signal/harness, thermal movement and assembly access; selected part geometry. | A single carrier can simplify mounting but link otherwise independent tolerances. | B, T, F, P |
| DFMA-58 | Preserve required electrical/mechanical separation after final assembly. | Fasteners, harness, swarf, thermal movement and service disturbances considered; final construction tested against authoritative requirements. | Dense integration can demand tighter assembly controls and inspection. | J, P |
| DFMA-59 | Specify compatible materials and exposed finishes. | Dissimilar materials, cleaners, heat, grease, moisture, corrosion, wear and touch/cosmetic requirements; evidence for consequential combinations. | One finish or adhesive for all parts can fail a specific environment. | T, P |
| DFMA-60 | Maintain cleanable, durable surfaces and accessible contamination control. | Edge/seam/trap geometry, intended cleaning method and replaceable filters/seals; assembly residues and retained debris inspection. | Smooth bonded closures aid cleaning but can prevent economical repair. | T, F, P |

## K. Inspection, test and manufacturing evidence

| ID | Review requirement | Required evidence and acceptance basis | Trade-off to expose | Basis |
|---|---|---|---|---|
| DFMA-61 | Identify critical characteristics and their actual measurement methods. | Feature/requirement list linked to incoming, in-process and final checks; instrument/fixture access, uncertainty and acceptance source. | Excess inspection costs time; unmeasurable requirements cannot control escapes. | B, F, P |
| DFMA-62 | Build test access into the assembled product and sequence. | Probe/connect/flash/functional-test route, fixture contacts, temporary configurations and restoring closures; feasible at intended rate. | Test points and fixtures add cost but may reduce fault localization and scrap. | B, J, P |
| DFMA-63 | Separate process screens from product qualification. | Test-purpose map, coverage and known escape modes; tests appropriate to production variation distinguished from operating/fault qualification. | A short screen cannot prove every lifetime or fault requirement. | P |
| DFMA-64 | Demonstrate representative assembly and first-article fit. | Real part/fixture trials, timed operations, interference/defect records and disposition; identify hand adjustments that would recur. | One carefully hand-fitted unit does not demonstrate repeatable manufacture. | B, F, P |
| DFMA-65 | Establish recurring process quality from suitable data. | First-pass yield, defect classification, rework/scrap and dimensional/process variation at matched conditions; stability before capability claims. | Narrowing tolerances without evidence may raise cost without improving yield. | B, F, P |
| DFMA-66 | Keep released drawings, BOM, process and evidence synchronized. | Hash/revision manifest, source-of-truth fields, approved changes/substitutions and affected inspection/retest; traceability for consequential lots. | Additional document copies increase drift unless responsibility is clear. | J, F, P |

## L. Cost comparison, service and improvement acceptance

| ID | Review requirement | Required evidence and acceptance basis | Trade-off to expose | Basis |
|---|---|---|---|---|
| DFMA-67 | Compare cost per accepted complete unit on a matched basis. | Same quantity, process, geography and denominator; parts, fabrication, assembly, testing, scrap/rework, harness/cooling and logistics; uncertainty. | Line-price or part-count reductions may lose after yield and assembly effects. | B, P |
| DFMA-68 | Separate recurring savings, one-time costs and accounting effects. | Tooling/NRE/fixture/qualification and changeover tracked separately; avoided expenditure versus capacity freed versus allocated overhead. | Faster assembly does not automatically reduce cash cost at low volume. | B, T, P |
| DFMA-69 | Demonstrate service through the intended opening. | Extraction and replacement sequence for actual service items, retained wiring, access and sacrificial consumables; rear-door/preference conformance explicit. | A smaller opening or integrated assembly may enlarge replacement cost. | B, F, P |
| DFMA-70 | Restore function and protection after repair. | Reassembly location, torque, thermal interface, seals/bonds and required retest; access and error prevention demonstrated across intended cycles. | Easy opening is insufficient if sealing or thermal performance cannot be restored. | T, P |
| DFMA-71 | Require a supported combined improvement against the fixed benchmark. | Exact comparator/candidate identities, matched requirement/cost/evidence basis; meaningful economic/simplicity gain and technical gain; uncertainty and regressions. | Different nondominating options may remain rather than forcing one weighted winner. | P |
| DFMA-72 | Close stage-critical evidence before adopting a candidate. | PASS/FAIL/UNVERIFIED gate decisions with evidence and scope; consequential unknowns have owners and closure checks; no score overrides a critical floor. | Digital preference can precede qualification; supplier/physical evidence may overturn it. | P |

## Gates and comparison discipline

These are original review conventions. Define the applicable gate and acceptance authority before grading, rather than deciding what matters after seeing a score.

1. **Identity and interface gate:** exact compatible revisions and complete required interfaces; no verified required-part collision, absent attachment or impossible build step in the proposed sample.
2. **Functional construction gate:** electrical, insulation, protective bonds, thermal paths, controls and exposure requirements supported for the specific proposed operating stage. Record FAIL separately from UNVERIFIED.
3. **Process and package gate:** manufacturing outputs, selected parts, process routes, critical dimensions, assembly instructions and inspection criteria agree; consequential supplier assumptions have suitable evidence for the claimed stage.
4. **Repeatability gate:** representative build and process evidence establish the intended rate/variation/quality; qualification and production screens have explicit roles.
5. **Improvement gate:** the candidate is cheaper or meaningfully simpler and technically better under the agreed benchmark rule, while preserving every required floor and reporting other trade-offs.

A gate does not prohibit a narrower learning sample whose scope avoids the unresolved function; document that scope. Passing a mechanical fit sample does not release the complete cooker.

Compare operations and physical quantities before ordinal scores. Useful metrics are accepted-unit cost, setup/tooling cost, assembly time distribution, orientation/tool changes, manually touched joints, first-pass yield, rework minutes, inspection access, qualified stocked items, service extraction time and restoration success. Count physical parts, placements, PCB footprints, procurement lines and CAD solids separately. Freeze applicability and update both sides if a measurement method changes.

For cost, use recorded total batch consumption and manufacturing costs divided by accepted output, or a component model with an explicit yield/rework allowance. **Do not divide by yield again if scrap has already entered the accepted-output denominator.** Amortized tooling belongs against an explicit expected quantity; report it separately from the unit cash cost. Saved minutes may release capacity without changing payroll or overhead. Record both effects without double counting.

## Review record template

| Field | Content |
|---|---|
| Design and stage | Exact PCB/schematic/BOM/enclosure/harness/process revisions; intended sample/use and quantity |
| Criterion and function | DFMA ID, affected interface and reason it matters |
| Requirement | Acceptance value or condition, authority and operating/process corner |
| Evidence | File/page, date, input identity, measurement/setup and uncertainty; evidence class |
| Decision | 0/1/2/3/U/NA; gate PASS/FAIL/UNVERIFIED if relevant; consequence |
| Comparison | Benchmark and candidate metrics under the same basis; saved/added parts and operations |
| Trade-off | Requirements preserved; noncritical regressions; supplier or model assumptions |
| Closure | Owner, smallest check that resolves the uncertainty, trigger for retest |

## Temper hypotheses to explore after the benchmark exists

These directions derive from Temper's existing strategy and mechanical preferences. They have not been selected or graded here.

| Hypothesis | Potential gain | What would disprove or limit it | Criteria |
|---|---|---|---|
| Self-locating enclosure joints and fewer fastener/tool families | Less alignment and handling work; more repeatable fit | Overconstraint, bend/finish variation, inadequate retention or impaired teardown | 25–27, 31–36, 49–53, 69–70 |
| Integrated coil/sensor/glass support | Fewer carriers/joins and a shorter assembly sequence | Lost electrical separation, thermal movement, coupling accuracy or repairability | 02–03, 31–40, 57, 69–70 |
| A deliberate four-sided cover and rear service path | Fewer seams and coherent access | Unformable corners, inaccessible tools, trapped wiring, poor cooling or seals | 25–27, 41, 49–56, 69 |
| PCBA process rationalization | Fewer special operations and less ambiguous placement | Loss of power/insulation/thermal margins or increased hidden-joint defects | 13–24, 58, 62–68 |
| Installed inlet/filter/harness redesign | Less custom wiring and more repeatable EMI/assembly behavior | Cost shifted to final assembly, unsuitable bonds, heat or unqualified coupling | 43–48, 61–68 |
| Accessible and repeatable heat-sink clamp/TIM stack | Faster installation and more consistent contact | Package stress, insulating-interface failure, hot variation or service drift | 31–39, 42, 49–54, 70 |

Maintain preference conformance separately from manufacturability: the four-sided cover, rear service door, concealed screws, catalog sourcing and proposed physical-part reduction remain product goals, even when another option is buildable. The earlier suggestion of roughly 3 mm walls is a starting hypothesis; material, geometry, process and load determine the justified thickness.
