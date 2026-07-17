---
date: 2026-07-17
topic: cp-sat-optimize-cli-wiring
---

# CP-SAT Optimize CLI Wiring

## Summary

Wire `solve_placement()` into `temper-placer optimize` for the `--no-loop` path. Reuse the PCB parsing and constraint loading the loop path already does. On success, update component positions in the input PCB and write to `--output`. On infeasible, exit non-zero with UNSAT core to stderr.

---

## Problem Frame

`temper-placer optimize`'s CP-SAT branch (`cli/__init__.py:391-396`) prints a stale "Full CP-SAT pipeline integration is in progress" banner and exits without calling the solver. With `--loop` (the default), `PlaceRouteLoop.run()` does call `solve_placement()` internally — the loop path is wired. But with `--no-loop`, no solver call exists: the banner prints, the `if loop:` block is skipped, and `sys.exit(0)` runs. Zero placement work happens.

The solver itself (`encoder.py:solve_placement()`) is complete — it builds a CP-SAT model, encodes PCL constraints, solves, and returns positions with status metadata. The gap is purely CLI wiring: one call between parsing and output for the bare-placement case, plus removing the misleading banner text.

The pre-existing compound doc `docs/solutions/logic-errors/cp-sat-optimize-cli-non-functional-stub-2026-07-17.md` root-causes this to four `console.print` lines that drop through to nothing when the loop block is skipped. The `temper pipeline` fallback the banner suggests does not exist as a CLI command.

---

## Actors

- A1. **Human operator**: Runs `temper-placer optimize --no-loop <board> -c <config> -o <output>` to get a quick CP-SAT placement without routing
- A2. **Automation / CI**: Calls `temper-placer optimize --no-loop` programmatically, checks exit code and output file presence to determine success

---

## Requirements

**Placement**
- R1. When `--no-loop` is set, `optimize()` must parse the input PCB, load constraints, call `solve_placement()`, and produce a result — none of which the current `--no-loop` path does.
- R2. Reuse the existing PCB parsing (`parse_kicad_pcb`) and constraint loading (`load_constraints`) logic the loop path already performs. Do not introduce a second parsing path. The `--no-loop` path passes netlist, board, and constraints to `solve_placement()` — zones and loop components are loop-path constructs that gate routed outputs and are not needed for bare placement.

**Output**
- R3. On feasible placement (`status` is `optimal` or `feasible`), write the input PCB with updated component positions and rotations to `--output`. Preserve all existing PCB content (footprints, nets, pads, zones) — only component `(at ...)` coordinates and rotation change.
- R4. On infeasible (`status` is `infeasible` or `model_invalid`), write the UNSAT core to stderr listing the conflicting constraint labels, exit non-zero, and write no output file.

**Honest status reporting**
- R5. Remove the stale "Full CP-SAT pipeline integration is in progress" banner and the dead "Use `temper pipeline`" suggestion. Replace with real progress output reflecting what the CLI is actually doing (parsing, solving, writing) and actual solve status.

---

## Acceptance Examples

- AE1. **Covers R1, R3.** Given `pcb/temper.kicad_pcb` and a valid production config, when `temper-placer optimize --no-loop pcb/temper.kicad_pcb -c configs/temper_production_config.yaml -o /tmp/placed.kicad_pcb`, the solver runs, places components, and `/tmp/placed.kicad_pcb` exists with updated `(at ...)` positions matching the solved coordinates.
- AE2. **Covers R4.** Given a board and config whose constraints make placement infeasible, when `temper-placer optimize --no-loop board.kicad_pcb -c infeasible_config.yaml -o /tmp/out.kicad_pcb`, the CLI exits non-zero, writes UNSAT core to stderr, and `/tmp/out.kicad_pcb` does not exist.
- AE3. **Covers R5.** When `temper-placer optimize` runs with `--no-loop`, the output must not contain the string "in progress" or the nonexistent command reference "temper pipeline".

---

## Success Criteria

- A bare `temper-placer optimize --no-loop` against the production board with a valid config produces a placed `.kicad_pcb` output file within the solver's default time limit (1000ms per `solve_placement()`)
- The UNSAT path fails closed: exit code non-zero, no dangling output file, UNSAT core on stderr
- The stale banner text is gone — the CLI output honestly reflects what the tool is doing and whether it succeeded

---

## Scope Boundaries

- Fixing `gate_unmeasured` failures in the loop's routing path — separate problem, routing gate integration
- Adding routing or gating support to `--no-loop` — placement-only
- Updating CP-SAT baseline extraction tooling or `temper-placer regression` baselines
- Refactoring `PlaceRouteLoop` internals — the loop path is not being changed

---

## Key Decisions

- **Fail-closed on infeasible, not best-effort partial placement.** A script checking exit code must not treat an INFEASIBLE run as success. No output file is written — callers verify via exit code and file presence.
- **Modify input PCB in-place for output, not emit JSON.** The output is a directly-usable KiCad PCB, matching the format the loop path produces when it converges. This avoids a second output format that tooling would need to convert.

---

## Dependencies / Assumptions

- `solve_placement()` in `encoder.py` works correctly when called with the parsed board and constraints from the CLI. This is assumed per the existing CP-SAT test suite (34 test references to `solve_placement`), but has not been exercised through the CLI entry point.
- `parse_kicad_pcb` and `load_constraints` produce compatible board and netlist objects for `solve_placement()` — verified by the loop path which passes those same objects to `PlaceRouteLoop.run()` → `_call_solver()` → `solve_placement()`.
- KiCad PCB position update uses `kiutils` or equivalent to modify `(at x y rotation)` without rewriting the entire file — format compatibility with the existing `kicad_writer.py`/`kicad_exporter.py` infrastructure is assumed.
