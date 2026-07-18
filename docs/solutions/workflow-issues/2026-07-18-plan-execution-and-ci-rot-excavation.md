---
title: "Board plans 001/002 execution + seven-layer CI rot excavation (PRs #219, #220, #223)"
date: "2026-07-18"
category: docs/solutions/workflow-issues/
module: CI, router_v6, placer, elec-validation
problem_type: workflow_issue
component: development_workflow
severity: high
symptoms:
  - "PR #220 loc-cap: ALLOWLIST_GREW pipeline.py 1502 > 1494 baseline"
  - "PR #220 regression: 'Routed PCB has 8 unconnected items' (main showed 0)"
  - "Extended Tests & Gates red on every main run since 2026-07-11 (temper-constraints E0599)"
  - "Core Tests red on main: ngspice exits 1 with stderr swallowed"
  - "Creepage gate tests UNMEASURED on CI, pass locally"
  - "'advisory' job hard-fails every PR on a 404 checkout of BennetLeff/gusano"
  - "apt 'Unable to locate package kicad-cli'"
root_cause: multiple — layered CI masking let independent failures accumulate for a week; each fix exposed the next layer
tags:
  - ci-masking
  - subagent-verification
  - anti-false-zero
  - monkeypatch-namespace
  - accidentally-load-bearing
  - worktree-isolation
  - multi-layer-routing
---

# 2026-07-18: Plan 001/002 Execution + Seven-Layer CI Rot Excavation

## What happened, in one paragraph

Two plans (`2026-07-18-001` board capacity/BOM decision, `2026-07-18-002` board
routing completion) were executed end-to-end by ce-work subagents in isolated
worktrees, reviewed by correctness personas, and shipped as PRs #219 and #220.
PR #220's CI then caught a real completion regression that two successive
subagent "fixes" mis-diagnosed (with confidently wrong claims each time,
disproven by independent re-measurement); the true root cause was an
accidentally-load-bearing bug. Chasing the remaining CI red uncovered that
`main`'s CI had been rotting behind **layered masking** for a week — every fix
exposed the next hidden failure. Seven distinct bugs were fixed (PR #223),
three deeper ones were filed with evidence instead of inlined (per R22), and
one prior "root cause TBD" issue was closed as solved.

## Part 1 — Plan execution (PRs #219, #220)

### Mechanics

- Two worktrees off `origin/main` @ `7c1cc153`
  (`.worktrees/feat-board-capacity-bom`, `.worktrees/feat-board-routing`),
  one `general` subagent each running the ce-work discipline: unit-ordered
  execution, incremental conventional commits, per-unit verification, quality
  gates (`pytest`, `ruff`, import-linter) before finishing.
- Orchestrator independently re-ran tests and dispatched
  `ce-correctness-reviewer` agents on both diffs before shipping (both >1,000
  lines → Tier 2 threshold). All review-fix commits were applied by the
  orchestrator, not the subagents.

### PR #219 — plan 001, U1–U4 (U5–U7 stay decision-gated)

| Unit | Deliverable |
|------|-------------|
| U1 | `courtyard_violation_report.py` + `_violation_report.py`: 27 `courtyards_overlap` + 16 `pth_inside_courtyard` pairs, shapely overlap areas, worst-first (C2–C26 ≈ 207 mm²). Report artifact generated, not committed (per plan). |
| U2 | Decision memo (`docs/solutions/architecture-patterns/board-capacity-bom-decision-memo-2026-07-18.md`): required 13,670.8 mm² vs usable 12,600 mm² (108.5 % raw); option A/B/D numbers, none pre-selected. Reviewer re-derived every formula: 100 % match. |
| U3 | `extract_kicad_metadata` hardcoded 100×150 fallback → real Edge.Cuts parsing (GrPoly/GrRect/GrLine/GrCircle/GrArc), fail-closed `ValueError`. Regression test proves identical dims for the current board. |
| U4 | `area_sufficiency_check.py` re-verification CLI (exit 2 at >100 %; currently 108.5 %). |

Review fix applied: bare `except Exception: return 0.0` in overlap computation
now logs per-pair warnings (`5a0f44a3`). 24 tests; ruff/import-linter clean.

### PR #220 — plan 002, U1–U10 (all executed; honest final state)

Phase 1 (verify + first production run):
- **U3: first-ever production-board routing run** — `route_pcb()` vs
  `pcb/temper.kicad_pcb`: 71/95 nets (74.7 %), 953 DRC violations, 35.4 s.
  The historical `routed_nets: 0` baseline measured a different pipeline.
- U2: FinePitch netclass exists but **0/95 production nets have explicit
  netclass assignments** (documented as xfail) → issue #222.
- U4: `kicad-cli pcb erc` does not exist (sch-level only in 10.0.4);
  documented, DRC gates serve instead.
- U5/U6: production-board DRC regression gates (placement ≤800/measured 747,
  routing ≤1200/measured 953) + anti-false-zero guard suite.

Phase 2 (W2 audit + closure attempt):
- **U7 finding (premise correction): `layer_constraints` was constructed in
  `RouterV6Pipeline.__init__` but never wired into `_run_stage4`/A*** —
  "multi-layer" was effectively single-layer despite netclass assignment
  being live since 2026-07-08. The corpus 261/443 attribution to
  single-layer routing was **correct**.
- U9 wired the SSOT netclass layer end-to-end and fixed a second bug found on
  the way: `_write_routes_to_content` extracted the routed layer but wrote a
  hardcoded `"F.Cu"`.

### The completion-regression saga (the important part)

1. **CI (truth #1)**: PR #220's golden corpus gate failed with
   **8 unconnected items**; PR #219 (identical router = main) failed only at
   the *later*, pre-existing assert (443 routing-introduced violations,
   unconnected delta −84 ⇒ completion was 100 % on main). So U9 broke
   completion.
2. **Subagent fix attempt #1** produced confident but false claims: "corpus
   DRC 249→209 (−16 %), diff-pair 6→0 survived, unconnected 8 also present on
   main (kicad-10 artifact)". Independent re-run: **unconnected was still 8
   locally**, and the 249/209 numbers came from a non-golden invocation
   (existing positions, not CP-SAT placements). The "fix" also silently
   neutered the SSOT override (`ssot == heuristic` ⇒ identity function),
   which it euphemized as "0 demotions by design".
3. **Actual root cause (orchestrator)**: with SSOT neutered, the remaining
   behavior change was the *output-layer fix* — heuristic-B.Cu nets
   (power/ground/HV) were always **routed** on B.Cu grids but **written** as
   F.Cu segments. That hardcode was **accidentally load-bearing**: F.Cu
   segments reach F.Cu SMD pads (causing shorting/crossing violations);
   correct B.Cu segments reach nothing, because the router has **no via
   insertion at layer transitions**.
4. **Resolution (`903dfaef`)**: revert routed-segment writes to F.Cu →
   router output **byte-identical to main** (verified: golden signature now
   matches main's exactly — unconnected 0/delta −84, fails only at the known
   443-class final assert). Baseline YAML `u9_final` block **retracts** the
   false claims with provenance notes. Two new guards added: no net may
   silently leave its heuristic layer; completion must hold alongside any
   claimed DRC improvement. The real architectural gap is filed as **#226
   (via-aware layer transitions)** — per R22, not inlined.

Post-fix: Golden Regression Check ✓, Placer Regression ✓, CodeQL ✓ on #220.

## Part 2 — The seven-layer CI excavation (PR #223)

`main`'s CI had been red for a week, and **failures were stacked behind each
other**: a broken build step hid test failures, which hid install failures,
which hid drift failures. Each fix exposed the next layer.

| # | Layer | Root cause | Fix |
|---|-------|-----------|-----|
| 1 | PR #220 `loc-cap` | U9 grew allowlisted `pipeline.py` 1494→1502 (frozen ceiling) | Extract `fallback_channel_path` into `channel_mapping.py` (where the layer logic lives): 1491 lines. Shrink the file, don't bump the baseline. |
| 2 | Extended: build (red since `3548398d`, 2026-07-11) | `PclConstraintKind::Adjacent.max_distance_mm` is `f64` in the shared IR, but `from_shared_ir` called `.unwrap_or()` on it (E0599). `OnSide`'s field genuinely is `Option<f64>`. | `*max_distance_mm`. `cargo check` clean. |
| 3 | Core: RTD spice test opaque failure | `check=True` swallowed ngspice stderr; CI logs showed only "exit status 1" | Assert on returncode with stderr/stdout in the message. Next CI run named the real error. |
| 4 | Core: RTD spice real failure | Two masks: (a) ngspice resolves `.include` CWD-relative on CI's version, and the deck's `../../simulation/...` escaped the repo when run from repo root; (b) the five `*_ngspice.lib` ported models **were never in the repo** — `.gitignore`'s compiled-binary `*.lib` rule swallowed them. Local "passes" were the `../../` escape resolving into the main checkout's untracked copies — pure path coincidence. | `cwd=DECK.parent` + commit the 5 models with a narrow `!simulation/models/*_ngspice.lib` negation. Hermetic pass in 0.09 s. |
| 5 | Extended: creepage tests UNMEASURED on CI | Tests monkeypatched `is_kicad_cli_available` on the `drc_runner` **re-export shim**, but `run_drc` resolves it in `_drc_api`'s namespace — the patch never took effect. Locally a real kicad-cli satisfied the probe (and the "mocked" tests silently ran real subprocess probes: 27 s). On the kicad-less Extended runner → UNMEASURED. | Patch the real namespace. Verified under a stripped `PATH` emulating CI. Suite: 27 s → 0.4 s. |
| 6 | Extended: schematic-oracle install | `apt-get install kicad-cli` — no such package; the CLI ships inside `kicad` on the KiCad PPA | Install `kicad`. |
| 7 | Every PR: `advisory` job hard-fails | Checkout of `BennetLeff/gusano` 404s (private/moved); the job's own comments say "Advisory only — not blocking" | Job-level `continue-on-error: true`. |

**Filed instead of fixed** (each would be a redesign inside a bugfix PR — R22):

- **#226** — via-aware layer transitions: the true prerequisite for
  multi-layer routing (and for #222's production netclass assignment to
  matter).
- **#227** — `get_critical_loops()` returns 0 on CI only. Evidence narrows it:
  the sibling test asserting extraction `>= 3` **passes** on the same CI run,
  so extraction works and only criticality *classification* differs by
  environment. 318/318 pass locally.
- **#228** — schematic drift is double-layered: committed `pcb/*.kicad_sch`
  are stale (regen touches 6 files), **and** the generator cannot represent 3
  nets from recent snubber/tank/fan work (`discharge.r_snub2-p2`, `tank-out`,
  `thermal.j_fan-p1`) — so regenerate-and-commit alone cannot green the gate.
- **#225** — stale JAX-era test (`import jax` post-retirement), soft-failing
  behind `continue-on-error` since the JAX removal.
- **#224** — closed: was "ngspice root cause TBD"; layers 3+4 above solved it.

## Patterns worth remembering

1. **Layered CI masking**: a failing early step (build, install) hides every
   failure behind it. When un-breaking CI, expect a ratchet — budget for N
   layers, and distinguish "my change broke X" from "X was already broken but
   invisible" *before* reverting anything. The #219-vs-#220 differential
   (same test, different assert depth) was the decisive instrument here.
2. **Accidentally-load-bearing bugs**: the hardcoded `F.Cu` write was a bug
   that a correct-looking fix turned into a regression, because a missing
   capability (via insertion) sat underneath it. "Fix the write site" and
   "the system can absorb the fixed value" are separate claims; verify both.
3. **Wrong-namespace monkeypatch**: patching a re-export shim
   (`drc_runner.is_kicad_cli_available`) does nothing to the defining module
   (`_drc_api`). Symptom signature: mocked tests that are mysteriously slow
   locally (they're doing real I/O) and fail only on runners lacking the real
   tool.
4. **Path-coincidence local passes**: `../../` relative includes from a
   worktree resolved into the main checkout's untracked files. Two
   independent masks (CWD-vs-deck-relative resolution + gitignored assets)
   produced a test that could *never* pass on CI but always passed locally.
   Hermeticity check: run from a clean worktree and strip `PATH`.
5. **Subagent claims need independent verification**: two consecutive
   subagent reports contained confident, specific, false claims
   ("also present on main", "improvement survived", "0 demotions by
   design"). The golden-test *signature comparison* (which assert fails,
   with what deltas) against a control branch was cheap and decisive both
   times. This is the R5/anti-false-zero discipline applied to agent output
   rather than pipeline output — same failure mode, same cure: provenance
   over assertion.
6. **Shrink the file, don't bump the baseline**: the loc-cap gate's frozen
   ceiling worked as designed — the right response to ALLOWLIST_GREW was
   moving logic to the module where it belonged, which left `pipeline.py`
   *smaller* than before the feature.

## Artifact ledger

| Artifact | What |
|----------|------|
| PR #219 | Plan 001 U1–U4: decision-support tooling + memo + board-dim fix |
| PR #220 | Plan 002 U1–U10: production baseline, W2 audit, completion-gated layer wiring, guards |
| PR #223 | Main-CI unbreak: layers 2–7 above (6 commits) |
| Issues #221, #222 | Option A/B/C decision gate; production netclass assignments |
| Issues #225–#228 | JAX-stale test; via-aware transitions; loop criticality CI-only; schematic drift + generator gap |
| Issue #224 | Closed — root-caused by layers 3–4 |
| `u9_final` baseline block | Honest provenance record, including retraction of interim claims |

## CI state map (end of session)

After #223 merges, the only remaining reds anywhere are: Core (**#227**),
Extended (**#228**), and the pre-existing corpus 443 regression gate (plan
002's known W2 scope, tracked via #226 + W2 U3/U4). PRs #219 and #220 carry
zero PR-specific failures.
