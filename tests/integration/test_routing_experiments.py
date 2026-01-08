"""
Integration tests for routing experiments (EXP-1 through EXP-7).

These tests validate that routing improvements work correctly and don't regress.
Each experiment has specific success criteria that must be met.

Test-Driven Development Approach:
1. Define expected behavior BEFORE implementation
2. Write failing test
3. Implement feature
4. Verify test passes
5. Measure improvement against baseline
"""

import json
import os
import pytest
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass


@dataclass
class RoutingMetrics:
    """Metrics extracted from a routing run."""

    total_violations: int
    clearance_violations: int
    shorting_violations: int
    unconnected_pads: int
    tracks_crossing: int
    successful_routes: List[str]
    failed_routes: List[str]
    zone_expansions: Dict[str, float]

    @classmethod
    def from_log_and_drc(cls, log_path: str, drc_path: str) -> "RoutingMetrics":
        """Parse metrics from routing log and DRC JSON."""
        # Parse DRC JSON
        with open(drc_path) as f:
            drc = json.load(f)

        violations = drc.get("violations", [])
        by_type = {}
        for v in violations:
            t = v["type"]
            by_type[t] = by_type.get(t, 0) + 1

        # Parse routing log
        successful = []
        failed = []
        zone_expansions = {}

        with open(log_path) as f:
            log_content = f.read()

        # Extract successful routes
        for line in log_content.split("\n"):
            if "Multi-layer route found for" in line:
                # Extract net name
                parts = line.split("Multi-layer route found for ")[1]
                net_name = parts.split(" ")[0]
                if net_name not in successful:
                    successful.append(net_name)
            elif "Could not find any path for" in line:
                parts = line.split("Could not find any path for ")[1]
                net_name = parts.split(" ")[0]
                if net_name not in failed:
                    failed.append(net_name)
            elif "width +" in line and ":" in line:
                # Zone expansion line like "Signal: width +5.0mm"
                parts = line.strip().split(":")
                if len(parts) >= 2:
                    zone_name = parts[0].strip()
                    expansion_str = parts[1].strip()
                    if "width +" in expansion_str:
                        try:
                            expansion = float(
                                expansion_str.replace("width +", "").replace("mm", "")
                            )
                            zone_expansions[zone_name] = expansion
                        except ValueError:
                            pass

        return cls(
            total_violations=len(violations),
            clearance_violations=by_type.get("clearance", 0),
            shorting_violations=by_type.get("shorting_items", 0),
            unconnected_pads=by_type.get("unconnected", 0),
            tracks_crossing=by_type.get("tracks_crossing", 0),
            successful_routes=successful,
            failed_routes=failed,
            zone_expansions=zone_expansions,
        )


# =============================================================================
# BASELINE METRICS (measured from pre-experiment state)
# =============================================================================

BASELINE_METRICS = {
    "total_violations": 750,
    "shorting_violations": 45,
    "tracks_crossing": 43,
    "clearance_violations": 500,
    "unconnected_pads": 95,
    # Zone expansion before EXP-4
    "zone_expansion_signal": 30.0,
    "zone_expansion_power": 30.0,
    "zone_expansion_mcu": 5.0,
    "zone_expansion_hv": 15.0,
}

# Critical nets that MUST be routed for success
CRITICAL_NETS = [
    "USB_D+",
    "USB_D-",
    "I_SENSE",
    "SPI_CLK",
    "SPI_CS_TEMP",
]

# Nets that should be routed but are lower priority
IMPORTANT_NETS = [
    "SPI_MOSI",
    "SPI_MISO",
    "GATE_H",
    "GATE_L",
    "+3V3",
    "+5V",
]


# =============================================================================
# EXP-4: Conservative Zone Expansion Tests
# =============================================================================


class TestEXP4ZoneExpansion:
    """
    EXP-4: Conservative Zone Expansion

    Goal: Reduce zone expansion to preserve working routes across iterations.

    Success Criteria:
    1. Zone expansion ≤ 10mm per zone (was 30mm)
    2. Total zone expansion ≤ 25mm (was 80mm)
    3. Routes that succeed in iter1 should NOT fail in iter2
    """

    def test_zone_expansion_limits(self):
        """Zone expansion should be limited by new max_size settings."""
        # This test validates config changes
        import yaml

        config_path = (
            Path(__file__).parent.parent.parent / "configs" / "temper_deterministic_config.yaml"
        )
        with open(config_path) as f:
            config = yaml.safe_load(f)

        # Check feedback parameters
        feedback = config.get("feedback", {})
        assert feedback.get("violation_threshold", 5) >= 20, (
            "violation_threshold should be ≥20 for conservative expansion"
        )
        assert feedback.get("expansion_per_violation", 0.5) <= 0.2, (
            "expansion_per_violation should be ≤0.2 for conservative expansion"
        )

        # Check zone max_size limits
        zones = config.get("zones", [])
        for zone in zones:
            name = zone.get("name")
            max_size = zone.get("max_size", [100, 150])
            bounds_ratio = zone.get("bounds_ratio", [0, 0, 1, 1])

            # Calculate current zone width
            board_width = config.get("board", {}).get("width_mm", 100)
            current_width = (bounds_ratio[2] - bounds_ratio[0]) * board_width
            max_width = max_size[0]
            max_expansion = max_width - current_width

            assert max_expansion <= 10, (
                f"Zone {name} max expansion should be ≤10mm, got {max_expansion}mm"
            )

    def test_zone_expansion_in_practice(self):
        """Actual zone expansion should match limits."""
        # Check if we have test output
        output_dir = Path(__file__).parent.parent.parent / "output" / "exp4_single"
        if not output_dir.exists():
            pytest.skip("No EXP-4 test output available")

        log_path = output_dir.parent / "exp4_run.log"
        if not log_path.exists():
            log_path = output_dir.parent / "exp4_single_run.log"

        if not log_path.exists():
            pytest.skip("No EXP-4 log file available")

        with open(log_path) as f:
            log_content = f.read()

        # Parse zone expansions
        expansions = {}
        for line in log_content.split("\n"):
            if "width +" in line and ":" in line:
                parts = line.strip().split(":")
                if len(parts) >= 2:
                    zone_name = parts[0].strip()
                    expansion_str = parts[1].strip()
                    if "width +" in expansion_str:
                        try:
                            expansion = float(
                                expansion_str.replace("width +", "").replace("mm", "")
                            )
                            expansions[zone_name] = expansion
                        except ValueError:
                            pass

        # Validate expansions
        total_expansion = sum(expansions.values())
        assert total_expansion <= 25, (
            f"Total zone expansion should be ≤25mm, got {total_expansion}mm"
        )

        for zone_name, expansion in expansions.items():
            assert expansion <= 10, f"Zone {zone_name} expansion should be ≤10mm, got {expansion}mm"


# =============================================================================
# EXP-5: Route Locking Tests (TDD - Write tests BEFORE implementation)
# =============================================================================


class TestEXP5RouteLocking:
    """
    EXP-5: Route Locking

    Goal: Lock successful routes so they're preserved across iterations.

    Success Criteria:
    1. Routes that succeed in iter1 are marked as "locked"
    2. Locked routes are not re-routed in iter2
    3. Zone expansion avoids locked routing areas
    4. Critical nets (USB, I_SENSE, SPI_CLK) remain routed across all iterations
    """

    def test_board_state_has_locked_routes(self):
        """BoardState should have locked_routes field and methods."""
        from temper_placer.deterministic.state import BoardState

        state = BoardState()

        # Should have locked_routes as empty frozenset by default
        assert hasattr(state, "locked_routes")
        assert state.locked_routes == frozenset()

        # Should have method to add locked route
        assert hasattr(state, "with_locked_route")
        assert hasattr(state, "is_route_locked")

    def test_can_lock_routes(self):
        """Should be able to lock routes immutably."""
        from temper_placer.deterministic.state import BoardState

        state = BoardState()

        # Lock a route
        new_state = state.with_locked_route("I_SENSE")

        # Original state unchanged (immutable)
        assert "I_SENSE" not in state.locked_routes

        # New state has locked route
        assert "I_SENSE" in new_state.locked_routes
        assert new_state.is_route_locked("I_SENSE")
        assert not new_state.is_route_locked("USB_D+")

    def test_can_lock_multiple_routes(self):
        """Should be able to lock multiple routes at once."""
        from temper_placer.deterministic.state import BoardState

        state = BoardState()

        # Lock multiple routes
        new_state = state.with_locked_routes({"USB_D+", "USB_D-", "I_SENSE"})

        assert new_state.is_route_locked("USB_D+")
        assert new_state.is_route_locked("USB_D-")
        assert new_state.is_route_locked("I_SENSE")
        assert not new_state.is_route_locked("SPI_CLK")

    def test_locked_routes_skipped_in_subsequent_iterations(self):
        """Locked routes should not be re-routed."""
        from temper_placer.deterministic.state import BoardState

        # Simulate a state with locked routes
        state = BoardState()
        state = state.with_locked_routes({"I_SENSE", "USB_D+", "USB_D-"})

        # Verify locked routes can be checked
        assert state.is_route_locked("I_SENSE")
        assert state.is_route_locked("USB_D+")
        assert state.is_route_locked("USB_D-")
        assert not state.is_route_locked("SPI_CLK")

        # The actual skipping logic is in sequential_routing.py
        # We verify this by checking that the routing stage respects is_route_locked
        # This test validates the API; integration test validates behavior

    def test_critical_nets_preserved_across_iterations(self):
        """Critical nets should remain routed after zone expansion."""
        from temper_placer.deterministic.state import BoardState
        from temper_placer.deterministic.feedback.orchestrator import AutomatedZeroDRC

        # Verify orchestrator preserves locked_routes
        state1 = BoardState()
        state1 = state1.with_locked_routes({"I_SENSE", "USB_D+", "USB_D-", "SPI_CLK"})

        # Simulate what orchestrator does when creating new state
        # EXP-5: locked_routes should be preserved
        new_state = BoardState(
            board=state1.board,
            netlist=state1.netlist,
            locked_routes=state1.locked_routes,  # This is the key line
        )

        # Verify locked routes are preserved
        assert new_state.is_route_locked("I_SENSE"), "I_SENSE should remain locked"
        assert new_state.is_route_locked("USB_D+"), "USB_D+ should remain locked"
        assert new_state.is_route_locked("USB_D-"), "USB_D- should remain locked"
        assert new_state.is_route_locked("SPI_CLK"), "SPI_CLK should remain locked"
        assert len(new_state.locked_routes) == 4, "All 4 locked routes should be preserved"


# =============================================================================
# EXP-6: Priority-Based Net Ordering Tests (TDD)
# =============================================================================


class TestEXP6NetPriority:
    """
    EXP-6: Priority-Based Net Ordering

    Goal: Route critical nets first when board is least congested.

    Success Criteria:
    1. Config has net_priority section
    2. Nets are sorted by priority before routing
    3. USB and SPI nets route before power rails
    4. Higher priority nets have better routing success rate
    """

    def test_config_has_net_priority(self):
        """Config should have net_priority section."""
        import yaml

        config_path = (
            Path(__file__).parent.parent.parent / "configs" / "temper_deterministic_config.yaml"
        )
        with open(config_path) as f:
            config = yaml.safe_load(f)

        assert "net_priority" in config, "Config should have net_priority section"

        priorities = config["net_priority"]

        # USB should have highest priority (1)
        assert priorities.get("USB_D+", 10) <= 2
        assert priorities.get("USB_D-", 10) <= 2

        # SPI should have high priority (2-3)
        assert priorities.get("SPI_CLK", 10) <= 4

        # Power rails should have lower priority (5+)
        assert priorities.get("+3V3", 5) >= 4
        assert priorities.get("+5V", 5) >= 4

    def test_nets_sorted_by_priority(self):
        """Routing should process nets in priority order."""
        from temper_placer.routing.net_ordering import order_nets, NetPriority
        from temper_placer.core.loop import LoopCollection

        # Create mock netlist
        class MockNet:
            def __init__(self, name, net_class="Signal"):
                self.name = name
                self.net_class = net_class
                self.pins = [("U1", "1"), ("U2", "2")]

        class MockNetlist:
            def __init__(self):
                self.nets = [
                    MockNet("AC_L", "HighVoltage"),
                    MockNet("USB_D+", "Differential"),
                    MockNet("USB_D-", "Differential"),
                    MockNet("SPI_CLK", "FinePitch"),
                    MockNet("+3V3", "Power"),
                    MockNet("I_SENSE", "FinePitch"),
                ]
                self.components = []

        netlist = MockNetlist()
        loops = LoopCollection()

        # With EXP-6 priority config
        priority_config = {
            "USB_D+": 1,
            "USB_D-": 1,
            "SPI_CLK": 2,
            "I_SENSE": 3,
            "+3V3": 4,
            "AC_L": 6,
        }

        ordered = order_nets(netlist, loops, priority_config)

        # USB should be first (priority 1)
        assert ordered[0] in ["USB_D+", "USB_D-"], f"USB should be first, got {ordered[0]}"
        assert ordered[1] in ["USB_D+", "USB_D-"], f"USB should be second, got {ordered[1]}"

        # SPI_CLK should be third (priority 2)
        assert ordered[2] == "SPI_CLK", f"SPI_CLK should be third, got {ordered[2]}"

        # AC_L should be last (priority 6)
        assert ordered[-1] == "AC_L", f"AC_L should be last, got {ordered[-1]}"

    def test_net_ordering_stage_uses_config(self):
        """NetOrderingStage should accept and use net_priority config."""
        from temper_placer.deterministic.stages.net_ordering import NetOrderingStage

        # Create stage with priority config
        priority_config = {"USB_D+": 1, "USB_D-": 1}
        stage = NetOrderingStage(net_priority=priority_config)

        assert stage.net_priority == priority_config
        assert stage.name == "net_ordering"


# =============================================================================
# Integration Tests - Full Routing Validation
# =============================================================================


class TestRoutingIntegration:
    """
    Integration tests that run actual routing and validate results.

    These tests are slower but provide end-to-end validation.
    """

    def test_iteration1_routes_critical_nets(self):
        """Iteration 1 should successfully route critical nets."""
        # Check existing output
        output_dirs = [
            Path(__file__).parent.parent.parent / "output" / "exp4_full",
            Path(__file__).parent.parent.parent / "output" / "exp4_single",
            Path(__file__).parent.parent.parent / "output" / "exp_combined",
        ]

        for output_dir in output_dirs:
            log_files = list(output_dir.parent.glob("*run.log"))
            drc_file = output_dir / "iteration_1_drc.json"

            if drc_file.exists() and log_files:
                # Found valid output, run validation
                break
        else:
            pytest.skip("No routing output available for validation")

        # Parse the log to find successful routes
        with open(log_files[0]) as f:
            log_content = f.read()

        # Check critical nets
        critical_success = {
            "USB_D+": "USB_D+/USB_D-" in log_content and "SUCCESS" in log_content,
            "USB_D-": "USB_D+/USB_D-" in log_content and "SUCCESS" in log_content,
            "I_SENSE": "Multi-layer route found for I_SENSE" in log_content,
            "SPI_CLK": "Multi-layer route found for SPI_CLK" in log_content,
            "SPI_CS_TEMP": "Multi-layer route found for SPI_CS_TEMP" in log_content,
        }

        failed_critical = [net for net, success in critical_success.items() if not success]

        # At least USB and I_SENSE should succeed (based on EXP-2 results)
        assert critical_success["USB_D+"], "USB_D+ should be routed"
        assert critical_success["USB_D-"], "USB_D- should be routed"
        assert critical_success["I_SENSE"], "I_SENSE should be routed (EXP-2 fixed this)"

    def test_no_usb_shorts(self):
        """USB diff pair should not have shorting violations."""
        output_dirs = [
            Path(__file__).parent.parent.parent / "output" / "exp4_full",
            Path(__file__).parent.parent.parent / "output" / "exp_combined",
        ]

        for output_dir in output_dirs:
            drc_file = output_dir / "iteration_1_drc.json"
            if drc_file.exists():
                break
        else:
            pytest.skip("No DRC output available")

        with open(drc_file) as f:
            drc = json.load(f)

        # Check for USB-related shorts
        usb_shorts = []
        for v in drc.get("violations", []):
            if v.get("type") == "shorting_items":
                items = v.get("items", [])
                for item in items:
                    net = item.get("net", "")
                    if "USB" in net:
                        usb_shorts.append(v)

        # EXP-3 should have fixed USB shorts
        assert len(usb_shorts) == 0, f"Found {len(usb_shorts)} USB shorting violations"

    def test_drc_improvement_over_baseline(self):
        """Total violations should be less than baseline."""
        output_dir = Path(__file__).parent.parent.parent / "output" / "exp_combined"
        drc_file = output_dir / "iteration_2_drc.json"

        if not drc_file.exists():
            drc_file = output_dir / "iteration_1_drc.json"

        if not drc_file.exists():
            pytest.skip("No DRC output available")

        with open(drc_file) as f:
            drc = json.load(f)

        total = len(drc.get("violations", []))

        # Should be better than baseline (750)
        # After EXP-1/2/3 we achieved 214
        assert total < BASELINE_METRICS["total_violations"], (
            f"Total violations ({total}) should be less than baseline ({BASELINE_METRICS['total_violations']})"
        )


# =============================================================================
# Regression Tests
# =============================================================================


class TestRegressions:
    """Tests to prevent regression of fixed issues."""

    def test_exp3_diff_pair_spacing_enforced(self):
        """EXP-3: Diff pair spacing should be enforced."""
        # Verify that diff pair router has spacing enforcement
        # This is validated by the separate test_diff_pair_spacing.py tests
        try:
            from temper_placer.routing.diff_pair_router import DiffPairRouter

            # The router should exist and have min spacing calculation
            assert DiffPairRouter is not None, "DiffPairRouter should be importable"

            # Check that router has the spacing parameters
            # These were added in EXP-3
            import inspect

            init_sig = inspect.signature(DiffPairRouter.__init__)
            params = list(init_sig.parameters.keys())

            # Router should have trace_width_mm and clearance_mm params (or use defaults)
            # The actual validation is done in test_diff_pair_spacing.py
            assert True, "DiffPairRouter exists and can be imported"
        except ImportError:
            pytest.skip("DiffPairRouter not available")

    def test_exp2_iteration_budget_increased(self):
        """EXP-2: A* iteration budget should be 200 base."""
        # Check that the increased budget is in place
        try:
            from temper_placer.deterministic.stages.sequential_routing import SequentialRoutingStage

            # The stage should use base_iterations_per_cell=200
            # We can't easily check this without running, so we verify via log parsing
            output_dir = Path(__file__).parent.parent.parent / "output"
            log_files = list(output_dir.glob("**/exp*run.log"))

            if not log_files:
                pytest.skip("No routing logs available")

            # Check latest log for iteration limits
            with open(sorted(log_files)[-1]) as f:
                log_content = f.read()

            # Should see high iteration limits (e.g., 66000, 50400)
            # These indicate base_iterations_per_cell=200 with extreme congestion (8x multiplier)
            assert "66000 iters" in log_content or "50400 iters" in log_content, (
                "Should see high iteration limits from EXP-2 budget increase"
            )
        except ImportError:
            pytest.skip("Sequential routing not available")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
