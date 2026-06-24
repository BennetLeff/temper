# V5→V6 A* Migration Path

**Created:** 2026-06-24  
**Status:** Deferred — requires `sequential_routing.py` migration

## Blocked Modules

Three V5 A* modules cannot be deleted until the active routing stage is migrated:

| File | Lines | Deprecated? | Blocked By |
|------|-------|-------------|------------|
| `packages/temper-placer/src/temper_placer/deterministic/stages/multilayer_astar.py` | 663 | Parameters only | `sequential_routing.py` |
| `packages/temper-placer/src/temper_placer/deterministic/stages/bidirectional_astar.py` | 391 | No marker | `sequential_routing.py` |
| `packages/temper-placer/src/temper_placer/routing/astar/` | 50 | Shim | Both V5 A* files |

## Import Chain

```
create_drc_aware_pipeline() (deterministic/__init__.py)
  └─ SequentialRoutingStage (sequential_routing.py, 2,152 lines)
       ├─ MultiLayerAStar (multilayer_astar.py) — primary pathfinder, line 7
       │    └─ RouteSegment, MultiLayerPath (routing/astar/)
       └─ BidirectionalAStar (bidirectional_astar.py) — long-route pathfinder, line 1602
            └─ RouteSegment, MultiLayerPath (routing/astar/)
```

## API Gap

V5 and V6 use fundamentally different interfaces:

- **V5** (`MultiLayerAStar.find_path`): point-to-point — `find_path(start, end, start_layer, end_layer) → MultiLayerPath`
- **V6** (`run_astar_pathfinding`): board-level batch — `run_astar_pathfinding(channel_mapping, grid, ...) → PathfindingResult`

V6 has independent types (`RoutePath`, `RoutePath3D`, `RouteNode3D` in `router_v6/astar_core.py`). The `routing/astar/` README misleadingly claims types are "shared by both" — V6 imports nothing from `routing.astar`.

## Files Deletable After Migration

Once `sequential_routing.py` is migrated to V6:

- `packages/temper-placer/src/temper_placer/deterministic/stages/multilayer_astar.py`
- `packages/temper-placer/src/temper_placer/deterministic/stages/bidirectional_astar.py`
- `packages/temper-placer/src/temper_placer/routing/astar/` (3 files)
- `packages/temper-placer/tests/deterministic/test_multilayer_path_reconstruction.py`
- `packages/temper-placer/tests/routing/test_bidirectional_astar.py`
- `packages/temper-placer/tests/routing/test_cython_integration.py`
- `packages/temper-placer/tests/routing/test_heuristic_numba_manual.py`

**Total:** ~1,100 lines source + ~800 lines tests deleted.

## Also Deletable (Circular Dependency Cleanup)

`sequential_routing.py` also imports from `router_v6` (creating a documented circular dependency worked around by PEP 562 lazy loading in `router_v6/__init__.py`). Once `sequential_routing.py` is V6-native, the lazy-loader workaround can be removed.

## References

- V6 pathfinder: `packages/temper-placer/src/temper_placer/router_v6/astar_pathfinding.py`
- V6 core types: `packages/temper-placer/src/temper_placer/router_v6/astar_core.py`
- Plan doc: `docs/plans/2026-06-24-002-chore-remaining-bloat-cleanup-plan.md`
