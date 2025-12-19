"""
Unit tests for memory profiling (temper-1my.3.6).

Tests cover:
- Memory profiler execution
- Memory measurement collection
- Threshold enforcement
- Result formatting and export
"""

import json

from temper_placer.fixtures.synthetic import generate_200_component_netlist
from temper_placer.scale.memory_profiler import (
    MemoryProfile,
    check_memory_thresholds,
    profile_optimizer_memory,
)

# =============================================================================
# MemoryProfile Tests
# =============================================================================


class TestMemoryProfile:
    """Tests for MemoryProfile dataclass."""

    def test_creation(self):
        """Test creating a MemoryProfile."""
        profile = MemoryProfile(
            n_components=100,
            peak_rss_mb=512.5,
            jax_device_mb=128.0,
            memory_growth_mb_per_100_epochs=0.5,
            gc_collections=15,
            runtime_seconds=45.2,
        )

        assert profile.n_components == 100
        assert profile.peak_rss_mb == 512.5
        assert profile.jax_device_mb == 128.0
        assert profile.memory_growth_mb_per_100_epochs == 0.5
        assert profile.gc_collections == 15
        assert profile.runtime_seconds == 45.2

    def test_to_dict(self):
        """Test converting to dictionary."""
        profile = MemoryProfile(
            n_components=100,
            peak_rss_mb=512.5,
            jax_device_mb=128.0,
            memory_growth_mb_per_100_epochs=0.5,
            gc_collections=15,
            runtime_seconds=45.2,
        )

        data = profile.to_dict()

        assert data["n_components"] == 100
        assert data["peak_rss_mb"] == 512.5
        assert "memory_growth_mb_per_100_epochs" in data

    def test_from_dict(self):
        """Test creating from dictionary."""
        data = {
            "n_components": 100,
            "peak_rss_mb": 512.5,
            "jax_device_mb": 128.0,
            "memory_growth_mb_per_100_epochs": 0.5,
            "gc_collections": 15,
            "runtime_seconds": 45.2,
        }

        profile = MemoryProfile.from_dict(data)

        assert profile.n_components == 100
        assert profile.peak_rss_mb == 512.5


# =============================================================================
# Memory Profiling Tests
# =============================================================================


class TestProfileOptimizerMemory:
    """Tests for profile_optimizer_memory function."""

    def test_profile_small_netlist(self):
        """Test profiling with small netlist (fast test)."""
        netlist = generate_200_component_netlist(seed=42)
        # Use only first 50 components for speed
        netlist.components = netlist.components[:50]

        profile = profile_optimizer_memory(
            n_components=50,
            epochs=100,  # Short run for test
            seed=42,
            netlist=netlist,
        )

        assert profile.n_components == 50
        assert profile.peak_rss_mb > 0
        assert profile.runtime_seconds > 0

    def test_profile_measures_peak_memory(self):
        """Test that peak RSS is measured."""
        netlist = generate_200_component_netlist(seed=42)
        netlist.components = netlist.components[:50]

        profile = profile_optimizer_memory(
            n_components=50,
            epochs=100,
            seed=42,
            netlist=netlist,
        )

        # Should measure some memory usage
        assert profile.peak_rss_mb > 10  # At least 10MB

    def test_profile_measures_runtime(self):
        """Test that runtime is measured."""
        netlist = generate_200_component_netlist(seed=42)
        netlist.components = netlist.components[:50]

        profile = profile_optimizer_memory(
            n_components=50,
            epochs=100,
            seed=42,
            netlist=netlist,
        )

        # Should take measurable time
        assert profile.runtime_seconds > 0.1

    def test_profile_deterministic_with_seed(self):
        """Test that same seed gives similar results."""
        netlist1 = generate_200_component_netlist(seed=42)
        netlist1.components = netlist1.components[:50]

        netlist2 = generate_200_component_netlist(seed=42)
        netlist2.components = netlist2.components[:50]

        profile1 = profile_optimizer_memory(50, 100, seed=42, netlist=netlist1)
        profile2 = profile_optimizer_memory(50, 100, seed=42, netlist=netlist2)

        # Memory usage should be similar (within 10%)
        assert abs(profile1.peak_rss_mb - profile2.peak_rss_mb) / profile1.peak_rss_mb < 0.1

    def test_profile_increases_with_components(self):
        """Test that memory scales with component count."""
        netlist_small = generate_200_component_netlist(seed=42)
        netlist_small.components = netlist_small.components[:50]

        netlist_large = generate_200_component_netlist(seed=42)
        netlist_large.components = netlist_large.components[:100]

        profile_small = profile_optimizer_memory(50, 100, seed=42, netlist=netlist_small)
        profile_large = profile_optimizer_memory(100, 100, seed=42, netlist=netlist_large)

        # Larger netlist should use more memory
        assert profile_large.peak_rss_mb > profile_small.peak_rss_mb


# =============================================================================
# Threshold Tests
# =============================================================================


class TestCheckMemoryThresholds:
    """Tests for memory threshold checking."""

    def test_passes_under_threshold(self):
        """Test that profiles under threshold pass."""
        profile = MemoryProfile(
            n_components=100,
            peak_rss_mb=1000.0,  # Under 1000MB threshold (500 + 100*5)
            jax_device_mb=100.0,
            memory_growth_mb_per_100_epochs=400.0,  # Under 500MB/100 threshold
            gc_collections=10,
            runtime_seconds=30.0,
        )

        result = check_memory_thresholds(profile)

        assert result.passed is True
        assert len(result.violations) == 0

    def test_fails_peak_memory_threshold(self):
        """Test that excessive peak memory is flagged."""
        profile = MemoryProfile(
            n_components=100,
            peak_rss_mb=2000.0,  # Over 1000MB threshold (500 + 100*5)
            jax_device_mb=100.0,
            memory_growth_mb_per_100_epochs=400.0,
            gc_collections=10,
            runtime_seconds=30.0,
        )

        result = check_memory_thresholds(profile)

        assert result.passed is False
        assert len(result.violations) > 0
        assert any("peak_rss_mb" in v for v in result.violations)

    def test_fails_memory_growth_threshold(self):
        """Test that memory leaks are flagged."""
        profile = MemoryProfile(
            n_components=100,
            peak_rss_mb=1000.0,
            jax_device_mb=100.0,
            memory_growth_mb_per_100_epochs=600.0,  # Over 500MB/100 threshold
            gc_collections=10,
            runtime_seconds=30.0,
        )

        result = check_memory_thresholds(profile)

        assert result.passed is False
        assert any("memory_growth" in v for v in result.violations)

    def test_custom_thresholds(self):
        """Test using custom thresholds."""
        profile = MemoryProfile(
            n_components=200,
            peak_rss_mb=3500.0,
            jax_device_mb=100.0,
            memory_growth_mb_per_100_epochs=0.5,
            gc_collections=10,
            runtime_seconds=30.0,
        )

        # Custom thresholds for 200 components
        thresholds = {
            200: {"peak_rss_mb": 4000.0, "memory_growth_mb_per_100_epochs": 1.0}
        }

        result = check_memory_thresholds(profile, custom_thresholds=thresholds)

        assert result.passed is True


# =============================================================================
# Export Tests
# =============================================================================


class TestMemoryProfileExport:
    """Tests for exporting memory profiles."""

    def test_export_to_json(self, tmp_path):
        """Test exporting profile to JSON."""
        profile = MemoryProfile(
            n_components=100,
            peak_rss_mb=512.5,
            jax_device_mb=128.0,
            memory_growth_mb_per_100_epochs=0.5,
            gc_collections=15,
            runtime_seconds=45.2,
        )

        output_file = tmp_path / "profile.json"
        profile.save_json(output_file)

        assert output_file.exists()

        # Load and verify
        with open(output_file) as f:
            data = json.load(f)

        assert data["n_components"] == 100
        assert data["peak_rss_mb"] == 512.5

    def test_load_from_json(self, tmp_path):
        """Test loading profile from JSON."""
        profile = MemoryProfile(
            n_components=100,
            peak_rss_mb=512.5,
            jax_device_mb=128.0,
            memory_growth_mb_per_100_epochs=0.5,
            gc_collections=15,
            runtime_seconds=45.2,
        )

        output_file = tmp_path / "profile.json"
        profile.save_json(output_file)

        loaded = MemoryProfile.load_json(output_file)

        assert loaded.n_components == profile.n_components
        assert loaded.peak_rss_mb == profile.peak_rss_mb

    def test_export_multiple_profiles(self, tmp_path):
        """Test exporting multiple profiles as report."""
        profiles = [
            MemoryProfile(50, 500.0, 100.0, 0.3, 10, 20.0),
            MemoryProfile(100, 1000.0, 200.0, 0.5, 15, 40.0),
            MemoryProfile(200, 2000.0, 400.0, 0.8, 25, 80.0),
        ]

        output_file = tmp_path / "memory_report.json"
        MemoryProfile.save_report(profiles, output_file)

        assert output_file.exists()

        # Load and verify
        with open(output_file) as f:
            data = json.load(f)

        assert len(data["profiles"]) == 3
        assert data["profiles"][0]["n_components"] == 50
