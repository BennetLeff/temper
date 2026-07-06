# Architecture Snapshot

## Repository Map

| Module | Language | Symbols | Exported |
|--------|----------|---------|----------|
| `.` | python | 0 | 0 |
| `Eagle2Kicad` | python | 14 | 14 |
| `Eagle2Kicad/Board` | python | 12 | 11 |
| `Eagle2Kicad/Common` | python | 94 | 72 |
| `Eagle2Kicad/Library` | python | 6 | 5 |
| `Eagle2Kicad/Schematic` | python | 2 | 1 |
| `components/LMR51420/test_files` | python | 13 | 11 |
| `components/UCC27511A` | python | 4 | 4 |
| `firmware` | c | 10 | 10 |
| `firmware/components/control` | c | 146 | 141 |
| `firmware/components/hal/esp32` | c | 74 | 27 |
| `firmware/components/hal/include` | c | 45 | 45 |
| `firmware/components/hal/mock` | c | 135 | 84 |
| `firmware/components/safety` | c | 70 | 58 |
| `firmware/components/safety/include` | c | 25 | 25 |
| `firmware/components/testing` | c | 1 | 1 |
| `firmware/components/webui` | c | 11 | 7 |
| `firmware/components/webui/include` | c | 3 | 3 |
| `firmware/main` | c | 119 | 108 |
| `firmware/test` | c | 474 | 321 |
| `firmware/test` | python | 474 | 321 |
| `firmware/test/unity` | c | 46 | 35 |
| `firmware/tools` | python | 15 | 15 |
| `packages/temper-autoprof/src/temper_autoprof` | python | 11 | 10 |
| `packages/temper-autoprof/tests` | python | 6 | 6 |
| `packages/temper-placer` | python | 1 | 1 |
| `packages/temper-placer/benchmarks` | python | 34 | 25 |
| `packages/temper-placer/examples` | python | 5 | 5 |
| `packages/temper-placer/experiments/diff_pair` | python | 16 | 14 |
| `packages/temper-placer/research` | python | 6 | 6 |
| `packages/temper-placer/scripts` | python | 47 | 47 |
| `packages/temper-placer/scripts/analysis` | python | 12 | 12 |
| `packages/temper-placer/src/temper_placer` | python | 26 | 18 |
| `packages/temper-placer/src/temper_placer/_constraint_types` | python | 40 | 39 |
| `packages/temper-placer/src/temper_placer/ablation` | python | 107 | 79 |
| `packages/temper-placer/src/temper_placer/adapters` | python | 27 | 18 |
| `packages/temper-placer/src/temper_placer/algo` | python | 3 | 3 |
| `packages/temper-placer/src/temper_placer/analysis` | python | 16 | 16 |
| `packages/temper-placer/src/temper_placer/cli` | python | 72 | 57 |
| `packages/temper-placer/src/temper_placer/constraints` | python | 52 | 30 |
| `packages/temper-placer/src/temper_placer/core` | python | 308 | 278 |
| `packages/temper-placer/src/temper_placer/deterministic` | python | 42 | 33 |
| `packages/temper-placer/src/temper_placer/deterministic/feedback` | python | 22 | 14 |
| `packages/temper-placer/src/temper_placer/deterministic/geometry` | python | 11 | 10 |
| `packages/temper-placer/src/temper_placer/deterministic/stages` | python | 238 | 132 |
| `packages/temper-placer/src/temper_placer/experiments` | python | 90 | 66 |
| `packages/temper-placer/src/temper_placer/explainability` | python | 106 | 77 |
| `packages/temper-placer/src/temper_placer/extraction` | python | 4 | 3 |
| `packages/temper-placer/src/temper_placer/fixtures` | python | 6 | 5 |
| `packages/temper-placer/src/temper_placer/geometry` | python | 130 | 130 |
| `packages/temper-placer/src/temper_placer/heuristics` | python | 175 | 132 |
| `packages/temper-placer/src/temper_placer/io` | python | 198 | 154 |
| `packages/temper-placer/src/temper_placer/losses` | python | 495 | 348 |
| `packages/temper-placer/src/temper_placer/losses/physics` | python | 14 | 10 |
| `packages/temper-placer/src/temper_placer/manufacturing` | python | 27 | 20 |
| `packages/temper-placer/src/temper_placer/metrics` | python | 33 | 29 |
| `packages/temper-placer/src/temper_placer/ml` | python | 22 | 15 |
| `packages/temper-placer/src/temper_placer/optimizer` | python | 263 | 189 |
| `packages/temper-placer/src/temper_placer/pcl` | python | 231 | 147 |
| `packages/temper-placer/src/temper_placer/pcl/schemas` | python | 0 | 0 |
| `packages/temper-placer/src/temper_placer/physics` | python | 23 | 21 |
| `packages/temper-placer/src/temper_placer/pipeline` | python | 298 | 201 |
| `packages/temper-placer/src/temper_placer/pipeline/stages` | python | 23 | 10 |
| `packages/temper-placer/src/temper_placer/placement` | python | 44 | 22 |
| `packages/temper-placer/src/temper_placer/placer` | python | 17 | 16 |
| `packages/temper-placer/src/temper_placer/profiling` | python | 52 | 42 |
| `packages/temper-placer/src/temper_placer/profiling/validation` | python | 6 | 5 |
| `packages/temper-placer/src/temper_placer/regression` | python | 107 | 82 |
| `packages/temper-placer/src/temper_placer/report` | python | 11 | 9 |
| `packages/temper-placer/src/temper_placer/router_v6` | python | 812 | 589 |
| `packages/temper-placer/src/temper_placer/scale` | python | 14 | 11 |
| `packages/temper-placer/src/temper_placer/templates` | python | 12 | 11 |
| `packages/temper-placer/src/temper_placer/testing` | python | 25 | 17 |
| `packages/temper-placer/src/temper_placer/topological` | python | 41 | 33 |
| `packages/temper-placer/src/temper_placer/validation` | python | 421 | 361 |
| `packages/temper-placer/src/temper_placer/validation/spice_templates` | python | 5 | 5 |
| `packages/temper-placer/src/temper_placer/visualization` | python | 165 | 132 |
| `packages/temper-placer/tests` | python | 385 | 353 |
| `packages/temper-placer/tests/ablation` | python | 124 | 124 |
| `packages/temper-placer/tests/algo` | python | 1 | 1 |
| `packages/temper-placer/tests/analysis` | python | 12 | 12 |
| `packages/temper-placer/tests/cli` | python | 236 | 236 |
| `packages/temper-placer/tests/closure` | python | 11 | 7 |
| `packages/temper-placer/tests/comparison` | python | 48 | 48 |
| `packages/temper-placer/tests/constraints` | python | 113 | 113 |
| `packages/temper-placer/tests/core` | python | 372 | 366 |
| `packages/temper-placer/tests/deterministic` | python | 243 | 209 |
| `packages/temper-placer/tests/deterministic/stages` | python | 218 | 192 |
| `packages/temper-placer/tests/domain` | python | 0 | 0 |
| `packages/temper-placer/tests/explainability` | python | 394 | 393 |
| `packages/temper-placer/tests/fixtures` | python | 41 | 40 |
| `packages/temper-placer/tests/fixtures/external` | python | 20 | 18 |
| `packages/temper-placer/tests/fixtures/generators` | python | 15 | 12 |
| `packages/temper-placer/tests/geometry` | python | 85 | 84 |
| `packages/temper-placer/tests/heuristics` | python | 151 | 150 |
| `packages/temper-placer/tests/integration` | python | 157 | 146 |
| `packages/temper-placer/tests/invariants` | python | 10 | 10 |
| `packages/temper-placer/tests/io` | python | 435 | 428 |
| `packages/temper-placer/tests/losses` | python | 500 | 477 |
| `packages/temper-placer/tests/manufacturing` | python | 35 | 34 |
| `packages/temper-placer/tests/measurements` | python | 3 | 3 |
| `packages/temper-placer/tests/mechanical` | python | 7 | 7 |
| `packages/temper-placer/tests/metrics` | python | 15 | 15 |
| `packages/temper-placer/tests/ml` | python | 2 | 2 |
| `packages/temper-placer/tests/optimizer` | python | 652 | 635 |
| `packages/temper-placer/tests/parity` | python | 3 | 2 |
| `packages/temper-placer/tests/pcl` | python | 408 | 388 |
| `packages/temper-placer/tests/physics` | python | 63 | 63 |
| `packages/temper-placer/tests/pipeline` | python | 496 | 484 |
| `packages/temper-placer/tests/pipeline/stages` | python | 21 | 21 |
| `packages/temper-placer/tests/placement` | python | 21 | 18 |
| `packages/temper-placer/tests/placer` | python | 14 | 14 |
| `packages/temper-placer/tests/profiling` | python | 38 | 37 |
| `packages/temper-placer/tests/property` | python | 10 | 8 |
| `packages/temper-placer/tests/protocol` | python | 110 | 99 |
| `packages/temper-placer/tests/regression` | python | 183 | 174 |
| `packages/temper-placer/tests/requirements` | python | 0 | 0 |
| `packages/temper-placer/tests/requirements/dfm` | python | 139 | 139 |
| `packages/temper-placer/tests/requirements/emc` | python | 81 | 81 |
| `packages/temper-placer/tests/requirements/review` | python | 36 | 36 |
| `packages/temper-placer/tests/requirements/safety` | python | 71 | 71 |
| `packages/temper-placer/tests/requirements/validators` | python | 201 | 201 |
| `packages/temper-placer/tests/robustness` | python | 63 | 63 |
| `packages/temper-placer/tests/router_v6` | python | 1694 | 1476 |
| `packages/temper-placer/tests/rust_integration` | python | 68 | 68 |
| `packages/temper-placer/tests/scale` | python | 52 | 52 |
| `packages/temper-placer/tests/sensitivity` | python | 30 | 30 |
| `packages/temper-placer/tests/templates` | python | 5 | 5 |
| `packages/temper-placer/tests/testing` | python | 31 | 30 |
| `packages/temper-placer/tests/topological` | python | 229 | 229 |
| `packages/temper-placer/tests/unit` | python | 73 | 73 |
| `packages/temper-placer/tests/validation` | python | 419 | 415 |
| `packages/temper-placer/tests/verification` | python | 259 | 259 |
| `packages/temper-placer/tests/visualization` | python | 397 | 397 |
| `packages/temper-testing/src/temper_testing` | python | 144 | 127 |
| `packages/temper-tools/src/temper_tools` | python | 0 | 0 |
| `packages/temper-tools/src/temper_tools/ato` | python | 3 | 3 |
| `packages/temper-tools/src/temper_tools/eco` | python | 0 | 0 |
| `packages/temper-tools/src/temper_tools/kicad` | python | 21 | 12 |
| `packages/temper-tools/src/temper_tools/routing` | python | 2 | 2 |
| `packages/temper-tools/tests` | python | 3 | 3 |
| `packages/temper-validation/src/temper_validation` | python | 5 | 5 |
| `packages/temper-validation/src/temper_validation/comparison` | python | 20 | 20 |
| `packages/temper-validation/src/temper_validation/metrics` | python | 5 | 5 |
| `packages/temper-validation/src/temper_validation/reporting` | python | 7 | 5 |
| `packages/temper-validation/tests/comparison` | python | 35 | 35 |
| `packages/temper-validation/tests/metrics` | python | 7 | 7 |
| `packages/temper-validation/tests/reporting` | python | 16 | 16 |
| `packages/temper-workflow/src/temper_workflow` | python | 0 | 0 |
| `packages/temper-workflow/src/temper_workflow/metrics` | python | 7 | 7 |
| `packages/temper-workflow/src/temper_workflow/routing` | python | 4 | 4 |
| `packages/temper-workflow/src/temper_workflow/utils` | python | 0 | 0 |
| `packages/temper-workflow/tests` | python | 0 | 0 |
| `power_pcb_dataset/sources/Hardware/LIBS/Keystone/1048/PADS` | c | 0 | 0 |
| `power_pcb_dataset/sources/Hardware/LIBS/LTC6810-2/PADS` | c | 0 | 0 |
| `power_pcb_dataset/sources/Hardware/LIBS/LTC6811-1/PADS` | c | 0 | 0 |
| `power_pcb_dataset/sources/Hardware/LIBS/LTC6812-1/PADS` | c | 0 | 0 |
| `power_pcb_dataset/sources/Hardware/LIBS/LTC6813-1/PADS` | c | 0 | 0 |
| `scripts` | python | 208 | 169 |
| `scripts/tests` | python | 118 | 107 |
| `session-dashboard` | python | 91 | 66 |
| `test-boards/mvb` | python | 11 | 11 |
| `tests` | python | 26 | 26 |
| `tests/deterministic` | python | 205 | 205 |
| `tests/integration` | python | 53 | 53 |
| `tests/manual` | python | 10 | 8 |
| `tests/placement` | python | 7 | 7 |
| `tests/router_v6` | python | 8 | 6 |
| `tests/routing` | python | 9 | 9 |
| `tests/scripts` | python | 2 | 2 |
| `tests/spice` | python | 101 | 101 |
| `tools` | python | 28 | 22 |
| `tools/measurements` | python | 6 | 1 |
| `tools/sil` | python | 16 | 8 |
| `tools/spice` | python | 47 | 30 |
| `tools/spice/challenger` | python | 15 | 10 |

## Architecture Pattern

_No specific architecture pattern detected._

## Entry Points

- **handler**: `firmware/components/webui.webui_server_start` (firmware/components/webui/server.c)
- **handler**: `firmware/components/webui.webui_server_stop` (firmware/components/webui/server.c)
- **handler**: `firmware/components/webui/include.webui_server_init` (firmware/components/webui/include/webui_server.h)
- **handler**: `firmware/components/webui/include.webui_server_start` (firmware/components/webui/include/webui_server.h)
- **handler**: `firmware/components/webui/include.webui_server_stop` (firmware/components/webui/include/webui_server.h)
- **handler**: `firmware/test.test_fault_labels_preserved` (firmware/test/test_fault_list_generated.c)
- **handler**: `packages/temper-placer/src/temper_placer/io/kicad_writer.strip_routing_preserve_nets` (packages/temper-placer/src/temper_placer/io/kicad_writer.py)
- **handler**: `packages/temper-placer/src/temper_placer/pcl/sat_bridge.register_handler` (packages/temper-placer/src/temper_placer/pcl/sat_bridge.py)
- **handler**: `packages/temper-placer/src/temper_placer/router_v6/routing_failure_handler.handle_routing_failures` (packages/temper-placer/src/temper_placer/router_v6/routing_failure_handler.py)
- **handler**: `packages/temper-placer/src/temper_placer/router_v6/via_grid_reservation.reserve_via_positions` (packages/temper-placer/src/temper_placer/router_v6/via_grid_reservation.py)
- **handler**: `packages/temper-placer/src/temper_placer/visualization/server.create_server` (packages/temper-placer/src/temper_placer/visualization/server.py)
- **handler**: `packages/temper-placer/tests/deterministic/stages/test_deterministic_invariants_pbt.test_component_count_preserved` (packages/temper-placer/tests/deterministic/stages/test_deterministic_invariants_pbt.py)
- **handler**: `packages/temper-placer/tests/deterministic/stages/test_deterministic_invariants_pbt.test_empty_board_state_handled_gracefully` (packages/temper-placer/tests/deterministic/stages/test_deterministic_invariants_pbt.py)
- **handler**: `packages/temper-placer/tests/io/test_dsn_normalizer.test_normalize_preserves_schema_version` (packages/temper-placer/tests/io/test_dsn_normalizer.py)
- **handler**: `packages/temper-placer/tests/io/test_via_dedup.test_distinct_positions_preserved` (packages/temper-placer/tests/io/test_via_dedup.py)
- **handler**: `packages/temper-placer/tests/pcl/test_integration_auto_enrich.test_enrich_preserves_existing_constraints` (packages/temper-placer/tests/pcl/test_integration_auto_enrich.py)
- **handler**: `packages/temper-placer/tests/pipeline/conftest.mock_observer` (packages/temper-placer/tests/pipeline/conftest.py)
- **handler**: `packages/temper-placer/tests/router_v6/test_acid_trap_boundary.test_none_vias_handled` (packages/temper-placer/tests/router_v6/test_acid_trap_boundary.py)
- **handler**: `packages/temper-placer/tests/router_v6/test_acid_trap_induction.test_acid_trap_modify_preserves_compliance` (packages/temper-placer/tests/router_v6/test_acid_trap_induction.py)
- **handler**: `packages/temper-placer/tests/router_v6/test_acid_trap_induction.test_acid_trap_remove_preserves_compliance` (packages/temper-placer/tests/router_v6/test_acid_trap_induction.py)
- **handler**: `packages/temper-placer/tests/router_v6/test_annular_ring_induction.test_annular_ring_modify_preserves_compliance` (packages/temper-placer/tests/router_v6/test_annular_ring_induction.py)
- **handler**: `packages/temper-placer/tests/router_v6/test_annular_ring_induction.test_annular_ring_remove_preserves_compliance` (packages/temper-placer/tests/router_v6/test_annular_ring_induction.py)
- **handler**: `packages/temper-placer/tests/router_v6/test_bundled_equivalence.test_safety_constraints_preserved` (packages/temper-placer/tests/router_v6/test_bundled_equivalence.py)
- **handler**: `packages/temper-placer/tests/router_v6/test_clearance_induction.test_clearance_modify_preserves_compliance` (packages/temper-placer/tests/router_v6/test_clearance_induction.py)
- **handler**: `packages/temper-placer/tests/router_v6/test_clearance_induction.test_clearance_remove_preserves_compliance` (packages/temper-placer/tests/router_v6/test_clearance_induction.py)
- **handler**: `packages/temper-placer/tests/router_v6/test_copper_balance_induction.test_copper_balance_modify_preserves_compliance` (packages/temper-placer/tests/router_v6/test_copper_balance_induction.py)
- **handler**: `packages/temper-placer/tests/router_v6/test_copper_balance_induction.test_copper_balance_remove_preserves_compliance` (packages/temper-placer/tests/router_v6/test_copper_balance_induction.py)
- **handler**: `packages/temper-placer/tests/router_v6/test_creepage_induction.test_creepage_modify_preserves_compliance` (packages/temper-placer/tests/router_v6/test_creepage_induction.py)
- **handler**: `packages/temper-placer/tests/router_v6/test_creepage_induction.test_creepage_remove_preserves_compliance` (packages/temper-placer/tests/router_v6/test_creepage_induction.py)
- **handler**: `packages/temper-placer/tests/router_v6/test_grid_update.test_update_grid_marks_cells_reserved` (packages/temper-placer/tests/router_v6/test_grid_update.py)
- **handler**: `packages/temper-placer/tests/router_v6/test_manufacturing_report_induction.test_manufacturing_report_modify_preserves_compliance` (packages/temper-placer/tests/router_v6/test_manufacturing_report_induction.py)
- **handler**: `packages/temper-placer/tests/router_v6/test_manufacturing_report_induction.test_manufacturing_report_remove_preserves_compliance` (packages/temper-placer/tests/router_v6/test_manufacturing_report_induction.py)
- **handler**: `packages/temper-placer/tests/router_v6/test_routing_failure_handler.test_handle_routing_failures` (packages/temper-placer/tests/router_v6/test_routing_failure_handler.py)
- **handler**: `packages/temper-placer/tests/router_v6/test_routing_failure_handler.test_no_failures` (packages/temper-placer/tests/router_v6/test_routing_failure_handler.py)
- **handler**: `packages/temper-placer/tests/router_v6/test_teardrop_induction.test_teardrop_modify_preserves_compliance` (packages/temper-placer/tests/router_v6/test_teardrop_induction.py)
- **handler**: `packages/temper-placer/tests/router_v6/test_teardrop_induction.test_teardrop_remove_preserves_compliance` (packages/temper-placer/tests/router_v6/test_teardrop_induction.py)
- **handler**: `packages/temper-placer/tests/router_v6/test_thermal_relief_induction.test_thermal_relief_modify_preserves_compliance` (packages/temper-placer/tests/router_v6/test_thermal_relief_induction.py)
- **handler**: `packages/temper-placer/tests/router_v6/test_thermal_relief_induction.test_thermal_relief_remove_preserves_compliance` (packages/temper-placer/tests/router_v6/test_thermal_relief_induction.py)
- **handler**: `packages/temper-placer/tests/router_v6/test_via_grid_reservation.test_reserve_via_positions_basic` (packages/temper-placer/tests/router_v6/test_via_grid_reservation.py)
- **handler**: `packages/temper-placer/tests/router_v6/test_via_grid_reservation.test_reserve_via_positions_custom_grid` (packages/temper-placer/tests/router_v6/test_via_grid_reservation.py)
- **handler**: `packages/temper-placer/tests/router_v6/test_via_grid_reservation.test_reserve_via_positions_grid_snapping` (packages/temper-placer/tests/router_v6/test_via_grid_reservation.py)
- **handler**: `packages/temper-placer/tests/router_v6/test_via_grid_reservation.test_reserved_via_blocked_layers` (packages/temper-placer/tests/router_v6/test_via_grid_reservation.py)
- **handler**: `packages/temper-placer/tests/router_v6/test_via_grid_reservation.test_reserved_via_through_via_detection` (packages/temper-placer/tests/router_v6/test_via_grid_reservation.py)
- **handler**: `packages/temper-placer/tests/router_v6/test_wave3_skip_sat.test_r7_default_false_preserves_existing_behavior` (packages/temper-placer/tests/router_v6/test_wave3_skip_sat.py)
- **handler**: `packages/temper-placer/tests/router_v6/test_wave3_skip_sat.test_r8_map_topology_to_channels_handles_none_topology` (packages/temper-placer/tests/router_v6/test_wave3_skip_sat.py)
- **handler**: `packages/temper-placer/tests/test_metrics_observer.eight_stage_manifest` (packages/temper-placer/tests/test_metrics_observer.py)
- **handler**: `packages/temper-placer/tests/test_metrics_observer.execution_log` (packages/temper-placer/tests/test_metrics_observer.py)
- **handler**: `packages/temper-placer/tests/test_metrics_observer.passthrough_manifest` (packages/temper-placer/tests/test_metrics_observer.py)
- **handler**: `packages/temper-placer/tests/test_metrics_observer.sample_config` (packages/temper-placer/tests/test_metrics_observer.py)
- **handler**: `packages/temper-placer/tests/test_metrics_observer.single_stage_manifest` (packages/temper-placer/tests/test_metrics_observer.py)
- **handler**: `packages/temper-placer/tests/test_round_trip_integrity.test_round_trip_component_count_preserved` (packages/temper-placer/tests/test_round_trip_integrity.py)
- **handler**: `packages/temper-placer/tests/visualization/test_server.minimal_state` (packages/temper-placer/tests/visualization/test_server.py)
- **handler**: `packages/temper-placer/tests/visualization/test_server.state_with_data` (packages/temper-placer/tests/visualization/test_server.py)
- **main**: `Eagle2Kicad/Start.main` (Eagle2Kicad/Start.py)
- **main**: `components/LMR51420/test_files/verify_simple.main` (components/LMR51420/test_files/verify_simple.py)
- **main**: `components/LMR51420/test_files/verify_spice_simulation.main` (components/LMR51420/test_files/verify_spice_simulation.py)
- **main**: `components/UCC27511A/verify_ucc27511a.main` (components/UCC27511A/verify_ucc27511a.py)
- **main**: `firmware/test.main` (firmware/test/test_fault_list_generated.c)
- **main**: `firmware/test/gen_transition_table.main` (firmware/test/gen_transition_table.py)
- **main**: `firmware/tools/check_config_matches_manifest.main` (firmware/tools/check_config_matches_manifest.py)
- **main**: `firmware/tools/gen_config.main` (firmware/tools/gen_config.py)
- **main**: `firmware/tools/gen_fault_list.main` (firmware/tools/gen_fault_list.py)
- **main**: `firmware/tools/gen_transition_table.main` (firmware/tools/gen_transition_table.py)
- **main**: `packages/temper-autoprof/src/temper_autoprof/cli.main` (packages/temper-autoprof/src/temper_autoprof/cli.py)
- **main**: `packages/temper-placer/benchmarks/bench_demand_budget.main` (packages/temper-placer/benchmarks/bench_demand_budget.py)
- **main**: `packages/temper-placer/benchmarks/bench_net_ordering.main` (packages/temper-placer/benchmarks/bench_net_ordering.py)
- **main**: `packages/temper-placer/benchmarks/bench_optimizer.main` (packages/temper-placer/benchmarks/bench_optimizer.py)
- **main**: `packages/temper-placer/examples/demo_constraint_builder.main` (packages/temper-placer/examples/demo_constraint_builder.py)
- **main**: `packages/temper-placer/examples/demo_constraint_reporting.main` (packages/temper-placer/examples/demo_constraint_reporting.py)
- **main**: `packages/temper-placer/examples/demo_integrated_pipeline.main` (packages/temper-placer/examples/demo_integrated_pipeline.py)
- **main**: `packages/temper-placer/research/inductance_model_comparison.main` (packages/temper-placer/research/inductance_model_comparison.py)
- **main**: `packages/temper-placer/scripts/analysis/analyze_gnd_connections.main` (packages/temper-placer/scripts/analysis/analyze_gnd_connections.py)
- **main**: `packages/temper-placer/scripts/analysis/analyze_power_placement.main` (packages/temper-placer/scripts/analysis/analyze_power_placement.py)
- **main**: `packages/temper-placer/scripts/analyze_centrality.main` (packages/temper-placer/scripts/analyze_centrality.py)
- **main**: `packages/temper-placer/scripts/analyze_seed_sensitivity.main` (packages/temper-placer/scripts/analyze_seed_sensitivity.py)
- **main**: `packages/temper-placer/scripts/characterize_pathological_seeds.main` (packages/temper-placer/scripts/characterize_pathological_seeds.py)
- **main**: `packages/temper-placer/scripts/compare_initialization.main` (packages/temper-placer/scripts/compare_initialization.py)
- **main**: `packages/temper-placer/scripts/demo_drc_oracle.main` (packages/temper-placer/scripts/demo_drc_oracle.py)
- **main**: `packages/temper-placer/scripts/diagnose_failures.main` (packages/temper-placer/scripts/diagnose_failures.py)
- **main**: `packages/temper-placer/scripts/export_dsn.main` (packages/temper-placer/scripts/export_dsn.py)
- **main**: `packages/temper-placer/scripts/profile_memory_scale.main` (packages/temper-placer/scripts/profile_memory_scale.py)
- **main**: `packages/temper-placer/scripts/profile_routing.main` (packages/temper-placer/scripts/profile_routing.py)
- **main**: `packages/temper-placer/scripts/spike_drc_proxy_correlation.main` (packages/temper-placer/scripts/spike_drc_proxy_correlation.py)
- **main**: `packages/temper-placer/scripts/tune_jiggle.main` (packages/temper-placer/scripts/tune_jiggle.py)
- **main**: `packages/temper-placer/scripts/tune_ramp_rate.main` (packages/temper-placer/scripts/tune_ramp_rate.py)
- **main**: `packages/temper-placer/scripts/validate_core_routing.main` (packages/temper-placer/scripts/validate_core_routing.py)
- **main**: `packages/temper-placer/scripts/validate_spectral_init.main` (packages/temper-placer/scripts/validate_spectral_init.py)
- **main**: `packages/temper-placer/scripts/verify_spectral_wirelength.main` (packages/temper-placer/scripts/verify_spectral_wirelength.py)
- **main**: `packages/temper-placer/src/temper_placer/analysis/run_correlation_analysis.main` (packages/temper-placer/src/temper_placer/analysis/run_correlation_analysis.py)
- **main**: `packages/temper-placer/src/temper_placer/cli/__init__.main` (packages/temper-placer/src/temper_placer/cli/__init__.py)
- **main**: `packages/temper-placer/src/temper_placer/cli/drc_cli.main` (packages/temper-placer/src/temper_placer/cli/drc_cli.py)
- **main**: `packages/temper-placer/src/temper_placer/experiments/seed_robustness_validation.main` (packages/temper-placer/src/temper_placer/experiments/seed_robustness_validation.py)
- **main**: `packages/temper-placer/src/temper_placer/ml/train_gnn.main` (packages/temper-placer/src/temper_placer/ml/train_gnn.py)
- **main**: `packages/temper-placer/src/temper_placer/regression/cli.main` (packages/temper-placer/src/temper_placer/regression/cli.py)
- **main**: `packages/temper-placer/src/temper_placer/regression/measure_closure.main` (packages/temper-placer/src/temper_placer/regression/measure_closure.py)
- **main**: `packages/temper-placer/src/temper_placer/router_v6/benchmark.main` (packages/temper-placer/src/temper_placer/router_v6/benchmark.py)
- **main**: `packages/temper-placer/tests/fixtures/external/download_pcbs.main` (packages/temper-placer/tests/fixtures/external/download_pcbs.py)
- **main**: `packages/temper-placer/tests/fixtures/generate_large_board.main` (packages/temper-placer/tests/fixtures/generate_large_board.py)
- **main**: `packages/temper-placer/tests/fixtures/generators/generate_pitchfork.main` (packages/temper-placer/tests/fixtures/generators/generate_pitchfork.py)
- **main**: `packages/temper-tools/src/temper_tools/ato/diff.main` (packages/temper-tools/src/temper_tools/ato/diff.py)
- **main**: `packages/temper-tools/src/temper_tools/routing/route.main` (packages/temper-tools/src/temper_tools/routing/route.py)
- **main**: `packages/temper-validation/src/temper_validation/cli.main` (packages/temper-validation/src/temper_validation/cli.py)
- **main**: `packages/temper-workflow/src/temper_workflow/metrics/aesthetic_turing_test.main` (packages/temper-workflow/src/temper_workflow/metrics/aesthetic_turing_test.py)
- **main**: `packages/temper-workflow/src/temper_workflow/metrics/compare_refinement.main` (packages/temper-workflow/src/temper_workflow/metrics/compare_refinement.py)
- **main**: `packages/temper-workflow/src/temper_workflow/metrics/measure_displacement.main` (packages/temper-workflow/src/temper_workflow/metrics/measure_displacement.py)
- **main**: `packages/temper-workflow/src/temper_workflow/routing/route_and_measure.main` (packages/temper-workflow/src/temper_workflow/routing/route_and_measure.py)
- **main**: `packages/temper-workflow/src/temper_workflow/routing/steiner_sweep.main` (packages/temper-workflow/src/temper_workflow/routing/steiner_sweep.py)
- **main**: `scripts/batch_pipeline_validate.main` (scripts/batch_pipeline_validate.py)
- **main**: `scripts/bench_coarse_to_fine.main` (scripts/bench_coarse_to_fine.py)
- **main**: `scripts/bench_rust_constraints.main` (scripts/bench_rust_constraints.py)
- **main**: `scripts/benchmark_numba_los.main` (scripts/benchmark_numba_los.py)
- **main**: `scripts/bless_baselines.main` (scripts/bless_baselines.py)
- **main**: `scripts/bmc_adoption_gate.main` (scripts/bmc_adoption_gate.py)
- **main**: `scripts/calibrate_drc_ceiling.main` (scripts/calibrate_drc_ceiling.py)
- **main**: `scripts/check_coverage_gate.main` (scripts/check_coverage_gate.py)
- **main**: `scripts/check_fault_list_consistency.main` (scripts/check_fault_list_consistency.py)
- **main**: `scripts/check_manifest_gate.main` (scripts/check_manifest_gate.py)
- **main**: `scripts/check_perf_regression.main` (scripts/check_perf_regression.py)
- **main**: `scripts/check_script_sunset.main` (scripts/check_script_sunset.py)
- **main**: `scripts/check_traceability.main` (scripts/check_traceability.py)
- **main**: `scripts/check_typecheck_gate.main` (scripts/check_typecheck_gate.py)
- **main**: `scripts/ci_check_drc.main` (scripts/ci_check_drc.py)
- **main**: `scripts/ci_closure_test.main` (scripts/ci_closure_test.py)
- **main**: `scripts/debug_diff_pair_path.main` (scripts/debug_diff_pair_path.py)
- **main**: `scripts/extract_corpus_baselines.main` (scripts/extract_corpus_baselines.py)
- **main**: `scripts/full_pipeline_profile.main` (scripts/full_pipeline_profile.py)
- **main**: `scripts/generate_kicad_dru.main` (scripts/generate_kicad_dru.py)
- **main**: `scripts/human_reference_compare.main` (scripts/human_reference_compare.py)
- **main**: `scripts/import_linter_gate.main` (scripts/import_linter_gate.py)
- **main**: `scripts/internal_route.main` (scripts/internal_route.py)
- **main**: `scripts/pipeline_metrics.main` (scripts/pipeline_metrics.py)
- **main**: `scripts/pipeline_report.main` (scripts/pipeline_report.py)
- **main**: `scripts/placement_quality_report.main` (scripts/placement_quality_report.py)
- **main**: `scripts/pr_perf_compare.main` (scripts/pr_perf_compare.py)
- **main**: `scripts/pr_scorecard.main` (scripts/pr_scorecard.py)
- **main**: `scripts/profile_router_v6_sampling.main` (scripts/profile_router_v6_sampling.py)
- **main**: `scripts/profile_rust_topology.main` (scripts/profile_rust_topology.py)
- **main**: `scripts/quarantine_report.main` (scripts/quarantine_report.py)
- **main**: `scripts/reconcile_metrics.main` (scripts/reconcile_metrics.py)
- **main**: `scripts/run_feedback_loop.main` (scripts/run_feedback_loop.py)
- **main**: `scripts/scan_external_corpus.main` (scripts/scan_external_corpus.py)
- **main**: `scripts/trace_invocations.main` (scripts/trace_invocations.py)
- **main**: `scripts/update_regression_cache.main` (scripts/update_regression_cache.py)
- **main**: `scripts/validate_footprints.main` (scripts/validate_footprints.py)
- **main**: `scripts/verify_proofs.main` (scripts/verify_proofs.py)
- **main**: `scripts/vulture_gate.main` (scripts/vulture_gate.py)
- **main**: `test-boards/mvb/generate_mvbs.main` (test-boards/mvb/generate_mvbs.py)
- **main**: `test-boards/mvb/test_mvb_progression.main` (test-boards/mvb/test_mvb_progression.py)
- **main**: `tests/test_diff_pair_comprehensive.main` (tests/test_diff_pair_comprehensive.py)
- **main**: `tools/check_kicad_layers.main` (tools/check_kicad_layers.py)
- **main**: `tools/clone_and_extract_pcbs.main` (tools/clone_and_extract_pcbs.py)
- **main**: `tools/fix_unused_args.main` (tools/fix_unused_args.py)
- **main**: `tools/loc_cap_check.main` (tools/loc_cap_check.py)
- **main**: `tools/scrape_github_pcbs.main` (tools/scrape_github_pcbs.py)
- **main**: `tools/setup_kicad_env.main` (tools/setup_kicad_env.py)
- **main**: `tools/sil/check_coverage.main` (tools/sil/check_coverage.py)
- **main**: `tools/sil/generate_traces.main` (tools/sil/generate_traces.py)
- **main**: `tools/sil/perturb.main` (tools/sil/perturb.py)
- **main**: `tools/sil/plant_model.main` (tools/sil/plant_model.py)
- **main**: `tools/spice/corner_sweep.main` (tools/spice/corner_sweep.py)
- **main**: `tools/spice/extract.main` (tools/spice/extract.py)
- **main**: `tools/spice/inject_parasitics.main` (tools/spice/inject_parasitics.py)
- **main**: `tools/spice/sign_off.main` (tools/spice/sign_off.py)
- **main**: `tools/spice/sim_runner.main` (tools/spice/sim_runner.py)

## Dependency Rules

- `Eagle2Kicad/Board` -> `Eagle2Kicad/Common`
- `Eagle2Kicad/Library` -> `Eagle2Kicad/Common`
- `Eagle2Kicad` -> `Eagle2Kicad/Board`
- `Eagle2Kicad` -> `Eagle2Kicad/Library`
- `firmware/components/control` -> `firmware/components/control`
- `firmware/components/hal/esp32` -> `firmware/components/hal/include`
- `firmware/components/hal/include` -> `firmware/components/hal/include`
- `firmware/components/hal/mock` -> `firmware/components/hal/include`
- `firmware/components/safety/include` -> `firmware/components/hal/include`
- `firmware/components/safety` -> `firmware/components/control`
- `firmware/components/safety` -> `firmware/components/hal/include`
- `firmware/components/safety` -> `firmware/components/safety/include`
- `firmware/components/safety` -> `firmware/components/safety`
- `firmware/components/testing` -> `firmware/test/unity`
- `firmware/components/webui` -> `firmware/components/webui/include`
- `firmware/main` -> `firmware/components/control`
- `firmware/main` -> `firmware/components/hal/include`
- `firmware/main` -> `firmware/components/safety`
- `firmware/main` -> `firmware/main`
- `firmware/main` -> `firmware`
- `firmware/test/unity` -> `firmware/test/unity`
- `firmware/test` -> `firmware/components/control`
- `firmware/test` -> `firmware/components/hal/include`
- `firmware/test` -> `firmware/components/safety/include`
- `firmware/test` -> `firmware/components/safety`
- `firmware/test` -> `firmware/main`
- `firmware/test` -> `firmware/test/unity`
- `firmware/test` -> `firmware/test`
- `firmware/test` -> `firmware`
- `firmware` -> `firmware`
- `packages/temper-placer/benchmarks` -> `packages/temper-placer/src/temper_placer/core`
- `packages/temper-placer/benchmarks` -> `packages/temper-placer/src/temper_placer/losses`
- `packages/temper-placer/benchmarks` -> `packages/temper-placer/src/temper_placer/optimizer`
- `packages/temper-placer/benchmarks` -> `packages/temper-placer/src/temper_placer/router_v6`
- `packages/temper-placer/benchmarks` -> `packages/temper-placer/tests/fixtures/generators`
- `packages/temper-placer/examples` -> `packages/temper-placer/src/temper_placer/constraints`
- `packages/temper-placer/examples` -> `packages/temper-placer/src/temper_placer/deterministic`
- `packages/temper-placer/examples` -> `packages/temper-placer/src/temper_placer/io`
- `packages/temper-placer/scripts/analysis` -> `packages/temper-placer/src/temper_placer/io`
- `packages/temper-placer/scripts` -> `packages/temper-placer/src/temper_placer/core`
- `packages/temper-placer/scripts` -> `packages/temper-placer/src/temper_placer/io`
- `packages/temper-placer/scripts` -> `packages/temper-placer/src/temper_placer/losses`
- `packages/temper-placer/scripts` -> `packages/temper-placer/src/temper_placer/optimizer`
- `packages/temper-placer/scripts` -> `packages/temper-placer/src/temper_placer/router_v6`
- `packages/temper-placer/scripts` -> `packages/temper-placer/src/temper_placer/scale`
- `packages/temper-placer/src/temper_placer/_constraint_types` -> `packages/temper-placer/src/temper_placer/core`
- `packages/temper-placer/src/temper_placer/ablation` -> `packages/temper-placer/src/temper_placer/optimizer`
- `packages/temper-placer/src/temper_placer/adapters` -> `packages/temper-placer/src/temper_placer`
- `packages/temper-placer/src/temper_placer/algo` -> `packages/temper-placer/src/temper_placer/core`
- `packages/temper-placer/src/temper_placer/cli` -> `packages/temper-placer/src/temper_placer/io`
- `packages/temper-placer/src/temper_placer/cli` -> `packages/temper-placer/src/temper_placer/pipeline`
- `packages/temper-placer/src/temper_placer/cli` -> `packages/temper-placer/src/temper_placer/profiling`
- `packages/temper-placer/src/temper_placer/cli` -> `packages/temper-placer/src/temper_placer/report`
- `packages/temper-placer/src/temper_placer/cli` -> `packages/temper-placer/src/temper_placer/validation`
- `packages/temper-placer/src/temper_placer/cli` -> `packages/temper-placer/src/temper_placer`
- `packages/temper-placer/src/temper_placer/constraints` -> `packages/temper-placer/src/temper_placer/_constraint_types`
- `packages/temper-placer/src/temper_placer/deterministic/feedback` -> `packages/temper-placer/src/temper_placer/deterministic`
- `packages/temper-placer/src/temper_placer/deterministic/stages` -> `.`
- `packages/temper-placer/src/temper_placer/deterministic/stages` -> `packages/temper-placer/src/temper_placer/constraints`
- `packages/temper-placer/src/temper_placer/deterministic/stages` -> `packages/temper-placer/src/temper_placer/core`
- `packages/temper-placer/src/temper_placer/deterministic/stages` -> `packages/temper-placer/src/temper_placer/io`
- `packages/temper-placer/src/temper_placer/deterministic/stages` -> `packages/temper-placer/src/temper_placer/router_v6`
- `packages/temper-placer/src/temper_placer/deterministic` -> `packages/temper-placer/src/temper_placer/validation`
- `packages/temper-placer/src/temper_placer/experiments` -> `packages/temper-placer/src/temper_placer/core`
- `packages/temper-placer/src/temper_placer/experiments` -> `packages/temper-placer/src/temper_placer/geometry`
- `packages/temper-placer/src/temper_placer/experiments` -> `packages/temper-placer/src/temper_placer/losses`
- `packages/temper-placer/src/temper_placer/experiments` -> `packages/temper-placer/src/temper_placer/optimizer`
- `packages/temper-placer/src/temper_placer/extraction` -> `packages/temper-placer/src/temper_placer/core`
- `packages/temper-placer/src/temper_placer/fixtures` -> `packages/temper-placer/src/temper_placer/core`
- `packages/temper-placer/src/temper_placer/fixtures` -> `packages/temper-placer/src/temper_placer/io`
- `packages/temper-placer/src/temper_placer/geometry` -> `packages/temper-placer/src/temper_placer/core`
- `packages/temper-placer/src/temper_placer/heuristics` -> `packages/temper-placer/src/temper_placer/core`
- `packages/temper-placer/src/temper_placer/heuristics` -> `packages/temper-placer/src/temper_placer/io`
- `packages/temper-placer/src/temper_placer/heuristics` -> `packages/temper-placer/src/temper_placer/placer`
- `packages/temper-placer/src/temper_placer/heuristics` -> `packages/temper-placer/src/temper_placer/router_v6`
- `packages/temper-placer/src/temper_placer/heuristics` -> `packages/temper-placer/src/temper_placer/topological`
- `packages/temper-placer/src/temper_placer/io` -> `packages/temper-placer/src/temper_placer/_constraint_types`
- `packages/temper-placer/src/temper_placer/io` -> `packages/temper-placer/src/temper_placer/core`
- `packages/temper-placer/src/temper_placer/io` -> `packages/temper-placer/src/temper_placer/deterministic/geometry`
- `packages/temper-placer/src/temper_placer/io` -> `packages/temper-placer/src/temper_placer/losses`
- `packages/temper-placer/src/temper_placer/io` -> `packages/temper-placer/src/temper_placer/router_v6`
- `packages/temper-placer/src/temper_placer/losses/physics` -> `packages/temper-placer/src/temper_placer/core`
- `packages/temper-placer/src/temper_placer/losses/physics` -> `packages/temper-placer/src/temper_placer/losses`
- `packages/temper-placer/src/temper_placer/losses` -> `packages/temper-placer/src/temper_placer/core`
- `packages/temper-placer/src/temper_placer/losses` -> `packages/temper-placer/src/temper_placer/extraction`
- `packages/temper-placer/src/temper_placer/losses` -> `packages/temper-placer/src/temper_placer/geometry`
- `packages/temper-placer/src/temper_placer/losses` -> `packages/temper-placer/src/temper_placer/io`
- `packages/temper-placer/src/temper_placer/losses` -> `packages/temper-placer/src/temper_placer/validation`
- `packages/temper-placer/src/temper_placer/manufacturing` -> `packages/temper-placer/src/temper_placer/core`
- `packages/temper-placer/src/temper_placer/metrics` -> `packages/temper-placer/src/temper_placer/core`
- `packages/temper-placer/src/temper_placer/metrics` -> `packages/temper-placer/src/temper_placer/losses`
- `packages/temper-placer/src/temper_placer/metrics` -> `packages/temper-placer/src/temper_placer/router_v6`
- `packages/temper-placer/src/temper_placer/metrics` -> `packages/temper-placer/src/temper_placer/validation`
- `packages/temper-placer/src/temper_placer/ml` -> `packages/temper-placer/src/temper_placer/core`
- `packages/temper-placer/src/temper_placer/ml` -> `packages/temper-placer/src/temper_placer/io`
- `packages/temper-placer/src/temper_placer/optimizer` -> `packages/temper-placer/src/temper_placer/core`
- `packages/temper-placer/src/temper_placer/optimizer` -> `packages/temper-placer/src/temper_placer/explainability`
- `packages/temper-placer/src/temper_placer/optimizer` -> `packages/temper-placer/src/temper_placer/geometry`
- `packages/temper-placer/src/temper_placer/optimizer` -> `packages/temper-placer/src/temper_placer/heuristics`
- `packages/temper-placer/src/temper_placer/optimizer` -> `packages/temper-placer/src/temper_placer/io`
- `packages/temper-placer/src/temper_placer/optimizer` -> `packages/temper-placer/src/temper_placer/losses`
- `packages/temper-placer/src/temper_placer/optimizer` -> `packages/temper-placer/src/temper_placer/ml`
- `packages/temper-placer/src/temper_placer/optimizer` -> `packages/temper-placer/src/temper_placer/pipeline`
- `packages/temper-placer/src/temper_placer/optimizer` -> `packages/temper-placer/src/temper_placer/validation`
- `packages/temper-placer/src/temper_placer/pcl` -> `packages/temper-placer/src/temper_placer/core`
- `packages/temper-placer/src/temper_placer/pcl` -> `packages/temper-placer/src/temper_placer/losses`
- `packages/temper-placer/src/temper_placer/pcl` -> `packages/temper-placer/src/temper_placer/router_v6`
- `packages/temper-placer/src/temper_placer/pipeline/stages` -> `packages/temper-placer/src/temper_placer/pipeline`
- `packages/temper-placer/src/temper_placer/pipeline/stages` -> `packages/temper-placer/src/temper_placer/router_v6`
- `packages/temper-placer/src/temper_placer/pipeline` -> `packages/temper-placer/src/temper_placer/core`
- `packages/temper-placer/src/temper_placer/pipeline` -> `packages/temper-placer/src/temper_placer/heuristics`
- `packages/temper-placer/src/temper_placer/pipeline` -> `packages/temper-placer/src/temper_placer/losses`
- `packages/temper-placer/src/temper_placer/pipeline` -> `packages/temper-placer/src/temper_placer/optimizer`
- `packages/temper-placer/src/temper_placer/pipeline` -> `packages/temper-placer/src/temper_placer/pcl`
- `packages/temper-placer/src/temper_placer/pipeline` -> `packages/temper-placer/src/temper_placer/placer`
- `packages/temper-placer/src/temper_placer/pipeline` -> `packages/temper-placer/src/temper_placer/regression`
- `packages/temper-placer/src/temper_placer/pipeline` -> `packages/temper-placer/src/temper_placer/router_v6`
- `packages/temper-placer/src/temper_placer/placement` -> `packages/temper-placer/src/temper_placer/core`
- `packages/temper-placer/src/temper_placer/placement` -> `packages/temper-placer/src/temper_placer/placer`
- `packages/temper-placer/src/temper_placer/placement` -> `packages/temper-placer/src/temper_placer/router_v6`
- `packages/temper-placer/src/temper_placer/profiling/validation` -> `packages/temper-placer/src/temper_placer/deterministic`
- `packages/temper-placer/src/temper_placer/profiling` -> `packages/temper-placer/src/temper_placer/regression`
- `packages/temper-placer/src/temper_placer/regression` -> `packages/temper-placer/src/temper_placer/adapters`
- `packages/temper-placer/src/temper_placer/regression` -> `packages/temper-placer/src/temper_placer/core`
- `packages/temper-placer/src/temper_placer/regression` -> `packages/temper-placer/src/temper_placer/heuristics`
- `packages/temper-placer/src/temper_placer/regression` -> `packages/temper-placer/src/temper_placer/io`
- `packages/temper-placer/src/temper_placer/regression` -> `packages/temper-placer/src/temper_placer/losses`
- `packages/temper-placer/src/temper_placer/regression` -> `packages/temper-placer/src/temper_placer/metrics`
- `packages/temper-placer/src/temper_placer/regression` -> `packages/temper-placer/src/temper_placer/optimizer`
- `packages/temper-placer/src/temper_placer/regression` -> `packages/temper-placer/src/temper_placer/pipeline`
- `packages/temper-placer/src/temper_placer/router_v6` -> `packages/temper-placer/src/temper_placer/core`
- `packages/temper-placer/src/temper_placer/router_v6` -> `packages/temper-placer/src/temper_placer/deterministic/stages`
- `packages/temper-placer/src/temper_placer/router_v6` -> `packages/temper-placer/src/temper_placer/deterministic`
- `packages/temper-placer/src/temper_placer/router_v6` -> `packages/temper-placer/src/temper_placer/io`
- `packages/temper-placer/src/temper_placer/router_v6` -> `packages/temper-placer/src/temper_placer/placement`
- `packages/temper-placer/src/temper_placer/router_v6` -> `packages/temper-placer/src/temper_placer/validation`
- `packages/temper-placer/src/temper_placer/scale` -> `packages/temper-placer/src/temper_placer/core`
- `packages/temper-placer/src/temper_placer/scale` -> `packages/temper-placer/src/temper_placer/io`
- `packages/temper-placer/src/temper_placer/scale` -> `packages/temper-placer/src/temper_placer/losses`
- `packages/temper-placer/src/temper_placer/scale` -> `packages/temper-placer/src/temper_placer/optimizer`
- `packages/temper-placer/src/temper_placer/scale` -> `packages/temper-placer/src/temper_placer/validation`
- `packages/temper-placer/src/temper_placer/templates` -> `packages/temper-placer/src/temper_placer/core`
- `packages/temper-placer/src/temper_placer/topological` -> `packages/temper-placer/src/temper_placer/core`
- `packages/temper-placer/src/temper_placer/validation` -> `packages/temper-placer/src/temper_placer/core`
- `packages/temper-placer/src/temper_placer/validation` -> `packages/temper-placer/src/temper_placer/experiments`
- `packages/temper-placer/src/temper_placer/validation` -> `packages/temper-placer/src/temper_placer/geometry`
- `packages/temper-placer/src/temper_placer/validation` -> `packages/temper-placer/src/temper_placer/io`
- `packages/temper-placer/src/temper_placer/validation` -> `packages/temper-placer/src/temper_placer/losses`
- `packages/temper-placer/src/temper_placer/visualization` -> `packages/temper-placer/src/temper_placer/core`
- `packages/temper-placer/src/temper_placer` -> `packages/temper-placer/src/temper_placer/cli`
- `packages/temper-placer/src/temper_placer` -> `packages/temper-placer/src/temper_placer/core`
- `packages/temper-placer/tests/ablation` -> `packages/temper-placer/src/temper_placer/ablation`
- `packages/temper-placer/tests/ablation` -> `packages/temper-placer/src/temper_placer/core`
- `packages/temper-placer/tests/algo` -> `packages/temper-placer/src/temper_placer/algo`
- `packages/temper-placer/tests/algo` -> `packages/temper-placer/src/temper_placer/core`
- `packages/temper-placer/tests/algo` -> `packages/temper-placer/src/temper_placer/extraction`
- `packages/temper-placer/tests/analysis` -> `packages/temper-placer/src/temper_placer/analysis`
- `packages/temper-placer/tests/cli` -> `packages/temper-placer/src/temper_placer/cli`
- `packages/temper-placer/tests/cli` -> `packages/temper-placer/src/temper_placer/pipeline`
- `packages/temper-placer/tests/comparison` -> `packages/temper-placer/src/temper_placer/core`
- `packages/temper-placer/tests/comparison` -> `packages/temper-placer/src/temper_placer/io`
- `packages/temper-placer/tests/comparison` -> `packages/temper-placer/src/temper_placer/losses`
- `packages/temper-placer/tests/comparison` -> `packages/temper-placer/src/temper_placer/optimizer`
- `packages/temper-placer/tests/comparison` -> `packages/temper-placer/tests/fixtures/external`
- `packages/temper-placer/tests/constraints` -> `packages/temper-placer/src/temper_placer/constraints`
- `packages/temper-placer/tests/constraints` -> `packages/temper-placer/src/temper_placer/io`
- `packages/temper-placer/tests/core` -> `packages/temper-placer/src/temper_placer/core`
- `packages/temper-placer/tests/core` -> `packages/temper-placer/src/temper_placer/extraction`
- `packages/temper-placer/tests/core` -> `packages/temper-placer/src/temper_placer/heuristics`
- `packages/temper-placer/tests/core` -> `packages/temper-placer/src/temper_placer/io`
- `packages/temper-placer/tests/core` -> `packages/temper-placer/src/temper_placer/losses`
- `packages/temper-placer/tests/core` -> `packages/temper-placer/src/temper_placer/optimizer`
- `packages/temper-placer/tests/deterministic/stages` -> `packages/temper-placer/src/temper_placer/core`
- `packages/temper-placer/tests/deterministic/stages` -> `packages/temper-placer/src/temper_placer/deterministic/geometry`
- `packages/temper-placer/tests/deterministic/stages` -> `packages/temper-placer/src/temper_placer/deterministic/stages`
- `packages/temper-placer/tests/deterministic/stages` -> `packages/temper-placer/src/temper_placer/deterministic`
- `packages/temper-placer/tests/deterministic/stages` -> `packages/temper-placer/src/temper_placer/io`
- `packages/temper-placer/tests/deterministic/stages` -> `packages/temper-placer/src/temper_placer/router_v6`
- `packages/temper-placer/tests/deterministic/stages` -> `tests/deterministic`
- `packages/temper-placer/tests/deterministic` -> `packages/temper-placer/src/temper_placer/core`
- `packages/temper-placer/tests/deterministic` -> `packages/temper-placer/src/temper_placer/deterministic/feedback`
- `packages/temper-placer/tests/deterministic` -> `packages/temper-placer/src/temper_placer/deterministic/stages`
- `packages/temper-placer/tests/deterministic` -> `packages/temper-placer/src/temper_placer/deterministic`
- `packages/temper-placer/tests/deterministic` -> `packages/temper-placer/src/temper_placer/io`
- `packages/temper-placer/tests/deterministic` -> `packages/temper-placer/src/temper_placer/router_v6`
- `packages/temper-placer/tests/explainability` -> `packages/temper-placer/src/temper_placer/core`
- `packages/temper-placer/tests/explainability` -> `packages/temper-placer/src/temper_placer/explainability`
- `packages/temper-placer/tests/fixtures/generators` -> `packages/temper-placer/src/temper_placer/core`
- `packages/temper-placer/tests/fixtures` -> `packages/temper-placer/src/temper_placer/fixtures`
- `packages/temper-placer/tests/geometry` -> `packages/temper-placer/src/temper_placer/geometry`
- `packages/temper-placer/tests/heuristics` -> `packages/temper-placer/src/temper_placer/core`
- `packages/temper-placer/tests/heuristics` -> `packages/temper-placer/src/temper_placer/heuristics`
- `packages/temper-placer/tests/heuristics` -> `packages/temper-placer/src/temper_placer/io`
- `packages/temper-placer/tests/integration` -> `packages/temper-placer/src/temper_placer/constraints`
- `packages/temper-placer/tests/integration` -> `packages/temper-placer/src/temper_placer/core`
- `packages/temper-placer/tests/integration` -> `packages/temper-placer/src/temper_placer/deterministic/stages`
- `packages/temper-placer/tests/integration` -> `packages/temper-placer/src/temper_placer/deterministic`
- `packages/temper-placer/tests/integration` -> `packages/temper-placer/src/temper_placer/io`
- `packages/temper-placer/tests/integration` -> `packages/temper-placer/src/temper_placer/losses`
- `packages/temper-placer/tests/integration` -> `packages/temper-placer/src/temper_placer/optimizer`
- `packages/temper-placer/tests/integration` -> `packages/temper-placer/src/temper_placer/router_v6`
- `packages/temper-placer/tests/integration` -> `packages/temper-placer/tests/fixtures/external`
- `packages/temper-placer/tests/integration` -> `tests/integration`
- `packages/temper-placer/tests/invariants` -> `packages/temper-placer/src/temper_placer/core`
- `packages/temper-placer/tests/io` -> `packages/temper-placer/src/temper_placer/core`
- `packages/temper-placer/tests/io` -> `packages/temper-placer/src/temper_placer/deterministic/stages`
- `packages/temper-placer/tests/io` -> `packages/temper-placer/src/temper_placer/io`
- `packages/temper-placer/tests/io` -> `packages/temper-placer/src/temper_placer/losses`
- `packages/temper-placer/tests/io` -> `packages/temper-placer/src/temper_placer/router_v6`
- `packages/temper-placer/tests/losses` -> `packages/temper-placer/src/temper_placer/core`
- `packages/temper-placer/tests/losses` -> `packages/temper-placer/src/temper_placer/extraction`
- `packages/temper-placer/tests/losses` -> `packages/temper-placer/src/temper_placer/losses/physics`
- `packages/temper-placer/tests/losses` -> `packages/temper-placer/src/temper_placer/losses`
- `packages/temper-placer/tests/losses` -> `packages/temper-placer/src/temper_placer/validation`
- `packages/temper-placer/tests/manufacturing` -> `packages/temper-placer/src/temper_placer/core`
- `packages/temper-placer/tests/manufacturing` -> `packages/temper-placer/src/temper_placer/manufacturing`
- `packages/temper-placer/tests/measurements` -> `packages/temper-placer/src/temper_placer/io`
- `packages/temper-placer/tests/measurements` -> `packages/temper-placer/src/temper_placer/losses`
- `packages/temper-placer/tests/measurements` -> `packages/temper-placer/src/temper_placer/optimizer`
- `packages/temper-placer/tests/metrics` -> `packages/temper-placer/src/temper_placer/core`
- `packages/temper-placer/tests/metrics` -> `packages/temper-placer/src/temper_placer/metrics`
- `packages/temper-placer/tests/metrics` -> `packages/temper-placer/src/temper_placer/validation`
- `packages/temper-placer/tests/ml` -> `packages/temper-placer/src/temper_placer/ml`
- `packages/temper-placer/tests/optimizer` -> `packages/temper-placer/src/temper_placer/core`
- `packages/temper-placer/tests/optimizer` -> `packages/temper-placer/src/temper_placer/geometry`
- `packages/temper-placer/tests/optimizer` -> `packages/temper-placer/src/temper_placer/heuristics`
- `packages/temper-placer/tests/optimizer` -> `packages/temper-placer/src/temper_placer/io`
- `packages/temper-placer/tests/optimizer` -> `packages/temper-placer/src/temper_placer/losses`
- `packages/temper-placer/tests/optimizer` -> `packages/temper-placer/src/temper_placer/optimizer`
- `packages/temper-placer/tests/optimizer` -> `packages/temper-placer/src/temper_placer/pcl`
- `packages/temper-placer/tests/optimizer` -> `packages/temper-placer/src/temper_placer/placement`
- `packages/temper-placer/tests/parity` -> `packages/temper-placer/src/temper_placer/core`
- `packages/temper-placer/tests/parity` -> `packages/temper-placer/src/temper_placer/deterministic/stages`
- `packages/temper-placer/tests/parity` -> `packages/temper-placer/src/temper_placer/deterministic`
- `packages/temper-placer/tests/parity` -> `packages/temper-placer/src/temper_placer/io`
- `packages/temper-placer/tests/pcl` -> `packages/temper-placer/src/temper_placer/core`
- `packages/temper-placer/tests/pcl` -> `packages/temper-placer/src/temper_placer/losses`
- `packages/temper-placer/tests/pcl` -> `packages/temper-placer/src/temper_placer/pcl`
- `packages/temper-placer/tests/physics` -> `packages/temper-placer/src/temper_placer/physics`
- `packages/temper-placer/tests/pipeline/stages` -> `packages/temper-placer/src/temper_placer/core`
- `packages/temper-placer/tests/pipeline/stages` -> `packages/temper-placer/src/temper_placer/io`
- `packages/temper-placer/tests/pipeline/stages` -> `packages/temper-placer/src/temper_placer/pipeline`
- `packages/temper-placer/tests/pipeline` -> `packages/temper-placer/src/temper_placer/core`
- `packages/temper-placer/tests/pipeline` -> `packages/temper-placer/src/temper_placer/deterministic/stages`
- `packages/temper-placer/tests/pipeline` -> `packages/temper-placer/src/temper_placer/deterministic`
- `packages/temper-placer/tests/pipeline` -> `packages/temper-placer/src/temper_placer/pcl`
- `packages/temper-placer/tests/pipeline` -> `packages/temper-placer/src/temper_placer/pipeline`
- `packages/temper-placer/tests/placement` -> `packages/temper-placer/src/temper_placer/core`
- `packages/temper-placer/tests/placement` -> `packages/temper-placer/src/temper_placer/placement`
- `packages/temper-placer/tests/placement` -> `packages/temper-placer/src/temper_placer/router_v6`
- `packages/temper-placer/tests/placer` -> `packages/temper-placer/src/temper_placer/core`
- `packages/temper-placer/tests/placer` -> `packages/temper-placer/src/temper_placer/placer`
- `packages/temper-placer/tests/placer` -> `packages/temper-placer/src/temper_placer/router_v6`
- `packages/temper-placer/tests/profiling` -> `packages/temper-placer/src/temper_placer/cli`
- `packages/temper-placer/tests/profiling` -> `packages/temper-placer/src/temper_placer/profiling`
- `packages/temper-placer/tests/property` -> `packages/temper-placer/src/temper_placer/core`
- `packages/temper-placer/tests/property` -> `packages/temper-placer/src/temper_placer/deterministic/stages`
- `packages/temper-placer/tests/property` -> `packages/temper-placer/src/temper_placer/io`
- `packages/temper-placer/tests/protocol` -> `packages/temper-placer/src/temper_placer/deterministic/stages`
- `packages/temper-placer/tests/protocol` -> `packages/temper-placer/src/temper_placer/deterministic`
- `packages/temper-placer/tests/protocol` -> `packages/temper-placer/src/temper_placer`
- `packages/temper-placer/tests/regression` -> `packages/temper-placer/src/temper_placer/core`
- `packages/temper-placer/tests/regression` -> `packages/temper-placer/src/temper_placer/losses`
- `packages/temper-placer/tests/regression` -> `packages/temper-placer/src/temper_placer/metrics`
- `packages/temper-placer/tests/regression` -> `packages/temper-placer/src/temper_placer/regression`
- `packages/temper-placer/tests/regression` -> `packages/temper-placer/src/temper_placer/router_v6`
- `packages/temper-placer/tests/requirements/dfm` -> `packages/temper-placer/tests/requirements/validators`
- `packages/temper-placer/tests/requirements/review` -> `packages/temper-placer/tests/requirements/validators`
- `packages/temper-placer/tests/requirements/safety` -> `packages/temper-placer/tests/requirements/validators`
- `packages/temper-placer/tests/robustness` -> `packages/temper-placer/src/temper_placer/core`
- `packages/temper-placer/tests/robustness` -> `packages/temper-placer/src/temper_placer/geometry`
- `packages/temper-placer/tests/robustness` -> `packages/temper-placer/src/temper_placer/io`
- `packages/temper-placer/tests/robustness` -> `packages/temper-placer/src/temper_placer/losses`
- `packages/temper-placer/tests/robustness` -> `packages/temper-placer/src/temper_placer/optimizer`
- `packages/temper-placer/tests/router_v6` -> `packages/temper-placer/src/temper_placer/core`
- `packages/temper-placer/tests/router_v6` -> `packages/temper-placer/src/temper_placer/deterministic/stages`
- `packages/temper-placer/tests/router_v6` -> `packages/temper-placer/src/temper_placer/deterministic`
- `packages/temper-placer/tests/router_v6` -> `packages/temper-placer/src/temper_placer/io`
- `packages/temper-placer/tests/router_v6` -> `packages/temper-placer/src/temper_placer/losses`
- `packages/temper-placer/tests/router_v6` -> `packages/temper-placer/src/temper_placer/router_v6`
- `packages/temper-placer/tests/router_v6` -> `tests/router_v6`
- `packages/temper-placer/tests/scale` -> `packages/temper-placer/src/temper_placer/core`
- `packages/temper-placer/tests/scale` -> `packages/temper-placer/src/temper_placer/fixtures`
- `packages/temper-placer/tests/scale` -> `packages/temper-placer/src/temper_placer/losses`
- `packages/temper-placer/tests/scale` -> `packages/temper-placer/src/temper_placer/optimizer`
- `packages/temper-placer/tests/scale` -> `packages/temper-placer/src/temper_placer/scale`
- `packages/temper-placer/tests/scale` -> `packages/temper-placer/tests/fixtures/generators`
- `packages/temper-placer/tests/sensitivity` -> `packages/temper-placer/src/temper_placer/core`
- `packages/temper-placer/tests/sensitivity` -> `packages/temper-placer/src/temper_placer/geometry`
- `packages/temper-placer/tests/sensitivity` -> `packages/temper-placer/src/temper_placer/heuristics`
- `packages/temper-placer/tests/sensitivity` -> `packages/temper-placer/src/temper_placer/io`
- `packages/temper-placer/tests/sensitivity` -> `packages/temper-placer/src/temper_placer/losses`
- `packages/temper-placer/tests/sensitivity` -> `packages/temper-placer/src/temper_placer/optimizer`
- `packages/temper-placer/tests/templates` -> `packages/temper-placer/src/temper_placer/core`
- `packages/temper-placer/tests/templates` -> `packages/temper-placer/src/temper_placer/templates`
- `packages/temper-placer/tests/testing` -> `packages/temper-placer/src/temper_placer/core`
- `packages/temper-placer/tests/testing` -> `packages/temper-placer/src/temper_placer/deterministic`
- `packages/temper-placer/tests/testing` -> `packages/temper-placer/src/temper_placer/io`
- `packages/temper-placer/tests/testing` -> `packages/temper-placer/src/temper_placer/testing`
- `packages/temper-placer/tests/topological` -> `packages/temper-placer/src/temper_placer/core`
- `packages/temper-placer/tests/topological` -> `packages/temper-placer/src/temper_placer/heuristics`
- `packages/temper-placer/tests/topological` -> `packages/temper-placer/src/temper_placer/io`
- `packages/temper-placer/tests/topological` -> `packages/temper-placer/src/temper_placer/pcl`
- `packages/temper-placer/tests/topological` -> `packages/temper-placer/src/temper_placer/topological`
- `packages/temper-placer/tests/unit` -> `packages/temper-placer/src/temper_placer/core`
- `packages/temper-placer/tests/unit` -> `packages/temper-placer/src/temper_placer/geometry`
- `packages/temper-placer/tests/unit` -> `packages/temper-placer/src/temper_placer/io`
- `packages/temper-placer/tests/unit` -> `packages/temper-placer/src/temper_placer/optimizer`
- `packages/temper-placer/tests/validation` -> `packages/temper-placer/src/temper_placer/core`
- `packages/temper-placer/tests/validation` -> `packages/temper-placer/src/temper_placer/io`
- `packages/temper-placer/tests/validation` -> `packages/temper-placer/src/temper_placer/losses`
- `packages/temper-placer/tests/validation` -> `packages/temper-placer/src/temper_placer/optimizer`
- `packages/temper-placer/tests/validation` -> `packages/temper-placer/src/temper_placer/validation`
- `packages/temper-placer/tests/verification` -> `packages/temper-placer/src/temper_placer/core`
- `packages/temper-placer/tests/verification` -> `packages/temper-placer/src/temper_placer/geometry`
- `packages/temper-placer/tests/verification` -> `packages/temper-placer/src/temper_placer/io`
- `packages/temper-placer/tests/verification` -> `packages/temper-placer/src/temper_placer/losses`
- `packages/temper-placer/tests/verification` -> `packages/temper-placer/src/temper_placer/optimizer`
- `packages/temper-placer/tests/verification` -> `packages/temper-placer/src/temper_placer/validation`
- `packages/temper-placer/tests/visualization` -> `packages/temper-placer/src/temper_placer/core`
- `packages/temper-placer/tests/visualization` -> `packages/temper-placer/src/temper_placer/visualization`
- `packages/temper-placer/tests` -> `packages/temper-placer/src/temper_placer/cli`
- `packages/temper-placer/tests` -> `packages/temper-placer/src/temper_placer/core`
- `packages/temper-placer/tests` -> `packages/temper-placer/src/temper_placer/deterministic/stages`
- `packages/temper-placer/tests` -> `packages/temper-placer/src/temper_placer/deterministic`
- `packages/temper-placer/tests` -> `packages/temper-placer/src/temper_placer/io`
- `packages/temper-placer/tests` -> `packages/temper-placer/src/temper_placer/losses`
- `packages/temper-placer/tests` -> `packages/temper-placer/src/temper_placer/optimizer`
- `packages/temper-placer/tests` -> `packages/temper-placer/src/temper_placer/pipeline`
- `packages/temper-placer/tests` -> `packages/temper-placer/src/temper_placer/profiling`
- `packages/temper-placer/tests` -> `packages/temper-placer

---
*[Truncated in: Dependency Rules]*
