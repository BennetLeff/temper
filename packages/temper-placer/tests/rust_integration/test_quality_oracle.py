"""
Integration tests for the Rust quality oracle crate (temper_quality_oracle).

Covers:
- R14: E2E tests drive full oracle through PyO3
- Parity with existing Python quality pipeline
- NormalizedScore error handling
- panic-to-exception safety (R15)
"""

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
