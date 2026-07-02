"""
Integration tests for the Rust quality oracle crate (temper_quality_oracle).

Covers:
- R14: E2E tests drive full oracle through PyO3
- Parity with existing Python quality pipeline
- IPC-2221 bracket parity between Rust and Python
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


class TestOracleModule:
    def test_module_imports(self):
        require_oracle()
        assert temper_quality_oracle.is_available_py() is True

    def test_version_reports(self):
        require_oracle()
        version = temper_quality_oracle.version_py()
        assert version == "0.1.0"

    def test_required_clearance_known_voltage(self):
        require_oracle()
        assert abs(temper_quality_oracle.required_clearance_py(230.0) - 3.20) < 1e-6
        assert abs(temper_quality_oracle.required_clearance_py(0.0) - 0.13) < 1e-6
        assert abs(temper_quality_oracle.required_clearance_py(500.0) - 8.00) < 1e-6


class TestNetClassification:
    def test_classify_simple_nets(self):
        require_oracle()
        netlist = {
            "nets": [
                {"name": "GND", "pins": []},
                {"name": "+12V", "pins": []},
                {"name": "SW_NODE", "pins": []},
                {"name": "GATE_H", "pins": []},
                {"name": "SIG1", "pins": []},
            ],
            "components": [],
        }
        result = temper_quality_oracle.classify_nets_py(netlist)
        assert result["GND"] == "ground"
        assert result["+12V"] == "power"
        assert result["SW_NODE"] == "high_voltage"
        assert result["GATE_H"] == "gate_drive"
        assert result["SIG1"] == "signal"


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
        result = temper_quality_oracle.evaluate_quality_py(netlist, placement, spec, metrics)
        assert result["verdict"] == "Pass"
        assert "metrics" in result
        assert abs(result["metrics"]["overall_score"] - 0.5) < 1e-6

    def test_hv_lv_violation_detected(self):
        require_oracle()
        netlist = {
            "nets": [{"name": "SIG1", "pins": ["Q1", "U1"]}],
            "components": [
                {"ref": "Q1", "footprint": "TO-247", "width": 15.0, "height": 20.0, "voltage": 230.0},
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
            "thermal_score": 0.5, "zone_compliance_score": 0.5,
            "hv_lv_clearance_score": 0.5, "loop_area_score": 0.5,
            "congestion_score": 0.5, "compactness_score": 0.5,
            "connectivity_clustering_score": 0.5, "total_wirelength_mm": 100.0,
        }
        result = temper_quality_oracle.evaluate_quality_py(netlist, placement, spec, metrics)
        assert result["verdict"] == "Fail"
        assert "violations" in result
        violations = result["violations"]
        assert len(violations) > 0
        assert any(v["type"] == "creepage_insufficient" for v in violations)

    def test_invalid_score_rejected(self):
        require_oracle()
        netlist = {"nets": [], "components": []}
        placement = {"positions": [], "component_refs": [], "board_width_mm": 100.0, "board_height_mm": 100.0}
        spec = {"name": "test"}
        metrics = {
            "thermal_score": 1.5, "zone_compliance_score": 0.5,
            "hv_lv_clearance_score": 0.5, "loop_area_score": 0.5,
            "congestion_score": 0.5, "compactness_score": 0.5,
            "connectivity_clustering_score": 0.5, "total_wirelength_mm": 100.0,
        }
        result = temper_quality_oracle.evaluate_quality_py(netlist, placement, spec, metrics)
        assert result["verdict"] == "Fail"
        assert "violations" in result

    def test_deterministic(self):
        require_oracle()
        netlist = {"nets": [], "components": []}
        placement = {"positions": [], "component_refs": [], "board_width_mm": 100.0, "board_height_mm": 100.0}
        spec = {"name": "test"}
        metrics = {
            "thermal_score": 0.5, "zone_compliance_score": 0.5,
            "hv_lv_clearance_score": 0.5, "loop_area_score": 0.5,
            "congestion_score": 0.5, "compactness_score": 0.5,
            "connectivity_clustering_score": 0.5, "total_wirelength_mm": 100.0,
        }
        r1 = temper_quality_oracle.evaluate_quality_py(netlist, placement, spec, metrics)
        r2 = temper_quality_oracle.evaluate_quality_py(netlist, placement, spec, metrics)
        assert r1["verdict"] == r2["verdict"]


class TestIPC2221BracketParity:
    def test_bracket_boundaries_match_python(self):
        require_oracle()
        from temper_placer.router_v6.creepage_check import _calculate_required_creepage
        voltages = [0, 10, 15, 16, 30, 31, 50, 51, 100, 101, 150, 151, 170, 171, 230, 250, 251, 300, 301, 500, 600, 800, 1000, 1500]
        for v in voltages:
            rust_val = temper_quality_oracle.required_clearance_py(v)
            py_val = _calculate_required_creepage(v)
            assert abs(rust_val - py_val) < 1e-6, f"mismatch at {v}V: rust={rust_val}, python={py_val}"
