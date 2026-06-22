---
date: 2026-06-21
topic: cython-twin-measure
---

# Cython Twin: Measure-Then-Decide for the A* Hot Path

## Summary

A two-step initiative that (1) finalizes the incomplete Jan 17 2026 cleanup of the deleted Cython A* twin — removing dangling build config, a runtime import that always fails, and an archived benchmark — and (2) runs a measure-first gate on the now-pure-Python active A* (`packages/temper-placer/temper_placer/router_v6/astar_pathfinding.py`, 2289 lines) against the existing multi-board benchmark corpus. If the hot path does not clear a material speedup threshold, deletion is finalized and a regression benchmark locks the pure-Python performance. If it clears the threshold, a Cython twin is re-introduced via codegen from type-annotated `.py`, with a parity test asserting byte-identical routes against golden fixtures. The parity test is added regardless of outcome so that any future twin is safe to delete again.

---

## Problem Frame

The original ideation (N7) framed this as "two hand-maintained copies of A* with drift risk." Verifying the codebase changes that framing:

- The Cython twin (`packages/temper-placer/src/temper_placer/routing/astar/astar_core.{pyx,pxd}`, 707 lines) was **deleted** in commit `3314d94a` ("Major Cleanup: JAX Removal, Legacy Purge, and Structural Flattening", Jan 17 2026) along with the entire `routing/astar/` package. It no longer exists on `main`; the only on-disk copy lives in a stale agent worktree (`.claude/worktrees/agent-ac3b6b1a386e1bf71/`).
- The cleanup was **incomplete**. Four classes of dangling reference remain on `main`:
  1. `packages/temper-placer/setup.py` still defines an `Extension("temper_placer.routing.astar.astar_core", [.../astar_core.pyx], ...)` and calls `cythonize(...)` — a build script that fails on a missing source file.
  2. `packages/temper-placer/pyproject.toml` still lists `Cython>=3.0.0` as a dependency and carries a `[tool.cython]` section.
  3. `packages/temper-placer/temper_placer/deterministic/stages/multilayer_astar.py:263-301` still runs `from temper_placer.routing.astar import find_path as find_path_impl` on every `find_path` call (guarded only by `TEMPER_USE_CYTHON_ASTAR` defaulting to `"1"`), catches the guaranteed `ImportError`, prints a warning, and falls through to Python. This is dead code that fires an exception-and-recover on every invocation of the legacy deterministic router.
  4. `docs/reports/PERFORMANCE_OPTIMIZATION_SESSION.md` and `router-experiments/reports/exp_24_piantor_2026-01-10.md` still cite the Cython twin as live infrastructure, including the `TEMPER_USE_CYTHON_ASTAR` env var and a 40× per-path speedup claim (0.086 ms vs 3.5 ms) that is no longer reproducible because the implementation is gone.
- The **active** A* — `router_v6/astar_pathfinding.py`, 2289 lines, pure Python, imported by `router_v6/pipeline.py:21` — has **no** Cython twin and references none. It is the canonical router. The legacy `deterministic/stages/multilayer_astar.py` is still imported by `pipeline/mvp3_runner.py` and several diagnostic scripts, so its dead Cython branch is not strictly unreachable.

So the real problem has two parts, not one: (a) a drift-causing incomplete deletion that should be finalized regardless of any performance decision, and (b) an open question about whether the now-pure-Python active hot path justifies re-introducing a Cython twin — informed by measurement, not by the historical 40× figure that was measured against a different (now-deleted) implementation on a different router generation.

---

## Actors

- A1. **Developer** — runs the router, edits `router_v6/astar_pathfinding.py`, observes routing-stage wall time.
- A2. **CI pipeline** — runs the benchmark corpus, the parity test (if a twin exists), and the performance-regression gate. The enforcement layer for both the measure-first gate and any future drift.
- A3. **Build system** (`pyproject.toml`, `setup.py`, hatchling) — the surface on which a re-introduced Cython twin would be compiled; today, the surface that carries the broken `cythonize(...)` call.

---

## Key Flows

- F1. **Developer runs the router on a representative board**
  - **Trigger:** A1 invokes the router (CLI or `router_v6/benchmark.py`) on one of the corpus boards.
  - **Actors:** A1
  - **Steps:** (1) A1 runs the router. (2) The active `router_v6/astar_pathfinding.py` is exercised; no Cython import is attempted because router_v6 has no Cython code path. (3) The benchmark runner records per-path and per-stage timings. (4) A1 reads the routing-stage wall time and per-path A* latency.
  - **Outcome:** A reproducible measurement of the pure-Python hot path on a known corpus, suitable for comparison against any future Cython twin.
  - **Covered by:** R1, R3

- F2. **CI finalizes the deletion of the Cython twin**
  - **Trigger:** Push to `main`.
  - **Actors:** A2
  - **Steps:** (1) A2 runs lint/tests. (2) `setup.py` no longer references `astar_core.pyx`; `pyproject.toml` no longer declares `Cython>=3.0.0` or a `[tool.cython]` section. (3) `multilayer_astar.py` no longer attempts `from temper_placer.routing.astar import find_path`. (4) The perf doc and the experiment report carry a dated note that the Cython twin was removed in Jan 2026 and any re-introduction is gated on R3's measurement.
  - **Outcome:** No on-disk artifact references a deleted file; no runtime path attempts an import that is guaranteed to fail; the build no longer carries an undeclared-but-broken build hook.
  - **Covered by:** R1, R2

- F3. **Measure-first gate decides whether a twin is re-introduced**
  - **Trigger:** R3's benchmark completes on the corpus.
  - **Actors:** A1, A2
  - **Steps:** (1) A1 reads the measured routing-stage wall time and per-path A* latency for the pure-Python active router. (2) A1 compares against the threshold in R4. (3) If below threshold → Approach A is the final state; the regression benchmark (R5) locks the pure-Python performance. (4) If at/above threshold → Approach B (codegen) or C (hand-maintained) is selected in planning; the parity test (R6) is implemented alongside the twin.
  - **Outcome:** A documented decision, recorded in `docs/`, with the measured numbers attached. The decision is reversible: the parity test (R6) makes a future deletion safe.
  - **Covered by:** R3, R4, R5, R6

- F4. **Developer edits the A* implementation when a twin exists**
  - **Trigger:** A1 edits `router_v6/astar_pathfinding.py` (Approach B/C only).
  - **Actors:** A1, A2
  - **Steps:** (1) A1 edits the `.py`. (2) Under Approach B, the `.pyx` is regenerated from the annotated `.py` at build time; under Approach C, A1 hand-edits the `.pyx` in parallel. (3) A2 runs CI: the parity test (R6) runs both implementations against the golden routing fixtures and asserts byte-identical paths. (4) Any divergence fails CI with a named diff.
  - **Outcome:** A change to the A* algorithm either produces identical routes from both implementations or fails CI — never silently diverges based on a build flag.
  - **Covered by:** R6, R7

---

## Requirements

**Phase 1 — Finalize the deletion (unconditional)**

- R1. `packages/temper-placer/setup.py` no longer references `astar_core.pyx`, `temper_placer.routing.astar.astar_core`, or `cythonize`. If no other Cython extension exists in the package, the file is deleted and the `[build-system]` table in `pyproject.toml` drops `Cython>=3.0.0` from `requires`. A build that cannot find a `.pyx` it claims to compile is a build bug; this requirement makes the build honest about what it ships.
- R2. `packages/temper-placer/temper_placer/deterministic/stages/multilayer_astar.py` no longer attempts `from temper_placer.routing.astar import find_path`. The `TEMPER_USE_CYTHON_ASTAR` env-var branch (lines ~261-301) is removed; the Python implementation is the sole path. `docs/reports/PERFORMANCE_OPTIMIZATION_SESSION.md` and `router-experiments/reports/exp_24_piantor_2026-01-10.md` carry a dated note that the Cython twin was removed in commit `3314d94a` (Jan 17 2026) and that any re-introduction is gated on the R3 measurement; the historical 40× figure is explicitly labeled as non-reproducible against the current router.

**Phase 2 — Measure-first gate (unconditional)**

- R3. A benchmark script measures the active pure-Python `router_v6/astar_pathfinding.py` on the existing multi-board corpus defined in `packages/temper-placer/temper_placer/router_v6/test_boards.py` (Piantor_Right, LibreSolar_BMS, RP2040_DesignGuide, BitAxe_Ultra; the Temper entry whose `path` is hardcoded to an absolute user path is either relativized or excluded). The script records, per board: total routing-stage wall time, per-path A* latency (mean/median/p95), path count, and failure count. Output is machine-readable JSON committed under `packages/temper-placer/tests/benchmarks/`. The benchmark reuses the runner pattern in `router_v6/benchmark.py` rather than introducing a new harness.
- R4. A decision threshold is recorded in `docs/`: re-introduce a Cython twin only if the measured per-path p95 A* latency on the corpus is **≥ 5×** the hypothetical Cython target, OR the measured end-to-end routing-stage wall time is **≥ 2×** what a Cython twin would deliver. The 2× single-number threshold from ideation is rejected as too low for A* in a PCB router: the historical evidence (`PERFORMANCE_OPTIMIZATION_SESSION.md`) was 40× per-path, and a build step that delivers <5× per-path speedup does not justify the ongoing drift risk and build complexity. The two-number threshold (per-path AND end-to-end) prevents the case where per-path speedup is large but the routing stage is not the bottleneck.

**Phase 3 — Lock the pure-Python performance (unconditional)**

- R5. A CI performance-regression gate runs the R3 benchmark on every push that touches `router_v6/astar_pathfinding.py` or its direct imports (`occupancy_grid.py`, `channel_mapping.py`, `adaptive_grid.py`). The gate compares against the committed baseline JSON; a regression beyond a recorded tolerance (default 15% on per-path p95) fails CI with a named diff. This gate exists whether or not a twin is re-introduced: it makes the pure-Python performance a tracked, non-regressing property of the codebase, and it provides the baseline against which any future Cython twin is measured.

**Phase 4 — Parity test (conditional: only if R4 threshold is met and a twin is re-introduced)**

- R6. A parity test runs both the pure-Python `router_v6/astar_pathfinding.py` and the Cython twin against a set of golden routing fixtures, asserting **byte-identical path output** for each net (same coordinate sequence, same layer assignments, same via positions). The fixtures are drawn from the R3 corpus — at minimum the four external boards — and committed alongside the test. The test name identifies the diverging net, the diverging coordinate index, and the two implementations' values. The parity test is the artifact that makes any future deletion of the twin safe: it proves the two implementations agree today, so deleting the twin tomorrow cannot change routing behavior.
- R7. The Cython twin is **generated from type-annotated `.py`** (Approach B), not hand-maintained as a separate `.pyx` (Approach C). The `.py` carries Cython type annotations (`cython.int`, `cython.double`, typed memoryviews) guarded by `if cython.compiled` so the file remains importable as pure Python. The build step lives in `pyproject.toml` as a hatchling build hook (or `setup.py` if hatchling does not support the required cythonize step), runs at `pip install` time, and is exercised in CI on every push that touches the annotated `.py`. Hand-maintained `.pyx` is rejected as the default because it reintroduces the exact drift risk this initiative exists to eliminate.

---

## Approaches Considered

- **Approach A — Finalize deletion.** Remove all dangling references (R1, R2); do not re-introduce a Cython twin. The pure-Python `router_v6/astar_pathfinding.py` is the sole implementation; R5 locks its performance.
  - **Pros:** Zero build complexity; zero drift risk; removes a currently-broken build hook and a runtime exception-and-recover on the legacy hot path; matches the direction already taken in `3314d94a`.
  - **Cons:** Forfeits any speedup the historical 40× figure implies. If the active router is bottlenecked on A*, this leaves the bottleneck in place.
  - **When chosen:** When R3's measurement falls below the R4 threshold.

- **Approach B — Generate `.pyx` from type-annotated `.py` (codegen).** Add Cython type annotations to `router_v6/astar_pathfinding.py` behind `if cython.compiled`, generate the `.pyx` at build time, ship both. R6 parity test guards drift.
  - **Pros:** Single source of truth (the `.py`); the `.pyx` cannot drift because it is generated; the `.py` remains runnable as pure Python for debugging; the parity test makes future deletion safe.
  - **Cons:** Build step adds complexity (hatchling hook or `setup.py`); the annotated `.py` is less readable than pure Python; the codegen tooling must be maintained.
  - **When chosen:** Default if R4 threshold is met.

- **Approach C — Hand-maintained `.pyx` twin with parity test.** Re-create `astar_core.pyx` as a separate hand-maintained file mirroring the `.py`; R6 parity test guards drift.
  - **Pros:** Maximum per-file performance (the `.pyx` can use C-level constructs the annotated `.py` cannot); matches the pre-Jan-17 architecture.
  - **Cons:** Reintroduces the exact two-hand-maintained-copies drift risk this initiative exists to eliminate; the parity test catches drift at CI time but does not prevent the double-edit cost; requires the benchmark corpus to be worth the maintenance.
  - **When chosen:** Only if Approach B is measured to be insufficient (e.g. codegen delivers <50% of the hand-maintained speedup) AND the R4 threshold is met with margin.

**Default recommendation:** Phase 1 + Phase 2 + Phase 3 land unconditionally. Approach A is the default outcome; Approach B is triggered only by the R4 threshold. Approach C is a planning-time escalation if B is insufficient. The parity test (R6) is implemented only when B or C is triggered, but its design is fixed now so the gate is unambiguous.

---

## Success Criteria

- `pip install -e packages/temper-placer` succeeds without invoking `cythonize` and without referencing any `.pyx` file. The build is honest about what it ships.
- `grep -r "routing.astar\|astar_core\|cythonize" packages/temper-placer/temper_placer/ packages/temper-placer/setup.py packages/temper-placer/pyproject.toml` returns zero matches outside the dated historical note in `docs/`.
- A run of the R3 benchmark on the four-board corpus produces a committed JSON baseline; a subsequent run that introduces a 15% per-path p95 regression on `router_v6/astar_pathfinding.py` fails CI.
- A reader of `docs/reports/PERFORMANCE_OPTIMIZATION_SESSION.md` knows within the first section that the Cython twin it describes was removed in Jan 2026 and that the current router is pure Python — they do not waste time looking for `astar_core.pyx`.
- If a twin is re-introduced: the R6 parity test passes on all golden fixtures; deleting the twin (returning to Approach A) is a one-changeset operation that the parity test proves is behavior-preserving.

---

## Scope Boundaries

- **Re-introducing the pre-Jan-17 `routing/astar/` package verbatim** — out of scope. The deleted twin targeted the legacy `deterministic/stages/multilayer_astar.py` algorithm, not the active `router_v6/astar_pathfinding.py`. Resurrecting it would couple a dead router to a re-introduced twin. Any re-introduction targets the active router.
- **Migrating the legacy `deterministic/stages/` router to `router_v6/`** — out of scope. The legacy router is still imported by `pipeline/mvp3_runner.py` and diagnostic scripts; its migration is a separate initiative. This initiative only removes the dead Cython branch from `multilayer_astar.py` (R2).
- **Hardware-specific SIMD or C-extension optimization beyond Cython** — out of scope. If R3 shows A* is bottlenecked and Cython is insufficient, the escalation is Approach C, not a hand-written C extension.
- **Property-based route optimality testing** — out of scope. R6 asserts byte-identical output between implementations, not route optimality. Optimality is a separate concern owned by the router's own tests.
- **Repairing the hardcoded `/Users/bennet/...` path in `test_boards.py`** — in scope only to the extent it blocks R3 (the Temper board entry). R3 either relativizes the path or excludes the board; the broader path-hygiene cleanup is deferred.

---

## Key Decisions

- **The ideation premise is corrected by verification.** The `.pyx` twin does not exist on `main`; the drift risk today is dangling references to a deleted file, not two hand-maintained copies. Phase 1 (R1, R2) finalizes the deletion unconditionally — this is not a measure-then-decide outcome, it is a bug fix for an incomplete cleanup.
- **The measure-first gate measures the active router, not the deleted twin.** The historical 40× figure was measured against `routing/astar/astar_core.pyx` driving `deterministic/stages/multilayer_astar.py`. It is not evidence about `router_v6/astar_pathfinding.py`. R3 re-measures from scratch on the active router; the historical figure is treated as an upper bound, not a prediction.
- **The 2× threshold is rejected; a two-number threshold (5× per-path OR 2× end-to-end) is adopted.** A 2× single-number threshold under-weights the build-complexity cost of a Cython twin and ignores the historical reality (40×). The two-number form also guards against the case where per-path speedup is large but the routing stage is not the wall-time bottleneck.
- **Codegen (Approach B) is the default if the threshold is met; hand-maintained `.pyx` (Approach C) is escalation-only.** The ideation floated both; verification confirms the drift risk of two hand-maintained copies is the exact failure mode this initiative exists to prevent. Codegen from a single annotated `.py` is the only re-introduction path that does not reintroduce the disease while treating the symptom.
- **The parity test is conditional on re-introduction, not unconditional.** The ideation proposed adding it "either way." Verification changes this: with no twin, there is nothing to test parity against. The regression gate (R5) plays the drift-prevention role when no twin exists. R6 is specified now so the gate is unambiguous if a twin is introduced.

---

## Dependencies / Assumptions

- **The benchmark corpus is already available.** `packages/temper-placer/temper_placer/router_v6/test_boards.py` defines four external boards (Piantor, LibreSolar BMS, RP2040, BitAxe) with `.kicad_pcb` fixtures under `packages/temper-placer/tests/fixtures/external/.cache/`. R3 reuses this; no new corpus is built.
- **The benchmark harness pattern is already established.** `router_v6/benchmark.py` demonstrates the per-board runner + structured-report pattern. R3 extends it with per-path A* latency capture rather than introducing a new harness.
- **The deleted `.pyx` is not recoverable from `main` but is recoverable from git history.** Commit `3314d94a`'s tree contains `astar_core.{pyx,pxd}` (707 lines). If Approach B/C is triggered, the historical implementation is a reference, not a starting point — it targeted a different algorithm.
- **The legacy `deterministic/stages/multilayer_astar.py` is still imported but is not the active router.** `pipeline/mvp3_runner.py` and several diagnostic scripts import it. R2 removes its dead Cython branch; it does not delete the file. Confirm during planning that no production path still depends on the Cython branch's behavior (the branch's behavior is "always raise ImportError and fall through to Python," so the answer is structurally yes — but confirm).
- **The hardcoded `/Users/bennet/...` path in `test_boards.py:54` is a pre-existing bug.** R3 either relativizes it or excludes the Temper board from the corpus. Assumption: excluding it does not invalidate the measurement because the four external boards span a representative range of board complexity (consumer keyboard, BMS, MCU design guide, mining board).
- **Hatchling supports a cythonize build hook, or `setup.py` remains a supported escape hatch.** R7 assumes the build step can be wired into the existing build system. If hatchling does not support it, `setup.py` (already present) is the fallback. This is unverified for the current hatchling version — confirm during planning.

---

## Open Questions

### Resolve Before Planning

- **[Affects R3][Technical]** Does `router_v6/benchmark.py` already capture per-path A* latency, or only per-board aggregates? R3 needs per-path p95; if the existing harness only records aggregates, the harness extension is a planning-time work item.
- **[Affects R4][Decision]** Is the 5×-per-path / 2×-end-to-end threshold acceptable to the project owner? The ideation defaulted to 2×; this document raises it. Owner sign-off is required before R3 runs, because the threshold determines whether Phase 4 is ever triggered.
- **[Affects R1][Technical]** Are there other consumers of `Cython>=3.0.0` in `packages/temper-placer/` besides `setup.py`? If yes, R1 drops the dependency only from the build hook, not from `[project.dependencies]`. Confirm by grep during planning.

### Deferred to Planning

- **[Affects R7][Technical]** Does hatchling's build-hook API support invoking `cythonize` at build time, or is `setup.py` the only path? If `setup.py`, confirm it composes with the hatchling backend already declared in `[build-system]`.
- **[Affects R6][Technical]** What is the exact byte-identical assertion surface for a routed path? `RoutePath.coordinates` (list of `(x, y)` tuples) and `RoutePath.layer_name` are obvious; `RoutePath3D.segments` (with per-segment layer) and `via_positions` are the multi-layer surface. Confirm which dataclass the parity test asserts against.
- **[Affects R3][Needs research]** Is the absolute path in `test_boards.py:54` (`/Users/bennet/Desktop/temper/packages/temper-placer/temper_router_v6_fine.kicad_pcb`) pointing to a tracked file? If yes, relativize; if the file is not under version control, exclude the Temper board from the R3 corpus.
