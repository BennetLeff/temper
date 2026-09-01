---
title: "DRC admission needs typed semantic, saturation, and mutation-scope evidence"
date: "2026-09-01"
last_updated: "2026-09-01"
category: architecture-patterns
module: temper-drc-rs
problem_type: architecture_pattern
component: tooling
severity: critical
applies_when:
  - "KiCad DRC output is used to admit or reject generated PCB candidates"
  - "repeated DRC runs preserve engineering meaning while changing provider-selected raw items"
  - "a whole-board DRC category reaches KiCad's reporting cap"
  - "candidate generation mutates a closed, mechanically provable footprint set"
tags:
  - drc
  - kicad-cli
  - semantic-identity
  - reporting-cap
  - mutation-scope
  - fail-closed
  - rust-authority
---

# DRC admission needs typed semantic, saturation, and mutation-scope evidence

## Context

The Net-41 corridor campaign originally stopped before measuring any of its
2,880 declared candidates. Three byte-identical production-board DRC runs
reported `W:silk_overlap=199`, KiCad's warning-report cap, while their
`creepage` members differed despite stable counts. Treating raw records as the
only identity made provider traversal look like an unstable instrument;
treating the capped value as a count would instead have made an incomplete
instrument look exact. Neither result can safely admit a PCB candidate.

The live investigation found the same provider-selection behavior in
`unconnected_items`: KiCad alternated between two connected track primitives
for the same J1 pad and net while preserving the 351-observation engineering
multiset. It also found that a real candidate could have repeatable evidence
and still be unsafe. A materialized candidate produced three
semantically identical samples and nine new hard DRC observations. That is a
candidate veto, not an instrument failure.

## Guidance

Model DRC evidence as three separate questions rather than one pass/fail bit:

1. **Did repeated runs observe the same engineering conditions?**
2. **Was every admission-relevant category measured completely?**
3. **Given trustworthy evidence, did the candidate regress?**

Rust owns the identities, validation, scope proof, and verdict inputs. Python
orchestrates KiCad, staging, partition traversal, caching, and typed JSON
transport, with all reusable or admission evidence replayed through Rust.

### Keep raw and semantic identities together

Every finding enters one raw multiset and two semantic multisets:

- The raw provider identity retains KiCad's description, item descriptions,
  and item coordinates. It is diagnostic evidence and makes traversal churn
  visible.
- The engineering identity retains rule category, normalized message
  semantics, exact measured distance, net multiset, component multiset, and
  multiplicity. Only categories proven to select interchangeable connected
  copper providers omit the raw item list. The allowlist is currently exactly
  `creepage` and `unconnected_items`; all other categories retain items in
  their semantic family key.

This is deliberately a multiset, not a set. Two identical violations remain
two observations, so normalization cannot hide duplicate debt. A repeated
envelope records intersection, union, sample digests, and the unstable fringe
for raw, family, and observation identities.

An exception to semantic identity needs a production-shaped anti-vacuity
test. For `unconnected_items`, changing only the provider track must preserve
the semantic digest while changing the raw digest; changing the net or
component must still change the semantic digest. A generic synthetic value
that the production board never emits is not evidence for the exception.

### Represent saturation as a typed state

A capped category is not a count. Admission comparison assigns each category
one of three states:

- `uncapped-exact`
- `raw-saturated-scoped-complete`
- `raw-saturated-unresolved`

Only the middle state may support admission, and only for the proven mutation
scope. It does not claim that the whole-board total or finding set is known.
Any other cap remains unresolved and makes the instrument inconclusive.

For `silk_overlap`, the campaign proves a closed mutation cone instead of
subtracting counts from the saturated whole-board result. Rust compares the
source and candidate boards, proves that every changed footprint is in the
declared allowlist, and proves the change is rigid placement only. The rigid
proof tokenizes the footprint S-expressions, ignores formatting and root
placement, normalizes pad body angles relative to the footprint rotation, and
requires pad offsets and every other child token to remain unchanged.

Rust then derives every unordered footprint pair incident to the Rust-selected
measurement scope: the closed declared cone for the baseline, and actually
mutated references for candidates. Python stages cross-product boards and runs
the canonical full-project DRC environment. Rust compares all three assigned semantic
multisets; equal counts are not agreement. Scoped finding identity omits the
absolute coordinates that necessarily change under a rigid move, but retains
the exact silk primitive descriptions. An equal-count `Text` to `Segment`
substitution is therefore new evidence, while moving the same two primitives
is not. Saturated or disagreeing cells split first across footprint
cross-products and then, for an atomic footprint pair, across rendered
silk-child cross-products. Reference properties remain present so item
partitioning cannot erase the identity needed to attribute a finding. The
final Rust receipt validates the complete item grid and rejects missing,
duplicate, foreign, or unresolved footprint pairs.

On the production baseline the reviewed v4 instrument closed all 1,148
expected pairs across five leaves and 24 KiCad invocations, while honestly
retaining the global 199-item floor. A synthetic uncapped seven-reference scope
closes in two root cells (six repeated invocations), preventing the earlier
per-anchor/per-pair 84-run minimum.

Self-overlap records need their own typed subject. KiCad can report a
one-reference silk finding, so pair extraction must distinguish
`SelfOverlap(reference)` from `Pair(first, second)` rather than converting a
valid one-reference record into an ambiguous-pair instrument error. Rigid-only
mutation proves that an unchanged footprint's internal silk geometry cannot
change, allowing the scoped comparison to exclude self-overlaps explicitly.

### Separate evidence availability from engineering acceptance

The comparison receipt exposes `instrument_conclusive` independently from
regression counts. It is true only when semantic repeats agree, no cap remains
unresolved, and no hard comparison is indeterminate. New or worsened hard DRC
observations and new scoped silk findings are then candidate vetoes.

This distinction prevents two opposite false conclusions:

- A provider-selected raw item changed, so the campaign is stopped even
  though the engineering observation is stable.
- A repeatable candidate introduced a short, clearance regression, or other
  hard finding, so the measurement is mislabeled unavailable instead of
  rejecting the candidate.

### Reuse only a proved projection

Scoped silk evidence is expensive, but route-only variants with identical
footprint geometry do not need independent silk measurements. Cache reuse is
safe only after Rust derives the same silk projection from the new subject,
revalidates the rigid mutation census, and replays the completed leaf ledger
into a receipt bound to the new subject hash. The receipt also binds the KiCad
version, runner flags and schema, project, generated DRU, footprint table and
library tree, safe ceiling, partition manifest, and every leaf hash. Even a
same-subject cache hit is replayed through Rust so a stale or forged manifest
digest cannot bypass validation. Rust also emits the typed execution metadata;
Python does not append hidden fields after the receipt crosses the pyo3
boundary. Partial trees and non-trusted candidate checkpoints are never
reusable.

The campaign therefore materializes all survivors while sharing one completed
silk receipt per identical placement projection. Candidate checkpoints bind
the exact materialization instruction, board content, and Rust-owned semantic
identity of the current baseline DRC receipt. Provider-only raw churn in the
normalized baseline categories therefore does not invalidate equivalent work,
while a changed engineering observation, cap set, scoped-silk receipt, tool
version, or board does. Interrupted,
indeterminate, or prior-schema checkpoints remain diagnostic artifacts and are
recomputed. Failure to persist a checkpoint does not rewrite already-complete
instrument evidence as a candidate failure.

### Persist an evidence index, not every repeated sample

The three full KiCad finding arrays are needed transiently to build the Rust
comparison receipt. They are not needed again by terminal campaign admission,
which consumes the typed evidence summary. Copying those arrays into every
candidate checkpoint and then into the final manifest is both redundant and a
reliability defect: during the live replay, one checkpoint reached 2,698,748
bytes, of which 1,279,304 compact bytes were `semantic_samples`. At that size,
2,880 checkpoints plus their 1.5 MB scratch boards would require roughly 12 GB
before the final manifest is assembled.

The v4 checkpoint instead persists the small admission evidence and a typed
payload index. Each index entry records the canonical byte count and SHA-256 of
the complete transient payload. The DRC entry additionally retains its
category/cap summary, comparison receipt, compact Rust family/observation
identity, and scoped-silk receipt identity. On the production-shaped sample,
that reduced one checkpoint from 2,698,748 to 21,111 bytes (127.8x smaller)
while preserving a cryptographic commitment to every omitted byte. This
discards transient diagnostic detail while retaining all admission evidence
and a proof index. A candidate can be remeasured from the bound board and
instruction under the same baseline and tool context; the stored digest then
reveals whether the resulting canonical payload is byte-identical.

## Why This Matters

DRC output is an instrument reading, not a self-interpreting truth. Raw
equality is too strict when KiCad chooses a different representative of the
same connected geometry. Count equality is too weak when finding membership
changes. A reporting-cap value is only a lower bound. A scoped uncapping
protocol is unsound unless the actual mutation set and pair denominator are
proved from the bytes being judged.

Keeping these distinctions typed makes the terminal result auditable. A
reviewer can tell whether work stopped because the instrument was incomplete,
because a candidate was conclusively unsafe, or because no candidate survived
the route budget. Those outcomes must never collapse into the same zero.

## When to Apply

- Apply the raw/semantic envelope whenever a nondeterministic external checker
  selects representative objects from equivalent connected geometry.
- Apply mutation-scoped uncapping only when the mutation census is closed by
  construction and the rule is pair-local under the staged transformation.
- Keep a category unresolved when either premise cannot be proved.
- Preserve raw records even when semantic normalization is accepted; they are
  the evidence used to discover and bound future provider exceptions.

## Examples

```text
Three runs, same nets/components/distance, different connected track item:
  raw envelope      = unstable
  semantic envelope = stable
  instrument        = potentially conclusive

Three runs, global silk_overlap == 199, complete mutation-pair receipt:
  whole-board total = unknown saturated floor
  campaign delta    = scoped-comparable
  category state    = raw-saturated-scoped-complete

Three stable candidate runs, nine new hard observations:
  instrument state  = trusted
  candidate verdict = rejected
```

## Related

- `docs/plans/2026-09-01-0903-fix-net41-drc-instrument-reliability-plan.md`
- `docs/evidence/net41-corridor-execution-20260901/README.md`
- `docs/evidence/2026-08-12-uncapped-drc-measurement.md`
- `docs/solutions/workflow-issues/board-correcting-pr-fallout-classes-2026-08-23.md`
- `packages/temper-drc-rs/src/drc_evidence.rs`
- `scripts/measure_uncapped_drc.py`
- `scripts/run_net41_corridor_campaign.py`
