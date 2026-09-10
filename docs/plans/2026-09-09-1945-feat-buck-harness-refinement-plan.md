---
title: "Buck Harness Bounded Refinement and Recovery Plan"
date: 2026-09-09
type: feat
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
product_contract_source: docs/plans/2026-09-09-1635-feat-buck-engineering-validation-plan.md
execution: code
---

# Buck Harness Bounded Refinement and Recovery Plan

## Goal Capsule

Add bounded continual harness controls around the existing full-buck
experiment: persistent standard-Python state, external measurement, Rust-owned
failure classification, immutable learned artifacts, same-attempt recovery, and
optional host telemetry. Deliver local synthetic integration evidence without
claiming a qualified buck or launching live trials.

## Product Contract

### Summary

An OpenCode-driven buck attempt acts through admitted MCP PCB tools, observes an
independently measured board, applies versioned refinement at fixed successful
mutation boundaries, and resumes under its original deadline and budget.
Independent trials remain reset and isolated.

### Requirements

- R19. Preserve OpenCode, the existing MCP relay, and model/tool/preflight
  contracts.
- R20. Persist interpreter state within an attempt and retain board, action
  history, revision, and remaining deadline across recovery.
- R21. Classify measurement, model, transport, process, and admission failures
  separately from deterministic Rust policy.
- R22. Store complete versioned `notes.md`/`skills.py` artifacts with hashes,
  parent/source window, and frozen inheritance boundaries.
- R23. Keep telemetry optional and failure-isolated; engineering qualification
  and hardware remain unverified until the prior gates pass.

### Scope boundaries

Deferred: live full-buck scoring, model qualification, physical validation, and
SaaS trace delivery without authorized configuration. Out of scope: alternate
agent runtimes, DSLs, vector databases, unbounded recovery, provider fallback,
DRC threshold changes, and cross-trial mutable memory.

## Planning Contract

### Key technical decisions

- KTD15. Rust owns schemas, hashes, classification, and admission; Python owns
  process/file orchestration at the existing standalone crate boundary.
- KTD16. Refine only after native measurement at the prior plan's 20/60/100
  successful-mutation boundaries, preserving the fixed experiment.
- KTD17. Exporter failure is observational only; authoritative receipts remain
  valid when LangSmith/OTEL is unavailable.

### Sources and research

The authoritative prior contract is
`docs/plans/2026-09-09-1635-feat-buck-engineering-validation-plan.md`.
Current coverage and gaps are in `harness-lab/BUCK-ENGINEERING.md`; the relay is
`harness-lab/run_zen_trials.py`. OpenCode 1.x's official server documentation
describes a headless HTTP/OpenAPI boundary; this plan does not assume OpenCode 2
APIs. Prime Agent (arXiv:2608.23552) and Continual Harness (arXiv:2605.09998)
support persistent execution, bounded accounting, and reset-free act/refine
alternation, but do not qualify electrical or physical evidence.

## Problem frame and scope

The existing `harness-lab` has a working OpenCode relay, isolated XDG state,
native PCB tools, durable wire/action evidence, and a Rust-owned engineering
judge. It does not yet have the outer continual loop described by the current
engineering plan: an attempt must act, obtain an external measurement, classify
the result, optionally refine versioned `notes.md`/`skills.py`, and resume with
the same board and remaining budget. Recovery is currently retained but not
automatically classified or resumed, and learned artifacts are not promoted.

This plan adds that bounded control plane and its proof controls. OpenCode
remains the agent runtime and the existing MCP tool boundary remains the only
PCB operation surface. The implementation does not add LangChain/LangGraph, a
DSL, a vector store, unbounded repair, provider fallback, altered DRC limits,
or cross-trial memory. Optional LangSmith/OpenTelemetry export is host-boundary
telemetry only; missing credentials, backend, or exporter errors cannot affect
authoritative receipts and no data is uploaded without an already authorized
configuration.

The authoritative prior contract remains unchanged, especially U2/U3/U4, the
three conditions, ten-attempt ceiling, fresh trial isolation, and engineering
admission gates in `docs/plans/2026-09-09-1635-feat-buck-engineering-validation-plan.md`.
This is a follow-up implementation plan for the missing prerequisites around
U4/U5; it does not admit live full-buck scoring while stages 1–4 remain
unqualified. Product Contract preservation: unchanged.

## Compatibility decisions

1. `run_buck_trials.py` owns phase orchestration and calls the already existing
   `run_zen_trials.py` configuration/relay path. It must preserve the prior
   preflight, development, and evaluation argument contracts and append fields
   to receipts rather than changing existing meanings.
2. The host owns process lifecycle, deadlines, filesystem paths, and optional
   telemetry. Rust owns the deterministic schemas, hashes, revision identity,
   failure taxonomy, inheritance-manifest validation, and admission decisions.
   Python remains thin process and JSON I/O glue, consistent with the standalone
   `harness-lab` crate.
3. A revision is an immutable, content-addressed pair of complete `notes.md`
   and `skills.py` plus parent/source-window metadata. The active revision is
   selected only at the fixed successful-mutation boundaries already specified
   by the prior plan (20, 60, and 100), after native measurement, and never
   after construction passes or its deadline expires.
4. A recovery decision is one of `resume_same_attempt`, `record_indeterminate`,
   `record_failed`, `blocked_admission`, or `operator_action_required`. It is
   derived from structured evidence (deadline, process exit, transport status,
   native receipt, and state hashes), never from an LLM-generated label.
5. Trial inheritance reads only an explicit frozen development manifest. The
   manifest names immutable revision digests and source trial IDs; reserved
   results, transcripts, and runtime state are rejected as inheritance inputs.

The prior plan names U2/U3/U4 as predecessors, but this checkout currently
contains neither a full-buck `run_buck_trials.py` nor the persistent interpreter
and refinement modules. Implementers must close these compatibility
prerequisites before claiming U12/U13 complete. They are the existing U2/U3
contracts made concrete, not a replacement experiment:

* Full-buck admitted operations must exist behind `buck_host.py`, with atomic
  placement/copper edits, one shared budget, and native reload checks. The
  historical two-footprint `harness.py` and `combined_host.py` profiles remain
  unchanged.
* The U3 persistent standard Python subprocess and deny-by-default OS/container
  boundary must be proven before executable revisions are applied. The local
  presence of `sandbox-exec` and OpenCode is recorded as environment evidence,
  not treated as a portable assumption. If the boundary cannot be qualified,
  local schema/storage controls may pass while live refinement and scoring stay
  blocked.
* Same-attempt recovery resumes state only when the transport/driver
  interruption leaves the persistent worker demonstrably alive and its state
  hash unchanged. A worker crash or a timeout that kills the worker ends the
  attempt as `indeterminate`; retain its board, action log, and evidence but do
  not reconstruct arbitrary Python globals or claim a resume. Independent trials intentionally reset
  board, conversation, interpreter, and working directory. Development to
  evaluation crosses only the frozen inheritance manifest.

## Requirements traceability

The units below implement R5–R12 and KTD3–KTD9 from the prior contract while
honoring R13–R18 as a hard admission boundary. They provide the missing
executable evidence for the coverage gaps recorded in
`harness-lab/BUCK-ENGINEERING.md`: outer recovery/refinement, automated
diagnosis, and promotion into versioned learned artifacts. They must preserve
the prior plan's exact three conditions, four development attempts, six
reserved attempts, remaining-budget semantics, and no-live-run-while-blocked
rule.

## Implementation units

### P1. Complete full-buck admitted operations (U2 prerequisite)

**Owned files:** `harness-lab/buck_host.py`, `harness-lab/buck_native.py`,
`harness-lab/src/buck.rs` (or a new `harness-lab/src/buck_operations.rs` if
that boundary is cleaner), `harness-lab/src/main.rs` only for dispatcher
registration, and `harness-lab/test_buck_boundary.py`.

Implement or reconcile the admitted full-buck operations against the
existing Rust judge and fixture contract. Preserve historical profile
interfaces and one shared mutation budget. An independent reload/check must
prove each board action before the continual loop observes it.

Test invalid arguments, stationary unrelated copper, net replacement,
protected state, exhausted budget, stale requests, and complete witness replay.
This unit is complete only when the nine-component public operation contract
does not rely on the two-footprint session.

### P2. Qualify the persistent interpreter boundary (U3 prerequisite)

**Depends on:** P1. **Owned files:** `harness-lab/workspace.py`,
`harness-lab/workspace_worker.py`, `harness-lab/test_workspace.py`, and minimal
`harness-lab/buck_host.py` RPC wiring.

Run ordinary Python in a persistent worker with bounded RPC, 120-second
per-call/64-KiB output limits, dedicated working directory, no credentials,
network, subprocess creation, repository, or witness access. Qualify the real
`sandbox-exec` profile on this host (or an equivalent container) with real
deny tests; import filtering and a DSL are not substitutes. Variables and the
`skills` binding persist inside an attempt, while a new trial starts fresh.

Test persistence and composition through full-buck operations, then denials
for files, network, subprocess, protected paths, infinite execution, output
flooding, malformed RPC, and nested budget exhaustion. An unavailable boundary
produces an explicit blocked capability.

### U11. Add the Rust-owned continual-loop contract

**Depends on:** existing `harness-lab/src/main.rs`, `buck.rs`, and U2/U3/U4
interfaces; no engineering qualification is assumed.

**Owned files:** `harness-lab/src/continual.rs`, `harness-lab/src/main.rs`,
`harness-lab/src/lib.rs` only if the crate needs a testable library boundary,
`harness-lab/test_continual_contract.py` for process-level JSON controls.

Define versioned schemas for attempt state, external measurement, recovery
classification, refinement proposal, revision manifest, and trial inheritance.
Validate finite values, monotonic deadlines, exact content hashes, sequence
numbers, allowed states, and no path escaping. Classification must make
transport/process/native failures distinct from model outcomes and retain the
original evidence references. A stale or incomplete state cannot be silently
resumed. Keep all policy in Rust and expose one JSON judge entrypoint through
the existing dispatcher.

Test scenarios: malformed and unknown fields fail closed; duplicate sequence or
hash mismatch is rejected; a native `pass`/`fail` remains distinct from
transport timeout, worker crash, deadline exhaustion, and missing measurement;
an already consumed attempt slot cannot be resumed; a valid same-attempt state
preserves board hash, action count, revision hash, and absolute deadline.

### U12. Implement immutable learned-artifact storage and refinement

**Depends on:** U11 and the existing U3 workspace boundary.

**Owned files:** `harness-lab/refinement.py`, `harness-lab/artifacts.py`,
`harness-lab/test_refinement.py`, `harness-lab/test_artifacts.py`,
`harness-lab/skills/base/notes.md`, `harness-lab/skills/base/skills.py`, and
minimal additions to `harness-lab/buck_host.py` needed to expose the current
revision in observations.

Store complete artifact contents under an attempt-local, ignored run directory
and retain a compact manifest with parent digest, source attempt/window,
contents digest, model/transport receipt, and application boundary. Validate
size, UTF-8, Python syntax, and path identity before loading a new isolated
worker module. Keep ordinary variables and the board alive while replacing the
`skills` binding; retained aliases remain attributed to their old revision.
Proposal timeout, parse failure, or transport-integrity failure retains the old
revision and records the reason. The artifact writer must use atomic creation
and refuse overwrite; frozen evaluation artifacts and the repository remain
unwritable.

Test scenarios: an ordinary skill changes behavior after a boundary; board
hash, action history, variables, and absolute deadline survive application;
parent/child hashes and source windows are reproducible; malformed syntax,
oversized content, path traversal, overwrite, and frozen-manifest edits fail;
rollback keeps both revisions and history; a refiner cannot call PCB, shell,
network, repository, witness, credential, or provider-switching tools.

### U13. Build the bounded OpenCode act → measure → classify → resume runner

**Depends on:** P1, P2, U11 and U12; preserve the current relay behavior in
`harness-lab/run_zen_trials.py`.

**Owned files:** `harness-lab/run_buck_trials.py`,
`harness-lab/continual_host.py`, `harness-lab/test_buck_runner.py`,
`harness-lab/test_continual_integration.py`, and focused updates to
`harness-lab/TRIAL-INPUTS.md` and `harness-lab/README.md`.

Implement the three existing phases and the outer loop around one attempt:
start fresh isolated OpenCode/XDG/interpreter state, relay admitted MCP calls,
perform the independent native measurement, classify with the Rust contract,
and invoke refinement only at the frozen mutation boundaries. On a transport or
driver interruption, resume only after proving the worker is still alive and
its state hash is unchanged; a worker crash or killing timeout consumes the
attempt as `indeterminate` and retains evidence without reconstructing state.
Never reset the board, deadline, or edit budget during an eligible resume. Do
not run development/evaluation unless qualification and
engineering receipts are current and pass the prior gate. Freeze a development
inheritance manifest before any reserved trial and reject reserved output as a
source.

Test scenarios: preflight remains inspection-only and exact tool/model schemas
are enforced; one scripted attempt reaches measure/classify/refine/resume with
the same board and reduced deadline while the worker survives; a worker crash
or killing timeout preserves completed actions but becomes indeterminate;
transport failure cannot be retried without a liveness proof; all four development and six evaluation
slots appear exactly once; each condition receives the same frozen context;
qualification drift, stale engineering evidence, missing inheritance, and no
usable revision block launch with explicit receipts.

### U14. Add optional host-boundary trace export

**Depends on:** U13; telemetry is strictly downstream of authoritative receipt
creation.

**Owned files:** `harness-lab/telemetry.py`,
`harness-lab/test_telemetry.py`, and minimal wiring in
`harness-lab/run_buck_trials.py` and `harness-lab/README.md`.

Provide a no-op local exporter by default and an opt-in adapter for the
configured LangSmith/OpenTelemetry backend. Span attributes may identify run,
attempt, phase, revision digest, model, tool call, duration, and classification;
redact auth headers and credential-bearing payloads. Export attempts are
bounded and isolated from the result path: exporter import, credential,
connection, serialization, or shutdown failures become telemetry diagnostics
only. Do not add a tracing dependency to the Rust judge or require network
access for local operation. Follow OpenCode's documented host/server boundary
and existing relay rather than replacing the runtime.

Test scenarios: disabled/no-credential mode performs no network operation;
successful export receives only redacted metadata; a fake backend timeout or
exception leaves byte-identical authoritative receipts and exit status;
oversized payloads are dropped with a local diagnostic; telemetry cannot alter
classification, budgets, retries, or inheritance.

### U15. End-to-end controls and operator evidence

**Depends on:** U11–U14. This unit may run synthetic controls while U6–U10
remain scientifically blocked.

**Owned files:** `harness-lab/test_buck_runner.py`,
`harness-lab/test_continual_integration.py`,
`harness-lab/test_failure_classification.py`,
`harness-lab/CONTINUAL-HARNESS.md`,
`harness-lab/evidence/continual-harness-controls-20260909/README.md`.

Exercise the real process boundaries with at least one scripted-provider
integration that performs real full-buck native actions in the real sandboxed
persistent interpreter and reaches the Rust judge. Add deterministic fake
OpenCode/native endpoint controls for transport faults, worker death, and
exporter failure. Prove revised executable skill use, alive-worker-only
same-state recovery, frozen cross-trial inheritance, and telemetry failure
isolation. Document coverage in new `CONTINUAL-HARNESS.md` and link it from the
clean `harness-lab/README.md`; do not edit the already-dirty engineering
coverage document, add live model results, or alter prior evidence files.

## Dependency graph and sequencing

```text
P1 full-buck ops -> P2 sandboxed interpreter -> U11 contract -> U12 artifacts
                                                       |             |
                                                       +------> U13 runner -> U14 telemetry
                                                                         \-> U15 controls
```

Review P1/P2 before claiming the continual loop is executable. Review U11's
schemas before U12; review artifact immutability before U13;
review the runner's synthetic end-to-end controls before enabling any external
provider call. U6–U10 from the authoritative plan remain prerequisites for a
qualified reference and U5 live scoring, but do not block implementation of
these local controls. A full-buck pilot remains blocked until engineering
requirements, exact circuit/component evidence, qualified simulation, and
layout/reference admission pass independently.

## Verification contract

Run the focused Python unit suites for U11–U15, then `make -C harness-lab
build check` and the import boundary gate. Use fresh ignored output directories
for runner demonstrations. Verify that all authoritative JSON is reproducible
from retained local inputs, that no protected existing files were modified,
and that `git diff --check` is clean. Before any actual trial, require current
qualification/engineering receipts, a successful inspection preflight, a
reviewed frozen inheritance manifest, and an operator decision that the
engineering gates are satisfied. A synthetic-control pass is evidence of
control behavior only and cannot qualify the buck or enable U5.

## Definition of Done

P1/P2 full-buck and sandbox prerequisites are either implemented and proven or
report an explicit environment blocker. U11–U15 focused tests demonstrate
revision use, alive-worker-only state/deadline-preserving recovery,
deterministic failure
classification, frozen inheritance, and exporter failure isolation. Existing
profiles and protected evidence remain unchanged; receipts distinguish control
demonstrations from qualified experiments. No live full-buck trial is admitted
without the prior engineering gates.

## Risks and explicit blockers

The OS sandbox boundary and persistent interpreter required by U3 may be
unavailable; this blocks live runner use but does not invalidate schema/storage
controls. OpenCode or MCP transport changes may require adapting the relay;
do not silently fall back to another provider or runtime. The solver remains
pinned to the existing free OpenCode model; Luna authors implementation only,
and no paid model or provider fallback is permitted. LangSmith/OTEL
credentials and network backends may be absent; telemetry remains optional and
must not block local operation. The current engineering qualification gaps
(unresolved product limits, component derating evidence, exact-device model
qualification, and requalified layout reference) remain true blockers for live
full-buck scoring. No model qualification or physical validation may be
inferred from these software controls.

## Review result

The plan is implementation-ready with bounded scope, exact owned/test files,
Rust ownership for domain policy, explicit compatibility with U2/U3/U4 and
U5/U6–U10 gates, and independent controls for the three requested risks:
revised executable skill use, state/deadline-preserving recovery, and exporter
failure isolation. The only true blockers are runtime sandbox availability and
the pre-existing engineering admission evidence; neither requires changing
this plan or the authoritative prior contract.
