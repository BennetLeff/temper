---
date: 2026-06-21
topic: duplicate-script-consolidation
related: 2026-06-21-source-of-truth-validation-requirements.md
ideation: N5
---

# Duplicate-Script Consolidation Trio

## Summary

A three-track consolidation that deletes tracked duplicate scripts and routes every caller to one canonical implementation per concern. The codebase has more duplication than N5's premise stated, but the duplication is shallower than it looks: each cluster already has a de-facto canonical survivor, so the work is mostly *call-site migration + deletion*, not greenfield design. The trio: (a) `strip_routing` — delete the three stale `scripts/strip_routing*.py` copies in favor of the existing `packages/temper-placer` `strip_routing()` function, leaving a regression fixture; (b) router runners — fold the three thin stdout-parsing wrappers (`run_router_v6_{minimal,simple,baseline}.py`) into `run_router_v6.py` as run modes, after verifying they add no unique flags; (c) batch validation — delete the `_fixed.py` supersession and the `.bak`, then decide whether the remaining `batch_validate_power_pcb.py` stays as a script or is promoted to a `temper-placer` CLI subcommand. A `docs/consolidation-log.md` appendix pattern is established and reused by future consolidations.

---

## Problem Frame

The Temper repo grew organically during the router-v6 sprint: each experiment forked a script, each fix forked a script, and the originals were never deleted after the fork was proven. Three clusters now have multiple tracked implementations of the same intent:

- **`scripts/strip_routing.py`, `scripts/strip_routing_v2.py`, `scripts/strip_routing_kiutils.py`** — three implementations of "remove routing from a KiCad PCB, leave placement." A *fourth*, canonical implementation already exists inside `packages/temper-placer/.../kicad_writer.py:strip_routing()` (with `keep_zones`/`keep_fills` flags) and is the function imported by the placer package's own CLI, `scripts/run_benchmark.py`, `packages/temper-placer/scripts/generate_unrouted_benchmarks.py`, `temper_placer/pipeline/mvp3_runner.py`, and `scripts/visualize_placement.py`. The three `scripts/strip_routing*.py` files are stale, less capable duplicates whose only tracked caller is `scripts/batch_validate.sh`.
- **`run_router_v6.py` plus `run_router_v6_{minimal,simple,baseline}.py`** — three thin wrappers that `subprocess.run` `run_router_v6.py` and parse its stdout with fragile string matches (`"Routed:"`, `"Success:"`, `"Completion:"`). They add no router capability the canonical script's flags don't already expose. (The related `run_via_aware_router.py` and `run_via_aware_real.py` are **not** duplicates of `run_router_v6.py` — they directly instantiate different router classes (`ExactGeometryRouterViaAware` vs `ExactGeometryRouter`) and are out of scope for this consolidation; see Open Questions.)
- **`batch_validate_power_pcb.py`, `batch_validate_power_pcb_fixed.py`, `batch_validate_power_pcb_fixed.py.bak`** — the original plus a "fixed" successor plus a backup file under git. Only one caller (`scripts/batch_validate.sh`, `benchmarks/COMPARISON_WORKFLOW.md`) references them. Note: N5 proposed `packages/temper-validation` as the canonical replacement; that is incorrect — `temper-validation` is a ground-truth *comparison* tool (wirelength / DRC compliance / routing-feasibility scoring) and does not run the `placement_routing_loop.py` sweep that `batch_validate_power_pcb.py` orchestrates. The canonical batch harness is `batch_validate_power_pcb.py`, not `temper-validate`.

The recurring failure shape: a fix lands in `_fixed` or `_v2`, the original is never deleted, future contributors copy the wrong one. CI cannot catch this because both files parse. The consolidation converts "two tracked impls, choose correctly" into "one tracked impl, choose by default."

---

## Actors

- A1. **Developer** — runs router validation, batch validation, and routing-strip workflows from the repo root or `scripts/`. The actor most likely to copy the wrong `strip_routing.py`.
- A2. **CI pipeline** — runs lint, tests, and (after the source-of-truth-validation work) golden-file diffs. The enforcement layer that should fail when a deleted script is still referenced.
- A3. **Benchmark / batch harness shells** — `scripts/batch_validate.sh`, `benchmarks/beads_epics.sh`, `benchmarks/QUICK_REFERENCE.md`-documented flows, `scripts/run_placement_experiments.py`. Callers that must migrate to the canonical entries before the duplicates can be deleted.

---

## Key Flows

- F1. **Developer strips routing from a PCB**
  - **Trigger:** A1 wants an unrouted board for placement benchmarking.
  - **Actors:** A1
  - **Steps:** (1) A1 invokes *one* canonical entry point — either `python -m temper_placer ... strip-routing` (the existing CLI subcommand path used by `run_benchmark.py`) or the `temper_placer.io.kicad_writer.strip_routing` function. (2) The function applies `keep_zones` / `keep_fills` per A1's flags. (3) The output board matches the fixture-ground-truth output byte-for-byte modulo whitespace. (4) The three `scripts/strip_routing*.py` files no longer exist; a shelled-out `python scripts/strip_routing_v2.py` is a "command not found" error, not a silent wrong answer.
  - **Outcome:** Exactly one path strips routing; output is reproducible by CI fixture.
  - **Covered by:** R1, R2, R3

- F2. **Developer runs router-v6 in three modes**
  - **Trigger:** A1 wants full, baseline, or minimal diagnostics.
  - **Actors:** A1, A3
  - **Steps:** (1) A1 invokes `run_router_v6.py --mode {full|baseline|minimal}` (or equivalent subcommand). (2) The same process handles the run — no `subprocess.run` re-invocation of itself, no stdout regex parsing. (3) The benchmark shells (`benchmarks/beads_epics.sh`, `scripts/batch_validate.sh`, `scripts/run_placement_experiments.py`) call only `run_router_v6.py`. (4) The three wrapper files (`run_router_v6_{minimal,simple,baseline}.py`) are deleted.
  - **Outcome:** One entry point, three named modes; no fragile stdout scraping in the repo.
  - **Covered by:** R4, R5, R6

- F3. **Developer runs batch validation across the power-PCB dataset**
  - **Trigger:** A1 wants per-board placement/routing metrics across the 20-board dataset.
  - **Actors:** A1, A3
  - **Steps:** (1) A1 invokes one canonical entry — either the surviving `batch_validate_power_pcb.py` or, if promoted, `python -m temper_placer batch-validate`. (2) The `_fixed.py` and `.bak` files do not exist; `git log` remains the history. (3) CI's grep step (R10) confirms no script in the repo references the deleted filenames.
  - **Outcome:** One entry point for the batch sweep; `temper-validate` remains the comparison-tool CLI (separate concern).
  - **Covered by:** R7, R8

- F4. **Future contributor adds a `_v2` of any script**
  - **Trigger:** A contributor is about to commit `foo_v2.py` next to `foo.py`.
  - **Actors:** A2
  - **Steps:** (1) The contributor opens `docs/consolidation-log.md` and sees the precedent. (2) A reviewer reading the PR description sees the log entry pointing to the pattern "extend the canonical, delete the fork." (3) The PR either deletes the original or documents in the log why a parallel fork is the correct shape (rare).
  - **Outcome:** Duplicate-by-default becomes extend-by-default.
  - **Covered by:** R9

---

## Requirements

**Track A — `strip_routing` consolidation**

- R1. The three files `scripts/strip_routing.py`, `scripts/strip_routing_v2.py`, `scripts/strip_routing_kiutils.py` are `git rm`'d. The canonical implementation remains `packages/temper-placer/.../kicad_writer.py:strip_routing()`. No new implementation is written.
- R2. `scripts/batch_validate.sh` (the only tracked caller of `strip_routing_v2.py`) is migrated to invoke the canonical entry — either the placer package CLI subcommand already used by `scripts/run_benchmark.py:13` or a direct `python -c "from temper_placer.io.kicad_writer import strip_routing; ..."` one-liner. The migrated call passes `keep_zones=True, keep_fills=False` to preserve current shell behavior.
- R3. A fixture corpus and regression test are added under `packages/temper-placer/tests/` (or `pcb/fixtures/` per the source-of-truth-validation convention): at least two committed `.kicad_pcb` files with known segment/via/arc counts; the test asserts `strip_routing(input)` yields an output whose `traceItems.segments/vias/arcs` are all empty *and* whose non-routing content (footprints, nets, zones when `keep_zones=True`) is byte-identical to a golden output modulo whitespace. This locks the consolidation as a regression test, so a future fork's behavior diff shows up in CI.

**Track B — router-runner consolidation**

- R4. The three files `run_router_v6_minimal.py`, `run_router_v6_simple.py`, `run_router_v6_baseline.py` are `git rm`'d. `run_router_v6.py` is the canonical router runner.
- R5. Prior to deletion, an audit (recorded in `docs/consolidation-log.md`) confirms that none of the three wrappers exposes a CLI flag or behavior not already expressible via `run_router_v6.py`'s existing flags (`--theta-star`, `--lazy-theta`, `--smoothing`, `--no-legalize`, `--placement-mode`, `--max-nets`, `--nets`). Any wrapper-unique flag that is still referenced by a tracked caller is **promoted** to `run_router_v6.py` as a CLI arg (not dropped); unused flags are noted as dropped in the log. This is the policy for "one-off flags worth preserving."
- R6. The wrapper-equivalent run modes are expressed on the canonical runner as a `--mode {full|baseline|minimal}` argument (or equivalent named profiles) so call sites that currently select a wrapper select a mode instead. The tracked callers — `benchmarks/beads_epics.sh`, `scripts/batch_validate.sh`, `scripts/run_placement_experiments.py`, and any benchmark doc referencing `_minimal`/`_simple`/`_baseline` — are migrated to `--mode ...` in the same PR.

**Track C — batch-validation consolidation**

- R7. `batch_validate_power_pcb_fixed.py` and `batch_validate_power_pcb_fixed.py.bak` are `git rm`'d. `batch_validate_power_pcb.py` is the canonical batch harness. (The "_fixed = improvement" pattern is replaced by "improve the original, rely on `git log` for history.")
- R8. A pressure-test decision — **assumed**: `batch_validate_power_pcb.py` **remains a root script** for this consolidation (not promoted to a `python -m temper_placer batch-validate` subcommand). Rationale: promotion is a larger refactor (argument surface, packaging, test relocation) that belongs with the broader SSOT-validation initiative, not this deletion-focused trio. The consolidation log records this as a deferred decision with a pointer; a future PR may promote it. `packages/temper-validation` is explicitly **not** the canonical replacement — its scope is ground-truth comparison, not the placement-routing-loop sweep.
- R9. CI (or a `make verify-consolidation` / `bd` task) runs a `grep` for the deleted filenames across the repo; any reference causes a failure with a named message. This is the regression gate that catches a resurrected caller (e.g., a stale benchmark shell invoking `strip_routing_v2.py`).

**Cross-cutting**

- R10. `docs/consolidation-log.md` is created as the durable record of this trio and as the convention for future consolidations. Each entry records: date, files deleted, canonical survivor, migration path, fixture/test added, unique flags preserved or dropped, and a one-line rationale. The source-of-truth-validation brainstorm's "consolidation log" mention is reconciled by pointing to this same file (single log, not two).
- R11. PR sequencing — **assumed**: three sequenced PRs, one per track, in order **A → B → C**. Rationale: Track A is the lowest-risk (canonical impl already exists, one shell caller); Track B is medium (three shell callers, mode surface change); Track C is the most coupled (overlaps with N1's `.bak`-file purge). Sequencing lets each PR's CI gate run against a stable baseline. A single combined PR is rejected as too large for review and too entangled with N1 to revert cleanly.

---

## Acceptance Examples

- AE1. **Covers R1, R2, R3.** Given `scripts/strip_routing_v2.py` is deleted, when `scripts/batch_validate.sh` runs, it invokes the placer CLI subcommand and produces an unrouted board whose `traceItems` counts match the golden fixture. When `python scripts/strip_routing_v2.py` is invoked, the shell returns "command not found."
- AE2. **Covers R4, R5, R6.** Given `benchmarks/beads_epics.sh` previously called `run_router_v6_baseline.py`, when the script is migrated to `run_router_v6.py --mode baseline`, the run produces the same metrics JSON shape as before. `git ls-files 'run_router_v6_*.py'` returns only `run_router_v6.py`.
- AE3. **Covers R7.** Given `batch_validate_power_pcb_fixed.py` is deleted, when `git log --oneline -- batch_validate_power_pcb.py` is consulted, the fix commits are visible in the original file's history. `git ls-files 'batch_validate_power_pcb*'` returns only `batch_validate_power_pcb.py`.
- AE4. **Covers R9.** Given a future commit adds `python scripts/strip_routing_v2.py` to a new shell script, when CI's verify-consolidation step runs, it fails with `Reference to deleted script 'strip_routing_v2.py' — use the placer CLI subcommand (see docs/consolidation-log.md).`
- AE5. **Covers R10.** Given a reviewer opens Track B's PR, the `docs/consolidation-log.md` diff shows: deleted `run_router_v6_{minimal,simple,baseline}.py`, survivor `run_router_v6.py`, migrated 3 shell callers, added `--mode` arg, no unique flags dropped, fixture = existing benchmark board.

---

## Success Criteria

- `git ls-files 'scripts/strip_routing*.py'` returns empty; the placer package's `strip_routing()` is the only implementation in the repo.
- `git ls-files 'run_router_v6*.py'` returns exactly `run_router_v6.py`; the three wrappers are gone and their callers pass `--mode`.
- `git ls-files 'batch_validate_power_pcb*'` returns exactly `batch_validate_power_pcb.py`; the `_fixed` and `.bak` are gone.
- A new contributor running `ls scripts/ | grep strip` finds nothing and is funneled by `docs/consolidation-log.md` to the placer CLI subcommand.
- The CI verify-consolidation grep step fails the first PR that re-introduces a deleted filename as a caller.
- In the three months after merge, no new `_v2.py` / `_fixed.py` / `_minimal.py` appears beside an existing script in `scripts/` or the repo root; if one does, the consolidation log convention is cited in its PR description.

---

## Scope Boundaries

- **`run_via_aware_router.py` and `run_via_aware_real.py`** — these are not duplicates of `run_router_v6.py`; they instantiate different router classes for via-aware routing and are exploratory entry points. They may be candidates for a separate "experiment-script disposition" pass (see Open Questions), but **out of scope for N5**.
- **`packages/temper-validation` as SSOT CLI** — N5's premise that this package replaces `batch_validate_power_pcb.py` is **incorrect** (verified by reading `temper_validation/cli.py`: it compares two PCBs, it does not sweep a dataset). Promoting `temper-validate` to absorb the batch sweep is a larger refactor that belongs with the source-of-truth-validation initiative, not this consolidation.
- **`packages/temper-testing`** — N5 mentioned a `scripts/temper_testing` path; that path does not exist. The `packages/temper-testing/` package is a property/oracle-testing toolkit unrelated to the three clusters. Not touched.
- **`scripts/run_placement_experiments.py` rewrite** — only the call sites invoking deleted scripts are migrated; rewriting the experiment runner itself is out of scope.
- **KiCad Python-plugin migration, Pydantic net-class model, DRU golden-file diffing** — all owned by the source-of-truth-validation initiative; not re-specified here. The `docs/consolidation-log.md` file is the only shared artifact.
- **N1 (Purge-and-Protect) overlap** — N1 owns untracked artifacts (`.bak`, build outputs, `__pycache__`, CI gates for untracked files). N5 owns tracked duplicate scripts. The single `_fixed.py.bak` is a boundary case: N1 deletes it as an untracked artifact pattern; N5 deletes `_fixed.py` as a tracked duplicate. R7 claims the `.bak` deletion here because it is adjacent to the tracked `_fixed.py`; if N1 lands first and removes the `.bak`, R7 simply skips it. The boundary is documented in `docs/consolidation-log.md`.

---

## Key Decisions

- **The canonical survivor already exists for every cluster.** No new canonical implementation is written. This is a deletion-and-migration project, not a design project. The risk is in caller migration, not in API design.
- **Unique wrapper flags are promoted, not dropped.** R5 codifies the policy: audit first, promote any caller-referenced flag, drop only unreferenced ones, and record the decision in the log. This is the answer to N5's "one-off flags worth preserving" question.
- **`docs/consolidation-log.md` is a new convention worth establishing.** Three deletions is the minimum non-trivial size; the value is not the three entries but the precedent and the CI grep gate (R9) that prevents recurrence. A log without the gate would be overkill; the gate without the log would be opaque. The two together justify the convention.
- **Three sequenced PRs, not one.** A → B → C. Track A is the safe warmup, Track B is the medium-risk core, Track C is the one most entangled with N1. Reviewers see small diffs; reverts are clean.
- **`batch_validate_power_pcb.py` stays a script for now.** Promotion to a `python -m temper_placer batch-validate` subcommand is deferred to the source-of-truth-validation initiative, which already owns packaging changes. This trio only deletes its duplicates, not itself.
- **`packages/temper-validation` is explicitly not the canonical batch CLI.** The N5 idea's framing here is corrected by code reading (see Problem Frame and Scope Boundaries). The consolidation log records this as a "do not promote to absorb batch sweep" note to prevent a future contributor from merging two unrelated concerns.

---

## Dependencies / Assumptions

- **The placer package's `strip_routing()` is correct.** Verified: it is the function imported by 5 internal call sites (`run_benchmark.py`, `generate_unrouted_benchmarks.py`, `mvp3_runner.py`, `visualize_placement.py`, the placer CLI `__init__.py:3844`). It already supports `keep_zones`/`keep_fills`, which the three scripts/ copies do not. Assumed correct pending Track A's regression fixture (R3), which will surface any latent bug.
- **`scripts/batch_validate.sh` is the only tracked caller of `strip_routing_v2.py`.** Verified by `grep -rln strip_routing_v2` across the repo at brainstorm time. If a private/untracked caller exists, R9's grep gate will fail after migration and force a fix.
- **The three router-runner wrappers add no unique flags.** Verified by sampling each — they are `subprocess.run(["python", "run_router_v6.py", ...], capture_output=True)` followed by stdout regex parsing. The canonical runner already accepts `--max-nets`, `--nets`, `--no-legalize`, `--placement-mode`, `--theta-star`, `--lazy-theta`, `--smoothing`. R5's audit is the formal confirmation step before deletion.
- **`run_via_aware_*.py` are not duplicates of `run_router_v6.py`.** Verified: they directly import and instantiate `ExactGeometryRouter` / `ExactGeometryRouterViaAware`, not the v6 pipeline. Their disposition is out of scope (see Open Questions).
- **`packages/temper-validation` is a comparison tool, not a batch sweep.** Verified by reading `temper_validation/cli.py`: its `cmd_compare` takes `--optimized` and `--reference` PCBs and produces a wirelength/DRC/routing-feasibility report. It does not loop `placement_routing_loop.py` across a dataset. Therefore it is not the canonical replacement for `batch_validate_power_pcb.py`.
- **N1 will delete untracked `.bak` files; N5 will delete tracked `_fixed.py`.** If N1 lands first and removes `batch_validate_power_pcb_fixed.py.bak`, R7 simply deletes the remaining tracked `_fixed.py`. No conflict.
- **Three PRs can land within the same sprint** so that the in-flight state (one cluster deleted, others not) does not break CI. Track A is independently safe; Track B requires migrating three shell callers in the same PR; Track C is internally safe. None depends on the others' merge order, but sequencing reduces reviewer load.

---

## Outstanding Questions

### Resolve Before Planning

- **[Affects R5][Audit]** Do `run_router_v6_{minimal,simple,baseline}.py` expose any CLI flag or behavior not expressible through `run_router_v6.py`'s existing args? The planning pass must diff each wrapper's `argv` against the canonical runner's argparse to confirm zero unique flags, or identify the ones to promote. Track B's PR is blocked on this audit.
- **[Affects R6][Mode surface]** Should the three "modes" be expressed as a single `--mode {full|baseline|minimal}` enum, or as composable flags (e.g., `--no-iterative --no-legalize`)? Enum is simpler; composable flags preserve the wrappers' thin-shell structure. Recommend enum; confirm at planning.
- **[Affects R3][Fixture]** Are the existing benchmark boards under `pcb/` or `benchmarks/` suitable as strip_routing fixtures, or do new minimal fixtures need to be committed? Reusing existing boards avoids new binary commits but couples the regression test to the benchmark corpus.

### Deferred to Planning

- **[Affects R8 / Track C boundary][Scope]** Should `batch_validate_power_pcb.py` itself eventually be promoted to `python -m temper_placer batch-validate`? This trio defers the decision; the source-of-truth-validation initiative may claim it. The consolidation log records the deferral.
- **[Out-of-scope probe]** Are `run_via_aware_router.py` and `run_via_aware_real.py` still used by any tracked caller, or are they exploratory scripts that could be archived under `docs/legacy/` in a separate disposition pass? `grep -rln run_via_aware` at brainstorm time found only `benchmarks/QUICK_REFERENCE.md` and `POWER_PCB_VALIDATION_TDD.md` references, no executable caller. Recommend a separate follow-up issue, not part of N5.
- **[Affects R10][Convention]** Should `docs/consolidation-log.md` live at `docs/` root (as proposed) or under `docs/brainstorms/` alongside this requirements doc? Root is more discoverable for contributors; brainstorms is more cohesive with the design record. Recommend root, with a backreference pointer from this brainstorm.
- **[Affects R9][CI gate]** Is the grep-based "verify-consolidation" step best added as a pre-commit hook, a `make`/`just` target, or a GitHub Actions job? Pre-commit is fastest feedback; CI is most authoritative. Recommend CI, with pre-commit as a stretch goal — confirm during planning against the existing CI shape.