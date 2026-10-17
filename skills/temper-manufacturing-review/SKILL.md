---
name: temper-manufacturing-review
description: Review whether a Temper mechanical or electronic design can be fabricated, assembled, inspected, and repeated at its intended volume; use for manufacturing-readiness and design-for-assembly decisions.
---

# Manufacturing review for Temper

Review the actual revision and intended build volume. A CAD model, DRC result, or successful prototype answers only part of the manufacturing question. Match the depth of review to the decision and maturity of the design.

1. State the function, expected volume, candidate material and process, finish, supplier assumptions, and what has been physically demonstrated. Compare candidate processes on quality, cost, rate, flexibility, tooling lead time, and likely variation. Keep prototype and production assumptions distinct. Ask the relevant fabricator or assembler to validate process-specific geometry and capability rather than importing example lecture dimensions.
2. Walk the physical build sequence with the intended tools and part presentation. Check visibility, reach, grasp, lead-ins, self-location, orientation errors, wiring route and inspection, access to fasteners, test placement, temporary disassembly, and repair. Part-count reduction is useful only when function, reliability, and service are preserved.
3. Identify the few assembly-level characteristics that control function. For each, show the locating strategy and datum/tolerance chain through parts, joints, fasteners, and thermal or use-condition movement. Use a worst-case stack when a limit must hold for every conforming combination; use statistical estimates only with defensible distribution, centering, and correlation assumptions. Bring in a tolerance specialist where the stack is consequential or uncertain.
4. Check procurement and build identity: current BOM/revision, exact manufacturer part, package/footprint and mating features, approved substitute criteria, material/finish specification, supplier source, and lot/build traceability where relevant. A schematic symbol or nominal package name is insufficient proof of a purchasable, correctly fitting item.
5. For each critical characteristic, record the requirement and its source, inspection or test method, measurement fixture/calibration, sampling stage, acceptance rule, observed result, and trace to revision/lot. Distinguish a production screen (detecting defects in each build) from qualification (demonstrating the design and process across stresses, lots, and use conditions). Track process average and spread over real builds; specification limits and control limits serve different purposes. Do not invent universal numerical pass limits or claim capability from one hand-built unit.
6. Report blockers, evidence gaps, and proposed next build or measurement with a responsible owner. Where a process or assembly change affects a previously tested feature, identify the retest point.

State which next stage the evidence supports: a mockup, controlled engineering prototype, learning pilot, or production release. When volume or process changes, revisit tooling, material, fixtures, inspection, and qualification; a small-batch result does not automatically transfer to a production tool or supplier. Name the evidence and responsible role for the next stage decision.

The linked MIT lectures teach general manufacturing and assembly methods. They do not set appliance safety, electrical insulation, surface-temperature, material-rating, or certification limits. Derive those from applicable standards, manufacturer data, supplier process evidence, and qualified review. Read [evidence notes](references/evidence.md) when citing the method or selecting a process-specific check.
