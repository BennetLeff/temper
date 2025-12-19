"""
Unit tests for footprint library loading (temper-1my.1.2).

Tests cover:
- Loading footprint library from YAML
- Accessing footprint bounds and properties
- Error handling for missing/invalid footprints
- Integration with Component creation
"""


import pytest
import yaml

from temper_placer.core.netlist import Component
from temper_placer.io.footprint_library import (
    FootprintLibrary,
    FootprintSpec,
    load_footprint_library,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def sample_library_yaml():
    """Sample footprint library YAML content."""
    return """
footprints:
  TO-247-3:
    bounds: [16.0, 21.0]
    courtyard_margin: 0.25
    thermal_pad: true
    pin_1_offset: [-5.08, 0]

  SOIC-16_W:
    bounds: [10.3, 7.5]
    courtyard_margin: 0.2
    thermal_pad: false

  "0805":
    bounds: [2.0, 1.25]
    courtyard_margin: 0.15
    thermal_pad: false

  "0603":
    bounds: [1.6, 0.8]
    courtyard_margin: 0.1
    thermal_pad: false
"""


@pytest.fixture
def library_file(sample_library_yaml, tmp_path):
    """Create a temporary footprint library file."""
    library_path = tmp_path / "footprints.yaml"
    library_path.write_text(sample_library_yaml)
    return library_path


# =============================================================================
# FootprintSpec Tests
# =============================================================================


class TestFootprintSpec:
    """Tests for FootprintSpec data class."""

    def test_creation(self):
        """Test creating a FootprintSpec."""
        spec = FootprintSpec(
            name="TO-247-3",
            bounds=(16.0, 21.0),
            courtyard_margin=0.25,
            thermal_pad=True,
            pin_1_offset=(-5.08, 0.0),
        )

        assert spec.name == "TO-247-3"
        assert spec.bounds == (16.0, 21.0)
        assert spec.courtyard_margin == 0.25
        assert spec.thermal_pad is True
        assert spec.pin_1_offset == (-5.08, 0.0)

    def test_default_values(self):
        """Test default values for optional fields."""
        spec = FootprintSpec(
            name="0805",
            bounds=(2.0, 1.25),
        )

        assert spec.courtyard_margin == 0.0
        assert spec.thermal_pad is False
        assert spec.pin_1_offset is None

    def test_width_height_properties(self):
        """Test width/height convenience properties."""
        spec = FootprintSpec(
            name="0805",
            bounds=(2.0, 1.25),
        )

        assert spec.width == 2.0
        assert spec.height == 1.25


# =============================================================================
# FootprintLibrary Tests
# =============================================================================


class TestFootprintLibrary:
    """Tests for FootprintLibrary class."""

    def test_empty_library(self):
        """Test creating an empty library."""
        lib = FootprintLibrary()

        assert len(lib) == 0
        assert list(lib.footprints.keys()) == []

    def test_add_footprint(self):
        """Test adding footprints to library."""
        lib = FootprintLibrary()

        spec = FootprintSpec("0805", (2.0, 1.25))
        lib.add(spec)

        assert len(lib) == 1
        assert "0805" in lib
        assert lib["0805"] == spec

    def test_get_footprint(self):
        """Test getting footprint by name."""
        lib = FootprintLibrary()
        spec = FootprintSpec("0805", (2.0, 1.25))
        lib.add(spec)

        retrieved = lib.get("0805")
        assert retrieved == spec

    def test_get_missing_footprint(self):
        """Test getting non-existent footprint."""
        lib = FootprintLibrary()

        with pytest.raises(KeyError):
            lib.get("NONEXISTENT")

    def test_get_with_default(self):
        """Test get with default value."""
        lib = FootprintLibrary()

        default = FootprintSpec("DEFAULT", (1.0, 1.0))
        result = lib.get("NONEXISTENT", default=default)

        assert result == default

    def test_contains(self):
        """Test checking if footprint exists."""
        lib = FootprintLibrary()
        lib.add(FootprintSpec("0805", (2.0, 1.25)))

        assert "0805" in lib
        assert "0603" not in lib

    def test_iteration(self):
        """Test iterating over footprints."""
        lib = FootprintLibrary()
        lib.add(FootprintSpec("0805", (2.0, 1.25)))
        lib.add(FootprintSpec("0603", (1.6, 0.8)))

        names = list(lib.footprints.keys())
        assert "0805" in names
        assert "0603" in names


# =============================================================================
# YAML Loading Tests
# =============================================================================


class TestLoadFootprintLibrary:
    """Tests for loading footprint library from YAML."""

    def test_load_from_file(self, library_file):
        """Test loading library from YAML file."""
        lib = load_footprint_library(library_file)

        assert len(lib) == 4
        assert "TO-247-3" in lib
        assert "SOIC-16_W" in lib
        assert "0805" in lib
        assert "0603" in lib

    def test_load_to247_bounds(self, library_file):
        """Test TO-247-3 bounds are correct."""
        lib = load_footprint_library(library_file)
        spec = lib["TO-247-3"]

        assert spec.bounds == (16.0, 21.0)
        assert spec.width == 16.0
        assert spec.height == 21.0

    def test_load_thermal_pad_flag(self, library_file):
        """Test thermal_pad flag is loaded correctly."""
        lib = load_footprint_library(library_file)

        assert lib["TO-247-3"].thermal_pad is True
        assert lib["SOIC-16_W"].thermal_pad is False

    def test_load_pin_offset(self, library_file):
        """Test pin_1_offset is loaded correctly."""
        lib = load_footprint_library(library_file)

        assert lib["TO-247-3"].pin_1_offset == (-5.08, 0.0)
        assert lib["SOIC-16_W"].pin_1_offset is None

    def test_load_invalid_file(self):
        """Test loading non-existent file."""
        with pytest.raises(FileNotFoundError):
            load_footprint_library("nonexistent.yaml")

    def test_load_malformed_yaml(self, tmp_path):
        """Test loading malformed YAML."""
        bad_file = tmp_path / "bad.yaml"
        bad_file.write_text("{ invalid yaml: [")

        with pytest.raises(yaml.YAMLError):
            load_footprint_library(bad_file)

    def test_load_missing_bounds(self, tmp_path):
        """Test footprint missing required 'bounds' field."""
        bad_lib = tmp_path / "bad_lib.yaml"
        bad_lib.write_text("""
footprints:
  BadFootprint:
    courtyard_margin: 0.1
    # Missing bounds!
""")

        with pytest.raises(ValueError, match="bounds"):
            load_footprint_library(bad_lib)

    def test_load_invalid_bounds_format(self, tmp_path):
        """Test footprint with invalid bounds format."""
        bad_lib = tmp_path / "bad_lib.yaml"
        bad_lib.write_text("""
footprints:
  BadFootprint:
    bounds: [1.0]  # Should be [width, height]
""")

        with pytest.raises(ValueError, match="bounds"):
            load_footprint_library(bad_lib)

    def test_load_from_string(self, sample_library_yaml):
        """Test loading library from YAML string."""
        lib = FootprintLibrary.from_yaml_string(sample_library_yaml)

        assert len(lib) == 4
        assert "TO-247-3" in lib


# =============================================================================
# Integration Tests
# =============================================================================


class TestFootprintLibraryIntegration:
    """Integration tests with Component creation."""

    def test_create_component_from_library(self, library_file):
        """Test creating component using library bounds."""
        lib = load_footprint_library(library_file)

        # Get bounds from library
        spec = lib["0805"]

        # Create component
        comp = Component(
            ref="R1",
            footprint="0805",
            bounds=spec.bounds,
        )

        assert comp.bounds == (2.0, 1.25)
        assert comp.width == 2.0
        assert comp.height == 1.25

    def test_library_provides_accurate_bounds(self, library_file):
        """Test that library bounds match expected values."""
        lib = load_footprint_library(library_file)

        # Verify key footprints
        assert lib["TO-247-3"].bounds == (16.0, 21.0)
        assert lib["SOIC-16_W"].bounds == (10.3, 7.5)
        assert lib["0805"].bounds == (2.0, 1.25)
        assert lib["0603"].bounds == (1.6, 0.8)

    def test_component_factory_pattern(self, library_file):
        """Test using library as a component factory."""
        lib = load_footprint_library(library_file)

        def make_component(ref: str, footprint: str, **kwargs):
            """Factory function using library."""
            if footprint not in lib:
                raise ValueError(f"Unknown footprint: {footprint}")

            spec = lib[footprint]
            return Component(
                ref=ref,
                footprint=footprint,
                bounds=spec.bounds,
                **kwargs
            )

        # Use factory
        r1 = make_component("R1", "0805")
        q1 = make_component("Q1", "TO-247-3")

        assert r1.bounds == (2.0, 1.25)
        assert q1.bounds == (16.0, 21.0)

        # Should fail for unknown footprint
        with pytest.raises(ValueError, match="Unknown footprint"):
            make_component("U1", "UNKNOWN")
