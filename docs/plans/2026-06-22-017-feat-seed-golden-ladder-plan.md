---
title: "feat: Seed Golden Ladder — 32 Stage 2 Micro-Stage Fixtures"
type: feat
status: active
date: 2026-06-22
origin: docs/ideation/2026-06-22-test-and-build-next-ideation.md
depends_on:
  - docs/plans/2026-06-22-009-feat-golden-fixture-ladder-plan.md
---

# feat: Seed Golden Ladder — 32 Stage 2 Micro-Stage Fixtures

## Summary

Populate the golden fixture ladder (plan 009) with fixtures for all 8 Stage 2
placement micro-stages across 4 canonical boards (32 fixtures). Wire a CI diff
gate so any PR diverging from golden output beyond geometric tolerance blocks
merge. Fixtures <100 KB each; DSN for geometric stages, JSON for analysis stages.

## Problem

Plan 009 defines the golden ladder architecture but populates nothing:
`power_pcb_dataset/goldens/temper/` has only `README.md`. The 8 Stage 2
placement micro-stages produce BoardState at each boundary — zero of 32 needed
fixtures exist. Without golden fixtures, the strangler fig extraction safety net
is non-functional for the placement pipeline.

## Scope

| Item | Status |
|------|--------|
| 8 Stage-2 micro-stage boundary registry entries | New |
| Golden CLI `generate` / `check` subcommand | New (harnesses existing serializers + diff engine) |
| 32 golden fixtures (8 stages x 4 boards) | New — `power_pcb_dataset/goldens/<board>/<stage>.<ext>` |
| CI diff gate `.github/workflows/golden-check.yml` | Rewrite (existing targets `temper dsn check` — replace with `temper golden check`) |
| `power_pcb_dataset/goldens/manifest.yaml` | New — fixture index with board/stage/git_hash/format_version |

**Deferred:** PipelineOrchestrator boundaries, RouterV6 boundaries, remaining
DeterministicPipeline stages (Stage 3/4/5), `# @req` traceability annotations.

## Stage 2 Micro-Stages (8 Boundaries)

These are the placement-phase stages from `create_drc_aware_pipeline()` in
`packages/temper-placer/src/temper_placer/deterministic/__init__.py:207`:

| # | Boundary Name | Stage Class | Output | Format |
|---|---------------|-------------|--------|--------|
| 1 | `zone_geometry` | `ZoneGeometryStage` | Zone shapes, computed layout regions | DSN |
| 2 | `zone_assignment` | `ZoneAssignmentStage` | Components assigned to zones | DSN |
| 3 | `slot_generation` | `ZoneAwareSlotGenerationStage` | Slot placement grid | DSN |
| 4 | `component_assignment` | `PhasedComponentAssignmentStage` | Components assigned to slots | DSN |
| 5 | `apply_placements` | `ApplyPlacementsStage` (first) | Components placed on board | DSN |
| 6 | `courtyard_check` | `CourtyardCheckStage` | After overlap/clamping resolution | DSN |
| 7 | `apply_placements_reapply` | `ApplyPlacementsStage` (re-apply post-clamp) | Final placement state before routing | DSN |
| 8 | `placement_validation` | `PlacementValidationStage` | Violation list (HV clearance, proximity) | JSON |

**Tolerance:** `1e-3 mm` for DSN coordinates, `1e-3 mm` for JSON numeric fields.

## Canonical Boards (4)

| ID | Path | Description |
|----|------|-------------|
| `temper_placed` | `pcb/temper_placed.kicad_pcb` | Placed, not routed (~74 components) |
| `temper_routable` | `pcb/temper_routable.kicad_pcb` | Full routing-ready (~74 components) |
| `temper_ready_for_route` | `pcb/temper_ready_for_route.kicad_pcb` | Ready for routing pass |
| `temper_optimized_hq` | `pcb/temper_optimized_hq.kicad_pcb` | HQ optimized placement |

## Implementation Units

### U1. Extend Boundary Registry for Stage 2 Micro-Stages

**Goal:** Add 8 Stage 2 placement boundaries to `stage_boundaries.yaml` and
register them in `boundary_registry.py`. Wire serializers.

**Files:**
- `packages/temper-placer/src/temper_placer/io/boundary_registry.py` — add 8 Stage 2 `BoundaryDef` entries
- `power_pcb_dataset/stage_boundaries.yaml` — create with the 8 boundaries (new file, or extend if exists)

Each boundary maps to a serializer function already in `golden_serializers.py`:
DSN boundaries → `serialize_boardstate_to_dsn`, JSON boundaries →
`serialize_violations_to_json`.

**Test:** All 8 boundary names resolve to importable serializers with correct `output_format`.

### U2. Create Golden CLI (`temper golden generate` / `temper golden check`)

**Goal:** Add `golden` CLI command group with `generate` and `check` subcommands
that leverage existing `golden_serializers.py` (serialization) and
`golden_diff.py` (diff engine). Uses the legacy pipeline (`create_legacy_pipeline()`)
for fixture generation to avoid DRC metadata requirements.

**Files:**
- `packages/temper-placer/src/temper_placer/cli/golden.py` — new
- `packages/temper-placer/src/temper_placer/cli/__init__.py` — register `golden` command

**`generate` flow:**
1. Parse PCB via `parse_kicad_pcb()` → `Board` + `Netlist`
2. Build pipeline with only the target stage boundary's preceding stages
3. Run pipeline → `BoardState` at boundary
4. Serialize via `golden_serializers.SERIALIZER_REGISTRY[name](state)` → `str`
5. Write to `power_pcb_dataset/goldens/<board>/<stage>.<ext>`
6. Update `goldens/manifest.yaml` with fixture metadata + `git rev-parse HEAD`

**`check` flow:**
1. Load `goldens/manifest.yaml` → fixture list
2. For each fixture: re-run pipeline, serialize, diff against committed golden via `diff_golden()`
3. Aggregate `DiffReport`; exit 0 if all pass, 1 on any BEYOND_TOLERANCE or BINARY
4. `--json` flag outputs structured `DiffReport.to_json()` for CI annotations

**Flags:** `--stage`, `--board`, `--all-boards`, `--all-stages`, `--json`, `--verbose`.

**Performance:** Single fixture <10 sec; full ladder (32 fixtures) <4 min.

### U3. Generate and Commit 32 Golden Fixtures

**Goal:** Run `temper golden generate --all-boards --all-stages` once to produce
all 32 fixtures, then commit them.

**Directory structure:**
```
power_pcb_dataset/goldens/
  manifest.yaml
  temper_placed/
    zone_geometry.dsn
    zone_assignment.dsn
    slot_generation.dsn
    component_assignment.dsn
    apply_placements.dsn
    courtyard_check.dsn
    apply_placements_reapply.dsn
    placement_validation.json
  temper_routable/
    ... (same 8)
  temper_ready_for_route/
    ... (same 8)
  temper_optimized_hq/
    ... (same 8)
```

**Size constraint:** Each DSN fixture <100 KB; JSON <10 KB.
Verify with `find power_pcb_dataset/goldens -type f -size +100k` returns nothing.

**`goldens/manifest.yaml` schema:**
```yaml
format_version: 1
fixtures:
  - board: temper_placed
    stage: zone_geometry
    pipeline: DeterministicPipeline
    output_format: dsn
    file: goldens/temper_placed/zone_geometry.dsn
    git_hash: "<sha>"
    format_version: 1
    first_added_at: "2026-06-22T..."
    first_added_hash: "<sha>"
```

### U4. Rewrite CI Workflow

**Goal:** Replace the existing `.github/workflows/golden-check.yml` (which
calls `temper dsn check` and targets old-style DSN boundaries) with a new
workflow that runs `temper golden check` on all fixtures.

**Current state (to replace):** Targets 5 `PipelineOrchestrator` boundaries
(semantic, topological, placement, routing, validation) via `temper dsn check`.
These boundaries have no golden files.

**New workflow:**
```yaml
name: Golden Fixture Check
on:
  push:
    branches: [main]
    paths:
      - 'packages/temper-placer/**'
      - 'power_pcb_dataset/goldens/**'
      - '.github/workflows/golden-check.yml'
  pull_request:
    branches: [main]
    paths:
      - 'packages/temper-placer/**'
      - 'power_pcb_dataset/goldens/**'
      - '.github/workflows/golden-check.yml'
jobs:
  golden-check:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: astral-sh/setup-uv@v4
      - run: uv sync --all-packages
      - run: uv run temper golden check --json
```

**Matrix strategy:** Optionally split by board (4 parallel jobs × 8 stages each)
if single-job runtime exceeds 5 minutes.

### U5. Self-Verification: Regeneration Reproducibility

**Goal:** Verify that regeneration produces byte-identical output (same machine,
same code). Verify CI diff gate catches intentional divergence.

**Steps:**
1. Run `temper golden check` — must exit 0 (all 32 pass)
2. Run `temper golden generate --all-boards --all-stages` — must produce files identical to committed goldens (same SHAs)
3. Inject a 2mm coordinate shift in `ApplyPlacementsStage` → `temper golden check` must exit 1 with BEYOND_TOLERANCE for `apply_placements` and `apply_placements_reapply` boundaries
4. Revert shift → `temper golden check` exits 0

## Existing Assets (Already Implemented)

| Module | Path | Status |
|--------|------|--------|
| DSN/SES/JSON serializers | `golden_serializers.py` | Complete — 4 serializers + registry |
| Geometric diff engine | `golden_diff.py` | Complete — DSN/SES/JSON diff with tolerance |
| Boundary registry | `boundary_registry.py` | Has 5 basic boundaries; needs Stage 2 entries |
| Stage 2 micro-stages | `deterministic/stages/*.py` | Complete — all 8 stage classes |
| Legacy pipeline factory | `create_legacy_pipeline()` | Complete — usable without DRC metadata |
| `golden_manifest.yaml` | `power_pcb_dataset/` | Has 1 board entry; needs 3 more |

## Dependencies

- **Plan 009** (golden fixture ladder) — architecture decisions (K1–K9, R1–R20)
  defined there; this plan populates the first rung.
- **`golden_serializers.py`** — serializer functions exist; no code changes needed.
- **`golden_diff.py`** — diff engine exists; may need SES coordinate parsing
  fixes for the Stage 2 boundaries (Stage 2 outputs DSN/JSON, not SES, so
  likely no changes needed).

## Risks

| Risk | Mitigation |
|------|------------|
| Pipeline needs config/DRC metadata to produce meaningful state | Use `create_legacy_pipeline()` which requires no metadata; Stage 2 micro-stages from legacy pipeline cover all 8 placement boundaries |
| SES boundaries not needed for Stage 2 | Stage 2 placement stages produce DSN/JSON only — no SES wiring yet |
| Fixtures >100 KB | Verify size post-generation; if >100 KB, configure `DSNExporter` to omit non-semantic detail |
| 4 canonical boards share config template but have different layouts | Each board supplies its own KiCad metadata — legacy pipeline adapts per-board automatically |

## Success Criteria

- `ls power_pcb_dataset/goldens/temper_placed/ | wc -l` → 8
- `ls power_pcb_dataset/goldens/ | grep -v manifest | grep -v README | wc -l` → 4 (boards)
- Total fixtures: 32 files across 4 board directories
- `temper golden check` exits 0 on clean checkout
- `.github/workflows/golden-check.yml` triggers on `packages/temper-placer/**` changes
- Every DSN fixture <100 KB
- Intentional pipeline change → CI fails with BEYOND_TOLERANCE for affected stage(s)
- Regeneration in same PR → CI passes (golden manually regenerated and committed)

## Sources

- Plan 009: `docs/plans/2026-06-22-009-feat-golden-fixture-ladder-plan.md`
- Ideation: `docs/ideation/2026-06-22-test-and-build-next-ideation.md` (idea #2)
- Golden serializers: `packages/temper-placer/src/temper_placer/io/golden_serializers.py`
- Diff engine: `packages/temper-placer/src/temper_placer/testing/golden_diff.py`
- Pipeline: `packages/temper-placer/src/temper_placer/deterministic/__init__.py`
- Legacy pipeline: `create_legacy_pipeline()` in `deterministic/__init__.py:271`
