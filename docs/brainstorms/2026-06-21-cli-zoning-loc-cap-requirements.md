---
date: 2026-06-21
topic: cli-zoning-loc-cap
---

# CLI Zoning, 1000-Line LOC Cap, and entry_points Discovery

## Summary

A four-phase initiative that converts the Temper PCB toolchain from one where complexity concentrates in a handful of 2000–4000 line god-objects into one where no source file exceeds a fixed line cap, enforced by CI, with subcommands discovered via Python entry_points rather than hand-wired `add_command` calls. The phases are sequenced by risk: the LOC cap lands first as a non-blocking baseline allowlist (capturing the five current offenders), the CLI is decomposed next using a Louis Kahn served/servant zoning (subcommands are served → self-registering modules; argparse/IO/logging are servants → internal helper modules), then the two routing god-objects (`exact_geometry_router.py`, `astar_pathfinding.py`) and `sequential_routing.py` are decomposed in descending risk order, and finally `state_machine.c` is brought under the cap. The 3946-line `cli/__init__.py` becomes a ~50-line dispatcher.

---

## Problem Frame

Five files dominate the repo's complexity surface, each by a wide margin:

- `packages/temper-placer/temper_placer/cli/__init__.py` — 3946 lines (largest `.py` in the repo)
- `packages/temper-placer/temper_placer/router_v6/exact_geometry_router.py` — 3811 lines
- `packages/temper-placer/temper_placer/router_v6/astar_pathfinding.py` — 2289 lines
- `packages/temper-placer/temper_placer/deterministic/stages/sequential_routing.py` — 2046 lines
- `firmware/main/state_machine.c` — 1035 lines

These files share a common shape: each mixes several distinct responsibilities behind a single module boundary. The CLI file interleaves Click command definitions, argument-parsing helpers, rich console IO, progress reporting, summary printing, and signal handling in one 3946-line file. New subcommands are added by appending to the file; existing subcommands are found by scrolling. The two routing files mix geometry primitives, search state, scoring heuristics, and orchestration. There is no structural pressure to stop growth — a 4000-line file becomes a 5000-line file with the same review cost as a 200-line file, because nothing in CI measures it.

Two external ideas inform the decomposition. Louis Kahn's *served/servant* zoning separates spaces that house the building's purpose (served) from spaces that house its infrastructure (servant). Applied to the CLI: subcommands (`place`, `route`, `validate`, `dru`, `report`) are served — they are the product. Argument parsing, console IO, progress bars, and logging are servants — they exist to support the served spaces and should be factored into modules the served spaces import. The Python `entry_points` specification (already used by this repo for `[project.scripts]` → `temper-placer = "temper_placer.cli:main"`) provides a native discovery mechanism: a package can advertise a named group (`temper_placer.cli.subcommands`) listing its subcommand objects, and the dispatcher loads them at startup without any `add_command` call. This makes registration automatic and makes a lost registration a CI-detectable regression rather than a silent missing command.

The risk this initiative addresses is not a single bug class — it is the *rate* at which these files accumulate bugs. A 4000-line file with twelve interleaved responsibilities is harder to review, harder to test in isolation, and harder to reason about than twelve 300-line files each with one responsibility. The LOC cap is a forcing function: it makes the cost of growth visible to CI, so the next person who would add a 200-line subcommand to `cli/__init__.py` instead creates a new module.

---

## Actors

- A1. **Developer** — adds subcommands, edits routing logic, extends the firmware state machine. The primary source of the growth this initiative constrains.
- A2. **CI pipeline** — runs the LOC cap gate, ruff, pytest, and the CLI smoke tests on every push and pull request. The primary enforcement layer.
- A3. **Package installer** (`uv sync` / `pip install`) — reads `entry_points` metadata at install time and exposes the registered subcommand group to the dispatcher at runtime.

---

## Key Flows

- F1. **CI rejects an over-cap file**
  - **Trigger:** A1 pushes a change that pushes a `.py` or `.c` source file above 1000 lines, or adds a new file to the baseline allowlist.
  - **Actors:** A1, A2
  - **Steps:** (1) A1 pushes. (2) A2 runs the LOC gate job: `find packages firmware -name '*.py' -o -name '*.c' | xargs wc -l`, compares each file against 1000, and checks any over-cap file against `.loc-allowlist.txt`. (3) A file over cap and not on the allowlist fails the gate with a message naming the file, its line count, and the cap. (4) A file on the allowlist whose line count has *grown* since the baseline also fails the gate — the allowlist is a frozen ceiling, not a license to grow. (5) A new entry added to the allowlist fails the gate — the allowlist is append-only by ticketed PR, and a PR that both adds an entry and does not remove another is rejected.
  - **Outcome:** The push is blocked until A1 either splits the file or removes an allowlist entry by decomposing the file it covers.
  - **Covered by:** R1, R2, R3

- F2. **Developer adds a new CLI subcommand via entry_points**
  - **Trigger:** A1 wants a new `temper-placer frobnicate` subcommand.
  - **Actors:** A1, A2, A3
  - **Steps:** (1) A1 creates `packages/temper-placer/temper_placer/cli/frobnicate.py` containing a `@click.command("frobnicate")` decorated object. (2) A1 adds an entry to the `temper_placer.cli.subcommands` entry_points group in `packages/temper-placer/pyproject.toml`. (3) A1 runs `uv sync` (A3 picks up the new entry). (4) A1 runs `temper-placer frobnicate --help` — the dispatcher loads all entries in the group and the command appears. (5) A2 runs CI: the CLI smoke test asserts the command name appears in `temper-placer --help` output; the command-count test asserts the registered count matches the entry_points group count. (6) If A1 forgot the entry_points entry, the smoke test fails with a named message.
  - **Outcome:** The subcommand is registered with one `pyproject.toml` line and one module file — no edit to `cli/__init__.py`. Forgetting the entry produces a smoke-test failure, not a silently missing command.
  - **Covered by:** R6, R7, R8

- F3. **Developer decomposes the CLI god-object**
  - **Trigger:** Phase 2 begins — the CLI is the first decomposition target.
  - **Actors:** A1, A2
  - **Steps:** (1) A1 extracts servant code (argparse helpers, rich console setup, progress/summary printers, signal handlers) into `cli/_args.py`, `cli/_io.py`, `cli/_logging.py` — plain internal modules imported by the served modules. (2) A1 extracts each inlined subcommand from `__init__.py` into its own served module (`cli/place.py`, `cli/route.py`, etc.), keeping the existing `pipeline_commands.py` and `trace_commands.py` pattern. (3) A1 replaces each `@main.command(...)` in `__init__.py` with an entry_points registration. (4) `__init__.py` shrinks to a ~50-line dispatcher that loads the entry_points group and attaches each command to `main`. (5) A2 runs CI: the smoke tests verify every previously-available subcommand still appears in `--help`; the LOC gate verifies `__init__.py` is under cap and the new modules are each under cap. (6) A1 removes `cli/__init__.py` from `.loc-allowlist.txt`.
  - **Outcome:** `cli/__init__.py` is under 1000 lines with no behavior change observable to a user running `temper-placer`. The allowlist shrinks by one entry.
  - **Covered by:** R4, R5, R6, R7, R8, R9

- F4. **Developer decomposes a routing god-object**
  - **Trigger:** Phase 3 — `exact_geometry_router.py` (3811) is the next target after the CLI proves the pattern.
  - **Actors:** A1, A2
  - **Steps:** (1) A1 identifies the responsibility seams in the router (geometry primitives, search state, scoring, orchestration) — exact module names are a planning deliverable, not a requirement. (2) A1 extracts each seam into its own module under `router_v6/`, keeping public import paths stable via `__init__.py` re-exports so downstream callers are unaffected. (3) A2 runs CI: existing router tests must pass unchanged; the LOC gate verifies the new modules are each under cap. (4) A1 removes `exact_geometry_router.py` from `.loc-allowlist.txt`. (5) Repeat for `astar_pathfinding.py` and `sequential_routing.py` in descending risk order.
  - **Outcome:** Each routing file is under 1000 lines with no change to its public API. The allowlist shrinks by three more entries.
  - **Covered by:** R4, R9, R10

---

## Requirements

**Phase 1 — LOC cap as non-blocking gate with baseline allowlist**

- R1. **LOC cap gate.** A CI job (`.github/workflows/`) fails any push or pull request in which a source `.py` or `.c` file exceeds 1000 lines and is not listed in `.loc-allowlist.txt`. The job prints the offending file, its line count, and the cap value in the failure message.
- R2. **Baseline allowlist.** `.loc-allowlist.txt` is committed at the end of Phase 1 with exactly the five current offenders (`cli/__init__.py`, `exact_geometry_router.py`, `astar_pathfinding.py`, `sequential_routing.py`, `state_machine.c`), each annotated with a ticket ID tracking its decomposition. The allowlist is the *complete* set of over-cap files at commit time — verified by the gate itself.
- R3. **Allowlist is a frozen ceiling, not a license to grow.** The gate fails if (a) an allowlisted file's line count has increased beyond its baseline value recorded in the allowlist, (b) a new entry is added to the allowlist without a corresponding removal, or (c) a file is removed from the allowlist but is still over cap. The allowlist must shrink monotonically.
- R4. **Cap scope.** The cap applies to all `.py` files under `packages/**/src/` and `packages/**/temper_placer/` (source, not tests) and all `.c` files under `firmware/`. Tests, generated code, vendored code, and build artifacts are exempt. (Exact exemption list is an Assumption — see below.)

**Phase 2 — CLI served/servant decomposition + entry_points discovery**

- R5. **Servant extraction.** Argument-parsing helpers, rich console setup, progress/summary printing, and signal handling are extracted from `cli/__init__.py` into servant modules (`cli/_args.py`, `cli/_io.py`, `cli/_logging.py` — exact names are planning's call). These are plain internal modules imported by the served modules; they are not registered as subcommands.
- R6. **Served subcommand extraction.** Each subcommand currently inlined in `cli/__init__.py` (e.g. `mvp3-route` and the others between lines 129 and 3946) is extracted into its own served module. The existing `pipeline_commands.py` and `trace_commands.py` pattern is the reference — new served modules follow it.
- R7. **entry_points discovery.** `packages/temper-placer/pyproject.toml` declares an entry_points group named `temper_placer.cli.subcommands` listing each served subcommand object. The dispatcher in `cli/__init__.py` loads every entry in the group at startup and attaches it to `main` — no `main.add_command(...)` calls remain for served subcommands.
- R8. **Smoke tests for registration.** A CI test asserts that (a) `temper-placer --help` lists every subcommand name in the entry_points group, (b) each listed subcommand's `--help` exits zero, and (c) the count of registered commands equals the count of entry_points entries. This catches lost registrations.
- R9. **Dispatcher shrinks under cap.** After Phase 2, `cli/__init__.py` is removed from `.loc-allowlist.txt` and the gate confirms it is under 1000 lines.

**Phase 3 — Routing god-object decomposition**

- R10. **Router decomposition.** `exact_geometry_router.py`, `astar_pathfinding.py`, and `sequential_routing.py` are each decomposed into modules under 1000 lines, in that order (highest line count first, highest risk first). Public import paths are preserved via `__init__.py` re-exports so downstream callers require no changes. Each is removed from `.loc-allowlist.txt` as it lands.
- R11. **Router test stability.** The existing router test suite must pass unchanged after each decomposition step. If a test currently imports an internal symbol that moves, the test is updated to import from the re-export path — the public API surface does not shrink.

**Phase 4 — Firmware state machine under cap**

- R12. **`state_machine.c` decomposition.** The 1035-line firmware state machine is brought under 1000 lines by extracting helper functions or state handlers into separate `.c`/`.h` files under `firmware/main/`. The exact seam (per-state handlers vs. per-concern helpers) is a planning deliverable. Removed from `.loc-allowlist.txt` when complete.

---

## Success Criteria

- No source `.py` or `.c` file in the repo exceeds 1000 lines, and `.loc-allowlist.txt` is empty.
- A developer who adds a new CLI subcommand creates one module file and one `pyproject.toml` entry — and does not edit `cli/__init__.py`.
- A developer who forgets the `entry_points` entry sees a smoke-test failure naming the missing command — not a silently absent subcommand.
- `cli/__init__.py` is a ~50-line dispatcher readable in one screen.
- The LOC gate fails a push that grows any file past 1000 lines without a corresponding decomposition — the cost of growth is visible to CI, not invisible.
- The existing router and CLI test suites pass unchanged after every decomposition step — behavior is preserved, only structure changes.
- The decomposition pattern (served/servant zoning + entry_points + LOC cap) is reusable: the next god-object that forms is caught by the cap and split by the same pattern without a new design discussion.

---

## Out of Scope

- **Naming the exact module split for each decomposition.** Which symbols go in `cli/_io.py` vs. `cli/_args.py`, and which router concerns become which modules, is a planning deliverable per file. This document specifies the *pattern* (served/servant, entry_points, under-cap), not the per-file split.
- **Rewriting the CLI in Typer or argparse.** The CLI uses Click and the existing `pipeline_commands.py` / `trace_commands.py` pattern works. The decomposition reuses Click; a framework migration is a separate initiative.
- **Capping test files.** Tests are exempt from the 1000-line cap (see Assumptions). A separate test-file size guideline may follow but is not required here.
- **Capping generated or vendored code.** Generated JAX kernels, vendored KiCad parsers, and build artifacts are exempt.
- **Decomposing the firmware beyond `state_machine.c`.** Other `.c` files are under cap; Phase 4 targets only the one offender.
- **Migrating routing modules to a different package layout.** Decomposed router modules stay under `router_v6/` and `deterministic/stages/`; the package structure is preserved via re-exports.

---

## Assumptions

- A-LOC. **Cap value is 1000 lines.** This is the ideation target and is tight enough to force seams on all five offenders (the smallest, `state_machine.c`, is 1035 — just over — so the cap bites immediately on all five). A 1500-line cap would let `state_machine.c` and `sequential_routing.py` comply without changes and weaken the forcing function; a 500-line cap would require splitting files that are currently coherent. 1000 is the value that bites all five without over-splitting.
- A-SCOPE. **Cap applies to source `.py` (under `packages/**/src/` and `packages/**/temper_placer/`) and `.c` (under `firmware/`), excluding tests, generated code, vendored code, and build artifacts.** Tests are excluded because a parametrized test file can legitimately exceed 1000 lines and forcing its split harms readability. Generated code is excluded because its size is not under developer control. The exact exemption predicate (path globs) is a planning deliverable.
- A-ALLOWLIST. **Allowlist mechanism is a baseline `.loc-allowlist.txt` file with ticketed removal, not per-file pragmas.** Per-file `# pragma: loc-cap-allow` comments would be easy to add and hard to audit; a single baseline file with one line per offender plus a ticket ID is reviewable in one diff and shrinks monotonically (R3).
- A-ORDER. **Decomposition order is CLI → `exact_geometry_router` → `astar_pathfinding` → `sequential_routing` → `state_machine.c`**, in descending line count. The CLI is first despite `exact_geometry_router` being close in size because (a) the served/servant pattern is cleanest there, (b) `pipeline_commands.py` and `trace_commands.py` already prove the extraction works, and (c) the CLI is the user-facing surface where a regression is most visible — proving the pattern on the highest-visibility target builds confidence.
- A-DISCOVERY. **Discovery mechanism is Python `entry_points`, not pluggy and not bare `add_command`.** `entry_points` is native to the packaging system this repo already uses (`[project.scripts]` → `temper-placer = "temper_placer.cli:main"`), requires no new dependency, and gives true plugin discovery (a separate package could register a subcommand). `pluggy` adds a dependency for a feature this CLI does not need. Bare `add_command` is the status quo and is what this initiative replaces — it is the source of the "lost registration" risk the smoke tests catch.
- A-PREREQ. **The LOC cap lands first with the allowlist; decomposition follows.** The alternative — decompose first, then add the cap — would let new growth accumulate during the decomposition window. Cap-first-with-allowlist makes the cap a non-blocking gate on day one (all five offenders are allowlisted) and turns each decomposition into an allowlist-shrinking event the gate verifies.
- A-SMOKE. **Smoke tests are `temper-placer --help` output assertion + per-subcommand `--help` exits zero + registered-count equals entry_points-count.** This trio catches the three failure modes: a missing command (not in `--help`), a broken command (`--help` exits nonzero), and a registration/count mismatch (command object exists but is not in the group). Full end-to-end execution of every subcommand is out of scope — `--help` is the registration proxy.
- A-PUBLIC-API. **Router public import paths are preserved via `__init__.py` re-exports.** Downstream callers (`scripts/`, other `temper_placer` modules, tests) import from `router_v6` and `deterministic.stages` package roots; the decomposition moves symbols between internal modules but the package `__init__.py` re-exports the same names. No downstream edit is required.

---

## Open Questions

### Resolve Before Planning

- **[Affects R4][Scope]** Is `packages/temper-placer/temper_placer/` the only non-`src/` source tree, or do other packages keep source outside `src/`? The exemption predicate needs to cover all source trees without admitting tests. Confirm the full list of source paths before writing the gate script.
- **[Affects R7][Technical]** Should the entry_points group live in `packages/temper-placer/pyproject.toml` only, or should the root `pyproject.toml` (workspace) also declare one for cross-package subcommands? The current `[project.scripts]` entry is in the placer package; confirm whether cross-package subcommand discovery is a future need before scoping the group.
- **[Affects R8][Technical]** Does Click's `--help` output format remain stable enough across versions to assert on command names literally? If not, the smoke test should parse `--help` with Click's own `CliRunner` rather than scraping stdout. Confirm the Click version pin and the test approach.

### Deferred to Planning

- **[Affects R10][Design]** What are the responsibility seams in `exact_geometry_router.py` (3811 lines)? Identifying them is the planning deliverable for the first router split. The requirement specifies only that the split lands and the public API is preserved.
- **[Affects R12][Design]** Should `state_machine.c` be split by state (per-handler files) or by concern (transitions, actions, guards)? The 1035-line file is only just over the cap; a single extraction of one concern may suffice. Planning decides.
- **[Affects R3][Policy]** What is the review policy for an allowlist-shrinking PR that *also* adds a new entry for a newly-discovered offender? R3 says the allowlist must shrink monotonically, but a new offender discovered mid-decomposition needs an entry. Resolve whether the policy is "net shrink" (one removal can fund one addition) or "strict shrink" (additions require a separate ticketed exception).
- **[Affects R6][Naming]** Are the served module names (`cli/place.py`, `cli/route.py`, `cli/validate.py`, `cli/dru.py`, `cli/report.py`) the right granularity, or should some subcommands share a module? Several subcommands in `__init__.py` are variants of the same operation (e.g. `mvp3-route` and other route commands). Planning maps subcommands to modules.
