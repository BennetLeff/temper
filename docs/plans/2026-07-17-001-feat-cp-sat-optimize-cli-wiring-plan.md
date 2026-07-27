---
title: "feat: Wire CP-SAT solver into temper-placer optimize --no-loop"
type: feat
status: completed
date: 2026-07-17
origin: docs/brainstorms/2026-07-17-cp-sat-optimize-cli-wiring-requirements.md
swept: 2026-07-25
swept_basis: "already declared"
---

# Wire CP-SAT Solver into temper-placer optimize --no-loop

## Summary

Wire `solve_placement()` into the `--no-loop` path of `temper-placer optimize` by replacing the dead `console.print` stub with a real solver call, PCB position write, and fail-closed error handling. The `--loop` path is unchanged. A single integration test proves the CLI actually calls the solver.

---

## Problem Frame

`temper-placer optimize`'s CP-SAT branch prints "Full CP-SAT pipeline integration is in progress" and exits without calling the solver. The `--loop` path (default) is wired through `PlaceRouteLoop`, but `--no-loop` is a silent no-op: it prints the banner, skips the `if loop:` block, and reaches `sys.exit(0)`. The solver itself (`solve_placement()` in `encoder.py`) is complete and tested (34 test references). The gap is four lines in `cli/__init__.py:391-396`.

Per `docs/solutions/logic-errors/cp-sat-optimize-cli-non-functional-stub-2026-07-17.md`, this is the third confirmed instance of JAX-retirement-era code left unexercised.

---

## Requirements

- R1. When `--no-loop` is set, `optimize()` must parse the input PCB, load constraints, call `solve_placement()`, and produce a result.
- R2. Reuse existing `parse_kicad_pcb` and `load_constraints` from the loop path. The `--no-loop` path passes netlist, board, and constraints to `solve_placement()` — zones and loop components are loop-path constructs not needed for bare placement.
- R3. On feasible placement, write the input PCB with updated component positions and rotations to `--output`.
- R4. On infeasible, write UNSAT core to stderr, exit non-zero, and write no output file.
- R5. Remove the stale "Full CP-SAT pipeline integration is in progress" banner and the dead "Use `temper pipeline`" suggestion.

**Origin actors:** A1 (human operator), A2 (automation / CI)
**Origin acceptance examples:** AE1 (feasible placement produces output), AE2 (infeasible exits non-zero), AE3 (stale banner removed)

---

## Scope Boundaries

- Fixing `gate_unmeasured` failures in the loop's routing path — separate problem
- Adding routing or gating support to `--no-loop` — placement-only
- Updating CP-SAT baseline extraction tooling or `temper-placer regression` baselines
- Refactoring `PlaceRouteLoop` internals — the loop path is not being changed

---

## Context & Research

### Relevant Code and Patterns

- **Solver entry point:** `solve_placement()` in `packages/temper-placer/src/temper_placer/placer/cp_sat/encoder.py:936` — returns `CpSatPlacementResult` with `positions`, `rotations`, `status`, `unsat_core`
- **PCB parsing:** `parse_kicad_pcb` in `packages/temper-placer/src/temper_placer/io/kicad_parser.py`, returns `ParseResult` with `.netlist` and `.board`
- **Constraint loading:** `load_constraints` in `packages/temper-placer/src/temper_placer/io/config_loader.py:831`, returns `PlacementConstraints` with `.pcl_constraints`
- **PCB writing:** `write_placements_to_pcb` in `packages/temper-placer/src/temper_placer/io/kicad_writer.py:77` — uses kiutils to update `(at x y rotation)` in footprints
- **UNSAT surfacing:** `_maybe_surface_unsat()` in `packages/temper-placer/src/temper_placer/cli/__init__.py:45` — renders Rich Panel, optionally writes JSON
- **CLI patterns:** Lazy imports inside command body, `click.ClickException` for user-facing errors, `sys.exit(n)` for explicit exits, `from ._io import console` for Rich output
- **Test patterns:** `click.testing.CliRunner`, `mock.patch("temper_placer.placer.cp_sat.encoder.solve_placement")`, fixtures in `tests/fixtures/` (minimal_board.kicad_pcb, constraints_minimal.yaml)

### Institutional Learnings

- **Third JAX-retirement stub** (`docs/solutions/logic-errors/cp-sat-optimize-cli-non-functional-stub-2026-07-17.md`): root cause doc for the exact bug being fixed. Prevention rules: (1) unfinished CLI paths must exit non-zero, not silently; (2) fallback messages must point at real commands.
- **Silent guard condition pattern** (`docs/solutions/architecture-patterns/silent-guard-condition-infrastructure-failure-pattern-2026-07-02.md`): integration tests proving activation are required — unit tests on solver modules are insufficient.
- **Feasibility-first paradigm** (`docs/solutions/architecture-patterns/cp-sat-feasibility-first-paradigm-2026-07-03.md`): `--no-loop` should call feasibility-only solve (no wirelength objective) for ~0.1s baseline. Wirelength polish is a separate follow-up.

---

## Key Technical Decisions

- **Feasibility-first, no objective for `--no-loop`.** `solve_placement()` is called with hard constraints only — no wirelength objective. This matches the feasibility-first paradigm (~0.1s solve) and avoids the O(n²) timeout on objective-heavy boards. Wirelength optimization is deferred to a separate follow-up.
- **PCB writing via `write_placements_to_pcb` (kiutils), not text transformation.** Verified 2026-07-17: the loop path (`loop.py`) does not actually call `export_placements()`/`write_placements_to_pcb` itself — it uses its own `route_pcb`/`_build_minimal_pcb` mechanism to feed the router, a different concern from writing the CLI's `--output` file. `export_placements()` (`kicad_writer.py:331`) is real and does wrap `write_placements_to_pcb`, and the function is exercised in production via `io/placement_exporter.py` (a separate, JAX-era caller) — the underlying writer is sound and the pattern to follow, just not literally "already used by the loop path." `CpSatPlacementResult.positions` are converted to `PlacementUpdate` dicts with rotation = `rotations[ref] * 90.0`.
- **`--no-loop` passes netlist + board + constraints only.** Zones, zone components, and loop components are loop-path constructs that gate routed outputs and are not needed for bare placement. Omitting them keeps the `--no-loop` path simpler and avoids coupling to routing infrastructure.

---

## Open Questions

### Deferred to Implementation

- **`PlacementUpdate` coordinate conversion — resolved by static analysis 2026-07-17, no longer open.** `solve_placement()` extracts positions as `solver.Value(cv.x_center) / units_per_mm` (`encoder.py:1109-1111`) — the solver's own internal variable is literally named `x_center`/`y_center`, confirming these are component-center coordinates, not footprint-origin. `write_placements_to_pcb`'s docstring (`kicad_writer.py:97-98`) confirms it treats positions as footprint-origin *unless* `components` is passed, in which case it applies the center-offset correction. Conclusion: **always pass `components=netlist.components`** when calling `write_placements_to_pcb` from the `--no-loop` path — this is not a "verify at runtime" judgment call, it's required by the solver's own coordinate convention.
- **Timeout value for `--no-loop`.** `solve_placement()` defaults to 1000ms. The implementer should verify this is adequate for the production board and, if not, either increase the default or add a `--cp-sat-timeout` CLI option. The 1000ms default is presumed adequate per the feasibility-first paradigm.

---

## Implementation Units

### U1. Wire `solve_placement()` into the `--no-loop` path

**Goal:** Replace the dead `console.print` stub at lines 391-396 with a real solver call, reusing the same parsing and constraint loading the loop path uses.

**Requirements:** R1, R2

**Dependencies:** None

**Files:**
- Modify: `packages/temper-placer/src/temper_placer/cli/__init__.py`

**Approach:**
- After the current stub lines (391-396), add an `else:` block that runs when `--no-loop` is set
- Inside the `else:` block: parse PCB via `parse_kicad_pcb`, load constraints via `load_constraints`, call `solve_placement()` with netlist + board + pcl_constraints
- Use the existing lazy import pattern (same as the loop path at lines 402-407)
- Remove the stale banner text entirely; replace with a real progress line: "Running CP-SAT solver (--no-loop)..."
- Remove the dead "Use `temper pipeline`" suggestion

**Patterns to follow:**
- Lazy imports inside function body: `packages/temper-placer/src/temper_placer/cli/__init__.py:402-407`
- `click.ClickException` for user-facing errors: `packages/temper-placer/src/temper_placer/cli/__init__.py:583-585`

**Test scenarios:**
- Happy path: `optimize --no-loop` against a minimal board with valid constraints → `solve_placement()` is called, exit code 0
- Happy path: `optimize --no-loop` with `--seed 42` propagates seed to `solve_placement(seed=42)`
- Error path: PCB file does not exist → `click.ClickException` with clear message
- Error path: Config file does not exist → `click.ClickException` with clear message
- Integration: solver returns `status="infeasible"` → exit code non-zero, UNSAT core on stderr (mocked)

**Verification:**
- `temper-placer optimize --no-loop <board> -c <config> -o <output>` parses the PCB and calls `solve_placement()` (verified via mock assertion)
- The stale "Full CP-SAT pipeline integration is in progress" string no longer appears in CLI output
- The dead "Use `temper pipeline`" string no longer appears in CLI output

---

### U2. Write solver positions to the output PCB on success

**Goal:** Convert `CpSatPlacementResult.positions` and `.rotations` to `PlacementUpdate` dicts and write them to `--output` via `write_placements_to_pcb`.

**Requirements:** R3

**Dependencies:** U1

**Files:**
- Modify: `packages/temper-placer/src/temper_placer/cli/__init__.py`

**Approach:**
- After `solve_placement()` returns a feasible result, build a `PlacementUpdate` dict for each component
- Map `result.positions[ref]` → `(x, y)`, `result.rotations[ref] * 90` → `rotation`
- Call `write_placements_to_pcb(template_pcb=input_pcb, output_pcb=output, placements=placements, preserve_unmatched=True)`
- Log the number of components placed and output path via Rich console

**Patterns to follow:**
- `write_placements_to_pcb` signature: `packages/temper-placer/src/temper_placer/io/kicad_writer.py:77`
- `PlacementUpdate` dataclass: `packages/temper-placer/src/temper_placer/io/kicad_writer.py:59`
- Console output: `console.print(f"  [green]✓[/] ...")` pattern from loop path

**Test scenarios:**
- Happy path: solver returns `status="optimal"` with 4 positions → output PCB exists, `(at ...)` lines match solved coordinates
- Edge case: solver returns `status="feasible"` with subset of components placed → `preserve_unmatched=True` keeps unplaced footprints in output
- Edge case: solver returns empty positions (unknown status) → appropriate error handling (not a silent no-op)

**Verification:**
- On a feasible solver result, `--output` file exists and contains updated `(at x y rotation)` s-expressions for solved components
- Unplaced components' footprints are preserved in the output

---

### U3. Fail-closed error handling for infeasible and error states

**Goal:** Handle all failure modes — infeasible solve, model_invalid, and unexpected exceptions — with fail-closed behavior: exit non-zero, no output file written, diagnostics to stderr.

**Requirements:** R4

**Dependencies:** U1, U2

**Files:**
- Modify: `packages/temper-placer/src/temper_placer/cli/__init__.py`

**Approach:**
- Check `result.status` after `solve_placement()` returns
- If `infeasible` or `model_invalid`: call existing `_maybe_surface_unsat(result, unsat_report)` then `sys.exit(1)`
- If `result.status` is neither feasible nor infeasible (unexpected status): log warning, exit non-zero
- Wrap the entire `--no-loop` block in try/except matching the loop path's pattern (re-raise `click.ClickException`, wrap others)
- Ensure `sys.exit(0)` at line 591 is only reached from the loop path's success branch — restructure so the `--no-loop` path handles its own exit

**Patterns to follow:**
- `_maybe_surface_unsat()`: `packages/temper-placer/src/temper_placer/cli/__init__.py:45`
- Exception handling pattern: `packages/temper-placer/src/temper_placer/cli/__init__.py:586-589`

**Test scenarios:**
- Error path: solver returns `status="infeasible"` → exit code 1, UNSAT core in output, no `--output` file created
- Error path: solver returns `status="model_invalid"` → exit code 1, diagnostic on stderr
- Error path: solver call raises `RuntimeError` → `click.ClickException` with wrapped message
- Integration: `--unsat-report /tmp/report.json` writes JSON when infeasible (covers A2 CI automation actor)

**Verification:**
- Infeasible solve exits non-zero and does not create a dangling output file
- UNSAT core appears in `result.output` (stderr) as a Rich Panel or text
- `--unsat-report <path>` produces a valid JSON file

---

### U4. CLI integration tests for `--no-loop`

**Goal:** Add tests that prove the `--no-loop` path correctly calls the solver, writes output on success, and exits non-zero on infeasible. This closes the "integration tests proving connectivity" gap documented in the unwired-infrastructure learnings.

**Requirements:** R1, R3, R4, R5 (all verifiable through CLI invocation)

**Dependencies:** U1, U2, U3

**Files:**
- Create: `packages/temper-placer/tests/cli/test_optimize_no_loop.py`

**Approach:**
- Use `click.testing.CliRunner` and `tmp_path` fixture
- Mock `solve_placement` at `temper_placer.placer.cp_sat.encoder.solve_placement` (confirmed mockable via the lazy-import pattern `loop.py` uses at line 197-198)
- Use existing test fixtures: `tests/fixtures/minimal_board.kicad_pcb`, `tests/fixtures/constraints_minimal.yaml`
- Test both success and infeasible paths, verifying exit codes, output file presence, and string presence/absence

**Patterns to follow:**
- CLI test with mock: `packages/temper-placer/tests/cli/test_cp_sat_flag.py`
- UNSAT report test: `packages/temper-placer/tests/cli/test_unsat_report.py`
- `CliRunner` usage: NOT `tests/cli/test_optimize.py` — that file doesn't exist.
  Its predecessor (`test_optimize_command.py`) was deleted in commit
  `1278724f` (JAX-dependent test cleanup). Use the `CliRunner` pattern from
  `test_cp_sat_flag.py`/`test_unsat_report.py` instead — both already
  exercise `optimize`.

**Test scenarios:**
- Happy path: mock `solve_placement` returns `CpSatPlacementResult(status="optimal", positions={"R1": (10.0, 20.0)}, rotations={"R1": 0})` → exit 0, output file exists
- Happy path: verify stale banner text "Full CP-SAT pipeline integration is in progress" is NOT in `result.output` (covers AE3)
- Error path: mock returns `status="infeasible"` with `unsat_core=[{"name": "loop_area_hb", "because": ""}]` → exit 1, no output file, UNSAT core text in output
- Error path: mock returns `status="infeasible"` with `--unsat-report /tmp/report.json` → JSON file written
- Integration: mock raises `RuntimeError("OR-Tools solver timed out")` → `click.ClickException`, exit non-zero
- Covers AE1: feasible solve with --no-loop produces a placed output file
- Covers AE2: infeasible solve exits non-zero with UNSAT core, no output file

**Verification:**
- `uv run pytest packages/temper-placer/tests/cli/test_optimize_no_loop.py -v` passes all scenarios
- Integration test proves `solve_placement` was called (mock assertion on call count or arguments)
- No test touches real CP-SAT solver — all solver calls are mocked

---

## System-Wide Impact

- **Interaction graph:** Only the `optimize` CLI command in `cli/__init__.py` is modified. No changes to `PlaceRouteLoop`, `solve_placement`, or any solver module.
- **Error propagation:** Follows existing `click.ClickException` → exit 1 pattern. New `sys.exit(1)` for infeasible matches the existing `sys.exit(1)` pattern for deprecated paths (line 362).
- **State lifecycle risks:** None — the `--no-loop` path is stateless (parse → solve → write → exit). No shared state with the loop path.
- **API surface parity:** `--no-loop` accepts the same `--seed`, `--unsat-report` flags as `--loop`. New timeout flag is deferred to implementation.
- **Integration coverage:** U4 integration tests cover the full `--no-loop` flow end-to-end with mocked solver.
- **Unchanged invariants:** `--loop` (default) path is not modified. All existing CLI behavior, exit codes, and output formats for `--loop` are preserved. The `sys.exit(0)` at line 591 must remain reachable only from the `--loop` success branch.

---

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| Solver returns positions in a coordinate system mismatch with `write_placements_to_pcb`'s footprint-origin expectation | Pass `netlist.components` for center-offset correction; verify with a real board before merging |
| `--no-loop` path accidentally exits 0 on infeasible due to shared `sys.exit(0)` at line 591 | U3 explicitly restructures exit handling so `--no-loop` owns its exit paths |
| Mock patch target for `solve_placement` changes if import path is refactored | Confirmed: `loop.py` already patches at `temper_placer.placer.cp_sat.encoder.solve_placement` — use same target |
| Stale layout from removed banner lines causes imports or control flow to shift | Minimal diff: replace the 4 print lines with the else-block, keeping surrounding code structurally intact |

---

## Sources & References

- **Origin document:** [docs/brainstorms/2026-07-17-cp-sat-optimize-cli-wiring-requirements.md](../brainstorms/2026-07-17-cp-sat-optimize-cli-wiring-requirements.md)
- **Bug root cause:** [docs/solutions/logic-errors/cp-sat-optimize-cli-non-functional-stub-2026-07-17.md](../solutions/logic-errors/cp-sat-optimize-cli-non-functional-stub-2026-07-17.md)
- **Unwired infrastructure pattern:** [docs/solutions/architecture-patterns/silent-guard-condition-infrastructure-failure-pattern-2026-07-02.md](../solutions/architecture-patterns/silent-guard-condition-infrastructure-failure-pattern-2026-07-02.md)
- **Feasibility-first paradigm:** [docs/solutions/architecture-patterns/cp-sat-feasibility-first-paradigm-2026-07-03.md](../solutions/architecture-patterns/cp-sat-feasibility-first-paradigm-2026-07-03.md)
- Related code: `packages/temper-placer/src/temper_placer/cli/__init__.py:306-591`
- Related code: `packages/temper-placer/src/temper_placer/placer/cp_sat/encoder.py:936-1134`

## Shipped

**Merged in [PR #218](https://github.com/BennetLeff/temper/pull/218) on 2026-07-18.** The CP-SAT solver was wired into the `--no-loop` path of `temper-placer optimize`, replacing the dead `console.print` stub with a real solver call, PCB position write, fail-closed error handling, and a single integration test proving the CLI actually calls the solver. All 4 implementation units (U1-U4) shipped: U1 wired `solve_placement()`, U2 wrote solver positions to output PCB, U3 added fail-closed error handling, U4 added CLI integration tests in `test_optimize_no_loop.py`.
