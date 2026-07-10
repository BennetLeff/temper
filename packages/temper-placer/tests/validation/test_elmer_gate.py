"""
Tests for Elmer corroboration gate (validation/elmer_gate.py).

Covers:
- Gate with absent Elmer → UNMEASURED (fail-closed).
- Gate with synthetic comparison where fields agree → CLEAN.
- Gate with synthetic fields that disagree → VIOLATIONS.
- Gate config validation.

Uses synthetic numpy fields — no real Elmer solve needed.
"""

import numpy as np
import pytest

from temper_placer.placer.cp_sat.gates import GateStatus
from temper_placer.validation.elmer_gate import (
    ElmerCorroborationGate,
    ElmerGateConfig,
)
from temper_placer.physics.thermal_fdm import ThermalFDMConfig
from temper_placer.physics.tj_cross_check import DeviceThermalConfig


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fdm_config() -> ThermalFDMConfig:
    return ThermalFDMConfig(
        cell_size_mm=0.5,
        origin_mm=(0.0, 0.0),
        height_cells=20,
        width_cells=30,
        ambient_C=40.0,
        heatsink_edge="TOP",
    )


@pytest.fixture
def devices() -> dict[str, tuple[float, float]]:
    return {"Q1": (5.0, 5.0)}


@pytest.fixture
def device_thermal() -> dict[str, DeviceThermalConfig]:
    return {
        "Q1": DeviceThermalConfig(
            name="Q1",
            R_theta_jc=0.6,
            R_theta_cs=0.5,
            R_theta_sa=5.0,
            T_j_max=150.0,
            R_jc_because="STGW30NC60W datasheet §2.1",
            R_cs_because="TO-247 thermal pad, mica insulator",
            R_sa_because="heatsink MFG datasheet",
        ),
    }


# ---------------------------------------------------------------------------
# Gate with absent Elmer → UNMEASURED
# ---------------------------------------------------------------------------


class TestElmerCorroborationGateAbsent:
    """Gate fails-closed when Elmer is absent."""

    def test_gate_unmeasured_when_elmer_absent(
        self, fdm_config, devices, device_thermal, monkeypatch
    ):
        import shutil

        monkeypatch.setattr(shutil, "which", lambda name: None)

        config = ElmerGateConfig(
            fdm_config=fdm_config,
            devices=devices,
            power_map={"Q1": 15.0},
            device_thermal=device_thermal,
            tolerance_C=5.0,
        )
        gate = ElmerCorroborationGate(config)
        result = gate._check_inner()
        assert result.status is GateStatus.UNMEASURED
        assert "not found" in result.error_message.lower()


# ---------------------------------------------------------------------------
# Gate with synthetic comparison where fields agree → CLEAN
# ---------------------------------------------------------------------------


class TestElmerCorroborationGateClean:
    """Gate returns CLEAN when Elmer is present and fields agree."""

    def test_gate_clean_synthetic_agree(
        self, fdm_config, devices, device_thermal, monkeypatch, tmp_path
    ):
        import shutil

        from temper_placer.validation.elmer import ElmerResult, ElmerRunner
        from temper_placer.fields.field import CostField
        from temper_placer.fields.result import FieldResult
        from temper_placer.placer.cp_sat.gates import GateResult, GateStatus as GS

        monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")

        H, W = fdm_config.height_cells, fdm_config.width_cells
        cs = fdm_config.cell_size_mm
        ox, oy = fdm_config.origin_mm
        T = np.full((H, W), 45.0, dtype=np.float64)

        # Node coords: FDM cell centres at mid-plane (mm)
        xc = ox + (np.arange(W, dtype=np.float64) + 0.5) * cs
        yc = oy + (np.arange(H, dtype=np.float64) + 0.5) * cs
        xx, yy = np.meshgrid(xc, yc)
        z_mid = 1.6 / 2.0
        node_coords = np.column_stack([xx.ravel(), yy.ravel(), np.full(H*W, z_mid)])

        # Monkey-patch FDM solver to return our synthetic field
        def fake_fdm(config, devices, power_map, copper_grid=None, h_field=None):
            return FieldResult(
                gate_result=GateResult(status=GS.CLEAN),
                field=CostField(
                    grid=T,
                    cell_size_mm=config.cell_size_mm,
                    origin_mm=config.origin_mm,
                ),
            )

        monkeypatch.setattr(
            "temper_placer.physics.thermal_fdm.solve_thermal_fdm",
            fake_fdm,
        )

        # Monkey-patch ElmerGrid to be a no-op
        monkeypatch.setattr(
            "temper_placer.validation.elmer.elmer_grid",
            lambda mesh_dir: None,
        )

        # Monkey-patch ElmerRunner.run to return matching field + node_coords
        def fake_run(self, mesh_dir, sif_path):
            return ElmerResult(
                success=True,
                temperature_field=T.ravel().copy(),
                node_coords=node_coords.copy(),
                elapsed_ms=10.0,
            )

        monkeypatch.setattr(ElmerRunner, "run", fake_run)

        config = ElmerGateConfig(
            fdm_config=fdm_config,
            devices=devices,
            power_map={"Q1": 15.0},
            device_thermal=device_thermal,
            tolerance_C=5.0,
        )
        gate = ElmerCorroborationGate(config, output_dir=tmp_path / "elmermesh")
        result = gate._check_inner()

        assert result.status is GateStatus.CLEAN


# ---------------------------------------------------------------------------
# Gate with synthetic fields that disagree → VIOLATIONS
# ---------------------------------------------------------------------------


class TestElmerCorroborationGateViolations:
    """Gate returns VIOLATIONS when fields disagree beyond tolerance."""

    def test_gate_violations_synthetic_disagree(
        self, fdm_config, devices, device_thermal, monkeypatch, tmp_path
    ):
        import shutil

        from temper_placer.validation.elmer import ElmerResult, ElmerRunner
        from temper_placer.fields.field import CostField
        from temper_placer.fields.result import FieldResult
        from temper_placer.placer.cp_sat.gates import GateResult as GR, GateStatus as GS

        monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")

        H, W = fdm_config.height_cells, fdm_config.width_cells
        cs = fdm_config.cell_size_mm
        ox, oy = fdm_config.origin_mm
        T_fdm = np.full((H, W), 45.0, dtype=np.float64)

        # Node coords: FDM cell centres at mid-plane (mm)
        xc = ox + (np.arange(W, dtype=np.float64) + 0.5) * cs
        yc = oy + (np.arange(H, dtype=np.float64) + 0.5) * cs
        xx, yy = np.meshgrid(xc, yc)
        z_mid = 1.6 / 2.0
        node_coords = np.column_stack([xx.ravel(), yy.ravel(), np.full(H*W, z_mid)])

        # Mock FDM to return a cool uniform field
        def fake_fdm(config, devices, power_map, copper_grid=None, h_field=None):
            return FieldResult(
                gate_result=GR(status=GS.CLEAN),
                field=CostField(
                    grid=T_fdm,
                    cell_size_mm=config.cell_size_mm,
                    origin_mm=config.origin_mm,
                ),
            )

        monkeypatch.setattr(
            "temper_placer.physics.thermal_fdm.solve_thermal_fdm",
            fake_fdm,
        )

        # Monkey-patch ElmerGrid to be a no-op
        monkeypatch.setattr(
            "temper_placer.validation.elmer.elmer_grid",
            lambda mesh_dir: None,
        )

        # Elmer returns a much hotter field — disagreement
        T_elmer = np.full((H, W), 200.0, dtype=np.float64)

        def fake_run(self, mesh_dir, sif_path):
            return ElmerResult(
                success=True,
                temperature_field=T_elmer.ravel().copy(),
                node_coords=node_coords.copy(),
                elapsed_ms=10.0,
            )

        monkeypatch.setattr(ElmerRunner, "run", fake_run)

        config = ElmerGateConfig(
            fdm_config=fdm_config,
            devices=devices,
            power_map={"Q1": 15.0},
            device_thermal=device_thermal,
            tolerance_C=5.0,
        )
        gate = ElmerCorroborationGate(config, output_dir=tmp_path / "elmermesh_v")
        result = gate._check_inner()

        assert result.status is GateStatus.VIOLATIONS
        assert len(result.violations) >= 1
        violation = result.violations[0]
        assert "Elmer-FDM" in violation.description


# ---------------------------------------------------------------------------
# GateConfig validation
# ---------------------------------------------------------------------------


class TestElmerGateConfig:
    """ElmerGateConfig dataclass behaviour."""

    def test_config_creation(self, fdm_config, devices, device_thermal):
        config = ElmerGateConfig(
            fdm_config=fdm_config,
            devices=devices,
            power_map={"Q1": 15.0},
            device_thermal=device_thermal,
            tolerance_C=5.0,
        )
        assert config.fdm_config is fdm_config
        assert config.devices == devices
        assert config.tolerance_C == 5.0

    def test_config_default_tolerance(self, fdm_config, devices, device_thermal):
        config = ElmerGateConfig(
            fdm_config=fdm_config,
            devices=devices,
            power_map={"Q1": 15.0},
            device_thermal=device_thermal,
        )
        assert config.tolerance_C == 5.0

    def test_config_with_copper_grid(self, fdm_config, devices, device_thermal):
        copper = np.ones(
            (fdm_config.height_cells, fdm_config.width_cells), dtype=np.float64
        ) * 0.4
        config = ElmerGateConfig(
            fdm_config=fdm_config,
            devices=devices,
            power_map={"Q1": 15.0},
            device_thermal=device_thermal,
            copper_grid=copper,
        )
        assert config.copper_grid is not None


# ---------------------------------------------------------------------------
# Gate name and stage
# ---------------------------------------------------------------------------


class TestGateMetadata:
    """Gate metadata — name and stage."""

    def test_gate_name(self, fdm_config, devices, device_thermal):
        config = ElmerGateConfig(
            fdm_config=fdm_config,
            devices=devices,
            power_map={"Q1": 15.0},
            device_thermal=device_thermal,
        )
        gate = ElmerCorroborationGate(config)
        assert gate.name == "elmer_corroboration"
        assert gate.stage.name == "ROUTING"
