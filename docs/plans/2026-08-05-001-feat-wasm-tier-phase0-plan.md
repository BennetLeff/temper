---
title: WASM Verification Tier — Phase 0 Implementation Plan
type: feat
date: 2026-08-05
topic: wasm-tier-phase0
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
product_contract_source: ce-plan
execution: code
status: active
swept: 2026-08-07
swept_basis: "Phase 0 of the wasm-verification-tier plan; superseded in scope by Phase 1 (2026-08-07-001-feat-wasm-tier-phase1-plan.md) which is now the active execution unit"
---

# WASM Verification Tier — Phase 0 Implementation Plan

## Goal Capsule

- **Objective:** Turn Phase 0 of `docs/plans/2026-08-03-002-feat-wasm-verification-tier-plan.md`
  (R1, R2, R3) into executable units with gates, and produce a **single recorded
  verdict** that either upholds D3 (Cloudflare Workers) or reopens it. This plan
  enriches that artifact's scope; every Key Decision there governs here, and no
  Requirement or Decision in it is edited by this plan or by anyone executing it.
- **Product authority:** temper maintainer. This plan owns only the *execution
  shape* of Phase 0 — what is built, in what order, what evidence closes each
  unit. It does not own R1/R2/R3's content, D3's disposition, or anything in
  Phases 1–4.
- **Open blockers:** One, and it is the reason this plan exists in its current
  shape. **Phase 0 is roughly half-landed already, and the landed half proves
  less than its requirements' text claims.** R1 was closed by `cargo check`,
  which does not link. R2's amendment measures three geometry kernels and an
  arithmetic memory projection, not a full-board rule pass and not peak resident
  memory. R3's producer is blocked on a router that does not execute on `main`.
  Details and evidence in §0.

---

## 0. State of Phase 0 on `origin/main` (verified 2026-08-05 at `0718a0943`)

This section is measurement, not planning. Every unit below is sized against it.

### What has landed

| PR | Commit | What it established |
|---|---|---|
| #656 | `bcfd3272e` | `temper-drc-rs`: `pyo3` optional behind `python` (default-on). `cargo check --target wasm32-unknown-unknown --no-default-features` exit 0. |
| #659 | `f9cbd8fde` | `temper-geometry`: same, plus `dlsym` math resolution gated `#[cfg(not(target_arch = "wasm32"))]` and a `getrandom` `js` shim for `wasm32`. |
| #658, #660 | `10d65cc93`, `7ca89702a` | Same treatment for `temper-dsn`, `temper-ipc`, `temper-quality-oracle`, `temper-thermal` — **beyond R1's named scope**, useful later. |
| #661 | `eb24b9557` | `temper-rust-router-core`: `rustsat`/`rustsat-cadical` optional behind a default-on `sat` feature. `temper-constraint-compiler` forwards it (`sat = ["temper-rust-router-core/sat"]`). |
| #663 | `f20d605eb` | `packages/temper-geometry/examples/r2_cost_model.rs` — the measurement R2's text now cites. |
| #667 | `57838465e` | Clippy runs `--all-features` across all 15 crate manifests. |
| #669 | `550cab2a3` | `docs/plans/2026-08-04-001-feat-board-regeneration-proposal.md` — Q2 answered, R3 scoped. |
| #675 | `5c03cdcc5` | `docs/evidence/2026-08-04-board-regeneration-cost.md` — R3 cost measured; router found broken. |

### What that leaves open — the five gaps this plan closes

**G1. R1's evidence level cannot detect R1's own failure mode.**
Both #656 and #659 verified with `cargo check`. `cargo check` runs the front end;
it does **not** run codegen and does **not** link. Both crates contain
`unsafe extern "C" { fn dlsym(...) }` declarations
(`packages/temper-drc-rs/src/validation.rs:81-95`,
`packages/temper-geometry/src/pad_geometry.rs:47-56`, and the same pattern in
`grid_raster.rs`). An undefined host symbol reaching a `wasm32-unknown-unknown`
build surfaces at **link** time, not at check time. Those blocks happen to be
`cfg`-gated out today, so the claim is probably true — but the *instrument used
to establish it* is structurally incapable of catching the class of defect the
crates actually carry. No `.wasm` artifact has ever been produced from either
crate.

**G2. No CI job keeps R1 true.** `grep -rn "wasm32" .github/workflows/` returns
**nothing**. The `wasm32` build is a point-in-time claim from 2026-08-03 with no
regression guard, in a repo whose `AGENTS.md:90-92` records that `main` has no
branch-protection required checks at all. Any commit can silently un-prove R1.

**G3. `--no-default-features` removes more than `pyo3`, and nothing measures
what is left.** Both PRs gated at *module* granularity where per-item gating was
awkward. `packages/temper-drc-rs/src/validation.rs` — 922 lines, ten migrated
DRC kernels (`tht_hole_collisions`, `trace_length`, `min_hv_lv_trace_clearance`,
`geometric_validate`, `compute_drc_penalty`, `group_violations`, …) — is
**entirely** `#[cfg(feature = "python")]`, including its `host_math` module.
`temper-geometry`'s `bridge.rs` (~1500 lines) and `congestion_tensor.rs` are
gated at their `mod` declarations; #659's own message records "expected dead-code
warnings for pyo3-only kernels that have no non-python caller." So R1 as closed
proves *a crate compiles*, not *the rules the tier exists to run are reachable
from `wasm32`*. A tier that compiles and can run nothing is the vacuous-gate
shape `scripts/check_vacuous_gates.py` exists to prevent and which the parent
plan names under D6/R8 as the largest risk it faces.

**G4. R2's landed measurement is not R2's stated subject.** R2 asks for
"per-case CPU cost and peak resident memory for **a full-board rule pass**."
`r2_cost_model.rs` benchmarks `box_box_distance`, `box_box_distance_aabb`,
`component_overlap_amount` and `compute_total_overlap` — four pure geometry
kernels in `temper-geometry` — and then *computes* an occupancy-grid size from
`side × side × 4 bytes × 6 layers`. No rule from `temper-drc-rs` executes in it.
No process's resident set is ever read. The 4 ns/case and 24 MB figures are
real and useful; they answer a narrower question than the requirement asks, and
the requirement's amended text now reads as satisfied.

**G5. R3 is blocked upstream, and the fix is not on `main`.**
`docs/evidence/2026-08-04-board-regeneration-cost.md` measured netlist at
11.46 s (N=4) and a full 120-sample `--all-track-errors` DRC pass at 417.9 s
(6.97 min, N=120, cross-machine-reproducing the committed ceiling exactly). It
found the route stage dead through all three entry points. The `NetClassRules`
`_mm` drift it diagnosed was subsequently fixed in `65c100c82` — which
`git merge-base --is-ancestor 65c100c82 origin/main` reports **is not an
ancestor of `origin/main`**. It sits on a feature branch. R3's producer still
has no working middle stage on `main` as of this writing.

---

## 1. Unit breakdown

Nine units in three tracks. **Track A (R1) and Track B (R2) gate every later
phase. Track C (R3) is independent and can run fully in parallel** — it shares
no file with A or B, and R2's "measured natively" wording means B does not wait
on A either.

```
Track A (R1)   U1 ──> U2 ──> U3
                 \             \
Track B (R2)   U4 ──> U5        \
                                 \
Track C (R3)   U6 ──> U7 ──> U8   \
                                   \
                                    U9  (verdict — needs U1,U2,U4,U5,U6)
```

`U4` deliberately does **not** depend on `U1`: R2 says "measured natively before
any Worker is written," so the cost model runs on the host and is unaffected by
whether the `wasm32` build links. This is what lets the two gating tracks run
concurrently, which matters because a FAIL in either reopens D3 and there is no
reason to discover that serially.

---

### Track A — R1: the substrate proof, and a guard that keeps it true

#### U1. Raise R1's evidence from `check` to a linked artifact and one executed rule

**Goal.** Replace the `cargo check` claim with a `.wasm` binary that exists on
disk and a rule verdict computed inside a WASM runtime that matches the native
verdict exactly.

**Why.** G1. `cargo check` cannot see link failures; the crates contain the
exact construct that produces them.

**What "compiles" means for R1 — three rungs, and the bar is rung 3.** This is
the definitional answer the parent plan does not give:

| Rung | Command | Catches | Status |
|---|---|---|---|
| 1 — type-checks | `cargo check --target wasm32-unknown-unknown --no-default-features` | Missing `cfg`s, non-portable APIs in signatures | **Landed** (#656, #659) |
| 2 — links | `cargo build --release --target wasm32-unknown-unknown --no-default-features` | Undefined host symbols (`dlsym`), missing intrinsics, `getrandom` misconfiguration | **Required by this unit** |
| 3 — executes | Load the `.wasm` in `wasmtime` and run one full rule against a fixture board slice | Runtime traps, unreachable, stack/memory limits, `getrandom` JS-glue absence in a bare `wasm32-unknown-unknown` host | **Required by this unit** |

Rung 3 is not optional and here is the concrete reason: `temper-geometry` pulls
`getrandom = { version = "0.2", features = ["js"] }` on `wasm32`, because
`transform.rs::gumbel_softmax` calls `rand::random()` unconditionally in a pure
kernel compiled in **both** feature configurations. The `js` feature satisfies
the *build*; at runtime it requires JS glue (`wasm-bindgen`) to be present. In a
bare `wasm32-unknown-unknown` module with no JS import object, a call into that
path traps. Rung 2 will pass and rung 3 will fail. Rung 1 already passes and
tells you neither.

**Files touched**
- New: `packages/temper-drc-rs/examples/r1_wasm_smoke.rs` — a `no_mangle`
  exported entry point taking a serialized board slice and returning a violation
  count, so the module has something callable that is not `main`.
- New: `tools/wasm/run_r1_smoke.sh` — builds rung 2, runs rung 3 under
  `wasmtime`, prints both verdicts, exits non-zero on mismatch.
- New: `docs/evidence/2026-08-05-r1-wasm-substrate-verdict.md`.
- No production source is expected to change. If it must, that change is itself
  part of the R1 verdict and is recorded as "R1 required N source changes,"
  because R1's premise is that the crates are *already* portable.

**Verification / evidence that closes U1**
1. `target/wasm32-unknown-unknown/release/*.wasm` exists for both crates; record
   byte size and the output of `wasm-objdump -x` (or `wasm-tools print | grep
   '(import'`) — **the import list is the artifact that matters**: a module with
   zero non-WASI imports is deployable to a Worker; one importing
   `__wbindgen_*` or `env.dlsym` is not.
2. One rule from each of the six families named in R5 (`drc`, `emc`, `erc`,
   `safety`, `placement`, `routing`) runs under `wasmtime` and returns a verdict
   **exactly equal** to the native run on the same input — same violation count,
   same violation identities, no tolerance. If a float differs in the last ULP
   and flips a threshold, that is the finding, recorded verbatim, and it does
   **not** fail R1 (the parent plan's Dependencies section already anticipates
   ULP divergence and R15 makes the tier advisory) — but it must be *recorded*,
   not absorbed.
3. The verdict document states one of exactly three outcomes (§2).

**Blocks:** U2, U3, U9.

---

#### U2. Measure the portable surface

**Goal.** Answer: *of the rule kernels and tests that exist, how many survive
`--no-default-features`?* Report the delta, per crate, per rule family.

**Why.** G3. R1 is satisfiable by a crate that compiles to `wasm32` with every
rule gated out. Nothing currently distinguishes that from success.

**What is measured**
- Per crate: `cargo test --no-run --no-default-features` vs
  `cargo test --no-run` (default features) — count the compiled test binaries'
  test functions in each configuration. The delta is the test surface the tier
  cannot run.
- Per rule family: for each of `drc`, `emc`, `erc`, `safety`, `placement`,
  `routing` in `packages/temper-drc-rs/src/rules/`, whether its module and its
  public entry point are reachable under `--no-default-features`.
- The known-excluded list, explicitly: `validation.rs` (922 lines, 10 kernels),
  `board_py_bridge.rs`, `bridge.rs`, `congestion_tensor.rs`, and anything else
  the measurement finds.

**Files touched**
- New: `tools/wasm/portable_surface.py` — runs the two `--no-run` builds, parses
  `--list` output from each test binary, emits a JSON delta. Ruff-clean.
- Appends a section to `docs/evidence/2026-08-05-r1-wasm-substrate-verdict.md`.

**Gate — this is the sharp one.** R1 is recorded **PASS** only if all six rule
families in R5 are reachable under `--no-default-features`. If any family is
gated out, R1 is **PASS-WITH-CAVEAT** and the caveat names the family and the
work to un-gate it (split the module into pure kernel + `#[cfg]` bridge, the
pattern #659 already used for eleven `temper-geometry` modules). A caveat does
**not** reopen D3 — it is scope discovered, not substrate failure — but it is
Phase 1's precondition and must be written down as such.

**Non-goal for U2:** do not un-gate anything. Measuring is the unit. Splitting
`validation.rs` is a follow-on with its own review.

**Blocks:** U3, U9. **Blocked by:** U1.

---

#### U3. The regression guard — one step, zero new job slots

**Goal.** Make R1 a standing property instead of a dated claim.

**Why.** G2. And because job count, not job duration, is this repo's binding CI
constraint.

**Design.** Append two steps to the **existing** `rust-checks` job in
`.github/workflows/python-tests.yml` (job defined at line 632, 45-minute
timeout, cold cargo target dir, already loops 15 manifests through clippy). Do
**not** create a new job.

```yaml
# after the existing "Clippy (all Rust crates, -D warnings)" step
- name: Install wasm32 target
  if: ${{ !cancelled() && steps.setup.outcome == 'success' }}
  run: rustup target add wasm32-unknown-unknown

- name: wasm32 substrate guard (R1)
  if: ${{ !cancelled() && steps.setup.outcome == 'success' }}
  run: |
    cargo build --release --target wasm32-unknown-unknown \
      --no-default-features -p temper-drc-rs -p temper-geometry
    cargo clippy --manifest-path packages/temper-drc-rs/Cargo.toml \
      --no-default-features --all-targets -- -D warnings
    cargo clippy --manifest-path packages/temper-geometry/Cargo.toml \
      --no-default-features --all-targets -- -D warnings
```

Two notes on that block. It is `build`, not `check`, because U1 established that
`check` cannot see the failure mode. And the `--no-default-features` clippy runs
are additive to #667's `--all-features` runs, not a replacement: `--all-features`
lints the union, `--no-default-features` lints the *wasm configuration*, and
neither implies the other. #659 shipped with known dead-code warnings in exactly
that configuration, so expect this to be red on first run and to require either
`#[cfg_attr]` allowances with reasons or (better) removal of the now-unreachable
code — which is U2's list.

**Job-count cost: zero.** This adds runner minutes to a job that already exists
and already compiles a cold dependency graph for 15 crates inside a 45-minute
budget. The `wasm32` build reuses the same `~/.cargo` registry; the marginal cost
is codegen for two crates against a new target triple. If the container image
`ghcr.io/bennetleff/temper-ci:latest` can be updated to pre-install the target,
the `rustup target add` step disappears entirely.

**Evidence that closes U3:** the guard is green on a PR, and a deliberate
break — a temporary commit adding an un-`cfg`'d `std::fs::read` to
`temper-drc-rs` — turns it red. Do not land the guard without demonstrating the
red. `scripts/check_vacuous_gates.py` exists in this repo because gates that do
not bite recur here.

**Blocked by:** U1, U2.

---

### Track B — R2: what a full-board rule pass actually costs

#### U4. Measure a full-board rule pass: per-case CPU and peak RSS

**Goal.** Produce the measurement R2's text asks for, natively, and keep the
existing `r2_cost_model.rs` figures rather than replacing them — they answer a
different, still-useful question about the geometry kernels.

**Why.** G4.

**Subject under measurement.** `pcb/temper.kicad_pcb` (1,032,079 bytes,
sha256 `51e39844b18aa37c84e4cc0b011acc51dc24cb1282359e1334ecbdf6ed07d9af` as
recorded in the R3 evidence doc — **re-hash at measurement time and record it;
do not trust the transcribed value**). One pass = every rule in every family in
`packages/temper-drc-rs/src/rules/` evaluated over the whole board.

**Protocol.**

- **Sampling.** N = 32 samples for the headline figure; N = 12 is the floor
  below which a figure is not reportable. Each sample is a **fresh process** —
  peak RSS is a high-water mark and does not reset within a process, so
  in-process repetition measures the max of the run, not of a pass. Report
  **median and full observed range**, never a mean; the repo's DRC evidence
  convention (`AGENTS.md:56-71`, and every board-write evidence doc) reports
  ranges because point values here have repeatedly been wrong.
- **Per-case CPU.** A "case" is one rule evaluation against one candidate
  geometry pair — the unit a property test generates and the unit Cloudflare
  bills. Report ns/case per rule family and the whole-pass wall time.
  `std::hint::black_box` on inputs and outputs, warmup of `N/10`, exactly as
  `r2_cost_model.rs` already does.
- **Peak resident memory.** `getrusage(RUSAGE_SELF).ru_maxrss`, read once at
  process exit. **`ru_maxrss` units differ by platform — bytes on Darwin, KiB
  on Linux.** Normalize explicitly in the code with a `#[cfg(target_os)]` and
  say so in the evidence doc, or the Linux/macOS numbers differ by 1024× and
  the 128 MiB comparison becomes nonsense.
- **Comparison.** **Exact, not tolerance-based.** Peak RSS ≤ 128 MiB, or it is
  over. `134217728` bytes is the number; `134217729` fails. This program has
  already had a result flip on a last-unit difference and the parent plan's own
  Dependencies section anticipates ULP divergence between native and WASM — a
  tolerance here would be the mechanism by which a real overflow is absorbed.
- **The margin that is not measured natively.** A native RSS figure is a *lower
  bound* on the isolate's requirement. A Worker's 128 MiB covers the WASM linear
  memory **plus** the runtime's own overhead, and WASM linear memory grows in
  64 KiB pages and does not return to the OS. Record the native number and state
  explicitly that the headroom against 128 MiB is what is being judged, not
  equality. Recommended reporting: native peak RSS, and the ratio to 128 MiB.
  **A pass consuming >50% of 128 MiB natively should be treated as FAIL pending
  an in-isolate measurement**, because the unmeasured overhead is not small.

**Files touched**
- New: `packages/temper-drc-rs/examples/r2_full_board_pass.rs`.
- New: `tools/wasm/r2_sample.py` — drives N fresh processes, collects
  median/range, emits JSON. Ruff-clean.
- New: `docs/evidence/2026-08-05-r2-full-board-cost.md`.
- **Explicitly not touched:** `power_pcb_dataset/drc_ceiling.json`,
  `power_pcb_dataset/metrics/perf_ab_baseline.jsonl`, or any other baseline.
  This unit measures cost, not correctness; it has no business writing a
  violation baseline.

**Evidence that closes U4:** the evidence doc, with the board hash, machine
context (the R3 doc's table is the format to copy), N, median, range, and an
exact PASS/FAIL against 128 MiB.

**Blocks:** U5, U9.

---

#### U5. Turn U4's numbers into the Q7 verdict

**Goal.** Say which of Q7's four memory strategies Phase 1 needs, and at what
grid resolution each becomes necessary. Build none of them.

**Why.** Q7 lists four candidates cheapest-first (bitmap packing, region
sharding, per-row RLE, hash-consed quadtree) and states the real obstacle is
mutation, not compression: the kernels write cell-by-cell via `merge_cell`,
while hash-consing needs immutability. That is a design constraint discovered
before design started, and it should not be re-derived.

**Output.** A table: for each resolution in {1.0, 0.5, 0.1, 0.05, 0.01} mm, the
measured (not projected) peak RSS of a full pass, and the cheapest Q7 candidate
that brings it under 128 MiB. Plus a one-line verdict.

**The likely answer, stated so nobody over-builds.** Production uses 1.0 mm at
131 call sites, 0.5 mm and 0.1 mm elsewhere, and nothing uses 0.01 mm. The
landed projection gives 24 MB at 0.1 mm across six layers. **"No memory strategy
is required for Phase 1" is a legitimate and probably correct verdict**, and
recording it that way is more valuable than picking a strategy speculatively.
Q7's candidates become live at Phase 2 (manufacturing variation wanting
sub-trace-width detail), which is not this plan's to schedule.

**Files touched:** appends to `docs/evidence/2026-08-05-r2-full-board-cost.md`.
Does **not** edit Q7 in the parent plan; the verdict doc is the input a
maintainer uses to close it.

**Blocked by:** U4. **Blocks:** U9.

---

### Track C — R3: the producer (independent of A and B)

#### U6. Re-verify the router at HEAD, and record the R3 gating verdict

**Goal.** Establish whether the route stage executes on `origin/main` *today*,
because `docs/evidence/2026-08-04-board-regeneration-cost.md` measured it broken
at `caa492f25` and the fix (`65c100c82`) is not an ancestor of `origin/main`.

**Procedure.** The repro block in that evidence document, §Reproduction, verbatim:

```bash
uv run python3 scripts/route_board.py --output /tmp/routed.kicad_pcb
```

- **If it still fails** (expected — `AttributeError: 'NetClassRules' object has
  no attribute 'via_diameter_mm'`): record it, and U7 is **deferred, not
  descoped**. Phase 0 exits with R3 marked BLOCKED-UPSTREAM and a named
  dependency: `65c100c82` (or equivalent) landing on `main`, plus un-masking
  `test_production_board_routing_drc_regression`, which currently runs under
  `continue-on-error: true` and has produced no signal for ~12 days.
- **If it now succeeds:** measure route wall time, N = 12 fresh processes,
  median and range. Then re-run the determinism protocol from
  `docs/evidence/2026-07-27-router-determinism.md`: 5 fresh processes, compare
  `sha256` of the output **exactly**. Record whether the 53.1%-vs-37.5%
  net-completion discrepancy that document flags as UNVERIFIED reproduces.

**Files touched:** `docs/evidence/2026-08-05-r3-router-status.md` only. No
production source, no workflow, no board file. `git status` must be clean after.

**Blocks:** U7, U9.

---

#### U7. The R3 CI producer — nightly, one job, discards its artifact

**Conditional on U6 clearing.** Build nothing here if the router is still dead;
shipping a nightly job whose middle stage is a known crash is precisely the
"gate that cannot bite" failure class.

**Trigger.** `schedule` (nightly, off-peak UTC) + `workflow_dispatch`. **Not**
`push`, **not** `pull_request`.

**Job-count justification — the required argument.** Four workflow files
independently record the same measurement: an account concurrency ceiling of
~24 jobs against ~40 requested by a single push
(`required-checks.yml:19`, `codeql.yml:20`, `literal-removal-advisory.yml:11`,
`python-tests.yml:684-685`). A new **push-triggered** job would take a slot from
that contended pool — and D3's entire justification for choosing Workers is that
this pool is the constraint, so spending it here would be self-defeating.

A **scheduled** job does not contend: it runs when no push is in flight, and
GitHub's concurrency accounting is per-moment, not per-day. The cost is runner
minutes, which are not the binding constraint here. Measured budget:
11.46 s netlist + route (unmeasured, bounded by a single SAT solve over a fixed
placement) + 417.9 s for a full 120-sample DRC pass ≈ **under 30 minutes**,
comparable to `r9-evidence.yml`'s 30-minute budget and a sixth of
`corpus-batch.yml`'s 180. In CI, drop DRC to **N = 12** (~42 s) rather than 120;
120 is the *ceiling re-measurement* protocol and this job never writes a ceiling.

Net: **+1 scheduled job, +0 push-contended jobs.** That is the whole cost
argument and it should be restated in the workflow's header comment, matching
how the other four workflows record theirs.

**What "verifies the pipeline still produces a valid board" asserts — concretely.**
Five assertions, in order, and **none of them is a byte diff**:

1. **Every stage exits 0.** netlist → route → DRC. A non-zero exit fails the job.
2. **The output parses.** `parse_kicad_pcb_v6` on the regenerated file succeeds
   and round-trips. This is the assertion that catches a writer producing
   syntactically plausible garbage.
3. **Order-independent structural equivalence with the committed board.**
   Compare *sorted canonical sets*, not sequences:
   - component count and the set of `(ref, footprint, x, y, rotation, layer)`
   - net count and the set of net names
   - the set of `(net, layer, start, end, width)` track tuples
   - the set of `(net, x, y, drill, diameter)` via tuples

   **This is deliberately order-insensitive, and that is why R3 does not depend
   on the board-writer emission-order fix.** The writer emits tracks and vias
   from a `frozenset`, so regeneration is not byte-reproducible; a sorted-set
   comparison is invariant under that. R3 discards the artifact rather than
   diffing it, so it never needs byte reproducibility. *(Unverified: I could not
   find a branch named `fix/board-writer-emission-order` on `origin`. If it
   lands, this assertion gets strictly stronger for free and needs no change.)*
4. **DRC within the committed ceiling.** Regenerate `pcb/temper.kicad_dru`
   first — it is gitignored and generated from `scripts/generate_kicad_dru.py`,
   and **a missing DRU yields a different, wrong, self-consistent-looking
   answer** (the R3 evidence doc's §3a trap: `clearance` read 499–503 instead of
   377–378, and `creepage`/`track_width` vanished entirely). Then
   `kicad-cli pcb drc --all-track-errors --format json`, N = 12, and assert every
   category's observed range lies at or below `power_pcb_dataset/drc_ceiling.json`.
   Assert **within ceiling**, not **equal to the committed board** — the
   regenerated board legitimately differs.
5. **Content address.** Compute `sha256` of the regenerated artifact, print it,
   and upload the artifact with a 7-day retention. This is R6's content-hash
   requirement arriving early and cheaply.

**Hard prohibitions, encoded in the workflow, not in review convention.**
The job must never write `power_pcb_dataset/drc_ceiling.json`, never commit
`pcb/temper.kicad_pcb`, never author a `Ceiling-Approval:` commit trailer, and
never open a PR. `docs/plans/2026-08-02-023-feat-drc-ceiling-monotone-contract-plan.md`
records that the trailer is currently unchecked free text — any commit
containing the string passes the approval gate — so an automated writer with
commit access is a live exploit of a known-open gap. Give the job
`permissions: contents: read` and nothing else.

**Files touched**
- New: `.github/workflows/board-regeneration.yml`.
- New: `scripts/verify_regenerated_board.py` — assertions 2–4. Ruff-clean, under
  the 1000-line LOC cap.
- No change to `Makefile`, `pcb/**`, or `power_pcb_dataset/**`.

**Blocked by:** U6. **Blocks:** U8.

---

#### U8. Prove the R3 job can fail

**Goal.** Demonstrate the producer is not a vacuous gate.

**Procedure.** A `workflow_dispatch` input `inject_defect` that, when set,
mutates the regenerated artifact before verification — delete one track, or
displace one component by 5 mm — and assert the job goes **red**. Run it once
per assertion class (2, 3, 4) and record the three red runs in
`docs/evidence/2026-08-05-r3-producer-anti-vacuity.md`.

This is not optional decoration. `scripts/check_vacuous_gates.py` exists because
this failure class recurs here; the parent plan's D6/R8 name demonstrated kill
capability as the antidote to coverage theatre; and the router breakage U6
investigates went unnoticed for 12 days behind a `continue-on-error` mask on the
one gate that covered it.

**Blocked by:** U7.

---

### U9. The Phase 0 verdict

**Goal.** One document, one table, one sentence about D3.

**Files touched:** new `docs/evidence/2026-08-05-wasm-tier-phase0-verdict.md`.

**Content.**

| Req | Verdict | Evidence | Consequence |
|---|---|---|---|
| R1 | PASS / PASS-WITH-CAVEAT / FAIL | U1, U2 docs | FAIL → D3 reopens |
| R2 | PASS / FAIL | U4, U5 docs | FAIL → D3 reopens |
| R3 | PASS / BLOCKED-UPSTREAM | U6, U7, U8 docs | Neither reopens D3 |

Followed by exactly one of:

> **D3 stands.** The substrate proof and cost model support Cloudflare Workers.
> Phase 1 may be pulled.

or

> **D3 is reopened.** [R1 | R2] failed as follows: … The substrate choice returns
> to an open decision and no later phase may be pulled until it is re-settled.

**Where the substrate decision goes if it reopens.** Back to the maintainer, via
`ce-brainstorm` against the parent plan — **not** into an edit of D3 by whoever
ran Phase 0. D3 is recorded as `session-settled: user-directed`; an executor does
not overturn it, an executor supplies the evidence that makes overturning it the
maintainer's obvious next move. The verdict document is that evidence. The
alternatives D3 already considered and rejected (native-first spike,
containers-as-runners at ~$65–535/month) are the candidates a reopening returns
to; this plan does not pre-select among them.

**Blocked by:** U1, U2, U4, U5, U6.

---

## 2. The R1 verdict procedure

Stated separately because it is the unit most likely to be executed by someone
who reads only this section.

**R1 = PASS** requires all four:

1. `cargo build --release --target wasm32-unknown-unknown --no-default-features`
   produces a `.wasm` for both `temper-drc-rs` and `temper-geometry`.
2. The module's import list contains no host symbol a Cloudflare isolate cannot
   provide. Record the list; do not summarize it.
3. At least one rule from each of R5's six families executes under `wasmtime`
   and returns a verdict exactly equal to native on the same input.
4. All six families are reachable under `--no-default-features` (U2).

**R1 = PASS-WITH-CAVEAT:** 1–3 hold, 4 does not. The `wasm32` substrate is
proven; the portable surface is smaller than the tier needs. Record which
families are gated out and what un-gating costs. **D3 is not reopened** — this
is scope, not substrate. Phase 1 inherits the un-gating as a precondition.

**R1 = FAIL:** 1, 2 or 3 fails. Record, in the verdict document:
- the exact command and its full output;
- the crate, file and line the failure attaches to;
- whether it is *intrinsic* (a dependency that cannot target `wasm32`) or
  *incidental* (a `cfg` that was never added);
- for incidental failures, an estimate of the fix — because an incidental
  failure that is a two-line `cfg` should not reopen a substrate decision, and
  the verdict must say which kind it found.

Then D3 reopens per §U9. **Do not work around a FAIL.** R1's own text says
failure "reopens D3 rather than being worked around," and the temptation here is
real: a `wasm32`-hostile dependency can usually be vendored, patched or stubbed,
and every one of those moves converts a substrate finding into hidden technical
debt inside a tier whose entire value is being trustworthy.

---

## 3. Sequencing summary

| Unit | Blocked by | Blocks | Evidence that closes it |
|---|---|---|---|
| U1 R1 rungs 2–3 | — | U2, U3, U9 | `.wasm` on disk + import list + 6 exact native/wasm verdict matches |
| U2 portable surface | U1 | U3, U9 | JSON delta + per-family reachability table |
| U3 CI guard | U1, U2 | — | Green on a PR **and** demonstrated red on a planted break |
| U4 full-board cost | — | U5, U9 | Board hash, N=32, median+range, exact ≤128 MiB verdict |
| U5 Q7 verdict | U4 | U9 | Resolution/strategy table + one-line verdict |
| U6 router status | — | U7, U9 | Repro transcript; if green, N=12 timing + 5-run sha256 identity |
| U7 producer | U6 | U8 | Nightly workflow green; artifact uploaded and discarded |
| U8 anti-vacuity | U7 | — | Three recorded red runs, one per assertion class |
| U9 verdict | U1,U2,U4,U5,U6 | Phase 1 | The D3 sentence |

**Critical path to a D3 answer:** U1 → U2 → U9 (Track A) and U4 → U5 → U9
(Track B), concurrently. Track C never gates D3 — R3 cannot invalidate the
substrate; it can only delay the tier's input.

**Phase 0 exits** when U9 exists. U7 and U8 may still be outstanding if U6
recorded BLOCKED-UPSTREAM; that is an acceptable Phase 0 exit, because R3's
failure mode is "the tier has a stale input," not "the tier cannot exist."

---

## 4. Non-goals

Drawn from the parent plan's Scope Boundaries. None of these is in Phase 0:

- **Any Worker.** No `wrangler.toml`, no Cloudflare account, no deployment, no
  KV/R2/D1, no `workers-rs`. Phase 0 measures natively and runs WASM under a
  local runtime only. R2's own text — "before any Worker is written" — makes
  this a requirement, not a preference.
- **Sharding design.** That is R5, and Q4 explicitly defers it until R2 has the
  memory profile. U5 supplies the input; it does not do the design.
- **Building any Q7 memory strategy.** U5 names which is needed. Building it is
  Phase 1 or 2.
- **The CP-SAT solve and the SAT-backed router core.** Out per Scope Boundaries.
  `temper-rust-router-core`, `temper-constraint-compiler` and
  `temper-rust-router` are not Phase 0 crates. (Note #661 has since made
  `rustsat`/`rustsat-cadical` optional behind a default-on `sat` feature, so the
  blocker is now removable — that changes the *feasibility* of a later decision
  and changes nothing about this phase's scope.)
- **`kicad-cli` on Workers.** It is a native application; R9 keeps it in GitHub
  Actions.
- **Migration of the Python test suite.** Wave 4 owns it.
- **Removing the `python` feature.** R1's gate is interim; Wave 4's endgame
  removes the Python boundary. Phase 0 adds a feature flag and touches nothing
  about the boundary's fate.
- **Automating placement.** Both prior artifacts establish that placement is
  human-gated with candidate selection and that CP-SAT is bit-identical only
  when it terminates without hitting its timeout. R3's producer covers the
  deterministic subset only, and §5 below records that as a stated narrowing.
- **Per-push board regeneration.** Rejected on the job-count argument in U7.
- **Editing `power_pcb_dataset/drc_ceiling.json`, any measurement baseline, or
  the parent plan's Requirements and Decisions.** Anything Phase 0 finds wrong
  with them goes in the verdict document.
- **Phases 1–4.** D5 fixes their order and they are pulled individually.

---

## 5. What this plan believes is wrong or underspecified upstream

Recorded here rather than edited into the parent plan, per that plan's authority
and this plan's instructions.

1. **R2's amendment does not measure R2's subject.** R2 asks for "per-case CPU
   cost and peak resident memory for a full-board rule pass." The cited
   measurement benchmarks four `temper-geometry` pairwise kernels and *computes*
   an occupancy-grid size arithmetically. No `temper-drc-rs` rule runs; no
   process's resident set is read. The figures are sound for what they measure.
   The requirement now reads as satisfied. **Suggested amendment:** split R2 into
   R2a (per-case kernel CPU — satisfied, cite `r2_cost_model.rs`) and R2b
   (full-board pass peak RSS — open, U4 closes it).

2. **R1's verification level is weaker than the failure mode it faces.** R1 says
   "compile," which `cargo check` satisfies. `cargo check` does not link, and
   both crates carry `unsafe extern "C" { fn dlsym }`. **Suggested amendment:**
   R1 should say "builds a `wasm32-unknown-unknown` artifact and executes one
   rule under a WASM runtime," which is what D4 needs it to mean if it is to be
   capable of invalidating D3.

3. **R1 does not require the rules to survive the feature gate.** Gating whole
   modules satisfies R1 while removing `validation.rs`'s ten kernels,
   `bridge.rs` and `congestion_tensor.rs` from the portable build. A crate that
   compiles to `wasm32` and can run nothing satisfies R1 as written.
   **Suggested amendment:** add "and the rule families named in R5 remain
   reachable in the `wasm32` configuration."

4. **R3's literal text is not satisfiable and both prior artifacts say so.**
   "An input that changes when the harness changes" requires the *placement*
   harness, and `make build` has no placement step; every recent board change
   came from a human-gated CP-SAT re-solve with candidate selection.
   `docs/plans/2026-08-04-001-...md` §5 flags this as a scope narrowing Phase 0
   "should record as a scope narrowing, not a silent success." This plan records
   it. **Suggested amendment:** R3 should say "the deterministic subset
   (netlist → route → DRC) over the committed placement."

5. **No requirement covers how 783 Rust tests execute on `wasm32`.** `cargo
   test`'s harness cannot target `wasm32-unknown-unknown` — no argv, no threads,
   no process exit — so a build-time dispatch table is needed. The parent plan
   has R1–R16 and none of them mention it. **The briefing that produced this
   plan cites "R17/R18" and describes Q7 as a dispatch-table question; neither
   matches the parent plan's current text** (Q7 is the memory-strategy question
   about occupancy-grid compression). Either the briefing is stale against a
   rewritten plan, or the dispatch-table requirement was dropped. Flagging rather
   than guessing: **the test-dispatch question is genuinely unowned today** and
   Phase 1 will hit it immediately.

6. **`getrandom`'s `js` feature and `gumbel_softmax`'s unconditional
   `rand::random()` are unowned risks.** `temper-geometry` compiles for `wasm32`
   only because a JS-backed entropy source was added, and that source is needed
   because a *pure kernel* calls the global RNG unconditionally, in both feature
   configurations. Two consequences neither plan covers: the `js` feature
   requires `wasm-bindgen` glue at runtime (a bare isolate without it traps),
   and a verification tier whose kernels consume global entropy cannot reproduce
   its own findings. U1 rung 3 will surface the first; the second wants a seeded
   RNG threaded through `gumbel_softmax`, which is Wave 4's business, not this
   plan's.

7. **`drc_ceiling.json`'s approval trailer remains an unchecked substring.**
   Restating `docs/plans/2026-08-02-023-...md`'s finding because U7 builds
   automation adjacent to it. This plan's mitigation is `permissions: contents:
   read` and an explicit prohibition, not a hope. It does not close the gap.

---

## 6. What could not be verified

Stated plainly, because a confident plan step down a dead end costs more than an
admitted unknown.

- **The "783 `#[test]`, zero using `tokio`/threads/`rayon`/`std::fs`" figure.** I
  measure **1006** `#[test]` across `packages/*/src` + `packages/*/tests`, of
  which **488** are in the two Phase 0 crates. I could not reproduce 783 under
  any scoping I tried, so the two figures may count different things. Separately,
  the four named hazard categories do not cover the hazard both crates actually
  carry: `dlsym`/`extern "C"` host-symbol resolution, present in
  `temper-drc-rs/src/validation.rs` and `temper-geometry/src/pad_geometry.rs`
  and `grid_raster.rs`. The portability claim is probably still right; its stated
  basis is incomplete.
- **The "≥12 samples with 32 as precedent" convention.** I could not locate it
  written anywhere. What I found: `AGENTS.md:56-71` mandates **120** samples for
  DRC ceiling re-measurement; `benchmarks/perf_ab.py:108-109` uses
  `DEFAULT_WARMUP = 3`, `DEFAULT_REPEATS = 9`;
  `power_pcb_dataset/metrics/perf_ab_baseline.jsonl` has 12 **rows**, which are
  distinct benchmarks rather than samples. U4's N = 32 / floor 12 follows the
  briefing's instruction, not a convention I verified.
- **The "1-ULP difference already flipped a result here" precedent.** The closest
  documented instances: `temper-drc-rs/src/validation.rs:31-40` records 262/200000
  mismatches of `x*x` vs `x**2` and 274/200000 of `sqrt` vs `x**0.5`, and
  `benchmarks/perf_ab.py:857-858` records PR #714 passing a differential at
  iterations `[0,1,2,8,17,100]` then failing CI at 120. Neither is literally a
  1-ULP flip. The *policy* — exact comparison, not tolerance — is well-supported
  regardless.
- **Whether the router executes at `0718a0943`.** Not run. Disk headroom on this
  machine was ~12 GiB with other agents active, and `uv sync --all-packages` plus
  a route attempt is not a safe spend. **This is U6's entire job** and the plan is
  written to survive either answer.
- **Route wall time.** Unmeasured upstream and unmeasured here. U7's ~30-minute
  budget is `11.46 s + route + 42 s` with route unbounded; if route turns out to
  cost tens of minutes, the nightly cadence still holds but the budget line in
  U7 needs re-stating.
- **`fix/board-writer-emission-order`.** No branch by that name exists on
  `origin` (`git branch -r --list "*board-writer*"` → empty). Either it is local
  to another agent's worktree or it is named differently. U7's assertion 3 is
  designed to be independent of it either way.
- **Any actual `wasm32` build or `wasmtime` run.** None performed — this is a
  planning artifact and the disk budget forbade it. Every claim in §0 about the
  landed state comes from reading commits, manifests and source, not from
  re-running the builds those commits describe.

---

## Sources / Research

- `docs/plans/2026-08-03-002-feat-wasm-verification-tier-plan.md` — the
  requirements plan this enriches. D3, D4, D5, D6, R1–R16, Q4, Q7, Scope
  Boundaries.
- `docs/plans/2026-08-04-001-feat-board-regeneration-proposal.md` — Q2's answer;
  the deterministic-subset recommendation U7 implements and the placement
  narrowing §5.4 records.
- `docs/evidence/2026-08-04-board-regeneration-cost.md` — netlist 11.46 s (N=4),
  DRC 417.9 s (N=120), the DRU trap, and the router's three broken entry points.
- `bcfd3272e` (#656), `f9cbd8fde` (#659) — R1's landed evidence and its
  `cargo check` limit; the module-granularity gating that produced G3.
- `f20d605eb` (#663), `packages/temper-geometry/examples/r2_cost_model.rs` —
  R2's landed measurement and its scope.
- `eb24b9557` (#661) — `rustsat`/`rustsat-cadical` behind an optional `sat`
  feature.
- `.github/workflows/python-tests.yml:632-706` — the `rust-checks` job U3
  extends, and the header comment recording why gates report independently.
- `packages/temper-drc-rs/src/validation.rs:74-120`,
  `packages/temper-geometry/src/pad_geometry.rs:29-120` — the `dlsym` blocks
  behind G1.
- `docs/plans/2026-08-02-023-feat-drc-ceiling-monotone-contract-plan.md` — the
  unchecked `Ceiling-Approval:` trailer U7 must not touch.
- `AGENTS.md:45-97` — the 120-sample protocol and the no-branch-protection
  record.
- `docs/evidence/2026-07-27-router-determinism.md`,
  `docs/evidence/2026-08-01-ortools-cpsat-spike.md` — the determinism bounds U6
  re-checks.
