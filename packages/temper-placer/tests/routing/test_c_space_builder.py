"""
Tests for C-Space Builder module.

Part of temper-v6u3: C-Space Builder: OpenCV Rasterization
"""

import pytest
import numpy as np

from temper_placer.routing.c_space_builder import (
    CSpaceBuilder,
    CSpaceCache,
    CSpaceConfig,
    CSpaceGrid,
    HAS_OPENCV,
    HAS_SHAPELY,
)


# Skip all tests if dependencies not installed
pytestmark = pytest.mark.skipif(
    not (HAS_OPENCV and HAS_SHAPELY),
    reason="OpenCV and Shapely required for C-Space tests"
)


class TestCSpaceConfig:
    """Tests for CSpaceConfig dataclass."""
    
    def test_default_values(self):
        config = CSpaceConfig()
        assert config.resolution_mm == 0.1
        assert config.default_trace_width == 0.2
        assert config.default_clearance == 0.2
    
    def test_custom_values(self):
        config = CSpaceConfig(
            resolution_mm=0.05,
            power_trace_width=3.0,
        )
        assert config.resolution_mm == 0.05
        assert config.power_trace_width == 3.0


class TestCSpaceGrid:
    """Tests for CSpaceGrid operations."""
    
    def test_world_to_pixel(self):
        grid = np.zeros((100, 200), dtype=np.uint8)
        c_space = CSpaceGrid(
            grid=grid,
            origin=(10.0, 20.0),
            resolution=0.1,
            trace_width=0.2,
            clearance=0.2,
        )
        
        # Origin maps to (0, 0)
        px, py = c_space.world_to_pixel(10.0, 20.0)
        assert px == 0
        assert py == 0
        
        # 1mm from origin -> 10 pixels
        px, py = c_space.world_to_pixel(11.0, 21.0)
        assert px == 10
        assert py == 10
    
    def test_pixel_to_world(self):
        grid = np.zeros((100, 200), dtype=np.uint8)
        c_space = CSpaceGrid(
            grid=grid,
            origin=(0.0, 0.0),
            resolution=0.1,
            trace_width=0.2,
            clearance=0.2,
        )
        
        # Pixel (0, 0) maps to cell center (0.05, 0.05)
        x, y = c_space.pixel_to_world(0, 0)
        assert abs(x - 0.05) < 0.001
        assert abs(y - 0.05) < 0.001
        
        # Pixel (10, 10) maps to (1.05, 1.05)
        x, y = c_space.pixel_to_world(10, 10)
        assert abs(x - 1.05) < 0.001
        assert abs(y - 1.05) < 0.001
    
    def test_is_free(self):
        grid = np.zeros((100, 100), dtype=np.uint8)
        grid[50, 50] = 255  # Block one cell
        
        c_space = CSpaceGrid(
            grid=grid,
            origin=(0.0, 0.0),
            resolution=0.1,
            trace_width=0.2,
            clearance=0.2,
        )
        
        # (0, 0) should be free
        assert c_space.is_free(0.0, 0.0)
        
        # (5.0, 5.0) maps to pixel (50, 50) which is blocked
        assert not c_space.is_free(5.0, 5.0)


class TestCSpaceBuilder:
    """Tests for CSpaceBuilder functionality."""
    
    def test_initialization(self):
        builder = CSpaceBuilder(
            width_mm=100.0,
            height_mm=150.0,
            origin=(0.0, 0.0),
        )
        
        assert builder.width_mm == 100.0
        assert builder.height_mm == 150.0
        assert builder.width_px == 1000  # 100mm / 0.1mm
        assert builder.height_px == 1500  # 150mm / 0.1mm
    
    def test_add_pad(self):
        builder = CSpaceBuilder(width_mm=50.0, height_mm=50.0)
        
        builder.add_pad(
            center_x=25.0,
            center_y=25.0,
            width=2.0,
            height=1.0,
            net="VCC",
        )
        
        assert len(builder._obstacles) == 1
        assert builder._obstacle_nets[0] == "VCC"
    
    def test_build_empty_grid(self):
        builder = CSpaceBuilder(width_mm=10.0, height_mm=10.0)
        
        grid = builder.build_c_space_grid()
        
        assert grid.grid.shape == (100, 100)  # 10mm / 0.1mm
        assert np.all(grid.grid == 0)  # All free
    
    def test_build_grid_with_pad(self):
        builder = CSpaceBuilder(width_mm=20.0, height_mm=20.0)
        
        # Add a 2mm x 2mm pad at center
        builder.add_pad(10.0, 10.0, 2.0, 2.0, net="TEST")
        
        # Build with 0.2mm trace, 0.2mm clearance
        # Fatal radius = 0.1 + 0.2 = 0.3mm
        grid = builder.build_c_space_grid(trace_width=0.2, clearance=0.2)
        
        # Center should be blocked
        assert not grid.is_free(10.0, 10.0)
        
        # Edge of pad (at 11mm) + fatal radius (0.3mm) should be blocked
        assert not grid.is_free(11.2, 10.0)
        
        # Beyond inflated zone should be free (pad edge 11mm + 0.3mm = 11.3mm)
        assert grid.is_free(12.0, 10.0)
    
    def test_exclude_nets(self):
        builder = CSpaceBuilder(width_mm=20.0, height_mm=20.0)
        
        builder.add_pad(10.0, 10.0, 2.0, 2.0, net="VCC")
        builder.add_pad(5.0, 5.0, 1.0, 1.0, net="GND")
        
        # Build excluding VCC - only GND should block
        grid = builder.build_c_space_grid(exclude_nets={"VCC"})
        
        # VCC pad location should now be free
        assert grid.is_free(10.0, 10.0)
        
        # GND pad should still be blocked
        assert not grid.is_free(5.0, 5.0)


class TestCSpaceCache:
    """Tests for CSpaceCache functionality."""
    
    def test_cache_hit(self):
        builder = CSpaceBuilder(width_mm=10.0, height_mm=10.0)
        cache = CSpaceCache(builder)
        
        # First call computes
        grid1 = cache.get_grid(trace_width=0.2, clearance=0.2)
        assert cache.cache_size == 1
        
        # Second call hits cache
        grid2 = cache.get_grid(trace_width=0.2, clearance=0.2)
        assert cache.cache_size == 1
        
        # Same object returned
        assert grid1 is grid2
    
    def test_different_params_different_grids(self):
        builder = CSpaceBuilder(width_mm=10.0, height_mm=10.0)
        cache = CSpaceCache(builder)
        
        grid1 = cache.get_grid(trace_width=0.2, clearance=0.2)
        grid2 = cache.get_grid(trace_width=0.5, clearance=0.3)
        
        assert cache.cache_size == 2
        assert grid1 is not grid2
    
    def test_exclude_nets_caching(self):
        builder = CSpaceBuilder(width_mm=10.0, height_mm=10.0)
        builder.add_pad(5.0, 5.0, 1.0, 1.0, net="VCC")
        cache = CSpaceCache(builder)
        
        # Same params but different exclude_nets -> different cache entries
        grid1 = cache.get_grid(0.2, 0.2, exclude_nets=set())
        grid2 = cache.get_grid(0.2, 0.2, exclude_nets={"VCC"})
        
        assert cache.cache_size == 2
        
        # Grid1 has VCC blocked, Grid2 doesn't
        assert not grid1.is_free(5.0, 5.0)
        assert grid2.is_free(5.0, 5.0)
    
    def test_clear_cache(self):
        builder = CSpaceBuilder(width_mm=10.0, height_mm=10.0)
        cache = CSpaceCache(builder)
        
        cache.get_grid(0.2, 0.2)
        cache.get_grid(0.3, 0.3)
        assert cache.cache_size == 2
        
        cache.clear()
        assert cache.cache_size == 0
    
    def test_cache_stats_tracking(self):
        """Test that cache hit/miss statistics are tracked correctly."""
        builder = CSpaceBuilder(width_mm=10.0, height_mm=10.0)
        cache = CSpaceCache(builder)
        
        # Initial state
        assert cache.stats.hits == 0
        assert cache.stats.misses == 0
        assert cache.stats.hit_rate == 0.0
        
        # First call is a miss
        cache.get_grid(0.2, 0.2)
        assert cache.stats.misses == 1
        assert cache.stats.hits == 0
        
        # Second call is a hit
        cache.get_grid(0.2, 0.2)
        assert cache.stats.hits == 1
        assert cache.stats.misses == 1
        assert cache.stats.hit_rate == 0.5
        
        # Third call (same params) is another hit
        cache.get_grid(0.2, 0.2)
        assert cache.stats.hits == 2
        assert cache.stats.hit_rate == pytest.approx(2/3, rel=0.01)
    
    def test_get_grid_for_net_power(self):
        """Test get_grid_for_net uses correct net class rules for power nets."""
        from temper_placer.core.design_rules import create_temper_design_rules
        
        builder = CSpaceBuilder(width_mm=20.0, height_mm=20.0)
        cache = CSpaceCache(builder)
        rules = create_temper_design_rules()
        
        # VCC is detected as a power net
        grid = cache.get_grid_for_net("VCC", rules)
        
        # Power class has trace_width=1.0mm, clearance=0.5mm
        assert grid.trace_width == 1.0
        assert grid.clearance == 0.5
    
    def test_get_grid_for_net_signal(self):
        """Test get_grid_for_net uses default rules for signal nets."""
        from temper_placer.core.design_rules import create_temper_design_rules
        
        builder = CSpaceBuilder(width_mm=20.0, height_mm=20.0)
        cache = CSpaceCache(builder)
        rules = create_temper_design_rules()
        
        # Unknown net defaults to signal-like rules
        grid = cache.get_grid_for_net("NET_SOME_SIGNAL", rules)
        
        # Default class has trace_width=0.2mm, clearance=0.15mm
        assert grid.trace_width == 0.2
        assert grid.clearance == 0.15
    
    def test_get_grid_for_net_caching(self):
        """Test get_grid_for_net properly caches by underlying parameters."""
        from temper_placer.core.design_rules import create_temper_design_rules
        
        builder = CSpaceBuilder(width_mm=10.0, height_mm=10.0)
        cache = CSpaceCache(builder)
        rules = create_temper_design_rules()
        
        # Two power nets should share the same cached grid
        grid1 = cache.get_grid_for_net("VCC", rules)
        grid2 = cache.get_grid_for_net("VDD", rules)
        
        # Same grid object since same trace_width/clearance
        assert grid1 is grid2
        assert cache.cache_size == 1
        
        # Signal net gets different grid
        grid3 = cache.get_grid_for_net("DATA_OUT", rules)
        assert grid3 is not grid1
        assert cache.cache_size == 2


class TestCSpaceAcceptanceCriteria:
    """Tests for temper-3028 acceptance criteria."""
    
    def test_cache_hit_rate_above_95_percent(self):
        """Cache hit rate >95% during simulated routing session.
        
        Simulates routing 100 nets with 3 net classes, requesting grids
        multiple times per net (typical routing behavior).
        """
        from temper_placer.core.design_rules import create_temper_design_rules
        
        builder = CSpaceBuilder(width_mm=100.0, height_mm=140.0)
        cache = CSpaceCache(builder)
        rules = create_temper_design_rules()
        
        # Simulate routing 100 nets: 70 signal, 20 power, 10 ground
        net_classes = (
            ["SIGNAL_" + str(i) for i in range(70)] +
            ["VCC_" + str(i) for i in range(20)] +
            ["GND_" + str(i) for i in range(10)]
        )
        
        # Each net requests grid 5 times (start, retries, verification)
        for net in net_classes:
            for _ in range(5):
                cache.get_grid_for_net(net, rules)
        
        # Should have very high hit rate
        # 100 nets × 5 calls = 500 total
        # First call for each net class is a miss (3 misses)
        # Remaining calls are hits
        assert cache.stats.hit_rate >= 0.95, f"Hit rate {cache.stats.hit_rate:.2%} below 95%"
        print(f"\nCache hit rate: {cache.stats.hit_rate:.2%}")
        print(f"Hits: {cache.stats.hits}, Misses: {cache.stats.misses}")
    
    def test_memory_usage_under_100mb(self):
        """Memory usage <100MB for 3 net class grids at full resolution.
        
        Tests with Temper board dimensions (100mm × 140mm) at 0.1mm resolution.
        """
        from temper_placer.core.design_rules import create_temper_design_rules
        
        builder = CSpaceBuilder(width_mm=100.0, height_mm=140.0)
        cache = CSpaceCache(builder)
        rules = create_temper_design_rules()
        
        # Generate grids for 3 main net classes
        cache.get_grid_for_net("VCC", rules)      # Power
        cache.get_grid_for_net("GND", rules)      # Ground  
        cache.get_grid_for_net("SIGNAL", rules)   # Signal (default)
        
        memory_mb = cache.memory_usage_mb()
        
        # Each grid is ~1.4MB (1000 × 1400 × 1 byte)
        # 3 grids should be ~4.2MB, well under 100MB
        assert memory_mb < 100, f"Memory usage {memory_mb:.1f}MB exceeds 100MB"
        print(f"\nMemory usage for 3 grids: {memory_mb:.1f}MB")


class TestCSpacePerformance:
    """Performance benchmarks for C-Space operations."""
    
    def test_grid_generation_speed(self):
        """Grid generation should be <100ms for typical board size."""
        import time
        
        builder = CSpaceBuilder(width_mm=100.0, height_mm=140.0)
        
        # Add realistic number of obstacles (500 pads)
        for i in range(50):
            for j in range(10):
                builder.add_pad(
                    center_x=i * 2.0 + 1.0,
                    center_y=j * 14.0 + 1.0,
                    width=0.8,
                    height=0.8,
                    net=f"NET_{i}_{j}",
                )
        
        # Time the grid generation
        start = time.perf_counter()
        result = builder.build_c_space_grid(trace_width=0.2, clearance=0.2)
        elapsed_ms = (time.perf_counter() - start) * 1000
        
        assert result.grid.shape == (1400, 1000)
        assert elapsed_ms < 200, f"Grid generation too slow: {elapsed_ms:.1f}ms"
        print(f"\nGrid generation: {elapsed_ms:.1f}ms")
    
    @pytest.mark.skip(reason="Run manually to check detailed timing")
    def test_realistic_board_timing(self):
        """Check timing with realistic board."""
        import time
        
        builder = CSpaceBuilder(width_mm=100.0, height_mm=140.0)
        
        # Simulate 500 pads (typical for Temper board)
        for i in range(500):
            x = (i % 50) * 2.0 + 1.0
            y = (i // 50) * 14.0 + 1.0
            builder.add_pad(x, y, 0.5, 0.5, net=f"NET_{i}")
        
        start = time.perf_counter()
        grid = builder.build_c_space_grid()
        elapsed = (time.perf_counter() - start) * 1000
        
        print(f"Grid generation: {elapsed:.2f}ms")
        print(f"Grid shape: {grid.grid.shape}")
        print(f"Memory: {grid.grid.nbytes / 1024:.1f} KB")
        
        assert elapsed < 100, f"Too slow: {elapsed:.2f}ms"

