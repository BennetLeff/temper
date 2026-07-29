---
title: "When your own result contradicts a passing gate, suspect your reconstruction of the gate — not the board"
date: "2026-07-29"
category: best-practices
module: net_classification
problem_type: best_practice
component: hardware_design
severity: high
applies_when:
  - "reasoning about what a gate/check found by re-implementing its computation from scratch rather than calling the gate's own code"
  - "a self-derived measurement contradicts a gate that has been passing, and the natural next step is to conclude the gate has a blind spot"
  - "a graph, partition, or connectivity computation gets rebuilt to answer a question the original gate's main() already answers, without calling every function that main() calls"
  - "using a finding as grounds for abandoning or narrowing a derivation, before checking whether the finding itself omitted a step the gate performs"
tags:
  - gate-reconstruction
  - connected-components
  - self-verification
  - domain-partition
  - net-classification
  - own-the-mistake
---

# When your own result contradicts a passing gate, suspect your reconstruction of the gate

## Context

Commit `8d8b7955` needed to explain why 110 of 164 nets could not yet be
declared, and asserted, in bold, "THE ENTIRE BOARD IS ONE CONNECTED
COMPONENT" — used to justify that no netlist-connectivity derivation could
distinguish HV from SELV nets, because (the claim went) they were all one
graph. This directly contradicted `check_domain_partition.py`'s own
passing result of 0 violations on a genuinely partitioned design — a
contradiction the commit did not resolve, only asserted past.

The claim was wrong, caught the next day by a derivation agent
(`57ebf112`, `docs: correct the record -- the board is NOT one connected
component`). The author's own account of the mistake: *"I built the graph
with `build_graph(netlist, resolve_isolator_refs(...))` and never called
`synthesize_chain_head_isolators`, which the gate's own `main()` does."*
Measured both ways on the identical netlist:

```
without chain-head synthesis (the omission): 24 components, largest 141
with it (what the gate actually does):       25 components, largest
                                              110 (SELV) and 31 (HV)
```

The remaining 23 components are the singleton zero-pin nets (see
[[encode-facts-as-facts-not-judgments-2026-07-29]]) — 110 + 31 + 23 = 164,
the full net count. `check_domain_partition`'s "0 violations" was a genuine
result on a genuinely partitioned design; the "one connected component"
claim was an artifact of the reconstruction's own missing step, not a
property of the board. The corrected derivation went on to reproduce every
one of the 54 already-known net domains exactly (21/21 HV, 33/33 SELV,
zero mismatches) before any of the 110 new proposals were trusted.

## The pattern

**Reimplementing a gate's internals to reason about it reproduces its
inputs, not its logic.** `build_graph` and `resolve_isolator_refs` are
inputs to `check_domain_partition`'s answer, not the answer itself —
`synthesize_chain_head_isolators` is a step in between that changes which
nodes count as cut points, and it is invoked inside the gate's own
`main()`, not exposed as an obviously-required call from outside. Calling
only the pieces that look like "the graph" and skipping the step that
actually does the partitioning produces a real graph, correctly built from
real data, that answers a different question than the gate answers.

The deeper trap: a self-derived result that contradicts a passing gate
feels like a discovery (the gate has a blind spot!) precisely because it
is surprising, which is exactly the condition under which a reconstruction
error is most likely to be mistaken for a finding rather than checked as
one. The bolder the claim ("the entire board is one connected component"),
the more it should have prompted checking the reconstruction against the
gate's own entry point before writing it down.

## What to do

1. **Call the gate's own entry point (`main()`, its public function) to
   reason about what the gate does, rather than assembling the same
   answer from lower-level pieces by hand.** If the gate's logic must be
   partially reproduced (e.g., to build a superset derivation on top of
   it), diff the reproduction's intermediate output against the gate's own
   intermediate output on the same input before trusting either.
2. **When a self-derived result contradicts a check that is currently
   passing, treat the contradiction as a prompt to re-verify the
   reconstruction first, not as evidence the check is blind.** A passing
   gate and a contradicting hand-built model is symmetric evidence until
   one of the two is shown to be right — and the hand-built model is the
   newer, less-tested of the two.
3. **State a systemic claim ("the entire board is X") as a hypothesis with
   its derivation shown, not as a conclusion, until it has been checked
   against the gate's own code path.** The bolder the claim, the more it
   should be treated as a candidate for re-verification, not less.
4. **When correcting a wrong claim, keep the review process that caught it
   as a standing check, not a one-off.** The corrected derivation here
   added its own self-validation (reproduce all 54 known-good nets exactly
   before trusting any of the 110 new ones) — a test, not a one-time
   sanity check, so future runs of the same derivation can't silently
   regress the same way.

## Why This Matters

The original claim didn't just misdescribe the board — it was used to
justify *stopping* a derivation that, once done correctly, produced usable
domain proposals for all 110 nets (10 HV + 73 SELV + 4 reviewed-elsewhere +
23 unwired). Believing "the board is one connected component" would have
left 110 safety-relevant nets undeclared indefinitely on the premise that
no computation could ever help — a premise that was false and traceable to
one missing function call. The author reported the wrong conclusion "here
and to the user" before it was caught, which is also why this doc names
the mistake as the author's own rather than a third party's: owning it
plainly is what let it get corrected the next day instead of persisting.

## When to Apply

- Before writing down a systemic claim ("the whole X is one Y") derived by
  reimplementing part of an existing gate — call the gate's own top-level
  function first and compare.
- When a hand-built model contradicts a currently-passing check, audit the
  model's construction against the check's actual call graph before
  concluding the check is wrong.
- Reviewing any commit that uses "this cannot be derived/computed" as
  justification for scope reduction — confirm the underlying computation
  was actually attempted via the real code path, not a partial
  reconstruction of it.

## Examples

```python
# WRONG — reconstructs the graph, skips a step main() performs
graph = build_graph(netlist, resolve_isolator_refs(netlist))
# 24 components, largest 141 -- looks like "one big blob"

# RIGHT — call what the gate's own main() calls, in the same order
graph = build_graph(netlist, resolve_isolator_refs(netlist))
graph = synthesize_chain_head_isolators(graph, ...)   # <- the omitted step
# 25 components: 110 (SELV), 31 (HV), 23 singletons -- genuinely partitioned
```

## Related

- [[provenance-is-an-axis-not-a-value-2026-07-29]] — what the corrected
  derivation was used for: proposing `domain_provenance = "derived"`
  values for the 110 nets this correction unblocked.
- [[encode-facts-as-facts-not-judgments-2026-07-29]] — the 23 singleton
  components in the corrected count are exactly the 23 zero-pin nets
  declared `"unwired"`.
- `docs/evidence/2026-07-28-net-domain-derivation-worksheet.md` — the full
  per-net derivation worksheet, grouped by subsystem with path evidence.
- `scripts/check_domain_partition.py` — the gate whose `main()` calls
  `synthesize_chain_head_isolators`; the source of truth this correction
  brought the reconstruction back in line with.
- Commit `8d8b7955` — the original, incorrect "one connected component"
  claim.
- Commit `57ebf112` — `docs: correct the record -- the board is NOT one
  connected component`, the fix and its self-check against the 54 known
  net domains.
