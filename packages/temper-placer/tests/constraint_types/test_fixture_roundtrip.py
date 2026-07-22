"""Round-trip tests: load every YAML fixture/config and verify key fields."""

from pathlib import Path

from temper_placer.io.config_loader import load_constraints

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
CONFIGS_DIR = Path(__file__).parent.parent.parent / "configs"


class TestFixtureRoundtrip:
    def test_constraints_minimal(self):
        c = load_constraints(FIXTURES_DIR / "constraints_minimal.yaml")
        assert c.board_width_mm == 50.0
        assert c.board_height_mm == 30.0
        assert c.board_margin_mm == 2.0
        assert len(c.zones) == 1
        assert len(c.component_groups) == 2

    def test_constraints_medium(self):
        c = load_constraints(FIXTURES_DIR / "constraints_medium.yaml")
        assert c.board_width_mm == 60.0
        assert c.board_height_mm == 40.0
        assert c.board_margin_mm == 2.0
        assert len(c.zones) == 3
        assert len(c.component_groups) == 9
        assert len(c.fixed_components) == 2  # dict format converted to list

    def test_constraints_large(self):
        c = load_constraints(FIXTURES_DIR / "constraints_large.yaml")
        assert c.board_width_mm == 100.0
        assert c.board_height_mm == 150.0
        assert len(c.zones) == 7
        assert len(c.component_groups) == 6

    def test_constraints_structural(self):
        c = load_constraints(FIXTURES_DIR / "constraints_structural.yaml")
        assert c.board_width_mm == 100.0
        assert c.board_height_mm == 100.0
        assert len(c.zones) == 1
        assert len(c.component_groups) == 2

    def test_temper_constraints(self):
        c = load_constraints(CONFIGS_DIR / "temper_constraints.yaml")
        assert c.board_width_mm == 100.0
        assert c.board_height_mm == 150.0
        assert c.board_margin_mm == 3.0
        assert len(c.zones) == 4
        assert len(c.component_groups) == 15  # 9 groups + 6 component_groups
        assert c.hv_clearance_mm == 10.0
        assert len(c.net_class_rules) > 0
        assert len(c.fixed_components) >= 4

    def test_empty_config_defaults(self, tmp_path):
        p = tmp_path / "empty.yaml"
        p.write_text("{}")
        c = load_constraints(p)
        assert c.board_width_mm == 100.0
        assert c.board_height_mm == 150.0
        assert c.board_margin_mm == 3.0
