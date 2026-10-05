# Product judgment for Temper

Temper should earn trust through predictable cooking control, understandable feedback, easy cleaning, durable interfaces, and practical repair. These are proposed priorities for this cooker, not aesthetic preferences attributed to its owner or requirements imposed by MIT. Use the course methods below to decide what to build and which evidence would change that decision.

## Make quality observable

Translate “premium,” “precise,” “robust,” and “manufacturable” into behaviors before choosing details. A cook can tell the difference between a selected temperature and a measured one, stop heating deliberately, understand a sensor fault, remove food from a seam, and repeat a setting with wet hands. An assembler can locate a board, reach its fasteners, route its harness, and verify the result without improvisation. A repairer can replace a fan or sensor without destroying unrelated parts. Each proposed behavior needs an observation or measurement; a rendering cannot supply it.

This is an application of 2.007's requirements-to-alternatives process and 2.70's function/ergonomics/environment/analysis/risk method; the particular cooking examples are our engineering interpretation. See [product synthesis](product-manufacturing/synthesis.md#product-taste-as-an-engineering-decision).

## Prefer mechanisms with margin

Choose a design that tolerates real variation over one that works only at nominal geometry. Give glass, coil, sensor, board, and heat sink explicit locating features and error budgets. Separate the tolerance needed to assemble parts from the accuracy needed while hot and loaded. A larger hole may permit assembly while sacrificing location. Extra constraints may force a part to bend when screws are tightened or materials expand.

For a consequence-sensitive interface, establish bounds first. Root-sum-square and Monte Carlo methods can help predict yield or rank alternatives, but require justified assumptions about distributions, drift, and correlation. An assumed population with no failures does not prove all admissible corners pass. See [mechanical principles 2–7](mechanical/synthesis.md#source-derived-design-principles) and [variation methods](product-manufacturing/synthesis.md#tolerances-fixtures-and-variation).

## Design the product across its interfaces

The electrical power path, heat path, load path, insulation boundary, spill path, and assembly sequence meet at the same physical parts. A heat sink changes enclosure volume, airflow, fastening, and parasitic capacitance. A coil support changes mechanical stiffness, sensor contact, magnetic surroundings, and insulation. A smooth cover may complicate cleaning or service if it hides an uncontrolled gap or requires destructive bonding.

Draw those paths together before optimizing a component in isolation. Preserve useful separation between dirty cooling air and sensitive areas only when the actual construction supports it. Do not assume that a sealed-looking CAD volume establishes an insulation environment. MIT supplies the coupled mechanical and electrical reasoning; supplier construction and applicable product requirements determine acceptance. See [mechanical transfer](mechanical/synthesis.md#temper-transfer-hypotheses--engineering-inference-not-course-claims), [layout/thermal/EMI methods](electronics/synthesis.md#principles-transferable-to-temper), and [transcript explanations](video/README.md#findings-relevant-to-temper).

## Simplify operations without deleting necessary function

Compare designs by custom operations, fixtures, adjustments, inspection, purchased-part availability, assembly errors, and service effort—not just part count. A separate inexpensive wear piece can be better than a complex monolithic component. A fastening scheme can be visually quiet while remaining reachable and replaceable. Conversely, removing screws in favor of adhesive or snaps may transfer cost and risk into cure control, inspection, shock, heat, or repair.

Choose the process for the intended quantity and design maturity. A sheet prototype does not establish molded-part economics; a supplier's generic capability table does not establish capability for this part, material, finish, and tool. Get quotes and process samples for decisions that depend on them. These distinctions follow the 2.008 quality/cost/rate/flexibility framework and 2.875 assembly reasoning. See [manufacturing synthesis](product-manufacturing/synthesis.md#manufacturing-and-assembly-gates).

## Buy evidence that resolves the next decision

Use a full-size mockup for reach and feedback, a tolerance fixture for a critical mechanism, a bend coupon for sheet development, and an instrumented module for a heat or switching question. State what each experiment predicts, which conditions it covers, and what result would reject the design. Test edge conditions that could defeat its mechanism: sensor contact loss despite pan presence, obstructed airflow, rail decay, a load transition, or service reassembly.

Keep evidence distinct: source inspection, dimensional computation, analytical prediction, simulation, and physical measurement. A geometry check cannot establish stiffness; connectivity cannot establish interruption time; a successful nominal demonstration cannot establish endurance or production yield. Qualify the design separately from screening defects in each manufactured unit. This applies MIT's error budgets, critical-module prototyping, and measurement-driven quality methods to Temper.

## A compact decision record

For a consequential choice, record the following in a few rows rather than creating a new process document for every edit:

| Field | What makes it useful |
|---|---|
| Decision and current artifact | Exact revision and interface being decided |
| User/function requirement | Observable outcome, source, and any unresolved assumption |
| Options and tradeoff | Plausible choices; why the proposed one fits current priorities |
| Failure mechanism | How the choice could fail in assembly, use, fault, or service |
| Evidence and limit | What was actually inspected/calculated/tested; what it cannot establish |
| Next discriminating test | Condition, method, requirement-derived criterion, responsible role |

Apply [product taste](../../../skills/temper-product-taste/SKILL.md) to product choices, [mechanical review](../../../skills/temper-mechanical-review/SKILL.md) to interfaces and mechanisms, [PCB/power review](../../../skills/temper-pcb-power-review/SKILL.md) to circuits and layout, and [manufacturing review](../../../skills/temper-manufacturing-review/SKILL.md) to build and production decisions. The [Temper review](application/review.md) demonstrates their use on the current candidate and both enclosure packages.
