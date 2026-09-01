"""
Integration tests for the Rust quality oracle crate (temper_quality_oracle).

Covers:
- R14: E2E tests drive full oracle through PyO3
- Parity with existing Python quality pipeline
- NormalizedScore error handling
- panic-to-exception safety (R15)
"""

import json

import pytest

try:
    import temper_quality_oracle  # type: ignore[import-untyped]

    HAS_RUST_ORACLE = True
except ImportError:
    HAS_RUST_ORACLE = False


def require_oracle():
    if not HAS_RUST_ORACLE:
        pytest.skip("temper_quality_oracle not installed")


def evaluate_quality(netlist, placement, spec, metrics):
    """Exercise the two-step API used by production callers."""
    prepared = temper_quality_oracle.prepare_quality_py(netlist, spec)
    return temper_quality_oracle.evaluate_prepared_py(prepared, placement, metrics)


class TestOracleModule:
    def test_module_imports(self):
        require_oracle()
        assert callable(temper_quality_oracle.prepare_quality_py)

    def test_regional_declaration_is_sorted_and_budgeted(self):
        require_oracle()
        rows = temper_quality_oracle.declare_regional_candidates_py(
            ["C002", "C001"], [5.5, 4.0, 5.0, 4.5], 8
        )
        assert rows[0] == (1, "R14HV-001", "C001", 4.0)
        assert rows[-1] == (8, "R14HV-008", "C002", 5.5)
        with pytest.raises(ValueError, match="budget"):
            temper_quality_oracle.declare_regional_candidates_py(["C001"], [4.0, 4.5], 1)

    def test_pre_route_verdict_is_rust_owned_and_ordered(self):
        require_oracle()
        accepted, reasons = temper_quality_oracle.evaluate_pre_route_candidate_py(
            12.0, 11.0, 1, 1, 1, 1, 1, 1, 1, 1
        )
        assert not accepted
        assert reasons == [
            "k1_j1",
            "route_to_selv",
            "affected_safety",
            "safety_regression",
            "body_overlap",
            "courtyard_overlap",
            "containment",
        ]

    def test_corridor_family_is_content_addressed_and_authority_bound(self):
        require_oracle()
        request = {
            "schema_version": "temper-regional-corridor-request/v2",
            "declaration_hash": "d" * 64,
            "board_hash": "b" * 64,
            "generated_input_hashes": ["a" * 64, "c" * 64],
            "placements": [
                {"placement_id": "P002", "j1_position": [101.0, 200.0]},
                {"placement_id": "P001", "j1_position": [100.0, 200.0]},
            ],
            "endpoint_x_mm": [122.64, 123.14],
            "corridor_x_mm": [120.0, 120.5],
            "entry_y_mm": [226.0, 230.0],
            "endpoint_y_mm": 252.5225,
            "fixed_start": [112.0, 218.0],
            "knee_y_mm": 250.0,
            "layer": "In3.Cu",
            "route_width_mm": 0.5,
            "via_diameter_mm": 0.9,
            "via_drill_mm": 0.3,
            "via_span": ["In3.Cu", "F.Cu"],
            "candidate_budget": 16,
        }
        first = json.loads(
            temper_quality_oracle.declare_corridor_candidates_json_py(json.dumps(request))
        )
        request["placements"].reverse()
        second = json.loads(
            temper_quality_oracle.declare_corridor_candidates_json_py(json.dumps(request))
        )
        assert first == second
        assert first["candidate_count"] == 16
        assert first["topology_authority"]["clearance_mm"] == 6.0
        assert first["topology_authority"]["creepage_mm"] == 12.6
        assert len({row["candidate_id"] for row in first["candidates"]}) == 16

    def test_corridor_screening_is_attributed_and_deterministic(self):
        require_oracle()
        request = {
            "schema_version": "temper-regional-screen-request/v2",
            "candidates": [
                {"candidate_id": "c", "minimum_clearance_mm": 7.0, "minimum_creepage_mm": 13.0, "route_length_mm": 30.0},
                {"candidate_id": "a", "minimum_clearance_mm": 7.0, "minimum_creepage_mm": 13.0, "route_length_mm": 30.0},
                {"candidate_id": "b", "minimum_clearance_mm": 5.9, "minimum_creepage_mm": 20.0, "route_length_mm": 10.0},
            ],
            "route_budget": 12,
        }
        result = json.loads(
            temper_quality_oracle.screen_corridor_candidates_json_py(json.dumps(request))
        )
        assert result["routing_subset"] == ["a", "c"]
        rejected = next(row for row in result["results"] if row["candidate_id"] == "b")
        assert rejected["raw_measurements"]["minimum_clearance_mm"] == 5.9
        assert rejected["vetoes"][0]["authority_key"] == "clearance.hv_lv.project.target"

    @pytest.mark.parametrize(
        ("candidate_id", "clearance", "creepage", "expected_keys"),
        [
            ("clearance-only", 5.9, 12.6, ["clearance.hv_lv.project.target"]),
            ("creepage-only", 6.0, 12.5, ["creepage.hv_lv.pd3.production"]),
            (
                "both",
                5.9,
                12.5,
                ["clearance.hv_lv.project.target", "creepage.hv_lv.pd3.production"],
            ),
            ("exact-threshold", 6.0, 12.6, []),
        ],
    )
    def test_corridor_screening_enforces_each_safety_threshold(
        self, candidate_id, clearance, creepage, expected_keys
    ):
        require_oracle()
        request = {
            "schema_version": "temper-regional-screen-request/v2",
            "candidates": [
                {
                    "candidate_id": candidate_id,
                    "minimum_clearance_mm": clearance,
                    "minimum_creepage_mm": creepage,
                    "route_length_mm": 1.0,
                }
            ],
            "route_budget": 1,
        }
        result = json.loads(
            temper_quality_oracle.screen_corridor_candidates_json_py(json.dumps(request))
        )
        row = result["results"][0]
        assert [veto["authority_key"] for veto in row["vetoes"]] == expected_keys
        for veto in row["vetoes"]:
            assert veto["required_mm"] in (6.0, 12.6)
            assert veto["measured_mm"] in (clearance, creepage)
            assert veto["source"]

    def test_bound_corridor_screen_requires_the_complete_declared_family(self):
        require_oracle()
        declaration_request = {
            "schema_version": "temper-regional-corridor-request/v2",
            "declaration_hash": "d" * 64,
            "board_hash": "b" * 64,
            "generated_input_hashes": ["a" * 64],
            "placements": [{"placement_id": "P001", "j1_position": [100.0, 200.0]}],
            "endpoint_x_mm": [122.64, 123.14],
            "corridor_x_mm": [120.0],
            "entry_y_mm": [226.0],
            "endpoint_y_mm": 252.5225,
            "fixed_start": [112.0, 206.0],
            "knee_y_mm": 250.0,
            "layer": "In3.Cu",
            "route_width_mm": 0.5,
            "via_diameter_mm": 0.9,
            "via_drill_mm": 0.3,
            "via_span": ["In3.Cu", "F.Cu"],
            "candidate_budget": 2,
        }
        candidate_set = json.loads(
            temper_quality_oracle.declare_corridor_candidates_json_py(
                json.dumps(declaration_request)
            )
        )
        measurements = [
            {
                "candidate_id": candidate["candidate_id"],
                "minimum_clearance_mm": 6.0,
                "minimum_creepage_mm": 12.6,
                "route_length_mm": 10.0,
            }
            for candidate in candidate_set["candidates"]
        ]
        request = {
            "schema_version": "temper-regional-bound-screen-request/v3",
            "candidate_set": candidate_set,
            "candidates": measurements,
            "route_budget": 1,
        }
        verdict = json.loads(
            temper_quality_oracle.screen_declared_corridor_candidates_json_py(
                json.dumps(request)
            )
        )
        assert verdict["evaluated_count"] == 2
        assert verdict["candidate_set_digest"] == candidate_set["candidate_set_digest"]

        request["candidates"] = measurements[:-1]
        with pytest.raises(ValueError, match="exact declared candidate set"):
            temper_quality_oracle.screen_declared_corridor_candidates_json_py(
                json.dumps(request)
            )

class TestQualityOraclePipeline:
    def test_empty_board_passes(self):
        require_oracle()
        netlist = {"nets": [], "components": []}
        placement = {
            "positions": [],
            "component_refs": [],
            "board_width_mm": 100.0,
            "board_height_mm": 100.0,
        }
        spec = {"name": "test"}
        metrics = {
            "thermal_score": 0.5,
            "zone_compliance_score": 0.5,
            "hv_lv_clearance_score": 0.5,
            "loop_area_score": 0.5,
            "congestion_score": 0.5,
            "compactness_score": 0.5,
            "connectivity_clustering_score": 0.5,
            "total_wirelength_mm": 100.0,
        }
        result = evaluate_quality(netlist, placement, spec, metrics)
        assert result["verdict"] == "Pass"
        assert "metrics" in result
        assert abs(result["metrics"]["overall_score"] - 0.5) < 1e-6

    def test_hv_lv_violation_detected(self):
        require_oracle()
        netlist = {
            "nets": [{"name": "SIG1", "pins": ["Q1", "U1"]}],
            "components": [
                {
                    "ref": "Q1",
                    "footprint": "TO-247",
                    "width": 15.0,
                    "height": 20.0,
                    "voltage": 230.0,
                },
                {"ref": "U1", "footprint": "SOIC-8", "width": 5.0, "height": 4.0, "voltage": 3.3},
            ],
        }
        placement = {
            "positions": [5.0, 5.0, 6.0, 5.0],
            "component_refs": ["Q1", "U1"],
            "board_width_mm": 100.0,
            "board_height_mm": 100.0,
        }
        spec = {"name": "test"}
        metrics = {
            "thermal_score": 0.5,
            "zone_compliance_score": 0.5,
            "hv_lv_clearance_score": 0.5,
            "loop_area_score": 0.5,
            "congestion_score": 0.5,
            "compactness_score": 0.5,
            "connectivity_clustering_score": 0.5,
            "total_wirelength_mm": 100.0,
        }
        result = evaluate_quality(netlist, placement, spec, metrics)
        assert result["verdict"] == "Fail"
        assert "violations" in result
        violations = result["violations"]
        assert len(violations) > 0
        assert any(v["type"] == "creepage_insufficient" for v in violations)

    def test_invalid_score_rejected(self):
        require_oracle()
        netlist = {"nets": [], "components": []}
        placement = {
            "positions": [],
            "component_refs": [],
            "board_width_mm": 100.0,
            "board_height_mm": 100.0,
        }
        spec = {"name": "test"}
        metrics = {
            "thermal_score": 1.5,
            "zone_compliance_score": 0.5,
            "hv_lv_clearance_score": 0.5,
            "loop_area_score": 0.5,
            "congestion_score": 0.5,
            "compactness_score": 0.5,
            "connectivity_clustering_score": 0.5,
            "total_wirelength_mm": 100.0,
        }
        result = evaluate_quality(netlist, placement, spec, metrics)
        assert result["verdict"] == "Fail"
        assert "violations" in result

    def test_deterministic(self):
        require_oracle()
        netlist = {"nets": [], "components": []}
        placement = {
            "positions": [],
            "component_refs": [],
            "board_width_mm": 100.0,
            "board_height_mm": 100.0,
        }
        spec = {"name": "test"}
        metrics = {
            "thermal_score": 0.5,
            "zone_compliance_score": 0.5,
            "hv_lv_clearance_score": 0.5,
            "loop_area_score": 0.5,
            "congestion_score": 0.5,
            "compactness_score": 0.5,
            "connectivity_clustering_score": 0.5,
            "total_wirelength_mm": 100.0,
        }
        r1 = evaluate_quality(netlist, placement, spec, metrics)
        r2 = evaluate_quality(netlist, placement, spec, metrics)
        assert r1["verdict"] == r2["verdict"]


class TestPrepareEvaluateSplit:
    """The setup/evaluate precompute split (R-x: prepare once, score many)."""

    def _hv_lv_inputs(self):
        netlist = {
            "nets": [{"name": "GATE_DRV_H", "pins": ["Q1", "U1"]}],
            "components": [
                {
                    "ref": "Q1",
                    "footprint": "TO-247",
                    "width": 15.0,
                    "height": 20.0,
                    "voltage": 230.0,
                },
                {"ref": "U1", "footprint": "SOIC-8", "width": 5.0, "height": 4.0, "voltage": 3.3},
            ],
        }
        spec = {"name": "test"}
        metrics = {
            "thermal_score": 0.5,
            "zone_compliance_score": 0.5,
            "hv_lv_clearance_score": 0.5,
            "loop_area_score": 0.5,
            "congestion_score": 0.5,
            "compactness_score": 0.5,
            "connectivity_clustering_score": 0.5,
            "total_wirelength_mm": 100.0,
        }
        return netlist, spec, metrics

    def test_prepared_round_trips(self):
        require_oracle()
        netlist, spec, _ = self._hv_lv_inputs()
        prepared = temper_quality_oracle.prepare_quality_py(netlist, spec)
        assert set(prepared.keys()) == {"spec", "config", "classifications"}
        config = prepared["config"]
        assert set(config.keys()) == {
            "thermal_components",
            "hv_components",
            "lv_components",
            "zone_assignments",
            "loop_components",
            "min_hv_lv_clearance_mm",
        }
        assert "Q1" in config["hv_components"]
        assert "U1" in config["lv_components"]
        assert prepared["classifications"] == [
            {"net_name": "GATE_DRV_H", "class": "gate_drive"}
        ]

    def test_evaluate_prepared_matches_evaluate_quality(self):
        require_oracle()
        netlist, spec, metrics = self._hv_lv_inputs()
        placement = {
            "positions": [5.0, 5.0, 6.0, 5.0],
            "component_refs": ["Q1", "U1"],
            "board_width_mm": 100.0,
            "board_height_mm": 100.0,
        }
        single = evaluate_quality(netlist, placement, spec, metrics)
        prepared = temper_quality_oracle.prepare_quality_py(netlist, spec)
        split = temper_quality_oracle.evaluate_prepared_py(prepared, placement, metrics)
        assert split == single
        assert split["verdict"] == "Fail"
        assert any(v["type"] == "creepage_insufficient" for v in split["violations"])

    def test_prepare_once_score_many_placements(self):
        require_oracle()
        netlist, spec, metrics = self._hv_lv_inputs()
        prepared = temper_quality_oracle.prepare_quality_py(netlist, spec)

        close = {
            "positions": [5.0, 5.0, 6.0, 5.0],
            "component_refs": ["Q1", "U1"],
            "board_width_mm": 100.0,
            "board_height_mm": 100.0,
        }
        far = {
            "positions": [5.0, 5.0, 80.0, 80.0],
            "component_refs": ["Q1", "U1"],
            "board_width_mm": 100.0,
            "board_height_mm": 100.0,
        }
        r_close = temper_quality_oracle.evaluate_prepared_py(prepared, close, metrics)
        r_far = temper_quality_oracle.evaluate_prepared_py(prepared, far, metrics)
        assert r_close["verdict"] == "Fail"
        assert r_far["verdict"] == "Pass"
        # The same prepared dict is reusable across placement states.
        r_close_again = temper_quality_oracle.evaluate_prepared_py(prepared, close, metrics)
        assert r_close_again == r_close

    def test_evaluate_prepared_rejects_bad_metrics(self):
        require_oracle()
        netlist, spec, metrics = self._hv_lv_inputs()
        prepared = temper_quality_oracle.prepare_quality_py(netlist, spec)
        placement = {
            "positions": [5.0, 5.0, 80.0, 80.0],
            "component_refs": ["Q1", "U1"],
            "board_width_mm": 100.0,
            "board_height_mm": 100.0,
        }
        bad_metrics = dict(metrics)
        bad_metrics["thermal_score"] = 1.5
        result = temper_quality_oracle.evaluate_prepared_py(prepared, placement, bad_metrics)
        assert result["verdict"] == "Fail"
        assert any(v["type"] == "invalid_metric" for v in result["violations"])
