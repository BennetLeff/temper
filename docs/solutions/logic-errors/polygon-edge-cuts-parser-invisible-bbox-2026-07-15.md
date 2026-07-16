---
title: "Edge.Cuts polygon outline invisible to board bounding-box parser"
module: "packages/temper-placer/src/temper_placer/io/kicad_parser.py"
date: "2026-07-15"
problem_type: logic_error
component: tooling
severity: high
symptoms:
  - "board width/height = -inf from parse_kicad_pcb on production board"
  - "all component positions read as (-inf, -inf) before pipeline runs"
  - "zone geometry fallback zones all carry -inf bounds"
  - "slot grid generates zero slots; KD-tree crashes on non-finite pad centers"
root_cause: logic_error
resolution_type: code_fix
tags:
  - kicad
  - polygon
  - edge-cuts
  - bounding-box
  - parser
  - silent-failure
---

# Edge.Cuts polygon outline invisible to board bounding-box parser

## Problem

`_extract_board_geometry` in `kicad_parser.py` only consumed Edge.Cuts items with `start`/`end` attributes (`gr_rect`, `gr_line`). The generated production board's outline is a `gr_poly` with a `coordinates` list -- the bounding-box loop skipped it entirely, producing `-inf` for width and height.

## Symptoms

- `parse_kicad_pcb('pcb/temper.kicad_pcb')` returned `board.width = -inf`, `board.height = -inf`
- All 100 component `initial_position` values were `(-inf, -inf)`
- The zone-free fallback in `ZoneGeometryStage` built zones with `-inf` bounds, producing zero placement slots
- `drc_oracle_setup` crashed on non-finite pad centers in the KD-tree
- The "No Edge.Cuts found -> use 100x150 default" guard at line 218 was unreachable because `edge_cuts` was NON-empty (the `gr_poly` existed on the Edge.Cuts layer)

## What Didn't Work

- **Zone-free fallback theory.** The handoff suspected the default zone geometry fallback required an explicit config. Instrumentation proved it works correctly -- it was fed `-inf` dimensions from the parser.
- **The existence guard at line 218.** `if not edge_cuts: return Board.temper_default()` was a false safety net. A non-empty-but-unparseable list sailed right past it.

## Solution

Extended the coordinate-collection loop to handle three geometry types, and added a post-loop finiteness guard:

```python
for item in edge_cuts:
    if hasattr(item, "start") and hasattr(item, "end"):
        for pt in [item.start, item.end]:
            if pt is not None:
                x_min = min(x_min, pt.X); x_max = max(x_max, pt.X)
                y_min = min(y_min, pt.Y); y_max = max(y_max, pt.Y)

    if hasattr(item, "coordinates") and item.coordinates:
        for pt in item.coordinates:
            x_min = min(x_min, pt.X); x_max = max(x_max, pt.X)
            y_min = min(y_min, pt.Y); y_max = max(y_max, pt.Y)

    if hasattr(item, "mid") and item.mid is not None:
        for pt in [item.start, item.mid, item.end]:
            if pt is not None:
                x_min = min(x_min, pt.X); x_max = max(x_max, pt.X)
                y_min = min(y_min, pt.Y); y_max = max(y_max, pt.Y)

if not (math.isfinite(x_min) and math.isfinite(x_max)
        and math.isfinite(y_min) and math.isfinite(y_max)):
    warnings.append(
        "Edge.Cuts geometry present but has no parseable coordinate data. "
        "Falling back to Board.temper_default()."
    )
    return Board.temper_default()
```

Three changes:
1. Added `gr_poly` handling via `item.coordinates`
2. Added `gr_arc` handling via `item.start`/`item.mid`/`item.end`
3. Post-loop finiteness guard converts silent `-inf` propagation into an explicit fallback

## Why This Works

The root cause is a shape-type blind spot: the loop assumed Edge.Cuts geometry is exclusively line-segment-based (`gr_rect`, `gr_line`), but a production board outline is typically a `gr_poly` -- defined by a `coordinates` list, not `start`/`end` pairs. The loop implicitly skipped `gr_poly` items, contributing nothing to the min/max accumulators.

The post-loop finiteness guard catches the case where Edge.Cuts items exist but none had parseable coordinates, triggering the safe default fallback instead of propagating `-inf` through every downstream pipeline stage.

This is the fourth bug of the same family in `kicad_parser.py` -- all were shape-handling gaps that a single end-to-end smoke test with a finiteness assertion would have caught at parse time.

## Prevention

**Production-board smoke test** (`packages/temper-placer/tests/io/test_production_board_smoke.py`, 4 tests):

```python
def test_production_board_parses_with_finite_bbox():
    result = parse_kicad_pcb("pcb/temper.kicad_pcb")
    assert result.board.width > 0
    assert result.board.height > 0
    assert math.isfinite(result.board.width)

def test_all_parsed_positions_are_finite():
    for comp in result.netlist.components:
        px, py = comp.initial_position
        assert math.isfinite(px), f"{comp.ref} x={px} is not finite"
        assert math.isfinite(py)

def test_production_board_component_count_matches_netlist():
    assert len(result.netlist.components) >= 90

def test_production_board_has_no_malformed_warnings():
    for w in result.warnings:
        assert "fell back" not in w.lower()
```

**Practices:**
- Post-loop finiteness assertion on any accumulator that feeds downstream geometry
- When adding a new KiCad geometry type, audit all loops that iterate Edge.Cuts items for shape-type coverage
- Run the smoke test on every push (already in CI via `python-tests.yml` checks job)

## Related

- `docs/solutions/logic-errors/baseline-extractor-four-silent-fail-metrics-2026-07-01.md` -- same silent-failure family; directly inspired the smoke test pattern
- `docs/solutions/logic-errors/off-center-pad-offset-defeats-centered-bounds-2026-07-08.md` -- same file, same class (parser geometry primitive coverage gap)
- `docs/solutions/architecture-patterns/silent-guard-condition-c-cap-indentation-2026-07-02.md` -- the non-finite guard + fallback is an instance of the pattern
- `packages/temper-placer/tests/io/test_production_board_smoke.py` -- the prevention smoke test
