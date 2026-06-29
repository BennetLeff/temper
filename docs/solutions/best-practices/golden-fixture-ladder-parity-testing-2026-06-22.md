---
title: "Golden Fixture Ladder — Per-Stage Strangler Fig Parity Testing"
date: 2026-06-22
category: best-practices
module: temper_placer
problem_type: best_practice
component: testing_framework
severity: high
applies_when:
  - Extracting a stage from a monolith pipeline via strangler fig pattern
  - Adding or modifying pipeline stage boundary definitions
  - Changing serialization logic for DSN, SES, or JSON stage output
  - Introducing a new canonical test board beyond the existing 3-board ladder
  - CI signals false failures from floating-point noise in coordinate comparisons
  - Intentionally regenerating goldens after a monolith behavior change
tags:
  - golden-fixtures
  - parity-testing
  - strangler-fig
  - pcb-pipeline
  - ci-gate
  - tolerance-diff
  - deterministic-serialization
  - ladder-growth
---

# Golden Fixture Ladder — Per-Stage Strangler Fig Parity Testing

## Context

Temper has three overlapping PCB design automation pipeline systems (PipelineOrchestrator 8-phase monolith, RouterV6Pipeline 5-stage, DeterministicPipeline 26 stages) being decomposed via strangler fig adapters. The closure test (`parse -> place -> route -> DRC`) operates only at pipeline endpoints — an extracted stage can silently diverge from the monolith's behavior at intermediate seams, and the divergence is only discovered at the final DRC step, requiring backward tracing through 8+ phases.

The golden fixture ladder automates Fowler's strangler parity-test pattern at every pipeline stage boundary: a committed golden DSN/SES fixture per (board, stage) pair, a CI diff that runs the current pipeline output against the golden, and a geometric-tolerance pass/fail gate that blocks PRs on divergence. Each stage extraction becomes self-certifying: replace a stage, run the pipeline, compare output to the golden, and if the diff is within tolerance the stage is safe to deploy.

## Guidance

### Architecture

The ladder has five layers in dependency order:

1. **Stage boundary registry** — `boundary_registry.py` declares every pipeline stage boundary with its pipeline class, output format (DSN/SES/JSON), and serialization function. Each boundary entry carries a per-format geometric tolerance threshold (1e-3mm for DSN coordinates, 1e-6mm for SES trace endpoints).

2. **Deterministic serializers** — `golden_serializers.py` provides three `BoardState -> str` callables (DSN, SES, JSON). All enforce byte-identical reproduction on the same machine: float formatting pinned to `f"{val:.6f}"`, dict/set iteration uses `sorted()`, JSON uses `sort_keys=True`, and no non-semantic data (timestamps, PRNG state, file paths) is serialized.

3. **Geometric diff engine** — `golden_diff.py` parses DSN place/nets, SES wire segments, or JSON structures from both golden and candidate outputs, computes coordinate deltas, and classifies each difference into one of three categories:

   | Category | Meaning | Gate impact |
   |---|---|---|
   | `BINARY` | Structural mismatch (missing net, missing component, different pin count) | FAIL |
   | `BEYOND_TOLERANCE` | Coordinate delta > tolerance threshold | FAIL |
   | `WITHIN_TOLERANCE` | Coordinate delta <= tolerance threshold | Informational only |

4. **CLI commands** — `temper golden generate` creates/updates fixtures by running the monolith pipeline to a stage boundary and serializing the output. `temper golden check` runs the full ladder (or a targeted `--stage --board` subset), diffs each fixture, and exits 0 if all pass. `temper golden regenerate` updates goldens after intentional monolith changes.

5. **CI gate** — A dedicated `golden-check.yml` workflow runs `temper golden check` on every PR with path filters on `packages/**` and `power_pcb_dataset/**`. The job is a required branch protection check.

### Key Principle: CI Circularity Solved

When a developer makes an intentional monolith change that alters pipeline output, they commit regenerated goldens alongside the code change. The golden manifest records the git commit hash at generation time. CI verifies that every committed golden's `git_hash` is an ancestor of PR HEAD via `git merge-base --is-ancestor`. If golden regeneration and code change are in separate PRs, the check catches the gap. This prevents both drift (forgetting to regenerate) and abuse (regenerating goldens without matching code changes).

### R6 vs R8: Two Different Guarantees

| Requirement | Scope | Guarantee |
|---|---|---|
| R6 (byte-identical) | Same machine, same code, same seed | `output1 == output2` as raw strings |
| R8 (tolerance-based) | Cross-machine, cross-JAX-version | Coordinate delta <= per-format threshold |

R6 guarantees that the `generate` step is deterministic enough to commit fixtures — you don't want golden regeneration producing different bytes on every run. R8 guarantees that CI diff is meaningful across CI runners with different hardware/compiler stacks. They serve different purposes and must not be conflated.

### Board Selection (3 Canonical Boards)

Three canonical boards exercise enough variance to catch most regressions:

- **`temper_placed`** — the primary target board, placed but not routed, with medium complexity (representative of typical pipeline behavior)
- **Minimal board** — a simple board exercising edge cases with few components (catches over-generalization in complex logic)
- **Complex board** — a high-density design with many nets and components (catches scaling bugs and performance regressions)

Additional boards are added to the ladder when a regression is discovered on a board not represented by the existing set. The ladder grows incrementally, never shrinks.

### Generation Is Per-Stage-Boundary, Not Full-Pipeline

Developers check only their stage. Running `temper golden check --stage apply_placements --board temper_placed` verifies a single stage on a single board in under 30 seconds. This is the developer inner loop — not the full-ladder CI run. The full ladder (3 boards x 5 stages = 15 fixtures) completes in under 5 minutes on CI hardware.

### Fixture Storage: Committed to Repo

DSN files are typically <100KB, SES <1MB. Committing them to the repo avoids external artifact storage, makes the ladder visible in code review (diffs of golden files are reviewable), and eliminates network-dependency failures in CI. The `power_pcb_dataset/goldens/` directory is the single source of truth.

## Why This Matters

| Without golden fixture ladder | With golden fixture ladder |
|---|---|
| Stage extraction is a gamble — divergence only caught at final DRC | Per-stage parity test gates every extraction before merge |
| "The X coordinate drifted by 2mm" discovered days later by a human | CI diff catches the 2mm delta at PR time with `BEYOND_TOLERANCE` |
| Floating-point noise from JAX version bump causes CI confusion | Geometric tolerance threshold absorbs noise, only real divergence fails |
| Developer extracting a stage must run the full pipeline every time | `--stage --board` targeted check completes in <30 seconds |
| No way to know if a refactored stage matches the original monolith output | Byte-identical golden + tolerance-based diff proves equivalence |
| Golden regeneration and code change can drift across PRs | Manifest git_hash ancestry check ensures regeneration is always in the same commit tree |

## When to Apply

- **New stage boundary**: Register it in `boundary_registry.py`, add the serializer to `golden_serializers.py`, run `temper golden generate --stage <name> --all-boards`, commit the fixtures, verify with `temper golden check`.
- **Stage extraction via strangler fig**: Before replacing a monolith stage, commit goldens of the monolith output. During development, run targeted checks to verify parity. After extraction, regenerate goldens to reflect the new implementation as the new baseline.
- **Monolith behavior change**: Commit code change + regenerated goldens in the same PR. CI `git merge-base` check verifies coherence.
- **New canonical board**: Generate all-stage goldens for the new board. Existing boards are unaffected; the ladder grows without breaking.
- **Floating-point CI noise**: If JAX/XLA version bumps produce coordinate deltas within tolerance, R8 absorbs them. If deltas exceed tolerance boundaries, adjust the thresholds in `stage_boundaries.yaml` only after confirming the deltas are noise, not real divergence.

### Decision Flow

```
Stage extraction or pipeline modification
    │
    ├─ Is there a committed golden for this (board, stage)? ── No ──→ generate it first
    │
    ├─ Does `temper golden check --stage X --board Y` pass? ── Yes ──→ safe to merge
    │
    ├─ Are failures all WITHIN_TOLERANCE? ── No ──→ investigate real divergence
    │
    ├─ Is this an intentional monolith change? ── Yes ──→ regenerate in same PR
    │
    └─ Is the coordinate delta from JAX/XLA version noise? ── Yes ──→ adjust tolerance or regenerate
```

## Examples

### Example 1: Golden manifest format and generation

From `temper golden generate --stage apply_placements --board temper_placed`:

```bash
$ temper golden generate --stage apply_placements --board temper_placed --input pcb/temper_placed.kicad_pcb
Wrote power_pcb_dataset/goldens/temper_placed/apply_placements.dsn
Updated power_pcb_dataset/goldens/manifest.yaml
```

Resulting manifest entry in `power_pcb_dataset/goldens/manifest.yaml`:

```yaml
format_version: 1
fixtures:
  - board: temper_placed
    stage: apply_placements
    pipeline: DeterministicPipeline
    format: dsn
    generated_at_commit: "a1b2c3d4e5f6..."
    golden_file: goldens/temper_placed/apply_placements.dsn
```

### Example 2: Deterministic DSN serialization

From `golden_serializers.py` — all three determinism rules enforced:

```python
def serialize_boardstate_to_dsn(state: BoardState) -> str:
    from temper_placer.io.dsn_exporter import DSNExporter

    if state.board is None or state.netlist is None:
        raise ValueError("BoardState missing board or netlist")

    exporter = DSNExporter(board=state.board, netlist=state.netlist)
    dsn_expr = exporter.export_pcb(pcb_name="temper")
    return str(dsn_expr)
```

The DSNExporter enforces: components sorted by ref, pins sorted by number, nets sorted by name, floats formatted `{:.6f}`. Two invocations on the same unmuted BoardState produce byte-identical output.

### Example 3: Geometric diff engine — DSN coordinate comparison

From `golden_diff.py` — DSN place parsing and tolerance-based comparison:

```python
DSN_PLACE_RE = re.compile(r'\(\s*place\s+(\S+)\s+([\d.]+)\s+([\d.]+)\s+\S+\s+([\d.]+)')

def _parse_dsn_places(dsn_text: str) -> dict | None:
    """Parse (place REF X Y side ROT) into {ref: (x_mm, y_mm, rot_deg)}."""
    try:
        places = {}
        for m in DSN_PLACE_RE.finditer(dsn_text):
            ref = m.group(1)
            x = float(m.group(2)) / 100.0    # DSN units -> mm
            y = float(m.group(3)) / 100.0
            rot = float(m.group(4))
            places[ref] = (round(x, 6), round(y, 6), round(rot, 6))
        return places
    except Exception:
        return None
```

Key detail: DSN internal units are 10μm (resolution um 10), so divide by 100 to convert to mm. Rotation comparison wraps at 360° (`delta = min(abs(gv - cv) % 360, 360 - ...)`).

### Example 4: Tolerance thresholds — absorbing floating-point noise

A component's X coordinate at `5.000001` in the golden vs `5.000002` in CI output produces delta `0.000001` mm. With DSN tolerance `0.001` mm (1e-3), this is `WITHIN_TOLERANCE` and the gate passes. The same component shifted to `5.200000` produces delta `0.2` mm — `BEYOND_TOLERANCE` and the gate fails.

Specified in `stage_boundaries.yaml` per boundary:

```yaml
boundaries:
  - name: apply_placements
    output_format: dsn
    tolerance_mm: 0.001        # 1e-3 mm — absorbs JAX/XLA float noise, catches real placement drift
  - name: sequential_routing
    output_format: ses
    tolerance_mm: 0.000001     # 1e-6 mm — SES trace coords are higher precision
```

### Example 5: CI circularity — intentional regeneration flow

When a developer modifies the monolith's placement algorithm, they must regenerate the affected goldens in the same PR:

```bash
$ temper golden regenerate --stage apply_placements --board temper_placed
Wrote power_pcb_dataset/goldens/temper_placed/apply_placements.dsn

$ git add power_pcb_dataset/goldens/
$ git commit -m "feat: improve placement algorithm + regenerate golden fixtures"
```

The CI check (`golden-check.yml`) then runs:

```bash
$ temper golden check
OK: 3 boards x 5 stages = 15 fixtures matched.
```

The `git merge-base --is-ancestor` check validates that the commit hash recorded in the manifest is an ancestor of PR HEAD. If the developer forgets to regenerate, the old golden diverges from the new code output and CI fails with a named failure pointing at the stage and the delta.

### Example 6: Ladder growth — adding a fourth board

Adding a new board `temper_buck` is non-breaking for existing fixtures:

```bash
$ temper golden generate --board temper_buck --all-stages
Wrote power_pcb_dataset/goldens/temper_buck/apply_placements.dsn
Wrote power_pcb_dataset/goldens/temper_buck/clearance_grid.dsn
...
Wrote power_pcb_dataset/goldens/temper_buck/connectivity_validation.json

$ git add power_pcb_dataset/goldens/temper_buck/
$ git add power_pcb_dataset/golden_manifest.yaml
$ git commit -m "feat: add temper_buck to golden fixture ladder"
```

Existing CI checks continue to pass for `temper_placed`, `minimal`, and `complex` boards. The new board's fixtures are validated alongside existing ones. The ladder grows from 15 to 20 fixtures without risk of regression.

### Example 7: CI workflow structure

```yaml
name: Golden Fixture Check

on:
  push:
    branches: [main]
    paths:
      - 'packages/**'
      - 'power_pcb_dataset/**'
      - '.github/workflows/golden-check.yml'
  pull_request:
    branches: [main]
    paths:
      - 'packages/**'
      - 'power_pcb_dataset/**'
      - '.github/workflows/golden-check.yml'

jobs:
  golden-check:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: astral-sh/setup-uv@v3
      - run: uv sync --all-packages
      - run: uv run temper golden check
```

The workflow is a separate CI job (not embedded in `python-tests.yml`) because golden checking has distinct runtime characteristics (minutes), depends on JAX + all pipeline deps, and benefits from parallel CI execution with unit tests. Path filters prevent unnecessary runs on documentation-only or firmware-only PRs.

## Related

- `docs/plans/2026-06-22-009-feat-golden-fixture-ladder-plan.md` — full implementation plan with 8 implementation units across 4 phases
- `docs/brainstorms/2026-06-22-golden-fixture-ladder-requirements.md` — 20 requirements (R1–R20) driving the ladder design
- `docs/brainstorms/2026-06-22-dsn-universal-seam-requirements.md` — Ideation #1: DSN/SES serialization layer (foundation for golden serializers)
- `docs/brainstorms/2026-06-22-unified-stage-protocol-requirements.md` — Ideation #3: typed StageInput/StageOutput (drives serializer signatures)
- `packages/temper-placer/src/temper_placer/io/golden_serializers.py` — deterministic DSN, SES, JSON serialization functions
- `docs/solutions/architecture-patterns/ci-profiling-platform-canonical-metrics-contract-2026-06-28.md` — the golden check lives alongside profiling in CI; the profiling platform provides the time-series store, PR comparison, and dashboard that golden fixtures benefit from
- `packages/temper-placer/src/temper_placer/testing/golden_diff.py` — geometric diff engine with coordinate tolerance thresholds
- `packages/temper-placer/src/temper_placer/io/boundary_registry.py` — registered stage boundaries with per-boundary tolerance
- `packages/temper-placer/src/temper_placer/testing/ladder_growth.py` — incremental ladder growth validation (non-breaking additions)
- `packages/temper-placer/tests/testing/test_golden_diff.py` — 13 test scenarios covering identical, shifted, missing-net, empty-golden, and unknown-format cases
- `packages/temper-placer/tests/io/test_dsn_integration.py` — end-to-end DSN export, normalize, embed-hash, validate, and deterministic byte-identical tests
- `packages/temper-placer/tests/router_v6/test_stage2_golden_parity.py` — Router V6 Stage 2 golden parity tests for 4 canonical boards across 8 micro-stages
- `packages/temper-placer/tests/router_v6/generate_stage2_goldens.py` — golden fixture generation for Router V6 Stage 2 micro-stages
- `power_pcb_dataset/golden_manifest.yaml` — board registry for golden generation (board ID, path, baseline commit)
- `packages/temper-placer/src/temper_placer/cli/dsn_commands.py` — `temper dsn generate`, `check`, `export`, `validate` commands
- `packages/temper-testing/src/temper_testing/golden.py` — generic golden/snapshot testing utilities (underlying `GoldenComparison` dataclass pattern)
- `docs/solutions/architecture-patterns/ci-gate-quality-enforcement.md` — CI gate meta-pattern (baseline + monotonic shrink) that the golden gate instantiates
