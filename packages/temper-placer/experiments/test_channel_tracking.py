"""
Test: Channel capacity tracking during routing.

TDD approach - write tests first, then implement features.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

print("=" * 70)
print("TEST: Channel Capacity Tracking")
print("=" * 70)

# Test 1: ChannelState data structure exists
print("\n[Test 1] ChannelState data structure")
try:
    from temper_placer.router_v6.channel_state import ChannelState
    
    channel = ChannelState(
        channel_id="ch_001",
        capacity=4,
        used=2,
        nets_using=["SPI_CLK", "SPI_MOSI"],
        bounding_components=("U_MCU", "MAX31865"),
        position=(25.0, 30.0),
        width_mm=2.5,
    )
    
    assert channel.capacity == 4
    assert channel.used == 2
    assert channel.available == 2  # Property: capacity - used
    assert channel.utilization == 0.5  # Property: used / capacity
    
    print(f"✅ ChannelState created: {channel}")
    print(f"   Available: {channel.available}, Utilization: {channel.utilization:.0%}")
    
except ImportError as e:
    print(f"❌ FAIL: ChannelState not implemented yet")
    print(f"   Expected: temper_placer.router_v6.channel_state.ChannelState")
except AssertionError as e:
    print(f"❌ FAIL: ChannelState properties incorrect: {e}")
except Exception as e:
    print(f"❌ FAIL: {e}")

# Test 2: Enhanced RoutingFailureReport
print("\n[Test 2] Enhanced RoutingFailureReport")
try:
    from temper_placer.router_v6.astar_pathfinding import RoutingFailureReport
    from temper_placer.router_v6.channel_state import ChannelState
    
    channel = ChannelState(
        channel_id="ch_001",
        capacity=4,
        used=4,  # Full!
        nets_using=["SPI_CLK", "SPI_MOSI", "SPI_MISO", "GND"],
        bounding_components=("U_MCU", "MAX31865"),
        position=(25.0, 30.0),
        width_mm=2.5,
    )
    
    failure = RoutingFailureReport(
        net_name="I_SENSE",
        failure_reason="channel_capacity_exceeded",
        blocking_nets=["SPI_CLK", "SPI_MOSI"],
        attempted_ripups=5,
        congestion_region=(25.0, 30.0),
        pin_count=8,
        # NEW fields
        failed_at=(25.3, 30.1),
        congested_channel=channel,
        suggested_spacing_mm=2.0,
        blocking_components=["U_MCU", "MAX31865"],
        confidence=0.9,
    )
    
    assert failure.failed_at == (25.3, 30.1)
    assert failure.congested_channel.utilization == 1.0  # 100% full
    assert failure.suggested_spacing_mm == 2.0
    assert failure.confidence == 0.9
    assert "U_MCU" in failure.blocking_components
    
    print(f"✅ Enhanced RoutingFailureReport created")
    print(f"   Failed at: {failure.failed_at}")
    print(f"   Channel: {failure.congested_channel.utilization:.0%} utilized")
    print(f"   Suggested spacing: {failure.suggested_spacing_mm}mm")
    print(f"   Confidence: {failure.confidence:.0%}")
    
except ImportError as e:
    print(f"❌ FAIL: Enhanced fields not implemented yet")
except TypeError as e:
    print(f"❌ FAIL: RoutingFailureReport doesn't accept new fields: {e}")
except Exception as e:
    print(f"❌ FAIL: {e}")

# Test 3: Spacing estimation function
print("\n[Test 3] Spacing estimation from channel capacity")
try:
    from temper_placer.router_v6.channel_state import estimate_required_spacing
    
    # Scenario: Channel has capacity 4, used 4, need 1 more
    # With 0.2mm trace + 0.2mm clearance = 0.4mm pitch
    # Need 1 more track = 0.4mm * 1.5 (margin) = 0.6mm
    
    spacing = estimate_required_spacing(
        tracks_needed=5,
        tracks_available=4,
        trace_width_mm=0.2,
        clearance_mm=0.2,
    )
    
    expected = 0.6  # (5-4) * (0.2+0.2) * 1.5
    assert abs(spacing - expected) < 0.01, f"Expected {expected}, got {spacing}"
    
    print(f"✅ Spacing estimation working")
    print(f"   Need 5 tracks, have 4 → add {spacing:.2f}mm")
    
except ImportError:
    print(f"❌ FAIL: estimate_required_spacing not implemented yet")
except AssertionError as e:
    print(f"❌ FAIL: Spacing calculation incorrect: {e}")
except Exception as e:
    print(f"❌ FAIL: {e}")

# Test 4: Blocking component identification
print("\n[Test 4] Blocking component identification")
try:
    from temper_placer.router_v6.channel_state import identify_blocking_components
    
    # Mock scenario: A* failed at (25.3, 30.1)
    # Grid cells at that location are occupied by U_MCU and MAX31865 pads
    
    occupied_cells = {
        (253, 301): "U_MCU.5",      # Grid coordinates (x*10, y*10)
        (254, 301): "MAX31865.1",
    }
    
    failure_grid_pos = (253, 301)
    
    blocking = identify_blocking_components(
        failure_grid_pos=failure_grid_pos,
        occupied_cells=occupied_cells,
        search_radius=2,  # Check 2 cells around failure point
    )
    
    assert "U_MCU" in blocking
    assert "MAX31865" in blocking
    
    print(f"✅ Blocking component identification working")
    print(f"   Found blockers: {blocking}")
    
except ImportError:
    print(f"❌ FAIL: identify_blocking_components not implemented yet")
except AssertionError as e:
    print(f"❌ FAIL: Blocking identification incorrect: {e}")
except Exception as e:
    print(f"❌ FAIL: {e}")

# Test 5: Confidence scoring
print("\n[Test 5] Confidence scoring")
try:
    from temper_placer.router_v6.channel_state import compute_failure_confidence
    
    # High confidence: Channel at 100%, clear blockers, exact location
    confidence_high = compute_failure_confidence(
        channel_utilization=1.0,
        blocking_components_count=2,
        has_exact_location=True,
        has_channel_data=True,
    )
    
    # Low confidence: Channel unknown, no blockers
    confidence_low = compute_failure_confidence(
        channel_utilization=None,
        blocking_components_count=0,
        has_exact_location=False,
        has_channel_data=False,
    )
    
    assert confidence_high > 0.8, f"High confidence should be >0.8, got {confidence_high}"
    assert confidence_low < 0.3, f"Low confidence should be <0.3, got {confidence_low}"
    
    print(f"✅ Confidence scoring working")
    print(f"   High confidence: {confidence_high:.0%}")
    print(f"   Low confidence: {confidence_low:.0%}")
    
except ImportError:
    print(f"❌ FAIL: compute_failure_confidence not implemented yet")
except AssertionError as e:
    print(f"❌ FAIL: Confidence scoring incorrect: {e}")
except Exception as e:
    print(f"❌ FAIL: {e}")

print("\n" + "=" * 70)
print("TEST SUMMARY")
print("=" * 70)
print("""
Expected failures at this stage (TDD - tests written first):
- All tests should fail with ImportError or TypeError
- This defines the API we need to implement

Next steps:
1. Implement ChannelState dataclass
2. Add new fields to RoutingFailureReport
3. Implement helper functions
4. Re-run tests until all pass
""")
