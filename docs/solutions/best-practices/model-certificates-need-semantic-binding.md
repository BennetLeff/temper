---
title: "Model certificates need semantic binding as well as artifact hashes"
date: "2026-09-11"
category: best-practices
module: zapote
problem_type: best_practice
component: testing_framework
severity: high
applies_when:
  - "promoting simulation or analytical results into an engineering acceptance rule"
  - "transferring a model-validation lesson from one electrical unit to another"
  - "a producer can regenerate both model output and its evidence hashes"
tags:
  - "model-qualification"
  - "semantic-binding"
  - "agent-memory"
  - "mutation-testing"
  - "evidence-boundary"
---

# Model certificates need semantic binding as well as artifact hashes

## Context

The RTD qualification work exposed a distinction that a file-integrity check
cannot establish: a model artifact and a valid mathematical certificate can
both be fresh while disagreeing about the same fault's timing. Recomputing a
hash proves which bytes were supplied, not that their claims agree or that
the selected equations describe the source circuit.

Earlier RTD development also produced plausible output from an unsupported
scalar timing bound, an omitted threshold-divider current in a sense-wire
fault bound, and a SPICE switch that reconnected a wire instead of opening it.
The important transferable lesson is the qualification procedure, not the
corrected RTD number. The conditional 0.97146 ms result belongs only to the
reviewed topology and parameter envelope.

The implementation and evidence described here are present in the local
working tree as of this writing; this document makes no merge or publication
claim. See the [retained review](../../../zapote/rtd/model-correctness/README.md)
and [closeout receipt](../../../zapote/rtd/model-correctness/closeout-receipt.json).

## Guidance

Maintain three linked forms of knowledge:

| Form | Contains | Authority |
|---|---|---|
| Durable lesson | Cause, rejected approaches, applicability, supporting evidence | Helps an agent choose an investigation |
| Selected agent memory | A short applicable procedure, revision and evidence references | Advice delivered to a particular attempt |
| Executable validator | Required inputs, independently computed bounds, verdicts and regression cases | Decides whether the engineering claim is supported |

A lesson should point to a rule and its reproducer when one exists. Do not
copy acceptance constants into advisory notes and create a second authority.
A useful portable note here is: inspect each post-fault graph, check datasheet
column and test conditions, corroborate solver behavior, justify parameter
coverage, and test the normal validator with deliberately corrupted claims.
An exact node voltage, component limit or timing certificate transfers only
with the relevant source and operating-condition identities.

The current RTD implementation demonstrates the executable part:

- `zapote/packages/zapote-harness/src/lib.rs:149` invokes qualification from
  the normal unit validation entry point.
- `zapote/packages/zapote-harness/src/model_qualification.rs:139` checks
  model bytes, source bytes and identities; its reviewed topology identity
  prevents coordinated replacement of source hashes from authorizing a new
  circuit without review.
- `zapote/packages/zapote-harness/src/model_qualification.rs:406` recomputes
  the five required fault certificates and checks supplied numerical claims.
- `zapote/packages/zapote-harness/src/model_qualification.rs:507` requires
  one corresponding runtime row per fault, with matching bound and observed
  latency. The runtime model cannot contradict the certificate simply by
  supplying a fresh hash.
- `zapote/packages/zapote-harness/src/model_qualification.rs:89` retains
  device applicability as INDETERMINATE after mathematical qualification.
  A producer's device-PASS label cannot remove omitted physical behavior.

## Prevention example

Retain this negative control through the real validation entry point:

```text
start with a valid bound unit input
change a runtime fault row's timing bound
regenerate the raw model JSON and both matching model hashes
keep the independently justified certificate unchanged
expect the semantic comparison to fail
```

Also retain missing/duplicate-case, reduced parameter-range, wrong topology,
wrong experiment direction and physical-applicability controls where relevant.
A sampled numerical comparison checks implementation behavior. It does not
replace an argument that a bound covers the declared continuous ranges.

The [compiled-validator replay](../../../zapote/rtd/model-correctness/root-review/replay_mutations.py)
contains the rehashed-model counterexample. The
[derivation](../../../zapote/rtd/model-correctness/root-review/analytic-derivation.md)
explains the continuous-range argument and its physical boundary.

## Feeding the next agent

The existing memory policy is in `harness-lab/src/memory.rs` and its dispatcher
is registered in `harness-lab/src/main.rs:261`. The current catalog at
`harness-lab/memory/catalog.json` pins lesson evidence hashes. Editing one of
those lessons changes its identity; publish a reviewed new package revision
and preserve the old bytes/receipt rather than silently rewriting an old
selection's evidence.

At capture time, Zapote's harness entry point has no corresponding memory
module integration. The existing
[engineering-memory plan](../../plans/2026-09-10-1322-feat-engineering-agent-memory-plan.md)
already specifies the missing selection/delivery work. Reuse the donor's
reviewed Rust policy through Zapote's package boundary; do not build a new
memory service merely to store these notes.

For the next unit attempt:

1. Select the general procedure by task capabilities and applicability. Keep
   the RTD-specific numerical certificate out of another unit's constraints.
2. Record selected entry IDs, versions and evidence hashes before construction.
3. Retain the actual model-visible input containing those notes. Merely writing
   a file or a worker acknowledgement does not establish delivery.
4. Record invoked helpers separately; cite a lesson in a decision record when
   used. Do not infer causal improvement from selection or delivery alone.
5. Review any new proposed lesson against the attempt's evidence, then publish
   it between attempts. Memory cannot relax the active validation rules.

Until those receipts exist, claim that the lesson is stored and the RTD
validator is enforced, not that automatic cross-unit memory reuse is proven.

## Applicability

Use this procedure for later sensing, gate-drive, power and protection units.
Reuse the verification structure; derive each unit's own equations, faults,
limits and device-applicability conditions. Agent placement and routing remain
agent decisions through the existing KiCad editing tools.
