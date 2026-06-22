---
title: "Pattern: CI-Gate Quality Enforcement (Baseline + Monotonic Shrink)"
date: 2026-06-22
category: architecture-patterns
module: CI
problem_type: architecture_pattern
component: build-system
severity: medium
applies_when:
  - A recurring bug class has no structural prevention
  - Existing debt prevents a clean gate from landing
  - Human review is the only enforcement mechanism
tags:
  - ci-gates
  - quality-enforcement
  - baseline-allowlist
  - monotonic-shrink
  - structural-prevention
  - meta-pattern
  - sprint-N1-N9
---

# Pattern: CI-Gate Quality Enforcement (Baseline + Monotonic Shrink)

## Context

During the N1–N9 sprint sequence (June 2026 clean-base hardening), a recurring
failure class emerged across every initiative: a quality regression that CI had
no signal for. Root artifacts reappear. Safety constants drift across four
files. A function is "tested" by a Mock that validates no real contract. A
duplicate script is re-referenced after its deletion. A source file grows from
4000 to 5000 lines with no structural pushback. Dead code accumulates because no
tool flags it.

The solution converged on the same five-element pattern in every sprint.
This document captures that meta-pattern so future hardening initiatives can
apply it without reinventing the detection-and-baseline scaffolding.

## Guidance

The pattern has five elements, applied in dependency order:

1. **Gate mechanism** — A pytest test or standalone script that detects the bug
   class structurally (not by human inspection). Placed inside an existing CI
   step rather than creating a new job. The gate must produce a named, specific
   failure message that points the developer at the fix.

2. **Baseline allowlist** — A committed file listing every pre-existing
   violation the gate discovers at landing time. The allowlist makes the gate
   mergeable on day one while making the debt *visible* (it is a diffable,
   committed artifact) and *monotonically shrinking*.

3. **Hard block on new violations** — Any finding absent from the baseline fails
   CI immediately. No warn-only grace period. By definition, a finding not in
   the baseline is new and must not merge silently.

4. **Stale-entry enforcement** — A baseline entry whose corresponding violation
   no longer exists must be removed in the same commit that fixes it. The gate
   fails if a baseline line refers to a violation that is gone. This prevents
   the allowlist from rotting into permanent amnesty.

5. **Ticketed exit path** — Every baseline entry has a removal ticket filed at
   landing time. The allowlist is debt with a documented remediation plan, not
   permanent acceptance. The ticket ID is recorded alongside the entry.

The pattern composes across gates. A function caught by the coverage gate (N3)
is not silently dismissed by the dead-code gate (N9) — they operate on different
failure classes (dynamic execution vs. static reachability). Each gate is
narrow, single-concern, and its allowlist is scoped to exactly the violation
class it detects.

## Why This Matters

Without a CI gate, quality regressions are found only by a human reading the
code. The cost is invisible until a bug surfaces in production. The June 2026
sprint fixed twelve silent bugs of exactly this shape — values that drifted
across four files, a round-trip path broken for months behind a Mock, a dead
code path masked by a `try/except Exception` that swallowed `TypeError` into
`ValueError`.

The gate pattern converts "first human use reveals the bug" into "CI reveals the
bug at PR time." It makes the absence-of-enforcement condition structural rather
than opportunistic. A developer who types `clearance=6.0` into a new safety
check sees a named CI failure; a developer who adds `analyze_new.py` to the repo
root sees a named CI failure; a developer who pushes a 1001-line source file
sees a named CI failure. The feedback is immediate, specific, and mechanical.

The baseline-allowlist element is critical: without it, a gate cannot land on a
codebase with existing debt. The allowlist absorbs the pre-existing baseline,
makes the gate mergeable, and converts the remaining debt into a visible,
shrinking artifact. Each entry is an admission: "we know this exists, here is
where we tracked it." Over time, the allowlist shrinks to zero or stabilizes at
a small set of justified exceptions.

## When to Apply

Apply this pattern when:

- A recurring bug class has no CI signal and human review is the only enforcement.
- The bug class is mechanical to detect (a static rule, a CLI invocation, a
  `grep`-equivalent) and does not require subjective judgment.
- Existing instances of the bug class would fail the gate immediately, making a
  clean landing impossible without a baseline.
- The gate's failure message is self-documenting — it names the file, the
  violation, and the intended fix path.

Do NOT apply when:

- The detection requires subjective judgment (e.g., "does this function name
  match its behavior?").
- The existing debt is so large that the baseline would be unmaintainable (>200
  entries without a clear triage plan).
- The gate cannot produce a specific, actionable failure message (e.g., a
  percentage-threshold gate that says "coverage dropped to 89%" without naming
  which function dropped).

### Decision Flow

```
Recurring bug class identified
    │
    ├─ Can CI detect it mechanically? ── No ──→ Not a CI-gate candidate
    │
    ├─ Would existing code fail? ── No ──→ Land gate cleanly, no baseline needed
    │
    ├─ Is existing debt countable and triageable? ── No ──→ Fix debt first,
    │                                                       then land gate
    │
    └─ Yes → Apply baseline + monotonic shrink pattern
```

## Examples

### N1: Root-Hygiene CI Gate (`test_root_hygiene.py`)

Prevents root artifacts from reappearing after a 162-file purge. The gate runs
`git ls-files`, filters to root-level paths, and fails if any `.py`,
`.kicad_pcb`, `.kicad_pro`, or `*-drc.json` exists outside an explicit allowlist.

- **Gate:** pytest in `packages/temper-drc/tests/`, collected by existing CI step.
- **Baseline:** An allowlist literal in the test file (expected empty after purge).
- **New-violation block:** Any root file matching forbidden suffixes fails CI with
  a named message pointing to `scripts/` or `pcb/` as intended destinations.
- **Stale-entry enforcement:** N/A (allowlist expected empty — no entries to
  stale). If an entry were added, the test's assertion `violations == []` would
  fail on any new root file.
- **Composes with:** `.gitignore` root-anchored patterns (silent block) +
  the pytest gate (loud block) — defense in depth.

### N2: Safety-Constant SSOT (`test_safety_constant_lint.py` + `test_safety_constant_reconciliation.py`)

Prevents safety-clearance constants from drifting across four consumers. Two
independent enforcement layers: an AST linter (catches bare float literals
matching authority values) and a reconciliation test (catches derived/indirect
values).

- **Gate:** Two pytest files in `packages/temper-drc/tests/`. Linter uses
  `ast.walk`; reconciliation test reads authority record, DRU output, and
  runtime check defaults.
- **Baseline:** `safety_constant_overrides.yaml` — a committed YAML file mapping
  `(site, expected_value, reason, ticket)` for each known drift.
- **New-violation block:** Reconciliation test fails with HOLD findings on any
  divergence not in the overrides file. Linter is a hard block with no override
  (there is no legitimate reason to introduce a bare float literal duplicating an
  authority value).
- **Stale-entry enforcement:** The override entry's `expected_value` is checked
  against the actual value; a stale override (where the real value changed but
  the override stayed) does not apply and the HOLD fires.
- **Acceptance criterion:** The reconciliation test must FAIL against current
  `main` with an empty override file — proving the detection works. The override
  file is then populated in the landing commit.

### N3: Coverage Gate (`scripts/check_coverage_gate.py`)

Prevents zero-test public functions from being added. A standalone script reads
`coverage.json`, computes zero-coverage public functions, subtracts the
allowlist, and fails on any net-new uncovered function.

- **Gate:** Standalone script `scripts/check_coverage_gate.py`, invoked as a new
  CI step after the placer test run.
- **Baseline:** `.coverage-allowlist` — plain text `module::function  # TODO:
  temper-xxx`, one entry per line.
- **New-violation block:** Any public function with zero executed lines not in
  the allowlist fails CI with a named file/function.
- **Stale-entry enforcement:** `--check-shrink` mode verifies that any entry
  removed from the allowlist is paired with either a test exercising the
  function or a deletion of the function. An entry added without a ticket
  reference fails.
- **Monotonic shrink:** A PR that adds a new allowlist entry without removing a
  larger one is rejected. Phase 2 cannot land until Phase 1's allowlist shrinks
  by ≥50%.

### N5: Consolidation Guard (`test_consolidation_guard.py`)

Prevents deleted duplicate scripts from being re-referenced after a 7-file
consolidation. The guard maintains a denylist of deleted filenames and fails CI
if any reappear in `git ls-files` or are referenced outside `docs/`.

- **Gate:** pytest in `packages/temper-drc/tests/`. Runs `git ls-files` and
  `git grep` against the denylist.
- **Baseline:** The denylist is a Python set literal in the test file — fixed
  set of 7 filenames.
- **New-violation block:** Any denylisted filename tracked by git or referenced
  in a non-docs file fails with a named message pointing to
  `docs/consolidation-log.md` for the canonical survivor.
- **Stale-entry enforcement:** N/A (denylist is fixed — no entry is expected to
  be removed; the guard is an invariant, not a shrinking allowlist).

### N6: LOC Cap Gate (`tools/loc_cap_check.py`)

Prevents any source `.py`/`.c` file from exceeding 1000 lines without an
allowlist entry. The gate also enforces that allowlisted files do not grow
beyond their baseline and that the allowlist only ever shrinks.

- **Gate:** Standalone script `tools/loc_cap_check.py`, invoked as a separate
  `loc-cap` CI job.
- **Baseline:** `.loc-allowlist.txt` — 16 entries at landing (15 `.py` + 1
  `.c`), each with `path`, `baseline_lines`, `ticket_id`, and description.
- **New-violation block:** Four violation classes: UNLISTED_OVER_CAP (file over
  1000 not on allowlist), ALLOWLIST_GREW (allowlisted file grew beyond
  baseline), NEW_ENTRY_NO_REMOVAL (net allowlist growth), REMOVED_STILL_OVER_CAP
  (entry removed but file still over cap).
- **Stale-entry enforcement:** A removed allowlist entry whose file is still
  over cap fails. The strict-shrink policy (a new entry requires a larger
  removal) prevents allowlist bloat.
- **Scope gating:** Subsequent phases expand the gate to new directories only
  after the prior phase's allowlist shrinks by ≥50%.

### N9: Vulture Dead-Code Gate (`scripts/vulture_gate.py`)

Prevents new dead code from accumulating by running Vulture (whole-program AST
reachability) against a committed baseline and failing CI on any finding not in
the baseline or any baseline entry Vulture no longer reports.

- **Gate:** Wrapper script `scripts/vulture_gate.py` that runs Vulture twice
  (with and without the baseline), diffs the sets, and produces a three-bucket
  result.
- **Baseline:** `deadcode-baseline.py` — Vulture's native whitelist format
  (Python source file passed as a positional argument). Seeded from `vulture
  --make-whitelist` at landing.
- **New-violation block:** Exit code 3 — any finding present when Vulture runs
  *with* the baseline (i.e., not suppressed by it) is new dead code.
- **Stale-entry enforcement:** Exit code 4 — any line in the baseline that
  Vulture no longer reports (because the symbol was deleted or wired up) must be
  removed in the same commit.
- **Composes with N3:** Vulture is static reachability (code that *cannot* be
  reached); coverage is dynamic execution (code that *can* be reached but *is
  not* tested). A finding from one is not dismissed by the other.

## Related

- `docs/plans/2026-06-22-001-feat-purge-and-protect-plan.md` (N1: root hygiene)
- `docs/plans/2026-06-22-002-feat-safety-constant-ssot-plan.md` (N2: safety SSOT)
- `docs/plans/2026-06-22-003-feat-dead-path-coverage-gate-plan.md` (N3: coverage gate)
- `docs/plans/2026-06-22-005-feat-duplicate-script-consolidation-plan.md` (N5: consolidation guard)
- `docs/plans/2026-06-22-006-feat-cli-zoning-loc-cap-plan.md` (N6: LOC cap)
- `docs/plans/2026-06-22-009-feat-vulture-ruff-deadcode-gate-plan.md` (N9: vulture gate)
- `CLAUDE.md` — documentation of live gate mechanisms and allowlist conventions
