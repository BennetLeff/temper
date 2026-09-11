# Zapote validation objective

The product outcome is a cooker board that passes a broad, demanding suite of
Rust engineering validations. The agent places/routes in KiCad through the
working Python adapter. Replacing that adapter with Rust is later work, not a
prerequisite for checking or correcting the board.

The user's scale ambition is two to three orders of magnitude more validation
than conventional CAD checking: 100–1,000 times the breadth/depth of a defined
comparison workload. This is a target, not an achieved or verified claim about
KiCad or Altium. A numerical comparison requires a named version/configuration,
the same board/scenarios and a defined counting unit. Do not invent a vendor
test count, equate test cases with independent rules, or delay useful board
work while researching a marketing comparison.

## What the suite must establish

Evaluate the actual saved board, source circuit and applicable operating
requirements. Existing Rust validators and their tests are the starting point.
Copy needed code into Zapote packages; extend coverage where real cooker
requirements or observed failure modes expose gaps. The Rust rule computes the
engineering verdict; Python only transports inputs, edits through KiCad, and
returns results. KiCad's own checks remain complementary independent evidence.

The coverage inventory must consider these families. They are inventory
categories, not claims that every check already exists or is applicable:

| Family | Examples of board-specific obligations |
|---|---|
| Source/circuit identity | Exact parts, pin-to-pad mapping, net partitions, intentional NCs, no omitted required parts |
| Geometry and manufacturing | Clearance, courtyards, containment, drill/annular-ring rules, mask, assembly access and actual fabricator limits |
| Connectivity and return paths | Physical copper connectivity, required ground returns, via spans, zone connectivity, unintended shorts |
| Power and component stress | Trace/via current capacity, neckdowns, dissipation, voltage/current ratings and adopted operating corners |
| Isolation and protection | Authored domain boundaries, creepage/clearance, slots, isolation components, protection interconnections |
| Thermal | Device/board temperature margins under declared models, copper/thermal vias, neighboring heat sources |
| Switching and signal integrity | Critical loops, gate paths, decoupling, return discontinuities, coupling, antenna/clock/sensitive-signal constraints |
| Control and system interfaces | Reset/boot configuration, firmware pin correspondence, required sensing/control/protection connections |

Classify each assertion as exact structural validation, bounded calculation,
simulation/model-based evidence, heuristic, or physical-test requirement.
Preserve model assumptions and uncertainty. A passing heuristic or simulation
does not become proof of measured RF/thermal/hardware behavior.

## Rule inventory and test corpus

P1 records one compact coverage manifest with: requirement/fault ID, actual
Rust owner/entry point, relevant source inputs, applicability, units/thresholds
and authority, evidence class, status, tests/oracles, and unresolved gaps.
P3 provides target-board context; existing donor rule names/counts are
reconciled against actual registration and execution rather than file presence.

For each required rule, retain meaningful positive cases, near-boundary cases,
and at least one intentional violation that must be detected. Add interaction,
property-based and adversarial cases where the domain warrants them. Include
real board values and non-orthogonal geometry where needed. Independently
verify expected results; donor equality and self-consistency are insufficient.

Track these separately:

- Production engineering rules and distinct requirements/fault classes covered.
- Rule applications on actual board objects, nets, layers and operating corners.
- Validator regression/property test cases and sampled runs.
- Distinct injected faults detected and missed, false positives, and unresolved
  coverage/input gaps.

Repeated seeds, renamed assertions and many pad pairs can increase executions
without adding independent fault coverage. Every generated case must have a
defined property/oracle. Preserve discovered counterexamples as regressions.

## Agent feedback and final acceptance

Start by wiring the existing Rust checks to the existing KiCad editing path and
running a full-board baseline on a scratch candidate. Give the agent actionable
rule/object/location findings and let it correct the board. Small control
fixtures qualify the connection; they do not replace the full-board workload.
The MCU/assembly work remains a tractable construction slice of this objective.

Freeze the adopted suite and inputs for each attempt. Iteratively add justified
coverage between attempts, keeping versions and earlier outcomes. Do not drop
rules or relax requirements to make a candidate pass. Distinguish pass, fail,
not applicable with a reason, and indeterminate/not run. Missing required input,
an unimplemented required rule, or a broken checker prevents full acceptance.

Fast applicable checks may run after edits. Run the complete adopted suite and
independent native KiCad checks on the final saved candidate, including costly
checks omitted from the interactive loop. Tie reports to board/source/suite
hashes. A green validator test corpus proves software behavior on those cases;
it is not itself a passing board result. Report residual physical-test work and
uncovered requirements separately from the checked board's result.

## First delivery

Deliver the current-board coverage inventory/baseline, a working agent–KiCad–
Rust feedback loop, and one evidenced agent correction. Then expand copied
rules and fault cases in priority order and work toward passing the complete
adopted board suite. Do not make Python removal, a new IPC client, a custom PCB
writer, or complete package cleanup a dependency of this delivery.

## Required physical stackup gate for new unit acceptance

Before accepting a new or changed unit PCB, run the reusable Rust gate on its saved native board:

```sh
CARGO_TARGET_DIR=/private/tmp/zapote-rtd-target cargo run --manifest-path zapote/Cargo.toml -p zapote-harness --example stackup_check -- path/to/board.kicad_pcb
```

`DRC.BOARD.STACKUP` checks positive copper/dielectric thickness, declared-versus-stackup copper order, positive intervening dielectrics and the nominal total including mask. Current-sense automatically runs it in its normal acceptance path against SHA-256-bound board bytes; older RTD records were not retroactively requalified. This check does not replace fabrication qualification or 3D inspection. The [current-sense repair](current-sense/evidence/stackup-fix/README.md) preserves the real defect and red/green proof.
