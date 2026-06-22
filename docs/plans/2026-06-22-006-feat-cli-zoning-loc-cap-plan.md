---
title: "feat: CLI Zoning, 1000-Line LOC Cap, and entry_points Discovery"
type: feat
status: active
date: 2026-06-22
origin: docs/brainstorms/2026-06-21-cli-zoning-loc-cap-requirements.md
---

# feat: CLI Zoning, 1000-Line LOC Cap, and entry_points Discovery

## Summary

A four-phase structural initiative that converts the Temper toolchain from one where complexity concentrates in five 2000–4000 line god-objects into one where **no source `.py`/`.c` file exceeds 1000 lines, enforced by CI**, with CLI subcommands discovered via Python `entry_points` instead of hand-wired `add_command` calls. Phase 1 lands the LOC cap as a non-blocking gate with a baseline allowlist capturing the five named offenders (the actual `main` branch contains **15 source `.py` files over 1000 lines** — see Open Question 1; this plan's Phase 1 allowlist scope is decided below). Phase 2 decomposes `packages/temper-placer/temper_placer/cli/__init__.py` (3946 lines) along Louis Kahn served/servant seams: subcommands are *served* → one self-registering module per command via a `temper_placer.cli.subcommands` entry_points group; argparse helpers, rich console IO, progress/summary printing, and signal handling are *servants* → internal `cli/_*.py` modules. Phase 3 splits the three routing god-objects (`exact_geometry_router.py` 3811, `astar_pathfinding.py` 2289, `sequential_routing.py` 2046) in descending risk order, preserving public import paths via `__init__.py` re-exports. Phase 4 brings `firmware/main/state_machine.c` (1035) under the cap by extracting per-state handlers. The 3946-line `cli/__init__.py` becomes a ~50-line dispatcher.

---

## Problem Frame

Five files dominate the repo's complexity surface, verified on current `main`:

| File | Lines | Role |
|------|-------|------|
| `packages/temper-placer/temper_placer/cli/__init__.py` | 3946 | CLI: 19 `@main.command`/`@main.group` decorators interleaved with console IO, progress, signal handling |
| `packages/temper-placer/temper_placer/router_v6/exact_geometry_router.py` | 3811 | Router: geometry primitives + `VisibilityGraph` + `ExactGeometryRouter` class (333–3786) + `run_exact_geometry_routing` |
| `packages/temper-placer/temper_placer/router_v6/astar_pathfinding.py` | 2289 | Router: 4 dataclasses + ~30 `_*` search/heap/grid helpers + `run_astar_pathfinding` |
| `packages/temper-placer/temper_placer/deterministic/stages/sequential_routing.py` | 2046 | Stage: `DiffPairConfig` + `SequentialRoutingStage` (64–end) |
| `firmware/main/state_machine.c` | 1035 | Firmware: 8-state machine with 16 `state_*_entry`/`state_*_update` handlers + safety interlocks |

Each file mixes several distinct responsibilities behind one module boundary. The CLI file interleaves Click command definitions, argument-parsing helpers (`cli/__init__.py:14-27` imports `signal`, `rich.console.Console`, `rich.progress.*`), rich console IO (`console = Console()` at line 27), progress reporting (lines 2661–2662), summary printing (`_print_placement_summary` at line 30), and signal handling (lines 954, 1057, 1067, 1074). New subcommands are added by appending; existing ones are found by scrolling. There is no structural pressure to stop growth — a 4000-line file becomes a 5000-line file with the same review cost, because nothing in CI measures it.

Two external ideas inform the decomposition. **Louis Kahn's served/servant zoning** separates the building's purpose (served) from its infrastructure (servant). Applied to the CLI: subcommands (`place`, `route`, `validate`, `dru`, `report`, …) are served — they are the product. Argument parsing, console IO, progress bars, and logging are servants — they exist to support the served spaces and are factored into modules the served modules import. The existing `cli/pipeline_commands.py` (lines 11, 95: `@click.command()` `pipeline`, `@click.group()` `phase`) and `cli/trace_commands.py` (line 6: `@click.group() trace`) already prove the served-module extraction pattern works — they are wired in at `cli/__init__.py:121-126`. **Python `entry_points`** (already used by this repo for `[project.scripts]` → `temper-placer = "temper_placer.cli:main"` in `packages/temper-placer/pyproject.toml`) provides native discovery: a package can advertise a named group (`temper_placer.cli.subcommands`) listing its subcommand objects, and the dispatcher loads them at startup without any `add_command` call. This makes registration automatic and a lost registration a CI-detectable regression rather than a silent missing command.

The risk this initiative addresses is not a single bug class — it is the *rate* at which these files accumulate bugs. A 4000-line file with twelve interleaved responsibilities is harder to review, harder to test in isolation, and harder to reason about than twelve 300-line files each with one responsibility. The LOC cap is a forcing function: it makes the cost of growth visible to CI.

---

## Scope Boundaries

### In scope

- R1–R12 from the origin requirements document: the LOC cap gate, baseline allowlist, frozen-ceiling enforcement, CLI served/servant decomposition, entry_points discovery, registration smoke tests, dispatcher shrinkage, three router decompositions, router test stability, and `state_machine.c` decomposition.
- The five named offenders are the decomposition targets of Phases 2–4. Phase 1's allowlist scope is resolved under Key Technical Decisions (Open Question 1).

### Deferred

- **Decomposing the 10 additional `.py` source files over 1000 lines discovered on `main`** (`kicad_parser.py:1352`, `kicad_writer.py:1443`, `nsga2.py:1521`, `config_loader.py:1549`, `optimizer/train.py:1652`, `benders_loop.py:1148`, `benders_master.py:1138`, `router_v6/pipeline.py:1135`, `losses/base.py:1131`, `convergence_analytics.py:1023`). These are not god-objects in the requirements doc's sense; their inclusion in the allowlist is decided below. Their *decomposition* is out of scope for N6 — a follow-up initiative (N7 candidate) would extend the pattern to them once the five-flagship decomposition proves the mechanism.
- **Rewriting the CLI in Typer or argparse.** The CLI uses Click (pinned `click>=8.1.0`); the existing `pipeline_commands.py` / `trace_commands.py` pattern works. Decomposition reuses Click.
- **Capping test files.** `packages/*/tests/**` and `firmware/test/**` are exempt (see Assumption A-SCOPE and Key Technical Decisions). A separate test-file size guideline may follow.
- **Capping generated or vendored code.** `firmware/test/build/**` (e.g. `CMakeCCompilerId.c`) and generated JAX kernels are exempt.
- **Decomposing firmware beyond `state_machine.c`.** Other `.c` source files are under cap (`safety.c` 531, `cascade_pid.c` 336 are the largest non-test sources after `state_machine.c`). Phase 4 targets only the one offender.
- **Migrating routing modules to a different package layout.** Decomposed router modules stay under `router_v6/` and `deterministic/stages/`; the package structure is preserved via re-exports.

### Out of scope

- Naming the exact module split for each router decomposition *beyond the seam analysis committed in this plan*. Per-file symbol assignment is a Phase 3 implementation deliverable; this plan commits the seams (Key Technical Decisions) but the implementer may refine within them.
- Cross-package subcommand discovery. R7's entry_points group is declared in `packages/temper-placer/pyproject.toml` only (resolves origin Open Question [Affects R7][Technical] — see below).
- Remediating the `pipeline`/`phase` command-name collision (see Risk Analysis) — surfaced as a finding in Phase 2, fix is part of U3.

---

## Key Technical Decisions

**Open Question 1 — Allowlist scope: capture ALL 15 over-cap `.py` source files, not "exactly five".** Research on `main` finds the requirements doc's "exactly five current offenders" (R2) is factually wrong. `find packages -name '*.py' -not -path '*/tests/*' | xargs wc -l | sort -n` yields **15** source files over 1000 lines: the five named plus `convergence_analytics.py` (1023), `losses/base.py` (1131), `router_v6/pipeline.py` (1135), `placement/benders_master.py` (1138), `placement/benders_loop.py` (1148), `io/kicad_parser.py` (1352), `io/kicad_writer.py` (1443), `optimizer/nsga2.py` (1521), `io/config_loader.py` (1549), `optimizer/train.py` (1652). The gate (R1) must fail on *all* over-cap files or it is non-functional. **Decision: the Phase 1 allowlist commits all 15 `.py` files plus `state_machine.c`, each annotated with a ticket ID.** The five named offenders get decomposition tickets owned by N6 (Phases 2–4); the 10 additional get follow-up tickets (N7 candidate). This preserves R1's gate integrity (the allowlist is the *complete* set of over-cap files, verifiable by the gate) and R3's monotonically-shrinking property. R2's "exactly five" is amended to "exactly fifteen `.py` plus one `.c` at Phase 1 commit" — flagged in Open Questions for the human to ratify, since it contradicts the origin doc's text.

**Open Question [Affects R4][Scope] — Source path predicate.** No package in this workspace uses a `src/` layout. Verified: every `packages/<name>/pyproject.toml` declares `packages = ["temper_<name>"]` (hatch wheel target) with the package directory at the package root (e.g. `packages/temper-placer/temper_placer/`, `packages/temper-drc/temper_drc/`). There is no `packages/*/src/` tree. **Decision: the gate scans `packages/*/temper_*/**/*.py` for source `.py`, excludes `packages/*/tests/**/*.py`, and scans `firmware/**/*.c` excluding `firmware/test/**/*.c` and `firmware/test/build/**`.** The exempt glob set is:
```
include: packages/*/temper_*/**/*.py, firmware/**/*.c
exclude: packages/*/tests/**, firmware/test/**, firmware/test/build/**, **/__pycache__/**
```
This covers all current source trees without admitting tests. (resolves origin Open Question [Affects R4][Scope])

**Open Question [Affects R7][Technical] — entry_points group location.** The `[project.scripts]` entry is in `packages/temper-placer/pyproject.toml` only (`temper-placer = "temper_placer.cli:main"`). The root `pyproject.toml` is a `[tool.uv.workspace]` manifest, not a package, and declares no `[project.scripts]`. Cross-package subcommand discovery is not a current need (only `temper-placer` exposes a CLI). **Decision: the `temper_placer.cli.subcommands` entry_points group lives in `packages/temper-placer/pyproject.toml` only.** A future cross-package group would require a separate initiative. (resolves origin Open Question [Affects R7][Technical])

**Open Question [Affects R8][Technical] — Smoke test mechanism.** Click is pinned `click>=8.1.0` in `packages/temper-placer/pyproject.toml`. Click's `--help` output format is stable across 8.1.x but is not part of Click's documented compatibility surface — scraping stdout is brittle. **Decision: smoke tests use `click.testing.CliRunner` to invoke `main` and each subcommand's `--help`, assert `result.exit_code == 0`, and parse subcommand names from `main.commands` (a `dict[str, Command]` Click exposes programmatically) rather than scraping `--help` text.** This is stable across Click 8.x. The registered-count assertion reads `len(main.commands)` and compares to `len(entry_points(group='temper_placer.cli.subcommands'))` via `importlib.metadata.entry_points`. (resolves origin Open Question [Affects R8][Technical])

**Open Question [Affects R3][Policy] — Allowlist growth policy.** **Decision: strict shrink.** A PR that adds a new allowlist entry without removing a larger one is rejected by the gate (the gate's "new entry without a corresponding removal" check from R3b). A newly-discovered offender discovered mid-decomposition gets its own ticketed PR that *also* decomposes an existing allowlisted file (net shrink), or — if decomposition is genuinely blocked — an explicit exception ticket referenced in the allowlist annotation, reviewed by the safety/architecture owner. The allowlist file format includes a `ticket` field per entry making every addition traceable. "Net shrink" is rejected as the default because it would let a 2000-line offender fund a 100-line addition, defeating the forcing function. (resolves origin Open Question [Affects R3][Policy])

**Open Question [Affects R6][Naming] — Served module map.** Each inlined `@main.command`/`@main.group` in `cli/__init__.py` maps to one served module, named after the command. The mapping, derived from the decorator scan at `cli/__init__.py:129,235,1351,1419,1641,1864,1921,1989,2338,2589,2755,3125,3188,3280,3340,3418,3502,3659,3794,3923`:

| Command (Click name) | Source line | Served module |
|---|---|---|
| `mvp3-route` | 129 | `cli/mvp3_route.py` |
| `optimize` | 235 | `cli/optimize.py` |
| `export` | 1351 | `cli/export.py` |
| `validate` | 1419 | `cli/validate.py` |
| `benchmark` | 1641 | `cli/benchmark.py` |
| `info` | 1864 | `cli/info.py` |
| `progression` | 1921 | `cli/progression.py` |
| `visualize` | 1989 | `cli/visualize.py` |
| `report` | 2338 | `cli/report.py` |
| `ablate` (group) | 2589 | `cli/ablate.py` |
| `pcl` (group) | 2755 | `cli/pcl.py` |
| `why` | 3125 | `cli/why.py` |
| `why-not` | 3188 | `cli/why_not.py` |
| `trace-info` | 3280 | `cli/trace_info.py` |
| `trace-list` | 3340 | `cli/trace_list.py` |
| `trace-export` | 3418 | `cli/trace_export.py` |
| `pipeline` | 3502 | `cli/pipeline_v2.py` (see collision note) |
| `phase` (group) | 3659 | `cli/phase_v2.py` (see collision note) |
| `place-deterministic` | 3794 | `cli/place_deterministic.py` |
| `version` | 3923 | `cli/version.py` (or inlined in dispatcher — 2 lines) |

**Collision note:** `cli/__init__.py:121-126` imports `pipeline`, `phase`, `trace` from `pipeline_commands.py` / `trace_commands.py` and registers them via `main.add_command(...)`. Then `cli/__init__.py:3502` and `:3659` define *different* `pipeline` and `phase` commands inline. Click stores commands by name in `main.commands`, so the inline `pipeline` (line 3502) shadows the imported `pipeline_commands.pipeline` (line 11 of `pipeline_commands.py`). The same applies to `phase`. This is a latent bug today. **Decision: the served-module extraction consolidates both `pipeline` definitions into one `cli/pipeline.py` (and `cli/phase.py`), with the inline 3502/3659 versions' bodies winning as the canonical implementation and the `pipeline_commands.py`/`trace_commands.py` files being folded into the served modules.** `trace_commands.py`'s `trace` group has no inline collision and moves to `cli/trace.py`. This is a behavior-affecting cleanup that U3 owns; it is called out in Risk Analysis and verified by the smoke tests (the surviving `pipeline`/`phase` commands must still appear in `--help`). (resolves origin Open Question [Affects R6][Naming])

**Servant module set.** Extracted from `cli/__init__.py`'s top-level imports and helper functions:
- `cli/_io.py` — `console = Console()` (line 27), `_print_placement_summary` (line 30), the `Progress`/`Panel`/`Table` rich setup (lines 20–23, 2661–2662, 3641–3648), summary/panel printers.
- `cli/_args.py` — repeated argument-parsing helpers (the `@click.argument`/`@click.option` patterns repeated across 19 commands; common option constructors like input-pcb/constraints/output paths).
- `cli/_signal.py` — the `signal.signal(signal.SIGINT, signal_handler)` blocks at lines 954, 1057, 1067, 1074 factored into a `with_interrupt_guard()` context manager.
- `cli/_version.py` — `from temper_placer import __version__` (line 25) and the `version` command (line 3923).

These are plain internal modules (underscore-prefixed, not registered as subcommands). Exact symbol-to-module assignment is a Phase 2 implementation deliverable; the seams above are the contract.

**Router decomposition seams.** From top-level symbol scans:

`exact_geometry_router.py` (3811 lines, 12 top-level symbols): 
- `_geom_primitives.py` — `compute_mst_edges` (65), `identify_differential_pairs` (112), `compute_parallel_offset_path` (157), `compute_steiner_point` (216).
- `_exact_route_path.py` — dataclasses `ExactSegment` (248), `ExactRoutePath` (268).
- `_visibility_graph.py` — `VisibilityGraph` (295).
- `exact_geometry_router.py` (residual) — `ExactGeometryRouter` (333–3786) orchestration + `run_exact_geometry_routing` (3787). This is ~3450 lines and still over cap; the `ExactGeometryRouter` class itself must be further split by method concern (path construction, grid/obstacle setup, scoring) — a Phase 3 implementation deliverable. `router_v6/__init__.py` re-exports all of the above names.

`astar_pathfinding.py` (2289 lines): 
- `astar_pathfinding.py` is mostly `_*` private helpers (30+ functions). Public surface is the 4 dataclasses (`RoutePath` 19, `RouteNode3D` 35, `RoutePath3D` 52, `RoutingFailureReport` 80, `PathfindingResult` 99) + `run_astar_pathfinding` (462). Internal callers exist: `router_v6/routing_failure_handler.py:13` imports `PathfindingResult`, `router_v6/grid_update.py:10` imports `PathfindingResult`, `run_router_v6.py` imports `RoutePath3D`, `tests/routing/test_path_simplifier_clearance.py:12` imports `RoutePath`. 
- Seams: `astar_pathfinding_dataclasses.py` (the 5 dataclasses), `astar_search.py` (`_astar_search` 1501, `_astar_search_lazy_theta_star` 1702, `_astar_search_theta_star` 1885, `_astar_search_3d` 1998, `_heuristic` 1578, `_line_of_sight` 1587, `_line_cost` 1641), `astar_pad_setup.py` (`_build_tht_pad_locations` 169, `_extract_pad_centers_per_net` 207, `_unblock_net_pads` 259, `_restore_net_pads` 372, `_is_at_tht_pad` 382, `_find_access_node` 410), `astar_pathfinding.py` (residual: `run_astar_pathfinding` + orchestration `_astar_route_with_ripup` 979, `_astar_route_multilayer` 1130, `_astar_route` 1329, `_route_segment_3d` 2138, marking helpers). `router_v6/__init__.py` re-exports `RoutePath`, `RoutePath3D`, `PathfindingResult`, `RoutingFailureReport`, `RouteNode3D`.

`sequential_routing.py` (2046 lines): 2 top-level symbols — `DiffPairConfig` (40) + `SequentialRoutingStage` (64–end, ~1980 lines in one class). The class is the file; decomposition requires splitting methods into mixins or helper modules. Seams: `sequential_routing_dataclasses.py` (`DiffPairConfig`), `sequential_routing_helpers.py` (the `snap_to_grid`/`add_endpoint_nudge` are already imported from `..geometry.grid_utils` at line 12 — not duplicated; the helpers to extract are the private methods of `SequentialRoutingStage` that do not touch `self` state, identified by static analysis during Phase 3), `sequential_routing.py` (residual: `SequentialRoutingStage` orchestration). `deterministic/stages/__init__.py` (68 lines) re-exports `SequentialRoutingStage`, `DiffPairConfig`, `COUPLED_ROUTER_AVAILABLE` (the runtime flag set at lines 29/31).

**`state_machine.c` decomposition seam (Open Question [Affects R12][Design]).** The file has 8 states × (entry + update) = 16 handler functions (`state_init_*` 346/362, `state_idle_*` 412/434, `state_pan_det_*` 470/494, `state_preheat_*` 543/564, `state_heating_*` 618/644, `state_no_pan_*` 751/771, `state_cooldown_*` 822/847, `state_fault_*` 875/896) plus `transition_to` (931), `check_safety_interlocks` (965), `fault_cleared` (1001), `show_message_then_transition` (1030), `run_self_test` (374). The 1035-line file is only just over the cap. **Decision: split by state — extract the 16 per-state handlers into `firmware/main/state_handlers.c` + `state_handlers.h`, keeping `state_machine.c` as the orchestration shell (`state_machine_init` 182, `state_machine_update` 224, `state_machine_start_profile` 217, the setters 278/323/328/338, `transition_to` 931, the static state struct 50–93).** This brings `state_machine.c` under cap and produces `state_handlers.c` at ~600 lines (16 handlers × ~35 lines), also under cap. `state_machine.c` and `state_handlers.c` are both added to `firmware/main/CMakeLists.txt` `SRCS`. The shared static state struct stays in `state_machine.c` with accessors exposed via `state_handlers.h` (or moved to a small `state_internal.h` — implementation-time call). Per-state splitting (8 files) is rejected as over-splitting for a 1035-line file. Per-concern splitting (transitions/actions/guards) is rejected because the handlers already interleave concerns and a per-state cut is cleaner. (resolves origin Open Question [Affects R12][Design])

**LOC cap gate mechanism.** A standalone Python script `tools/loc_cap_check.py` (new) that:
1. Globs `packages/*/temper_*/**/*.py` and `firmware/**/*.c`, applying the exempt globs.
2. For each file, `wc -l` equivalent (count `\n`).
3. Reads `.loc-allowlist.txt` (format: `<path> <baseline_lines> <ticket_id> # <description>`, one per line, `#` comments).
4. Fails with a named message per violation: (a) file over 1000 not on allowlist, (b) allowlisted file's line count > baseline, (c) new allowlist entry without removal (set-diff of allowlist vs previous commit's allowlist), (d) removed allowlist entry whose file is still over cap.
5. Exit nonzero on any violation.

The gate runs in a new CI job in `.github/workflows/python-tests.yml` (`loc-cap` job, runs on `push` and `pull_request`, `paths:` extended to include `firmware/**` and `tools/loc_cap_check.py` and `.loc-allowlist.txt`). It is a hard block. The existing `paths:` filter (`packages/**`, `pyproject.toml`, `.github/workflows/python-tests.yml`) is extended.

**Allowlist file format (`.loc-allowlist.txt` at repo root):**
```
# Temper LOC cap allowlist — shrinks monotonically (R3).
# Format: <repo-relative-path> <baseline_lines> <ticket-id> # <description>
packages/temper-placer/temper_placer/cli/__init__.py 3946 temper-N6-U2 # CLI god-object, Phase 2 decomposition
packages/temper-placer/temper_placer/router_v6/exact_geometry_router.py 3811 temper-N6-U5 # router, Phase 3
packages/temper-placer/temper_placer/router_v6/astar_pathfinding.py 2289 temper-N6-U6 # router, Phase 3
packages/temper-placer/temper_placer/deterministic/stages/sequential_routing.py 2046 temper-N6-U7 # stage, Phase 3
firmware/main/state_machine.c 1035 temper-N6-U8 # firmware, Phase 4
packages/temper-placer/temper_placer/optimizer/convergence_analytics.py 1023 temper-N7-1 # follow-up
packages/temper-placer/temper_placer/losses/base.py 1131 temper-N7-2 # follow-up
packages/temper-placer/temper_placer/router_v6/pipeline.py 1135 temper-N7-3 # follow-up
packages/temper-placer/temper_placer/placement/benders_master.py 1138 temper-N7-4 # follow-up
packages/temper-placer/temper_placer/placement/benders_loop.py 1148 temper-N7-5 # follow-up
packages/temper-placer/temper_placer/io/kicad_parser.py 1352 temper-N7-6 # follow-up
packages/temper-placer/temper_placer/io/kicad_writer.py 1443 temper-N7-7 # follow-up
packages/temper-placer/temper_placer/optimizer/nsga2.py 1521 temper-N7-8 # follow-up
packages/temper-placer/temper_placer/io/config_loader.py 1549 temper-N7-9 # follow-up
packages/temper-placer/temper_placer/optimizer/train.py 1652 temper-N7-10 # follow-up
```

**Documentation sync.** Per `AGENTS.md` "Documentation & Context Maintenance": the gate mechanism, allowlist format, served/servant zoning convention, entry_points registration procedure, and the `--help` smoke-test convention are recorded in `CLAUDE.md` (or `AGENT_INSTRUCTIONS.md` — confirm at implementation time; the sibling plan N2 references `CLAUDE.md`) in the same commit as U1 and U3.

---

## Implementation Units

### Phase 1 — LOC cap gate + baseline allowlist

### U1. LOC cap gate script, allowlist, and CI job

**Goal:** A CI-enforced gate that fails any push or PR in which a source `.py`/`.c` file exceeds 1000 lines and is not listed in `.loc-allowlist.txt`, with the frozen-ceiling and monotonically-shrinking properties from R3.

**Requirements:** R1, R2, R3, R4

**Dependencies:** None

**Files:**
- `tools/loc_cap_check.py` (new — the gate script)
- `.loc-allowlist.txt` (new — at repo root, 16 entries as above)
- `.github/workflows/python-tests.yml` (add `loc-cap` job; extend `paths:` with `firmware/**`, `tools/loc_cap_check.py`, `.loc-allowlist.txt`)
- `CLAUDE.md` or `AGENT_INSTRUCTIONS.md` (document gate, allowlist format, strict-shrink policy)

**Approach:**

1. Write `tools/loc_cap_check.py` using only stdlib (`pathlib`, `re`, `sys`, `subprocess` for the `git diff` of the allowlist against `main`). Steps:
   - Build the include/exclude glob sets (see Key Technical Decisions). Use `pathlib.Path.glob`.
   - For each included file, count lines (`sum(1 for _ in open(f))`).
   - Parse `.loc-allowlist.txt`: each non-comment, non-blank line is `<path> <baseline_lines> <ticket-id>` optionally followed by `# <desc>`. Validate every listed path exists; warn on missing.
   - Build `over_cap = {f: lines for f in included if lines > 1000}`.
   - Violation classes:
     - `UNLISTED_OVER_CAP`: `f in over_cap and f not in allowlist` → fail.
     - `ALLOWLIST_GREW`: `allowlisted_file_lines > baseline` → fail.
      - `NEW_ENTRY_NO_REMOVAL`: on a PR, `git diff origin/main...HEAD -- .loc-allowlist.txt` shows added lines > removed lines → fail (strict shrink). On a push to `main`, compare against the previous commit's allowlist. Explicit commands: **on push to main:** read allowlist from `git show HEAD~1:.loc-allowlist.txt`; **on pull_request:** read from `origin/main` via `git show origin/main:.loc-allowlist.txt`.
     - `REMOVED_STILL_OVER_CAP`: removed entry whose file is still in `over_cap` → fail.
   - Print one named message per violation: `[LOC-CAP-FAIL] <class>: <file> <lines> lines (cap 1000, baseline <b>, ticket <id>)`.
   - Exit 1 on any violation, 0 otherwise.
2. Commit `.loc-allowlist.txt` with the 16 entries above. The gate, run on this commit, must pass (every over-cap file is listed, no allowlisted file has grown, no removal).
3. Add the `loc-cap` job to `.github/workflows/python-tests.yml`:
   ```yaml
   loc-cap:
     runs-on: ubuntu-latest
     steps:
       - uses: actions/checkout@v4
         with: { fetch-depth: 0 }
       - name: Install uv
         uses: astral-sh/setup-uv@v4
         with: { version: "latest" }
       - name: Set up Python
         run: uv python install 3.12
       - name: LOC cap gate
         run: uv run python tools/loc_cap_check.py
   ```
   Extend the `paths:` filter on both `push` and `pull_request` to add `'firmware/**'`, `'tools/loc_cap_check.py'`, `'.loc-allowlist.txt'`.
4. Document in `CLAUDE.md`: the gate command (`uv run python tools/loc_cap_check.py`), the allowlist format, the strict-shrink policy, and the exemption globs.

**Patterns to follow:** Existing `.github/workflows/python-tests.yml` job structure. Stdlib-only scripts (no `uv run` needed for the script itself, but invoked via `uv run python` for environment consistency).

**Test scenarios:**
- On the commit that lands U1, `uv run python tools/loc_cap_check.py` exits 0.
- Temporarily adding a 1001-line `.py` file under `packages/temper-placer/temper_placer/` (not on allowlist) → exit 1 with `[LOC-CAP-FAIL] UNLISTED_OVER_CAP: <file> 1001 lines`.
- Appending one line to `cli/__init__.py` (pushing it to 3947) → `ALLOWLIST_GREW` violation naming `cli/__init__.py 3947 > baseline 3946`.
- Adding a new allowlist entry without removing one → `NEW_ENTRY_NO_REMOVAL`.
- Removing `state_machine.c` from the allowlist while it is still 1035 lines → `REMOVED_STILL_OVER_CAP`.
- A 1001-line file under `packages/temper-placer/tests/` → NOT flagged (test exempt).
- A 1001-line file under `firmware/test/` → NOT flagged (test exempt).
- A 1001-line file under `packages/temper-placer/temper_placer/foo.py` not in allowlist → flagged.

**Verification:** `uv run python tools/loc_cap_check.py` exits 0 on the U1 commit. The `loc-cap` CI job is green. Manually injecting each violation class locally produces the named failure.

**Local feedback (recommended):** Add a `.pre-commit-config.yaml` entry or a `make loc-check` target running `python tools/loc_cap_check.py` for instant local feedback before pushing. The CI gate is the enforcement boundary; a pre-commit hook or Makefile target gives developers a sub-second check without waiting for CI.

---

### Phase 2 — CLI served/servant decomposition + entry_points discovery

### U2. Servant module extraction

**Goal:** Extract argparse helpers, rich console IO, progress/summary printing, and signal handling from `cli/__init__.py` into `cli/_io.py`, `cli/_args.py`, `cli/_signal.py`, `cli/_version.py` — plain internal modules imported by the served modules. No behavior change observable to a user running `temper-placer`.

**Requirements:** R5

**Dependencies:** U1 (gate must be in place so the extraction's LOC impact is visible)

**Files:**
- `packages/temper-placer/temper_placer/cli/_io.py` (new — `console`, `_print_placement_summary`, rich setup)
- `packages/temper-placer/temper_placer/cli/_args.py` (new — common `@click.argument`/`@click.option` constructors)
- `packages/temper-placer/temper_placer/cli/_signal.py` (new — `with_interrupt_guard()` context manager)
- `packages/temper-placer/temper_placer/cli/_version.py` (new — `__version__` + `version` command)
- `packages/temper-placer/temper_placer/cli/__init__.py` (replace inline servant code with imports from `._*`)

**Approach:**

1. Move `console = Console()` (`cli/__init__.py:27`) and `_print_placement_summary` (line 30) and the rich imports (lines 20–23) into `cli/_io.py`. Re-import in `__init__.py` as `from ._io import console, _print_placement_summary`.
2. Move the four `signal.signal(signal.SIGINT, ...)` blocks (lines 954, 1057, 1067, 1074) into `cli/_signal.py` as a `with_interrupt_guard()` context manager that installs the handler on `__enter__` and restores on `__exit__`. Replace the four call sites with `with with_interrupt_guard():`.
3. Identify repeated `@click.option`/`@click.argument` patterns (input_pcb path, output path, constraints path, config path, loops path) and factor them into `cli/_args.py` as decorators (e.g. `input_pcb_arg()`, `output_opt()`). Apply at the call sites during U3 (served extraction) rather than in U2, to keep U2 a pure servant move.
4. Move `from temper_placer import __version__` (line 25) and the `version` command (line 3923, 2 lines) into `cli/_version.py`.
5. `cli/__init__.py` line count drops by the moved lines; verify the gate still passes (the allowlist baseline for `cli/__init__.py` is 3946; after U2 it must be ≤ 3946 — it will be, since extraction only removes lines).

**Patterns to follow:** The existing `cli/pipeline_commands.py` / `cli/trace_commands.py` style — module-level Click decorators, no class wrapping, plain functions. Underscore-prefix convention for non-public servant modules.

**Test scenarios:**
- `from temper_placer.cli._io import console` succeeds.
- `from temper_placer.cli._signal import with_interrupt_guard` succeeds; `with with_interrupt_guard(): pass` does not raise.
- `temper-placer --help` still lists all 19+ commands (U2 does not remove commands, only moves helpers).
- `temper-placer version` still prints the version.
- `temper-placer mvp3-route --help` exits 0 (the signal-guard refactor does not break the command).
- Existing CLI tests pass unchanged: `packages/temper-placer/tests/cli/test_*.py` (test_validate_command, test_pipeline_commands, test_place_deterministic, test_export_command, test_report_command, test_optimize_command, test_ablate_command, test_cli_error_handling) and `tests/explainability/test_cli_commands.py` (35+ `from temper_placer.cli import main` imports).

**Verification:** `uv run pytest packages/temper-placer/tests/cli/ -v` passes. `uv run python tools/loc_cap_check.py` passes. `temper-placer --help` lists every previously-available command.

---

### U3. Served subcommand extraction + entry_points registration + dispatcher shrink

**Goal:** Extract each inlined `@main.command`/`@main.group` from `cli/__init__.py` into its own served module (per the map in Key Technical Decisions), declare the `temper_placer.cli.subcommands` entry_points group in `packages/temper-placer/pyproject.toml`, replace `__init__.py`'s command definitions with a dispatcher that loads the group at startup, resolve the `pipeline`/`phase` collision by consolidation, and remove `cli/__init__.py` from `.loc-allowlist.txt`.

**Requirements:** R6, R7, R8, R9

**Dependencies:** U2 (servants available for served modules to import)

**Files:**
- `packages/temper-placer/temper_placer/cli/{mvp3_route,optimize,export,validate,benchmark,info,progression,visualize,report,ablate,pcl,why,why_not,trace_info,trace_list,trace_export,pipeline,phase,place_deterministic,trace}.py` (new — one per served command; `pipeline.py` and `phase.py` consolidate the `pipeline_commands.py` bodies with the inline `__init__.py:3502/3659` bodies; `trace.py` replaces `trace_commands.py`)
- `packages/temper-placer/temper_placer/cli/pipeline_commands.py` (delete — folded into `cli/pipeline.py` + `cli/phase.py`)
- `packages/temper-placer/temper_placer/cli/trace_commands.py` (delete — folded into `cli/trace.py`)
- `packages/temper-placer/temper_placer/cli/__init__.py` (rewrite to ~50-line dispatcher)
- `packages/temper-placer/pyproject.toml` (add `[project.entry-points."temper_placer.cli.subcommands"]` table)
- `.loc-allowlist.txt` (remove the `cli/__init__.py` entry; gate confirms under cap)

**Approach:**

1. For each command in the map, create a served module containing the `@click.command(...)`/`@click.group(...)` decorated function and its body, importing servants from `cli/_io`, `cli/_args`, `cli/_signal` as needed. Each served module exposes the command object as a module-level name (e.g. `mvp3_route = click.Command(...)`).
2. For `pipeline` and `phase`: the inline `__init__.py:3502` (`pipeline`) and `:3659` (`phase`) bodies are the canonical implementations (they shadow the `pipeline_commands.py` versions today). Move their bodies into `cli/pipeline.py` and `cli/phase.py`. The `pipeline_commands.py` versions (lines 11, 95) are deleted — they are dead (shadowed). Verify via the smoke tests that the surviving `pipeline`/`phase` commands retain all subcommands (`semantic`, `topological`, `geometric`, `routing` from `pipeline_commands.py:104,133,159,192` — confirm whether these subcommands are also inlined in `__init__.py:3502`'s `pipeline` or only in `pipeline_commands.py`; if only in the latter, they must be preserved in `cli/pipeline.py`). This is the one behavior-affecting cleanup in N6 and is called out in Risk Analysis.
3. Add to `packages/temper-placer/pyproject.toml`:
   ```toml
   [project.entry-points."temper_placer.cli.subcommands"]
   mvp3-route = "temper_placer.cli.mvp3_route:mvp3_route"
   optimize = "temper_placer.cli.optimize:optimize"
   # ... one per served command
   ```
   Each value is `module:attribute` pointing at the Click command object.
4. Rewrite `cli/__init__.py` to ~50 lines:
   ```python
   from __future__ import annotations
   import click
   from importlib.metadata import entry_points
   from temper_placer import __version__
   from ._version import version

   @click.group()
   @click.version_option(version=__version__, prog_name="temper-placer")
   def main() -> None:
       """temper-placer: JAX-based PCB placement optimizer."""
       pass

   for ep in entry_points(group="temper_placer.cli.subcommands"):
       cmd = ep.load()
       main.add_command(cmd)

   main.add_command(version)
   ```
   No `from .pipeline_commands import ...` / `main.add_command(...)` blocks remain. The `version` command may stay inlined (2 lines) or be registered via entry_points — implementation-time call; prefer entry_points for consistency.
5. Remove the `cli/__init__.py` line from `.loc-allowlist.txt`. The gate verifies `cli/__init__.py` is under 1000 (target ~50).
6. Delete `cli/__init__.py.bak` (a stale backup file present in the cli/ directory).

**Patterns to follow:** `cli/trace_commands.py` (the existing served module). `importlib.metadata.entry_points` (stdlib, Python 3.11+ per `requires-python = ">=3.11"`).

**Test scenarios:**
- `temper-placer --help` lists every command name in the entry_points group (smoke test U4).
- Each listed subcommand's `--help` exits 0 (U4).
- `len(main.commands)` equals `len(entry_points(group="temper_placer.cli.subcommands"))` + 1 (the `version` command if not in the group) (U4).
- `cli/__init__.py` is under 1000 lines (gate).
- `cli/pipeline.py`, `cli/phase.py`, `cli/trace.py` each under 1000 lines (gate).
- `pipeline_commands.py` and `trace_commands.py` no longer exist; no `ImportError` from any test (`grep -r pipeline_commands` returns only history).
- `temper-placer pipeline --help` shows the `semantic`/`topological`/`geometric`/`routing` subcommands (collision-resolution verification).
- All existing `packages/temper-placer/tests/cli/test_*.py` tests pass unchanged (they import `from temper_placer.cli import main`).

**Verification:** `uv run pytest packages/temper-placer/tests/cli/ -v` passes. `uv run python tools/loc_cap_check.py` passes with `cli/__init__.py` removed from the allowlist. `temper-placer --help` shows all commands.

---

### U4. Registration smoke tests

**Goal:** A pytest that asserts (a) `temper-placer --help` (via `CliRunner`) lists every subcommand name in the `temper_placer.cli.subcommands` entry_points group, (b) each listed subcommand's `--help` exits 0, (c) `len(main.commands)` equals the entry_points count (plus the inlined `version` if not registered). Catches lost registrations.

**Requirements:** R8

**Dependencies:** U3

**Files:**
- `packages/temper-placer/tests/cli/test_subcommand_registration.py` (new)

**Approach:**

1. Use `click.testing.CliRunner`:
   ```python
   from click.testing import CliRunner
   from importlib.metadata import entry_points
   from temper_placer.cli import main

   def test_all_entry_points_registered():
       eps = entry_points(group="temper_placer.cli.subcommands")
       ep_names = {ep.name for ep in eps}
       registered = set(main.commands.keys())
       assert ep_names <= registered, f"Missing: {ep_names - registered}"

   def test_each_subcommand_help_exits_zero():
       runner = CliRunner()
       for name in main.commands.keys():
           result = runner.invoke(main, [name, "--help"])
           assert result.exit_code == 0, f"{name} --help exited {result.exit_code}"

   def test_count_matches():
       eps = entry_points(group="temper_placer.cli.subcommands")
       # main.commands includes the entry_points-loaded commands plus any
       # inlined (version). Adjust the expectation accordingly.
       assert len(main.commands) >= len(eps)
   ```
2. The test reads `main.commands` (a `dict[str, Command]`) directly — no stdout scraping. This is stable across Click 8.x.
3. Wire into the existing `Run temper-placer tests (core only for CI speed)` step (`.github/workflows/python-tests.yml` — runs `uv run pytest tests/core/ -v`). The new test file lives in `tests/cli/`. Extend the CI step to `uv run pytest tests/core/ tests/cli/ -v` so that registration smoke tests run on every push and PR alongside the core tests.

**Patterns to follow:** `packages/temper-placer/tests/cli/test_validate_command.py` (existing CliRunner usage).

**Test scenarios:**
- On U3's commit, all three tests pass.
- Comment out one entry_points line in `pyproject.toml` (after `uv sync`) → `test_all_entry_points_registered` fails naming the missing command.
- Add a `@click.command()` to a served module without a `pyproject.toml` entry → `test_all_entry_points_registered` does not fail (the command is not in the group), but `test_count_matches` flags the discrepancy if the command is somehow registered. The primary signal is the entry_points group being the source of truth — a command not in the group is invisible to the dispatcher.
- A served module that raises at import time → `test_each_subcommand_help_exits_zero` fails with nonzero exit.

**Verification:** `uv run pytest packages/temper-placer/tests/cli/test_subcommand_registration.py -v` passes. CI runs it on every push/PR.

---

### Phase 3 — Routing god-object decomposition

### U5. Decompose `exact_geometry_router.py` (3811 lines)

**Goal:** Split `exact_geometry_router.py` into under-cap modules under `router_v6/`, preserving the public import path `from temper_placer.router_v6.exact_geometry_router import ExactGeometryRouter, ExactSegment, ExactRoutePath, VisibilityGraph, run_exact_geometry_routing, compute_mst_edges, identify_differential_pairs, compute_parallel_offset_path, compute_steiner_point` via re-exports in `router_v6/__init__.py` (124 lines today) and in `exact_geometry_router.py` itself (residual module re-imports from the split modules).

**Requirements:** R4, R9, R10, R11

**Dependencies:** U1 (gate)

**Files:**
- `packages/temper-placer/temper_placer/router_v6/_geom_primitives.py` (new — `compute_mst_edges`, `identify_differential_pairs`, `compute_parallel_offset_path`, `compute_steiner_point`)
- `packages/temper-placer/temper_placer/router_v6/_exact_route_path.py` (new — `ExactSegment`, `ExactRoutePath` dataclasses)
- `packages/temper-placer/temper_placer/router_v6/_visibility_graph.py` (new — `VisibilityGraph`)
- `packages/temper-placer/temper_placer/router_v6/exact_geometry_router.py` (residual — `ExactGeometryRouter` class + `run_exact_geometry_routing`; may require further method-level split if still over cap)
- `packages/temper-placer/temper_placer/router_v6/__init__.py` (add re-exports if not already present — currently re-exports from `constraint_model`, `dense_package_detection`, …, `stage0_data`; verify `ExactGeometryRouter` is reachable via `temper_placer.router_v6` today)

**Approach:**

1. Move the 4 geometry-primitive functions (lines 65, 112, 157, 216) and the 3 dataclasses (`ExactSegment` 248, `ExactRoutePath` 268, `VisibilityGraph` 295) into their respective new modules, preserving imports of their dependencies.
2. `exact_geometry_router.py` becomes `from ._geom_primitives import compute_mst_edges, ...` + `from ._exact_route_path import ExactSegment, ExactRoutePath` + `from ._visibility_graph import VisibilityGraph` + the `ExactGeometryRouter` class (333–3786) + `run_exact_geometry_routing` (3787). This re-export keeps `from temper_placer.router_v6.exact_geometry_router import X` working for all downstream callers.
3. The `ExactGeometryRouter` class itself is ~3450 lines and still over cap. The Phase 3 implementer further splits it by method concern into `exact_geometry_router.py` (orchestration: `__init__`, `route`, top-level pipeline methods) + `exact_geometry_router_internals.py` (path construction, grid/obstacle setup, scoring heuristics). The exact method-to-module assignment is a Phase 3 implementation deliverable; the gate enforces the cap.
4. Downstream callers verified to require no edit: `profile_bottlenecks.py:23`, `router-experiments/exp_30_*.py`, `validate_optimizations.py:20`, `test_dc_quick.py:11`, `tests/router_v6/test_congestion_tuning.py:17`, `tests/router_v6/test_homotopy_integration.py:18`, `tests/router_v6/test_via_insertion.py:21`, `tests/router_v6/test_layer_config_loading.py:15`, `tests/router_v6/test_direct_coordinate_routing.py:11`, `tests/router_v6/test_congested_homotopy.py:6`, `tests/router_v6/test_quick_isolation.py:11`, `tests/router_v6/test_sequential_interference.py:13`, `tests/router_v6/test_zone_routing.py:92`, `tests/test_power_pcb_validation.py:40`, `tests/performance/benchmark_suite.py:13`, `test_boost_simple.py:10` — all import `ExactGeometryRouter` from `temper_placer.router_v6.exact_geometry_router`, which re-exports unchanged.
5. Run the full router test suite: `uv run pytest packages/temper-placer/tests/router_v6/ -v` must pass unchanged. If a test imports an internal symbol that moved (e.g. a private `_*` helper), update the test to import from the new module — the public API surface does not shrink (R11).
6. Remove `exact_geometry_router.py` from `.loc-allowlist.txt` once under cap.

**Patterns to follow:** The existing `router_v6/__init__.py` re-export pattern (lines 7–67 re-export from many submodules).

**Test scenarios:**
- `from temper_placer.router_v6.exact_geometry_router import ExactGeometryRouter, ExactSegment, ExactRoutePath, VisibilityGraph, run_exact_geometry_routing, compute_mst_edges, identify_differential_pairs, compute_parallel_offset_path, compute_steiner_point` succeeds unchanged.
- `uv run pytest packages/temper-placer/tests/router_v6/ -v` passes.
- `uv run python tools/loc_cap_check.py` passes with `exact_geometry_router.py` removed from allowlist; the new `_*.py` modules are each under cap.

**Verification:** Router test suite green; gate green with allowlist entry removed.

---

### U6. Decompose `astar_pathfinding.py` (2289 lines)

**Goal:** Split per the seams in Key Technical Decisions: dataclasses, search algorithms, pad setup, residual orchestration. Preserve `from temper_placer.router_v6.astar_pathfinding import RoutePath, RouteNode3D, RoutePath3D, RoutingFailureReport, PathfindingResult, run_astar_pathfinding` via re-exports.

**Requirements:** R4, R9, R10, R11

**Dependencies:** U5 (proves the pattern on the larger router)

**Files:**
- `packages/temper-placer/temper_placer/router_v6/astar_pathfinding_dataclasses.py` (new — 5 dataclasses)
- `packages/temper-placer/temper_placer/router_v6/astar_search.py` (new — the 7 `_*_search`/`_*_theta_star`/`_heuristic`/`_line_*` functions)
- `packages/temper-placer/temper_placer/router_v6/astar_pad_setup.py` (new — `_build_tht_pad_locations`, `_extract_pad_centers_per_net`, `_unblock_net_pads`, `_restore_net_pads`, `_is_at_tht_pad`, `_find_access_node`)
- `packages/temper-placer/temper_placer/router_v6/astar_pathfinding.py` (residual — `run_astar_pathfinding` + orchestration + re-exports)
- `packages/temper-placer/temper_placer/router_v6/__init__.py` (add re-exports if needed)

**Approach:** Same as U5. Internal callers verified: `router_v6/routing_failure_handler.py:13` (`PathfindingResult`), `router_v6/grid_update.py:10` (`PathfindingResult`), `run_router_v6.py` (`RoutePath3D`), `tests/routing/test_path_simplifier_clearance.py:12` (`RoutePath`). All import from `temper_placer.router_v6.astar_pathfinding`, which re-exports. Run `uv run pytest packages/temper-placer/tests/routing/ -v` + `packages/temper-placer/tests/router_v6/ -v`. Remove from allowlist when under cap.

**Test scenarios:**
- Public imports succeed unchanged.
- `uv run pytest packages/temper-placer/tests/routing/ packages/temper-placer/tests/router_v6/ -v` passes.
- Gate passes with `astar_pathfinding.py` removed from allowlist.

**Verification:** Test suites green; gate green.

---

### U7. Decompose `sequential_routing.py` (2046 lines)

**Goal:** Split the `SequentialRoutingStage` class (64–end, ~1980 lines) into orchestration + stateless helper modules. Preserve `from temper_placer.deterministic.stages.sequential_routing import SequentialRoutingStage, DiffPairConfig, COUPLED_ROUTER_AVAILABLE, snap_to_grid, add_endpoint_nudge` via re-exports.

**Requirements:** R4, R9, R10, R11

**Dependencies:** U6

**Files:**
- `packages/temper-placer/temper_placer/deterministic/stages/sequential_routing_dataclasses.py` (new — `DiffPairConfig`)
- `packages/temper-placer/temper_placer/deterministic/stages/sequential_routing_helpers.py` (new — stateless methods extracted from `SequentialRoutingStage`, identified by static analysis of `self`-free method bodies)
- `packages/temper-placer/temper_placer/deterministic/stages/sequential_routing.py` (residual — `SequentialRoutingStage` orchestration + re-exports)
- `packages/temper-placer/temper_placer/deterministic/stages/__init__.py` (68 lines — add re-exports if needed)

**Approach:** Same as U5/U6. `snap_to_grid`/`add_endpoint_nudge` are already imported from `..geometry.grid_utils` (line 12), not defined here — they remain re-exported from `sequential_routing.py` for the test at `tests/deterministic/test_pipeline_integration.py:575,586`. `COUPLED_ROUTER_AVAILABLE` is set at lines 29/31 (try/except import) — keep in `sequential_routing.py` and re-export. Internal callers verified: `router-experiments/exp_24_piantor_benchmark.py:29`, `exp_24c_blocking_analysis.py:18`, `tests/integration/test_routing_experiments.py:583`, `tests/deterministic/test_power_planes.py:45`, `tests/deterministic/test_pipeline_integration.py:575,586`, `tests/deterministic/test_pth_clearance.py:120`, `scripts/validate_exp6_usb_routing.py:28`, `scripts/test_exp6_integration.py:27`. Run `uv run pytest packages/temper-placer/tests/deterministic/ -v`. Remove from allowlist when under cap.

**Test scenarios:**
- `from temper_placer.deterministic.stages.sequential_routing import SequentialRoutingStage, DiffPairConfig, COUPLED_ROUTER_AVAILABLE, snap_to_grid, add_endpoint_nudge` succeeds.
- `uv run pytest packages/temper-placer/tests/deterministic/ -v` passes.
- Gate passes with `sequential_routing.py` removed from allowlist.

**Verification:** Test suite green; gate green.

---

### Phase 4 — Firmware state machine under cap

### U8. Decompose `state_machine.c` (1035 lines)

**Goal:** Extract the 16 per-state handler functions into `firmware/main/state_handlers.c` + `state_handlers.h`, leaving `state_machine.c` as the orchestration shell. Bring `state_machine.c` under 1000 lines and remove it from `.loc-allowlist.txt`.

**Requirements:** R4, R9, R12

**Dependencies:** U1 (gate)

**Files:**
- `firmware/main/state_handlers.h` (new — prototypes for the 16 handlers + shared accessors)
- `firmware/main/state_handlers.c` (new — the 16 handler bodies: `state_init_entry/update`, `state_idle_*`, `state_pan_det_*`, `state_preheat_*`, `state_heating_*`, `state_no_pan_*`, `state_cooldown_*`, `state_fault_*`)
- `firmware/main/state_machine.c` (residual — static state struct 50–93, `state_machine_init` 182, `state_machine_update` 224, `state_machine_start_profile` 217, setters 278/323/328/338, `transition_to` 931, `check_safety_interlocks` 965, `fault_cleared` 1001, `show_message_then_transition` 1030, `run_self_test` 374)
- `firmware/main/state_machine.h` (no change — public enum/typedef API is preserved)
- `firmware/main/CMakeLists.txt` (add `state_handlers.c` to `SRCS`)
- `.loc-allowlist.txt` (remove `state_machine.c` entry)

**Approach:**

1. The static state struct (lines 50–93, `static struct { ... } g_state;`) and `thermal_mass_handle_t thermal_mass` (line 82) are accessed by both the handlers and the orchestration. Two options:
   - (a) Keep the struct in `state_machine.c` as `static`, expose accessors (`state_machine_get_state()`, `state_machine_set_state()`, etc.) in `state_handlers.h`. Handlers call accessors instead of touching `g_state` directly.
   - (b) Move the struct to `state_handlers.c` as `static`, expose accessors, have `state_machine.c` call the same accessors.
   
   Prefer (a): the struct is conceptually owned by the state machine; handlers are guests. The accessors are added to `state_handlers.h` and implemented in `state_machine.c`. This is a small refactor of the handler bodies (replace `g_state.xxx` with `state_machine_get_xxx()`), mechanical and reviewable.
2. Move the 16 handler function bodies (lines 346–929) to `state_handlers.c`. Update their prototypes in `state_handlers.h`. The `static` keyword on the handlers is dropped (they are now cross-file) — or kept `static` only if the accessors approach makes them callable solely via function pointers in a dispatch table; implementation-time call. Prefer non-static with prototypes in `state_handlers.h`, called from `state_machine_update` (224) via a switch or function-pointer table.
3. Add `state_handlers.c` to `firmware/main/CMakeLists.txt` `SRCS` (currently `"main.c"`, `"state_machine.c"`).
4. The `state_machine.c` residual is ~400 lines (orchestration + accessors + safety/transition helpers). `state_handlers.c` is ~600 lines. Both under cap.
5. Verify firmware build: `idf.py build` (or the project's firmware build command — confirm in `firmware/` at implementation time). The firmware test suite at `firmware/test/test_state_machine.c` (1157 lines, exempt) and `test_integration.c` (1099, exempt) must pass.

**Patterns to follow:** Existing ESP-IDf component structure (`firmware/main/CMakeLists.txt` `idf_component_register`). The `static const char *TAG` pattern (line 25) stays in `state_machine.c`.

**Test scenarios:**
- `firmware/main/state_machine.c` is under 1000 lines (gate).
- `firmware/main/state_handlers.c` is under 1000 lines (gate).
- Firmware build succeeds (`idf.py build` or equivalent).
- `firmware/test/test_state_machine.c` passes unchanged (it includes `state_machine.h`, whose public API is unchanged).
- `firmware/test/test_integration.c` passes unchanged.
- All 8 states still reachable and behave per the existing state-machine tests.

**Verification:** Firmware build green; firmware tests green; `uv run python tools/loc_cap_check.py` passes with `state_machine.c` removed from allowlist.

---

## System-Wide Impact

- **CI pipeline (`.github/workflows/python-tests.yml`):** New `loc-cap` job (U1) runs `uv run python tools/loc_cap_check.py` on every push/PR. `paths:` filter extended with `firmware/**`, `tools/loc_cap_check.py`, `.loc-allowlist.txt`. New smoke test `packages/temper-placer/tests/cli/test_subcommand_registration.py` (U4) runs in the existing `Run temper-placer tests (core only for CI speed)` step — extend that step's `tests/core/` to include `tests/cli/` if not already covered, or add a separate step. No new long-running job.
- **`packages/temper-placer/pyproject.toml`:** Gains `[project.entry-points."temper_placer.cli.subcommands"]` table (U3) with ~20 entries. The existing `[project.scripts]` `temper-placer = "temper_placer.cli:main"` is unchanged.
- **`packages/temper-placer/temper_placer/cli/`:** `__init__.py` shrinks from 3946 to ~50 lines. ~20 new served modules. 4 new servant modules (`_io`, `_args`, `_signal`, `_version`). `pipeline_commands.py` and `trace_commands.py` deleted. `__init__.py.bak` deleted. The `temper-placer` console-script entry point is unchanged.
- **`packages/temper-placer/temper_placer/router_v6/`:** `exact_geometry_router.py` shrinks; 3–4 new `_*.py` modules + re-exports. `astar_pathfinding.py` shrinks; 3 new modules + re-exports. `__init__.py` (124 lines) gains re-exports for the split symbols.
- **`packages/temper-placer/temper_placer/deterministic/stages/`:** `sequential_routing.py` shrinks; 2 new modules + re-exports. `__init__.py` (68 lines) gains re-exports.
- **`firmware/main/`:** New `state_handlers.c` + `state_handlers.h`. `state_machine.c` shrinks. `CMakeLists.txt` adds one `SRCS` entry. `state_machine.h` public API unchanged.
- **`.loc-allowlist.txt` (repo root, new):** 16 entries at U1; shrinks by 1 at U3, U5, U6, U7, U8 → 11 entries at end of N6 (the 10 N7 follow-ups + none from the five flagship remain). Target: empty after N7.
- **`CLAUDE.md` / `AGENT_INSTRUCTIONS.md`:** U1 documents the gate, allowlist format, strict-shrink policy, exemption globs. U3 documents the entry_points registration procedure ("to add a subcommand: create `cli/<name>.py`, add an entry to `[project.entry-points."temper_placer.cli.subcommands"]`, run `uv sync`") and the `--help` smoke-test convention.
- **Developer workflow:** A developer who adds a new subcommand creates one module + one `pyproject.toml` entry + `uv sync`; no edit to `cli/__init__.py`. A developer who grows a file past 1000 lines sees a named `[LOC-CAP-FAIL]` message at CI. A developer who forgets the entry_points entry sees `test_all_entry_points_registered` fail naming the missing command.

---

## Risk Analysis & Mitigation

| Risk | Severity | Likelihood | Mitigation |
|------|----------|------------|------------|
| The `pipeline`/`phase` collision (inline `__init__.py:3502/3659` shadows `pipeline_commands.py:11/95`) hides subcommands (`semantic`/`topological`/`geometric`/`routing` at `pipeline_commands.py:104/133/159/192`) that are only defined in the shadowed module | High | High | U3 consolidates both into `cli/pipeline.py` and `cli/phase.py`, preserving *all* subcommands from both sources. The smoke tests (U4) verify `temper-placer pipeline --help` lists the four subcommands. If subcommands are missing after consolidation, the smoke test fails. This is the one behavior-affecting change in N6 and must be called out in the U3 PR description. |
| The 16-entry allowlist contradicts R2's "exactly five" — a reviewer rejects the plan as out of scope | High | Medium | The plan's Key Technical Decisions (Open Question 1) documents the discrepancy and the rationale (the gate is non-functional if it allows 10 over-cap files to pass unlisted). The human is asked to ratify the amendment in Open Questions below. If rejected, the fallback is a 5-entry allowlist + a separate N7 ticket for the other 10, but the gate *must* still scan all source `.py` and fail on the 10 unlisted files — meaning the 5-entry version is non-functional on `main`. |
| `entry_points` discovery requires `uv sync` after every `pyproject.toml` edit; a developer who edits `pyproject.toml` but forgets `uv sync` sees a missing command | Medium | High | The smoke test (U4) catches this in CI. Document the `uv sync` requirement in `CLAUDE.md` and in the `temper-placer --help` output if a command is missing ("did you run `uv sync`?"). |
| The `ExactGeometryRouter` class (333–3786, ~3450 lines) cannot be split under 1000 lines without breaking its internal `self`-state cohesion | High | Medium | U5 commits the seam split (geometry/dataclasses/visibility) but explicitly defers the `ExactGeometryRouter` method-level split to the Phase 3 implementer, with the gate as the forcing function. If the class cannot be split coherently, the implementer may use mixin classes (`ExactGeometryRouterRoutingMixin`, `ExactGeometryRouterGridMixin`) composed in `exact_geometry_router.py`, keeping the public class name unchanged. The mixin approach is a fallback, not the default. |
| `state_handlers.c` cannot access the static `g_state` struct without making it non-static or adding accessors | Medium | High | U8 commits the accessor approach (Option a in Approach). The accessors are mechanical (`state_machine_get_state`, `state_machine_set_state`, `state_machine_get_target_temp`, …) and the handler bodies are updated by search-and-replace of `g_state.xxx` → `state_machine_get_xxx()`. The refactor is reviewable as a diff. |
| `importlib.metadata.entry_points` API differs between Python 3.11 and 3.12 | Low | Low | `entry_points(group="...")` is the stable 3.10+ API (returns a selectable `EntryPoints` object). The repo's `requires-python = ">=3.11"` and CI uses 3.12. No risk. |
| The LOC gate's `git diff` for `NEW_ENTRY_NO_REMOVAL` requires `fetch-depth: 0` in CI | Low | Medium | The `loc-cap` job's `actions/checkout@v4` step includes `with: { fetch-depth: 0 }`. Locally, the developer must have `origin/main` fetched; document this. |
| A served module's command object is not exposed at the `module:attribute` path declared in `pyproject.toml` | Medium | Medium | The smoke test (U4) loads each entry point and verifies it attaches; a missing attribute raises `AttributeError` at `ep.load()` time, failing `test_all_entry_points_registered`. |
| Deleting `pipeline_commands.py` / `trace_commands.py` breaks a downstream importer outside `packages/temper-placer/` | Low | Low | `grep -r "pipeline_commands\|trace_commands" --include="*.py"` confirms importers are only within `packages/temper-placer/` (the cli package itself + tests). No external package imports them. |
| The 10 N7 follow-up files grow during N6's window and the gate's `ALLOWLIST_GREW` check fails on an N6-unrelated file | Medium | Medium | The gate's `ALLOWLIST_GREW` check fires on any allowlisted file that grows — including the 10 N7 entries. This is correct behavior (R3's frozen ceiling). A developer who needs to grow an N7 file must decompose it first. The N7 tickets own that work; N6 does not. |

---

## Test Strategy

- **U1 (gate):** `tools/loc_cap_check.py` is itself tested by manual injection of each violation class (see U1 test scenarios). No separate test file — the gate is the test. CI runs it on every push/PR.
- **U2 (servants):** Existing `packages/temper-placer/tests/cli/test_*.py` suite (8 files) + `tests/explainability/test_cli_commands.py` (35+ imports of `main`) must pass unchanged. No new test file for U2 — the servants are covered by the command tests that use them.
- **U3 (served extraction + dispatcher):** Same existing CLI suite + the new U4 smoke tests. The collision-resolution verification (`temper-placer pipeline --help` shows the four subcommands) is a new assertion in U4.
- **U4 (smoke tests):** `packages/temper-placer/tests/cli/test_subcommand_registration.py` — three tests per the Approach. This is the primary regression-catching mechanism for the entry_points migration.
- **U5/U6/U7 (routers):** Existing `packages/temper-placer/tests/router_v6/`, `tests/routing/`, `tests/deterministic/`, `tests/integration/test_routing_experiments.py`, `tests/performance/benchmark_suite.py` must pass unchanged. No new router test files — the existing suite is the behavior-preservation oracle (R11). If a test imports a moved internal symbol, update the import to the re-export path; the public API does not shrink.
- **U8 (firmware):** `firmware/test/test_state_machine.c` (1157 lines, exempt) + `firmware/test/test_integration.c` (1099, exempt) must pass unchanged. Firmware build (`idf.py build`) must succeed. No new firmware test file.
- **CI integration:** `loc-cap` job (U1) is new. The smoke tests (U4) run in the existing placer test step (extend `tests/core/` → `tests/core/ tests/cli/` or add a step). Router and firmware tests run in their existing steps. No new long-running CI job.
- **Regression:** No existing tests are modified except (a) `test_design_rules.py` is not touched (that was N2), (b) router tests that import a moved private symbol get an import-path update in the same changeset as the move. The CLI test suite is the regression oracle for U2/U3.

---

## Deferred to Implementation

- **`ExactGeometryRouter` method-level split (U5):** The seam split (geometry/dataclasses/visibility) is committed here; the class-internal split (by method concern, or via mixins) is the Phase 3 implementer's call, constrained by the gate.
- **`SequentialRoutingStage` method extraction (U7):** Which methods are stateless (safe to extract to `sequential_routing_helpers.py`) is determined by static analysis of `self`-usage during Phase 3. The plan commits the seam; the implementer picks the methods.
- **`CLAUDE.md` vs `AGENT_INSTRUCTIONS.md`:** Confirm which exists at implementation time; the sibling plan N2 references `CLAUDE.md`, prefer it if present.
- **`version` command registration:** Inline in dispatcher (2 lines) or via entry_points — implementation-time call; prefer entry_points for consistency.
- **`state_handlers.c` static-struct accessor set:** The exact accessor names (`state_machine_get_xxx`) are determined by enumerating `g_state` field accesses in the handler bodies during U8 implementation.

- **Firmware build command:** Confirm the exact build invocation (`idf.py build` vs a project wrapper) in `firmware/` at U8 implementation time.
- **N7 ticket creation:** The 10 follow-up tickets (`temper-N7-1` … `temper-N7-10`) referenced in the allowlist must be created as part of U1 implementation so the `ticket` fields resolve. Use `bd create "Decompose <file>" -t task -p 2 --json` per the AGENTS.md workflow.
