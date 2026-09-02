---
title: "Pre-route candidate campaigns need feasibility witnesses before exhaustive enumeration"
date: "2026-09-02"
category: architecture-patterns
module: temper-quality-oracle
problem_type: architecture_pattern
component: tooling
severity: high
applies_when:
  - "A bounded PCB candidate study will enumerate or materialize a large declared family"
  - "Several pre-route admission instruments can reject the same candidate"
  - "Static model completeness and candidate-dependent physical validity are evaluated together"
  - "Routing is budgeted only after placement and pre-route safety admission"
  - "A zero-survivor result must distinguish conclusive exhaustion from instrument failure"
symptoms:
  - "Thousands of candidates receive the same pre-route veto before routing can begin"
  - "A Boolean field appears false at a stage where that check was deliberately not evaluated"
  - "Aggregate DRC debt does not worsen but new hard observation identities still veto every candidate"
root_cause: missing_validation
related_components:
  - "net41-corridor-campaign"
  - "pcb-candidate-admission"
tags:
  - "pcb-campaign"
  - "pre-route-admission"
  - "feasibility-witness"
  - "invariant-blockers"
  - "instrument-completeness"
  - "rust-authority"
  - "drc"
  - "fail-closed"
---

# Pre-route candidate campaigns need feasibility witnesses before exhaustive enumeration

## Context

PR #1560, still open when this learning was written, completed a bounded,
scratch-only Net-41 corridor campaign with an apparently surprising result:
all 2,880 declared candidates survived the immutable clearance/creepage
prefilter, were materialized, and received trusted pre-route evidence, but
none reached routing. The manifest records
`declared = measured = prefilter_survivors = materialized = 2880` and
`pre_route_survivors = routed = admitted = 0`
(`docs/evidence/net41-corridor-execution-20260901/candidate-manifest.json:3`).
The Rust receipt classifies this complete zero-survivor result as `exhausted`,
with no untested eligible candidate
(`docs/evidence/net41-corridor-execution-20260901/terminal-receipt.json:3`).

That is an admission result, not a routing result. Python asks Rust which
materialized rows were accepted and only invokes the router for those IDs
(`scripts/run_net41_corridor_campaign.py:1484`). Rust constructs the IDs by
applying pre-route vetoes to every trusted materialized row
(`packages/temper-quality-oracle/src/corridor_campaign.rs:559`). With an empty
set, the routing loop has nothing to execute. This campaign therefore says
nothing about router completion, performance, or capability.

The campaign also exposed two ways a truthful receipt can invite the wrong
explanation.

First, all 2,880 rows carried the same containment failure. The manifest
indexes the shared canonical payload with 50 bytes and SHA-256
`14561f0c5bd38ac7cbba57872c8e230bb668633f823d612e8f45c3e7c46274eb`
(`docs/evidence/net41-corridor-execution-20260901/candidate-manifest.json:49`).
Reconstructing the runner's indented, sorted, newline-terminated canonical
encoding produces that exact digest for:

```json
{
  "failures": [
    "J1:missing-geometry"
  ]
}
```

The containment implementation emits `<reference>:missing-geometry` when an
affected reference is absent from either the geometry or position model,
before it asks whether the component body lies inside the outline
(`scripts/run_net41_corridor_campaign.py:653`). The receipt therefore proves
an incomplete containment model for J1, not that J1 was physically outside
the board.

Second, every pre-route row serialized `netlist_reconciled: false`
(`scripts/run_net41_corridor_campaign.py:881`). At that stage the value means
"not evaluated": Rust calls `admission_vetoes(..., false)` for materialized
candidates (`packages/temper-quality-oracle/src/corridor_campaign.rs:577`),
and only considers the netlist veto when that stage flag is true
(`packages/temper-quality-oracle/src/corridor_campaign.rs:466`). Python runs
netlist reconciliation only after routing and replaces the field with its
actual result (`scripts/run_net41_corridor_campaign.py:1123`); Rust then calls
the post-route gate with `true`
(`packages/temper-quality-oracle/src/corridor_campaign.rs:648`). The existing
evidence README and preceding DRC-admission learning incorrectly described
all rows as having failed reconciliation. Reconciliation was never reached.

## Guidance

Treat a zero-survivor terminal as a valid engineering result when coverage,
instrument trust, and terminal accounting are conclusive. Rust requires exact
ordered materialization of every prefilter survivor
(`packages/temper-quality-oracle/src/corridor_campaign.rs:543`) and separates
trusted candidate vetoes from indeterminate measurement
(`packages/temper-quality-oracle/src/corridor_campaign.rs:573`). It emits
`exhausted` only when no eligible candidate remains untested
(`packages/temper-quality-oracle/src/corridor_campaign.rs:704`). Do not relabel
that state as a router failure, silently loosen admission, or manufacture a
survivor.

Before enumerating a large family, add a feasibility stage with two layers:

1. Validate family-wide model and instrument completeness independently of
   candidate choice. Every affected reference must resolve to the geometry,
   position, domain, and denominator data actually consumed by every pre-route
   gate. Completeness is contract-relative: this project's domain manifest is
   intentionally partial, and the established safety loader classifies a
   component when at least one net has one unambiguous explicit domain.
   Requiring every physical pad net to be declared would convert intentional
   manifest scope into false model failure.
   Missing shared inputs stop the family before materialization instead of
   appearing as thousands of identical candidate vetoes.
2. Materialize a deterministic representative candidate and run the complete
   pre-route stack. Classify every veto as family-invariant,
   placement-dependent, or route-shape-dependent. Expand to the full family
   and allocate route budget only after the corrected generator can produce
   at least one trusted, veto-free pre-route witness.

Preserve finding identities, not only aggregate counts. Every Net-41 row
passed connectivity and complete SELV-denominator construction
(`scripts/run_net41_corridor_campaign.py:762`), route geometry and current
capacity (`scripts/run_net41_corridor_campaign.py:795`), mutation-scope
validation, and repeated semantic DRC agreement
(`scripts/run_net41_corridor_campaign.py:846`). Nevertheless, every row
introduced between five and eleven hard DRC observation identities while
every row had zero *worsened* hard observations. Rust intentionally vetoes
either new or worsened hard observations
(`packages/temper-quality-oracle/src/corridor_campaign.rs:457`). Aggregate or
category counts can remain flat, or improve, while old observations disappear
and new ones appear.

For each candidate family, compute the intersection shared by all candidates
and the variant fringe keyed by candidate dimensions. Apply the same
identity-level treatment to safety signatures. In this run, every row had two
or three new safety signatures, one worsened safety signature, one containment
failure, and five to eleven new hard DRC observations. Courtyard overlap was
secondary: 720 rows had no new courtyard overlap, while every row had no new
body overlap and no new scoped-silk finding. Removing the courtyard veto alone
could not have produced a routable candidate.

Move the resulting constraints upstream. Family-invariant safety or
containment facts belong in a Rust-owned feasibility contract.
Placement-dependent and route-shape-dependent facts belong in the Rust
candidate generator or immutable prefilter so inadmissible rows are not
materialized. Python may stage KiCad projects and transport instrument
receipts, but it must not become a second source of candidate truth.

Represent lifecycle state explicitly. A post-route-only check needs a type
such as `not-evaluated | reconciled | findings`, not a Boolean whose `false`
conflates "not run" with "ran and failed." Rust should own the state
transition and admission semantics, while evidence summaries render the state
verbatim. An artifact should not require knowledge of a hidden function
argument to be interpreted correctly.

Finally, route only a pre-route-clean witness. Do not waive a safety,
containment, overlap, or hard-DRC gate merely to exercise the router. Once a
trusted witness exists, a failed route becomes evidence about the router or
the physical routing problem. Before that point, routing is unobserved.

## Why This Matters

Exhaustive search is valuable only after the search space and its instruments
are feasible. Without an invariant preflight, a campaign can spend most of
its cost repeatedly proving the same static defect. The completed Net-41 run
was still scientifically useful: exact coverage and retained identities prove
that the declared family was unsatisfiable under its current pre-route
contract. The process improvement is to reach that proof much earlier and
make its cause legible.

This distinction also protects design safety. A zero result creates pressure
to weaken a gate until something passes. That reverses the authority: the
admission vetoes are the specification the candidate must satisfy. Universal
failures mean either the family violates the specification or the evaluator
cannot yet model it. Repair the model, inspect the exact identities, and
constrain generation; do not reinterpret a Boolean, aggregate away new DRC
observations, or grant an exception.

Typed lifecycle states prevent durable documentation errors. The stored
netlist Boolean was internally safe because Rust received a separate stage
flag, but externally ambiguous enough to produce a false narrative in two
documents. If serialized evidence can be read without the caller, its state
must carry the lifecycle context itself.

The phase boundary also keeps router evaluation honest. A pre-route-clean
witness makes routing observable. Until then, a zero routed count is not a
router verdict.

## Implementation outcome: model-complete does not mean witness-clean

The 2026-09-02 implementation validated the pattern on the immutable Net-41
family. An initial live preflight stopped on five apparent domain gaps, but
that diagnosis exposed a bug in the new preflight rather than in the board:
`R45`, `R58`, `R66`, `SW1`, and `U22` each have an explicit LV_CONTROL net
while also carrying an intentionally unclassified internal signal. The
production safety loader includes such components by their classified nets
and keeps unclassified pad copper conservative. Aligning preflight with that
consumer contract restored complete model coverage without guessing five new
domain assignments or changing the frozen 240-pad SELV denominator.

The corrected run screened all 2,880 declaration rows, materialized exactly
one deterministic witness (ordinal 2,244), and routed zero. The witness had
trusted evidence but was rejected on four safety identities and nine new hard
DRC identities. Those included two J1 pad-to-track shorts, six local
clearance/hole-clearance findings, one 12.2478 mm HV-to-LV creepage finding,
and functional-creepage relationships in the `R54`/`R66`/`SW1`/`U22`
cluster. Because a singleton cannot prove which findings span the family,
Rust correctly left their dependency unresolved and did not emit either
`family-negative` or `exhausted`.

This produces three durable takeaways. First, preflight predicates need their
own oracle: a stricter-looking condition can be wrong when it checks a larger
universe than the downstream gate consumes. Second, fixing model completeness
does not rehabilitate a candidate; it makes the physical rejection
trustworthy. Third, the next efficient experiment is an exact finding matrix
over unique placement bases, not another routed enumeration. Intersections
can become Rust construction constraints; fringes identify which placement
axes must change before a clean witness is possible.

## When to Apply

- Hundreds or thousands of candidates share the same baseline model,
  placement family, or instrument setup.
- External tools such as KiCad supply measurements whose completeness can
  fail independently of candidate quality.
- Gates compare structured safety or DRC findings where identity changes
  matter more than totals.
- Some evidence is meaningful only after a lifecycle transition, such as
  post-route connectivity or netlist reconciliation.
- A zero-survivor result could otherwise be interpreted as an optimizer or
  router verdict.
- Safety pressure makes temporarily relaxing a gate appear attractive.

The pattern also applies outside PCB layout: compiler optimization searches,
manufacturing parameter sweeps, deployment candidate promotion, and test
matrix selection all benefit from separating static feasibility,
representative-witness validation, exhaustive screening, and expensive
execution.

## Examples

For a future Net-41 campaign, start with a Rust-owned preflight receipt that
enumerates every affected reference and proves its geometry, position, usable
domain membership, and denominator inputs are available. Materialize the
deterministic highest-ranked candidate and run connectivity, denominator
completeness, safety signatures, route geometry, ampacity, containment,
overlap, mutation scope, and repeated semantic DRC. The 2026-09-02 run did
exactly that and rejected the witness with 13 exact findings. The next pass
must partition those identities across unique placement bases and revise the
generator. Only a veto-free witness opens routing.

For DRC analysis, suppose a candidate's hard-error count remains 80 while five
baseline identities disappear and five new identities appear. A count-only
comparison says "unchanged." Identity-aware admission says "five new hard
observations" and rejects it. Across a family, an intersection report might
show that three identities occur on every row while two track an endpoint
choice; the first group is a family-level feasibility issue, and the second
belongs in the generator constraints.

For lifecycle evidence, replace a pre-route payload such as:

```json
{"netlist_reconciled": false}
```

with an explicit state such as:

```json
{"netlist_reconciliation": {"state": "not-evaluated"}}
```

A post-route clean result becomes `{"state": "reconciled"}`. A completed
check with discrepancies becomes
`{"state": "findings", "finding_count": 3}`. Rust owns the allowed
transitions; Python supplies the post-route receipt.

For terminal reporting, say:

> All 2,880 candidates were conclusively rejected before routing; the declared
> family is exhausted under the current pre-route contract. Routing was not
> attempted.

Do not say the router failed, and do not say candidates failed a post-route
check that remained unevaluated.

## Related

- `docs/solutions/architecture-patterns/drc-admission-needs-typed-semantic-and-scoped-evidence-2026-09-01.md`
- `docs/solutions/architecture-patterns/typed-rust-quality-oracle-pipeline-2026-07-01.md`
- `docs/solutions/architecture-patterns/cp-sat-feasibility-first-paradigm-2026-07-03.md`
- `docs/solutions/best-practices/infeasibility-claims-bar-class-and-unsat-core-nondeterminism-2026-08-02.md`
- `docs/evidence/net41-corridor-execution-20260901/README.md`
- `docs/evidence/net41-corridor-execution-20260901/terminal-receipt.json`
- `docs/evidence/net41-corridor-execution-20260901/candidate-manifest.json`
- `docs/evidence/net41-corridor-feasibility-20260902/README.md`
- `docs/evidence/net41-corridor-feasibility-20260902/feasibility-receipt.json`
- `scripts/run_net41_corridor_campaign.py`
- `packages/temper-quality-oracle/src/corridor_campaign.rs`
