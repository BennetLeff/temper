# Reference reconciliation and CI DRC baseline handoff

<!-- provenance: commit=bab2a75aa154b7e82c5187d8ff461bd915a7aca1 dirty=true -->

**Date:** 2026-07-30
**Scope:** PR #498 explicit placement-reference reconciliation.

## Reference result

`packages/temper-placer/configs/temper_constraints.references.yaml` is the
source-backed map consumed before direct CP-SAT or place→route solving. It
uses production-board `Sheetpath` identity and records the source export used
for the comparison. Only aliases whose targets are live parsed component
references are enabled. Live designator collisions and missing source
instances remain explicitly unresolved, so the existing fail-closed validator
stops before a placement candidate is generated.

The current map resolves exact identities including `U_MCU -> U26`,
`U_GATE/U_GD -> U6`, `C_BOOT -> C17`, `D_BOOT -> U7`, and the source-backed
decoupler/current-sense references. It deliberately does not map the legacy
conceptual `Q1/Q2/D1/D2` names: those names are already live designators for
different source instances on the production board. Automatic loop extraction
currently returns no production loop, while the small design-input export
declares only a schematic-level `commutation_loop`; no loop alias is invented.

## CI DRC result

The same PR head passes the targeted routing regression locally with KiCad
10.0.4. GitHub Actions on the Linux CI image produced a stable five-run
router-output total of `1537, 1537, 1538, 1537, 1537`, while the existing
local-derived ceiling is `1440`. The run also held `shorting_items=75` and
`unconnected_items=388` within their existing ceilings. This is an
environment/tool baseline mismatch, not a reason to silently raise a ceiling.

The regression workflow is pinned to the immutable manifest digest of the
current CI image and records the `kicad-cli` version in the job log. A new
ceiling may only be considered after the pinned image is remeasured and the
Linux-vs-macOS delta is attributed with a `Ceiling-Approval:` trailer.

## Physical blockers

The isolation keepout remains a hardware-layout blocker: the current board
has no `MAINS_SELV_ISOLATION_BARRIER` zone and its HV/SELV footprints are
interleaved, so adding an arbitrary strip would cut through real components or
copper. The prescribed next design action is a human floorplan/placement
decision followed by the required same-PR DRC ceiling remeasurement; this
software change adds no keepout geometry.

The separate requirements gate still reports 115 REQ-SAFE-01 violations and
six components inside the enforced 12.6mm margin. These are board/footprint
and routing debt, not validator settings to weaken. See
[`2026-07-30-current-board-clearance-debt.md`](2026-07-30-current-board-clearance-debt.md)
and [`2026-07-28-isolation-keepout.md`](2026-07-28-isolation-keepout.md).
