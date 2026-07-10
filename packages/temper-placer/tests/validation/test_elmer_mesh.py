"""
Tests for Elmer mesh converter (validation/elmer_mesh.py).

Covers:
- ``build_temper_mesh()``: generates geo file + .sif in output directory.
- .sif contains required keywords: Heat Equation, Material, Boundary Condition.
- Edge cases: zero devices, zero copper (bare board).
- Error cases: invalid board geometry (zero dimensions).
"""

from pathlib import Path

import pytest

from temper_placer.core.board import Board
from temper_placer.physics.thermal_fdm import ThermalFDMConfig
from temper_placer.physics.tj_cross_check import DeviceThermalConfig
from temper_placer.validation.elmer_mesh import build_temper_mesh


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fdm_config() -> ThermalFDMConfig:
    return ThermalFDMConfig(
        cell_size_mm=0.5,
        origin_mm=(0.0, 0.0),
        height_cells=100,
        width_cells=200,
        ambient_C=40.0,
        heatsink_edge="TOP",
    )


@pytest.fixture
def board_temper() -> Board:
    return Board.temper_default()


@pytest.fixture
def devices() -> dict[str, tuple[float, float]]:
    return {"Q1": (25.0, 10.0)}


@pytest.fixture
def device_thermal() -> dict[str, DeviceThermalConfig]:
    return {
        "Q1": DeviceThermalConfig(
            name="Q1",
            R_theta_jc=0.6,
            R_theta_cs=0.5,
            R_theta_sa=5.0,
            T_j_max=150.0,
            R_jc_because="STGW30NC60W datasheet",
            R_cs_because="TO-247 thermal pad",
            R_sa_because="heatsink MFG datasheet",
        ),
    }


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestBuildTemperMesh:
    """Happy path: the converter produces a non-empty mesh dir + .sif."""

    def test_generates_geo_and_sif(self, board_temper, fdm_config, devices, device_thermal, tmp_path):
        out = tmp_path / "elmermesh"
        mesh_dir, sif_path = build_temper_mesh(
            board=board_temper,
            fdm_config=fdm_config,
            devices=devices,
            device_thermal=device_thermal,
            output_dir=out,
        )

        assert mesh_dir.is_dir()
        assert sif_path.is_file()

        # Check .sif content
        sif_text = sif_path.read_text()
        assert "Heat Equation" in sif_text
        assert "Material" in sif_text
        assert "Boundary Condition" in sif_text
        assert "Header" in sif_text
        assert "Simulation" in sif_text

        # Check .geo content
        geo_files = sorted(mesh_dir.glob("*.geo"))
        assert len(geo_files) >= 1
        geo_text = geo_files[0].read_text()
        assert "Point" in geo_text
        assert "Volume" in geo_text

    def test_sif_contains_temper_specific_keywords(
        self, board_temper, fdm_config, devices, device_thermal, tmp_path
    ):
        """.sif contains Heat Equation solver, Material blocks, BC blocks."""
        _, sif_path = build_temper_mesh(
            board=board_temper,
            fdm_config=fdm_config,
            devices=devices,
            device_thermal=device_thermal,
            output_dir=tmp_path / "mesh",
        )
        sif_text = sif_path.read_text()

        # Required sections present
        present_keywords = [
            "Heat Equation",
            "Material 1",
            "Material 2",
            "Boundary Condition",
            "Heatsink Edge",
            "Temperature",
        ]
        for kw in present_keywords:
            assert kw.lower() in sif_text.lower(), f"Missing keyword: {kw}"

    def test_sif_contains_device_material(
        self, board_temper, fdm_config, devices, device_thermal, tmp_path
    ):
        """.sif references device material blocks for each device."""
        _, sif_path = build_temper_mesh(
            board=board_temper,
            fdm_config=fdm_config,
            devices=devices,
            device_thermal=device_thermal,
            output_dir=tmp_path / "mesh",
        )
        sif_text = sif_path.read_text()
        assert "Device Q1" in sif_text

    def test_creates_output_dir_if_missing(
        self, board_temper, fdm_config, devices, device_thermal, tmp_path
    ):
        """Output directory is created automatically."""
        out = tmp_path / "new_subdir" / "elmermesh"
        assert not out.exists()
        mesh_dir, _ = build_temper_mesh(
            board=board_temper,
            fdm_config=fdm_config,
            devices=devices,
            device_thermal=device_thermal,
            output_dir=out,
        )
        assert mesh_dir.is_dir()


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestPowerMapBodyForces:
    """power_map → Body Force sections in .sif."""

    def test_power_map_generates_body_force_sections(
        self, board_temper, fdm_config, devices, device_thermal, tmp_path
    ):
        """Body Force N sections are generated for each powered device."""
        _, sif_path = build_temper_mesh(
            board=board_temper,
            fdm_config=fdm_config,
            devices=devices,
            device_thermal=device_thermal,
            power_map={"Q1": 15.0},
            output_dir=tmp_path / "mesh_bf",
        )
        sif_text = sif_path.read_text()
        assert "Body Force 1" in sif_text
        assert "Device Q1 Power" in sif_text
        assert "Heat Source = Real 15.000000" in sif_text

    def test_device_body_references_body_force(
        self, board_temper, fdm_config, devices, device_thermal, tmp_path
    ):
        """Device Body N references its Body Force."""
        _, sif_path = build_temper_mesh(
            board=board_temper,
            fdm_config=fdm_config,
            devices=devices,
            device_thermal=device_thermal,
            power_map={"Q1": 25.0},
            output_dir=tmp_path / "mesh_bf2",
        )
        sif_text = sif_path.read_text()
        assert "Body Force = 1" in sif_text
        assert 'Name = "Device Q1"' in sif_text

    def test_empty_power_map_generates_zero_body_force(
        self, board_temper, fdm_config, devices, device_thermal, tmp_path
    ):
        """Empty power_map generates a single zero Body Force."""
        _, sif_path = build_temper_mesh(
            board=board_temper,
            fdm_config=fdm_config,
            devices=devices,
            device_thermal=device_thermal,
            power_map={},
            output_dir=tmp_path / "mesh_zero_bf",
        )
        sif_text = sif_path.read_text()
        assert "Body Force 1" in sif_text
        assert "Zero Power" in sif_text
        assert "Heat Source = Real 0.0" in sif_text

    def test_none_power_map_generates_zero_body_force(
        self, board_temper, fdm_config, devices, device_thermal, tmp_path
    ):
        """None power_map (default) generates a single zero Body Force."""
        _, sif_path = build_temper_mesh(
            board=board_temper,
            fdm_config=fdm_config,
            devices=devices,
            device_thermal=device_thermal,
            output_dir=tmp_path / "mesh_none_bf",
        )
        sif_text = sif_path.read_text()
        assert "Zero Power" in sif_text

    def test_power_map_preserves_material_conductivity_no_heat_source(
        self, board_temper, fdm_config, devices, device_thermal, tmp_path
    ):
        """Device Material blocks do NOT contain Heat Source = Equals."""
        _, sif_path = build_temper_mesh(
            board=board_temper,
            fdm_config=fdm_config,
            devices=devices,
            device_thermal=device_thermal,
            power_map={"Q1": 15.0},
            output_dir=tmp_path / "mesh_no_equals",
        )
        sif_text = sif_path.read_text()
        assert 'Heat Source = Equals' not in sif_text
        assert "Heat Conductivity = 385.0" in sif_text


class TestEdgeCases:
    """Edge: zero devices, zero copper, minimal board."""

    def test_zero_devices(self, board_temper, fdm_config, tmp_path):
        """Mesh generated without device bodies when both dicts are empty."""
        mesh_dir, sif_path = build_temper_mesh(
            board=board_temper,
            fdm_config=fdm_config,
            devices={},
            device_thermal={},
            output_dir=tmp_path / "mesh_zero",
        )
        sif_text = sif_path.read_text()
        # "Device" keyword should only appear in comments / non-body context
        assert "Device Q" not in sif_text
        assert "Body 1" in sif_text
        assert "Body 2" in sif_text
        # The template should NOT have a Body with "Device" in its Name
        # It should have the ! No device bodies comment
        assert mesh_dir.is_dir()


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


class TestErrorCases:
    """Error: invalid board geometry."""

    def test_zero_width_board(self, fdm_config, tmp_path):
        board = Board(width=0.0, height=100.0)
        with pytest.raises(ValueError, match="invalid dimensions"):
            build_temper_mesh(
                board=board,
                fdm_config=fdm_config,
                devices={},
                device_thermal={},
                output_dir=tmp_path / "mesh",
            )

    def test_zero_height_board(self, fdm_config, tmp_path):
        board = Board(width=100.0, height=0.0)
        with pytest.raises(ValueError, match="invalid dimensions"):
            build_temper_mesh(
                board=board,
                fdm_config=fdm_config,
                devices={},
                device_thermal={},
                output_dir=tmp_path / "mesh",
            )
