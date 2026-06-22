---
title: "feat: Duplicate-Script Consolidation Trio"
type: feat
status: active
date: 2026-06-22
origin: docs/brainstorms/2026-06-21-duplicate-script-consolidation-requirements.md
---

# feat: Duplicate-Script Consolidation Trio

## Summary

A three-track deletion-and-migration project that removes every tracked duplicate script in the Temper repo and routes each caller to one canonical implementation per concern. No new canonical implementation is written — each cluster already has a de-facto survivor, so the work is *audit, migrate call sites, delete, gate*. The trio: (a) **Track A** deletes the three stale `scripts/strip_routing*.py` copies in favor of `packages/temper-placer/.../kicad_writer.py:strip_routing()` and migrates the single tracked caller (`scripts/batch_validate.sh`); (b) **Track B** deletes the three `run_router_v6_{minimal,simple,baseline}.py` wrappers after an audit confirms they add no unique behavior and have zero executed callers — only documentation references; (c) **Track C** ports the beneficial deltas from `batch_validate_power_pcb_fixed.py` into the canonical `batch_validate_power_pcb.py`, then deletes the `_fixed.py`. A `docs/consolidation-log.md` convention artifact and a CI grep guard (R9) make the deletions durable against recurrence.

This plan corrects two premise errors in the origin requirements doc, both verified against current `main`:

1. **There is no `strip-routing` placer CLI subcommand.** `strip_routing` is an internal function in `packages/temper-placer/temper_placer/io/kicad_writer.py:674`, called in-process by the `place-deterministic` Click command (`packages/temper-placer/temper_placer/cli/__init__.py:3844,3892`) and imported directly by `scripts/run_benchmark.py:13`. R2 therefore migrates `scripts/batch_validate.sh` to a `python -c` one-liner, not a CLI subcommand.
2. **The `run_router_v6_{minimal,simple,baseline}.py` wrappers are not single-board run modes.** They are dataset-sweep harnesses, and `run_router_v6_baseline.py` is not a subprocess wrapper at all (it in-processes `RouterV6Pipeline(enable_legalization=False)`). R6's `--mode {full|baseline|minimal}` flag is therefore **rejected** — every underlying flag (`--no-legalize`, `--max-nets`) already exists on canonical `run_router_v6.py`. The wrappers are effectively dead/broken exploratory scripts with no executed caller, so Track B is deletion + doc cleanup, not mode-surface design.

The plan ships as **three sequenced PRs (A → B → C)** plus a Phase 0 convention artifact that lands in PR 1 and a Phase 4 CI guard that lands in PR 3 (the highest-risk track). Sequencing keeps each PR's diff small and let each track's CI gate run against a stable baseline.

---

## Problem Frame

The Temper repo grew organically during the router-v6 sprint: each experiment forked a script, each fix forked a script, and the originals were never deleted after the fork was proven. Three clusters now have multiple tracked implementations of the same intent. Verified state of current `main`:

### Track A — `strip_routing` (3 stale copies, 1 canonical)

| # | Path | Status |
|---|------|--------|
| canonical | `packages/temper-placer/temper_placer/io/kicad_writer.py:674` (`strip_routing(input_pcb, output_pcb, keep_zones=True, keep_fills=False) -> StrippingResult`) | authority — imported by 5 internal call sites |
| dup 1 | `scripts/strip_routing.py` | stale, less capable (no `keep_zones`/`keep_fills`) |
| dup 2 | `scripts/strip_routing_v2.py` | stale; **only executed tracked caller** = `scripts/batch_validate.sh:32` |
| dup 3 | `scripts/strip_routing_kiutils.py` | stale, no tracked caller |

The canonical `strip_routing()` is imported by `scripts/run_benchmark.py:13`, `packages/temper-placer/scripts/generate_unrouted_benchmarks.py`, `packages/temper-placer/temper_placer/pipeline/mvp3_runner.py`, `scripts/visualize_placement.py`, and the `place-deterministic` Click command. It already supports `keep_zones`/`keep_fills`; the three `scripts/` copies do not.

### Track B — router runners (3 wrappers, 1 canonical, 1 separate sibling)

| # | Path | Status |
|---|------|--------|
| canonical | `run_router_v6.py` (root) | authority — full argparse: `--pcb`, `--theta-star`, `--lazy-theta`, `--smoothing`, `--no-legalize`, `--placement-mode`, `--max-nets`, `--nets`, `--profile`, `--exact`, `--timeout` |
| sibling | `scripts/run_router_v6.py` | minimal variant referenced by integration tests — **out of scope for N5** (not a wrapper of the root canonical; lives under `scripts/`) |
| wrapper 1 | `run_router_v6_minimal.py` (root) | `subprocess.run(["run_router_v6.py", board, "-o", out])`; parses `"Routed:"` stdout; **has syntax bug** (`len([1]) if len([1]) > 0 else 1) * 100` — extra paren) + missing `Progress` import — broken |
| wrapper 2 | `run_router_v6_simple.py` (root) | `subprocess.run(["run_router_v6.py", "-o", out, "--max-nets", "30", "--verbose"])`; canonical has no `--verbose` flag; hardcoded 4-board list — broken against canonical |
| wrapper 3 | `run_router_v6_baseline.py` (root) | **NOT a subprocess wrapper** — directly instantiates `RouterV6Pipeline(enable_legalization=False)` in-process; equivalent to canonical `--no-legalize` |

**Wrapper callers — verified by `grep -rln` across the repo:** zero executed callers. The only references are:
- `benchmarks/beads_epics.sh:296,309` — both inside `bd create --acceptance "..."` / `--description "..."` heredoc strings (task-tracking text, not executed)
- `benchmarks/EPIC_SUMMARY.md:192,199` — markdown documentation
- `benchmarks/QUICK_REFERENCE.md:47` — markdown documentation

This makes Track B deletion + doc cleanup, with no shell caller migration required.

### Track C — batch validation (1 canonical, 1 tracked supersession, 1 untracked backup)

| # | Path | Status |
|---|------|--------|
| canonical | `batch_validate_power_pcb.py` (root) | authority — orchestrates `placement_routing_loop.py` sweep across `power_pcb_dataset/inventory.csv` |
| supersession | `batch_validate_power_pcb_fixed.py` (root, **git-tracked**) | adds `ExperimentConfig` dataclass + per-topology iteration configs + `has_components` filtering (`batch_validate_power_pcb_fixed.py:31-110`) |
| backup | `batch_validate_power_pcb_fixed.py.bak` (root, **untracked** — verified absent from `git ls-files`) | filesystem artifact; N1 owns its deletion as an untracked `.bak`-pattern purge |

The recurring failure shape: a fix lands in `_fixed` or `_v2`, the original is never deleted, future contributors copy the wrong one. CI cannot catch this because both files parse. The consolidation converts "two tracked impls, choose correctly" into "one tracked impl, choose by default."

---

## Scope Boundaries

### In scope

- R1–R11 from the origin requirements document: delete 7 tracked duplicate scripts (3 + 3 + 1), migrate 1 executed shell caller (`scripts/batch_validate.sh`), add 1 regression fixture + test, create `docs/consolidation-log.md`, add 1 CI grep guard.
- Port the `ExperimentConfig` + `has_components` filtering deltas from `batch_validate_power_pcb_fixed.py` into `batch_validate_power_pcb.py` before deletion (R7).

### Deferred

- **R8 promotion of `batch_validate_power_pcb.py` to `python -m temper_placer batch-validate`** — deferred to the source-of-truth-validation initiative (companion plan `docs/plans/2026-06-21-002-feat-source-of-truth-validation-plan.md`), which already owns packaging changes. This trio only deletes its duplicates, not itself. The consolidation log records the deferral with a pointer.
- **`packages/temper-validation` as canonical batch CLI** — explicitly *not* the replacement. `temper-validate` compares two PCBs (wirelength/DRC/feasibility); it does not sweep a dataset. The log records a "do not promote to absorb batch sweep" note.

### Out of scope

- `run_via_aware_router.py` and `run_via_aware_real.py` — not duplicates of `run_router_v6.py`; they instantiate different router classes (`ExactGeometryRouterViaAware` vs `ExactGeometryRouter`). Separate disposition pass; see Deferred to Implementation.
- `scripts/run_router_v6.py` (the `scripts/` sibling) — referenced by integration tests; not a wrapper of the root canonical and not part of the duplicate cluster.
- `scripts/run_placement_experiments.py` rewrite — only call sites invoking deleted scripts would migrate; verified no such call sites exist, so the file is untouched.
- Pydantic net-class model, DRU golden-file diffing, KiCad headless DRC — owned by the source-of-truth-validation initiative.
- **N1 (Purge-and-Protect) overlap:** N1 owns untracked artifacts (`.bak`, build outputs, `__pycache__`); N5 owns tracked duplicate scripts. The single `batch_validate_power_pcb_fixed.py.bak` is the boundary case: if N1 lands first and removes the untracked `.bak`, R7 simply skips the `.bak` deletion. The boundary is documented in `docs/consolidation-log.md`.

---

## Key Technical Decisions

1. **No new canonical implementation is written.** Every cluster already has a survivor. This is a deletion-and-migration project, not a design project. The risk is in caller migration, not API design.
2. **R2 migrates `scripts/batch_validate.sh:32` to a `python -c` one-liner**, not a placer CLI subcommand. Verified: the placer CLI (Click-based, `packages/temper-placer/temper_placer/cli/__init__.py`) has no `strip-routing` subcommand. `strip_routing` is an internal function surfaced only through `place-deterministic` (which does placement+routing, not strip-only). Adding a `strip-routing` subcommand would be a new implementation, violating R1's "no new implementation is written." The `python -c "from temper_placer.io.kicad_writer import strip_routing; strip_routing(Path('$board'), Path('$out'), keep_zones=True)"` form is the smallest faithful migration. The origin doc's explicit "either the CLI subcommand *or* a `python -c` one-liner" allows this branch.
3. **R6 `--mode {full|baseline|minimal}` flag is REJECTED.** The wrappers are dataset-sweep harnesses, not single-board run modes; `run_router_v6_baseline.py` is not even a subprocess wrapper (it in-processes `RouterV6Pipeline(enable_legalization=False)`). Every underlying flag (`--no-legalize`, `--max-nets`) already exists on canonical `run_router_v6.py`. Adding `--mode` would be a new abstraction for a behavior that has zero executed callers. The audit (R5) records this verdict in `docs/consolidation-log.md`; the wrappers are deleted outright.
4. **R5 audit verdict: zero unique flags to promote.**
   - `run_router_v6_minimal.py`: no unique flags; broken (syntax bug, missing import). Dropped.
   - `run_router_v6_simple.py`: unique `--verbose` flag — canonical has no `--verbose`; the wrapper is the only referent and is broken against canonical. Also broken: undefined `console` (no import at L30-32), undefined `nets` variable at L53, and the `pcb_path` parameter is never forwarded to subprocess (only routes the default board). Dropped.
   - `run_router_v6_baseline.py`: in-process `enable_legalization=False` = canonical `--no-legalize`. No unique flag. Dropped.
5. **R3 fixture reuses existing committed boards.** `packages/temper-placer/tests/fixtures/{minimal_board,medium_board,large_board}.kicad_pcb` are committed and suitable. No new binary commits. The regression test asserts `strip_routing(input)` yields empty `segments/vias/arcs` and byte-identical non-routing content (modulo whitespace) against a golden output generated *by the canonical function itself* in the test's setup phase — this locks the consolidation as a regression test without coupling to a hand-maintained golden.
6. **R7 ports deltas before deletion.** `batch_validate_power_pcb_fixed.py` contains two beneficial, non-conflicting deltas: the `ExperimentConfig` dataclass (`batch_validate_power_pcb_fixed.py:38-110`) and the `has_components` filtering loop (`batch_validate_power_pcb_fixed.py:137-143`). Track C ports both into `batch_validate_power_pcb.py` in the same PR as the deletion, so the deletion loses no behavior. If a delta conflicts with an existing caller's usage of the original (per `POWER_PCB_VALIDATION_TDD.md` examples), the conflict is documented in the log and that delta is skipped rather than force-merged.
7. **`docs/consolidation-log.md` lives at `docs/` root**, with a backreference pointer appended to `docs/brainstorms/2026-06-21-duplicate-script-consolidation-requirements.md`. Root is more discoverable for contributors; the brainstorms doc retains the design record.
8. **R9 CI gate is a pytest in `packages/temper-drc/tests/`**, not a pre-commit hook. The `temper-drc` package already owns repo-wide invariant guards and has a `conftest.py`; placing the guard there keeps it beside sibling static checks and runs in the existing `python-tests.yml` job. The test scans `git ls-files` for a denylist of deleted filenames and fails with a named message. The CI `paths:` filter in `.github/workflows/python-tests.yml` is extended to include `scripts/**` and `tests/**` so the guard runs on PRs touching those paths.

---

## Implementation Units

### Phase 0 — Convention artifact (lands in PR 1)

**U1. Create `docs/consolidation-log.md`**
- **Files touched:** `docs/consolidation-log.md` (new), `docs/brainstorms/2026-06-21-duplicate-script-consolidation-requirements.md` (append backreference).
- **Steps:**
  1. Create `docs/consolidation-log.md` with a header explaining the convention ("each entry records: date, files deleted, canonical survivor, migration path, fixture/test added, unique flags preserved or dropped, one-line rationale") and a template block future contributors copy.
  2. Append a one-line backreference to the bottom of the origin brainstorm: `> Consolidation log: docs/consolidation-log.md`.
- **Acceptance:** `docs/consolidation-log.md` exists, parses as markdown, and contains the template. The brainstorm doc has the backreference line.

### Phase 1 — Track A: `strip_routing` consolidation (PR 1)

**U2. Migrate `scripts/batch_validate.sh` to canonical `strip_routing()`**
- **Files touched:** `scripts/batch_validate.sh:32`.
- **Steps:**
  1. Replace the line `python scripts/strip_routing_v2.py "$board_path" \` with a `python -c` one-liner invoking `temper_placer.io.kicad_writer.strip_routing` with `keep_zones=True, keep_fills=False` (preserving current shell behavior — the `_v2` script strips traces/vias, keeps zones).
  2. Verify the migrated call produces an unrouted board whose `traceItems.segments/vias/arcs` are empty and whose footprints/zones/Edge.Cuts are preserved (the U4 regression test pins this).
- **Acceptance:** `scripts/batch_validate.sh` no longer references `strip_routing_v2.py`; running it on a fixture board produces the same unrouted output shape as before migration.

**U3. Delete the three `scripts/strip_routing*.py` files**
- **Files touched:** `scripts/strip_routing.py`, `scripts/strip_routing_v2.py`, `scripts/strip_routing_kiutils.py` (`git rm`).
- **Steps:**
  1. `git rm scripts/strip_routing.py scripts/strip_routing_v2.py scripts/strip_routing_kiutils.py`.
  2. Verify `git ls-files 'scripts/strip_routing*.py'` returns empty.
  3. Append the Track A entry to `docs/consolidation-log.md` (date, deleted files, survivor = `packages/temper-placer/.../kicad_writer.py:strip_routing`, migration path = `python -c` one-liner, fixture = U4 test, unique flags dropped = none, rationale = "canonical already supports keep_zones/keep_fills; scripts/ copies did not").
- **Acceptance:** `git ls-files 'scripts/strip_routing*.py'` returns empty. `grep -rln "strip_routing_v2\|strip_routing_kiutils\|scripts/strip_routing\.py" --include='*.sh' --include='*.py' --include='*.md' .` (excluding `docs/brainstorms/` and `docs/plans/` and `docs/consolidation-log.md`) returns empty.

**U4. Add `strip_routing` regression fixture + test**
- **Files touched:** `packages/temper-placer/tests/test_strip_routing_consolidation.py` (new).
- **Steps:**
  1. New test file. Use the committed boards at `packages/temper-placer/tests/fixtures/minimal_board.kicad_pcb` and `packages/temper-placer/tests/fixtures/medium_board.kicad_pcb` as inputs.
  2. Test 1 (idempotence): assert `strip_routing(input, out, keep_zones=True, keep_fills=False)` produces an output whose parsed `traceItems.segments`, `traceItems.vias`, `traceItems.arcs` are all empty.
  3. Test 2 (content preservation): assert the output's footprints, nets, zones (when `keep_zones=True`), and Edge.Cuts are byte-identical to the input modulo whitespace. Use a normalized text comparison (strip per-line whitespace, ignore blank-line differences) to avoid coupling to kiutils formatter churn.
  4. Test 3 (canonical-is-the-only-impl): assert `git ls-files 'scripts/strip_routing*.py'` returns empty — this is the repo-state guard.
- **Acceptance:** The three tests pass on PR 1's branch. Test 3 fails if any `scripts/strip_routing*.py` is re-introduced.

### Phase 2 — Track B: router-runner consolidation (PR 2)

**U5. Audit the three wrappers and record the verdict in the log**
- **Files touched:** `docs/consolidation-log.md` (append Track B entry).
- **Steps:**
  1. Diff each wrapper's `argv` / in-process construction against canonical `run_router_v6.py`'s argparse (`--pcb`, `--theta-star`, `--lazy-theta`, `--smoothing`, `--no-legalize`, `--placement-mode`, `--max-nets`, `--nets`, `--profile`, `--exact`, `--timeout`).
  2. Record the verdict per wrapper in the log:
     - `run_router_v6_minimal.py`: no unique flags; broken (syntax bug at `len([1]) if len([1]) > 0 else 1) * 100`, missing `Progress` import). Dropped.
     - `run_router_v6_simple.py`: unique `--verbose` — canonical has no `--verbose`; wrapper is the only referent and is broken against canonical. Dropped.
     - `run_router_v6_baseline.py`: in-process `RouterV6Pipeline(enable_legalization=False)` = canonical `--no-legalize`. No unique flag. Dropped.
  3. Record the R6 verdict: `--mode {full|baseline|minimal}` rejected — wrappers are dataset sweeps, not single-board modes; underlying flags already on canonical.
- **Acceptance:** The log entry exists and cites real identifiers/line numbers from each wrapper. A reviewer can reproduce the audit by reading the cited lines.

**U6. Delete the three wrappers + repoint documentation references**
- **Files touched:** `run_router_v6_minimal.py`, `run_router_v6_simple.py`, `run_router_v6_baseline.py` (`git rm`); `benchmarks/beads_epics.sh:296,309`, `benchmarks/EPIC_SUMMARY.md:192,199`, `benchmarks/QUICK_REFERENCE.md:47` (doc text updates).
- **Steps:**
  1. `git rm run_router_v6_minimal.py run_router_v6_simple.py run_router_v6_baseline.py`.
  2. Update the two `bd create` heredoc strings in `benchmarks/beads_epics.sh` (lines 296, 309) to reference `run_router_v6.py --no-legalize` instead of `power_pcb_dataset/run_router_v6_baseline.py`. These are task-tracking text, not executed calls, but the references must not point at deleted files.
  3. Update `benchmarks/EPIC_SUMMARY.md:192,199` and `benchmarks/QUICK_REFERENCE.md:47` similarly.
  4. Verify `git ls-files 'run_router_v6*.py'` returns exactly `run_router_v6.py` and `scripts/run_router_v6.py`.
- **Acceptance:** `git ls-files 'run_router_v6*.py'` returns exactly `run_router_v6.py` and `scripts/run_router_v6.py`. `grep -rln "run_router_v6_minimal\|run_router_v6_simple\|run_router_v6_baseline" --include='*.sh' --include='*.py' --include='*.md' .` (excluding `docs/brainstorms/`, `docs/plans/`, `docs/consolidation-log.md`) returns empty.

### Phase 3 — Track C: batch-validation consolidation (PR 3)

**U7. Port `ExperimentConfig` + `has_components` deltas into canonical**
- **Files touched:** `batch_validate_power_pcb.py`.
- **Steps:**
  1. Read `batch_validate_power_pcb_fixed.py` end-to-end. Identify the `ExperimentConfig` dataclass (`:38-118`) and the `has_components` filtering loop (`:137-143`).
  2. Port the `ExperimentConfig` dataclass and the per-topology iteration configs (`mppt`, `bms`, `inverter`, `buck`, `boost`, `motor_driver`) into `batch_validate_power_pcb.py`.
  3. Port the `has_components` filtering logic, preserving the canonical's existing topology-sweep structure (the canonical has more `topology` references — 64 vs `_fixed`'s 51 — they are different swaths; do not regress the canonical's coverage).
  4. If a delta conflicts with an existing caller's usage (per `POWER_PCB_VALIDATION_TDD.md` examples), document the conflict in `docs/consolidation-log.md` and skip that delta rather than force-merging.
  5. Run the canonical on a single fixture board to confirm it still parses and produces the expected metrics JSON shape.
- **Acceptance:** `batch_validate_power_pcb.py` contains `ExperimentConfig` and the `has_components` filter; running it on a fixture board from `power_pcb_dataset/inventory.csv` produces the same metrics JSON shape as before. No conflict is silently merged.

**U8. Delete `batch_validate_power_pcb_fixed.py` (and the `.bak` if present)**
- **Files touched:** `batch_validate_power_pcb_fixed.py` (`git rm`); `batch_validate_power_pcb_fixed.py.bak` (delete from filesystem if present — untracked, N1 boundary).
- **Steps:**
  1. `git rm batch_validate_power_pcb_fixed.py`.
  2. If `batch_validate_power_pcb_fixed.py.bak` still exists on the filesystem (N1 may have already removed it), `rm` it. Record the boundary in the log: "N1 owns untracked `.bak` purge; N5 deletes the tracked `_fixed.py`. If N1 landed first, R7 skips the `.bak`."
  3. Append the Track C entry to `docs/consolidation-log.md` (date, deleted = `_fixed.py` + `.bak`, survivor = `batch_validate_power_pcb.py`, migration path = delta port in U7, fixture = none new, unique flags = n/a, rationale = "_fixed = improvement" pattern replaced by "improve the original, rely on git log").
  4. Verify `git ls-files 'batch_validate_power_pcb*'` returns exactly `batch_validate_power_pcb.py`.
- **Acceptance:** `git ls-files 'batch_validate_power_pcb*'` returns exactly `batch_validate_power_pcb.py`. `git log --oneline -- batch_validate_power_pcb.py` shows the fix history is preserved in the canonical's history.

### Phase 4 — CI grep guard (lands in PR 3)

**U9. Add consolidation guard test + extend CI `paths:` filter**
- **Files touched:** `packages/temper-drc/tests/test_consolidation_guard.py` (new), `.github/workflows/python-tests.yml` (extend `paths:`).
- **Steps:**
  1. New test file `packages/temper-drc/tests/test_consolidation_guard.py`. The test:
     - Defines a denylist of deleted filenames: `scripts/strip_routing.py`, `scripts/strip_routing_v2.py`, `scripts/strip_routing_kiutils.py`, `run_router_v6_minimal.py`, `run_router_v6_simple.py`, `run_router_v6_baseline.py`, `batch_validate_power_pcb_fixed.py`.
     - Runs `git ls-files` and asserts none of the denylist files are tracked.
     - Runs `git grep` (or `grep -r` over `git ls-files`) for each deleted basename and asserts no reference exists outside `docs/brainstorms/`, `docs/plans/`, `docs/consolidation-log.md`. Failure message: `Reference to deleted script '<name>' — use the canonical survivor (see docs/consolidation-log.md).`
  2. Extend the `paths:` filter in `.github/workflows/python-tests.yml` so the python-tests job triggers on changes under `scripts/**` (in addition to the existing `packages/**` paths). The guard test itself lives under `packages/temper-drc/tests/` which is already covered by `packages/**`; the root `tests/**` glob is not needed. This ensures the guard runs on PRs touching shell scripts or test files.
  3. Verify the guard passes on PR 3's branch and would fail if a deleted filename were re-introduced.
- **Acceptance:** `pytest packages/temper-drc/tests/test_consolidation_guard.py` passes. Manually re-introducing a reference to `strip_routing_v2.py` in a shell script causes the test to fail with the named message.

---

## System-Wide Impact

- **`scripts/batch_validate.sh`** — one-line change at `:32`; behavior preserved (strips routing, keeps zones).
- **`packages/temper-placer/tests/`** — gains one new test file (`test_strip_routing_consolidation.py`); no existing tests modified.
- **`packages/temper-drc/tests/`** — gains one new guard test (`test_consolidation_guard.py`); no existing tests modified.
- **`benchmarks/`** — three doc-text updates (no executed code changes); the `bd create` heredoc strings in `beads_epics.sh` are task-tracking text, not runtime invocations.
- **`docs/`** — one new file (`consolidation-log.md`); one backreference line appended to the origin brainstorm.
- **`.github/workflows/python-tests.yml`** — `paths:` filter extended; no job logic changes.
- **Root scripts** — 7 files deleted; 1 file modified (`batch_validate_power_pcb.py`); no new root scripts created.
- **No firmware, no PCB schematics, no placer algorithm changes.** This is a repo-hygiene initiative; the router, placer, and DRC code are untouched.

---

## Risk Analysis & Mitigation

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| A private/untracked caller of `strip_routing_v2.py` exists that U2 misses | Low (verified at brainstorm + planning time) | Medium — caller breaks silently | R9 grep guard fails after migration and forces a fix. The guard is the safety net, not the audit. |
| A wrapper has an executed caller U6 misses | Low (verified: only doc/heredoc references) | Medium — caller breaks | Same R9 guard. The guard scans all `git ls-files` text, not just shell scripts. |
| Porting `ExperimentConfig` into canonical regresses the canonical's existing topology sweep | Medium (canonical has more `topology` references than `_fixed`) | High — batch validation produces wrong metrics | U7 step 4: if a delta conflicts with existing caller usage, skip rather than force-merge; document in log. U7 step 5: run canonical on a fixture board and confirm metrics JSON shape unchanged before deletion. |
| `docs/consolidation-log.md` becomes an unused artifact | Medium | Low — convention fails to prevent recurrence | The R9 CI guard is the active enforcement; the log is the human-readable record cited in the guard's failure message. The two together justify the convention. |
| PR 3 (Track C) lands before N1, leaving the `.bak` file | Low | Low — `.bak` is untracked, doesn't affect CI | U8 step 2: if the `.bak` still exists, `rm` it; otherwise skip. Boundary documented in the log. |
| `scripts/run_router_v6.py` (the `scripts/` sibling) is accidentally deleted | Low | High — integration tests break | U6 acceptance check explicitly verifies `git ls-files 'run_router_v6*.py'` returns *both* `run_router_v6.py` and `scripts/run_router_v6.py`. The guard test denylist lists only the three wrappers, not the sibling. |

---

## Test Strategy

- **Unit/regression (Track A):** `packages/temper-placer/tests/test_strip_routing_consolidation.py` — idempotence (empty `segments/vias/arcs`), content preservation (byte-identical footprints/zones/Edge.Cuts modulo whitespace), and repo-state guard (`scripts/strip_routing*.py` not tracked).
- **Repo-state guard (cross-cutting, R9):** `packages/temper-drc/tests/test_consolidation_guard.py` — denylist of 7 deleted filenames; asserts none tracked and none referenced outside `docs/`.
- **Manual smoke (Track A):** run `scripts/batch_validate.sh` on a fixture board; confirm unrouted output matches pre-migration shape.
- **Manual smoke (Track B):** `git ls-files 'run_router_v6*.py'` returns exactly the canonical + the `scripts/` sibling; `grep -rln run_router_v6_{minimal,simple,baseline}` returns only docs.
- **Manual smoke (Track C):** run `batch_validate_power_pcb.py` on one board from `power_pcb_dataset/inventory.csv`; confirm metrics JSON shape unchanged after the delta port; `git log --oneline -- batch_validate_power_pcb.py` shows fix history preserved.
- **CI:** the existing `python-tests.yml` job runs both new test files; the `paths:` extension ensures they trigger on `scripts/**` and `tests/**` changes.

---

## Deferred to Implementation

- **`run_via_aware_router.py` and `run_via_aware_real.py` disposition** — separate follow-up issue. At brainstorm time `grep -rln run_via_aware` found only `benchmarks/QUICK_REFERENCE.md` and `POWER_PCB_VALIDATION_TDD.md` references, no executable caller. Recommend a separate "experiment-script disposition" pass that either archives them under `docs/legacy/` or deletes them if confirmed exploratory.
- **`batch_validate_power_pcb.py` promotion to `python -m temper_placer batch-validate`** — deferred to the source-of-truth-validation initiative (`docs/plans/2026-06-21-002-feat-source-of-truth-validation-plan.md`). The consolidation log records the deferral with a pointer.
- **Pre-commit hook for the R9 guard** — stretch goal. The CI guard is the authoritative enforcement; a pre-commit mirror would give faster local feedback but is not required for the convention to hold.
- **`scripts/run_router_v6.py` (the `scripts/` sibling) disposition** — not part of N5; if it should fold into the root canonical, that is a separate scope decision owned by the router-maintenance track, not the duplicate-script consolidation.
