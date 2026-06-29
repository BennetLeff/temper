---
title: "Integration Hunting — find built-but-unwired code before building new features"
date: 2026-06-28
category: workflow-issues
module: temper_placer
problem_type: workflow_issue
component: development_workflow
severity: high
applies_when:
  - "A feature described in an ideation doc or plan seems like it needs new code"
  - "The codebase has been under active development with many contributors"
  - "Stale ideation docs may describe a state that is already resolved"
  - "Routing, pipeline, or integration work is the task at hand"
tags:
  - integration-hunting
  - dead-code-wiring
  - pipeline-integration
  - codebase-audit
  - workflow-pattern
---

# Integration Hunting — find built-but-unwired code before building new features

## Context

The Temper codebase was under active parallel development with multiple worktrees.
Many features described in ideation docs (dated 2026-06-24) were already shipped
by 2026-06-28 but the ideation docs themselves were never updated. This created a
risk of planning and building features that were already done — wasting time and
potentially creating merge conflicts with existing implementations.

During a session that planned to tackle 7 ideation ideas, 4 were found to be
already complete (DFM stages wire, DRCFence blocking flip, impedance trace width
from stackup, and fault enum codegen), 1 was determined unnecessary (serpentine
length matching), and only 2 required actual work (coupled diff pair router
universalization, coordinate decommissioning).

## Guidance

**Before implementing any feature from an ideation doc or plan, run a 3-minute audit:**

### 1. Audit the ideation doc's claims against origin/main

```bash
git grep "<key term from ideation>" -- packages/*/src/ packages/*/tests/
```

If the term appears as an export, in `__init__.py`, or in a pipeline call site,
the feature may already be wired. Check git log for recent merges containing the
feature name.

### 2. Check for the integration-hunt pattern

The Temper codebase has a recurring pattern: new features are built and tested in
isolation (often in `experiments/` or as standalone modules) but never wired into
the production pipeline. When a feature exists and is importable but has no path
from `pipeline.py`, that's the integration gap.

Checklist:
- Does the feature exist in `src/`? (importable)
- Is it exported from `__init__.py`? (public API)
- Is it called from `pipeline.py` or a stage's `run()` method? (production path)
- If importable but not called → integration gap, not a new feature

### 3. Run the "already done" check before planning

```bash
git log --oneline --all --grep="<feature keyword>" | head -10
```

If there are merged PRs with merge messages containing the feature name, the
work may already be on main. The ideation is stale, not the implementation.

### 4. Audit necessity before building signal/power features

For signal-integrity features (serpentine, impedance, length matching):
- Count the actual differential pairs on the board
- Check the protocol speeds (USB FS vs HS)
- Compute whether physical mismatch exceeds the spec
- If the worst-case is 30× below spec, skip the feature

## Why This Matters

**Velocity impact**: In one session, this pattern prevented ~5 features from being planned
and built unnecessarily (they were already done). The 2 features actually implemented
took ~2 hours total rather than the ~8+ hours that all 7 would have required.

**Merge conflict avoidance**: Building a feature that was already shipped on a different
branch creates predictable merge conflicts. Re-discovering that the work is done avoids
this entirely.

**Signal quality**: Ideation docs and plans get stale fast in multi-worktree development.
The fastest way to determine whether a feature still needs work is a git grep + git log,
not reading the ideation doc and trusting it.

## When to Apply

- At the start of any `/ce-plan` session for a feature from an existing ideation doc
- When picking up work from `docs/ideation/` that is more than 2 days old
- Before writing new code for any feature that sounds like "wire X into the pipeline"
- When a feature involves signal integrity, clearance, or safety — audit physical
  necessity against the actual board before building

## Examples

### Correct application: Coupled Diff Pair Router (20 minutes)

```
1. Grep for "CoupledDiffPairRouter" → found in experiments/ + sequential_routing.py
2. Check pipeline → found sys.path.insert hack, USB-only gate
3. Plan: promote to routing/, remove gate, add tests
4. Result: 2 PRs, ~1 hour total
```

### Missed if not audited: 4 features already shipped (would have cost hours)

```
1. DFM stages → already wired in _run_manufacturing_drc() (PR #20)
2. DRCFence blocking → already flipped in flags.py (PR #23)
3. Impedance trace width → already computed from stackup (PR #24)
4. Fault enum codegen → already generated from manifest.json
```

All four would have triggered planning + implementation cycles if the audit step
had been skipped.

### Necessity audit: Serpentine length matching (15 minutes)

```
1. Count diff pairs on board → 1 signal pair (USB_D+/USB_D-)
2. Check ESP32-S3 USB spec → Full Speed only (12 Mbps)
3. Compute worst-case mismatch → ~0.2mm → 6.7 ps
4. Check USB FS spec → ±2 ns receiver skew tolerance
5. Margin: 30× below spec → skip the feature
```

## Related

- `docs/solutions/design-patterns/dsn-universal-seam-eda-pipelines-2026-06-22.md` — sidecar as the integration seam pattern
- `docs/solutions/architecture-patterns/declarative-stage-dag-replaces-orchestrator-2026-06-22.md` — Stage contract pattern
- `docs/ideation/2026-06-24-router-v6-feature-completeness-ideation.html` — the ideation doc this pattern was tested against (4/7 ideas already done)
- `docs/audits/2026-06-28-serpentine-necessity-audit.md` — example of a necessity audit
- `docs/solutions/architecture-patterns/ci-profiling-platform-canonical-metrics-contract-2026-06-28.md` — the `temper profile run --all` CLI (shipped 2026-06-28) replaces the ad-hoc profiling scripts this audit workflow was designed to hunt
