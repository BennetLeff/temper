---
title: Lie-proof a green number before believing it — silent drops make every metric a lie, and integration peels truth in layers
date: "2026-07-11"
category: best-practices
module: temper_placer
problem_type: best_practice
component: development_workflow
severity: high
applies_when:
  - "a pipeline reports a good number (100% placed, below-human DRC, 'zone containment enforced') and you are about to trust it"
  - "two independently-built subsystems have never actually run end-to-end together"
  - "a constraint / rule / fix is present in code but you have not confirmed it takes effect at the point it must"
  - "a solver returns INFEASIBLE / UNSAT and you are tempted to treat it as a design verdict"
  - "you have just stated an aggregate root-cause claim ('~885, one cause') from eyeballing rather than measurement"
tags:
  - map-vs-territory
  - fail-closed
  - verification
  - integration
  - silent-failure
  - diagnosis
  - unsat-core
  - self-skepticism
---

# Lie-proof a green number before believing it

## Context

The temper "finish the board" arc began from a settled-looking diagnosis:
routing was stuck at 83.3%, blamed on the router. Every celebrated metric
in the project — 33/33 placed, below-human DRC, "zone containment
enforced," 83.3% routed — turned out to be standing on constraints that
were **not actually being applied**. Only 1 of ~29 constraints reached
the solver (the `constraints:` block was never parsed), the placement
zones were empty (an inverted-rectangle convention bug), and 17 more
constraint refs were dropping silently. The placement everyone had
optimized and measured was a placement with almost no constraints.

The generalizable lesson is not any single fix. It is a working
discipline: **do not believe a green number until you have made the
system loud enough that it cannot lie to you** — and then keep applying
that same skepticism to your own diagnosis, not just the code's output.

## Guidance

Four rules, each earned by a distinct failure in this arc:

1. **A fix that exists in code is not a fix that works.** Confirm effect
   by measurement, at the exact point in the pipeline where it can take
   effect. (The arc's origin: a "route signals last" sort existed twice —
   a no-op copy in the adapter and a real one in the pipeline — and the
   real one was already applied and not helping. Reading the code would
   never have revealed this; only running it did.)

2. **Make silent drops loud (fail-closed).** A constraint / rule / edge
   whose operand resolves to nothing must **raise**, not skip. A
   silently-dropped constraint is the "looks applied but isn't" failure
   mode, and it makes every downstream green number a lie. Add the guard
   at the resolution boundary — it is the cheapest place to catch drift,
   and it surfaces the *entire* gap at once (in this arc, a fail-loud ref
   validator surfaced 17 dropping refs, not the 11 found by log-grep).

3. **INFEASIBLE / UNSAT is only a design verdict if every constraint in
   the core is itself correctly specified.** A solver's proof is sound,
   but it proves unsatisfiability *given the encoding*. Before treating
   it as "the design is over-constrained," verify each constraint in the
   minimal UNSAT core individually. In this arc the "provable power-stage
   geometry conflict" dissolved into two more encoding bugs (an adjacency
   metric ignored; a phantom loop reference) — relaxing the innocent
   design margin would have masked them.

4. **Turn the skepticism on your own claims, especially aggregates.**
   "~885 violations, one root cause" is exactly the eyeballed aggregate
   that, if wrong, sends you building a cathedral for two-thirds of the
   problem. Decomposing it by measurement showed only 27% were true
   overlap; 73% were marginal (median 0.107mm gap vs a 0.2mm rule) —
   pointing at a one-parameter grid-resolution fix, not a router rewrite.

Corollary — **integration peels truth in layers, in order.** When two
subsystems have never run together, wiring them is not "making it work" —
it is a truth-extraction tool. Each fix surfaces the next layer's real
problem: 83.3% hid seven seam bugs → fixing them hid an INFEASIBLE →
fixing the adjacency-metric revealed 100% routing → 100% routing revealed
a DRC trace-geometry problem that had never been visible because the board
had never routed to completion on a real placement. Expect this, and
treat each "solved" as "what did this just make visible?"

## Why This Matters

Sophistication accumulates faster than it is connected to a measured,
end-to-end outcome. A project can have a CP-SAT placer that beats a human,
a router, physics gates, and 22k lines of verification — all validated in
isolation — while the one artifact the project exists for (a complete,
placed-and-routed, DRC-clean board) has never been produced end to end,
because the two core halves never ran together. The gap hides precisely
because each component works alone. A machine that says "this is
over-constrained, here is the exact conflict" is worth infinitely more
than one that says "33/33, all good" while silently dropping 28 of 29
constraints. The discipline is what converts the first into the second.

Safety stakes make it concrete: "zone containment enforced" was asserted
while the mains-input containment constraint (`J_AC` → the real ref was
`J_AC_IN`) was one of the silent drops. A green safety claim intersecting
a silent drop is the exact place this discipline earns its cost.

## When to Apply

- Before treating any pipeline metric as sign-off — ask "what would make
  this number a lie, and have I ruled it out by running the tool?"
- The first time two independently-built subsystems are wired together —
  budget for peeling, not for "done."
- Whenever a solver returns INFEASIBLE — verify the core constraints
  before concluding the design (not the encoding) is at fault.
- Right after stating an aggregate root-cause claim — decompose it by
  measurement before it becomes the premise of a large effort.
- Before "a substantial architecture effort," run the cheap levers first
  (shed-before-cathedral): is a geometry-aware mode simply off? Can a
  post-process pass clear most of it? Is it one parameter (grid size)?

## Examples

Fail-closed guard (the class fix that surfaces the whole gap at once):

```python
# BEFORE: unresolved ref silently drops — constraint becomes a no-op,
# every downstream "constraint satisfied" number is now a lie.
def _resolve_refs(name, components, ctx):
    if name in components:
        return [name]
    if name in ctx.zones:
        return ctx.zone_components.get(name, [])
    return []                      # <-- silent drop

# AFTER: validate at the resolution boundary; raise on drift.
def validate_constraint_refs(constraints, component_refs, zone_names,
                             loop_names, on_unresolved="raise"):
    unresolved = collect_unresolved(constraints, component_refs,
                                    zone_names, loop_names)
    if unresolved and on_unresolved == "raise":
        raise UnresolvedConstraintRefsError(unresolved)  # fail-closed
    return unresolved
```

Verify-the-core before believing INFEASIBLE (measured, not reasoned):

```
solve(full set)                        -> INFEASIBLE   (looks like a design conflict)
verify each core constraint individually:
  adjacency metric: config says edge_to_edge, encoder used center-to-center  -> BUG
  loop reference:   references U_GATE_DRV, absent from netlist               -> BUG
solve(both bugs fixed)                 -> OPTIMAL 33/33, mains contained
# The "design conflict" was two encoding bugs. Relaxing the design
# margin would have shipped a compromised board to hide them.
```

Decompose the aggregate before architecting for it:

```
claim (eyeballed): "~885 DRC violations, one root cause: centerline overlap"
measured decomposition of the 499 clearance violations:
   27% actual overlap (<=0.05mm)      -> possibly deep geometry problem
   73% marginal (0.1-0.2mm, med 0.107) -> smells like 1.0mm grid quantization
# The fix to test first is cell_size_mm 1.0 -> 0.1-0.25, not a router rewrite.
```

## Related

- `docs/solutions/best-practices/invariants-verify-model-not-reality-2026-07-09.md` — invariants prove internal consistency, not physical correspondence (the model-vs-reality sibling of this map-vs-territory rule)
- `docs/solutions/best-practices/per-net-isolation-routing-diagnosis-2026-07-10.md` — the router-vs-placement split this arc ultimately resolved by fixing the seam
- `docs/solutions/logic-errors/silent-constraint-drop-seam-bugs-2026-07-11.md` — the concrete catalog of the silent-drop bugs this discipline surfaced
- `docs/solutions/workflow-issues/silent-source-loss-worktree-parallel-merges-2026-07-01.md` — a sibling silent-loss failure mode (uncommitted work destroyed by a branch reset; recovered from git stash)
