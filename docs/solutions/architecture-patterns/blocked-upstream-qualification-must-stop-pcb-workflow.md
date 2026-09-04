---
title: "Blocked upstream qualification must stop the PCB workflow"
date: "2026-09-04"
category: architecture-patterns
module: pcb-hardware-design
problem_type: architecture_pattern
component: isolation-barrier
severity: critical
applies_when:
  - "An upstream safety qualification is not eligible before a PCB candidate can be admitted"
  - "A valid early stop must be published as a reproducible terminal package"
  - "Downstream geometry or production work could mistake missing authority for permission to proceed"
root_cause: missing_workflow_step
resolution_type: workflow_improvement
tags:
  - split-board
  - stopped-indeterminate
  - fail-closed
  - qualification
  - digest-binding
  - no-claim
  - pcb-floorplan
  - safety-closure
---

# Blocked upstream qualification must stop the PCB workflow

## Context

Safety qualification can stop before the physical work that a downstream PCB
team wants to begin. Temper's split-board campaign reached that boundary when
the U9 joint isolation qualification was not eligible for refloorplanning. The
correct result was an authoritative U1 stop aggregated into a U7 terminal
record, not a provisional split-board geometry result. The committed decision
therefore identifies `terminal_unit` as `U1`, `stage` as
`u7-terminal-decision`, and `verdict` as `stopped-indeterminate`
(`power_pcb_dataset/qualification/split_board_feasibility/decision.json:115`).

Earlier work established why this distinction is necessary. A local keepout
repair could not separate the interleaved HV and SELV placement, while the
subsequent qualification campaign still lacked controlled evidence and owner
authority. Continuing into a cosmetic board edit would have converted an
unresolved prerequisite into misleading physical evidence. A stopped campaign
must instead preserve exactly what was learned and state which later work was
never reached. (session history)

## Guidance

Model three outcomes separately:

1. **Replay error.** Filesystem escapes, symlinks, malformed JSON, digest
   mismatches, or evaluator failures are invalid packages. The Python adapter
   raises `SplitBoardReplayError` at this boundary
   (`scripts/check_split_board_feasibility.py:72`, `:258`).
2. **Valid upstream stop.** A canonical upstream verdict can be
   `stopped-indeterminate`. This is data, not an exception and not an
   architecture verdict. Rust permits terminal evaluation only for an
   admission-scoped U1 stop with no local axes
   (`packages/temper-quality-oracle/src/split_board_feasibility.rs:801`,
   `:951`).
3. **Physical candidate result.** Geometry, routing, DRC, or rejection evidence
   exists only after admission authorizes those units. It must not be inferred
   from a missing candidate.

Rebind both bytes and meaning. The replay adapter supplies the exact upstream
decision, contract, manifest, and combined-candidate bytes before constructing
the terminal package (`scripts/check_split_board_feasibility.py:295`). Rust
checks each digest against the supplied bytes, parses those bytes, compares
their declared records, and validates the blocked-state fields
(`packages/temper-quality-oracle/src/split_board_feasibility.rs:150`,
`:983`, `:1031`). A digest proves which bytes were supplied; it does not prove
that the bytes are the canonical artifact or express the permitted semantics.

Close the terminal binding vocabulary. The evaluator requires the exact U7
binding set and canonical paths, then requires precisely four local source
byte sets: manifest, admission decision, evidence index, and owner signoffs
(`packages/temper-quality-oracle/src/split_board_feasibility.rs:1083`,
`:1119`). It also verifies that the committed admission bytes equal the fresh
Rust admission result (`packages/temper-quality-oracle/src/split_board_feasibility.rs:1184`).
This prevents a caller from omitting an unfavorable authority, substituting an
alternate path, or editing a no-claim artifact and merely rebinding its hash.

Protect every consumed authority on both sides of evaluation. The live replay
snapshots the relevant inputs before verification and after evaluation; the
admission set always contains the U7 manifest and admission decision, while
terminal evaluation adds the evidence index and owner signoffs
(`scripts/check_split_board_feasibility.py:231`, `:358`, `:381`, `:446`). Keep the
protected set derived from the artifacts actually read so newly introduced
inputs cannot evade mutation detection.

Run the stop gate before downstream materialization, but keep later gates
independent. The workflow watches the entire qualification tree for push and
pull-request changes and executes the split-board replay before the generated
netlist is cached or built (`.github/workflows/python-tests.yml:181`, `:306`,
`:1745`). Its status-aware setup barrier still lets independent board checks
obtain a verdict after a red qualification replay
(`.github/workflows/python-tests.yml:1771`).

Record each downstream unit as `not-reached`, with the causal chain back to the
early stop. Temper's evidence index does this for U2 through U6 rather than
claiming those units passed, failed, or were silently omitted
(`power_pcb_dataset/qualification/split_board_feasibility/evidence_index.json:59-92`).

## Why This Matters

A stopped-indeterminate terminal package preserves the authority boundary. It
says that the prerequisite qualification is unresolved and names the next
authority while making no claim about spatial feasibility, candidate
rejection, architecture no-go, production readiness, or production
authorization
(`power_pcb_dataset/qualification/split_board_feasibility/decision.json:54-59`).
This prevents incomplete safety evidence from becoming geometry approval and
prevents a missing candidate from being presented as proof that an architecture
cannot work.

The package is also reproducible. A future replay can distinguish changed
authority, malformed input, semantic disagreement, and the same valid early
stop. The adapter requires the emitted terminal decision to byte-match the
checked-in artifact after evaluation
(`scripts/check_split_board_feasibility.py:376`, `:440`).

## When to Apply

Use this pattern when:

- downstream geometry, routing, or production authorization depends on an
  upstream eligibility verdict;
- authority is distributed across manifests, decisions, evidence, receipts,
  signoffs, or handoffs;
- a valid stop must be durable and machine-readable rather than inferred from
  a missing output; or
- CI must react to transitive qualification inputs that are not themselves PCB
  geometry.

Do not use `stopped-indeterminate` to hide malformed inputs or replay failures.
Do not run later physical units merely to fill a report after admission has
stopped. Resolve the named upstream authority, publish an eligible combined
candidate, and then begin downstream feasibility work.

## Examples

For a blocked upstream state, the workflow is:

```text
fresh canonical U9 replay
  -> byte-match the published U9 decision
  -> assemble U1 admission package
  -> Rust returns stopped-indeterminate
  -> bind the four U7 local sources and eight terminal paths
  -> byte-match the checked-in U7 early-terminal decision
```

The live-path tests should exercise this complete adapter boundary, not only a
hand-built Rust input. Temper's focused suite proves that the canonical U9
replay is called, that all four U7 source byte sets and eight bindings are
present, that admission and terminal protected sets differ intentionally, and
that path traversal fails at the real snapshot boundary
(`packages/temper-placer/tests/scripts/test_check_split_board_feasibility.py:103`,
`:155`, `:217`, `:253`).

## Related

- `docs/solutions/best-practices/qualification-exports-require-clean-build-replay-2026-09-01.md`
  — clean replay and immutable qualification-export identity.
- `docs/solutions/architecture-patterns/isolation-values-need-role-aware-authority-2026-08-31.md`
  — keeping safety authority distinct from downstream design interpretation.
- `docs/solutions/architecture-patterns/dense-creepage-repair-is-neighborhood-topology.md`
  — bounded physical candidate studies and scoped stopped-indeterminate results.
- `docs/solutions/architecture-patterns/physical-isolation-barrier-requires-domain-first-floorplan-2026-07-30.md`
  — why physical layout follows domain and component qualification.
- `docs/solutions/best-practices/gate-neutering-mechanisms-2026-07-26.md`
  — failure modes that turn apparently present CI checks into advisory signals.
