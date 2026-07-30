---
title: "Compound engineering for safety closure: make each claim carry its own source, falsifier, and owner decision"
date: "2026-07-30"
category: workflow-issues
module: safety-closure
problem_type: workflow_issue
component: development_workflow
severity: critical
applies_when:
  - "a safety conclusion spans Atopile source, generated netlists, KiCad board geometry, test gates, and design documentation"
  - "a passing logical or construction gate could be mistaken for proof of physical isolation or manufacturability"
  - "a numeric margin is being cited without naming the operating envelope and fault model that produced it"
  - "a board-changing fix would invalidate a DRC ceiling, netlist, placement result, or evidence record"
  - "several individually reasonable work items must converge before a hardware decision is safe to close"
tags:
  - compound-engineering
  - safety-closure
  - evidence-chain
  - measurement-provenance
  - falsifier
  - source-of-truth
  - physical-isolation
  - requirements-triage
  - design-decision
---

# Compound engineering for safety closure

## Context

Safety closure is not one test. It is a convergence problem across several
artifacts that answer different questions:

```text
Atopile source ──make netlist──> generated connectivity ──> domain gate
                                      │
KiCad board geometry ────────────────┼───────────────────> physical gates
                                      │
requirements tests ──────────────────┴───────────────────> safety findings

electrical arithmetic ──> operating-envelope claim
DRC measurement ────────> ceiling/provenance claim
documentation ──────────> human decision record
```

The dangerous failure is not necessarily a wrong calculation. It is a correct
calculation or a green gate being promoted to a stronger claim than it
actually measures. A source can describe one board while a generated netlist
describes another. A domain partition can be perfect while copper still has no
physical mains-to-SELV barrier. A nominal resistor-fault margin can be correct
at one operating voltage while being cited as if it covered the absolute bus
limit. A DRC ceiling can have valid provenance while still hiding substantial
design debt below its budget.

The 2026-07-30 safety-closure pass made these boundaries explicit in
`docs/evidence/2026-07-30-safety-closure-evidence.md`. It was deliberately a
measurement and decision-recording pass: it changed no board geometry, no
Atopile source, no netlist, no ceiling value, and no safety threshold.

This document records the method as a reusable compound-engineering pattern.
It is not a safety approval and it does not substitute for the owner decisions
listed in the evidence record.

## The pattern

Treat a safety closure as a set of small, coupled claims. For every claim,
record five things before interpreting the result:

1. **Artifact** — the exact source or generated object being measured.
2. **Commit** — the tree that produced the measurement.
3. **Question** — what the check actually establishes.
4. **Falsifier** — the concrete condition that must make the check fail.
5. **Owner decision** — what still requires an electrical or board-design
   decision rather than more automation.

The engineering work is compound because the defenses reinforce one another:

| Defense | It establishes | It does not establish |
|---|---|---|
| Base-commit assertion | The measurement started from the named tree | That the tree is safe or current forever |
| Fresh netlist build | The source can produce the generated connectivity being tested | That the hand-maintained PCB has the same physical geometry |
| Domain partition gate | Declared HV/SELV net relationships and isolator/protective-impedance rules | Creepage, clearance, keepouts, routing, or manufacturability |
| Physical keepout gate | The board contains the named physical barrier and its required geometry | Correct circuit topology or complete package-level clearance |
| REQ-SAFE-01 test | The current board's measured clearance/creepage findings | That all failures share one fix or that a lower threshold is justified |
| Independent arithmetic | A margin under named voltage, tolerances, and fault model | The standard interpretation, component qualification, or every operating case |
| DRC provenance gate | The ceiling describes the checked-in board hash | That the ceiling is a good engineering target or that debt is gone |
| Evidence document | What was measured and what remains open | Approval to choose an architecture or alter the board |

Do not merge these rows into a single “safety gate passed” sentence. The
separation is the protection.

## The closure loop

### 1. Orient before measuring

Start in a fresh worktree and assert the exact base:

```bash
git worktree add -b codex/<topic> ../<topic> origin/main
cd ../<topic>
scripts/assert-base.sh origin/main
```

If the dispatch names a commit rather than `origin/main`, assert that commit.
An evidence number without the tree it was measured on is not a current
measurement; it is an unattributed observation.

Inspect the nearest subsystem instructions and the existing evidence or
solution records before running a script. In this repository, that includes
the board-change/DCR-ceiling rule, the generated-netlist workflow, and the
prohibition on using the shared stash.

### 2. Rebuild the source-derived artifact

For electrical changes or safety analysis, regenerate the netlist first:

```bash
make netlist
```

Then run the domain gate against that generated result:

```bash
uv run --no-sync --package temper-placer \
  python scripts/check_domain_partition.py
```

The observed result in this pass was 0 domain crossings, 0 isolator-barrier
breaches, and 0 protective-impedance-chain defects across 54 declared nets,
10 declared isolators, and 2 chains. That is meaningful construction evidence.
It is not physical isolation evidence, because the gate does not inspect the
board's copper spacing or keepout geometry.

### 3. Run the physical gate independently

Check the board, not the source representation:

```bash
uv run --no-sync --package temper-placer \
  python scripts/check_isolation_keepout.py --board pcb/temper.kicad_pcb
```

The observed board had 169 footprints, 521 pads, and 2,482 copper items but
zero keepout zones. The required
`MAINS_SELV_ISOLATION_BARRIER` was absent, so the physical gate failed. This
failure is not contradicted by the passing domain gate; it is the reason both
gates exist.

When the physical gate fails, preserve the failure until one of the following
is actually designed and verified:

- a real PD3 / 12.6 mm board barrier for the current unsealed construction; or
- a genuinely sealed PD2 / 8.0 mm compartment, including thermal, cable,
  connector, assembly, and manufacturing arguments.

An architecture label in a document is not a sealed compartment. A named
keepout that is absent from the board is not a keepout.

### 4. Classify requirement failures before fixing them

Run the requirement test and keep the raw categories:

```bash
uv run --no-sync --package temper-placer pytest \
  packages/temper-placer/tests/requirements/safety/test_clearance.py::\
  TestClearanceIntegration::test_temper_board_clearance_compliance -q
```

The current measurement was 123 REQ-SAFE-01 clearance/creepage violations
across 86 pairs, with 11 intra-footprint records and six unclassified
proximity findings. The first pair was `C17↔R32` at 0.905 mm against 12.6 mm
reinforced creepage. The six unclassified findings were also retained with
their measured nearest-HV distances rather than folded into the headline:

| Component | Distance | HV neighbour |
|---|---:|---|
| R42 | 8.570 mm | R5 |
| R34 | 8.645 mm | R5 |
| R40 | 8.705 mm | R5 |
| R45 | 9.681 mm | R5 |
| C10 | 10.420 mm | C25 |
| R64 | 10.661 mm | U2 |

Separate at least these classes before proposing a patch:

- movable component-placement findings;
- package or footprint geometry that cannot be solved by translation;
- missing classification or source-to-board identity;
- architecture-dependent findings;
- routing or copper geometry findings;
- intra-footprint findings requiring a package or part decision.

Do not lower the requirement, add an exemption, or report a smaller count
because some findings are inconvenient to move. A classification is useful
only when it leads to the appropriate owner and fix surface.

### 5. Reconcile identity before approving placement

For a suspicious component, trace the same item through source, generated
netlist, and PCB. In this pass, `tank.c_tank3` reconciled as follows:

```text
Atopile tank.c_tank3
  -> generated designator C27
  -> C27 pin 1: SW_NODE
  -> C27 pin 2: tank.c_tank1-p2, shared with C25/C26/R30
  -> PCB C27 with matching sheetpath, footprint, and nets
```

Identity consistency did not make the placement valid. C27 was staged at
`(20.0, 272.75)`; the board edge ended near y=254 mm and the courtyard
extended to y=284.25 mm. It is outside the board and therefore not a
manufacturable placement.

The correct conclusion is “identity reconciled; placement remains open,” not
“the tank capacitor is done.”

### 6. Bound every electrical number

For a safety margin, write the equation and the envelope next to the result.
The ADC divider uses three 169 kΩ ±1% top resistors and a 10 kΩ ±1% bottom
resistor. Under the deliberately conservative two-top-resistors-short fault,
the remaining minimum resistance is:

```text
Rfault = (169 kΩ × 0.99) + (10 kΩ × 0.99) = 177.21 kΩ
I170V  = 170 V / 177.21 kΩ = 959.314 µA
margin = 1.35 mA / 959.314 µA = 1.407×
```

That supports the approximately 1.4× statement at the declared +170 V
half-bus. It does not support the same statement at the 400 V absolute full
bus, whose implied 200 V half-bus gives 1.196× under the same arithmetic.

The 1.35 mA limit itself is still a documented source claim (`0.75 mA/kW ×
1.8 kW`) with a standard-source caveat. The calculation also does not prove
the ADC input behaviour, resistor safety qualification, or the interpretation
of protective impedance. Mark those as unverified rather than allowing the
arithmetic to launder them into approval.

The pass also exposed a fault-survival defect in the source metadata. The ADC
top resistors originally declared 0.1 W while the same RC1206 family used by
the comparator divider declared 0.25 W. Under the source's own two-top-short
fault, the surviving ADC top resistor dissipates about 152.4 mW: 152% of the
declared rating, but 61% of the family rating. The 0.1 W value was therefore
not a cosmetic BOM discrepancy; it described a part that could fail in the
fault case the three-resistor protective-impedance construction exists to
survive. PR #503 corrected all three source fields to 0.25 W, regenerated the
netlist, and reran the domain gate. The arithmetic and its operating-envelope
caveat remain unchanged.

### 7. Treat DRC ceilings as provenance, not a quality target

For every board-changing PR, verify the ceiling against the board hash and
remeasure using the repository's documented tool and sample procedure:

```bash
uv run --no-sync python scripts/check_measurement_provenance.py
uv run --no-sync --package temper-placer \
  python scripts/ci_check_drc.py --backend kicad-cli
uv run --no-sync python scripts/check_drc_ceiling_approval.py \
  --base-ref origin/main
```

The current evidence record found fresh provenance and no unapproved ceiling
rise. A checker run observed 866/875 errors and 680/680 warnings; a direct
`run_drc()` sample reported 865 errors and 680 warnings. Preserve both facts
when they come from different invocations; do not manufacture one “canonical”
number by deleting the observed variation.

The ceiling's remaining slack is not evidence that the design is healthy. It
is a budget. In particular, 680 warnings exactly at the warning ceiling and a
large error count represent unresolved debt even though the provenance gate
passes. If a board change raises any ceiling, attribute the delta and include
the required `Ceiling-Approval:` trailer. If the cause is unknown, stop.

### 8. The enforcement split is a fabrication-safety failure

The PD2/PD3 disagreement is stronger than documentation drift because the
three enforcement points govern different layers of the built artifact:

| Enforcement point | Value on the current mainline | What it does |
|---|---:|---|
| `requirements/validators/clearance.py` | 12.6 mm, PD3 | Reports REQ-SAFE-01 findings |
| `pcb/temper.kicad.dru` | 8.0 mm, PD2 | KiCad's fabrication-board DRC rule |
| `check_isolation_keepout.py::MIN_BARRIER_WIDTH_MM` | 8.0 mm, PD2 | Physical keepout validation |

That permits a board to pass both artifact-governing checks at 8.0 mm while
the requirements layer reports it against 12.6 mm. The result is the worst
state: the project has concluded PD3 applies, but the physical gates enforce
PD2; the red requirement count cannot drive the artifact toward the governing
standard, and a green fabrication result can be misread as safety closure.

This is not solved by replacing `8.0` with `12.6` in three files. The number
is a consequence of the physical configuration:

- **PD3 path:** retain the unsealed, vented IP20 construction and retarget
  the KiCad DRC rule, keepout width, and board slot/placement geometry to
  12.6 mm. Existing components and the current floorplan will then produce
  real, actionable failures that must be designed out.
- **PD2 path:** earn a sealed electronics compartment with a credible
  pollution, thermal, cable, connector, assembly, and manufacturing argument;
  then keep the 8.0 mm artifact gates and retarget the reporting layer to the
  same PD2 construction assumption.

Until one physical configuration is approved, do not land a unilateral
retarget. The invariant to enforce after the decision is not merely “three
constants are equal”; it is “the selected physical configuration, the
requirements matrix, the generated `.kicad_dru`, and the keepout gate all
describe the same insulation requirement.”

### 9. Publish the evidence with the unresolved decisions visible

An evidence record should end with a short owner-decision table, not a green
headline. The current decision surface is:

1. Select PD2 sealed-compartment architecture or PD3 / 12.6 mm spacing for
   the actual construction.
2. Approve a real C27 placement and rerun board, netlist, keepout, DRC, and
   provenance gates in the same board-changing PR.
3. Decide whether the protective-impedance claim is cited only at +170 V or
   across a higher bus envelope. The ADC top-resistor metadata correction is
   landed in PR #503; it does not resolve the standard interpretation or
   operating-envelope question.
4. Resolve the 123 REQ-SAFE-01 findings through placement, package,
   classification, routing, and architecture work; never by making the gate
   less discriminating.

The document must state whether it changed source or geometry. “No board or
source changes” is a useful result when the purpose was evidence collection:
it explains why a DRC ceiling edit was not smuggled into a measurement PR and
why the unresolved physical failure remains visible.

## What went wrong in the old workflow

The recurring defect was claim drift rather than one isolated logic bug:

- a self-updating assertion checked a count derived from the same list it was
  supposed to describe, so prose could say the wrong number while tests stayed
  green;
- a grep sweep under-counted rotation sites because its patterns did not
  cover every spelling or inverse-convention helper;
- a 90-degree invariance argument was true for one board and was incorrectly
  used to exempt a general helper from the lint;
- stale compiled extensions produced plausible but false “pre-existing” test
  failures;
- a logical source/netlist gate could pass while the physical board lacked an
  isolation keepout;
- the requirements layer could report PD3 while KiCad and the physical
  keepout gate enforced PD2, allowing the artifact to pass the weaker rule;
- the ADC divider's 0.1 W metadata could pass normal-operation arithmetic while
  failing the two-top-short fault that justified the redundancy;
- a nominal ADC calculation could be repeated as an absolute-bus claim after
  its voltage assumption had disappeared;
- a staged component could be identity-consistent yet still sit outside the
  manufacturable board outline;
- a DRC summary could be treated as current without checking its content hash.

Each local defense in the compound pattern addresses one of these failure
modes. None of them can replace the others, because each observes a different
layer of the system.

## Implementation checklist

Use this sequence for the next actual closure change:

```text
[ ] Choose and record the isolation architecture and applicable spacing.
[ ] Assert the exact base in a fresh worktree.
[ ] Make the smallest source/board change for one decision.
[ ] Rebuild generated netlist and verify source-to-netlist-to-PCB identity.
[ ] Run the domain partition gate.
[ ] Run the physical keepout and board geometry gates.
[ ] Run REQ-SAFE-01 and classify every remaining finding.
[ ] Re-run DRC with the documented flags/sample count.
[ ] Refresh drc_ceiling.json in the same PR if the board changed.
[ ] Run provenance and Ceiling-Approval checks.
[ ] Rebuild/check all affected Rust extensions before interpreting tests.
[ ] Record exact counts, commit, dirty state, tool versions, and assumptions.
[ ] State the falsifier and the remaining owner decision in the PR body.
[ ] Push, inspect CI, and merge only when the unresolved items are explicit.
```

The final line is intentionally not “all gates green.” A truthful handoff can
contain a red safety requirement when the red result is the measured design
state and the PR does not pretend to have solved it.

## What this method closes, and what it leaves open

This method closes the evidence gap: future readers can tell which tree was
measured, which artifact was inspected, what a passing gate means, and why a
remaining failure is still actionable. It also prevents a docs-only evidence
pass from silently changing a board, a ceiling, or a safety threshold.

It does not decide whether PD2 or PD3 is the correct product architecture. It
does not approve the 1.35 mA standard interpretation, place C27, route the
board, or resolve the REQ-SAFE-01 findings. The ADC metadata correction is
landed, but it does not by itself qualify the protective-impedance standard
interpretation or make the 1.4× figure valid outside its stated voltage
envelope.
Those are design decisions and implementation tasks that must follow the
owner-decision sequence above.

## Related records

- `docs/evidence/2026-07-30-safety-closure-evidence.md` — measured values and
  current open decisions.
- `docs/superpowers/specs/2026-07-30-safety-closure-evidence-design.md` —
  approved scope for the evidence pass.
- PR #503 — ADC top-resistor metadata correction and regenerated-netlist
  validation.
- `docs/solutions/best-practices/falsify-the-fix-before-believing-it-2026-07-29.md`
  — require a motivating failure before trusting a new gate.
- `docs/solutions/best-practices/citation-loop-validates-a-model-against-itself-2026-07-27.md`
  — trace claims to independent evidence instead of counting copied values as
  corroboration.
- `docs/solutions/workflow-issues/resolving-conflicting-sources-safety-critical-schematic-2026-07-14.md`
  — resolve safety-critical source conflicts with an independent check.
