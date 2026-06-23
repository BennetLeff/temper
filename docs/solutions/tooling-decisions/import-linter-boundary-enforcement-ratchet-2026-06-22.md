---
title: "Import-Linter Boundary Enforcement Ratchet for Strangler-Fig Decomposition"
date: 2026-06-22
category: tooling-decisions
module: temper_placer
problem_type: tooling_decision
component: tooling
severity: medium
applies_when:
  - Extracting a module from a monolith during strangler-fig decomposition
  - Preventing accidental re-coupling from newly-extracted modules back to old monolith internals
  - Enforcing public-interface-only imports across package boundaries
  - Adding a new boundary enforcement CI gate with existing debt
tags:
  - import-linter
  - archunit
  - boundary-enforcement
  - strangler-fig
  - ratchet-baseline
  - monotonic-shrink
  - ci-gate
  - package-boundaries
  - public-interface
  - independence-contract
  - soft-launch
  - sprint-014
---

# Import-Linter Boundary Enforcement Ratchet for Strangler-Fig Decomposition

## Context

Temper has 7 Python packages (~36 subpackages within `temper_placer` alone) with zero guardrails on inter-module imports. During strangler-fig decomposition of the `temper_placer` monolith, a freshly-extracted module can silently re-couple to the old monolith through an accidental import — and nothing catches it.

We added `import-linter` (Python's ArchUnit equivalent) to enforce module boundaries mechanically at CI. Without it, extracted modules drift back toward depending on monolith internals over months, and the monolith can never be deleted.

## Guidance

### Architecture

Four artifacts compose the enforcement pipeline:

| Artifact | Format | Role |
|----------|--------|------|
| `.importlinter` | INI-style (import-linter native) | Declares boundary contracts (what is forbidden / independent) |
| `import-linter-baseline.yaml` | YAML (committed) | Records pre-existing violations at gate launch; diffs against PR violations |
| `import-linter-allowlist.yaml` | YAML (committed) | Monotonic-shrinking allowlist for justified exceptions with ticket references |
| `scripts/import_linter_gate.py` | Python wrapper | Runs import-linter, diffs against baseline, applies allowlist, enforces ratchet |

The ratchet works as follows:

1. `import-linter` runs in violation-reporting mode, producing a list of (source, target, contract) edges
2. The gate script subtracts baseline entries (pre-existing violations) and allowlist entries (justified exceptions)
3. Any remaining edges are **new violations** — CI fails
4. When a violation is fixed, the corresponding baseline entry is removed in the same commit, tightening the ratchet

### Boundary Contracts

The seed set (landed 2026-06-22) declares three contracts:

**Independence contract** — `core/ ⊥ router_v6/`: neither package may import from the other. This is the primary strangler-fig seam.

**Public-interface contracts** — External packages (all 23+ sibling modules within `temper_placer`) may only import from `temper_placer.core` and `temper_placer.router_v6` via their `__init__.py` re-exports. All individual submodule imports are forbidden.

```ini
# .importlinter (key sections)

[importlinter]
root_packages =
    temper_placer

# core/ ⊥ router_v6/ — neither may import from the other
[importlinter:contract:core-isolated-from-router-v6]
name = core-isolated-from-router-v6
type = independence
modules =
    temper_placer.core
    temper_placer.router_v6

# External packages may only import from core/ public interface
[importlinter:contract:core-public-interface-only]
name = core-public-interface-only
type = forbidden
source_modules =
    temper_placer.ablation
    temper_placer.adapters
    temper_placer.cli
    # ... 23 source modules total ...
    temper_placer.visualization
forbidden_modules =
    temper_placer.core.board
    temper_placer.core.decision
    # ... 22 internal submodules ...
    temper_placer.core.units
as_packages = False
ignore_imports =
    temper_placer.core.* -> temper_placer.core.*

# Same pattern for router_v6 public interface
[importlinter:contract:router-v6-public-interface-only]
name = router-v6-public-interface-only
type = forbidden
# ... 45 forbidden submodules ...
```

### Ratchet Baseline

`import-linter-baseline.yaml` captures every pre-existing cross-boundary import at gate launch. Example entry:

```yaml
violations:
  - contract: core-isolated-from-router-v6
    source: temper_placer.router_v6
    target: temper_placer.core
  - contract: core-public-interface-only
    source: temper_placer.cli
    target: temper_placer.core.board
```

The initial baseline contains ~130 entries across all 23 source modules that import from core internals. Each entry is a known violation admitted at launch — the gate suppresses them so existing code doesn't break CI.

### Allowlist Format

`import-linter-allowlist.yaml` uses regex patterns for source/target/contract fields. Each entry requires a `reason` and `ticket` field:

```yaml
allowlist:
  # Integration test blanket exception (R11)
  - source: temper_placer\.routing\..*
    target: temper_placer\.core\..*
    contract: core-public-interface-only
    reason: "Routing layer reads core data structures (netlist, state, board) to operate"
    ticket: temper-xxx

  # Script audit entries — 118+ ad-hoc scripts default to allowlisted (U7)
  - source: scripts/.*\.py
    target: temper_placer\..*
    contract: .*
    reason: "Ad-hoc tooling scripts — re-evaluate in temper-xxx"
    ticket: temper-xxx
```

### Soft-Launch Mode

A hardcoded `CUTOVER_DATE = datetime.date(2026, 7, 6)` in `scripts/import_linter_gate.py` gates the transition from WARNING-only to merge-blocking:

- **Before cutoff**: All violations are printed as CI warnings with remediation guidance, but the step exits 0 (never blocks merge).
- **After cutoff**: New violations (absent from baseline and allowlist) exit code 3, blocking the PR.

This gives developers 2 weeks to fix existing violations and adjust workflows before the gate becomes hard enforcement.

### Violation Remediation Messages

Each new violation prints R16-compliant guidance naming the boundary rule and two options:

```
  Boundary rule: core-public-interface-only
  Option A: Use the public interface at 'temper_placer.core' instead of 'temper_placer.core.board'
  Option B: Add an allowlist entry to 'import-linter-allowlist.yaml' with justification + ticket reference
```

### CI Integration

The gate runs as a step in the existing `python-tests.yml` workflow, after the Vulture dead-code gate:

```yaml
      - name: Import boundary enforcement
        run: uv run python scripts/import_linter_gate.py
```

Path triggers ensure the step runs when boundary config files change:
```yaml
on:
  push:
    paths:
      - 'import-linter.yaml'
      - 'import-linter-baseline.yaml'
      - 'import-linter-allowlist.yaml'
      - 'scripts/import_linter_gate.py'
```

### Local Pre-Merge Check

Developers can run the same check locally before pushing:

```bash
uv run python scripts/import_linter_gate.py
```

If violations are reported, the output includes the boundary contract violated and both remediation paths.

## Why This Matters

Without boundary enforcement, strangler-fig decomposition stalls. A freshly-extracted module that freely imports from the old monolith can never be fully separated — the monolith can never be deleted. This is the same problem FreeRouting solved with ArchUnit (Java) during their monolithic-to-modular decomposition.

The ratchet mechanism converts boundary enforcement from a "human reads the code" problem into a "CI reveals the violation at PR time" problem. The baseline makes the gate mergeable on day one while making all existing debt visible as a committed, diffable, shrinking artifact. Each baseline entry is an admission: "we know this import crosses the boundary, here is where we tracked it."

The allowlist provides a self-serve escape hatch — developers add entries with justification and ticket reference without separate review (R15). Boundary config changes (`.importlinter`) still require PR review.

The soft-launch prevents the gate from surprising developers. Two weeks of WARNING-only mode gives the team time to fix violations and adjust workflows before the gate becomes merge-blocking.

## When to Apply

Apply this pattern when:

- You are decomposing a monolith and need to prevent extracted modules from re-coupling to old internals.
- The codebase has existing cross-boundary imports that would fail a clean gate (need a baseline).
- The boundary violations are mechanical to detect (static import graph, not runtime behavior).
- You need a self-serve exception mechanism that doesn't require a separate review process.
- The team needs a transition period before hard enforcement.

Do NOT apply when:

- The codebase has no existing violations — land the gate cleanly without a baseline.
- The detection requires subjective judgment about import intent.
- The existing debt is so large that the baseline would be unmanageable (>500 entries without a clear triage plan).

## Key Learnings

1. **import-linter uses INI config, not YAML**. The plan assumed YAML config, but `import-linter` v2.0+ uses TOML-inspired INI syntax (`[importlinter:contract:name]`). The `.importlinter` file extended name is the convention.

2. **Ratchet via committed baseline YAML works**. `import-linter` has no native "baseline" feature. The wrapper script captures the violation report, serializes it to YAML, and diffs against the committed baseline. New edges absent from baseline and allowlist are violations.

3. **The allowlist uses regex patterns**. Entries in `import-linter-allowlist.yaml` are matched via `re.fullmatch()` against source, target, and contract fields. This allows compact blanket patterns like `scripts/.*\.py` covering 118 scripts in a single entry.

4. **Baseline shrinking is manual but verified**. The gate prints "RESOLVED VIOLATIONS — BASELINE SHRINK" when violations are fixed, but doesn't auto-remove entries. Developers commit the updated baseline in the same PR that fixes the violation.

5. **CI runtime is well under target**. The import-linter analysis completes in ~350ms plus the wrapper's YAML parsing (~10ms). The <30s CI budget is trivially met.

6. **Script audit is handled via blanket allowlist entries**. Rather than auditing all 118 scripts individually at launch, 5 broad regex entries (`scripts/`, `tools/`, `experiments/`, `simulation/`, `router-experiments/`) cover script directories. Individual scripts are migrated out as they are audited.

7. **The existing CI infrastructure is reused**. The gate runs in the same `uv run` environment provisioned by `uv sync --all-packages`, with zero additional setup cost. `import-linter` is added as a dev dependency in `pyproject.toml`.

## Related

- `docs/plans/2026-06-22-014-feat-import-linter-boundary-enforcement-plan.md` — origin plan with full requirements and acceptance examples
- `.importlinter` — active boundary contracts (independence + 2 public-interface forbiddens)
- `import-linter-baseline.yaml` — committed ratchet baseline (~130 pre-existing violations)
- `import-linter-allowlist.yaml` — monotonic-shrinking allowlist with regex entries and ticket references
- `scripts/import_linter_gate.py` — diff-wrapper gate script with soft-launch mode and R16 remediation messages
- `.github/workflows/python-tests.yml` — CI integration (step after Vulture gate)
- `pyproject.toml` — `import-linter>=2.0` dev dependency
- `AGENTS.md` — documented local check invocation (`uv run python scripts/import_linter_gate.py`)
- `docs/solutions/architecture-patterns/ci-gate-quality-enforcement.md` — meta-pattern (baseline + monotonic shrink) that this gate instantiates
- `docs/plans/2026-06-22-001-feat-purge-and-protect-plan.md` through `009` — sibling CI gates (N1–N9) using the same ratchet pattern
