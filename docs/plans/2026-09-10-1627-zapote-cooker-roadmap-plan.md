# Zapote: from validated units to the complete cooker
Created: 2026-09-10

Milestone 2 standalone RTD design/layout is accepted; see [the acceptance record](../../zapote/rtd/unit/ACCEPTANCE.md). Physical qualification and procurement are distinct remaining obligations. Standalone current sensing has also reached its digital milestone with recorded qualification gaps; see [its acceptance record](../../zapote/current-sense/ACCEPTANCE.md). Standalone voltage sensing has reached its digital milestone with qualification gaps; thermal Rev B and the standalone interlock now also have construction artifacts and acceptance records. The next separate construction unit is isolated gate drive.

This is the high-level delivery order. Detail only the next milestone as we
approach it. Milestone-specific plans sit underneath this roadmap; the rows
alone are scope commitments, not implementation-ready instructions or completion claims.

Updated scope, 2026-09-10: **build and accept each unit separately first, with
one goal per unit. Integrate the accepted units afterward under a separate
goal.** The complete routed cooker remains the overall destination, not the
acceptance condition for an individual unit. Fabrication and physical cooker
verification follow as separate deliverables.

## Delivery order

Each electrical unit has its own Atopile-derived schematic, placed/routed KiCad
board artifact, Rust validation evidence and explicit interface contract. Reuse
existing circuit design and accepted work. A unit closes on its own engineering
requirements; routing it into the full cooker is deferred. Rows containing
several units describe sequencing groups, not permission to combine their goals.

| Order | Deliverable | What must be true before moving on |
|---|---|---|
| 1 | **Buck, then MCU: separate unit goals and the working Zapote loop** | Reconcile existing standalone outputs; each has source identity, placement/routing, actual Rust feedback and unit acceptance. Carry applicable lessons forward. |
| 2 | **[Standalone pan-temperature sensing and hardware fault output](2026-09-10-1633-zapote-rtd-sensing-milestone-plan.md)** | RTD probe interface, reference, filtering and local fault circuitry pass unit checks. Power, SPI, fault and reference connections terminate at explicit unit boundaries. |
| 3 | **Current sensing, voltage sensing, thermal sensing, then safety interlock: separate goals** | Each unit is independently placed/routed and checked against declared input/output conditions. The interlock has explicit fault, watchdog, latch/reset and shutdown contracts. |
| 4 | **Isolated gate-drive unit** | Driver, local supply/decoupling and gate interfaces have standalone layout and checked isolation, gate-loop and shutdown constraints. |
| 5 | **Power-path units, each separately** | Detail power entry, auxiliary supply, bus discharge and switching/resonant units as bounded goals before execution. Accept each unit's stress, return, thermal and interface obligations. |
| 6 | **Remaining product units, each separately** | Cooling/fan and programming/UI units have checked interfaces and mechanical constraints; reconcile any remaining product functions before integration. |
| 7 | **Integration goal: complete cooker board** | Compose the accepted units, place/route cross-unit connections, and resolve mechanical, supply, noise, isolation and firmware interactions. Rerun unit regressions and whole-board checks. |
| 8 | **Full-board validation and fabrication release** | The complete adopted Rust suite and native KiCad checks pass on the frozen board; required indeterminate checks are resolved. BOM and release outputs match it. |
| 9 | **Assembled and physically verified cooker** | Staged hardware tests measure sensing, protection, heating and thermal behavior; required corrective revisions are closed. |

## Progress recorded 2026-09-23

The [parallel roadmap plan](2026-09-23-zapote-remaining-roadmap-parallel-plan.md)
produced source-bound digital readiness gates for the auxiliary, discharge,
inverter, cooling and programming/UI units. The [integration matrix](../../zapote/integration/matrix.tsv)
is **BLOCKED** by unresolved voltage-sense, return, stop, fault and native
endpoint interfaces. The [release inventory](../../zapote/release/release-manifest.tsv)
is **INCOMPLETE**, and its [assembled test protocol](../../zapote/release/physical-test-protocol.md)
is entirely **NOT_RUN**. These readiness artifacts organize the remaining
construction and evidence; they do not close orders 5–9 or replace the
standalone and physical acceptance conditions above.

This is a construction order. Record expected supply/isolation domains, mechanical
envelopes and inter-unit interfaces during unit work. Final whole-board placement
and cross-unit routing belong to integration. Revisit affected units when an
interface changes; rerun their checks.
The order does not imply energizing an incomplete power or protection chain.

## What grows with every milestone

Every milestone has three outputs:

- **A reusable cooker unit:** updated Atopile source, generated KiCad artifacts
  and a standalone placement/routing candidate with source identity preserved.
- **More useful validation:** reuse existing Temper Rust rules/tests in focused
  Zapote packages, supply their real inputs, and add missing checks for the new
  section. Keep a coverage/gap record and prove checks reject representative
  faults. Run unit regressions now and integrated regressions during integration.
- **Reusable engineering memory:** retain findings, successful corrections and
  reviewed lessons; select and deliver relevant lessons to the next agent.
  Record actual reuse and outcomes. Executable requirements belong in validators.

The agent chooses placement and routing. Keep the working Python/KiCad adapter
and host; new engineering rule logic belongs in Rust. Validator extraction and
feedback integration serve board construction throughout these milestones.
Replacing Python or rebuilding a placer/router is outside this roadmap.

The validation ambition remains 100–1,000 times broader testing than ordinary
CAD checks. Track meaningful rule coverage, evaluated board assertions and
fault detection separately from raw test totals. A comparative multiplier needs
a defined baseline; the immediate gate is the board meeting its engineering
requirements. See [the validation contract](../../zapote/VALIDATION.md).

Existing full-board defects do not block standalone unit acceptance unless they
expose a defect in the unit's own contract. Preserve existing integration work
and evidence for the later integration goal. Never present a unit pass as a
whole-board pass. Milestone 8 closes full-board release obligations; physical
verification belongs in milestone 9.

## How we add detail

Before starting each milestone, make one bounded execution plan specifying its
interfaces, owned standalone artifacts, required validations, unit exit
criteria and evidence handoff. Assign Luna agents independent work within that
milestone; one coordinator accepts the combined result. Advance through the
milestones in order, carrying forward unresolved obligations explicitly.

Reconcile existing owner outputs rather than restarting accepted buck/MCU work.
The standalone voltage-sensing digital construction milestone is complete; see [acceptance](../../zapote/voltage-sense/ACCEPTANCE.md). Thermal Rev B and the standalone interlock have reached their digital construction milestones with explicit qualification gaps. The next construction goal is the isolated gate-drive unit. Earlier composition plans and
integrated RTD attempts are retained as historical work, not current goal gates.

Existing milestone 1 plans:

- [Coordinator and acceptance](2026-09-10-1322-feat-mcu-harness-milestone-plan.md)
- [Atopile-to-MCU construction and Rust validation](2026-09-10-1322-feat-atopile-mcu-flow-plan.md)
- [Engineering memory](2026-09-10-1322-feat-engineering-agent-memory-plan.md)
- [Buck/MCU composition](2026-09-10-1322-feat-buck-mcu-composition-plan.md)

Scope is grounded in the current [cooker composition](../../elec/src/main.ato)
and [circuit modules](../../elec/src/modules.ato). Follow the settled
[Zapote architecture](../../zapote/ARCHITECTURE.md) for the harness boundary.
Dates, component changes, exact thresholds and task budgets belong in the later
milestone plans after their inputs are checked.
