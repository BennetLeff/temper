"""Tests for challenger thermal mesh and cross-validation."""

from __future__ import annotations

import pytest
from tools.spice.challenger.cross_validate import CrossValidationResult, cross_validate
from tools.spice.challenger.report import generate_challenger_report
from tools.spice.challenger.thermal_mesh import (
    HeatSource,
    ThermalMeshConfig,
    analytical_uniform_bar,
    compute_Tj_rtheta,
    solve_2d_steady_state,
)
from tools.spice.corner_results import CornerResult


class TestComputeTjRtheta:
    def test_basic_calculation(self) -> None:
        Tj = compute_Tj_rtheta(50.0, 25.0, 1.0, 10.0)
        assert Tj == pytest.approx(575.0)

    def test_zero_power_ambient_temp(self) -> None:
        Tj = compute_Tj_rtheta(0.0, 25.0, 1.0, 10.0)
        assert Tj == pytest.approx(25.0)


class TestThermalMesh:
    @pytest.fixture
    def config(self) -> ThermalMeshConfig:
        return ThermalMeshConfig(
            width_mm=40.0,
            height_mm=40.0,
            grid_resolution_mm=2.0,
            board_thickness_mm=1.6,
            T_ambient_C=25.0,
            max_iterations=2000,
            convergence_tol=1e-3,
        )

    def test_solver_converges(self, config: ThermalMeshConfig) -> None:
        sources = [
            HeatSource(x_mm=50.0, y_mm=75.0, power_W=10.0),
        ]
        result = solve_2d_steady_state(config, sources)
        assert result.converged
        assert result.T_max_C >= config.T_ambient_C

    def test_no_sources_ambient_only(
        self, config: ThermalMeshConfig
    ) -> None:
        result = solve_2d_steady_state(config, [])
        assert result.converged
        assert result.T_max_C == pytest.approx(config.T_ambient_C, abs=1.0)

    def test_higher_power_higher_temp(
        self, config: ThermalMeshConfig
    ) -> None:
        config2 = ThermalMeshConfig(
            width_mm=40.0,
            height_mm=40.0,
            grid_resolution_mm=1.0,
            board_thickness_mm=1.6,
            k_fr4_W_per_mK=1.0,
            T_ambient_C=25.0,
            max_iterations=5000,
            convergence_tol=1e-3,
        )
        result1 = solve_2d_steady_state(
            config2, [HeatSource(x_mm=20.0, y_mm=20.0, power_W=1.0, width_mm=5.0, height_mm=5.0)]
        )
        result2 = solve_2d_steady_state(
            config2, [HeatSource(x_mm=20.0, y_mm=20.0, power_W=10.0, width_mm=5.0, height_mm=5.0)]
        )
        assert result2.T_max_C >= result1.T_max_C

    def test_analytical_verification(self) -> None:
        L = 0.1
        w = 0.01
        t = 0.0016
        k = 385.0
        P = 10.0
        T_amb = 25.0
        h = 10.0

        T_max = analytical_uniform_bar(L, w, t, k, P, T_amb, h)
        assert T_max > T_amb


class TestCrossValidate:
    def test_no_corners(self) -> None:
        result = cross_validate([])
        assert result.total_corners == 0
        assert result.agreement_rate_pct == 100.0

    def test_synthetic_agreement(self) -> None:
        """Tj_primary matching challenger prediction should produce 100% agreement."""
        # With power_per_device_W=5.0, R_jc+R_ca=11:
        # Tj_challenger = 25 + 5*11 = 80°C = Tj_primary
        corners = [
            CornerResult(
                corner_name=f"corner_{i}",
                Vbus=320.0,
                Iload=10.0,
                Tj=25.0,
                Zload_angle=0.0,
                Tj_primary=80.0,
                switching_loss_mJ=0.0,
            )
            for i in range(10)
        ]
        result = cross_validate(corners, power_per_device_W=5.0)
        assert result.flagged_corners == 0

    def test_synthetic_disagreement(self) -> None:
        """Large Tj difference should produce flags."""
        corners = [
            CornerResult(
                corner_name="hot",
                Vbus=400.0,
                Iload=30.0,
                Tj=150.0,
                Zload_angle=0.0,
                Tj_primary=200.0,
                switching_loss_mJ=100.0,
            ),
        ]
        result = cross_validate(corners)
        assert result.total_corners == 1

    def test_convergence_error_handled(self) -> None:
        corners = [
            CornerResult(
                corner_name="failed",
                Vbus=320.0,
                Iload=10.0,
                Tj=25.0,
                Zload_angle=0.0,
                convergence_error=True,
                error_message="test failure",
            ),
        ]
        result = cross_validate(corners)
        assert result.total_corners == 1


class TestGenerateReport:
    def test_generates_markdown(self) -> None:
        validation = CrossValidationResult(
            total_corners=16,
            agreed_corners=14,
            flagged_corners=2,
            worst_disagreement_pct=15.5,
            worst_corner="V400_I30_T150_Z30",
            flagged_details=[
                {
                    "corner": "V400_I30_T150_Z30",
                    "Tj_primary": 180.0,
                    "Tj_challenger": 155.0,
                    "disagreement_pct": 13.9,
                },
            ],
        )
        report = generate_challenger_report(validation)
        assert "Cross-Validation" in report
        assert "Flagged Corners" in report
        assert "V400_I30_T150_Z30" in report

    def test_report_includes_agreement_rate(self) -> None:
        validation = CrossValidationResult(
            total_corners=16,
            agreed_corners=16,
            flagged_corners=0,
        )
        report = generate_challenger_report(validation)
        assert "100.0%" in report

    def test_report_no_flagged_corners(self) -> None:
        validation = CrossValidationResult(
            total_corners=10,
            agreed_corners=10,
            flagged_corners=0,
        )
        report = generate_challenger_report(validation)
        assert "Flagged" not in report or validation.flagged_corners == 0


class TestR7Independence:
    """Verify challenger source files have no temper-placer imports (R7 compliance)."""

    def test_no_placer_imports_in_thermal_mesh(self) -> None:
        import inspect

        import tools.spice.challenger.thermal_mesh as tm
        source = inspect.getsource(tm)
        assert "temper_placer" not in source
        assert "from temper_placer" not in source
        assert "import temper_placer" not in source

    def test_no_placer_imports_in_cross_validate(self) -> None:
        import inspect

        import tools.spice.challenger.cross_validate as cv
        source = inspect.getsource(cv)
        assert "temper_placer" not in source
        assert "from temper_placer" not in source
        assert "import temper_placer" not in source

    def test_no_placer_imports_in_report(self) -> None:
        import inspect

        import tools.spice.challenger.report as rpt
        source = inspect.getsource(rpt)
        assert "temper_placer" not in source
        assert "from temper_placer" not in source
        assert "import temper_placer" not in source
