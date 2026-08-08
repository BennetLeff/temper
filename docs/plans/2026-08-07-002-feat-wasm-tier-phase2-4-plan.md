---
title: WASM Verification Tier — Phases 2–4 Implementation Plan
type: feat
date: 2026-08-07
topic: wasm-tier-phase2-4
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
product_contract_source: ce-plan
execution: code
status: active
swept: 2026-08-07
swept_basis: "written directly against docs/evidence/2026-08-07-wasm-tier-phase2-4-status.md and docs/evidence/2026-08-07-reference-oracle-throughput-baseline.md, both merged into this worktree the same session; Phase 2 and Phase 4 units are gated on a maintainer decision (Q3, and Phase 4's de-scope) rather than landed"
---

# WASM Verification Tier — Phases 2–4 Implementation Plan

## Goal Capsule

- **Objective:** Turn Phases 2 (manufacturing variation), 3 (fault injection and
  mutation) and 4 (design-space variants) of
  `docs/plans/2026-08-03-002-feat-wasm-verification-tier-plan.md` into
  executable units with done-conditions and evidence artifacts — the same
  treatment Phase 0 and Phase 1 already received — **or, where the evidence
  gathered today does not support that, into a recorded de-scope decision with
  its reasoning and its reopening condition, rather than a unit list that
  papers over a phase with no stated question.** This plan enriches the parent
  plan's scope; it edits none of its Requirements or Decisions, and it edits
  neither `docs/wave4-verdicts.yaml` nor any `.github/workflows/*` file — the
  workflow unit below (§3) is a design for a future PR to implement, not a
  change this plan makes.
- **Product authority:** temper maintainer. This plan owns the execution shape
  of Phases 2–4 — what is built, in what order, what evidence closes each
  unit, and (for Phase 4) whether to build at all. It does not own the parent
  plan's D5 phase ordering, Q3's eventual answer, or anything already settled
  in Phase 0/Phase 1.
- **Open blockers:** Six, named rather than elided, because two of the parent
  plan's phase descriptions understate what is actually missing.
  1. **Phase 2 blocks on a fabrication-envelope model that exists nowhere in
     the repo.** The nearest adjacent code
     (`packages/temper-design-bundle/src/manufacturing_tolerances.rs`,
     exposed to Python as `temper_placer.manufacturing.tolerances`) is a
     per-feature etch/registration tolerance *table*, not a sweep surface —
     and its `ToleranceTable`/`FeatureTolerance`/`ToleranceAnalyzer` types
     embed `Py<PyAny>` fields and unconditional `use pyo3::prelude::*`
     (verified by inspection at `manufacturing_tolerances.rs:65-68`, no
     `#[cfg(feature = "python")]` anywhere in the file), so it cannot compile
     to `wasm32` in its current shape even as a starting point. The parent
     plan's own Q3 ("what a fabrication-envelope model contains... and where
     its values come from") is listed under "Resolve Before Planning" and is
     still unresolved. §4 below scaffolds the type-level shape and separates
     what can proceed today (portable data types) from what needs the
     maintainer (the tolerance values' source).
  2. **Phase 3's "R38 and R42 already in flight" claim is half true.** R38
     (board-defect mutation corpus) landed with code and evidence
     (`scripts/board_defect_mutator.py`, `scripts/check_board_defect_corpus.py`,
     `docs/evidence/2026-08-02-board-defect-corpus.md`). **R42's named files —
     `scripts/gate_mutate.py`, `scripts/check_gate_mutations.py` — do not
     exist.** `docs/plans/2026-08-02-035-feat-gate-mutation-testing-plan.md`
     fully specifies them but nothing has been built. Neither R38 nor R42
     runs on the tier's `wasm32` dispatch surface today.
  3. **Phase 4 has no multi-candidate placer mechanism, no Q-item, and its
     core dependency is excluded from `wasm32` by the parent plan's own Scope
     Boundaries** (the CP-SAT solve and SAT-backed router core). §6 recommends
     de-scoping it rather than writing units against a premise nothing
     supports.
  4. **The tier is not CI-wired in either direction.** `grep -rl
     "wrangler\|workers.dev" .github/workflows/*.yml` returns nothing, and
     every Phase 1 measurement (U1, U5, U6, U8) was a manual, researcher-driven
     sweep. §3 answers the goal-set's Q1 and designs (does not land) the
     wiring.
  5. **R7 is not well-posed as written**, and today's measurement
     (`docs/evidence/2026-08-07-reference-oracle-throughput-baseline.md`)
     supplies the oracle side but not the tier side. §2 restates R7 in a unit
     both systems can be measured against and makes measuring the tier's half
     an explicit unit rather than an assumption.
  6. **New Worker deployment or volume work (any unit that would extend
     Phase 1's 8 deployed Workers, or measure real Cloudflare cost) is
     blocked on the same Cloudflare-account/credentials gate Phase 1 recorded**
     — `wrangler` absent, Node v18 vs. the v22 the tooling wants, no API
     token. This gates *deployment* units specifically; it does not gate
     local (`wasmtime`/Node) volume measurement, exactly as Phase 1's own
     local-first ordering (D-decision in that plan's §6) already established.

---

## 0. State of Phases 2–4 on `origin/main` (verified 2026-08-07 at `7c35d251`)

This section is measurement, condensed from two evidence documents produced
earlier the same session and merged into this worktree for this plan:
`docs/evidence/2026-08-07-wasm-tier-phase2-4-status.md` (phase inventory, the
R4–R8 evidence map, the R8/#871 reachability analysis, the Q1 answer) and
`docs/evidence/2026-08-07-reference-oracle-throughput-baseline.md` (the R7
oracle-side measurement). Every claim below is either drawn directly from
those documents or independently re-checked against code at this commit; the
family-count figures in particular are re-measured here because the two
source documents and Phase 1's own verdict doc each cite slightly different
numbers, consistent with `AGENTS.md`'s repeated point that a measurement not
retaken at HEAD is not trustworthy.

### What exists (Phase 0/1 payload, for reference)

- `temper-drc-rs` builds for `wasm32-unknown-unknown`, zero imports, all six
  rule families reachable. `packages/temper-wasm-test-runner` dispatches 95
  registered tests, one per invocation.
- 8 Cloudflare Workers are deployed (`docs/evidence/2026-08-07-phase1-u8-multi-worker.md`):
  one full-corpus Worker plus seven per-family Workers at
  `temper-wasm-<family>.bennetleff.workers.dev`.
- **Re-measured directly against `tools/wasm/test_family_map.json` at this
  commit** (superseding both the phase2-4-status doc's `drc:1, emc:14, erc:9,
  safety:0, placement:12, routing:2, infra:109` and the deployed-Worker
  header comment in `tools/wasm/sweep_multi_worker.mjs`, both slightly
  stale): `drc: 1, emc: 16, erc: 0, safety: 10, placement: 10, routing: 2,
  dfm: 38, types: 16, integration: 2` — 95 tests total, 9 families. **`erc`
  still has zero registered tests; `drc` and `routing` remain thin (1 and 2
  respectively).** `safety` moved from 0 (as recorded in the phase2-4-status
  doc and the Phase 1 verdict) to 10 between that measurement and this one —
  the family counts are moving under concurrent work, not stable ground to
  plan against without re-checking. **Sharper confirmation of the same
  point, caught while regenerating this plan's own derived artifacts:**
  `uv run --no-sync python3 scripts/regen_derived.py`, run against this
  plan's own commit, reports `gen_wasm_test_registry.py` regenerating
  **147 tests across 25 modules** — `test_family_map.json`'s 95-entry count
  is stale *at the moment this plan was written*, undercounting the live
  registry by 52 tests with no family attribution for the difference. Every
  unit below that cites a family count must re-run both the registry
  generator and `test_family_map.json`'s own staleness check before sizing
  anything against these numbers.
- No workflow triggers any of this. No CI job invokes `wrangler`, a Worker
  URL, or a local `wasmtime`/Node sweep.

### Phase 2 — manufacturing variation: not started

No file in the repository contains the phrase "fabrication envelope."
`packages/temper-design-bundle/src/manufacturing_tolerances.rs` is the
nearest adjacent code — a per-feature tolerance *table* (etch tolerance by
copper weight, layer registration by layer type, solder-mask registration),
not a sweep surface, and its `ToleranceTable` struct is CPython-embedded
(`Py<PyAny>` fields, unconditional pyo3 use) rather than a portable Rust type.
`monte_carlo.py` and `stackup_validator.py` sit adjacent but neither
cross-references the wasm plan. Parent-plan Q3 (what the model contains, where
its values come from) is unresolved.

### Phase 3 — fault injection and mutation: R38 landed off-tier, R42 unbuilt

- **R38 (board-defect mutation corpus): implemented, off-tier.**
  `scripts/board_defect_mutator.py` uses `kiutils` to parse and mutate a
  `.kicad_pcb` copy; `scripts/check_board_defect_corpus.py` checks the result
  through `temper_placer.validation._drc_api.run_drc` — i.e. through
  `kicad-cli`. Neither is `wasm32`-portable as written: both depend on a
  Python KiCad file library and a native `kicad-cli` subprocess, not on
  `temper-drc-rs`'s rule kernels directly. Evidence:
  `docs/evidence/2026-08-02-board-defect-corpus.md`,
  `docs/evidence/2026-08-04-board-defect-corpus-uncovered-classes.md`.
- **R42 (gate-mutation testing): plan-only.**
  `docs/plans/2026-08-02-035-feat-gate-mutation-testing-plan.md` fully
  specifies `scripts/gate_mutate.py`, `ci-corpus/mutations.yaml`, and
  `scripts/check_gate_mutations.py`. **None of the three exist**
  (`find scripts -iname "*gate_mutate*" -o -iname "*check_gate_mutations*"`
  returns nothing at this commit), there is no `scripts/manifest.yaml` entry,
  and no evidence doc records a gate-mutation run.
- Nothing in `tools/wasm/test_family_map.json`'s 9 families references a
  defect-corpus or gate-mutation test name.

### Phase 4 — design-space variants: not started, no owning question

No file uses "design-space variant," "multi-candidate," or an equivalent term
for a pipeline holding N placer candidates for comparison. "Candidate
placement" in `packages/temper-placer` always names one working placement
under evaluation before commit. Unlike Phase 2, the parent plan names no
Q-item for Phase 4 at all — there is no open question recorded anywhere to
resolve before planning could even begin.

### R7 — the oracle side is now measured; the tier side is not

`docs/evidence/2026-08-07-reference-oracle-throughput-baseline.md`, produced
against the exact `kicad-cli 10.0.5` version CI pins
(`.github/docker/ci.Dockerfile:41`):

| Check | Single-process | At concurrency 8 (this machine, non-quiescent) |
|---|---|---|
| DRC (`pcb/temper.kicad_pcb`) | 0.86–0.96 whole-board checks/s | ~5.6 checks/s (73% scaling efficiency) |
| ERC (`pcb/temper.kicad_sch`) | 1.8–2.4 whole-schematic checks/s | ~12.7 checks/s (66% scaling efficiency) |

Against this, the tier's own published numbers (190,000 invocations at
~3,379 inv/s locally, 25–33 tests/s per Worker) count **atomic
rule-invocations** — one Rust `#[test]` function against one small fixture,
median 0.0012 ms — not whole-board passes. Dividing one by the other produces
≈3,900×, which the oracle-throughput document identifies as an artifact of
comparing incompatible units, not a real speed ratio. §2 restates R7 in units
both sides can be measured in and treats the tier-side measurement as an
explicit, currently-missing unit.

### Q1 and CI wiring — recommendation already reasoned, not yet wired

`docs/evidence/2026-08-07-wasm-tier-phase2-4-status.md` §5 recommends
continuous/scheduled execution over per-change, reasoning from the same
concurrency-pool argument D3 used to reject containers, and from
`.github/workflows/board-regeneration.yml`'s own header comment (nightly,
"a scheduled job does not contend... spending a slot [in the push-contended
pool] would be self-defeating"). This plan adopts that recommendation (§3)
and designs — does not land — the workflow that would act on it.

### Summary table

| Phase | Real blocker | What it gates | Can proceed today? |
|---|---|---|---|
| 2 — manufacturing variation | No fabrication-envelope model (Q3 unresolved) | Everything in Phase 2 past the type shape | Type scaffolding: yes. Sourcing values: no, needs maintainer (§4) |
| 3 — fault injection | R42's files don't exist; neither R38 nor R42 runs on the tier | Phase 3 "scaling" claim | R42 build: yes (existing plan). R38 port: yes (Phase 1 infra already lands). Volume run: yes, locally |
| 4 — design-space variants | No mechanism, no Q-item, core dependency excluded from `wasm32` | Everything | No — recommend de-scope (§6) |
| R7 (cross-cutting) | Tier-side board-equivalents/second unmeasured | R7's PASS/FAIL verdict | Yes, locally, no credentials needed |
| CI wiring / Q1 | No workflow exists in either direction | Continuous operation of any phase | Design only here; landing is a future PR |
| Worker deployment/cost | Cloudflare account/token not provisioned | New Worker units specifically | No — local units substitute |

---

## 1. Unit breakdown — track map

```
Track R (R7)     U-R1 ──> U-R2
                              \
Track Q (CI/Q1)  U-Q1          \
                    \            \
Track 2 (Phase 2) U2.1 ──> U2.2 ──> U2.3 ──> U2.4 ──> U2.5
                    (type)  (sourcing, (sweep    (canary)  (verdict)
                             maintainer  kernel)
                             decision)

Track 3 (Phase 3) U3.1 ────────────────> U3.3 ──> U3.4 ──> U3.5
                   (R42 build)            (port R42)(volume)(verdict)
                   U3.2 ─────────────────────────────┘
                   (port R38, independent of U3.1)

Track 4 (Phase 4) — no units; §6 is a de-scope record, not a track.
```

Track R gates neither Phase 2 nor Phase 3's *build* work, but it gates
whether Phase 2's sweep can be sized sensibly (U2.3 needs a throughput number
to know what sample count is affordable) and it gates any claim that Phase 3
"scales" fault injection rather than merely running it once more. Track Q
gates *continuous* operation of anything built here; it gates nothing about
whether the units can be built and evidenced as one-off local measurements
today — exactly the local-first pattern Phase 1 already established.

---

## 2. Track R — R7 restated, and the tier's missing half

### R7, restated

The parent plan's R7 reads: *"Sustained DRC and ERC check volume exceeds what
the reference oracle can sustain by at least an order of magnitude."* As
written this compares atomic rule-invocations (the tier's only published
unit) against whole-board passes (`kicad-cli`'s only measurable unit) — two
different denominations with no established conversion factor, per the
oracle-throughput document's §7. **This plan adopts that document's proposed
restatement as R7's operative form:**

> **R7 (restated).** Sustained **board-equivalents per second** — where one
> board-equivalent is the full set of tier rule-invocations required to check
> one instance of `pcb/temper.kicad_pcb` (respectively `pcb/temper.kicad_sch`
> for ERC) end to end — exceeds the reference oracle's measured
> whole-board/whole-schematic checks-per-second by at least an order of
> magnitude, both sides measured on the same board content and, ultimately,
> in the same enforcing environment (per the goal-set plan's AE3).

This does not edit the parent plan's R7 text; per this plan's own
instructions and the pattern Phase 0's §5 and Phase 1's §7 already
established, a restatement belongs in the executing plan's "what this plan
believes is wrong or underspecified upstream" section (§9) with the
maintainer deciding whether to fold it back into the parent plan.

#### U-R1. Measure the tier's board-equivalents/second

**Goal.** Supply the half of R7's ratio that
`docs/evidence/2026-08-07-reference-oracle-throughput-baseline.md`
explicitly left open: how many tier rule-invocations are needed to check one
real instance of `pcb/temper.kicad_pcb`, and at what rate can the tier
sustain that.

**Why.** Without this number, "10×" cannot be evaluated in either direction —
the oracle-throughput document is explicit that dividing raw
invocations/second by raw checks/second "produces a number that looks like a
slam-dunk 10× claim" but is an artifact.

**What changes.** This is measurement, not new production code, but it needs
an instrumentation point that does not exist today: `run_wasm_tests.mjs` (or
a new companion script) driven against a **real board input** rather than
the fixed synthetic fixtures the 95 registered tests use, counting how many
distinct rule evaluations fire when checking `pcb/temper.kicad_pcb` end to
end. Two viable approaches, cheaper first:

1. **Approximate from the family map.** Every DRC/ERC-family test currently
   exercises a synthetic fixture, not the production board. Multiply the
   per-family test count by an estimated "checks per test" factor derived
   from what each test's assertions cover (e.g. a `clearance` family test
   that iterates all component pairs on a fixture of N components scales to
   the production board's actual component count). This is an estimate, not
   a direct count, and must be labeled as such — the point is a defensible
   lower bound, not a precise figure.
2. **Instrument `temper-drc-rs`'s rule-evaluation entry points directly**
   (a counter incremented once per rule-vs-item-pair evaluation, gated
   `#[cfg(feature = "wasm-test-registry")]` so it never ships in the
   production `.so`), run once against a `BoardState` built from the real
   board via `tools/wasm/r2_serialize_board.py` +
   `packages/temper-drc-rs/src/board_py_bridge.rs`, and report the exact
   count. This is the rigorous option and should be preferred if U2's Track 2
   work (which also needs a real-board rule pass, for the envelope sweep) is
   being pulled around the same time — the instrumentation is reusable.

**Files touched**
- New: `tools/wasm/r7_board_equivalent.py` (or a Rust example binary under
  `packages/temper-drc-rs/examples/`, mirroring the R2 cost-model pattern) —
  counts rule-evaluations for one full pass over the real board and reports
  the tier's median invocations-per-board-equivalent and, combined with the
  existing per-invocation timing from Phase 1's U5, the implied
  board-equivalents/second.
- New: `docs/evidence/<date>-r7-tier-board-equivalents.md`.

**Evidence that closes U-R1:** the evidence doc states, for the real
`pcb/temper.kicad_pcb` (re-hashed at measurement time, not the transcribed
sha256 from an earlier document, per the pattern R2's own text insists on):
the rule-evaluation count for one board-equivalent, the method used (§1 or §2
above, stated explicitly), and the derived board-equivalents/second at
measured per-invocation throughput.

**Blocked by:** nothing technical. Can run locally, no Cloudflare credentials
needed — the same local-first ordering Phase 1 already used for its own
volume measurement. **Blocks:** U-R2.

#### U-R2. Compute and record the R7 verdict

**Goal.** Divide the two now-comparable numbers and record PASS/FAIL against
the restated ≥10× bar.

**Files touched:** `docs/evidence/<date>-r7-verdict.md`.

**Content:** the oracle-side table from §0 (already measured), the tier-side
number from U-R1, the ratio, and one of:

> **R7 (restated) PASS.** Board-equivalents/second on the tier exceeds
> `kicad-cli`'s measured whole-board rate by ≥10×, both measured on
> `pcb/temper.kicad_pcb` at commit `<sha>`.

or

> **R7 (restated) NOT YET MET / FAIL.** [state the ratio and why].

**Caveat that must be stated regardless of outcome:** both sides were
measured on a workstation, not in the environment that would enforce R7 (no
CI job invokes either side today — see §3). Per the goal-set plan's AE3, a
threshold is not considered measured until taken where it is enforced; U-R2's
verdict is a workstation measurement pending §3's wiring, and the evidence doc
must say so rather than implying a CI-grade result.

**Blocked by:** U-R1. **Blocks:** nothing structural in this plan, but it is
the input the Phase 2 sizing decision (U2.3) and any future "the tier
replaces `kicad-cli`" argument (R6/D7's retirement trajectory) will need.

---

## 3. Track Q — Q1 answered, and the CI-wiring unit

### Q1 — does scaled checking run per-change or continuously?

**Answer: continuously, scheduled — matching
`board-regeneration.yml`'s nightly, off-pool precedent. Today it runs
neither.** This plan adopts the recommendation and reasoning already recorded
in `docs/evidence/2026-08-07-wasm-tier-phase2-4-status.md` §5, restated here
because the goal-set plan requires this plan to answer it directly rather
than by reference:

1. **Per-change reintroduces exactly the coupling the tier was chosen to
   escape.** D3 rejected Cloudflare containers over Workers specifically
   because "the board regenerates on every harness change, so checking must
   be continuous," and the account's own concurrency ceiling (~24 jobs
   against ~40 requested by a single push, recorded independently in four
   workflow files) is the reason a *push-triggered* job was rejected for the
   board-regeneration producer in Phase 0's own U7. The same argument applies
   unchanged to the WASM tier's own trigger: putting a Worker sweep on the
   push path would put its latency and flakiness back on the merge critical
   path, which is the entire reason D3 chose Workers over containers.
2. **The one existing continuous-shaped precedent in this repo already made
   this exact argument and is scheduled, not per-PR.**
   `.github/workflows/board-regeneration.yml`'s header: a scheduled job "does
   not contend with push-triggered jobs for the account's ~24 concurrent
   runner ceiling; it runs when no push is in flight." This is the pattern to
   extend, not reinvent.
3. **R19's sustained-agreement protocol needing per-commit granularity is a
   measurement-method requirement, not a deployment-cadence requirement.**
   Phase 1's U6 walks 10 consecutive commits to attribute a disagreement to
   the commit that caused it; that does not imply the *production* tier must
   re-run on every commit, only that the comparison protocol, when invoked,
   needs to know which commit it is comparing. A nightly sweep against
   whatever is at `origin/main` HEAD when the schedule fires satisfies R19's
   attribution need exactly as well as a per-push trigger would, at zero pool
   cost.

**Consequence for this plan's phases:** Phase 2's envelope sweep and Phase
3's mutation volume runs are each designed below to be runnable as **local,
one-off measurements first** (matching Phase 1's own local-before-Worker
ordering) and **wired to the nightly cadence second**, once U-Q1 lands. No
unit in Phase 2 or 3 depends on U-Q1 to produce its first evidence document;
U-Q1 is what turns a one-off sweep into a standing, continuously-refreshed
one.

#### U-Q1. Design a nightly trigger for the tier (not landed by this plan)

**Goal.** Specify the workflow that would drive the tier's existing local
sweep and/or its 8 deployed Workers on the same schedule pattern as
`board-regeneration.yml`, so that whoever executes this plan has a
ready-to-implement design rather than a recommendation to re-derive.

**Explicitly not done by this plan:** creating or editing any
`.github/workflows/*` file. This unit is a specification for a future PR.

**Design.**
- **Trigger:** `schedule` (nightly, off-peak UTC, at a time slot distinct
  from `board-regeneration.yml`'s 05:00 UTC and the other named nightly jobs
  in that workflow's own header comment) + `workflow_dispatch`. **Not**
  `push`, **not** `pull_request` — per the Q1 reasoning above.
- **What it runs, in order:**
  1. `node tools/wasm/sweep_multi_worker.mjs --concurrency 64 --json
     <artifact>` against the 8 already-deployed Workers, **if** Cloudflare
     credentials are available to the runner (they are not, today — see the
     Goal Capsule's blocker 6). This step is designed to be skippable: a
     missing credential is a `skip`, not a failure, exactly as Phase 1's own
     U7/U8 treated the Cloudflare gate.
  2. Independent of step 1's outcome, a **local** `wasmtime`/Node sweep
     (`node tools/wasm/run_wasm_tests.mjs --repeat <K>`) that needs no
     credentials at all and therefore always runs — this is what keeps the
     nightly cadence meaningful even before Cloudflare is provisioned.
  3. The R19 comparison protocol from Phase 1's U1/U6, comparing the night's
     wasm32 verdicts against that commit's native `cargo test` verdicts, so
     the sustained-agreement measurement (currently a manual 10-commit walk)
     becomes a standing nightly data point instead of a one-time study.
- **Job-count argument (required, per Phase 0's U7 precedent):** +1 scheduled
  job, +0 push-contended jobs. Runner-minute cost is the local sweep's
  duration (Phase 1's U5 measured 190,000 invocations in 56.2 s locally) plus
  whatever the Worker sweep costs when credentials exist — both well inside
  the ~30-minute budget `board-regeneration.yml` itself uses as its
  precedent.
- **Hard prohibitions, matching Phase 0's U7 pattern:** never commits a
  result file that looks like a baseline artifact without the same
  measurement-provenance discipline `check_measurement_provenance.py`
  enforces elsewhere in this repo; `permissions: contents: read` unless a
  result genuinely needs to be persisted, in which case it goes through the
  same review discipline as any other committed measurement.

**Evidence that would close U-Q1 when implemented:** the workflow green on a
manual `workflow_dispatch` run, and — per this repo's own
`scripts/check_vacuous_gates.py` precedent — a demonstrated red run (a
planted failing test, or a `workflow_dispatch` credential-skip path exercised
deliberately) so the schedule is proven to bite rather than being a gate that
cannot fail.

**Blocked by:** nothing technical for the local-only path (step 2). The
Worker path (step 1) is blocked on Cloudflare credentials, same as Phase 1's
U7/U8. **Blocks:** nothing in this plan structurally, but every phase's
"continuous, not manual-sweep" claim depends on this landing eventually.

---

## 4. Phase 2 — manufacturing variation

### Recap of the real blocker

Phase 2's parent-plan text says it "requires a fabrication-envelope model
that does not exist yet." §0 above confirms this is exactly true and goes
further: the nearest adjacent code (`ToleranceTable` et al.) is not a
starting point in its current form, because it is a CPython-embedded pyclass
data model, not a portable Rust type — the same G1/G3 gap Phase 0 diagnosed
in `temper-drc-rs` and fixed there, unfixed here. And the parent plan's own
Q3 — what the model contains, where its values come from — is listed under
"Resolve Before Planning," not "Deferred to Planning," meaning the parent
plan itself does not consider Phase 2 plannable without an answer. This
section separates what can proceed without that answer (the type shape) from
what cannot (the tolerance values themselves).

### U2.1. A portable `FabricationEnvelope` type — shape only, no values sourced yet

**Goal.** Define, in a `wasm32`-portable Rust crate, a data type that names
the tolerance axes a manufacturing-variation sweep would perturb, mirroring
the axes `ToleranceTable` already names for a different purpose (etch,
registration) plus the axes Q3's own framing in the parent plan implies
(trace-width/spacing bands, copper-thickness variation, drill tolerance) —
**without** asserting real values for any of them yet.

**Why.** The type shape is a design decision independent of where the
numbers come from, and blocking the whole phase on Q3's resolution when the
shape work can proceed is the same mistake Phase 0's G3 finding warned
against (gating a whole surface out because one piece is missing, when the
missing piece is smaller than the whole).

**What it contains, explicitly separating "known shape" from "value TBD by
maintainer":**

| Axis | Shape (known) | Value source (open — Q3) |
|---|---|---|
| Etch tolerance | per copper weight (0.5/1/2 oz), µm over/under-etch | `ToleranceTable`'s existing defaults (0.025/0.05/0.075 mm) are placeholders seeded for a Python differential test, **not sourced from this board's actual fab's capability sheet** — flagged, not assumed correct |
| Layer registration | per layer type (outer/inner), offset range | Same caveat — `ToleranceTable`'s 0.1/0.15 mm defaults are unverified against a real fab capability doc |
| Copper thickness variation | per layer, ± around nominal weight | Not modeled anywhere today; shape must be added new |
| Drill tolerance | per hole diameter class, ± range | Not modeled anywhere today; shape must be added new |
| Solder-mask registration | single scalar (already in `ToleranceTable`) | Same caveat as etch/registration |

**Files touched**
- New: a `FabricationEnvelope` struct in a portable location — either a new
  module in `temper-drc-rs` (if the sweep kernel that consumes it belongs
  there) or a new small crate, decided by whoever executes this unit based on
  where U2.3's sweep kernel needs it. **Explicitly does not touch**
  `manufacturing_tolerances.rs` or its `python`-feature-gated pyclasses — this
  is a new, portable type, not a retrofit of the existing CPython-embedded
  one (retrofitting it is a larger, separate migration this unit does not
  scope).
- New: `docs/evidence/<date>-phase2-envelope-shape.md` — records the table
  above, cites every value's source (or explicitly "no source, TBD"), and
  states plainly that the shape is proposed, not the parent plan's Q3 answer.

**Evidence that closes U2.1:** the type compiles under `cargo check --target
wasm32-unknown-unknown --no-default-features` (rung 1 only — U2.1 is a shape
proposal, not yet wired to anything that would need rung 2/3), and the
evidence doc's source table is complete (every axis has an entry, even if the
entry is "TBD, needs maintainer").

**Blocked by:** nothing technical. **Blocks:** U2.2 (which needs the shape to
know what values to ask the maintainer for), U2.3.

### U2.2. Resolve Q3's value-sourcing question — a maintainer decision, not an engineering unit

**Goal.** State the question precisely enough that the maintainer (or a
follow-up session with fab-capability data in hand) can answer it in one
sitting, and record whatever interim default this plan uses if no answer
arrives before Phase 2 is pulled.

**Why this is not a normal unit.** Nothing in this repository names the
board's actual PCB fabricator or that fabricator's stated process
capabilities. `ToleranceTable`'s constants are, per its own module docstring
in `packages/temper-placer/src/temper_placer/manufacturing/tolerances.py`,
values reproduced bit-identically from a **pre-migration Python
implementation** for differential-testing purposes — there is no citation
trail from those numbers back to a fab capability document, and this plan
did not find one anywhere in the repo. Sourcing real tolerance bands is a
procurement/vendor-data question, structurally similar to the goal-set
plan's board-design-completeness goal (R11–R15), which `docs/STRATEGY.md`
already says should not be delegated to an agent.

**The question, stated for the maintainer:**
> For each axis in U2.1's table: is `ToleranceTable`'s existing default an
> acceptable stand-in for this board's actual fabricator's process
> capability, or does a real capability sheet exist (or need requesting) that
> should replace it? If no real data is available, is a documented
> conservative placeholder (e.g., IPC-2221 generic Class 2 tolerances)
> acceptable for a first sweep, clearly labeled as not fabricator-specific?

**Files touched:** appends the answer (or its absence, with a stated
interim default) to `docs/evidence/<date>-phase2-envelope-shape.md`.

**Evidence that closes U2.2:** either a maintainer-provided answer recorded
verbatim, or — if Phase 2 is pulled before that answer arrives — an explicit
interim-default decision recorded with its caveat ("not fabricator-verified,
Phase 2's findings under this default are bounds on relevance, not
fabrication-ready numbers").

**Blocked by:** U2.1 (needs the axis list). **Blocks:** U2.3 (the sweep
kernel needs real, even if provisional, values to perturb geometry by).

### U2.3. Envelope-sweep kernel

**Goal.** For N sweep samples (either a grid over the envelope's axes or a
Monte Carlo draw, matching the existing `monte_carlo.py` pattern's shape),
perturb the relevant board geometry within the envelope and re-run the
`temper-drc-rs` rule kernels against each perturbed instance, reporting
pass/fail per sample and per rule family.

**Why this is scoped as perturbation, not simulation.** Per D6's "coverage,
not defect count" framing and Q7's "CPU is effectively free" finding from
Phase 0 (median 4 ns/kernel case), a full manufacturing-physics simulation is
not needed to get sweep value — a bounds-based perturbation (trace width at
etch tolerance's extremes, layer offset at registration's extremes) already
answers the question Phase 2 exists to ask: does nominal-geometry DRC/ERC
passing survive the fabrication envelope's edges, or does it only pass at the
nominal (impossible-in-practice) exact geometry?

**Sizing the sweep.** U-R1/U-R2's board-equivalents/second number is the
input that tells this unit what N is affordable within a nightly budget —
this unit does not invent a sample count independent of that measurement.

**Files touched**
- New: sweep driver, location decided alongside U2.1's crate placement.
- New: `docs/evidence/<date>-phase2-sweep-results.md` — per-family
  pass/fail-under-perturbation counts, N, and the envelope values used
  (citing U2.2's answer).

**Evidence that closes U2.3:** the sweep runs to completion, N is stated and
justified against U-R2's throughput number, and results are reported per
rule family (not only aggregate pass/fail), matching R7's own "per kernel and
per rule family" framing.

**Blocked by:** U2.2 (needs real values), and informed by (not strictly
blocked by) U-R2 (needs a throughput number to size N sensibly — proceeding
without it means guessing N, which is discouraged but not impossible).
**Blocks:** U2.4.

### U2.4. Demonstrated-failing-case canary (R8/D6 non-vacuity)

**Goal.** Show the sweep can fail: construct a perturbation at the envelope's
extremes (maximum under-etch combined with maximum registration offset in the
same direction) that is known, by hand calculation against the board's
narrowest declared clearance, to violate a safety-critical clearance/creepage
rule that the nominal-geometry board passes.

**Why.** `scripts/check_vacuous_gates.py` exists because a coverage claim
with no demonstrated failing case recurs in this repository; D6 makes
demonstrated kill capability the explicit antidote. A sweep that always
reports "still passes" is indistinguishable from a sweep that checks
nothing.

**Evidence that closes U2.4:** one recorded case where the sweep's
worst-case perturbation trips a rule the nominal board passes, with the hand
calculation that predicted it, in
`docs/evidence/<date>-phase2-sweep-results.md`.

**Blocked by:** U2.3.

### U2.5. Phase 2 verdict

**Goal.** One document, one table, one sentence, matching Phase 0/1's U9
pattern.

**Content:** a table of U2.1–U2.4's verdicts, followed by exactly one of:

> **Phase 2 established.** The fabrication-envelope model (values per U2.2's
> [maintainer answer / interim default]) sweeps the board and demonstrates at
> least one failing case the nominal board does not surface. Phase 3 or
> continued Phase 2 work may proceed.

or

> **Phase 2 blocked on Q3.** No maintainer answer arrived; the interim
> default's findings are recorded as bounds on relevance only, not
> fabrication-ready results, and are not to be treated as a burn-down input
> under R12/R13 until real values replace them.

**Blocked by:** U2.1–U2.4.

---

## 5. Phase 3 — fault injection and mutation

### Recap: what "already in flight" actually means

R38 (board-defect mutation corpus) is real, landed, and evidenced — but it is
a Python/`kiutils`/`kicad-cli`-shaped script, structurally incompatible with
`wasm32` as written (it parses and mutates board files with a pure-Python
KiCad library and checks the result through a `kicad-cli` subprocess, neither
of which can run inside a Workers isolate). R42 (gate-mutation testing) has a
complete implementation-ready plan
(`docs/plans/2026-08-02-035-feat-gate-mutation-testing-plan.md`) and zero
landed code. Phase 3's "scales the seeded-defect work already in flight"
framing is accurate about R38's *existence* and wrong about its *readiness
for the tier* — porting is not a small step, because the whole mechanism
needs re-expressing against `temper-drc-rs`'s rule kernels directly instead of
against `kicad-cli`.

### U3.1. Land R42 per its existing plan

**Goal.** Build `scripts/gate_mutate.py`, `ci-corpus/mutations.yaml`, and
`scripts/check_gate_mutations.py` exactly as
`docs/plans/2026-08-02-035-feat-gate-mutation-testing-plan.md` U1/U2 already
specify.

**Why this plan does not re-specify R42's units.** That plan is
implementation-ready on its own terms (mutation axes, manifest schema, engine
design, test scenarios) and this plan's job is to name it as Phase 3's
prerequisite, not duplicate it. Re-deriving it here would risk drifting from
its own KTD1–KTD5 decisions.

**Evidence that closes U3.1:** whatever that plan's own U1/U2 evidence
closure requires — this plan treats "R42 landed" as the state where those
files exist, are registered in `scripts/manifest.yaml`, and have at least one
recorded mutation run per that plan's success signal (every fail-closed gate
has ≥1 registered mutation whose canary flips pass→fail under the mutation).

**Blocked by:** nothing on this plan's critical path — independently
pullable today, exactly as
`docs/evidence/2026-08-07-wasm-tier-phase2-4-status.md`'s next-step #7
already found. **Blocks:** U3.3.

### U3.2. Port R38 onto the tier's `wasm32` dispatch surface

**Goal.** For each of the three named defect classes (component off-board,
pad short, creepage crossing), add a `#[cfg(feature = "wasm-test-registry")]`
Rust test to `temper-drc-rs` that constructs the mutated board fixture
in-process (not via `kiutils`/file mutation) and asserts the owning rule
kernel fails on the mutated fixture and passes on the clean one — replacing
`kicad-cli` as the verdict oracle with `temper-drc-rs`'s own rule, which is
exactly the substitution the full-board DRC oracle differential
(portfolio R11) already validates is trustworthy for exact-match cases.

**Why this is real porting work, not a thin wrapper.**
`scripts/board_defect_mutator.py` mutates a `.kicad_pcb` file on disk via
`kiutils`; the tier's tests construct a `BoardState` in Rust directly (the
same structure `board_py_bridge.rs` builds). The three defect classes need
re-expressing as direct `BoardState` construction/perturbation rather than
file-level mutation — component off-board is a coordinate change, pad short
is two components' coordinates converging, creepage crossing is a
high-voltage/low-voltage net pair's clearance shrinking below the declared
creepage requirement. None of this is large per class, but none of it is
"just register the existing script" either.

**Files touched**
- New: test modules under `packages/temper-drc-rs/src/` (location follows the
  existing per-rule-family module convention), each with `WASM_TESTS` consts
  per `gen_wasm_test_registry.py`'s existing pattern.
- Regenerate `packages/temper-drc-rs/src/wasm_test_registry.rs` via
  `scripts/gen_wasm_test_registry.py`.
- New: `docs/evidence/<date>-phase3-r38-tier-port.md` — records, per defect
  class, the mutated-fails / clean-passes verdict, and cross-references the
  original R38 evidence doc's violation-count deltas to show the ported
  version reproduces the same finding by a different mechanism.

**Evidence that closes U3.2:** all three defect classes registered and
dispatchable, each demonstrated to fail its owning gate when mutated and pass
when clean, run once locally via `run_wasm_tests.mjs` and once (if
credentials exist) via a deployed Worker.

**Blocked by:** nothing beyond Phase 1's already-landed dispatch
infrastructure. **Blocks:** U3.4.

### U3.3. Port R42 onto the tier's dispatch surface

**Goal.** Same pattern as U3.2, applied to whatever gate-mutation manifest
entries U3.1 produces — each (gate, mutation, canary) triple that names a
`temper-drc-rs` rule as the gate becomes a `wasm-test-registry` test
asserting the canary flips under the mutation.

**Scope note.** Not every `ci-corpus/mutations.yaml` entry U3.1 produces will
name a rule inside `temper-drc-rs` — R42's plan covers gates generally (CI
scripts, thresholds outside the rules engine). Only the subset whose gate
*is* a `temper-drc-rs` rule is portable to the tier's dispatch surface by
this mechanism; the rest stay CI-only, and this unit's evidence doc must
state the split rather than silently porting a partial set and calling it
complete.

**Files touched:** same pattern as U3.2; a new
`docs/evidence/<date>-phase3-r42-tier-port.md` recording the ported/not-ported
split.

**Blocked by:** U3.1 (R42 must exist to have anything to port). **Blocks:**
U3.4.

### U3.4. Volume run and agreement measurement for ported mutation tests

**Goal.** Run the ported R38/R42 tests at volume (mirroring Phase 1's U5/U6
local-first protocol) and confirm every mutation canary still flips
correctly across repeated invocations — this is Phase 3's actual
differentiator over Phase 1's existing R19 measurement, which only proves the
*pre-existing* tests agree between native and `wasm32`, not that the *new*
mutation canaries survive at scale or across commits.

**Protocol:** identical in shape to Phase 1's U5 (`--repeat K`,
fresh-instantiation-per-invocation, deterministic verdict check across
repetitions) applied to the U3.2/U3.3 test subset specifically, plus a
10-commit sustained-agreement walk (Phase 1's U6 protocol) once at least 10
commits have touched the ported tests.

**Evidence that closes U3.4:** `docs/evidence/<date>-phase3-volume.md` with
throughput, determinism-across-repetitions, and (once available) the
10-commit agreement figure.

**Blocked by:** U3.2, U3.3. **Blocks:** U3.5.

### U3.5. Phase 3 verdict

Same pattern as U2.5 — one table, one sentence:

> **Phase 3 established.** R38 and R42 both run on the tier's dispatch
> surface at volume, [N] canaries demonstrated to flip under mutation,
> sustained agreement [SUSTAINED / NOT YET] over [span]. Findings route into
> the burn-down per D8/R12.

or the corresponding incomplete form naming which unit did not close.

**Blocked by:** U3.1–U3.4.

---

## 6. Phase 4 — design-space variants: recommended de-scope

### The value case, examined rather than assumed

Phase 4's stated goal is turning "DRC and ERC into a selection signal" across
multiple placer candidates. Evaluating whether this is worth building against
what today established:

1. **No mechanism exists to generate multiple candidates.** Every recent
   board change came from a human-gated CP-SAT re-solve with candidate
   selection at the human's judgment, not an automated multi-candidate
   pipeline. Building one is placer/CP-SAT work, not tier work, and the
   parent plan's own Scope Boundaries exclude the CP-SAT solve and the
   SAT-backed router core from `wasm32` entirely — so even a built
   multi-candidate generator could not run its *generation* step on the
   tier; only the *scoring* of already-generated candidates could.
2. **The premise that place-and-route quality is the thing worth optimizing
   is directly contradicted by this project's own strategy document, quoted
   in the parent plan's Scope Boundaries: "Autorouter quality work beyond
   what R16 requires... `docs/STRATEGY.md` records that place-and-route was
   not the bottleneck."** Phase 4's entire value proposition is a better
   selection signal over placer candidates — exactly the category of work
   that document already deprioritized.
3. **The single-candidate path Phase 4 would need to run N times doesn't
   complete once, today.** §0's R8 discussion (and
   `docs/evidence/2026-08-07-wasm-tier-phase2-4-status.md` §4) establishes
   that `route_pcb()` fails via both its code paths on the production board —
   an OOM on the path every producer uses, and a newly-exposed O(n²)
   skeleton-connectivity blowup on the other. Comparing N candidates
   presupposes generating even 1 reliably, which is not true today.
4. **Unlike Phase 2, the parent plan names no Q-item for Phase 4 at all.**
   Phase 2 at least has Q3 naming what's missing and inviting it to be
   resolved. Phase 4 has nothing to resolve — there is no open question on
   record, which means there is also no evidence anyone has scoped what
   "done" would even look like.

### Why this plan recommends de-scoping

Every other phase in this plan names a real, gate-relevant question it would
answer if built: Phase 2 asks whether nominal-geometry DRC/ERC passing
survives real fabrication tolerance (a safety-relevant question directly on
`docs/STRATEGY.md`'s critical path — creepage and clearance margins are named
protection-gate concerns). Phase 3 asks whether the gates that protect the
board actually bite, at volume (the trust-the-trust question D6 exists to
answer). **Phase 4 asks whether a selection mechanism the project has not
built, running on generation infrastructure explicitly out of `wasm32` scope,
over a router that cannot currently produce one reliable candidate, would
improve outcomes in a dimension (place-and-route quality) the project's own
strategy document says is not the bottleneck.** The DESAT brief's
de-scoping recommendation is the precedent this plan follows: a plan that
must recommend building something is not a plan, and building unit
breakdowns against a phase with this cost-benefit profile would be exactly
that.

**Recommendation: de-scope Phase 4 from the tier's active roadmap.** This
plan writes no units for it.

### What a future reopening would need

Not built here, recorded so the door is not silently closed:

1. A named Q-item in the parent plan (there is none today) stating what
   "design-space variant" means precisely enough to scope against — what
   generates a candidate, what "compares" means (a scalar score? a Pareto
   front over DRC violation count and some other axis?), and why that
   comparison is worth the SAT-router-generation cost `docs/STRATEGY.md`
   already deprioritized once.
2. `route_pcb()` completing reliably at least once (Phase 2/3's honest
   dependency chain already needs the router's health improved for other
   reasons — see §0's R8 discussion) — a prerequisite this plan does not
   scope, since it is router-quality work tracked separately (the same
   `_ensure_skeleton_connectivity` redesign the merged status document names
   as next-step #6).
3. A maintainer decision that place-and-route selection quality has become
   worth prioritizing again, reopening the `docs/STRATEGY.md` judgment this
   plan is not authorized to overturn.

---

## 7. Sequencing summary

| Unit | Blocked by | Blocks | Evidence that closes it |
|---|---|---|---|
| U-R1 tier board-equivalents/s | — | U-R2 | Evidence doc: rule-eval count, method, derived throughput |
| U-R2 R7 verdict | U-R1 | Phase 2 sizing (informal) | Ratio + PASS/FAIL/NOT-YET-MET, with the workstation-not-CI caveat |
| U-Q1 nightly trigger design | — | Continuous operation of any phase (design only, not landed) | Design recorded; implementation is a future PR |
| U2.1 envelope type shape | — | U2.2, U2.3 | `cargo check --target wasm32-unknown-unknown`; source table complete |
| U2.2 Q3 value sourcing | U2.1 | U2.3 | Maintainer answer or explicit interim-default record |
| U2.3 sweep kernel | U2.2 | U2.4 | Sweep completes; per-family results; N justified against U-R2 |
| U2.4 sweep canary | U2.3 | U2.5 | One demonstrated worst-case failing case, hand-calc + measured |
| U2.5 Phase 2 verdict | U2.1–U2.4 | — | Verdict doc |
| U3.1 land R42 | — | U3.3 | Per `2026-08-02-035`'s own U1/U2 closure |
| U3.2 port R38 to tier | — | U3.4 | 3 defect classes registered, mutated-fails/clean-passes shown |
| U3.3 port R42 to tier | U3.1 | U3.4 | Ported/not-ported split recorded; canaries demonstrated |
| U3.4 mutation volume run | U3.2, U3.3 | U3.5 | Throughput + determinism; 10-commit agreement once available |
| U3.5 Phase 3 verdict | U3.1–U3.4 | — | Verdict doc |
| Phase 4 | — | — | **De-scoped; no units.** §6 is the record. |

**What can proceed today, with no blocker at all:** U-R1, U2.1, U3.1, U3.2.
**What is blocked on a maintainer decision, not engineering:** U2.2 (Q3's
value sourcing), and by extension everything downstream of it in Phase 2.
**What is blocked on Cloudflare credentials specifically (not on anything
else):** only the Worker-deployment half of U-Q1's design and the
Worker-side verification steps inside U3.2/U3.4 — the local halves of all of
these proceed without it, matching Phase 1's own local-first precedent.

---

## 8. Non-goals

Drawn from the parent plan's Scope Boundaries and from what today's evidence
establishes is not worth pursuing yet:

- **Any new Worker deployment or Cloudflare spend.** Blocked on credentials;
  every unit above that needs a Worker specifically marks it optional and
  substitutes a local measurement.
- **Editing `.github/workflows/*`.** U-Q1 is a design, not a landed workflow.
- **Retrofitting `manufacturing_tolerances.rs`'s existing `ToleranceTable`
  pyclasses into a portable type.** U2.1 builds a new, separate portable
  type; migrating the existing CPython-embedded one is a larger Wave 4-shaped
  migration this plan does not scope.
- **Building Phase 4's multi-candidate mechanism, or any unit toward it.**
  §6 recommends de-scoping; this plan writes no implementation units for it.
- **Redesigning `_ensure_skeleton_connectivity` or fixing #871's OOM.**
  Named as a dependency for the router's own literal R8 path and for any
  eventual Phase 4 reopening, but scoped as separate router-quality work, not
  this plan's.
- **Editing the parent plan, the goal-set plan, `docs/wave4-verdicts.yaml`,
  or any measurement baseline (`power_pcb_dataset/drc_ceiling.json`).**
  Anything this plan finds wrong with them is recorded in §9, not edited in
  place.
- **Re-running `docs/evidence/2026-08-07-router-silent-noop-diagnosis.md`'s
  bisection or invoking `route_pcb()` on the production board.** Both source
  evidence documents this plan draws on already treat that as verified and
  explicitly avoided re-running it given the OOM/long-hang risk; this plan
  does not either.

---

## 9. What this plan believes is wrong or underspecified upstream

1. **R7's text conflates two different units and cannot be evaluated as
   written.** §2 restates it as board-equivalents/second and supplies the
   oracle-side measurement; the tier-side measurement (U-R1) is new work this
   plan defines but does not perform. **Suggested amendment to the parent
   plan:** replace R7's text with the board-equivalents/second framing once
   U-R2 produces a verdict.
2. **Phase 2's paragraph understates its own prerequisite's size.** "Requires
   a fabrication-envelope model that does not exist yet" reads like a
   one-line gap; §0/§4 establish that the nearest adjacent code is not a
   usable starting point (CPython-embedded, no cfg gating) and that the
   values themselves have no sourcing trail anywhere in the repo — this is a
   two-part blocker (shape + values), and the values half is a maintainer
   decision this plan cannot close on its own.
3. **Phase 3's "already in flight" framing is materially misleading about
   R42.** "Scales the seeded-defect work already in flight under portfolio
   R38 and R42" reads as if both exist and only need scaling. R42 does not
   exist. **Suggested amendment:** Phase 3's description should say "R38
   landed off-tier; R42 is plan-only" rather than treating both as
   equally in-flight.
4. **Phase 4 has no owning Q-item, unlike every other phase.** Phases 0–3 (via
   Q1–Q9 and Q3 specifically) each have at least one named open question in
   the parent plan. Phase 4 has none, which this plan reads as corroborating
   evidence that it was never scoped seriously in the first place, not as an
   oversight to quietly fix by adding one — §6 recommends de-scoping instead
   of retroactively inventing the missing Q-item.
5. **The parent plan's D5 ordering ("tooling correctness, then manufacturing
   variation, then fault injection, then design-space variants") assumed all
   four phases were equally worth reaching eventually.** Today's evidence
   does not support that assumption uniformly — Phase 2 and Phase 3 each
   answer a real question the project's own strategy document cares about;
   Phase 4 does not clearly answer one that hasn't already been
   deprioritized. This plan does not edit D5 (it is user-directed,
   session-settled), but flags that D5's ordering implicitly treats Phase 4
   as "later," and this plan's finding is closer to "maybe never, pending a
   Q-item that doesn't exist yet."

---

## 10. What could not be verified

Stated plainly, matching Phase 0/1's own convention:

- **Whether `ToleranceTable`'s default etch/registration values (0.025–0.075
  mm, 0.1–0.15 mm) trace back to any real fabricator's capability sheet.**
  Searched the module docstring, the crate, and `docs/` for a citation; found
  none. Treated in §4 as an open sourcing question (U2.2) rather than an
  assumed-correct baseline.
- **The exact runner-minute cost of a nightly Worker sweep once credentials
  exist.** Phase 1's U8 measured a real Worker volume run's cost at small
  scale; extrapolating to a recurring nightly cadence over months was
  explicitly flagged as an estimate, not a commitment, in that plan's §5
  item 6, and this plan inherits that same uncertainty for U-Q1's Worker
  half.
- **Whether the family-count figures cited in §0 (drc:1, emc:16, erc:0,
  safety:10, placement:10, routing:2, dfm:38, types:16, integration:2) will
  still match by the time any unit above executes.** They were re-measured
  directly against `tools/wasm/test_family_map.json` at this plan's own
  commit and already disagree with two other documents written the same
  session (the phase2-4-status doc and `sweep_multi_worker.mjs`'s header
  comment) — family counts are moving under concurrent work in this repo, and
  whoever executes a unit above should re-measure rather than trust this
  document's numbers past their measurement moment.
- **Whether U3.2/U3.3's per-defect-class port is small or large in practice.**
  Estimated as "not large per class, but not a thin wrapper either" from
  reading `board_defect_mutator.py`'s mutation logic; not attempted here,
  since this is a docs-only planning task.

---

## Sources / Research

- `docs/plans/2026-08-03-002-feat-wasm-verification-tier-plan.md` — the
  parent plan. Phased Path (Phase 2–4 paragraphs), D5, D6, Q3, Scope
  Boundaries (CP-SAT/SAT-router exclusion, autorouter-quality exclusion).
- `docs/plans/2026-08-04-002-docs-temper-goal-set-plan.md` — the goal-set
  plan. R4–R10, AE3, Outstanding Questions Q1.
- `docs/plans/2026-08-05-001-feat-wasm-tier-phase0-plan.md`,
  `docs/plans/2026-08-07-001-feat-wasm-tier-phase1-plan.md` — the structure
  and rigor this plan matches; U7's job-count-argument pattern, U9's verdict
  pattern, the local-first-before-Worker ordering this plan reuses in Track Q
  and Phase 2/3.
- `docs/evidence/2026-08-07-wasm-tier-phase2-4-status.md` — the status audit
  this plan is dispatched against: the phase inventory, the R4–R8 evidence
  map, the R8/#871 two-path reachability analysis, the Q1 recommendation and
  its reasoning, the next-step map. Merged into this worktree from
  `worktree-agent-acca281869a5601ab` (`b2400b67`) for this plan.
- `docs/evidence/2026-08-07-reference-oracle-throughput-baseline.md` — the R7
  oracle-side measurement (DRC 0.86–0.96/s single-process, 5.6/s at c8; ERC
  1.8–2.4/s, 12.7/s at c8) and the unit-mismatch finding this plan's §2
  restatement is built on. Merged into this worktree from
  `worktree-agent-a155a16122a1f08e9` (`7ba25800`) for this plan.
- `docs/evidence/2026-08-07-wasm-tier-phase1-verdict.md`,
  `docs/evidence/2026-08-07-phase1-u4-coverage.md`,
  `docs/evidence/2026-08-07-phase1-u5-volume.md`,
  `docs/evidence/2026-08-07-phase1-u8-multi-worker.md` — Phase 1's landed
  payload, family-coverage figures (re-measured independently in §0), and the
  local-first ordering decision this plan reuses.
- `docs/plans/2026-08-02-024-feat-board-defect-mutation-corpus-plan.md` (R38,
  landed) and `docs/plans/2026-08-02-035-feat-gate-mutation-testing-plan.md`
  (R42, plan-only) — Phase 3's two named dependencies; the latter's own U1/U2
  this plan's U3.1 references rather than re-specifies.
- `scripts/board_defect_mutator.py`, `scripts/check_board_defect_corpus.py` —
  R38's `kiutils`/`kicad-cli`-dependent implementation, read to establish why
  it is not directly `wasm32`-portable.
- `packages/temper-design-bundle/src/manufacturing_tolerances.rs`,
  `packages/temper-placer/src/temper_placer/manufacturing/tolerances.py`,
  `monte_carlo.py`, `stackup_validator.py` — the nearest existing tooling to
  Phase 2's fabrication-envelope model, and why it is not itself that model
  (`Cargo.toml`'s `python` feature is optional at the crate level but
  `manufacturing_tolerances.rs` uses pyo3 unconditionally with no internal
  `#[cfg]` gate).
- `.github/workflows/board-regeneration.yml` — the nightly, off-pool
  precedent U-Q1's design extends; its header comment's job-count argument,
  reused verbatim in reasoning.
- `tools/wasm/test_family_map.json`, `tools/wasm/sweep_multi_worker.mjs` — the
  family-count figures in §0, re-measured directly and found to disagree
  slightly with the two source evidence documents and each other.
- `docs/plans/README.md`, `scripts/gen_repo_state.py` — the plan-index
  frontmatter schema and generator this plan's frontmatter conforms to.
