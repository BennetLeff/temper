---
title: Migration pipeline — the missing wire and retire stages
type: feat
date: 2026-08-11
topic: migration-pipeline-wire-and-retire
artifact_contract: ce-unified-plan/v1
artifact_readiness: requirements-only
execution: code
product_contract_source: measurement
status: draft
swept: null
swept_basis: null
---

# Migration Pipeline — Wire and Retire

## Goal Capsule

**Objective:** Add the two stages [`../migration-pipeline.md`](../migration-pipeline.md)
is missing — **wire** (make production call the Rust) and **retire** (remove the
Python the Rust replaced) — and drain the backlog both omissions have already
accumulated.

**The defect, stated precisely.** The pipeline's stage 3 (`work`) checklist has
seven items: differential test, behavioural A/B, performance A/B, PBT,
metamorphic relations, induction proof, Rust idioms. Every one proves the Rust
is **correct**. None makes it **used**, and none removes what it replaced.
Stages 4–6 (`code-review`, `verify`, `land`) are process, not lifecycle. The
word "oracle" appears once in the whole document (line 31); "retire",
"sunset" and "delete the Python" appear zero times.

**The consequence, measured.** Each migration emits four artifacts — the Rust
kernel, the Python original (still called), a permanent Python oracle, and a
differential test. **Every migration therefore increases total code.** As of
this plan: 293,983 LOC Rust against 172,119 LOC production Python (665 files,
via `scripts/check_migration_narrowing.py::production_py_files`), with
`router_v6/` alone still 30,617 LOC across 102 Python files, only 51 of which
delegate to any Rust crate.

> **AMENDED 2026-08-11 after U2 (#1018) — this paragraph's original claim was
> wrong.** It read: *"107 registered kernels sit in `.unwired-kernel-inventory`
> with no production caller"*, and framed that as migration backlog. Triage of
> all 107 against their real call sites returned **WIRE: 0**,
> NEVER-WIRE-BY-DESIGN: 70, ORPHANED-DELETE: 37. There is no wiring backlog.
> **38 of the 107 are in fact already wired** — through runtime
> `PyModule::import` / `getattr` / pyo3 rename aliases that
> `scripts/check_unwired_kernels.py`'s Python AST scan structurally cannot see.
> The rest are deliberate non-callers (typed introspection and PBT surfaces) or
> dead weight from completed shim retirements and marshaler collapses.
>
> So the ledger's headline number is substantially an artifact of the detector,
> not a measure of unwired work. That does **not** invalidate the plan's core
> thesis — the pipeline still has no wire stage and no retire stage, and stage 7
> is still worth having for the migrations that come next. It does mean the
> *evidence* for the thesis is the pipeline's own text (see the stage-3
> checklist), not this count. The still-live consequence is U5's: 50,141+ LOC of
> Python oracles with no retirement criterion.
>
> A secondary finding worth acting on separately: a gate with ~35% false
> positives, made PR-blocking in #1004, will train readers to dismiss it. The
> false positives are individually ledgered with reasons so they do not block a
> merge, but the detector's blind spot to cross-extension and dynamic wiring
> should be recorded in its own docstring.

**Why this is urgent rather than tidy.** Because nothing retires per-kernel,
cleanup has happened instead as periodic bulk deletion passes driven by import
scans. On 2026-08-11 one such pass (`47349a50d`) deleted
`router_v6/pad_connectivity_audit.py` — the project's own declared PRIMARY
routing-completion metric — because its scan covered `src/` and `tests/` but
not `scripts/`. `scripts/route_board.py:269` calls it unconditionally, so
`make route` died with `ImportError` and the true completion figure was
unmeasurable for three days (restored in #1008). **Per-kernel retirement is
safer than bulk deletion**, because at retirement time the pipeline knows
exactly which Python the Rust replaced; a later import scan does not. The
deletion passes exist because the pipeline abdicated the job.

## Product Contract

### Summary

Two new stages are appended to the migration pipeline and enforced by gates
that already exist or are cheap to add:

- **Stage 7 — wire.** Repoint the production caller at the Rust kernel; prove
  it via `scripts/check_unwired_kernels.py` (made PR-blocking in #1004); delete
  the now-dead Python *implementation*. The oracle is **not** touched here.
- **Stage 8 — retire.** Once the differential has held for a defined bar,
  dispose of the oracle by one of three routes (below) and delete the
  differential's Python dependency.

### Oracle disposition — three routes, not two

The migration's own value depends on the oracle being an **independent**
implementation. Translating a Python oracle into Rust *from the Rust
implementation* yields two copies of the same bug and reports green — strictly
worse than no oracle. So "port the oracles" is not by itself a safe
instruction. Each oracle takes exactly one of:

| route | when | effect |
|---|---|---|
| **FREEZE** — snapshot oracle outputs over a fixed input corpus into golden vectors, delete the Python, keep the differential against the frozen vectors | default; the kernel is deterministic and its input domain is enumerable or samplable | regression signal retained, Python deleted, test becomes wasm32-tier-executable |
| **REIMPLEMENT** — write an independent Rust oracle **from the specification**, never from the Rust implementation | continuous adversarial differential value is high: safety kernels (creepage, clearance, via/keepout geometry) | independence retained in Rust; costs a genuine second implementation |
| **KEEP** — retain the Python oracle | CPython *is* the reference (comparing against a Python library's exact semantics, or a host-libm/`dlsym` property) | no change; must carry a written reason |

FREEZE is expected to be the large majority. It is the same mechanism the WASM
verification tier already relies on (deterministic seeded corpora standing in
for randomized exploration), so it introduces no new machinery.

### The retirement bar

Retirement needs a criterion, and the repo already has one that works: **R19
sustained agreement** — the WASM tier licenses a crate's native suite to leave
GitHub Actions after 100% per-test verdict agreement across 10 consecutive
`origin/main` commits, measured by
[`../../tools/wasm/u6_campaign.sh`](../../tools/wasm/u6_campaign.sh). Oracles
have no equivalent, which is the whole reason a differentially-proven kernel
keeps its oracle forever.

This plan adopts the same shape and the same number (10 consecutive commits,
zero differential disagreements) as the default bar, with REIMPLEMENT-class
safety kernels exempt — those keep a live differential indefinitely by design.

## Units

- **U1 — Amend `docs/migration-pipeline.md`.** Add stages 7 and 8 with their
  checklists; add the oracle-disposition table and the retirement bar to
  `## Hard rules`. Document that bulk import-scan deletion is **not** the
  retirement mechanism and cite `47349a50d` as the failure case. Smallest unit,
  unblocks the rest, and is the actual root-cause fix.

- **U2 — Triage the 107 unwired kernels.** Not 107 stalled migrations: the
  ledger already contains never-wire-by-design entries (`DrcComponentSnapshot`,
  `DrcNetClassRuleSnapshot` — typed introspection/PBT surfaces) and orphans
  (`DiffPairConfig` — the Python it replaced was itself deleted in `b1fd7edb6`).
  Partition into **WIRE** / **NEVER-WIRE-BY-DESIGN** / **ORPHANED-DELETE**, with
  a reason per entry, and encode the first two as inventory reasons so the
  distinction survives.

  **DONE 2026-08-11 (#1018). Result: WIRE 0 / NEVER-WIRE-BY-DESIGN 70 /
  ORPHANED-DELETE 37.** Every entry is now tagged in the ledger with a legend in
  its header. The five entries marked "needs triage" since #839
  (`DrillDefinition`, `evaluate_quality_py`, `net_currents`, `py_sum`,
  `tokenize`) plus `HypergraphBuildResult` were resolved against real call
  sites, and every entry whose name merely *looked* wireable was re-checked
  individually — `required_clearance_py` (its Python caller already delegates to
  a different, already-wired kernel), `parse_capacitance_rs` (the Python it
  would replace is a deliberate Rust-independent fallback; wiring it defeats the
  fallback), the `via_*` family (no matching step exists in the real algorithm).
  All resolved to NEVER-WIRE-BY-DESIGN.

- **U3 — Drain the WIRE partition.** ~~One kernel per commit; each repoints its
  production caller, runs the kernel's existing differential, and removes the
  now-dead Python implementation.~~ **NO-OP — U2 found zero WIRE candidates.**
  `check_unwired_kernels.py` reports the identical count before and after:
  `1011 registered kernel(s); 107 unwired, all ledgered`. Nothing to repoint.
  The unit is retained here rather than deleted so the next reader sees that it
  was executed and returned empty, not skipped.

- **U4 — Build the FREEZE tooling.** A generator that runs an oracle over a
  declared input corpus, writes golden vectors, and emits a Rust test asserting
  the kernel against them. This is the unit that makes retirement cheap enough
  to happen; without it every retirement is bespoke.

- **U5 — Retire the first oracle batch under the bar.** Pick kernels already
  long past 10 clean commits, apply FREEZE, measure the Python LOC actually
  deleted. Report the number honestly — the value of this plan is a
  **decreasing** production-Python figure, and if U5 does not move it, the
  approach is wrong.

- **U6 — Scope the Rust-driver endgame (investigation, not implementation).**
  Categories 2 and 3 of the "why is Python still here" question collapse if the
  top-level driver becomes Rust: pyo3 bindings exist to serve a Python consumer,
  `kicad-cli` is a subprocess callable from anywhere, `.kicad_pcb` is
  S-expressions, and `temper-orchestration`'s 51 integration tests import pyo3
  only because the code under test is exposed that way. The genuinely hard
  dependency is **CP-SAT via `ortools`** in `packages/temper-placer/src/temper_placer/placer/cp_sat/`.
  In-tree precedent exists for Rust solving (`rustsat` + `rustsat-cadical` in
  `temper-rust-router-core`), but SAT is not CP-SAT and the gap must be costed,
  not assumed. Deliverable is a costed assessment, not a migration.

## Scope Boundaries

- **Does not delete any oracle outside U5's measured batch.** An oracle without
  a recorded disposition stays.
- **Does not touch the WASM tier's R19 machinery** — it is borrowed as a model
  and cited, not modified.
- **Does not implement the Rust driver** (U6 is assessment only).
- **Does not run bulk import-scan deletion.** That mechanism is what this plan
  exists to replace.

## Dependencies / Assumptions

- `scripts/check_unwired_kernels.py` is PR-blocking as of #1004 — U3's progress
  depends on that remaining true.
- ~~**Assumption to verify in U2, not assumed here:** that a meaningful fraction
  of the 107 are genuinely WIRE-able. If triage finds they are overwhelmingly
  never-wire-by-design, U3 shrinks to near nothing and the backlog framing in
  this plan's Goal Capsule is wrong — say so and amend.~~
  **RESOLVED 2026-08-11 (#1018): the assumption was FALSE.** Zero of the 107 are
  WIRE-able; 38 are already wired invisibly to an AST scan. The Goal Capsule has
  been amended accordingly. Recorded here rather than deleted because the
  assumption being wrong is the useful part — it is why U2 was written as a
  triage gate in front of U3 instead of U3 being started directly, and the same
  discipline should apply to the next count this plan family quotes.
- FREEZE assumes deterministic kernels. Any kernel whose output depends on host
  facilities (`dlsym`/libm) or entropy is KEEP or REIMPLEMENT by construction —
  the WASM tier's existing exclusion classes (`no-entropy-source`,
  host-facility) already enumerate these.

## Outstanding Questions

- **Q1 — Is 10 commits the right bar for oracles?** It is the WASM tier's
  Phase-1 *licensing* bar; that plan notes it "can be raised later (e.g., to 50
  commits for Phase 5 gating)". Deleting an oracle is less reversible than
  moving a test suite between runners, which argues for a higher bar. Open.
- **Q2 — Do frozen golden vectors decay?** A frozen corpus cannot discover a
  bug in an input region it never sampled. This is the same unreachable-branch
  risk the tier has hit four times (geometry keepout, thermal overlap-area,
  quality-oracle IPC-2221 bracket, io-types special values). U4 must carry
  non-vacuity guards measuring the fraction of non-trivial cases, or FREEZE
  reproduces a known failure at scale.
- **Q3 — What is the real irreducible CPython core?** U6 answers this. The
  honest prior is that it is much smaller than the current 172k LOC, and
  possibly limited to the CP-SAT boundary.

## Sources / Research

- [`../migration-pipeline.md`](../migration-pipeline.md) — stages 1–6; the
  document this plan amends.
- [`../wave4-discipline-contract.md`](../wave4-discipline-contract.md) — the
  stage-3 gate checklist.
- [`../../.unwired-kernel-inventory`](../../.unwired-kernel-inventory) — the 107.
- [`../evidence/2026-08-11-python-deprecation-inventory.md`](../evidence/2026-08-11-python-deprecation-inventory.md)
  — DEAD/SHIM/PARTIAL/LIVE/RETAINED classification; 50,141+ LOC of retained
  oracles across 153 files.
- [`../plans/2026-08-07-001-feat-wasm-tier-phase1-plan.md`](./2026-08-07-001-feat-wasm-tier-phase1-plan.md)
  §U6 — the R19 sustained-agreement bar this plan borrows.
- `47349a50d` and PR #1008 — the bulk-deletion failure that motivates U1.
