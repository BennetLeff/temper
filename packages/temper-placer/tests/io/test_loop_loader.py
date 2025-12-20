"""
Tests for the loop template loader.
"""

import tempfile
from pathlib import Path

import pytest

from temper_placer.core.loop import (
    Loop,
    LoopCollection,
    LoopPriority,
    LoopType,
)
from temper_placer.io.loop_loader import (
    LoopLoadError,
    load_loop_collection,
    load_loop_from_dict,
    load_loop_template,
    save_loop_to_yaml,
)


class TestLoadLoopFromDict:
    """Tests for loading loops from dictionaries."""

    def test_minimal_loop(self):
        """Should load loop with only required fields."""
        data = {
            "name": "test_loop",
            "loop_type": "custom",
        }
        loop = load_loop_from_dict(data)
        assert loop.name == "test_loop"
        assert loop.loop_type == LoopType.CUSTOM
        assert loop.priority == LoopPriority.MEDIUM  # Default

    def test_full_loop(self):
        """Should load loop with all fields."""
        data = {
            "name": "commutation",
            "loop_type": "commutation",
            "description": "Main switching loop",
            "components": ["Q1", "Q2", "C_BUS"],
            "pins": [
                {"component": "Q1", "pin": "COLLECTOR", "net": "DC_BUS+"},
                {"component": "Q1", "pin": "EMITTER", "net": "SW_NODE"},
            ],
            "nets": ["DC_BUS+", "SW_NODE"],
            "max_area_mm2": 200,
            "priority": "critical",
            "events": {
                "di_dt": 1e9,
                "frequency_hz": 25000,
                "peak_current_a": 50,
            },
            "return_layer": "L2_GND",
            "return_net": "PGND",
        }

        loop = load_loop_from_dict(data)

        assert loop.name == "commutation"
        assert loop.loop_type == LoopType.COMMUTATION
        assert loop.description == "Main switching loop"
        assert loop.components == ["Q1", "Q2", "C_BUS"]
        assert len(loop.pins) == 2
        assert loop.pins[0].component_ref == "Q1"
        assert loop.pins[0].net_name == "DC_BUS+"
        assert loop.max_area_mm2 == 200
        assert loop.priority == LoopPriority.CRITICAL
        assert loop.events.di_dt == 1e9
        assert loop.events.frequency_hz == 25000
        assert loop.return_layer == "L2_GND"

    def test_missing_name_raises(self):
        """Should raise error if name is missing."""
        data = {"loop_type": "custom"}
        with pytest.raises(LoopLoadError, match="name"):
            load_loop_from_dict(data)

    def test_missing_loop_type_raises(self):
        """Should raise error if loop_type is missing."""
        data = {"name": "test"}
        with pytest.raises(LoopLoadError, match="loop_type"):
            load_loop_from_dict(data)

    def test_invalid_loop_type_raises(self):
        """Should raise error for unknown loop type."""
        data = {"name": "test", "loop_type": "invalid_type"}
        with pytest.raises(LoopLoadError, match="Unknown loop type"):
            load_loop_from_dict(data)

    def test_invalid_priority_raises(self):
        """Should raise error for unknown priority."""
        data = {"name": "test", "loop_type": "custom", "priority": "super_critical"}
        with pytest.raises(LoopLoadError, match="Unknown priority"):
            load_loop_from_dict(data)

    def test_case_insensitive_loop_type(self):
        """Loop type should be case-insensitive."""
        data = {"name": "test", "loop_type": "COMMUTATION"}
        loop = load_loop_from_dict(data)
        assert loop.loop_type == LoopType.COMMUTATION

    def test_case_insensitive_priority(self):
        """Priority should be case-insensitive."""
        data = {"name": "test", "loop_type": "custom", "priority": "CRITICAL"}
        loop = load_loop_from_dict(data)
        assert loop.priority == LoopPriority.CRITICAL


class TestLoadLoopTemplate:
    """Tests for loading loop templates from files."""

    def test_load_existing_template(self):
        """Should load an existing template file."""
        # Use the actual commutation template
        template_path = (
            Path(__file__).parent.parent.parent / "configs/templates/loops/commutation.yaml"
        )
        if not template_path.exists():
            pytest.skip("Template file not found")

        loop = load_loop_template(template_path)
        assert loop.name == "commutation"
        assert loop.loop_type == LoopType.COMMUTATION
        assert loop.priority == LoopPriority.CRITICAL

    def test_file_not_found(self):
        """Should raise FileNotFoundError for missing file."""
        with pytest.raises(FileNotFoundError):
            load_loop_template("/nonexistent/path/loop.yaml")

    def test_invalid_yaml(self):
        """Should raise LoopLoadError for invalid YAML."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("invalid: yaml: content: [}")
            temp_path = f.name

        try:
            with pytest.raises(LoopLoadError, match="Invalid YAML"):
                load_loop_template(temp_path)
        finally:
            Path(temp_path).unlink()

    def test_empty_file(self):
        """Should raise LoopLoadError for empty file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("")
            temp_path = f.name

        try:
            with pytest.raises(LoopLoadError, match="Empty YAML"):
                load_loop_template(temp_path)
        finally:
            Path(temp_path).unlink()


class TestLoadLoopCollection:
    """Tests for loading collections of loop templates."""

    def test_load_template_directory(self):
        """Should load all templates from a directory."""
        template_dir = Path(__file__).parent.parent.parent / "configs/templates/loops"
        if not template_dir.exists():
            pytest.skip("Template directory not found")

        collection = load_loop_collection(template_dir)

        # Should have at least the 5 standard templates
        assert len(collection) >= 5

        # Should have commutation loop
        comm = collection.get_loop("commutation")
        assert comm is not None
        assert comm.priority == LoopPriority.CRITICAL

    def test_collection_name_from_directory(self):
        """Collection name should default to directory name."""
        template_dir = Path(__file__).parent.parent.parent / "configs/templates/loops"
        if not template_dir.exists():
            pytest.skip("Template directory not found")

        collection = load_loop_collection(template_dir)
        assert collection.name == "loops"

    def test_custom_collection_name(self):
        """Should use custom collection name if provided."""
        template_dir = Path(__file__).parent.parent.parent / "configs/templates/loops"
        if not template_dir.exists():
            pytest.skip("Template directory not found")

        collection = load_loop_collection(
            template_dir,
            name="my_loops",
            description="My custom collection",
        )
        assert collection.name == "my_loops"
        assert collection.description == "My custom collection"

    def test_directory_not_found(self):
        """Should raise FileNotFoundError for missing directory."""
        with pytest.raises(FileNotFoundError):
            load_loop_collection("/nonexistent/directory")

    def test_not_a_directory(self):
        """Should raise LoopLoadError for file path."""
        with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as f:
            temp_path = f.name

        try:
            with pytest.raises(LoopLoadError, match="not a directory"):
                load_loop_collection(temp_path)
        finally:
            Path(temp_path).unlink()


class TestSaveLoopToYaml:
    """Tests for saving loops to YAML."""

    def test_save_and_reload(self):
        """Should be able to save and reload a loop."""
        from temper_placer.core.loop import LoopEvent, LoopPin

        original = Loop(
            name="test_loop",
            loop_type=LoopType.GATE_DRIVE_HIGH,
            description="Test loop for saving",
            components=["U1", "Q1"],
            pins=[
                LoopPin("U1", "OUT", "NET1"),
                LoopPin("Q1", "GATE", "NET1"),
            ],
            nets=["NET1"],
            max_area_mm2=50.0,
            priority=LoopPriority.HIGH,
            events=LoopEvent(di_dt=1e9, frequency_hz=50000),
            return_layer="L2_GND",
            return_net="GND",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test_loop.yaml"
            save_loop_to_yaml(original, path)

            # Verify file exists
            assert path.exists()

            # Reload and compare
            reloaded = load_loop_template(path)

            assert reloaded.name == original.name
            assert reloaded.loop_type == original.loop_type
            assert reloaded.description == original.description
            assert reloaded.components == original.components
            assert len(reloaded.pins) == len(original.pins)
            assert reloaded.max_area_mm2 == original.max_area_mm2
            assert reloaded.priority == original.priority
            assert reloaded.events.di_dt == original.events.di_dt
            assert reloaded.return_layer == original.return_layer

    def test_save_minimal_loop(self):
        """Should save loop with minimal fields."""
        minimal = Loop(
            name="minimal",
            loop_type=LoopType.CUSTOM,
            description="",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "minimal.yaml"
            save_loop_to_yaml(minimal, path)

            reloaded = load_loop_template(path)
            assert reloaded.name == "minimal"
            assert reloaded.loop_type == LoopType.CUSTOM


class TestInductionCookerTemplates:
    """Integration tests for induction cooker loop templates."""

    @pytest.fixture
    def template_dir(self):
        """Get the template directory path."""
        path = Path(__file__).parent.parent.parent / "configs/templates/loops"
        if not path.exists():
            pytest.skip("Template directory not found")
        return path

    def test_all_templates_load(self, template_dir):
        """All templates should load without error."""
        collection = load_loop_collection(template_dir)
        assert len(collection) >= 5

    def test_commutation_template(self, template_dir):
        """Commutation loop should have correct physics."""
        loop = load_loop_template(template_dir / "commutation.yaml")

        assert loop.loop_type == LoopType.COMMUTATION
        assert loop.priority == LoopPriority.CRITICAL
        assert loop.events.di_dt == 1.0e9  # 1 A/ns
        assert loop.events.frequency_hz == 25000  # 25 kHz
        assert loop.max_area_mm2 == 500

    def test_gate_drive_templates(self, template_dir):
        """Gate drive loops should have correct physics."""
        high = load_loop_template(template_dir / "gate_drive_high.yaml")
        low = load_loop_template(template_dir / "gate_drive_low.yaml")

        assert high.loop_type == LoopType.GATE_DRIVE_HIGH
        assert low.loop_type == LoopType.GATE_DRIVE_LOW

        # Both should be critical
        assert high.priority == LoopPriority.CRITICAL
        assert low.priority == LoopPriority.CRITICAL

        # Similar area constraints
        assert high.max_area_mm2 == low.max_area_mm2

    def test_bootstrap_template(self, template_dir):
        """Bootstrap loop should have correct settings."""
        loop = load_loop_template(template_dir / "bootstrap.yaml")

        assert loop.loop_type == LoopType.BOOTSTRAP
        assert loop.priority == LoopPriority.HIGH
        assert loop.max_area_mm2 <= 100  # Should be small but not critical

    def test_buck_template(self, template_dir):
        """Buck converter loop should have high frequency."""
        loop = load_loop_template(template_dir / "buck_15v.yaml")

        assert loop.loop_type == LoopType.BUCK_SWITCH
        assert loop.events.frequency_hz == 2400000  # 2.4 MHz
        assert loop.priority == LoopPriority.HIGH

    def test_critical_loops_count(self, template_dir):
        """Should have 3 critical loops (commutation + 2 gate drives)."""
        collection = load_loop_collection(template_dir)
        critical = collection.get_critical_loops()

        assert len(critical) == 3
        names = {l.name for l in critical}
        assert "commutation" in names
        assert "gate_drive_high" in names
        assert "gate_drive_low" in names
