<!-- provenance: commit=caa492f257d760dd3baffaf9d5a2bddbef94e0d6 dirty=false -->

# Board regeneration: measured per-run cost, and the blocker that stops the producer

**Date:** 2026-08-04

**Task:** Phase 0 / R3 of
`docs/plans/2026-08-03-002-feat-wasm-verification-tier-plan.md`. The
board-regeneration proposal
(`docs/plans/2026-08-04-001-feat-board-regeneration-proposal.md` Sec 5)
recommends a nightly CI-artifact producer over the **deterministic subset**
— netlist -> route -> DRC, run against the currently-committed placement —
and states that the per-run cost "is unmeasured in this investigation and
should be Phase 0's first task before committing to a cadence." This
document is that measurement.

**Scope of writes:** this task wrote **no** tracked file except this
document. `pcb/temper.kicad_pcb`, `power_pcb_dataset/drc_ceiling.json`, and
every workflow file are untouched; `git status` was verified clean after
every measurement below. No `Ceiling-Approval:` trailer was authored.

---

## Headline

**The recommended producer cannot be built today, because its middle stage
does not execute.** Routing the production board fails at import or at
runtime on `origin/main` through every available entry point:

| Entry point | State on `caa492f25` | Cause |
|---|---|---|
| `make route` | **Broken** | Targets a 33-component fixture, not the production board; and `scripts/internal_route.py` cannot be imported at all |
| `scripts/internal_route.py` | **Broken (import)** | Imports `temper_placer.io.trace_writer`, deleted 2026-07-10 in `6d9e24db7`; also imports undeclared `jax` |
| `scripts/route_board.py` | **Broken (runtime)** | `AttributeError: 'NetClassRules' object has no attribute 'via_diameter_mm'` |
| `route_pcb()` direct (the CI-gate call path) | **Broken (runtime)** | same `AttributeError`, in 1.25 s |

The two stages that *do* work are cheap — far cheaper than the proposal
assumed. Netlist is ~11.5 s. A full 120-sample DRC pass is **~7 minutes**,
not the ~2 hours implied by treating `_drc_api.py`'s 60 s subprocess timeout
as a per-run cost. **Cost is not what blocks R3. A broken router is.**

Because the router does not run, the determinism premise the proposal rests
on (`docs/evidence/2026-07-27-router-determinism.md`: route output
byte-identical across fresh processes) **could not be re-verified at all** —
neither confirmed nor refuted. A producer built on it today would be built
on an unchecked assumption.

---

## Machine and tool context

| Field | Value |
|---|---|
| Machine | Apple M2 Pro, 12 cores, 32 GB RAM |
| OS | macOS 26.5.1 (build 25F80), arm64 |
| Commit | `caa492f257d760dd3baffaf9d5a2bddbef94e0d6` (= `origin/main` at time of measurement), clean worktree |
| Worktree | `.claude/worktrees/agent-a6a1256ea385fa0b4`, own `.venv` via `uv sync --all-packages` |
| `kicad-cli` | 10.0.4 |
| Python | 3.12 (uv-managed venv) |
| Board under test | `pcb/temper.kicad_pcb`, sha256 `51e39844b18aa37c84e4cc0b011acc51dc24cb1282359e1334ecbdf6ed07d9af` |

The venv is this worktree's own, built from this commit — deliberately not
the shared root checkout's `.venv`, which sits on a dirty feature branch
whose modified Rust sources would have made every extension-backed
measurement below unattributable.

---

## 1. `make netlist` — WORKS, ~11.5 s

Four consecutive `make netlist` invocations (first is a cold run):

| Run | Wall |
|---|---:|
| 1 (cold) | 12.93 s |
| 2 | 11.47 s |
| 3 | 11.44 s |
| 4 | 11.40 s |

**Median 11.46 s, range 11.40–12.93 s (N=4).** Warm-run spread is 0.07 s.
Exits 0, 76 assertions pass, and stamps `elec/build/default.net` via
`scripts/write_build_stamp.py`. Output lands under `elec/build/`, which is
gitignored (`.gitignore:7` `build/`) — `git status` stayed clean.

CI already content-hash-caches this step
(`.github/workflows/python-tests.yml:527-537`), so its marginal cost in a
nightly producer is at or below this figure.

## 2. `make route` — BROKEN, cost unmeasurable

### 2a. `make route` does not target the production board

`Makefile:82` sets `PCB_FILE = pcb/benchmarks/temper_fixture_33.kicad_pcb`,
with a comment marking it interim until "the real production board is
generated from schematics." So even if the script worked, `make route`
routes a 33-component fixture (107,898 bytes), not
`pcb/temper.kicad_pcb` (1,032,079 bytes). The proposal's "run against the
currently-committed placement" is not what this target does.

### 2b. `scripts/internal_route.py` cannot be imported

Two independent import-time failures, both on `origin/main`:

```
ModuleNotFoundError: No module named 'jax'                          # line 13
ModuleNotFoundError: No module named 'temper_placer.io.trace_writer' # line 16
```

- **`jax` is an undeclared dependency.** It appears in **no**
  `pyproject.toml` and **nowhere in `uv.lock`** (verified by exhaustive
  grep), yet appears in 11 import statements across 9 files under
  `scripts/`, `packages/temper-placer/` and `packages/temper-workflow/`.
  A clean
  `uv sync --all-packages` cannot satisfy it, so this fails on any fresh
  runner. Ironically, commit `3314d94a5` is titled "Major Cleanup: JAX
  Removal…".
- **`temper_placer.io.trace_writer` no longer exists.** Deleted
  **2026-07-10** in `6d9e24db7 "chore: remove dead post-retirement
  stragglers"` — classified as dead code while `internal_route.py` still
  imports `write_traces_to_pcb` from it. `make route` has therefore been
  broken for **3+ weeks**.

Nothing in `.github/workflows/` invokes `internal_route.py`, which is why
no CI signal ever fired on this.

### 2c. The live API is also broken on the production board

`scripts/route_board.py` is the repo's own documented working entry point;
its module docstring already records 2b independently ("`internal_route.py`
imports the superseded `temper_placer.routing.*` tree plus an undeclared
`jax` dependency and cannot be imported at all"). It calls
`temper_placer.router_v6.adapter.route_pcb`, the same call the committed
route came from.

It fails on the production board:

```
File ".../router_v6/_pipeline_core.py", line 332, in run
  vias = generate_escape_vias(dense_pkg, pcb.design_rules, strategy="dog-bone")
File ".../router_v6/escape_via_generator.py", line 86, in generate_escape_vias
  via_diameter = rules.via_diameter_mm
AttributeError: 'NetClassRules' object has no attribute 'via_diameter_mm'.
Did you mean: 'via_diameter'?
```

**This is a genuine source-level mismatch, not a stale build.**
`escape_via_generator.py:86-88` reads `.via_diameter_mm`, `.via_drill_mm`
and `.clearance_mm` from the object returned by
`DesignRules.get_rules_for_net()`. That object is
`temper_placer.core.netclass_rules_gen.NetClassRules`, a **generated**
pydantic model whose fields are `via_diameter`, `via_drill` and
`clearance` — no `_mm` suffixes, confirmed by reading the model definition
(`netclass_rules_gen.py:19-60`), not only by attribute probing.

Dating the mismatch:

- `escape_via_generator.py` has read the `_mm` names since **2026-01-10**
  (`4214e6046`, Router V6 Stage 1.3).
- `netclass_rules_gen.py` was last regenerated **2026-07-23** in
  `5a17025b1 "fix: batch CI fixes — ruff, codegen, Docker pre-compile"`,
  which is also the commit that last touched the
  `generate_escape_vias(dense_pkg, …)` call site.

Note this is a *different* defect from `28dc960de` (#666, 2026-08-03),
which added `_mm` aliases to the **Rust `DesignRules` pyclass**. Those
aliases are on the wrong class — the crash is on the per-net
`NetClassRules` pydantic model, which #666 did not touch. Copper stripping
is irrelevant: the failure reproduces identically with and without
`strip_existing_copper`.

### 2d. Why CI has not caught it

The gate that covers exactly this path,
`test_production_board_routing_drc_regression`, **fails on `origin/main`**:

```
$ .venv/bin/python3 -m pytest \
    packages/temper-placer/tests/placer/cp_sat/test_regression_drc.py::test_production_board_routing_drc_regression -x -q
FAILED  ...::test_production_board_routing_drc_regression
1 failed in 1.25s
```

It runs in `python-tests.yml` under
**`continue-on-error: true`** (line 2073, `# TODO: temper-NNN -- parallel
test suite flakiness; hard-fail after 2026-09-01`), so its failure is
masked and never blocks a merge. Combined with `AGENTS.md`'s record that
`main` has no branch-protection required checks, a red router gate produces
no enforcement anywhere.

**Consequence for R3:** the route stage's wall time is **not measured and
not measurable** at this commit. Any cadence decision that depends on it is
unsupported.

## 3. DRC — WORKS, and is an order of magnitude cheaper than assumed

### 3a. The invocation has to include the DRU regeneration

A first pilot run with a bare
`kicad-cli pcb drc --all-track-errors` produced categories that did not
match `power_pcb_dataset/drc_ceiling.json` at all (no `creepage`, no
`track_width`; `clearance` read 499–503 instead of 377–378).

Cause: `pcb/temper.kicad_dru` is **neither tracked nor present** — it is
gitignored (`.gitignore:58` `/pcb/*.kicad_dru`) and generated from
`scripts/generate_kicad_dru.py` (SSOT). `scripts/ci_check_drc.py`
regenerates it unconditionally before measuring, precisely so that DRC does
not depend on ambient local state. Every figure in 3b below was taken
**after** that regeneration.

This is a real trap for any future producer: the same board plus a missing
DRU yields a different, wrong, self-consistent-looking answer.

### 3b. 120-sample measurement (full protocol, not extrapolated)

`AGENTS.md:56-71` requires 120 samples and the observed range, not a point
value. A pilot of N=11 gave a 3.42 s median, extrapolating to ~6.8 min for
120 — cheap enough that the full protocol run was done rather than
extrapolated. **The numbers below are measured at N=120.**

Invocation: `kicad-cli pcb drc --all-track-errors --format json --output
<tmp> pcb/temper.kicad_pcb`, 120 sequential fresh subprocesses, after the
DRU regeneration in 3a.

**Wall time: median 3.46 s, range 3.19–5.84 s. Total for the full
120-sample pass: 417.9 s = 6.97 min.**

Errors (`severity=error`, the ceiling's `violations_by_type`):

| Category | Median | Range (N=120) |
|---|---:|---|
| `annular_width` | 4 | 4–4 |
| `clearance` | 378 | **377–378** |
| `copper_edge_clearance` | 12 | 12–12 |
| `courtyards_overlap` | 11 | 11–11 |
| `creepage` | 186 | **185–187** |
| `drill_out_of_range` | 4 | 4–4 |
| `hole_clearance` | 105 | 105–105 |
| `hole_to_hole` | 3 | 3–3 |
| `shorting_items` | 199 | **199–200** |
| `solder_mask_bridge` | 154 | 154–154 |
| `track_width` | 199 | 199–199 |
| `tracks_crossing` | 3 | 3–3 |
| `via_diameter` | 4 | 4–4 |
| **error total** | **1262** | **1261–1263** |

Warnings (`severity=warning`, the ceiling's `warnings_by_type`) — **every
category deterministic at N=120**: `lib_footprint_issues` 11,
`lib_footprint_mismatch` 23, `missing_courtyard` 5, `pth_inside_courtyard`
1, `silk_edge_clearance` 1, `silk_over_copper` 172, `silk_overlap` 199,
`track_dangling` 45, `via_dangling` 15. Total 472, invariant across all 120
runs.

`unconnected_items` totalled 428 in all 120 runs, with zero variance.

Only three of 22 categories vary at all, and each by a span of 1–2.

### 3c. This independently reproduces the committed ceiling

Every category matches `power_pcb_dataset/drc_ceiling.json`'s recorded
measurement — taken on a different machine, at a different commit
(`3410ee4e1…`, branch `feat/k3-swap-and-board-write`), against the same
board hash:

| Category | Ceiling's recorded `observed` | Measured here (N=120) | Ceiling |
|---|---|---|---|
| `clearance` | 377–378 | **377–378** | 379 |
| `creepage` | 185–187 | **185–187** | 188 |
| `shorting_items` | 199–200 | **199–200** | 201 |

All other error categories and all nine warning categories reproduced
**exactly**, deterministically. This is a clean cross-machine confirmation
of the ceiling file and of `--all-track-errors`' determinism claim, and it
is the one part of the deterministic subset that is genuinely ready to feed
the WASM tier.

**One honest caveat on the `_drc_api.py` claim.** Its comment states that
with `--all-track-errors`, "`clearance` varies by at most 1." At N=120 that
held exactly: `clearance` spanned 377–378, a range of 1. `creepage` spans 3
distinct values (185–187), which the ceiling file itself already records;
the `_drc_api.py` comment predates the creepage category and should not be
read as covering it.

### 3d. Cost summary for the DRC stage

| Quantity | Value |
|---|---|
| Per-run wall (N=120) | median 3.46 s, range 3.19–5.84 s |
| Full 120-sample serial pass | **417.9 s = 6.97 min** (measured, not extrapolated) |
| `_drc_api.py` subprocess timeout | 60 s — never approached; max observed 5.84 s, a 10x margin |

The proposal's worry that a real 120-sample pass might be expensive is
**not supported**: it is a single-digit-minutes job. Serial is fine; no
sharding needed.

---

## 4. What this means for R3

**Total measurable cost of the deterministic subset today: 11.46 s
(netlist) + 417.9 s (120-sample DRC) ≈ 7.2 min of runner time, plus an
unmeasurable route stage.**

If the router worked and cost even 5–10 minutes (the committed route is a
single SAT solve over a fixed placement), the whole producer would land
comfortably inside a 30-minute nightly job — cheaper than
`corpus-batch.yml`'s 180-minute budget and comparable to
`r9-evidence.yml`'s 30. **Affordability was never the obstacle.**

The obstacle is that R3's premise — "the tier has an input that changes
when the harness changes" — currently has:

1. **No working route stage.** Three entry points, three different
   failures, the covering CI gate masked by `continue-on-error`.
2. **No verifiable determinism.** `docs/evidence/2026-07-27-router-determinism.md`'s
   byte-identical result could not be re-checked, because the router does
   not run. Its own `UNVERIFIED` section (the committed board's 53.1%
   completion never reproduced across 17 runs, every run giving 37.5%)
   therefore also remains open, and is now un-investigable at this commit.
3. **A scope gap that predates all of this.** Even a fully working
   deterministic subset would not satisfy R3's literal text. `make build`
   contains **no placement step** (`Makefile:41` and the stub `footprints`
   target at `Makefile:61-66`), and every recent
   change to `pcb/temper.kicad_pcb` (`de59c0458`, `0f0a13412`,
   `55226f8ad`, `27ea686c5`) came from a human-gated CP-SAT placement
   re-solve with candidate selection. The harness that actually changes the
   board is the placement harness, and it is deliberately not automatable
   (`docs/evidence/2026-08-01-ortools-cpsat-spike.md:171-185`: CP-SAT is
   bit-identical only when it terminates without hitting its timeout).

**No producer workflow was built.** Building one now would mean shipping a
nightly job whose central stage is a known, dated, unfixed crash — the
"gate that cannot bite" failure class `scripts/check_vacuous_gates.py`
exists to prevent, and which the WASM plan's own D6/R8 name as the largest
risk the tier faces.

## 5. What would unblock it

In dependency order:

1. **Fix the `NetClassRules` `_mm` mismatch** (Sec 2c) — three attribute
   reads in `escape_via_generator.py`, or three field aliases on the
   generated model. This looks small; it is not in this task's scope, and
   it should land with a test that is *not* `continue-on-error`.
2. **Un-mask `test_production_board_routing_drc_regression`**, or the same
   class of breakage recurs silently.
3. **Declare `jax`**, or remove the last import of it from any path a
   producer needs (`scripts/route_board.py` does not need it;
   `internal_route.py` does).
4. **Decide `internal_route.py`'s fate** — repair it, or delete it and
   re-point `make route` at `scripts/route_board.py` with `PCB_FILE`
   defaulting to the production board.
5. **Re-run the determinism protocol** once routing works, and only then
   set a cadence. The numbers in Sec 1 and 3 stand and will not need
   re-taking.

## UNVERIFIED

- **Route wall time on the production board.** Not measured; the router
  does not execute at this commit. Every cost statement about the route
  stage in this document is explicitly absent, not estimated.
- **Whether route output is still byte-identical across fresh processes.**
  Could not be re-checked (same cause). `docs/evidence/2026-07-27-router-determinism.md`'s
  claim is neither confirmed nor refuted here.
- **Whether the fix in Sec 5.1 is as small as it appears.** The mismatch
  was diagnosed by reading the model definition and the failing call site;
  no fix was attempted, so downstream consequences of routing actually
  proceeding past `generate_escape_vias` are unknown. There may be further
  breakage behind this one.
- **CI-runner cost.** All timings are on an M2 Pro. GitHub's
  `ubuntu-latest` is slower; the netlist and DRC figures should be treated
  as lower bounds, not as the CI budget.
- **`make schematics` and `make footprints`.** Not measured. `footprints`
  is a documented stub (`Makefile:61-66`); `schematics` was out of the
  proposal's deterministic subset.

## Reproduction

```bash
# Netlist
make netlist

# DRC, faithful invocation (DRU regeneration is mandatory — see Sec 3a)
python3 -c "
import sys, pathlib
sys.path.insert(0, 'scripts')
sys.path.insert(0, 'packages/temper-placer/src')
import generate_kicad_dru as g
g.OUTPUT_PATH.write_text(g.generate_dru(), encoding='utf-8')
"
kicad-cli pcb drc --all-track-errors --format json \
  --output /tmp/drc.json pcb/temper.kicad_pcb

# Route — reproduces the failure in Sec 2c
uv run python3 scripts/route_board.py --output /tmp/routed.kicad_pcb
```

## Sources

- `docs/plans/2026-08-04-001-feat-board-regeneration-proposal.md` — Sec 5,
  the recommendation this measurement was to cost.
- `docs/plans/2026-08-03-002-feat-wasm-verification-tier-plan.md` — R3, R6,
  D3, Phase 0.
- `AGENTS.md:45-97` — the 120-sample re-measurement protocol and the
  no-branch-protection record.
- `packages/temper-placer/src/temper_placer/validation/_drc_api.py:305-320`
  — `--all-track-errors` as the determinism fix.
- `scripts/ci_check_drc.py:28-56` — why the `.kicad_dru` must be
  regenerated before measuring.
- `scripts/route_board.py` — the working `route_pcb()` entry point, and its
  docstring's independent record of `internal_route.py`'s breakage.
- `power_pcb_dataset/drc_ceiling.json` — read only; never written by this
  task.
