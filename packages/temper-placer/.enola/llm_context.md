# Architecture Snapshot

## Repository Map

| Module | Language | Symbols | Exported |
|--------|----------|---------|----------|
| `.` | python | 2 | 2 |
| `.` | python | 2 | 2 |
| `examples` | python | 10 | 10 |
| `examples` | python | 10 | 10 |
| `experiments/diff_pair` | python | 32 | 28 |
| `experiments/diff_pair` | python | 32 | 28 |
| `research` | python | 12 | 12 |
| `research` | python | 12 | 12 |
| `scripts` | python | 126 | 104 |
| `scripts` | python | 126 | 104 |
| `scripts/analysis` | python | 24 | 24 |
| `scripts/analysis` | python | 24 | 24 |
| `src/temper_placer` | python | 52 | 36 |
| `src/temper_placer` | python | 52 | 36 |
| `src/temper_placer/_constraint_types` | python | 80 | 78 |
| `src/temper_placer/_constraint_types` | python | 80 | 78 |
| `src/temper_placer/ablation` | python | 222 | 164 |
| `src/temper_placer/ablation` | python | 222 | 164 |
| `src/temper_placer/adapters` | python | 54 | 36 |
| `src/temper_placer/adapters` | python | 54 | 36 |
| `src/temper_placer/algo` | python | 6 | 6 |
| `src/temper_placer/algo` | python | 6 | 6 |
| `src/temper_placer/analysis` | python | 32 | 32 |
| `src/temper_placer/analysis` | python | 32 | 32 |
| `src/temper_placer/cli` | python | 108 | 76 |
| `src/temper_placer/cli` | python | 108 | 76 |
| `src/temper_placer/constraints` | python | 104 | 60 |
| `src/temper_placer/constraints` | python | 104 | 60 |
| `src/temper_placer/core` | python | 680 | 612 |
| `src/temper_placer/core` | python | 680 | 612 |
| `src/temper_placer/deterministic` | python | 84 | 66 |
| `src/temper_placer/deterministic` | python | 84 | 66 |
| `src/temper_placer/deterministic/feedback` | python | 44 | 28 |
| `src/temper_placer/deterministic/feedback` | python | 44 | 28 |
| `src/temper_placer/deterministic/geometry` | python | 22 | 20 |
| `src/temper_placer/deterministic/geometry` | python | 22 | 20 |
| `src/temper_placer/deterministic/stages` | python | 476 | 264 |
| `src/temper_placer/deterministic/stages` | python | 476 | 264 |
| `src/temper_placer/explainability` | python | 212 | 154 |
| `src/temper_placer/explainability` | python | 212 | 154 |
| `src/temper_placer/extraction` | python | 8 | 6 |
| `src/temper_placer/extraction` | python | 8 | 6 |
| `src/temper_placer/fields` | python | 19 | 18 |
| `src/temper_placer/fixtures` | python | 12 | 10 |
| `src/temper_placer/fixtures` | python | 12 | 10 |
| `src/temper_placer/geometry` | python | 260 | 260 |
| `src/temper_placer/geometry` | python | 260 | 260 |
| `src/temper_placer/heuristics` | python | 320 | 240 |
| `src/temper_placer/heuristics` | python | 320 | 240 |
| `src/temper_placer/io` | python | 400 | 312 |
| `src/temper_placer/io` | python | 400 | 312 |
| `src/temper_placer/manufacturing` | python | 54 | 40 |
| `src/temper_placer/manufacturing` | python | 54 | 40 |
| `src/temper_placer/metrics` | python | 66 | 58 |
| `src/temper_placer/metrics` | python | 66 | 58 |
| `src/temper_placer/pcl` | python | 440 | 274 |
| `src/temper_placer/pcl` | python | 440 | 274 |
| `src/temper_placer/pcl/schemas` | python | 0 | 0 |
| `src/temper_placer/pcl/schemas` | python | 0 | 0 |
| `src/temper_placer/physics` | python | 84 | 54 |
| `src/temper_placer/physics` | python | 84 | 54 |
| `src/temper_placer/pipeline` | python | 640 | 426 |
| `src/temper_placer/pipeline` | python | 640 | 426 |
| `src/temper_placer/pipeline/stages` | python | 46 | 20 |
| `src/temper_placer/pipeline/stages` | python | 46 | 20 |
| `src/temper_placer/placer` | python | 34 | 32 |
| `src/temper_placer/placer` | python | 34 | 32 |
| `src/temper_placer/placer/cp_sat` | python | 342 | 182 |
| `src/temper_placer/placer/cp_sat` | python | 342 | 182 |
| `src/temper_placer/profiling` | python | 104 | 84 |
| `src/temper_placer/profiling` | python | 104 | 84 |
| `src/temper_placer/profiling/validation` | python | 12 | 10 |
| `src/temper_placer/profiling/validation` | python | 12 | 10 |
| `src/temper_placer/regression` | python | 216 | 165 |
| `src/temper_placer/regression` | python | 216 | 165 |
| `src/temper_placer/report` | python | 22 | 18 |
| `src/temper_placer/report` | python | 22 | 18 |
| `src/temper_placer/router_v6` | python | 1698 | 1232 |
| `src/temper_placer/router_v6` | python | 1698 | 1232 |
| `src/temper_placer/router_v6/metrics` | python | 34 | 16 |
| `src/temper_placer/router_v6/metrics` | python | 34 | 16 |
| `src/temper_placer/router_v6/quality` | python | 76 | 44 |
| `src/temper_placer/router_v6/quality` | python | 76 | 44 |
| `src/temper_placer/scale` | python | 48 | 34 |
| `src/temper_placer/scale` | python | 48 | 34 |
| `src/temper_placer/templates` | python | 24 | 22 |
| `src/temper_placer/templates` | python | 24 | 22 |
| `src/temper_placer/testing` | python | 50 | 34 |
| `src/temper_placer/testing` | python | 50 | 34 |
| `src/temper_placer/topological` | python | 82 | 66 |
| `src/temper_placer/topological` | python | 82 | 66 |
| `src/temper_placer/validation` | python | 877 | 745 |
| `src/temper_placer/validation` | python | 877 | 745 |
| `src/temper_placer/validation/prereg` | python | 15 | 10 |
| `src/temper_placer/validation/results` | python | 15 | 6 |
| `src/temper_placer/validation/spice_templates` | python | 10 | 10 |
| `src/temper_placer/validation/spice_templates` | python | 10 | 10 |
| `src/temper_placer/visualization` | python | 330 | 264 |
| `src/temper_placer/visualization` | python | 330 | 264 |
| `tests` | python | 770 | 706 |
| `tests` | python | 770 | 706 |
| `tests/ablation` | python | 248 | 248 |
| `tests/ablation` | python | 248 | 248 |
| `tests/algo` | python | 2 | 2 |
| `tests/algo` | python | 2 | 2 |
| `tests/analysis` | python | 24 | 24 |
| `tests/analysis` | python | 24 | 24 |
| `tests/cli` | python | 504 | 500 |
| `tests/cli` | python | 504 | 500 |
| `tests/closure` | python | 22 | 14 |
| `tests/closure` | python | 22 | 14 |
| `tests/comparison` | python | 96 | 96 |
| `tests/comparison` | python | 96 | 96 |
| `tests/constraints` | python | 226 | 226 |
| `tests/constraints` | python | 226 | 226 |
| `tests/core` | python | 886 | 874 |
| `tests/core` | python | 886 | 874 |
| `tests/deterministic` | python | 486 | 418 |
| `tests/deterministic` | python | 486 | 418 |
| `tests/deterministic/stages` | python | 436 | 384 |
| `tests/deterministic/stages` | python | 436 | 384 |
| `tests/domain` | python | 0 | 0 |
| `tests/domain` | python | 0 | 0 |
| `tests/explainability` | python | 788 | 786 |
| `tests/explainability` | python | 788 | 786 |
| `tests/fields` | python | 28 | 28 |
| `tests/fixtures` | python | 82 | 80 |
| `tests/fixtures` | python | 82 | 80 |
| `tests/fixtures/external` | python | 40 | 36 |
| `tests/fixtures/external` | python | 40 | 36 |
| `tests/fixtures/generators` | python | 30 | 24 |
| `tests/fixtures/generators` | python | 30 | 24 |
| `tests/geometry` | python | 170 | 168 |
| `tests/geometry` | python | 170 | 168 |
| `tests/heuristics` | python | 284 | 282 |
| `tests/heuristics` | python | 284 | 282 |
| `tests/integration` | python | 376 | 350 |
| `tests/integration` | python | 376 | 350 |
| `tests/invariants` | python | 20 | 20 |
| `tests/invariants` | python | 20 | 20 |
| `tests/io` | python | 890 | 876 |
| `tests/io` | python | 890 | 876 |
| `tests/manufacturing` | python | 70 | 68 |
| `tests/manufacturing` | python | 70 | 68 |
| `tests/measurements` | python | 6 | 6 |
| `tests/measurements` | python | 6 | 6 |
| `tests/mechanical` | python | 14 | 14 |
| `tests/mechanical` | python | 14 | 14 |
| `tests/metrics` | python | 30 | 30 |
| `tests/metrics` | python | 30 | 30 |
| `tests/ml` | python | 4 | 4 |
| `tests/ml` | python | 4 | 4 |
| `tests/parity` | python | 6 | 4 |
| `tests/parity` | python | 6 | 4 |
| `tests/pcl` | python | 802 | 764 |
| `tests/pcl` | python | 802 | 764 |
| `tests/physics` | python | 203 | 189 |
| `tests/physics` | python | 203 | 189 |
| `tests/pipeline` | python | 992 | 968 |
| `tests/pipeline` | python | 992 | 968 |
| `tests/pipeline/stages` | python | 42 | 42 |
| `tests/pipeline/stages` | python | 42 | 42 |
| `tests/placer` | python | 28 | 28 |
| `tests/placer` | python | 28 | 28 |
| `tests/placer/cp_sat` | python | 906 | 831 |
| `tests/placer/cp_sat` | python | 906 | 831 |
| `tests/profiling` | python | 76 | 74 |
| `tests/profiling` | python | 76 | 74 |
| `tests/property` | python | 20 | 16 |
| `tests/property` | python | 20 | 16 |
| `tests/protocol` | python | 220 | 198 |
| `tests/protocol` | python | 220 | 198 |
| `tests/regression` | python | 340 | 324 |
| `tests/regression` | python | 340 | 324 |
| `tests/requirements` | python | 0 | 0 |
| `tests/requirements` | python | 0 | 0 |
| `tests/requirements/dfm` | python | 278 | 278 |
| `tests/requirements/dfm` | python | 278 | 278 |
| `tests/requirements/emc` | python | 162 | 162 |
| `tests/requirements/emc` | python | 162 | 162 |
| `tests/requirements/review` | python | 72 | 72 |
| `tests/requirements/review` | python | 72 | 72 |
| `tests/requirements/safety` | python | 142 | 142 |
| `tests/requirements/safety` | python | 142 | 142 |
| `tests/requirements/validators` | python | 402 | 402 |
| `tests/requirements/validators` | python | 402 | 402 |
| `tests/robustness` | python | 126 | 126 |
| `tests/robustness` | python | 126 | 126 |
| `tests/router_v6` | python | 3671 | 3196 |
| `tests/router_v6` | python | 3671 | 3196 |
| `tests/router_v6/metrics` | python | 64 | 60 |
| `tests/router_v6/metrics` | python | 64 | 60 |
| `tests/rust_integration` | python | 136 | 136 |
| `tests/rust_integration` | python | 136 | 136 |
| `tests/scale` | python | 104 | 104 |
| `tests/scale` | python | 104 | 104 |
| `tests/sensitivity` | python | 60 | 60 |
| `tests/sensitivity` | python | 60 | 60 |
| `tests/templates` | python | 10 | 10 |
| `tests/templates` | python | 10 | 10 |
| `tests/testing` | python | 62 | 60 |
| `tests/testing` | python | 62 | 60 |
| `tests/topological` | python | 458 | 458 |
| `tests/topological` | python | 458 | 458 |
| `tests/unit` | python | 146 | 146 |
| `tests/unit` | python | 146 | 146 |
| `tests/validation` | python | 955 | 936 |
| `tests/validation` | python | 955 | 936 |
| `tests/validation/prereg` | python | 42 | 39 |
| `tests/verification` | python | 518 | 518 |
| `tests/verification` | python | 518 | 518 |
| `tests/visualization` | python | 794 | 794 |
| `tests/visualization` | python | 794 | 794 |

## Architecture Pattern

_No specific architecture pattern detected._

## Entry Points

- **handler**: `src/temper_placer/io/kicad_writer.strip_routing_preserve_nets` (src/temper_placer/io/kicad_writer.py)
- **handler**: `src/temper_placer/io/kicad_writer.strip_routing_preserve_nets` (temper-placer/src/temper_placer/io/kicad_writer.py)
- **handler**: `src/temper_placer/pcl/sat_bridge.register_handler` (src/temper_placer/pcl/sat_bridge.py)
- **handler**: `src/temper_placer/pcl/sat_bridge.register_handler` (temper-placer/src/temper_placer/pcl/sat_bridge.py)
- **handler**: `src/temper_placer/router_v6/routing_failure_handler.handle_routing_failures` (src/temper_placer/router_v6/routing_failure_handler.py)
- **handler**: `src/temper_placer/router_v6/routing_failure_handler.handle_routing_failures` (temper-placer/src/temper_placer/router_v6/routing_failure_handler.py)
- **handler**: `src/temper_placer/router_v6/via_grid_reservation.reserve_via_positions` (src/temper_placer/router_v6/via_grid_reservation.py)
- **handler**: `src/temper_placer/router_v6/via_grid_reservation.reserve_via_positions` (temper-placer/src/temper_placer/router_v6/via_grid_reservation.py)
- **handler**: `src/temper_placer/visualization/server.create_server` (src/temper_placer/visualization/server.py)
- **handler**: `src/temper_placer/visualization/server.create_server` (temper-placer/src/temper_placer/visualization/server.py)
- **handler**: `tests/deterministic/stages/test_deterministic_invariants_pbt.test_component_count_preserved` (temper-placer/tests/deterministic/stages/test_deterministic_invariants_pbt.py)
- **handler**: `tests/deterministic/stages/test_deterministic_invariants_pbt.test_component_count_preserved` (tests/deterministic/stages/test_deterministic_invariants_pbt.py)
- **handler**: `tests/deterministic/stages/test_deterministic_invariants_pbt.test_empty_board_state_handled_gracefully` (temper-placer/tests/deterministic/stages/test_deterministic_invariants_pbt.py)
- **handler**: `tests/deterministic/stages/test_deterministic_invariants_pbt.test_empty_board_state_handled_gracefully` (tests/deterministic/stages/test_deterministic_invariants_pbt.py)
- **handler**: `tests/io/test_dsn_normalizer.test_normalize_preserves_schema_version` (temper-placer/tests/io/test_dsn_normalizer.py)
- **handler**: `tests/io/test_dsn_normalizer.test_normalize_preserves_schema_version` (tests/io/test_dsn_normalizer.py)
- **handler**: `tests/io/test_via_dedup.test_distinct_positions_preserved` (temper-placer/tests/io/test_via_dedup.py)
- **handler**: `tests/io/test_via_dedup.test_distinct_positions_preserved` (tests/io/test_via_dedup.py)
- **handler**: `tests/pcl/test_integration_auto_enrich.test_enrich_preserves_existing_constraints` (temper-placer/tests/pcl/test_integration_auto_enrich.py)
- **handler**: `tests/pcl/test_integration_auto_enrich.test_enrich_preserves_existing_constraints` (tests/pcl/test_integration_auto_enrich.py)
- **handler**: `tests/pipeline/conftest.mock_observer` (temper-placer/tests/pipeline/conftest.py)
- **handler**: `tests/pipeline/conftest.mock_observer` (tests/pipeline/conftest.py)
- **handler**: `tests/router_v6/test_acid_trap_boundary.test_none_vias_handled` (temper-placer/tests/router_v6/test_acid_trap_boundary.py)
- **handler**: `tests/router_v6/test_acid_trap_boundary.test_none_vias_handled` (tests/router_v6/test_acid_trap_boundary.py)
- **handler**: `tests/router_v6/test_acid_trap_induction.test_acid_trap_modify_preserves_compliance` (temper-placer/tests/router_v6/test_acid_trap_induction.py)
- **handler**: `tests/router_v6/test_acid_trap_induction.test_acid_trap_modify_preserves_compliance` (tests/router_v6/test_acid_trap_induction.py)
- **handler**: `tests/router_v6/test_acid_trap_induction.test_acid_trap_remove_preserves_compliance` (temper-placer/tests/router_v6/test_acid_trap_induction.py)
- **handler**: `tests/router_v6/test_acid_trap_induction.test_acid_trap_remove_preserves_compliance` (tests/router_v6/test_acid_trap_induction.py)
- **handler**: `tests/router_v6/test_annular_ring_induction.test_annular_ring_modify_preserves_compliance` (temper-placer/tests/router_v6/test_annular_ring_induction.py)
- **handler**: `tests/router_v6/test_annular_ring_induction.test_annular_ring_modify_preserves_compliance` (tests/router_v6/test_annular_ring_induction.py)
- **handler**: `tests/router_v6/test_annular_ring_induction.test_annular_ring_remove_preserves_compliance` (temper-placer/tests/router_v6/test_annular_ring_induction.py)
- **handler**: `tests/router_v6/test_annular_ring_induction.test_annular_ring_remove_preserves_compliance` (tests/router_v6/test_annular_ring_induction.py)
- **handler**: `tests/router_v6/test_bundled_equivalence.test_safety_constraints_preserved` (temper-placer/tests/router_v6/test_bundled_equivalence.py)
- **handler**: `tests/router_v6/test_bundled_equivalence.test_safety_constraints_preserved` (tests/router_v6/test_bundled_equivalence.py)
- **handler**: `tests/router_v6/test_clearance_induction.test_clearance_modify_preserves_compliance` (temper-placer/tests/router_v6/test_clearance_induction.py)
- **handler**: `tests/router_v6/test_clearance_induction.test_clearance_modify_preserves_compliance` (tests/router_v6/test_clearance_induction.py)
- **handler**: `tests/router_v6/test_clearance_induction.test_clearance_remove_preserves_compliance` (temper-placer/tests/router_v6/test_clearance_induction.py)
- **handler**: `tests/router_v6/test_clearance_induction.test_clearance_remove_preserves_compliance` (tests/router_v6/test_clearance_induction.py)
- **handler**: `tests/router_v6/test_copper_balance_induction.test_copper_balance_modify_preserves_compliance` (temper-placer/tests/router_v6/test_copper_balance_induction.py)
- **handler**: `tests/router_v6/test_copper_balance_induction.test_copper_balance_modify_preserves_compliance` (tests/router_v6/test_copper_balance_induction.py)
- **handler**: `tests/router_v6/test_copper_balance_induction.test_copper_balance_remove_preserves_compliance` (temper-placer/tests/router_v6/test_copper_balance_induction.py)
- **handler**: `tests/router_v6/test_copper_balance_induction.test_copper_balance_remove_preserves_compliance` (tests/router_v6/test_copper_balance_induction.py)
- **handler**: `tests/router_v6/test_creepage_induction.test_creepage_modify_preserves_compliance` (temper-placer/tests/router_v6/test_creepage_induction.py)
- **handler**: `tests/router_v6/test_creepage_induction.test_creepage_modify_preserves_compliance` (tests/router_v6/test_creepage_induction.py)
- **handler**: `tests/router_v6/test_creepage_induction.test_creepage_remove_preserves_compliance` (temper-placer/tests/router_v6/test_creepage_induction.py)
- **handler**: `tests/router_v6/test_creepage_induction.test_creepage_remove_preserves_compliance` (tests/router_v6/test_creepage_induction.py)
- **handler**: `tests/router_v6/test_grid_update.test_update_grid_marks_cells_reserved` (temper-placer/tests/router_v6/test_grid_update.py)
- **handler**: `tests/router_v6/test_grid_update.test_update_grid_marks_cells_reserved` (tests/router_v6/test_grid_update.py)
- **handler**: `tests/router_v6/test_manufacturing_report_induction.test_manufacturing_report_modify_preserves_compliance` (temper-placer/tests/router_v6/test_manufacturing_report_induction.py)
- **handler**: `tests/router_v6/test_manufacturing_report_induction.test_manufacturing_report_modify_preserves_compliance` (tests/router_v6/test_manufacturing_report_induction.py)
- **handler**: `tests/router_v6/test_manufacturing_report_induction.test_manufacturing_report_remove_preserves_compliance` (temper-placer/tests/router_v6/test_manufacturing_report_induction.py)
- **handler**: `tests/router_v6/test_manufacturing_report_induction.test_manufacturing_report_remove_preserves_compliance` (tests/router_v6/test_manufacturing_report_induction.py)
- **handler**: `tests/router_v6/test_routing_failure_handler.test_handle_routing_failures` (temper-placer/tests/router_v6/test_routing_failure_handler.py)
- **handler**: `tests/router_v6/test_routing_failure_handler.test_handle_routing_failures` (tests/router_v6/test_routing_failure_handler.py)
- **handler**: `tests/router_v6/test_routing_failure_handler.test_no_failures` (temper-placer/tests/router_v6/test_routing_failure_handler.py)
- **handler**: `tests/router_v6/test_routing_failure_handler.test_no_failures` (tests/router_v6/test_routing_failure_handler.py)
- **handler**: `tests/router_v6/test_teardrop_induction.test_teardrop_modify_preserves_compliance` (temper-placer/tests/router_v6/test_teardrop_induction.py)
- **handler**: `tests/router_v6/test_teardrop_induction.test_teardrop_modify_preserves_compliance` (tests/router_v6/test_teardrop_induction.py)
- **handler**: `tests/router_v6/test_teardrop_induction.test_teardrop_remove_preserves_compliance` (temper-placer/tests/router_v6/test_teardrop_induction.py)
- **handler**: `tests/router_v6/test_teardrop_induction.test_teardrop_remove_preserves_compliance` (tests/router_v6/test_teardrop_induction.py)
- **handler**: `tests/router_v6/test_thermal_relief_induction.test_thermal_relief_modify_preserves_compliance` (temper-placer/tests/router_v6/test_thermal_relief_induction.py)
- **handler**: `tests/router_v6/test_thermal_relief_induction.test_thermal_relief_modify_preserves_compliance` (tests/router_v6/test_thermal_relief_induction.py)
- **handler**: `tests/router_v6/test_thermal_relief_induction.test_thermal_relief_remove_preserves_compliance` (temper-placer/tests/router_v6/test_thermal_relief_induction.py)
- **handler**: `tests/router_v6/test_thermal_relief_induction.test_thermal_relief_remove_preserves_compliance` (tests/router_v6/test_thermal_relief_induction.py)
- **handler**: `tests/router_v6/test_via_grid_reservation.test_reserve_via_positions_basic` (temper-placer/tests/router_v6/test_via_grid_reservation.py)
- **handler**: `tests/router_v6/test_via_grid_reservation.test_reserve_via_positions_basic` (tests/router_v6/test_via_grid_reservation.py)
- **handler**: `tests/router_v6/test_via_grid_reservation.test_reserve_via_positions_custom_grid` (temper-placer/tests/router_v6/test_via_grid_reservation.py)
- **handler**: `tests/router_v6/test_via_grid_reservation.test_reserve_via_positions_custom_grid` (tests/router_v6/test_via_grid_reservation.py)
- **handler**: `tests/router_v6/test_via_grid_reservation.test_reserve_via_positions_grid_snapping` (temper-placer/tests/router_v6/test_via_grid_reservation.py)
- **handler**: `tests/router_v6/test_via_grid_reservation.test_reserve_via_positions_grid_snapping` (tests/router_v6/test_via_grid_reservation.py)
- **handler**: `tests/router_v6/test_via_grid_reservation.test_reserved_via_blocked_layers` (temper-placer/tests/router_v6/test_via_grid_reservation.py)
- **handler**: `tests/router_v6/test_via_grid_reservation.test_reserved_via_blocked_layers` (tests/router_v6/test_via_grid_reservation.py)
- **handler**: `tests/router_v6/test_via_grid_reservation.test_reserved_via_through_via_detection` (temper-placer/tests/router_v6/test_via_grid_reservation.py)
- **handler**: `tests/router_v6/test_via_grid_reservation.test_reserved_via_through_via_detection` (tests/router_v6/test_via_grid_reservation.py)
- **handler**: `tests/router_v6/test_wave3_skip_sat.test_r7_default_false_preserves_existing_behavior` (temper-placer/tests/router_v6/test_wave3_skip_sat.py)
- **handler**: `tests/router_v6/test_wave3_skip_sat.test_r7_default_false_preserves_existing_behavior` (tests/router_v6/test_wave3_skip_sat.py)
- **handler**: `tests/router_v6/test_wave3_skip_sat.test_r8_map_topology_to_channels_handles_none_topology` (temper-placer/tests/router_v6/test_wave3_skip_sat.py)
- **handler**: `tests/router_v6/test_wave3_skip_sat.test_r8_map_topology_to_channels_handles_none_topology` (tests/router_v6/test_wave3_skip_sat.py)
- **handler**: `tests/test_metrics_observer.eight_stage_manifest` (temper-placer/tests/test_metrics_observer.py)
- **handler**: `tests/test_metrics_observer.eight_stage_manifest` (tests/test_metrics_observer.py)
- **handler**: `tests/test_metrics_observer.execution_log` (temper-placer/tests/test_metrics_observer.py)
- **handler**: `tests/test_metrics_observer.execution_log` (tests/test_metrics_observer.py)
- **handler**: `tests/test_metrics_observer.passthrough_manifest` (temper-placer/tests/test_metrics_observer.py)
- **handler**: `tests/test_metrics_observer.passthrough_manifest` (tests/test_metrics_observer.py)
- **handler**: `tests/test_metrics_observer.sample_config` (temper-placer/tests/test_metrics_observer.py)
- **handler**: `tests/test_metrics_observer.sample_config` (tests/test_metrics_observer.py)
- **handler**: `tests/test_metrics_observer.single_stage_manifest` (temper-placer/tests/test_metrics_observer.py)
- **handler**: `tests/test_metrics_observer.single_stage_manifest` (tests/test_metrics_observer.py)
- **handler**: `tests/test_round_trip_integrity.test_round_trip_component_count_preserved` (temper-placer/tests/test_round_trip_integrity.py)
- **handler**: `tests/test_round_trip_integrity.test_round_trip_component_count_preserved` (tests/test_round_trip_integrity.py)
- **handler**: `tests/visualization/test_server.minimal_state` (temper-placer/tests/visualization/test_server.py)
- **handler**: `tests/visualization/test_server.minimal_state` (tests/visualization/test_server.py)
- **handler**: `tests/visualization/test_server.state_with_data` (temper-placer/tests/visualization/test_server.py)
- **handler**: `tests/visualization/test_server.state_with_data` (tests/visualization/test_server.py)
- **main**: `examples/demo_constraint_builder.main` (examples/demo_constraint_builder.py)
- **main**: `examples/demo_constraint_builder.main` (temper-placer/examples/demo_constraint_builder.py)
- **main**: `examples/demo_constraint_reporting.main` (examples/demo_constraint_reporting.py)
- **main**: `examples/demo_constraint_reporting.main` (temper-placer/examples/demo_constraint_reporting.py)
- **main**: `examples/demo_integrated_pipeline.main` (examples/demo_integrated_pipeline.py)
- **main**: `examples/demo_integrated_pipeline.main` (temper-placer/examples/demo_integrated_pipeline.py)
- **main**: `research/inductance_model_comparison.main` (research/inductance_model_comparison.py)
- **main**: `research/inductance_model_comparison.main` (temper-placer/research/inductance_model_comparison.py)
- **main**: `scripts/analysis/analyze_gnd_connections.main` (scripts/analysis/analyze_gnd_connections.py)
- **main**: `scripts/analysis/analyze_gnd_connections.main` (temper-placer/scripts/analysis/analyze_gnd_connections.py)
- **main**: `scripts/analysis/analyze_power_placement.main` (scripts/analysis/analyze_power_placement.py)
- **main**: `scripts/analysis/analyze_power_placement.main` (temper-placer/scripts/analysis/analyze_power_placement.py)
- **main**: `scripts/analyze_centrality.main` (scripts/analyze_centrality.py)
- **main**: `scripts/analyze_centrality.main` (temper-placer/scripts/analyze_centrality.py)
- **main**: `scripts/analyze_seed_sensitivity.main` (scripts/analyze_seed_sensitivity.py)
- **main**: `scripts/analyze_seed_sensitivity.main` (temper-placer/scripts/analyze_seed_sensitivity.py)
- **main**: `scripts/characterize_pathological_seeds.main` (scripts/characterize_pathological_seeds.py)
- **main**: `scripts/characterize_pathological_seeds.main` (temper-placer/scripts/characterize_pathological_seeds.py)
- **main**: `scripts/compare_initialization.main` (scripts/compare_initialization.py)
- **main**: `scripts/compare_initialization.main` (temper-placer/scripts/compare_initialization.py)
- **main**: `scripts/demo_drc_oracle.main` (scripts/demo_drc_oracle.py)
- **main**: `scripts/demo_drc_oracle.main` (temper-placer/scripts/demo_drc_oracle.py)
- **main**: `scripts/diagnose_failures.main` (scripts/diagnose_failures.py)
- **main**: `scripts/diagnose_failures.main` (temper-placer/scripts/diagnose_failures.py)
- **main**: `scripts/experiment_netclass_layers.main` (scripts/experiment_netclass_layers.py)
- **main**: `scripts/experiment_netclass_layers.main` (temper-placer/scripts/experiment_netclass_layers.py)
- **main**: `scripts/export_dsn.main` (scripts/export_dsn.py)
- **main**: `scripts/export_dsn.main` (temper-placer/scripts/export_dsn.py)
- **main**: `scripts/profile_memory_scale.main` (scripts/profile_memory_scale.py)
- **main**: `scripts/profile_memory_scale.main` (temper-placer/scripts/profile_memory_scale.py)
- **main**: `scripts/profile_routing.main` (scripts/profile_routing.py)
- **main**: `scripts/profile_routing.main` (temper-placer/scripts/profile_routing.py)
- **main**: `scripts/spike_drc_proxy_correlation.main` (scripts/spike_drc_proxy_correlation.py)
- **main**: `scripts/spike_drc_proxy_correlation.main` (temper-placer/scripts/spike_drc_proxy_correlation.py)
- **main**: `scripts/tune_jiggle.main` (scripts/tune_jiggle.py)
- **main**: `scripts/tune_jiggle.main` (temper-placer/scripts/tune_jiggle.py)
- **main**: `scripts/tune_ramp_rate.main` (scripts/tune_ramp_rate.py)
- **main**: `scripts/tune_ramp_rate.main` (temper-placer/scripts/tune_ramp_rate.py)
- **main**: `scripts/validate_core_routing.main` (scripts/validate_core_routing.py)
- **main**: `scripts/validate_core_routing.main` (temper-placer/scripts/validate_core_routing.py)
- **main**: `scripts/validate_spectral_init.main` (scripts/validate_spectral_init.py)
- **main**: `scripts/validate_spectral_init.main` (temper-placer/scripts/validate_spectral_init.py)
- **main**: `scripts/verify_spectral_wirelength.main` (scripts/verify_spectral_wirelength.py)
- **main**: `scripts/verify_spectral_wirelength.main` (temper-placer/scripts/verify_spectral_wirelength.py)
- **main**: `src/temper_placer/analysis/run_correlation_analysis.main` (src/temper_placer/analysis/run_correlation_analysis.py)
- **main**: `src/temper_placer/analysis/run_correlation_analysis.main` (temper-placer/src/temper_placer/analysis/run_correlation_analysis.py)
- **main**: `src/temper_placer/cli/__init__.main` (src/temper_placer/cli/__init__.py)
- **main**: `src/temper_placer/cli/__init__.main` (temper-placer/src/temper_placer/cli/__init__.py)
- **main**: `src/temper_placer/cli/drc_cli.main` (src/temper_placer/cli/drc_cli.py)
- **main**: `src/temper_placer/cli/drc_cli.main` (temper-placer/src/temper_placer/cli/drc_cli.py)
- **main**: `src/temper_placer/regression/cli.main` (src/temper_placer/regression/cli.py)
- **main**: `src/temper_placer/regression/cli.main` (temper-placer/src/temper_placer/regression/cli.py)
- **main**: `src/temper_placer/regression/measure_closure.main` (src/temper_placer/regression/measure_closure.py)
- **main**: `src/temper_placer/regression/measure_closure.main` (temper-placer/src/temper_placer/regression/measure_closure.py)
- **main**: `src/temper_placer/router_v6/benchmark.main` (src/temper_placer/router_v6/benchmark.py)
- **main**: `src/temper_placer/router_v6/benchmark.main` (temper-placer/src/temper_placer/router_v6/benchmark.py)
- **main**: `tests/fixtures/external/download_pcbs.main` (temper-placer/tests/fixtures/external/download_pcbs.py)
- **main**: `tests/fixtures/external/download_pcbs.main` (tests/fixtures/external/download_pcbs.py)
- **main**: `tests/fixtures/generate_large_board.main` (temper-placer/tests/fixtures/generate_large_board.py)
- **main**: `tests/fixtures/generate_large_board.main` (tests/fixtures/generate_large_board.py)
- **main**: `tests/fixtures/generators/generate_pitchfork.main` (temper-placer/tests/fixtures/generators/generate_pitchfork.py)
- **main**: `tests/fixtures/generators/generate_pitchfork.main` (tests/fixtures/generators/generate_pitchfork.py)

## Dependency Rules

- `.` -> `src/temper_placer/router_v6`
- `examples` -> `src/temper_placer/constraints`
- `examples` -> `src/temper_placer/deterministic`
- `examples` -> `src/temper_placer/io`
- `scripts/analysis` -> `src/temper_placer/io`
- `scripts` -> `src/temper_placer/core`
- `scripts` -> `src/temper_placer/io`
- `scripts` -> `src/temper_placer/router_v6`
- `scripts` -> `src/temper_placer/scale`
- `scripts` -> `src/temper_placer`
- `src/temper_placer/_constraint_types` -> `src/temper_placer/core`
- `src/temper_placer/adapters` -> `src/temper_placer`
- `src/temper_placer/algo` -> `src/temper_placer/core`
- `src/temper_placer/cli` -> `src/temper_placer/io`
- `src/temper_placer/cli` -> `src/temper_placer/pipeline`
- `src/temper_placer/cli` -> `src/temper_placer/profiling`
- `src/temper_placer/cli` -> `src/temper_placer/report`
- `src/temper_placer/cli` -> `src/temper_placer/validation`
- `src/temper_placer/cli` -> `src/temper_placer`
- `src/temper_placer/constraints` -> `src/temper_placer/_constraint_types`
- `src/temper_placer/deterministic/feedback` -> `src/temper_placer/deterministic`
- `src/temper_placer/deterministic/stages` -> `.`
- `src/temper_placer/deterministic/stages` -> `src/temper_placer/constraints`
- `src/temper_placer/deterministic/stages` -> `src/temper_placer/core`
- `src/temper_placer/deterministic/stages` -> `src/temper_placer/io`
- `src/temper_placer/deterministic/stages` -> `src/temper_placer/router_v6`
- `src/temper_placer/deterministic` -> `src/temper_placer/validation`
- `src/temper_placer/extraction` -> `src/temper_placer/core`
- `src/temper_placer/fixtures` -> `src/temper_placer/core`
- `src/temper_placer/fixtures` -> `src/temper_placer/io`
- `src/temper_placer/geometry` -> `src/temper_placer/core`
- `src/temper_placer/heuristics` -> `src/temper_placer/core`
- `src/temper_placer/heuristics` -> `src/temper_placer/io`
- `src/temper_placer/heuristics` -> `src/temper_placer/placer`
- `src/temper_placer/heuristics` -> `src/temper_placer/router_v6`
- `src/temper_placer/heuristics` -> `src/temper_placer/topological`
- `src/temper_placer/io` -> `src/temper_placer/_constraint_types`
- `src/temper_placer/io` -> `src/temper_placer/core`
- `src/temper_placer/io` -> `src/temper_placer/deterministic/geometry`
- `src/temper_placer/io` -> `src/temper_placer/router_v6`
- `src/temper_placer/manufacturing` -> `src/temper_placer/core`
- `src/temper_placer/metrics` -> `src/temper_placer/core`
- `src/temper_placer/metrics` -> `src/temper_placer/router_v6`
- `src/temper_placer/metrics` -> `src/temper_placer/validation`
- `src/temper_placer/pcl` -> `src/temper_placer/core`
- `src/temper_placer/pcl` -> `src/temper_placer/router_v6`
- `src/temper_placer/physics` -> `src/temper_placer/placer/cp_sat`
- `src/temper_placer/pipeline/stages` -> `src/temper_placer/pipeline`
- `src/temper_placer/pipeline/stages` -> `src/temper_placer/router_v6`
- `src/temper_placer/pipeline` -> `src/temper_placer/core`
- `src/temper_placer/pipeline` -> `src/temper_placer/heuristics`
- `src/temper_placer/pipeline` -> `src/temper_placer/pcl`
- `src/temper_placer/pipeline` -> `src/temper_placer/placer`
- `src/temper_placer/pipeline` -> `src/temper_placer/regression`
- `src/temper_placer/pipeline` -> `src/temper_placer/router_v6`
- `src/temper_placer/placer/cp_sat` -> `src/temper_placer/pcl`
- `src/temper_placer/placer/cp_sat` -> `src/temper_placer/validation`
- `src/temper_placer/profiling/validation` -> `src/temper_placer/deterministic`
- `src/temper_placer/profiling` -> `src/temper_placer/regression`
- `src/temper_placer/regression` -> `src/temper_placer/adapters`
- `src/temper_placer/regression` -> `src/temper_placer/core`
- `src/temper_placer/regression` -> `src/temper_placer/heuristics`
- `src/temper_placer/regression` -> `src/temper_placer/io`
- `src/temper_placer/regression` -> `src/temper_placer/metrics`
- `src/temper_placer/regression` -> `src/temper_placer/pipeline`
- `src/temper_placer/regression` -> `src/temper_placer/placer`
- `src/temper_placer/regression` -> `src/temper_placer`
- `src/temper_placer/router_v6/metrics` -> `src/temper_placer/router_v6`
- `src/temper_placer/router_v6/quality` -> `src/temper_placer/router_v6`
- `src/temper_placer/router_v6` -> `src/temper_placer/core`
- `src/temper_placer/router_v6` -> `src/temper_placer/deterministic/stages`
- `src/temper_placer/router_v6` -> `src/temper_placer/deterministic`
- `src/temper_placer/router_v6` -> `src/temper_placer/io`
- `src/temper_placer/router_v6` -> `src/temper_placer/validation`
- `src/temper_placer/scale` -> `src/temper_placer/core`
- `src/temper_placer/scale` -> `src/temper_placer/io`
- `src/temper_placer/scale` -> `src/temper_placer/validation`
- `src/temper_placer/templates` -> `src/temper_placer/core`
- `src/temper_placer/topological` -> `src/temper_placer/core`
- `src/temper_placer/validation/results` -> `src/temper_placer/regression`
- `src/temper_placer/validation/results` -> `src/temper_placer/validation/prereg`
- `src/temper_placer/validation/results` -> `src/temper_placer/validation`
- `src/temper_placer/validation` -> `src/temper_placer/core`
- `src/temper_placer/validation` -> `src/temper_placer/geometry`
- `src/temper_placer/validation` -> `src/temper_placer/io`
- `src/temper_placer/validation` -> `src/temper_placer/regression`
- `src/temper_placer/validation` -> `src/temper_placer/validation/prereg`
- `src/temper_placer/visualization` -> `src/temper_placer/core`
- `src/temper_placer` -> `src/temper_placer/cli`
- `src/temper_placer` -> `src/temper_placer/core`
- `temper-placer/examples` -> `src/temper_placer/constraints`
- `temper-placer/examples` -> `src/temper_placer/deterministic`
- `temper-placer/examples` -> `src/temper_placer/io`
- `temper-placer/scripts/analysis` -> `src/temper_placer/io`
- `temper-placer/scripts` -> `src/temper_placer/core`
- `temper-placer/scripts` -> `src/temper_placer/io`
- `temper-placer/scripts` -> `src/temper_placer/router_v6`
- `temper-placer/scripts` -> `src/temper_placer/scale`
- `temper-placer/scripts` -> `src/temper_placer`
- `temper-placer/src/temper_placer/_constraint_types` -> `src/temper_placer/core`
- `temper-placer/src/temper_placer/adapters` -> `src/temper_placer`
- `temper-placer/src/temper_placer/algo` -> `src/temper_placer/core`
- `temper-placer/src/temper_placer/cli` -> `src/temper_placer/io`
- `temper-placer/src/temper_placer/cli` -> `src/temper_placer/pipeline`
- `temper-placer/src/temper_placer/cli` -> `src/temper_placer/profiling`
- `temper-placer/src/temper_placer/cli` -> `src/temper_placer/report`
- `temper-placer/src/temper_placer/cli` -> `src/temper_placer/validation`
- `temper-placer/src/temper_placer/cli` -> `src/temper_placer`
- `temper-placer/src/temper_placer/constraints` -> `src/temper_placer/_constraint_types`
- `temper-placer/src/temper_placer/deterministic/feedback` -> `src/temper_placer/deterministic`
- `temper-placer/src/temper_placer/deterministic/stages` -> `.`
- `temper-placer/src/temper_placer/deterministic/stages` -> `src/temper_placer/constraints`
- `temper-placer/src/temper_placer/deterministic/stages` -> `src/temper_placer/core`
- `temper-placer/src/temper_placer/deterministic/stages` -> `src/temper_placer/io`
- `temper-placer/src/temper_placer/deterministic/stages` -> `src/temper_placer/router_v6`
- `temper-placer/src/temper_placer/deterministic` -> `src/temper_placer/validation`
- `temper-placer/src/temper_placer/extraction` -> `src/temper_placer/core`
- `temper-placer/src/temper_placer/fixtures` -> `src/temper_placer/core`
- `temper-placer/src/temper_placer/fixtures` -> `src/temper_placer/io`
- `temper-placer/src/temper_placer/geometry` -> `src/temper_placer/core`
- `temper-placer/src/temper_placer/heuristics` -> `src/temper_placer/core`
- `temper-placer/src/temper_placer/heuristics` -> `src/temper_placer/io`
- `temper-placer/src/temper_placer/heuristics` -> `src/temper_placer/placer`
- `temper-placer/src/temper_placer/heuristics` -> `src/temper_placer/router_v6`
- `temper-placer/src/temper_placer/heuristics` -> `src/temper_placer/topological`
- `temper-placer/src/temper_placer/io` -> `src/temper_placer/_constraint_types`
- `temper-placer/src/temper_placer/io` -> `src/temper_placer/core`
- `temper-placer/src/temper_placer/io` -> `src/temper_placer/deterministic/geometry`
- `temper-placer/src/temper_placer/io` -> `src/temper_placer/router_v6`
- `temper-placer/src/temper_placer/manufacturing` -> `src/temper_placer/core`
- `temper-placer/src/temper_placer/metrics` -> `src/temper_placer/core`
- `temper-placer/src/temper_placer/metrics` -> `src/temper_placer/router_v6`
- `temper-placer/src/temper_placer/metrics` -> `src/temper_placer/validation`
- `temper-placer/src/temper_placer/pcl` -> `src/temper_placer/core`
- `temper-placer/src/temper_placer/pcl` -> `src/temper_placer/router_v6`
- `temper-placer/src/temper_placer/pipeline/stages` -> `src/temper_placer/pipeline`
- `temper-placer/src/temper_placer/pipeline/stages` -> `src/temper_placer/router_v6`
- `temper-placer/src/temper_placer/pipeline` -> `src/temper_placer/core`
- `temper-placer/src/temper_placer/pipeline` -> `src/temper_placer/heuristics`
- `temper-placer/src/temper_placer/pipeline` -> `src/temper_placer/pcl`
- `temper-placer/src/temper_placer/pipeline` -> `src/temper_placer/placer`
- `temper-placer/src/temper_placer/pipeline` -> `src/temper_placer/regression`
- `temper-placer/src/temper_placer/pipeline` -> `src/temper_placer/router_v6`
- `temper-placer/src/temper_placer/placer/cp_sat` -> `src/temper_placer/pcl`
- `temper-placer/src/temper_placer/placer/cp_sat` -> `src/temper_placer/validation`
- `temper-placer/src/temper_placer/profiling/validation` -> `src/temper_placer/deterministic`
- `temper-placer/src/temper_placer/profiling` -> `src/temper_placer/regression`
- `temper-placer/src/temper_placer/regression` -> `src/temper_placer/adapters`
- `temper-placer/src/temper_placer/regression` -> `src/temper_placer/core`
- `temper-placer/src/temper_placer/regression` -> `src/temper_placer/io`
- `temper-placer/src/temper_placer/regression` -> `src/temper_placer/metrics`
- `temper-placer/src/temper_placer/regression` -> `src/temper_placer/pipeline`
- `temper-placer/src/temper_placer/regression` -> `src/temper_placer/placer`
- `temper-placer/src/temper_placer/router_v6/metrics` -> `src/temper_placer/router_v6`
- `temper-placer/src/temper_placer/router_v6/quality` -> `src/temper_placer/router_v6`
- `temper-placer/src/temper_placer/router_v6` -> `src/temper_placer/core`
- `temper-placer/src/temper_placer/router_v6` -> `src/temper_placer/deterministic/stages`
- `temper-placer/src/temper_placer/router_v6` -> `src/temper_placer/deterministic`
- `temper-placer/src/temper_placer/router_v6` -> `src/temper_placer/io`
- `temper-placer/src/temper_placer/router_v6` -> `src/temper_placer/validation`
- `temper-placer/src/temper_placer/scale` -> `src/temper_placer/core`
- `temper-placer/src/temper_placer/scale` -> `src/temper_placer/io`
- `temper-placer/src/temper_placer/scale` -> `src/temper_placer/validation`
- `temper-placer/src/temper_placer/templates` -> `src/temper_placer/core`
- `temper-placer/src/temper_placer/topological` -> `src/temper_placer/core`
- `temper-placer/src/temper_placer/validation` -> `src/temper_placer/core`
- `temper-placer/src/temper_placer/validation` -> `src/temper_placer/geometry`
- `temper-placer/src/temper_placer/validation` -> `src/temper_placer/io`
- `temper-placer/src/temper_placer/visualization` -> `src/temper_placer/core`
- `temper-placer/src/temper_placer` -> `src/temper_placer/cli`
- `temper-placer/src/temper_placer` -> `src/temper_placer/core`
- `temper-placer/tests/ablation` -> `src/temper_placer/ablation`
- `temper-placer/tests/ablation` -> `src/temper_placer/core`
- `temper-placer/tests/algo` -> `src/temper_placer/algo`
- `temper-placer/tests/algo` -> `src/temper_placer/core`
- `temper-placer/tests/algo` -> `src/temper_placer/extraction`
- `temper-placer/tests/analysis` -> `src/temper_placer/analysis`
- `temper-placer/tests/cli` -> `src/temper_placer/cli`
- `temper-placer/tests/cli` -> `src/temper_placer/pcl`
- `temper-placer/tests/cli` -> `src/temper_placer/pipeline`
- `temper-placer/tests/cli` -> `src/temper_placer/placer/cp_sat`
- `temper-placer/tests/comparison` -> `src/temper_placer/core`
- `temper-placer/tests/comparison` -> `src/temper_placer/io`
- `temper-placer/tests/comparison` -> `src/temper_placer`
- `temper-placer/tests/comparison` -> `tests/fixtures/external`
- `temper-placer/tests/constraints` -> `src/temper_placer/constraints`
- `temper-placer/tests/constraints` -> `src/temper_placer/io`
- `temper-placer/tests/core` -> `src/temper_placer/core`
- `temper-placer/tests/core` -> `src/temper_placer/extraction`
- `temper-placer/tests/core` -> `src/temper_placer/heuristics`
- `temper-placer/tests/core` -> `src/temper_placer/io`
- `temper-placer/tests/core` -> `src/temper_placer`
- `temper-placer/tests/deterministic/stages` -> `src/temper_placer/core`
- `temper-placer/tests/deterministic/stages` -> `src/temper_placer/deterministic/geometry`
- `temper-placer/tests/deterministic/stages` -> `src/temper_placer/deterministic/stages`
- `temper-placer/tests/deterministic/stages` -> `src/temper_placer/deterministic`
- `temper-placer/tests/deterministic/stages` -> `src/temper_placer/io`
- `temper-placer/tests/deterministic/stages` -> `src/temper_placer/router_v6`
- `temper-placer/tests/deterministic/stages` -> `tests/deterministic`
- `temper-placer/tests/deterministic` -> `src/temper_placer/core`
- `temper-placer/tests/deterministic` -> `src/temper_placer/deterministic/feedback`
- `temper-placer/tests/deterministic` -> `src/temper_placer/deterministic/stages`
- `temper-placer/tests/deterministic` -> `src/temper_placer/deterministic`
- `temper-placer/tests/deterministic` -> `src/temper_placer/io`
- `temper-placer/tests/deterministic` -> `src/temper_placer/router_v6`
- `temper-placer/tests/explainability` -> `src/temper_placer/core`
- `temper-placer/tests/explainability` -> `src/temper_placer/explainability`
- `temper-placer/tests/fixtures/generators` -> `src/temper_placer/core`
- `temper-placer/tests/fixtures` -> `src/temper_placer/fixtures`
- `temper-placer/tests/geometry` -> `src/temper_placer/geometry`
- `temper-placer/tests/heuristics` -> `src/temper_placer/core`
- `temper-placer/tests/heuristics` -> `src/temper_placer/heuristics`
- `temper-placer/tests/heuristics` -> `src/temper_placer/io`
- `temper-placer/tests/integration` -> `src/temper_placer/constraints`
- `temper-placer/tests/integration` -> `src/temper_placer/core`
- `temper-placer/tests/integration` -> `src/temper_placer/deterministic/stages`
- `temper-placer/tests/integration` -> `src/temper_placer/deterministic`
- `temper-placer/tests/integration` -> `src/temper_placer/io`
- `temper-placer/tests/integration` -> `src/temper_placer/placer/cp_sat`
- `temper-placer/tests/integration` -> `src/temper_placer/router_v6`
- `temper-placer/tests/integration` -> `src/temper_placer`
- `temper-placer/tests/integration` -> `tests/fixtures/external`
- `temper-placer/tests/invariants` -> `src/temper_placer/core`
- `temper-placer/tests/io` -> `src/temper_placer/core`
- `temper-placer/tests/io` -> `src/temper_placer/deterministic/stages`
- `temper-placer/tests/io` -> `src/temper_placer/io`
- `temper-placer/tests/io` -> `src/temper_placer/router_v6`
- `temper-placer/tests/io` -> `src/temper_placer`
- `temper-placer/tests/manufacturing` -> `src/temper_placer/core`
- `temper-placer/tests/manufacturing` -> `src/temper_placer/manufacturing`
- `temper-placer/tests/measurements` -> `src/temper_placer/io`
- `temper-placer/tests/measurements` -> `src/temper_placer`
- `temper-placer/tests/metrics` -> `src/temper_placer/core`
- `temper-placer/tests/metrics` -> `src/temper_placer/metrics`
- `temper-placer/tests/metrics` -> `src/temper_placer/validation`
- `temper-placer/tests/ml` -> `src/temper_placer`
- `temper-placer/tests/parity` -> `src/temper_placer/core`
- `temper-placer/tests/parity` -> `src/temper_placer/deterministic/stages`
- `temper-placer/tests/parity` -> `src/temper_placer/deterministic`
- `temper-placer/tests/parity` -> `src/temper_placer/io`
- `temper-placer/tests/pcl` -> `src/temper_placer/core`
- `temper-placer/tests/pcl` -> `src/temper_placer/pcl`
- `temper-placer/tests/pcl` -> `src/temper_placer`
- `temper-placer/tests/physics` -> `src/temper_placer/physics`
- `temper-placer/tests/pipeline/stages` -> `src/temper_placer/core`
- `temper-placer/tests/pipeline/stages` -> `src/temper_placer/io`
- `temper-placer/tests/pipeline/stages` -> `src/temper_placer/pipeline`
- `temper-placer/tests/pipeline` -> `src/temper_placer/core`
- `temper-placer/tests/pipeline` -> `src/temper_placer/deterministic/stages`
- `temper-placer/tests/pipeline` -> `src/temper_placer/deterministic`
- `temper-placer/tests/pipeline` -> `src/temper_placer/pcl`
- `temper-placer/tests/pipeline` -> `src/temper_placer/pipeline`
- `temper-placer/tests/placer/cp_sat` -> `src/temper_placer/pcl`
- `temper-placer/tests/placer/cp_sat` -> `src/temper_placer/placer/cp_sat`
- `temper-placer/tests/placer` -> `src/temper_placer/core`
- `temper-placer/tests/placer` -> `src/temper_placer/placer`
- `temper-placer/tests/placer` -> `src/temper_placer/router_v6`
- `temper-placer/tests/profiling` -> `src/temper_placer/cli`
- `temper-placer/tests/profiling` -> `src/temper_placer/profiling`
- `temper-placer/tests/property` -> `src/temper_placer/core`
- `temper-placer/tests/property` -> `src/temper_placer/deterministic/stages`
- `temper-placer/tests/property` -> `src/temper_placer/io`
- `temper-placer/tests/protocol` -> `src/temper_placer/deterministic/stages`
- `temper-placer/tests/protocol` -> `src/temper_placer/deterministic`
- `temper-placer/tests/protocol` -> `src/temper_placer`
- `temper-placer/tests/regression` -> `src/temper_placer/core`
- `temper-placer/tests/regression` -> `src/temper_placer/metrics`
- `temper-placer/tests/regression` -> `src/temper_placer/regression`
- `temper-placer/tests/regression` -> `src/temper_placer/router_v6`
- `temper-placer/tests/requirements/dfm` -> `tests/requirements/validators`
- `temper-placer/tests/requirements/review` -> `tests/requirements/validators`
- `temper-placer/tests/requirements/safety` -> `tests/requirements/validators`
- `temper-placer/tests/robustness` -> `src/temper_placer/core`
- `temper-placer/tests/robustness` -> `src/temper_placer/geometry`
- `temper-placer/tests/robustness` -> `src/temper_placer/io`
- `temper-placer/tests/robustness` -> `src/temper_placer`
- `temper-placer/tests/router_v6/metrics` -> `src/temper_placer/router_v6/metrics`
- `temper-placer/tests/router_v6/metrics` -> `src/temper_placer/router_v6`
- `temper-placer/tests/router_v6` -> `src/temper_placer/core`
- `temper-placer/tests/router_v6` -> `src/temper_placer/deterministic/stages`
- `temper-placer/tests/router_v6` -> `src/temper_placer/deterministic`
- `temper-placer/tests/router_v6` -> `src/temper_placer/io`
- `temper-placer/tests/router_v6` -> `src/temper_placer/router_v6/quality`
- `temper-placer/tests/router_v6` -> `src/temper_placer/router_v6`
- `temper-placer/tests/router_v6` -> `src/temper_placer`
- `temper-placer/tests/scale` -> `src/temper_placer/core`
- `temper-placer/tests/scale` -> `src/temper_placer/fixtures`
- `temper-placer/tests/scale` -> `src/temper_placer/scale`
- `temper-placer/tests/scale` -> `src/temper_placer`
- `temper-placer/tests/scale` -> `tests/fixtures/generators`
- `temper-placer/tests/sensitivity` -> `src/temper_placer/core`
- `temper-placer/tests/sensitivity` -> `src/temper_placer/geometry`
- `temper-placer/tests/sensitivity` -> `src/temper_placer/heuristics`
- `temper-placer/tests/sensitivity` -> `src/temper_placer/io`
- `temper-placer/tests/sensitivity` -> `src/temper_placer`
- `temper-placer/tests/templates` -> `src/temper_placer/core`
- `temper-placer/tests/templates` -> `src/temper_placer/templates`
- `temper-placer/tests/testing` -> `src/temper_placer/core`
- `temper-placer/tests/testing` -> `src/temper_placer/deterministic`
- `temper-placer/tests/testing` -> `src/temper_placer/io`
- `temper-placer/tests/testing` -> `src/temper_placer/testing`
- `temper-placer/tests/topological` -> `src/temper_placer/core`
- `temper-placer/tests/topological` -> `src/temper_placer/heuristics`
- `temper-placer/tests/topological` -> `src/temper_placer/io`
- `temper-placer/tests/topological` -> `src/temper_placer/pcl`
- `temper-placer/tests/topological` -> `src/temper_placer/topological`
- `temper-placer/tests/unit` -> `src/temper_placer/core`
- `temper-placer/tests/unit` -> `src/temper_placer/geometry`
- `temper-placer/tests/unit` -> `src/temper_placer/io`
- `temper-placer/tests/unit` -> `src/temper_placer`
- `temper-placer/tests/validation` -> `src/temper_placer/core`
- `temper-placer/tests/validation` -> `src/temper_placer/io`
- `temper-placer/tests/validation` -> `src/temper_placer/validation`
- `temper-placer/tests/validation` -> `src/temper_placer`
- `temper-placer/tests/verification` -> `src/temper_placer/core`
- `temper-placer/tests/verification` -> `src/temper_placer/geometry`
- `temper-placer/tests/verification` -> `src/temper_placer/io`
- `temper-placer/tests/verification` -> `src/temper_placer/validation`
- `temper-placer/tests/verification` -> `src/temper_placer`
- `temper-placer/tests/visualization` -> `src/temper_placer/core`
- `temper-placer/tests/visualization` -> `src/temper_placer/visualization`
- `temper-placer/tests` -> `src/temper_placer/cli`
- `temper-placer/tests` -> `src/temper_placer/core`
- `temper-placer/tests` -> `src/temper_placer/deterministic/stages`
- `temper-placer/tests` -> `src/temper_placer/deterministic`
- `temper-placer/tests` -> `src/temper_placer/io`
- `temper-placer/tests` -> `src/temper_placer/pipeline`
- `temper-placer/tests` -> `src/temper_placer/profiling`
- `temper-placer/tests` -> `src/temper_placer/regression`
- `temper-placer/tests` -> `src/temper_placer/router_v6`
- `temper-placer/tests` -> `src/temper_placer/validation`
- `temper-placer/tests` -> `src/temper_placer/visualization`
- `temper-placer/tests` -> `src/temper_placer`
- `temper-placer/tests` -> `tests/fixtures/external`
- `temper-placer` -> `src/temper_placer/router_v6`
- `tests/ablation` -> `src/temper_placer/ablation`
- `tests/ablation` -> `src/temper_placer/core`
- `tests/algo` -> `src/temper_placer/algo`
- `tests/algo` -> `src/temper_placer/core`
- `tests/algo` -> `src/temper_placer/extraction`
- `tests/analysis` -> `src/temper_placer/analysis`
- `tests/cli` -> `src/temper_placer/cli`
- `tests/cli` -> `src/temper_placer/pcl`
- `tests/cli` -> `src/temper_placer/pipeline`
- `tests/cli` -> `src/temper_placer/placer/cp_sat`
- `tests/comparison` -> `src/temper_placer/core`
- `tests/comparison` -> `src/temper_placer/io`
- `tests/comparison` -> `src/temper_placer`
- `tests/comparison` -> `tests/fixtures/external`
- `tests/constraints` -> `src/temper_placer/constraints`
- `tests/constraints` -> `src/temper_placer/io`
- `tests/core` -> `src/temper_placer/core`
- `tests/core` -> `src/temper_placer/extraction`
- `tests/core` -> `src/temper_placer/heuristics`
- `tests/core` -> `src/temper_placer/io`
- `tests/core` -> `src/temper_placer`
- `tests/deterministic/stages` -> `src/temper_placer/core`
- `tests/deterministic/stages` -> `src/temper_placer/deterministic/geometry`
- `tests/deterministic/stages` -> `src/temper_placer/deterministic/stages`
- `tests/deterministic/stages` -> `src/temper_placer/deterministic`
- `tests/deterministic/stages` -> `src/temper_placer/io`
- `tests/deterministic/stages` -> `src/temper_placer/router_v6`
- `tests/deterministic/stages` -> `tests/deterministic`
- `tests/deterministic` -> `src/temper_placer/core`
- `tests/deterministic` -> `src/temper_placer/deterministic/feedback`
- `tests/deterministic` -> `src/temper_placer/deterministic/stages`
- `tests/deterministic` -> `src/temper_placer/deterministic`
- `tests/deterministic` -> `src/temper_placer/io`
- `tests/deterministic` -> `src/temper_placer/router_v6`
- `tests/explainability` -> `src/temper_placer/core`
- `tests/explainability` -> `src/temper_placer/explainability`
- `tests/fields` -> `src/temper_placer/fields`
- `tests/fields` -> `src/temper_placer/placer/cp_sat`
- `tests/fixtures/generators` -> `src/temper_placer/core`
- `tests/fixtures` -> `src/temper_placer/fixtures`
- `tests/geometry` -> `src/temper_placer/geometry`
- `tests/heuristics` -> `src/temper_placer/core`
- `tests/heuristics` -> `src/temper_placer/heuristics`
- `tests/heuristics` -> `src/temper_placer/io`
- `tests/integration` -> `src/temper_placer/constraints`
- `tests/integration` -> `src/temper_placer/core`
- `tests/integration` -> `src/temper_placer/deterministic/stages`
- `tests/integration` -> `src/temper_placer/deterministic`
- `tests/integration` -> `src/temper_placer/io`
- `tests/integration` -> `src/temper_placer/placer/cp_sat`
- `tests/integration` -> `src/temper_placer/router_v6`
- `tests/integration` -> `src/temper_placer`
- `tests/integration` -> `tests/fixtures/external`
- `tests/invariants` -> `src/temper_placer/core`
- `tests/io` -> `src/temper_placer/core`
- `tests/io` -> `src/temper_placer/deterministic/stages`
- `tests/io` -> `src/temper_placer/io`
- `tests/io` -> `src/temper_placer/router_v6`
- `tests/io` -> `src/temper_placer`
- `tests/manufacturing` -> `src/temper_placer/core`
- `tests/manufacturing` -> `src/temper_placer/manufacturing`
- `tests/measurements` -> `src/temper_placer/io`
- `tests/measurements` -> `src/temper_placer`
- `tests/metrics` -> `src/temper_placer/core`
- `tests/metrics` -> `src/temper_placer/metrics`
- `tests/metrics` -> `src/temper_placer/validation`
- `tests/ml` -> `src/temper_placer`
- `tests/parity` -> `src/temper_placer/core`
- `tests/parity` -> `src/temper_placer/deterministic/stages`
- `tests/parity` -> `src/temper_placer/deterministic`
- `tests/parity` -> `src/temper_placer/io`
- `tests/pcl` -> `src/temper_placer/core`
- `tests/pcl` -> `src/temper_placer/pcl`
- `tests/pcl` -> `src/temper_placer`
- `tests/physics` -> `src/temper_placer/fields`
- `tests/physics` -> `src/temper_placer/physics`
- `tests/physics` -> `src/temper_placer/placer/cp_sat`
- `tests/pipeline/stages` -> `src/temper_placer/core`
- `tests/pipeline/stages` -> `src/temper_placer/io`
- `tests/pipeline/stages` -> `src/temper_placer/pipeline`
- `tests/pipeline` -> `src/temper_placer/core`
- `tests/pipeline` -> `src/temper_placer/deterministic/stages`
- `tests/pipeline` -> `src/temper_placer/deterministic`
- `tests/pipeline` -> `src/temper_placer/pcl`
- `tests/pipeline` -> `src/temper_placer/pipeline`
- `tests/placer/cp_sat` -> `src/temper_placer/fields`
- `tests/placer/cp_sat` -> `src/temper_placer/pcl`
- `tests/placer/cp_sat` -> `src/temper_placer/placer/cp_sat`
- `tests/placer` -> `src/temper_placer/core`
- `tests/placer` -> `src/temper_placer/placer`
- `tests/placer` -> `src/temper_placer/router_v6`
- `tests/profiling` -> `src/temper_placer/cli`
- `tests/profiling` -> `src/temper_placer/profiling`
- `tests/property` -> `src/temper_placer/core`
- `tests/property` -> `src/temper_placer/deterministic/stages`
- `tests/property` -> `src/temper_placer/io`
- `tests/protocol` -> `src/temper_placer/deterministic/stages`
- `tests/protocol` -> `src/temper_placer/deterministic`
- `tests/protocol` -> `src/temper_placer`
- `tests/regression` -> `src/temper_placer/core`
- `tests/regression` -> `src/temper_placer/metrics`
- `tests/regression` -> `src/temper_placer/regression`
- `tests/regression` -> `src/temper_placer/router_v6`
- `tests/requirements/dfm` -> `tests/requirements/validators`
- `tests/requirements/review` -> `tests/requirements/validators`
- `tests/requirements/safety` -> `tests/requirements/validators`
- `tests/robustness` -> `src/temper_placer/core`
- `tests/robustness` -> `src/temper_placer/geometry`
- `tests/robustness` -> `src/temper_placer/io`
- `tests/robustness` -> `src/temper_placer`
- `tests/router_v6/metrics` -> `src/temper_placer/router_v6/metrics`
- `tests/router_v6/metrics` -> `src/temper_placer/router_v6`
- `tests/router_v6` -> `src/temper_placer/core`
- `tests/router_v6` -> `src/temper_placer/deterministic/stages`
- `tests/router_v6` -> `src/temper_placer/deterministic`
- `tests/router_v6` -> `src/temper_placer/fields`
- `tests/router_v6` -> `src/temper_placer/io`
- `tests/router_v6` -> `src/temper_placer/router_v6/quality`
- `tests/router_v6` -> `src/temper_placer/router_v6`
- `tests/router_v6` -> `src/temper_placer`
- `tests/scale` -> `src/temper_placer/core`
- `tests/scale` -> `src/temper_placer/fixtures`
- `tests/scale` -> `src/temper_placer/scale`
- `tests/scale` -> `src/temper_placer`
- `tests/scale` -> `tests/fixtures/generators`
- `tests/sensitivity` -> `src/temper_placer/core`
- `tests/sensitivity` -> `src/temper_placer/geometry`
- `tests/sensitivity` -> `src/temper_placer/heuristics`
- `tests/sensitivity` -> `src/temper_placer/io`
- `tests/sensitivity` -> `src/temper_placer`
- `tests/templates` -> `src/temper_placer/core`
- `tests/templates` -> `src/temper_placer/templates`
- `tests/testing` -> `src/temper_placer/core`
- `tests/testing` -> `src/temper_placer/deterministic`
- `tests/testing` -> `src/temper_placer/io`
- `tests/testing` -> `src/temper_placer/testing`
- `tests/topological` -> `src/temper_placer/core`
- `tests/topological` -> `src/temper_placer/heuristics`
- `tests/topological` -> `src/temper_placer/io`
- `tests/topological` -> `src/temper_placer/pcl`
- `tests/topological` -> `src/temper_placer/topological`
- `tests/unit` -> `src/temper_placer/core`
- `tests/unit` -> `src/temper_placer/geometry`
- `tests/unit` -> `src/temper_placer/io`
- `tests/unit` -> `src/temper_placer`
- `tests/validation/prereg` -> `src/temper_placer/validation/prereg`
- `tests/validation` -> `src/temper_placer/core`
- `tests/validation` -> `src/temper_placer/io`
- `tests/validation` -> `src/temper_placer/metrics`
- `tests/validation` -> `src/temper_placer/physics`
- `tests/validation` -> `src/temper_placer/regression`
- `tests/validation` -> `src/temper_placer/validation/prereg`
- `tests/validation` -> `src/temper_placer/validation/results`
- `tests/validation` -> `src/temper_placer/validation`
- `tests/validation` -> `src/temper_placer`
- `tests/verification` -> `src/temper_placer/core`
- `tests/verification` -> `src/temper_placer/geometry`
- `tests/verification` -> `src/temper_placer/io`
- `tests/verification` -> `src/temper_placer/validation`
- `tests/verification` -> `src/temper_placer`
- `tests/visualization` -> `src/temper_placer/core`
- `tests/visualization` -> `src/temper_placer/visualization`
- `tests` -> `src/temper_placer/cli`
- `tests` -> `src/temper_placer/core`
- `tests` -> `src/temper_placer/deterministic/stages`
- `tests` -> `src/temper_placer/deterministic`
- `tests` -> `src/temper_placer/io`
- `tests` -> `src/temper_placer/pipeline`
- `tests` -> `src/temper_placer/profiling`
- `tests` -> `src/temper_placer/regression`
- `tests` -> `src/temper_placer/router_v6`
- `tests` -> `src/temper_placer/validation`
- `tests` -> `src/temper_placer/visualization`
- `tests` -> `src/temper_placer`
- `tests` -> `tests/fixtures/external`

## Critical Modules

| Module | Fan-In | Fan-Out | Criticality |
|--------|--------|---------|-------------|
| `src/temper_placer/router_v6` | 1012 | 73 | high |
| `src/temper_placer/core` | 805 | 0 | high |
| `tests/router_v6` | 0 | 483 | high |
| `src/temper_placer` | 358 | 4 | high |
| `src/temper_placer/io` | 281 | 28 | high |
| `src/temper_placer/deterministic` | 180 | 4 | high |
| `src/temper_placer/deterministic/stages` | 130 | 17 | high |
| `src/temper_placer/pipeline` | 97 | 26 | high |
| `src/temper_placer/pcl` | 104 | 3 | high |
| `src/temper_placer/validation` | 68 | 37 | high |

## Risk Zones

- **Cyclic dependency detected (14 modules)** (confidence: 100%): The following modules form a dependency cycle: src/temper_placer/deterministic/stages -> src/temper_placer/metrics -> src/temper_placer/profiling -> src/temper_placer/heuristics -> src/temper_placer/pipeline -> src/temper_placer/cli -> src/temper_placer -> src/temper_placer/adapters -> src/temper_placer/regression -> src/temper_placer/io -> src/temper_placer/validation -> src/temper_placer/deterministic -> src/temper_placer/router_v6 -> src/temper_placer/pcl -> src/temper_placer/deterministic/stages. This can cause initialization issues, make refactoring harder, and indicates tight coupling.

## How to Add a Feature

General guidance:

1. Identify the appropriate module/package for the feature
2. Follow existing patterns in the codebase
3. Keep dependencies flowing in one direction
4. Add appropriate exports for cross-module usage
5. Wire the feature in the entry point

---

*Generated at 2026-07-09T20:58:19Z in 959.641792ms. 36899 facts, 233 insights.*
