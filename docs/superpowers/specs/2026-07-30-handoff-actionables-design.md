# Handoff actionables integration design

## Goal

Carry forward the verified, actionable work from the 2026-07-30 handoff in an
isolated worktree based exactly on `origin/main`, without importing stale board
measurements or asserting clause-level conclusions from an unavailable current
standard text.

## Scope and decisions

- Land the reusable HV↔SELV pairwise creepage measurement tool and its tests.
- Land the source-side removal of the unused mains-ZCD optocoupler U3 and its
  dedicated circuit. The CT/comparator-based current-ZCD path used for ZVS is
  explicitly out of scope and must remain unchanged.
- Record the standards finding as a provenance-qualified status: IEC's current
  catalog identifies IEC 60335-1:2020 as Edition 6.0, superseding Edition 5.2,
  but the paid current text is not available in this environment. No current
  clause mapping will be presented as verified without that text.
- Reconcile the KiCad board only after rebuilding the electrical artifact from
  the resulting source. A prior board-wide resync branch is evidence, not an
  input; its edits are not applied wholesale because the board has moved since
  that branch was created.

## Integration order

1. Add the measurement tool and tests.
2. Apply the U3 source deletion, resolving the shared tool file by retaining
   the identical tool implementation and adding the deletion's source changes.
3. Rebuild the electrical netlist and compare source/netlist/board identities.
4. Update the board through the repository's documented source-to-board flow,
   then run the copper-net and safety checks against the fresh artifacts.

## Verification

The result is acceptable only if the targeted measurement tests pass, the
electrical source compiles, the rebuilt netlist is internally consistent, and
the board consistency/safety checks either pass or report a specifically
attributed remaining board limitation. Every reported count is tied to this
worktree's final commit and regenerated inputs.

## Out of scope

Remote PR merges are not performed from this worktree when GitHub is
unreachable. The current-edition standard is not reconstructed from the
withdrawn Edition 5.2 text. No PD2/PD3 insulation redesign is implemented
until the current standard and the board/source reconciliation are both
settled.
