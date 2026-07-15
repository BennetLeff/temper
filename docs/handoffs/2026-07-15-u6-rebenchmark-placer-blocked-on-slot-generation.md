# Re-benchmark Placer Handoff — Zone-Free Slot Generation Produces Zero Placements

Date: 2026-07-15
Plan: [docs/plans/2026-07-15-001-feat-artifact-identity-provenance-plan.md](../plans/2026-07-15-001-feat-artifact-identity-provenance-plan.md), unit U6
Branch: `feat/rebenchmark-production-board` (based on `feat/gen-pcb-skeleton`, PR #210 — not yet merged to `main`)
Related: [docs/solutions/logic-errors/deterministic-placer-pipeline-post-jax-retirement-stubs.md](../solutions/logic-errors/deterministic-placer-pipeline-post-jax-retirement-stubs.md)
Blocker for: U6 (re-baseline placer/router metrics against the real ~100-component production board, retire the last quarantined fixture)

## Goal

Run `temper_placer.deterministic.create_drc_aware_pipeline()` against the real production board (`pcb/temper.kicad_pcb`, from `feat/gen-pcb-skeleton`), regenerate `power_pcb_dataset/corpus/temper/baseline.json`, and retire `pcb/benchmarks/temper_fixture_33.kicad_pcb`.

## What's already fixed and merged on this branch (commit `2afcc301`)

Three real, standalone bugs were blocking the pipeline from completing on **any** board, not just this one — see the linked solution doc for full detail:

1. `deterministic/stages/setup.py` — `net_class_setup` called `.name` on an already-plain string.
2. `deterministic/stages/placement_validation.py` — constructor defaulted to `list` but the class's own methods call dict-only `.get()`; the call site had a `# type: ignore[arg-type]` sitting directly on top of the bug.
3. `validation/drc_runner.py` — missing `from dataclasses import field`.

**Verified fix**: `create_drc_aware_pipeline()` now runs all 22 stages end-to-end against the quarantined 33-component fixture, producing 33/33 real placements (previously crashed at stage 11). `packages/temper-placer/tests/deterministic/` is 306 passed / 1 skipped / 2 pre-existing unrelated errors (fixture-name typos, `_caplog`/`_tmp_path`).

## Current blocker

Running the same pipeline against the real ~100-component board (`pcb/temper.kicad_pcb`) with **no config** (the only existing config, `configs/temper_deterministic_config.yaml`, is authored against the old fixture's refs — `Q1`, `U_GATE`, `C_BUS1`, etc. — and matches literally zero of the real board's `U1`..`U100` refs) produces **zero valid placements for all 100 components**. Every position comes out `(-inf, -inf)` after `zone_aware_slot_generation` / `component_assignment`, which then crashes `drc_oracle_setup` when it tries to build a KD-tree over pad positions:

```
ValueError: data must be finite, check for nan or inf values
  File ".../router_v6/constraints_spatial_index.py", line 194, in rebuild_index
    self._pad_index = cKDTree(centers)
```

### Reproduction

```python
from pathlib import Path
from temper_placer.deterministic import BoardState, create_drc_aware_pipeline
from temper_placer.io.kicad_metadata import extract_kicad_metadata
from temper_placer.io.kicad_parser import parse_kicad_pcb

pcb_path = Path("pcb/temper.kicad_pcb")
parse_result = parse_kicad_pcb(pcb_path)
metadata = extract_kicad_metadata(pcb_path)
pipeline = create_drc_aware_pipeline(design_rules=None, config=None, metadata=metadata, zone_aware=True)

state = BoardState(board=parse_result.board, netlist=parse_result.netlist)
for stage in pipeline.stages[:8]:  # through apply_placements
    state = stage.run(state)
print(len(state.placements))  # 0 — expected: 100
```

## What was ruled out

- **Not the fixture-config mismatch alone.** Re-ran with `config=None, design_rules=None` entirely (bypassing the fixture config's irrelevant zone/group refs) — still zero placements. The pipeline correctly switches to `component_assignment` (the config-free stage) instead of `phased_component_assignment`, confirmed via `pipeline.stages` names, but that stage itself produces nothing for a 100-component board with no defined zones.
- **Not a board-parsing problem.** `parse_kicad_pcb` correctly reports 100 components, matches the oracle's independent count from the PCB-skeleton-generation work.
- **Not the same class of bug as the three already fixed.** Those were type mismatches with one-line fixes; this is zero output from what looks like a real algorithmic path (slot generation / zone-free fallback) that may never have been exercised with this many components and zero zones simultaneously — the "minimal" corpus board (4 components) and the 33-component fixture (which does have a real, if fixture-specific, config with zones) are the only boards this path has likely ever run against.

## Most promising next step

Trace `zone_aware_slot_generation` and `component_assignment` (`packages/temper-placer/src/temper_placer/deterministic/stages/`) to find where a component with no matching zone is supposed to fall back to *something* (a default/catch-all zone, or the board's full bounds) — the 33-component fixture case proves a fallback path exists and works for at least a handful of unmatched components (6 components were "not found" in that run and still got placed), but it apparently doesn't work when **all** components take the fallback path simultaneously. Suspect an off-by-something in how the "no zones matched" case initializes the slot grid or default zone bounds — worth checking whether `zone_aware_slot_generation` requires at least one *explicit* zone to exist before it will generate any slots at all, vs. deriving a default zone from `metadata`/board dimensions when none are configured.

A real, populated config for the production board (zones covering the real `U1`-`U100` refs, at minimum a single default zone spanning the whole board) would likely also route around this without needing an algorithm fix — but authoring one requires real circuit-domain knowledge (which components are HV vs LV, which form the gate-drive group, etc.) that shouldn't be guessed at. Worth deciding which path to take before diving further: fix the zero-zone fallback path in code, or author a minimal real config.

## Build + test after fix

```bash
uv run python3 -c "
from pathlib import Path
from temper_placer.deterministic import BoardState, create_drc_aware_pipeline
from temper_placer.io.kicad_metadata import extract_kicad_metadata
from temper_placer.io.kicad_parser import parse_kicad_pcb
pcb_path = Path('pcb/temper.kicad_pcb')
parse_result = parse_kicad_pcb(pcb_path)
metadata = extract_kicad_metadata(pcb_path)
pipeline = create_drc_aware_pipeline(design_rules=None, config=None, metadata=metadata, zone_aware=True)
state = BoardState(board=parse_result.board, netlist=parse_result.netlist)
for stage in pipeline.stages:
    state = stage.run(state)
print('placements:', len(state.placements))  # must be 100
"
```

Once that produces 100/100 finite placements, resume U6 proper:

```bash
cp pcb/temper.kicad_pcb power_pcb_dataset/corpus/temper/temper.kicad_pcb
uv run python3 scripts/extract_corpus_baselines.py --board temper   # this script is ALSO stale (imports temper_placer.losses, deleted) — port to create_drc_aware_pipeline or use temper_placer.regression.cli directly
```

Board target size (`power_pcb_dataset/corpus/temper/constraints.yaml`, currently 100×150mm) does **not** need to change — confirmed via courtyard-area density check: even at a conservative 30% packing density, the real ~100-component design needs ~12,000mm², comfortably under the 15,000mm² the existing target already provides.
