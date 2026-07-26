---
title: "Design capacity is a resource that runs out silently — two protection circuits fully designed with nowhere to connect"
date: "2026-07-26"
category: best-practices
module: pcb-hardware-design
problem_type: best_practice
component: hardware_design
severity: high
applies_when:
  - "adding a new fault source to an existing fault-aggregation tree (OR-gate fan-in, mux select lines, interrupt controller inputs)"
  - "a design doc instructs surveying for a spare input before wiring one"
  - "a second engineer is about to re-run a capacity survey another engineer already ran on the same resource"
  - "an input on a shared aggregation IC 'looks free' because it's tied to a fixed logic level"
tags:
  - fan-in-budget
  - capacity-planning
  - fault-aggregation
  - sn74hc4075
  - resource-exhaustion
  - shared-ic-capacity
  - design-time-tracking
---

# Design capacity is a resource that runs out silently

## Context

OCP-02 and UVL-02 are both fully designed circuits on this project —
component values derived, tolerances analysed, both correctly implementing
their respective protection functions. **Neither can connect to the fault
latch.** Every SET-path input on both `SN74HC4075` triple-OR-gate packages
(`fault_or`, `fault_any_or`, `elec/src/modules.ato:2344-2345`) is occupied,
dead, or reaches the wrong logic:

| Gate | Inputs | Status |
|---|---|---|
| `fault_or` gate 1 (`A1/B1/C1→Y1`) | OCP-01, OVP-01, thermal | full |
| `fault_or` gate 2 (`A2/B2/C2→Y2`) | Y1 feedback, watchdog (`latch.Y4`), `runaway_cut` | full |
| `fault_or` gate 3 (`A3/B3/C3→Y3`) | all three tied GND | free inputs, but **`Y3` drives nothing anywhere in the module** — a dead end, not spare capacity |
| `fault_any_or` gate 1 (`A1/B1/C1→Y1`) | `fault_or.Y2`, `rtd_hw_fault`, and now `coil_thermal` (THM-02, added `d99c88e2` same day) | full — this is the gate whose `Y1` feeds `latch.A1`, the actual SET input |
| `fault_any_or` gate 2 (`A2/B2/C2→Y2`) | `C2` is GND-tied and *looks* free | it computes the **RESET qualifier** (`Y2 → latch.A3`); wiring a fault here blocks reset without ever tripping the latch — worse than not wiring it |
| `fault_any_or` gate 3 (`A3/B3/C3/Y3`) | entirely unreferenced | unused, but structurally identical to `fault_or` gate 3: no path into the SET aggregation without another OR stage |

Two independent surveys reached this same conclusion on the same day, from
two different starting points. The first (OCP-02, per
`docs/hardware/OCP02_DESIGN.md`'s own instruction to survey before wiring)
found no usable input and left OCP-02's comparator output at a test point.
The second (UVL-02) **had to re-run the entire survey from scratch**,
explicitly noting in the source comment
(`elec/src/modules.ato:2486-2490`) that its first pass was done "against a
stale worktree that still had `fault_any_or.C1` grounded and wrongly
concluded it was free" — see
`docs/solutions/best-practices/a-measurement-carries-its-commit-2026-07-26.md`
for that half of the story. Once re-run against the current tree (which now
includes THM-02, landed by `d99c88e2` between the two surveys), the second
survey reached the identical structural conclusion the first had already
established: no spare SET-path input exists on either package.

The lesson is not that the second survey should have been faster — it's that
**the second survey should not have had to happen at all.** The information
"every SET-path input is spoken for" was true after the OCP-02 survey and
remained true (modulo one more consumer taking the last nominally-free slot)
through UVL-02's design. Nothing tracked that fact as a project-level
resource; each engineer rediscovered it by re-enumerating every pin on both
packages.

## Guidance

1. **Fan-in capacity on a shared aggregation IC is a budget, not a per-use
   lookup.** The moment a design decision consumes an input on `fault_or` or
   `fault_any_or`, that consumption should be recorded somewhere a *later*
   protection-circuit design will see before it starts its own component
   design — not discovered by re-surveying every pin from scratch.
2. **Track the budget when a protection circuit is *designed*, not when it is
   *wired*.** OCP-02 and UVL-02 were both fully derived — values computed,
   tolerances checked, topology chosen — before either one discovered it had
   nowhere to connect. If the fan-in budget had been checked at design
   kickoff instead of at wiring time, the capacity constraint would have
   shaped the design (or triggered the "add a part" decision) before the
   component-value work was sunk cost.
3. **"Tied to GND" and "unreferenced" are not the same as "spare."** Three of
   the six gate-slots surveyed above have free electrical inputs; none of the
   three is usable — one drives nothing (`fault_or.Y3`), one computes a
   different function entirely (`fault_any_or`'s reset qualifier), and one
   needs an additional OR stage to reach the aggregation at all. A capacity
   budget needs to record *reachability to the SET path*, not just pin
   occupancy, or it will keep reporting false positives exactly like both
   surveys initially risked.
4. **When a design doc says "survey for a spare input before wiring" (as
   `OCP02_DESIGN.md` does), that survey's result belongs in a place the next
   designer reads before repeating it** — a capacity ledger next to the
   aggregation IC's instantiation, updated by whichever change consumes the
   last slot, not just a comment on the one gate that used it.
5. **When the budget is provably exhausted, say so as a decision point, not a
   workaround.** Both circuits correctly stopped at "bring the fault output
   to a test point" rather than wiring into a dead or wrong-function input —
   the right response to exhausted capacity is to surface the human decision
   it requires (add a part, restructure the tree, accept a documented gap),
   not to force a connection.

## Where this is being mechanized

A **module-instantiation completeness gate** is in flight, checking that
every module with a `.fault.line` (or equivalent required output) either
reaches a fault-aggregation SET input or terminates at an explicit,
documented sink (a test point, with a comment explaining why). That check
would have flagged OCP-02's and UVL-02's unconnected fault lines
automatically; it does not yet track the *complementary* fact this incident
is really about — that the aggregation ICs' own input budget is exhausted,
which is the fan-in-capacity ledger described above and does not currently
exist as a checked artifact.

## Why This Matters

The cost here was not incorrect design — both circuits are correctly
designed and their component values are sound. The cost was **duplicated
discovery work on a resource whose state should have been knowable in
seconds.** The second survey re-derived, from first principles, a fact the
first survey had already fully established (three gates, six slots, all
either occupied or unreachable), and would have gotten the wrong answer on
its first pass had it not independently caught its own stale-tree error. A
tracked capacity budget turns "is there room for one more fault source" into
a lookup; without one, it stays an enumeration exercise that has to be redone
by every subsequent design, with every redo carrying the same risk of
checking against a tree that has already moved.

## When to Apply

- Before starting component-value design for any new protection or fault
  circuit that must connect to a shared aggregation resource (OR-tree,
  interrupt controller, mux) — check whether capacity exists *before*
  sinking design effort into values that may have nowhere to connect.
- When a design doc instructs "survey for a spare X before wiring" — treat
  the survey's result as a fact to record for the next designer, not just a
  one-time gate for the current change.
- When a resource "looks free" (tied to a fixed level, unreferenced) — verify
  it actually reaches the aggregation point that matters, not just that the
  electrical pin is unconsumed.
- When two engineers independently need to answer "is there capacity left,"
  especially across a time gap — that is the trigger to build the tracked
  ledger rather than accept a second from-scratch survey as normal.

## Examples

```
# The two surveys' conclusions, side by side -- structurally identical,
# reached independently, one day apart:

OCP-02 survey (elec/src/modules.ato:2442-2478):
  fault_or gate 3:      free electrically, Y3 has no consumer -- dead end
  fault_any_or gate 1:  full (this is the one that reaches latch.A1)
  fault_any_or gate 2:  C2 free-looking, but it's the RESET qualifier -- unusable
  -> conclusion: no usable SET-path input anywhere

UVL-02 survey (elec/src/modules.ato:2486-2511), re-run after catching a
stale-tree false positive on its first pass:
  fault_or gate 3:      unchanged -- still a dead end
  fault_any_or gate 1:  now ALSO holds coil_thermal (THM-02) -- still full
  fault_any_or gate 2:  unchanged -- still the reset qualifier, still unusable
  fault_any_or gate 3:  fully unreferenced -- same "no path to SET" problem
  -> conclusion: identical to OCP-02's, rediscovered from scratch
```

```
# The ledger this incident argues for (sketch, next to the IC instantiation)
fault_or:
  gate1.Y1: CONSUMED by [ocp1, ovp1, thermal] -> feeds fault_or.A2
  gate2.Y2: CONSUMED by [Y1-feedback, watchdog, runaway_cut] -> feeds fault_any_or.A1
  gate3.Y3: UNREACHABLE (no consumer; needs new OR stage to matter)
fault_any_or:
  gate1.Y1: CONSUMED by [fault_or.Y2, rtd_hw_fault, coil_thermal] -> feeds latch.A1 (SET)
  gate2.Y2: CONSUMED, different function (reset qualifier) -> feeds latch.A3
  gate3.Y3: UNREACHABLE (fully unreferenced; needs new OR stage)
SET-PATH CAPACITY: 0 of 6 nominal input-slots usable. Next fault source
  requires either a new OR stage or a third aggregation IC -- flag at design
  kickoff, not at wiring time.
```

## Related

- `docs/solutions/best-practices/a-measurement-carries-its-commit-2026-07-26.md`
  — the stale-worktree half of the UVL-02 incident: its first survey pass
  wrongly concluded `fault_any_or.C1` was free because it ran against a tree
  that predated THM-02.
- `docs/solutions/best-practices/net-name-is-a-claim-not-an-authority-2026-07-26.md`
  and `docs/solutions/best-practices/claimed-isolation-vs-actual-connectivity-2026-07-26.md`
  — sibling hardware lessons from the same day where a label or a partial
  check stood in for tracing the actual structure.
- `docs/hardware/OCP02_DESIGN.md`, `docs/hardware/UVL02_DESIGN.md` §7 — the
  design documents recording both surveys and the human decision (rework the
  OR tree vs. add a third aggregation IC) they defer.
- `elec/src/modules.ato:2344-2345, 2440-2527` — the `SN74HC4075` instantiation
  and both surveys' comments in full.
