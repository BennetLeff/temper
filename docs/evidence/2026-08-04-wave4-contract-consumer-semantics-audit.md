# Wave-4 Board/Netlist Consumer-Semantics Audit — Evidence Record

**Date:** 2026-08-04
**Plan:** `docs/plans/2026-08-03-003-feat-wave4-phase3-first-pulls-plan.md` (U4, D3, R11)
**Base:** origin/main f2b09d846
**Counting rule:** modules with `from temper_placer.core.board import` /
`from temper_placer.core.netlist import` statements in
`packages/temper-placer/src/temper_placer/`, excluding `__init__.py`
re-exports. Recorded so later pulls can reproduce it (plan U4). The
reproducible source is the grep command itself; the lists below are its
complete output.

## Enumeration

- Board importers: **66**
- Netlist importers: **76**
- Overlap (import both): **48**
- Unique consumers: **94**

### Board importers (66)

`_constraint_types/config.py` `constraints/compiler.py` `core/interfaces.py` `core/state.py` `deterministic/stages/_grid_hv.py`
`deterministic/state.py` `fixtures/synthetic.py` `heuristics/base.py` `heuristics/mcu_subsystem.py` `heuristics/organizational.py`
`heuristics/pipeline.py` `heuristics/structural.py` `heuristics/style.py` `io/_kicad_types.py` `io/_parse_board.py`
`io/_parse_zones.py` `io/config_loader.py` `io/dsn_exporter.py` `io/dsn_schema.py` `io/kicad_exporter.py`
`io/kicad_parser.py` `io/reference_loader.py` `io/snapshot.py` `manufacturing/stackup_validator.py` `metrics/external_oracle.py`
`metrics/physics.py` `metrics/quality.py` `pcl/constraints.py` `pcl/linter.py` `pcl/parser.py`
`pcl/resolver.py` `pcl/sat_bridge.py` `physics/copper_coverage.py` `pipeline/dag_types.py` `pipeline/feedback.py`
`pipeline/iterator.py` `pipeline/topology_phase.py` `placer/adjustment.py` `placer/cp_sat/_encoder_solve.py` `placer/cp_sat/_loop_core.py`
`placer/deterministic.py` `profiling/validation/invariants.py` `router_v6/_adapter_core.py` `router_v6/_pipeline_verify.py` `router_v6/astar_core.py`
`router_v6/bottleneck_geometry.py` `router_v6/congestion.py` `router_v6/constraints_drc_oracle.py` `router_v6/copper_balance.py` `router_v6/escape_via_generator.py`
`router_v6/power_plane.py` `router_v6/stage0_data.py` `router_v6/thermal_relief.py` `router_v6/verifier.py` `topological/force_refinement.py`
`topological/initial_placement.py` `topological/zone_solver.py` `validation/base.py` `validation/drc.py` `validation/geometric.py`
`validation/manufacturing.py` `validation/metrics.py` `validation/preflight.py` `validation/spice_pipeline.py` `validation/spice.py`
`validation/trace_analyzer.py`

### Netlist importers (76)

`constraints/compiler.py` `core/community.py` `core/graph.py` `core/interfaces.py` `core/loop_extractor_rs.py`
`core/loop_extractor.py` `core/loop_ownership.py` `core/pin_geometry.py` `core/routing_validator.py` `core/state.py`
`deterministic/stages/_phase_core.py` `deterministic/stages/_phase_rotation.py` `deterministic/stages/_phase_zones.py` `deterministic/state.py` `extraction/hypergraph_factory.py`
`fixtures/synthetic.py` `heuristics/base.py` `heuristics/graph_utils.py` `heuristics/mcu_subsystem.py` `heuristics/organizational.py`
`heuristics/pipeline.py` `heuristics/structural.py` `heuristics/style.py` `io/_kicad_types.py` `io/_parse_modules.py`
`io/_parse_nets.py` `io/config_loader.py` `io/dsn_exporter.py` `io/dsn_schema.py` `io/kicad_parser.py`
`io/net_class_manager.py` `io/reference_loader.py` `io/snapshot.py` `metrics/external_oracle.py` `metrics/physics.py`
`metrics/quality.py` `pcl/_tag_expanders.py` `pcl/constraints.py` `pcl/linter.py` `pcl/parser.py`
`pcl/resolver.py` `pcl/sat_bridge.py` `pcl/tag_dispatch.py` `pipeline/dag_types.py` `pipeline/derivation.py`
`pipeline/feedback.py` `pipeline/iterator.py` `pipeline/topology_phase.py` `placer/adjustment.py` `placer/cp_sat/_loop_core.py`
`placer/cp_sat/isolation_barrier.py` `placer/deterministic.py` `profiling/validation/invariants.py` `router_v6/_adapter_core.py` `router_v6/benchmark.py`
`router_v6/congestion.py` `router_v6/constraint_model.py` `router_v6/dense_package_detection.py` `router_v6/escape_via_generator.py` `router_v6/layer_assignment.py`
`router_v6/net_ordering.py` `router_v6/obstacle_map.py` `router_v6/power_plane.py` `router_v6/stage0_data.py` `router_v6/verifier.py`
`validation/base.py` `validation/drc.py` `validation/geometric.py` `validation/manufacturing.py` `validation/metrics.py`
`validation/netlist_reconciliation.py` `validation/placement_roundtrip.py` `validation/preflight.py` `validation/spice_pipeline.py` `validation/spice.py`
`validation/tht_check.py`

### Overlap (48)

`constraints/compiler.py` `core/interfaces.py` `core/state.py` `deterministic/state.py` `fixtures/synthetic.py`
`heuristics/base.py` `heuristics/mcu_subsystem.py` `heuristics/organizational.py` `heuristics/pipeline.py` `heuristics/structural.py`
`heuristics/style.py` `io/_kicad_types.py` `io/config_loader.py` `io/dsn_exporter.py` `io/dsn_schema.py`
`io/kicad_parser.py` `io/reference_loader.py` `io/snapshot.py` `metrics/external_oracle.py` `metrics/physics.py`
`metrics/quality.py` `pcl/constraints.py` `pcl/linter.py` `pcl/parser.py` `pcl/resolver.py`
`pcl/sat_bridge.py` `pipeline/dag_types.py` `pipeline/feedback.py` `pipeline/iterator.py` `pipeline/topology_phase.py`
`placer/adjustment.py` `placer/cp_sat/_loop_core.py` `placer/deterministic.py` `profiling/validation/invariants.py` `router_v6/_adapter_core.py`
`router_v6/congestion.py` `router_v6/escape_via_generator.py` `router_v6/power_plane.py` `router_v6/stage0_data.py` `router_v6/verifier.py`
`validation/base.py` `validation/drc.py` `validation/geometric.py` `validation/manufacturing.py` `validation/metrics.py`
`validation/preflight.py` `validation/spice.py` `validation/spice_pipeline.py`

## Access-pattern inventory

Counts measured 2026-08-04 on the 94 consumers.

| Pattern class | Sites | Representative evidence (file:line at f2b09d846) |
|---|---|---|
| Container iteration (`for x in obj.nets/components/pins/...`) | 525 | `router_v6/verifier.py:161` `[n.name for n in netlist.nets]`; `core/community.py:119` `enumerate(netlist.components)` |
| `len()` / integer indexing | 106 | `placer/adjustment.py:53` `range(len(netlist.components))`; `validation/metrics.py:279` `netlist.components[i]` |
| Attribute reads (fields, properties) | pervasive | `placer/adjustment.py:54` `netlist.components[i].fixed`; `validation/metrics.py:316` `board.width * board.height`; `board.get_zone(comp.zone)` |
| Constructor call sites | 85 | `io/kicad_parser.py`, `io/config_loader.py`, `io/_parse_board.py`, `fixtures/synthetic.py`, `router_v6/constraint_model.py` |
| Getter-method calls (`get_*`, index lookups) | heavy | `core/community.py:98` `netlist.get_component_index(ref)`; `netlist.get_component/get_net/get_component_nets` |
| numpy float32 surface (KTD6: shim-kept) | 14 | `validation/metrics.py:158` `netlist.get_bounds_array()`; `validation/geometric.py:132` `netlist.get_bounds_array() # (N, 2)`; `router_v6/routing_space.py:138` `board.get_bounds_array()`; `core/community.py:57,119` `build_adjacency_matrix(netlist)` |
| Dunders: `repr`/`str` on contracts | few | debug/status paths (`visualization/status_report.py`) |
| Identity checks (`x is ...`) on contracts | 0 | — |
| Monkeypatch surfaces on `core.board`/`core.netlist` | 0 | verified across `src/` and `tests/` (L10: no re-export band-aid needed) |

## Enum semantics note (KTD2)

`LayerIndex` (IntEnum, `core/board.py`) is consumed as the layer SSOT: its
`__str__` returns the KiCad name and `.name` returns the enum name. Per
KTD2 the pyclass reproduces member identity, `__str__`, `members()`, and
value getters; int-comparison becomes a documented deviation, and any
consumer doing `LayerIndex.X == int` is adapted inside the migration PR
(the priority.py precedent: "IntEnum members are NOT equal to their int
value").

## Resolution slots (R11)

Each enumerated pattern resolves to one of: **reproduced** (pyclass
reproduces it), **consumer-adapted** (consumer changed inside the migration
PR), **shim-kept** (numpy wrappers / Python helpers per R10/KTD6/KTD7), or
**documented deviation** (KTD2 IntEnum int-comparison). The committed
catalog in `packages/temper-design-bundle/VERIFICATION.md` carries the
slot per pattern class; U5/U6 differentials key their pins to it.
