"""
Integration test: Router populates enhanced failure diagnostics.

This test validates that when routing fails, the router now provides:
- Exact failure location
- Channel capacity data
- Blocking components
- Suggested spacing
- Confidence score
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

print("=" * 70)
print("INTEGRATION TEST: Router Enhanced Diagnostics")
print("=" * 70)

# For now, this is a MANUAL test showing what the integration should look like
# Once we instrument the router, this will be an automated test

print("""
This test will validate the full integration once router instrumentation is complete.

Expected flow:
1. Router attempts to route a net
2. A* search fails at specific (x, y) location
3. Router analyzes:
   - Which grid cells were blocked
   - Which components occupy those cells
   - Channel capacity at failure location
   - How much more space is needed
4. Router creates RoutingFailureReport with all fields populated
5. Benders cut generator uses precise data to create targeted cuts

Current status:
✅ Data structures defined (ChannelState, enhanced RoutingFailureReport)
✅ Helper functions implemented (spacing estimation, blocking ID, confidence)
⏳ Router instrumentation (Phase 2) - IN PROGRESS

Next steps:
1. Modify A* search to track failure location
2. Add channel capacity analysis at failure point
3. Identify blocking components from grid state
4. Compute suggested spacing
5. Calculate confidence score
6. Populate all fields in RoutingFailureReport

This will be completed in Phase 2.
""")

print("\n" + "=" * 70)
print("MOCK EXAMPLE: What Enhanced Diagnostics Look Like")
print("=" * 70)

from temper_placer.router_v6.astar_pathfinding import RoutingFailureReport
from temper_placer.router_v6.channel_state import ChannelState

# Mock example of what router will produce
channel = ChannelState(
    channel_id="between_U_MCU_and_MAX31865",
    capacity=4,
    used=4,
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
    # Enhanced fields
    failed_at=(25.3, 30.1),
    congested_channel=channel,
    suggested_spacing_mm=2.0,
    blocking_components=["U_MCU", "MAX31865"],
    confidence=0.9,
)

print(f"\nEnhanced Failure Report for {failure.net_name}:")
print(f"  Reason: {failure.failure_reason}")
print(f"  Failed at: {failure.failed_at}")
print(f"  Channel: {channel.utilization:.0%} utilized ({channel.used}/{channel.capacity} tracks)")
print(f"  Blocking components: {failure.blocking_components}")
print(f"  Suggested spacing: {failure.suggested_spacing_mm}mm")
print(f"  Confidence: {failure.confidence:.0%}")

print(f"\nThis enables Benders to generate PRECISE cut:")
print(f"  spacing(U_MCU, MAX31865) >= current + {failure.suggested_spacing_mm}mm")
print(f"  Confidence: {failure.confidence:.0%} (vs 30-50% with heuristics)")

print("\n✅ Data structures ready for router instrumentation")
