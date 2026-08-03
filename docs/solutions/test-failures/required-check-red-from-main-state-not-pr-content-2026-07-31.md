---
module: ci
tags: [required-checks, merge-blocker, stale-extension, attribution, board-gate]
problem_type: test_failure
date: 2026-07-31
severity: high
---

> **Status update (2026-08-03 refresh):** superseded in mechanism, not in method: the single-umbrella-check era is now run by `.github/required-checks.json` (v2) + `scripts/check_required_checks.py` with manifest-driven job triggers and fail-closed skip verification — see `docs/solutions/workflow-issues/force-push-orphans-pull-request-check-runs-2026-08-03.md` and `strict-mode-merge-ladder-playbook-2026-08-03.md`. The per-job attribution discipline here is exactly what the aggregator encodes.


# The required-check merge blocker: red from main-state, not PR content

## Problem

`main` gained branch protection with a single required check ("Required
Python Tests"). Every PR was blocked. The knee-jerk reading — "my changes
broke something" — was wrong: **none of the failures were caused by the PRs
under test.** The red came from main's own state. Attribution required
pulling per-job CI logs and comparing against a pristine-main checkout.

## The failures and their actual causes

| Failing gate | Actual cause | Resolved by |
|---|---|---|
| `Type Check` | One pre-existing mypy error in `channel_widths.py:383` — `edge_widths` keyed by untyped networkx graph nodes (`tuple[object, object]`) where the dataclass expects `((x,y),(x,y))` float keys. The gate counts per-file errors against an allowlist baseline (220); this pushed it to 221. | A `cast` documenting the runtime invariant (networkx nodes are genuinely coordinate tuples). Runtime no-op. |
| `Rust Checks` | Main's own `astar.rs` was landed with clippy errors (`approx_constant` on `SQRT_2`, `assign-op-pattern`). A Rust-only PR that touches *none* of those files still failed the gate. | The clippy cleanup PR fixed `astar.rs`; rebased PRs then pass. |
| `Board & Netlist Gates` | The documented hardware gate — isolation-barrier keepout zones are missing from `pcb/temper.kicad_pcb` (AGENTS.md: "the fix is hardware work"). Red on main by design. | Hardware work, or a gate exception. Cannot be fixed from CI. |
| `Repo Hygiene`, `Provenance & Anti-Vacuity`, `Requirements`, `LOC Cap`, `Generated Repo State` | Nothing in the logs tied these to Rust-only PR content; consistent with main-state. | Cleared as the code-fixable gates above landed. |

Also misleading: the unconnected-items regression test (`test_production_board_
routing_drc_regression`) had drifted 405→407→408→411; PR #540 had already
rebaselined it on main, so no baseline change was needed from this session.

## The attribution methodology

1. **List the failing jobs**, not the aggregate check. The required check
   ("Required Python Tests") is an umbrella; its job list is the ground truth.
2. **Pull each failing job's log and read the actual error**, not the summary
   line. The summary ("has 1 errors (not in allowlist)") hid the specific
   mypy diagnostic; the log revealed the file:line.
3. **Run the failing gate command locally** on a main-based checkout. The
   gate scripts (`scripts/check_typecheck_gate.py`) run real tools (mypy,
   not pyright) — reading the script's `subprocess.run` revealed the exact
   invocation.
4. **Compare against pristine main.** A PR that touches Rust cannot cause a
   mypy error in a Python file it never touched; a PR touching one EMC rule
   cannot cause `approx_constant` in `astar.rs`. The parsimonious
   explanation is main-state until proven otherwise.

## A compounding trap: the stale-extension false failure

The same week, 60 Python tests failed with `AttributeError: module
'temper_geometry' has no attribute 'bbox_from_center_py'` — a function the
source clearly contains. Cause: the installed `temper_geometry.so` had been
reverted to a Jul-15 build by a concurrent session's `uv sync` clobbering
the shared `.venv`. Rebuilding the extension made all 60 pass. Rule: **when
Python tests fail on a pyo3 extension crate, check the installed `.so`
mtime before blaming the code** — the shared-venv clobber is a documented,
recurring failure mode (`shared-mutable-state-dominant-cost-multi-agent-repo-2026-07-28.md`).

## Prevention

- Diagnose against pristine main before assuming PR-caused breakage.
- Read the gate script to learn the real tool and invocation.
- Rebuild the extension (and check its mtime) before attributing Python-test
  failures to source changes.
- Separate the code-fixable main-state blockers (mypy baseline, astar clippy)
  from the hardware gate; a red hardware gate is a repo-owner decision, not a
  CI fix.
