# Zapote: from validated units to the complete cooker
Created: 2026-09-10

This is the high-level delivery order. Detail only the next milestone as we
approach it. Milestone-specific plans sit underneath this roadmap; the rows
alone are scope commitments, not implementation-ready instructions or completion claims.

The immediate finish line is **one complete, routed induction-cooker board
that passes the adopted Rust engineering validation suite**, with a reproducible
source-to-board record. Fabrication and physical cooker verification follow as
separate deliverables.

## Delivery order

Each electrical unit joins the same growing full-board candidate. Reuse the
existing circuit design and buck work, reconciling them against current sources.
An isolated block export can be a working artifact; the milestone closes on its
integration into the cooker.

| Order | Deliverable | What must be true before moving on |
|---|---|---|
| 1 | **Integrated buck + MCU, with a working Zapote loop** | Atopile-derived control section is placed/routed in the intended board context. The agent receives real Rust findings through the working KiCad adapter, fixes findings, and reruns checks. Existing full-board validator coverage and gaps are recorded; applicable buck lessons reach the MCU agent. |
| 2 | **[Pan-temperature sensing and its hardware fault output](2026-09-10-1633-zapote-rtd-sensing-milestone-plan.md)** | RTD interface, connector, reference, filtering and independent fault circuitry are integrated with MCU, supplies and safety interfaces. Source, layout and required engineering checks pass for the section. |
| 3 | **Current/voltage/thermal sensing and the safety interlock** | Sensing, watchdog, fault combination, latch/reset and shutdown interfaces form a checked protection chain. Required behavior and remaining physical tests are explicit. |
| 4 | **Isolated gate drive** | Drivers, local supplies/decoupling and gate connections are placed/routed against the defined power-stage geometry. Isolation, gate-loop and shutdown obligations have applicable checks and recorded results. |
| 5 | **Complete power path** | Power entry, auxiliary supply, bus discharge, half-bridge and resonant tank/coil connections are integrated. Supply, switching, return-path, component-stress and thermal constraints are checked across section boundaries. |
| 6 | **Complete product integration** | Cooling/fan circuitry, heatsink/coil/enclosure fit, connectors, programming/UI interfaces and firmware pin/function contracts are reconciled with the assembled board. No necessary product function is left as an unnamed future block. |
| 7 | **Full-board validation and fabrication release** | Routing is complete; the full adopted Rust suite and independent native KiCad checks run on the frozen final board. Mandatory failures and required indeterminate checks are resolved. BOM, fabrication/assembly outputs and bring-up instructions match that exact revision. |
| 8 | **Assembled and physically verified cooker** | Fabricated hardware is inspected and brought up under a separately detailed staged procedure. Firmware operation, sensing, protection, heating and thermal behavior have measured results; required corrective revisions are closed. |

This is a construction order. Define the whole-board outline/stackup, power and
isolation domains, major component envelopes, connector locations and inter-unit
interfaces in milestone 1. Reserve space for later sections before routing early
ones. Revisit affected sections when an interface changes; rerun their checks.
The order does not imply energizing an incomplete power or protection chain.

## What grows with every milestone

Every milestone has three outputs:

- **More of the real cooker:** updated Atopile source, generated KiCad artifacts
  and an integrated placement/routing candidate with source identity preserved.
- **More useful validation:** reuse existing Temper Rust rules/tests in focused
  Zapote packages, supply their real inputs, and add missing checks for the new
  section. Keep a coverage/gap record and prove checks reject representative
  faults. Run integrated regression checks as each section lands.
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

During incremental construction, explicitly tracked existing full-board defects
may remain outside the section being accepted. Do not introduce unexplained
regressions or present a section pass as a whole-board pass. Milestone 7 closes
all mandatory full-board obligations; physical-only evidence belongs in milestone 8.

## How we add detail

Before starting each milestone, make one bounded execution plan specifying its
interfaces, owned source/layout region, required validations, integration exit
criteria and evidence handoff. Assign Luna agents independent work within that
milestone; one coordinator accepts the combined result. Advance through the
milestones in order, carrying forward unresolved obligations explicitly.

Start by reconciling milestone 1's existing owner outputs against its plans,
then detail only what remains. Do not restart completed buck work or infer a
completed milestone from an individual owner's summary. Detail milestone 2
using the accepted control-section interfaces next.

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
