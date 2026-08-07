<!-- provenance: commit=7e1194b776aad76db2f1fd2a323defa0bebd5367 dirty=false -->

# WASM verification tier — Phase 2–4 status, R4–R8 evidence map, and the R8/#871 reachability question

**Date:** 2026-08-07
**Task:** Read Phases 2–4 of `docs/plans/2026-08-03-002-feat-wasm-verification-tier-plan.md`
(nobody had examined them this session — Phase 0 and most of Phase 1 have
landed, but the parent plan's later phases were last touched as prose on
2026-08-03). Enumerate their units, map goal-set R4–R8 to evidence, assess
what issue #871 actually blocks, answer the goal-set's Q1, and produce a
dependency-ordered next-step list. **Read-only against the tier — no Worker
deployed, no `wrangler` invoked, no cost incurred, `docs/wave4-verdicts.yaml`
and `.github/workflows/*` untouched.**
**Base assertion:** `git status --short` clean at `7e1194b7` on this worktree
branch; `scripts/assert-base.sh` was not run because this worktree branched
from `main` before today's session and has no upstream ref to assert
against — the base commit is stated directly instead.

**Bottom line up front:**

1. **Phases 2–4 have no units.** Unlike Phase 0 and Phase 1, which each got
   their own implementation-ready plan with numbered units (U0–U9 apiece),
   Phases 2–4 exist only as one-paragraph descriptions inside the parent
   plan's "Phased Path" section. Nothing under `docs/plans/` breaks any of
   them into units, and no code in the repo executes any of the three.
2. **R4 met, R5 partially met (offline artifact only, not threaded into
   findings), R6 unmet (no equivalence measurement exists), R7 unmet in
   both directions (numerator is unit-test volume, not DRC/ERC volume; the
   oracle's sustainable rate has never been measured), R8 unmet and not
   reachable today** — the harness that would regenerate the board from the
   committed placement cannot complete on the production board via either
   of its two code paths.
3. **#871 blocks R8's literal mechanism (board regeneration).** Today's
   plane-classification fix (branch `worktree-agent-adee024249f564698`,
   `8abcec24`, not on `main`) fixes the bug that was silently returning a
   fake "success" (0-variable model, 37.75% completion, certified passing)
   but exposes a second, previously-unreachable blocker: an O(n²)
   skeleton-connectivity blowup that does not complete in practical time.
   R8's *intent* — an input that changes when the harness changes — is
   reachable today without `route_pcb()` at all; see §3.
4. **Q1 (per-change vs. continuous): recommend continuous, not wired to CI
   yet either way.** No workflow invokes the Cloudflare Workers tier at
   all today — every Phase 1 measurement (U1, U5, U6, U8) was a manual,
   researcher-driven sweep, not a running system. The board-regeneration
   workflow (`.github/workflows/board-regeneration.yml`) is nightly-scheduled
   and off the push-contended pool already, which is the model to extend to
   the Worker tier, not per-PR triggering.

---

## 1. Method

Every claim below was checked against code, git history, or a measured
evidence document at HEAD — not against plan prose, per the task's standing
instruction that plan status fields in this repo have repeatedly been stale
(see `AGENTS.md`'s own base-commit-assertion and provenance sections, both
written in response to exactly that failure mode). Where a plan and the code
disagreed, the code wins and the disagreement is called out explicitly.

Two plans are in play and both use "R4–R8" for different requirements:

- The **parent plan** (`docs/plans/2026-08-03-002-feat-wasm-verification-tier-plan.md`)
  has its own R4–R23 numbering (R4–R6 there are "the tier" — WASM execution,
  sharding, content-hash addressing).
- The **goal-set plan** (`docs/plans/2026-08-04-002-docs-temper-goal-set-plan.md`)
  has a separate, smaller R1–R22, and this is the R4–R8 the task's §2 names
  (Verification substrate R4–R6, Scaled checking R7–R8). §3 of this document
  uses the goal-set's numbering throughout and cites the parent plan's
  corresponding requirement in parentheses where the two overlap.

---

## 2. Phase 2–4 unit inventory

The parent plan's "Phased Path" section (lines 118–127) is the entirety of
what exists for these three phases — one paragraph each, no unit breakdown,
no implementation-ready follow-on plan. Compare Phase 1, which got a
954-line implementation plan (`docs/plans/2026-08-07-001-feat-wasm-tier-phase1-plan.md`)
with nine numbered units, evidence-closure criteria per unit, and a verdict
document. Nothing equivalent exists for Phases 2, 3, or 4. This section
enumerates what each phase's paragraph actually requires and what already
exists toward it, since "units" cannot be verified against a plan that does
not define any.

### Phase 2 — manufacturing variation

> "Sweeps the board across the fabrication envelope rather than nominal
> geometry alone. Requires a fabrication-envelope model that does not exist
> yet." (parent plan line 124)

- **Requires:** a fabrication-envelope model — trace-width/spacing
  tolerance bands, layer-registration offset ranges, copper-thickness
  variation — that the tier's kernels sweep the board against. This is the
  parent plan's own outstanding **Q3**, explicitly unresolved ("Deferred to
  Planning," line 155).
- **Depends on:** Phase 1's payload being trustworthy (D5's ordering
  rationale — "scaling unvalidated checkers multiplies unreliable answers,"
  line 49) and the wasm-portable rule kernels Phase 1 already proved compile
  and run.
- **Status at HEAD: does not exist.** No file in the repository contains
  the phrase "fabrication envelope." The nearest adjacent tooling is
  `packages/temper-placer/src/temper_placer/manufacturing/tolerances.py`,
  `monte_carlo.py`, and `stackup_validator.py` (statistical
  process-variation/yield modeling used by the placer, since migrated
  toward Rust in `temper-design-bundle`) — but neither the wasm plan nor
  these modules cross-reference each other, and none of them define a
  fabrication-envelope model in the sense Phase 2 means (a sweep surface
  the WASM tier's kernels would iterate over). Verdict: **not started**, and
  the plan itself already says so — this is not new information, but it is
  now confirmed unchanged as of `7e1194b7`.

### Phase 3 — fault injection and mutation

> "Scales the seeded-defect work already in flight under portfolio R38 and
> R42, proving the gates bite at volume." (parent plan line 125)

- **Requires:** the portfolio's R38 (board-defect mutation corpus) and R42
  (gate-mutation testing) infrastructure, scaled to run at WASM-tier volume
  instead of at CI-budget volume.
- **Depends on:** Phase 1's payload (the tests being scaled are Rust
  test/canary functions) and, per D5, tooling correctness having been
  established first.
- **Status at HEAD: R38 landed, R42 does not exist — the "already in
  flight" claim is half true.**
  - **R38 (board-defect mutation corpus): implemented.**
    `scripts/board_defect_mutator.py`, `scripts/check_board_defect_corpus.py`,
    and `scripts/board_defect_corpus.yaml` exist, are registered in
    `scripts/manifest.yaml`, and have measured evidence
    (`docs/evidence/2026-08-02-board-defect-corpus.md`,
    `docs/evidence/2026-08-04-board-defect-corpus-uncovered-classes.md`) —
    all three named defect classes (component off-board, pad short,
    creepage crossing) reproduced with measured violation-count deltas.
    Plan: `docs/plans/2026-08-02-024-feat-board-defect-mutation-corpus-plan.md`.
  - **R42 (gate-mutation testing): plan-only, unimplemented.**
    `docs/plans/2026-08-02-035-feat-gate-mutation-testing-plan.md` fully
    specifies U1 (`scripts/gate_mutate.py`, `ci-corpus/mutations.yaml`) and
    U2 (`scripts/check_gate_mutations.py`); none of these files exist, there
    is no manifest entry, and no evidence doc under `docs/evidence/`
    documents a gate-mutation run.
  - Neither R38 nor R42, landed or not, runs on the WASM tier today — R38's
    corpus runner is a Python/`kicad-cli`-shaped script, not a wasm32
    dispatch entry, and nothing in `tools/wasm/test_family_map.json`'s 8
    families references defect-corpus or gate-mutation test names.
  - Verdict: **R38 exists but unported to the tier; R42 does not exist at
    all.** Phase 3 cannot scale infrastructure that is half-missing.

### Phase 4 — design-space variants

> "Validates placer candidates rather than only the committed one, turning
> DRC and ERC into a selection signal." (parent plan line 126)

- **Requires:** a mechanism that generates or holds multiple placer
  candidate outputs side by side and scores them against DRC/ERC results,
  turning the tier's checks into a comparison signal rather than a
  pass/fail gate on one committed board.
- **Depends on:** Phase 1's payload (the DRC/ERC kernels doing the scoring)
  and, implicitly, the CP-SAT placer producing more than one candidate per
  run (out of this plan's scope per the parent plan's own Scope Boundaries
  — "the CP-SAT solve and the SAT-backed router core" are excluded from
  `wasm32` portability entirely, so Phase 4's *scoring* could run on the
  tier even though the *candidate generation* structurally cannot).
- **Status at HEAD: does not exist.** No file or plan uses "design-space
  variant," "multi-candidate," or an equivalent term for a pipeline that
  scores N parallel placer candidates against each other. "Candidate
  placement" appears throughout `packages/temper-placer` (e.g.
  `router_v6/congestion.py`) but always names a single working/uncommitted
  placement under evaluation before commit, not multiple candidates held
  and compared. Verdict: **not started**, and — unlike Phase 2 — the parent
  plan doesn't even name an owning open question for it; there is no Q-item
  to resolve before planning could begin.

### Summary table

| Phase | Unit breakdown exists? | Core dependency | Status |
|---|---|---|---|
| 2 — manufacturing variation | No (one paragraph, Q3 open) | Fabrication-envelope model | Not started |
| 3 — fault injection/mutation | No (one paragraph) | Portfolio R38 + R42 ported to tier | R38 landed off-tier; R42 unimplemented; neither ported |
| 4 — design-space variants | No (one paragraph, no Q-item) | Multi-candidate placer output + DRC/ERC scoring | Not started |

All three are correctly described by the parent plan's own framing ("Phases
are pulled individually," line 120) — none is a broken promise, since
nothing has pulled them yet. The finding is that **Phase 1's exit did not
change any of this**: the phase's own verdict doc
(`docs/evidence/2026-08-07-wasm-tier-phase1-verdict.md`) says "Phase 2 may
be pulled when capacity allows," and capacity has not been spent on it.

---

## 3. R4–R8 evidence map (goal-set plan)

### R4 — "The pure-Rust rule and property kernels execute as WASM off the shared CI concurrency pool."

**MET**, for the payload that exists (Rust `#[cfg(test)]` functions, not yet
property kernels beyond what those tests already are). Evidence:

- Local: `docs/evidence/2026-08-07-phase1-u5-volume.md` — 190,000
  invocations, 56.2s, ~3,379 inv/s, deterministic (0 unexpected verdicts
  across 2,000 repetitions of 95 tests), 1.75 MiB peak linear memory (1.4%
  of the 128 MiB isolate limit).
- Worker: `docs/evidence/2026-08-07-phase1-u7-deploy-runbook.md` +
  `docs/evidence/2026-08-07-phase1-u8-multi-worker.md` — 8 Workers live at
  `*.bennetleff.workers.dev` (1 full-corpus + 7 per-family), reachable,
  `/run-test` verified.
- Caveat, not a gap in R4 itself but load-bearing for Q1 below: nothing in
  `.github/workflows/` invokes any of these Workers (`grep -rl "wrangler\|
  workers.dev" .github/workflows/*.yml` returns nothing). "Consumes no
  GitHub Actions concurrency" is true today only because the tier does not
  run *in* GitHub Actions at all yet, in either direction — it has not been
  wired to run per-PR (which would cost pool capacity) or on a schedule
  (which would not). All volume measured so far was a researcher manually
  checking out commits and running a local or Worker sweep by hand.

### R5 — "Every finding names the exact artifact it came from by content hash." (parent plan R6)

**PARTIALLY MET, and not where it would need to be.** The mechanism exists
but is disconnected from the tier's actual findings:

- `tools/wasm/r2_serialize_board.py:189-190` computes and prints a sha256 of
  the serialized board JSON. This is real, and the fix landed today
  (`f2596ca3` + `b0bf128c`, not yet on `main` — see below) makes that JSON
  content-deterministic across processes (10/10 byte-identical runs,
  verified in `b0bf128c`'s commit message, after fixing two independent
  hash-seed-dependent orderings: per-net `component_refs` in
  `r2_serialize_board.py` itself, and top-level `nets` ordering in
  `board_py_bridge.rs`, `0e29a88d`).
- **But this JSON and its hash feed `packages/temper-drc-rs/examples/
  r2_full_board_pass.rs`** — a standalone native Rust benchmark binary used
  for the parent plan's R2 CPU/memory cost-model measurement. It is **not**
  part of `wasm_test_registry.rs` and does not ship in any deployed Worker's
  `.wasm` module. Confirmed: `board_py_bridge.rs` carries no
  `#[cfg(feature = "wasm-test-registry")]` markers and no `WASM_TESTS`
  consts; the routing-data test added alongside the fix
  (`test_board_py_bridge_routing_data.py`) lives under
  `packages/temper-placer/tests/validation/` — a native Python test against
  the pyo3 bridge, structurally excluded from the wasm32 build by the same
  `python`-feature gate R1 depends on.
- **Net effect:** the board content-hash exists for an offline benchmark
  artifact. The 147 tests actually running on the deployed Workers today
  are static Rust assertions with no board input and therefore nothing to
  hash — a pass/fail verdict for `test_drc_clearance_basic` names a test
  name and a commit (via the wasm module's build provenance), never a board
  artifact, because no board artifact is in the loop for that invocation.
  R5 is met in the narrow sense that *a* content-hash mechanism exists and
  is now deterministic, and unmet in the sense that no *finding* the tier
  currently produces actually carries one.

### R6 — "The reference oracle is retired only once the Rust suite demonstrates interval-based equivalence with it." (parent plan R10/R11)

**UNMET — no retirement has been proposed, and the prerequisite measurement
(R10's equivalence bar) does not exist.** This requirement is a gate on a
future action (retiring `kicad-cli`), not a state to have reached yet, so
"unmet" here means "the precondition work has not started," not "violated."
Nothing retires `kicad-cli` today (`R9`/D7 both still hold: `kicad-cli`
"remains the reference oracle... while the tier is being established," and
it still runs in every DRC-touching CI step). The interval-equivalence
instrument the parent plan names (R11: "the full-board DRC oracle
differential") exists as a differential harness but has not been run
against the wasm tier's verdicts to produce an equivalence measurement —
Phase 1's R19 comparison (see R4 above) compares wasm32 vs. native `cargo
test`, which is a different comparison than wasm-verdict-vs-`kicad-cli`-verdict
interval equivalence.

### R7 — "Sustained DRC and ERC check volume exceeds what the reference oracle can sustain by at least an order of magnitude." (parent plan R7/R9/D6)

**UNMET, and the task's framing is correct: nobody has measured the
denominator.** Verified: `kicad-cli` is not installed in this environment
(`which kicad-cli` → not found), so this document cannot supply the
missing measurement either — it can only confirm that no prior evidence
doc does. `grep`-ing every `docs/evidence/*.md` file that mentions
`kicad-cli` for a wall-clock or throughput figure
(`2026-08-03-slow-lane-pair-baseline.md`,
`2026-08-04-creepage-rust-backend-survey.md`) turns up cost/latency
discussion in CI-job terms, never an isolated "N `kicad-cli pcb drc` runs
per second/minute on this board" figure. The closest existing number is
qualitative: `_drc_api.py`'s own comments describe `kicad-cli` DRC as
sharing a `BS::thread_pool` and being pinned to one worker for determinism,
which if anything argues its *concurrent* throughput is artificially capped
below its serial capability — the opposite direction from what R7 needs to
claim, and one more reason the comparison needs a real measurement rather
than an assumption in either direction.

Two further problems compound the missing denominator, both worth recording
because fixing the denominator alone would not make R7 true:

1. **The numerator isn't DRC/ERC volume either.** The 190,000 measured
   invocations (§R4) are repetitions of 95–147 Rust `#[cfg(test)]`
   functions. Per the U4 coverage doc
   (`docs/evidence/2026-08-07-phase1-u4-coverage.md`) and the multi-worker
   inventory (`docs/evidence/2026-08-07-phase1-u8-multi-worker.md`), the
   family breakdown at the point of that inventory was `drc:1, emc:14,
   erc:9, safety:0, placement:12, routing:2, infra:109` — i.e. the large
   majority of what's being run at volume (`infra`, 109 of 147) is not a
   DRC or ERC check at all, and `safety` had zero registered tests at the
   U4 measurement. Repeating a thin, mostly-non-DRC/ERC test corpus
   190,000 times is a real throughput measurement of *something*, but it is
   not yet a measurement of "DRC and ERC check volume" in R7's sense.
2. **Granularity mismatch, independent of both of the above.** A single
   `kicad-cli pcb drc` invocation evaluates the *entire* rule set against
   the *entire* board in one pass. A single wasm32 test invocation
   evaluates one assertion against a fixture. Comparing "invocations per
   second" across these two units without normalizing for what one
   invocation actually checks would overstate the tier's advantage by
   whatever factor `kicad-cli`'s single pass covers more ground than one
   Rust test does — a factor nobody has measured either.

R7 needs three numbers that do not currently exist: `kicad-cli`'s
sustainable full-board-DRC/ERC rate, the tier's sustainable *DRC/ERC-scoped*
(not whole-corpus) rate, and a normalization for what one unit of "check"
means on each side.

### R8 — "The board the tier checks is regenerated from the committed placement, so the input changes when the harness changes." (parent plan R3)

**UNMET and, via `route_pcb()`, not reachable today.** See §4 for the full
reachability assessment — the short version: the board-regeneration
producer (`.github/workflows/board-regeneration.yml`, nightly, calling
`scripts/route_board.py:132`) is the only regeneration path in the repo,
and both of the two ways to reach `route_pcb()` on this board fail to
complete: the stripped-copper path (what `route_board.py` uses) OOMs at
~12.4 GB RSS (issue #871, reproduced independently as recently as
`docs/evidence/2026-08-07-r3-frozenset-order-verification.md`), and the
direct/production path, after today's plane-classification fix, builds a
real (non-empty) model but cannot complete `_ensure_skeleton_connectivity`'s
O(n²) island-bridging pass in practical time (measured: did not finish in
79s of pure-Python CPU for a single outer-loop pass, `8abcec24`'s commit
message). Parent-plan R3 already records this as **BLOCKED-UPSTREAM** in
the Phase 0 verdict, and nothing since has closed it — it has gotten one
step closer (real model, not empty) and hit a new wall in the same place.

---

## 4. Is R8 reachable, and does #871 actually block it?

**#871, as literally scoped ("`route_pcb()` OOM at >13 GB RSS"), blocks one
of two paths to board regeneration — the one the current producer actually
uses. It does not block the other path, but that path has its own,
newly-exposed blocker that #871 never covered.** Both are documented in
`docs/evidence/2026-08-07-router-silent-noop-diagnosis.md`, which this task
was pointed at and which this document treats as verified (its bisection —
commit `556ccf4f` as the transition, direct repro at both sides via
throwaway `git worktree` checkouts — is independently reproducible and was
not re-run here, since re-running it would mean invoking `route_pcb()` on
the production board, which risks the same OOM/long-hang this document is
assessing, not re-verifying).

**The two paths, concretely:**

1. **Stripped-copper path** (`scripts/route_board.py`'s default,
   `keep_existing_copper=False`) — strips all committed copper (including
   zones) from a temp copy before parsing, so F.Cu/B.Cu read as `signal`
   regardless of the plane-condemnation bug. This is the **only path any
   producer in this repo uses** — `make route`'s target and
   `.github/workflows/board-regeneration.yml`'s R3 producer both call it.
   It reliably builds the full-size SAT model (millions of variables) and
   reliably OOMs: `docs/evidence/2026-08-07-r3-frozenset-order-verification.md`
   §4 recorded a real SIGKILL at ~12,448 MB RSS after ~7 minutes on this
   exact board content, four days before this document. **#871 describes
   this path and is live, current, and reproducible.**
2. **Direct/production path** (parsing `pcb/temper.kicad_pcb` straight,
   what the CI DRC gate test and most evidence-doc scripts use) — before
   today's fix, this path hit the plane-condemnation bug
   (`_extract_stackup()` classifying F.Cu/B.Cu as `"plane"` because *any*
   zone on a plane-required net sits there, an existential-over-zones
   check, not an area/role predicate) and silently built a **0-variable
   model**, which the pipeline's per-net fallback router then filled to
   37.75% completion — certified as a passing regression baseline by every
   `test_production_board_routing_drc_regression` re-measurement since
   2026-07-27. **#871, titled around the OOM, does not describe this path
   at all** — it structurally cannot OOM if it never builds a large model.
   Today's fix (`8abcec24`, not yet on `main`) sets
   `use_declared_layer_roles=True` so layer type comes from stackup
   position rather than zone occupancy, and separately removes a hardcoded
   `F.Cu`/`B.Cu`-only restriction in `ChannelSkeletonStage`
   (`channel_skeleton.py:341-346`) that independently zeroed the skeleton
   dict regardless of the plane bug. Confirmed end-to-end: `nets=110,
   skeletons=4` — a real, non-empty model, for the first time since
   `556ccf4f` (2026-07-27). **But** with real zone-pour geometry now
   present, each layer's medial-axis skeleton fragments into ~150
   disconnected islands, and `_ensure_skeleton_connectivity`'s island-bridge
   pass — O(components² × nodes_per_component²) — did not finish a single
   outer-loop iteration in 79 seconds of pure-Python CPU time on this
   board. This is a **new, previously-unreachable blocker**: it could not
   have shown up before today, because it requires both the plane fix and
   the `ChannelSkeletonStage` fix landed together before F.Cu/B.Cu ever
   reach this code with real pour geometry to fragment. **No issue number
   has been filed for it as of this document** (it postdates #871's filing
   and the fixing branch, `worktree-agent-adee024249f564698`, has not
   merged).

**So: reachable via `route_pcb()`, today, on this board — no.** Path 1 OOMs
in ~7 minutes; Path 2, even after today's fix lands, does not complete in
practical time either, for a different reason. Fixing #871 alone (say, by
capping memory or switching solvers) would not make R8 reachable, because
Path 2's skeleton-connectivity blowup is independent of #871's OOM mechanism
and was invisible until today's fix exposed it. Both blockers would need
separate fixes, and the second one (O(n² × n²) island bridging on ~150
islands of ~20,000 nodes each on F.Cu alone) is not a small follow-up — it
is an algorithmic redesign of `_ensure_skeleton_connectivity`, not a bounded
patch.

**Does R8's *intent* have a cheaper path?** R8's actual requirement is
narrower than "`route_pcb()` completes": *"the board the tier checks is
regenerated from the committed placement, so the input changes when the
harness changes."* Two observations suggest the literal router path is not
the only way to satisfy that intent, and may not be the right one to chase
first:

1. **Placement and routing are separable inputs, and only placement is
   named.** R8 says "regenerated from the committed placement" — not "fully
   re-routed." A regeneration that re-derives the board's zone pours,
   clearance geometry, and net topology from the committed *placement*
   (component positions) plus the current *harness* (rule definitions,
   net-class assignments, stackup declaration) without invoking the SAT
   router at all would already make the input change whenever the harness
   changes, which is the property R8 is actually protecting — a stale board
   silently outliving the tooling that would have produced a different one.
   The parent plan's own D11 ("Regeneration verifies; it does not commit")
   and R3 ("verifies the pipeline still produces a valid board") both frame
   regeneration as a validity check on the harness, not as a demand for a
   better route. A cheaper deterministic regeneration — parse, re-derive
   zones/DRC-relevant geometry from placement + current rules, discard —
   would satisfy that framing without depending on Stage 3's SAT solve or
   Stage 4's skeleton bridging at all.
2. **This is close to, but not identical to, what the R2 board producer
   already does.** `tools/wasm/r2_serialize_board.py` + `board_py_bridge.rs`
   already re-derive a `BoardState` from the parsed, committed board on
   every invocation, content-addressed by sha256, and (as of today's
   unmerged fix) deterministically. It is not yet "regenerated from the
   committed *placement*" in the sense of re-running the harness's
   geometry/DRC-relevant derivation steps from component positions — it
   currently re-serializes what's already on disk, including the already-
   routed traces/vias/zones, rather than re-deriving them. Extending it to
   re-run the harness's zone/clearance derivation from placement (a much
   smaller, faster operation than the SAT router) rather than re-parsing
   committed geometry verbatim would close most of the gap to R8's intent
   at a small fraction of `route_pcb()`'s cost, and would not need Stage 3
   or Stage 4 at all. This is scoped as a next step in §6, not implemented
   here.

**Recommendation:** treat the router path as not worth pursuing further for
R8 specifically until the skeleton-connectivity algorithm is redesigned —
that is real router-quality work with its own cost, independent of the
tier. Pursue the cheaper regeneration instead if R8 needs to move before
the router work lands; it satisfies the requirement's stated intent (input
changes when harness changes) without inheriting the router's two
independent failure modes.

---

## 5. Q1 — does scaled checking run per-change or continuously?

**Recommendation: continuously (scheduled), not per-change — and today it
runs neither; every measurement so far has been a manual, one-off sweep.**

The goal-set plan's own framing states the stakes precisely: "the tier was
chosen over containers precisely because checking must be continuous and
off the shared pool; running it per-change reintroduces the coupling it was
chosen to escape" (Q1, goal-set plan line 118). D3 (parent plan) makes the
same point from the cost side: Cloudflare containers were rejected at
$65–535/month against Workers' $5–7 *because* the board regenerates on
every harness change, so "checking must be continuous," not because
Workers are cheaper for the same workload shape.

Three pieces of evidence bear on the answer:

1. **No CI wiring exists in either direction.** `grep -rl "wrangler\|
   workers.dev" .github/workflows/*.yml` returns nothing. The tier is not
   triggered on push, on PR, or on a schedule. It is invoked by hand.
2. **The one existing continuous-shaped precedent in this repo is
   nightly-scheduled, not per-PR, and explicitly reasons about why.**
   `.github/workflows/board-regeneration.yml`'s header comment: "A
   scheduled job does not contend with push-triggered jobs for the
   account's ~24 concurrent runner ceiling; it runs when no push is in
   flight. ... D3's entire justification for choosing Workers is that the
   push-contended pool is the constraint, so spending a slot there would be
   self-defeating." This is the same argument Q1 is asking to have applied
   to the Worker tier itself, already made once for its board producer.
3. **Phase 1's own R19 sustained-agreement protocol is inherently
   per-commit in its measurement method** (`docs/evidence/2026-08-07-
   phase1-u6-sustained-agreement.md` walks 10 consecutive commits, checking
   each out and running the sweep) **but that is a measurement protocol,
   not a deployment model.** Nothing requires the *production* tier to
   re-run per-commit; the R19 comparison needed per-commit granularity to
   attribute a disagreement to the commit that caused it, which is a
   different concern from how often the tier itself executes in steady
   state.

Putting these together: per-change (i.e., triggered by every push/PR) would
put the tier back in competition with exactly the concurrency ceiling D3
rejected containers over, and would also reintroduce the coupling the
goal-set's own Q1 text warns about — a slow Worker deploy or a flaky sweep
would now sit on the merge path the same way a slow CI job does today.
Continuous/scheduled execution (the board-regeneration workflow's pattern,
extended to also drive the Worker sweep on the same or a similar cadence)
keeps the tier's cost and latency off the PR path entirely, which is the
entire reason D3 gives for choosing Workers over containers in the first
place. The gap is not a design disagreement — it is that nothing has wired
either model up yet, so the "continuous" framing the plan already commits
to (D3, Q1's own text) is not actually running continuously; it is running
whenever an agent remembers to invoke it.

---

## 6. Next-step map, in dependency order

Each item names what it unblocks, verified against what currently exists
rather than assumed.

1. **Wire the existing tier into a scheduled (not per-PR) trigger.**
   Extends `.github/workflows/board-regeneration.yml`'s nightly pattern to
   also drive `tools/wasm/sweep_multi_worker.mjs` against the 8 already-
   deployed Workers. Cheapest available step — no new code, reuses code
   already on `main` (`da57ce20`, `63ec4e75`). **Unblocks:** the U8
   ≥10⁴-invocation Worker volume run (still outstanding per the Phase 1
   verdict's Addendum), a real R19-vs-`kicad-cli` cadence, and answers Q1 in
   practice rather than only in recommendation. Answers the open half of
   U8 from the Phase 1 plan.
2. **Measure `kicad-cli`'s sustainable full-board DRC/ERC rate (R7's
   denominator) and re-scope the tier's numerator to DRC/ERC-family tests
   only.** No dependency on anything else in this list; blocked only on an
   environment with `kicad-cli` installed (absent from this worktree).
   **Unblocks:** R7 becoming a real, checkable claim instead of an
   unmeasured assumption in either direction; also directly informs D7/R6's
   retirement gate, which needs the same equivalence data.
3. **Grow the `erc`/`drc`/`safety`/`routing` family test counts** (0, 1, 0,
   2 of 95–147 at the U4/U8 measurements) before claiming R7 volume is
   DRC/ERC volume at all. This is Phase 1 scope that Phase 1's own verdict
   named as "the precondition for Phase 2's manufacturing-variation work"
   but is really a precondition for R7 full stop, independent of Phase 2.
   **Unblocks:** R7's numerator being honest; also feeds Phase 3 (more
   family coverage is more surface for R38/R42 mutations to run against).
4. **Land the plane-classification + `ChannelSkeletonStage` fix
   (`8abcec24`) on `main`, and file the O(n²) skeleton-connectivity blowup
   as its own issue.** Does not by itself close R8 (see §4) but stops every
   `test_production_board_routing_drc_regression` baseline from continuing
   to certify a 0-variable fake pass, and gives the connectivity blowup a
   tracked identity instead of living only in a commit message on an
   unmerged branch. **Unblocks:** honest routing DRC baselines; a scoped,
   assignable follow-up for the connectivity algorithm.
5. **Build the cheaper R8 regeneration path** (§4's second observation):
   extend `tools/wasm/r2_serialize_board.py`/`board_py_bridge.rs` to
   re-derive zone/clearance geometry from the committed placement and
   current harness rules, rather than re-serializing already-routed
   geometry verbatim, and wire it (content-hashed, per R5) into the tier's
   findings. **Depends on:** #2 above being at least partially done first
   isn't required, but doing #2 first means R7/R6 measurements taken
   against this new artifact are comparable to whatever baseline
   `kicad-cli` measurement lands. **Unblocks:** R8 without waiting on the
   router's skeleton-connectivity redesign; makes R5's content-hash
   mechanism reach an actual tier finding for the first time.
6. **Redesign `_ensure_skeleton_connectivity`'s island-bridging pass**
   (currently O(components² × nodes_per_component²)) as router-quality work,
   tracked separately from this tier. Not a tier blocker once #5 lands, but
   still the honest path to R8 in the router's own literal sense
   ("regenerated... the input changes when the harness changes" via a real
   route, not just re-derived geometry). **Unblocks:** the router path to
   R8 as an eventual upgrade over #5's cheaper substitute; also unblocks
   whatever multi-layer routing quality work depends on F.Cu/B.Cu actually
   being open (this fix is the prerequisite for the board ever using its
   inner layers for routing at all, independent of the tier).
7. **R42 (gate-mutation testing) implementation**, per its existing
   implementation-ready plan (`docs/plans/2026-08-02-035-feat-gate-mutation-
   testing-plan.md`) — currently plan-only. **Depends on:** nothing on this
   list; independently pullable today. **Unblocks:** Phase 3's "already in
   flight" claim becoming true for both of the requirements it cites,
   not just R38.
8. **Port R38 (landed) and R42 (once built) onto the wasm tier's dispatch
   surface**, i.e. add `wasm-test-registry` entries for the mutation-corpus
   and gate-mutation checks so they run at Worker volume rather than only
   in CI-budget volume. **Depends on:** #3 (family coverage growth uses the
   same per-crate dispatch-table mechanism) and #7 (R42 existing at all).
   **Unblocks:** Phase 3 becoming pullable in fact, not just in the parent
   plan's description of it.
9. **Fabrication-envelope model (Q3, Phase 2)** and **multi-candidate
   placer scoring (Phase 4)** remain unscoped past this document — both
   need their own planning pass before any unit breakdown is possible, and
   neither has an existing partial implementation to build from (§2).
   **Depends on:** #1–#3 (Phase 2/4 both assume the tier is already running
   continuously and checking something honestly volumetric before adding a
   new sweep dimension on top).

---

## Sources

- `docs/plans/2026-08-03-002-feat-wasm-verification-tier-plan.md` — parent
  plan, Phased Path (§118–127), R1–R28, D1–D15, Q1–Q9.
- `docs/plans/2026-08-04-002-docs-temper-goal-set-plan.md` — goal-set plan,
  R1–R22, Outstanding Questions Q1–Q5.
- `docs/plans/2026-08-07-001-feat-wasm-tier-phase1-plan.md` — Phase 1's
  unit breakdown, the only phase besides Phase 0 with one.
- `docs/evidence/2026-08-07-wasm-tier-phase1-verdict.md` (+ Addendum) — U0–U8
  verdicts, the 147-request/1.30×/c64 U8 sweep, the un-deferred Track D
  timeline.
- `docs/evidence/2026-08-07-phase1-u4-coverage.md`,
  `2026-08-07-phase1-u5-volume.md`,
  `2026-08-07-phase1-u8-multi-worker.md` — family-coverage counts, local
  volume figures, Worker deployment inventory.
- `docs/evidence/2026-08-07-router-silent-noop-diagnosis.md` — the plane-
  condemnation bisection, the two-code-path reconciliation, the full
  invalidated-measurements audit this document treats as verified.
- Commits `f2596ca3`, `b0bf128c` (branch `worktree-agent-a29ddea7502ada4f9`),
  `0e29a88d` (branch `worktree-agent-adfbaf643bff63678`), `8abcec24` (branch
  `worktree-agent-adee024249f564698`) — none on `main` as of `7e1194b7`.
- `.github/workflows/board-regeneration.yml` — the nightly-scheduled,
  off-pool precedent Q1's recommendation extends.
- `scripts/route_board.py`, `packages/temper-placer/src/temper_placer/
  router_v6/_pipeline_core.py`, `channel_skeleton.py`,
  `constraint_model.py` — the two `route_pcb()` code paths and the
  skeleton-connectivity blowup site.
- `tools/wasm/r2_serialize_board.py`, `packages/temper-drc-rs/examples/
  r2_full_board_pass.rs`, `packages/temper-drc-rs/src/board_py_bridge.rs` —
  the R5 content-hash mechanism and why it does not reach deployed Worker
  findings.
- `docs/plans/2026-08-02-024-feat-board-defect-mutation-corpus-plan.md` (R38,
  landed), `docs/plans/2026-08-02-035-feat-gate-mutation-testing-plan.md`
  (R42, plan-only) — Phase 3's two named dependencies.
- `packages/temper-placer/src/temper_placer/manufacturing/tolerances.py`,
  `monte_carlo.py`, `stackup_validator.py` — the nearest existing tooling to
  Phase 2's fabrication-envelope model, not itself that model.
- GitHub issues #871 (OPEN, OOM), #872 (OPEN, feature unification — fixed in
  substance by merged PRs #879/#880 but the issue itself remains open),
  #873 (OPEN, routing-data gap — fix exists on an unmerged branch).
