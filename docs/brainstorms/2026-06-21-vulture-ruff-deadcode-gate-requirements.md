---
date: 2026-06-21
topic: vulture-ruff-deadcode-gate
---

# Vulture + Ruff F401/F841 CI Gate with Baseline Allowlist

## Summary

A lightweight CI gate that makes dead code a build failure instead of a slow accumulation. Vulture (whole-program AST reachability, `--min-confidence 80`) scans `packages/` on every push; any unreachable function/method/class not listed in a committed `deadcode-baseline.txt` fails CI. Ruff `F401`/`F841` (already enabled in `pyproject.toml` and already running in `.github/workflows/python-tests.yml`) continue to catch file-local unused imports and locals. The baseline freezes the existing dead-code debt; new debt is blocked at the gate, and each baseline entry is ticketed for removal. Composes with the N3 coverage gate (dynamic) and the N7 parity test as the static reachability layer of the safety net.

---

## Problem Frame

The June 2026 clean-base sprint surfaced the recurring failure mode: code that exists, compiles, imports, and never runs. A DRC check implemented but never wired into the CLI's hardcoded list; a debug `print()` in a class body; a `design_rules.py` path duplicated outside the `src/` layout; a `.pyx` twin of a pure-Python module. None of these are caught by tests (the code is unreachable, so tests don't exercise it) or by ruff `F401`/`F841` (which are file-local: unused imports and unused locals, not unreachable functions or classes). They are found only when a human opens the file.

The structural defense missing is **whole-program reachability analysis**: a tool that knows `foo()` is never called from any entry point, anywhere in `packages/`. Vulture provides this via AST traversal with confidence tiers; ruff does not. The boy-scout rule ("leave the campsite cleaner than you found it") has no mechanical enforcement today — dead code accrues because removing it is optional and adding it is unblocked.

This gate does not remove existing dead code. It freezes the current debt into a baseline allowlist and makes *new* dead code a CI failure. Baseline entries are individually ticketed and removed over time; the allowlist only ever shrinks.

---

## Actors

- A1. **Developer** — adds a helper function, refactors a module, leaves an old entry point in place. Primary source of new dead code.
- A2. **CI pipeline** — runs ruff (`ruff check packages/`, already present) and a new Vulture step on every push and pull request. The enforcement layer.
- A3. **Baseline maintainer** — triages `deadcode-baseline.txt`, files removal tickets, shrinks the allowlist. Initially the developer who lands the gate.

---

## Key Flows

- F1. **Developer introduces new dead code**
  - **Trigger:** A1 adds a function that is never called from any `packages/` entry point, or removes the last caller of an existing function without removing the function.
  - **Actors:** A1, A2
  - **Steps:** (1) A1 pushes the change. (2) A2 runs ruff (unchanged) — `F401`/`F841` catch file-local unused imports/locals as today. (3) A2 runs Vulture `--min-confidence 80` over `packages/`. (4) Vulture reports the new unreachable symbol at confidence ≥80; it is not in `deadcode-baseline.txt`. (5) A2 fails the job with Vulture's message naming the file, line, and symbol.
  - **Outcome:** The push is blocked. A1 either removes the dead code, wires it to a caller, or (justified case) adds it to the baseline with a removal ticket.
  - **Covered by:** R1, R3, R4

- F2. **Developer touches code near a baseline entry**
  - **Trigger:** A1 edits a module that contains a symbol listed in `deadcode-baseline.txt`.
  - **Actors:** A1, A2, A3
  - **Steps:** (1) A1 refactors around the baseline entry without removing it. (2) A2 runs Vulture; the entry is still in the baseline, so CI passes. (3) If A1 *removes* the dead symbol, the next Vulture run no longer reports it; A3 prunes the stale baseline entry in the same PR (a clean baseline is enforced by R5).
  - **Outcome:** Baseline debt neither grows nor silently rots; every removal is reflected in the allowlist.
  - **Covered by:** R3, R5

- F3. **Baseline entry is removed**
  - **Trigger:** A3 (or A1) files a ticket to remove a baseline entry and deletes the dead symbol.
  - **Actors:** A1, A2, A3
  - **Steps:** (1) The dead symbol is deleted in a PR. (2) The same PR removes the corresponding line from `deadcode-baseline.txt`. (3) A2 runs Vulture — no finding for that symbol, baseline no longer lists it, CI passes. (4) A stale baseline entry (listed but not reported by Vulture) is itself a CI failure under R5, so the PR cannot leave the line in.
  - **Outcome:** The allowlist monotonically shrinks; it never accumulates phantom entries.
  - **Covered by:** R5

---

## Requirements

- R1. **Vulture is a dev dependency** in the workspace `pyproject.toml` dev group, alongside the existing `ruff`/`mypy`/`pytest` entries. No runtime dependency is introduced.
- R2. **A CI step runs Vulture** in `.github/workflows/python-tests.yml`, after the existing "Lint with ruff" step. The step runs `vulture` over `packages/` at `--min-confidence 80`, referencing a committed baseline allowlist. The step fails the job on any finding not present in the baseline.
- R3. **A baseline allowlist file** (`deadcode-baseline.txt`, repo root, committed) is seeded from `vulture --make-whitelist` output at gate-landing time. It lists every pre-existing dead-code finding the gate is introduced with. The file format is Vulture's native whitelist format so the tool consumes it directly (`vulture packages/ --min-confidence 80 --whitelist deadcode-baseline.txt` or the `--exclude`-equivalent path the installed Vulture version supports).
- R4. **New dead code fails CI immediately.** There is no warn-only grace period; the baseline absorbs all pre-existing debt at landing, so any finding absent from the baseline is by definition new. (Grace periods are reserved for the case where the baseline is empty at landing — not expected here.)
- R5. **A stale baseline entry is a CI failure.** A line in `deadcode-baseline.txt` that Vulture no longer reports (because the symbol was deleted or wired up) must itself fail the gate. This prevents the allowlist from accumulating phantom entries and enforces monotonic shrinkage. The mechanism is a CI check that diffs Vulture's reported findings against the baseline and fails on baseline-only entries. (Exact mechanism — Vulture's own `--min-confidence` + whitelist strictness, or a wrapper script — is a planning decision; the *behavior* is the requirement.)
- R6. **Ruff `F401` and `F841` remain enabled** in `[tool.ruff.lint]` `select` (currently `"F"` covers both) and are not added to `ignore`. These are not new work — they are already live in `.github/workflows/python-tests.yml` line 53 (`uv run ruff check packages/`). This requirement exists to prevent the dead-code gate from being weakened by a future config edit that suppresses the file-local catches.
- R7. **Every baseline entry has a removal ticket** filed at gate-landing time (or a single tracking epic with one child per entry). Tickets are linked from the PR that lands the gate. The baseline is debt with a documented exit path, not permanent amnesty.

---

## Success Criteria

- A developer who adds a function that no `packages/` entry point ever calls sees a CI failure naming the file, line, and symbol — without any human having to read the file.
- The `.pyx` twin / `design_rules.py`-outside-`src/` class of duplication (a symbol shadowed by a same-named file elsewhere in the import path) is reported by the gate, not discovered by accident.
- `deadcode-baseline.txt` is strictly shorter one month after landing than at landing. The allowlist never grows.
- A baseline entry whose dead symbol is deleted is removed from the allowlist in the same PR — a stale line is itself a CI failure.
- The gate composes with the N3 coverage gate (R-* in `2026-06-21-source-of-truth-validation-requirements.md`) without overlap: Vulture catches code that *cannot* be reached; coverage catches code that *can* be reached but *is not* tested. A finding from one is not silently dismissed by the other.

---

## Out of Scope

- **Removing the existing dead code** — the gate freezes current debt; removal is ticketed work, not part of landing the gate.
- **Vulture on non-Python sources** — the firmware C tree and KiCad schematics are not scanned; the gate is Python-only over `packages/`.
- **Ruff rule expansion** — adding non-F ruff rules (e.g. `ARG`, `PLR`, `SIM`) is a separate hygiene initiative. This gate touches only `F401`/`F841` (already on) and Vulture.
- **Pre-commit hook installation** — a `.pre-commit-config.yaml` hook for Vulture is a developer-experience enhancement, not a gate requirement. The CI step is the enforcement boundary; a local hook is optional and deferred.
- **Dynamic dead-code detection** — coverage-based unreachable-code inference (N3) and the static parity test (N7) are separate initiatives. This gate is static-only.
- **`# noqa: V` inline suppression as a primary mechanism** — inline comments are permitted for genuine false positives but are not the default suppression path; the baseline allowlist is. Inline suppression does not decay (it persists after the dead code is removed), the baseline does (R5).

---

## Assumptions

- **Ruff `F401`/`F841` are already enforced.** Verified: `pyproject.toml` line 59 `select = ["E", "W", "F", "I", "B", "C4", "UP"]` enables the `F` family (which includes F401 unused-import and F841 unused-local), and `.github/workflows/python-tests.yml` line 53 runs `uv run ruff check packages/`. The ruff portion of this idea is therefore a *status-quo assertion* (R6), not new gate work. The net-new mechanism is Vulture.
- **Vulture's `--make-whitelist` output is stable enough to commit.** Vulture's whitelist format is the tool's native serialization; committing it ties the baseline to a Vulture version. Assumption: Vulture is pinned (or a version range is documented in the CI step) so a Vulture upgrade does not silently invalidate the baseline. If it does, the upgrade PR regenerates the baseline and is reviewed entry-by-entry.
- **`--min-confidence 80` is the right threshold.** 80 surfaces high-confidence unreachable functions/classes/methods while excluding the long tail of dynamic-dispatch false positives that Vulture itself flags below 80. 60 is too noisy for a CI gate (would inflate the baseline); 90 misses real dead code that Vulture scores in the 80–89 band (typical for indirectly-unreachable helpers). 80 is the value the rationale specifies and is Vulture's commonly-recommended gate threshold.
- **Vulture adds value ruff does not.** Ruff `F401`/`F841` are file-local: unused imports within a file, unused locals within a function. Neither detects a module-level function never called from *any* file, or a method never invoked through any dispatch path. Vulture's whole-program AST reachability is the only mechanism here that catches the "implemented but never wired in" DRC-check failure mode. The two tools are complementary, not redundant.
- **All `packages/` are scanned at once at landing.** Seven packages is a small surface; a pilot on `temper-drc` alone would defer the gate's value and require a second landing. The baseline absorbs `temper-placer`'s larger existing debt without requiring per-package triage.
- **The `packages/` scan path matches the ruff scan path.** The existing ruff step scans `packages/`; Vulture scans the same root. (Note: `temper-placer` uses a flat layout — `packages/temper-placer/temper_placer/` — while other packages use `src/` layout. Vulture scans Python files by path, not by import resolution, so the layout mismatch does not affect reachability analysis. This is verified by `packages/temper-placer/pyproject.toml` `packages = ["temper_placer"]`.)
- **Stale-baseline enforcement (R5) is achievable with Vulture's native mode or a small wrapper.** Vulture reports findings; the baseline lists expected findings. A diff of the two sets yields three buckets: new (fail), matched (pass), stale-baseline (fail). Assumption: this is implementable as a short shell or Python step in CI without a third-party tool. Exact mechanism deferred to planning.

---

## Open Questions

### Resolve Before Planning

- **[Affects R3][Tooling]** Which Vulture version is pinned, and does its `--make-whitelist` / `--whitelist` CLI surface match the version installable via `uv`? Confirm the exact invocation and that the whitelist file is consumed as a *suppression list* (entries are ignored) rather than a *report allowlist* (entries must be present). The R5 stale-entry check depends on which semantics Vulture exposes.
- **[Affects R5][Tooling]** Does Vulture exit nonzero when *all* findings are whitelisted, or does it exit zero (treating the whitelist as "these are fine")? If the latter, the R5 stale-entry check must be a separate step that compares reported findings to the baseline and fails on baseline-only lines. Confirm Vulture's exit-code semantics before designing the wrapper.

### Deferred to Planning

- **[Affects R2][CI]** Should the Vulture step run on pull_request and push both, or only on push to `main` plus pull_request? The ruff step inherits the workflow's `on:` triggers (push to main + PR to main, path-filtered to `packages/**`). Matching ruff's triggers is the default; deviate only if Vulture runtime is non-trivial.
- **[Affects R7][Process]** One tracking epic with a child ticket per baseline entry, or one ticket per entry filed directly? Affects issue-tracker hygiene but not the gate. Decide at landing.
- **[Affects R1][Tooling]** Add `vulture` to the workspace `dev` dependency group in the root `pyproject.toml`, or to a per-package dev group? Workspace-level matches how `ruff`/`mypy` are declared today (root `pyproject.toml` line 8–14).
