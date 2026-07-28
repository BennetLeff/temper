"""U1 -- structured decline-reason contract (docs/plans/2026-07-28-001-*).

Covers R1/R3/R4/R10: every net the router declines must carry a
machine-readable reason naming the specific rule the system could not
discharge, or -- when no specific rule can be named -- an honest
``attribution_gap=True`` rather than a fabricated rule id. Follows the
UNSAT-core "because"-field candor pattern:
docs/solutions/architecture-patterns/two-tier-acceptance-gate-unsat-surfacing-2026-07-05.md
"""

from __future__ import annotations

from unittest import mock

import numpy as np
import pytest

from temper_placer.router_v6._astar_reconstruct import (
    FAILURE_REASON_PROVER_ERROR,
    RULE_ID_FORCED_SEGMENT_FAIL_CLOSED,
    RoutingFailureReport,
    run_astar_pathfinding,
)
from temper_placer.router_v6.channel_mapping import ChannelMapping, ChannelPath
from temper_placer.router_v6.net_classification import classify_net_type
from temper_placer.router_v6.occupancy_grid import OccupancyGrid
from temper_placer.router_v6.stage0_data import DesignRules, NetClassRules


def _walled_grid() -> OccupancyGrid:
    """A 30x30 grid with a full-height wall at column 15 -- no legal path."""
    grid = OccupancyGrid("F.Cu", np.zeros((30, 30), dtype=np.int8), (0, 0), 1.0, 30, 30)
    grid.grid[:, 15] = 1
    return grid


class TestForcedSegmentFailClosedAttribution:
    """Happy path: the one mechanism this module names as a specific rule."""

    def test_blocked_net_names_forced_segment_rule(self):
        grid = _walled_grid()
        channel_path = ChannelPath(
            net_name="SIGNAL_NET",
            channel_sequence=["ch_0"],
            waypoints=[(0.0, 0.0), (29.0, 0.0)],
            total_length=29.0,
            preferred_layer="F.Cu",
        )

        result = run_astar_pathfinding(
            ChannelMapping({"SIGNAL_NET": channel_path}),
            grid,
            design_rules=DesignRules(),
            max_iter=10_000,
        )

        assert "SIGNAL_NET" in result.failed_nets
        report = result.failure_reports["SIGNAL_NET"]
        assert report.rule_id == RULE_ID_FORCED_SEGMENT_FAIL_CLOSED, (
            "A net blocked by the forced-segment fail-closed gate must name "
            "that specific mechanism, not attribution_gap"
        )
        assert report.attribution_gap is False
        assert report.domain == classify_net_type("SIGNAL_NET")

    def test_hv_domain_net_blocked_by_gate_still_names_mechanism(self):
        """An HV-*class* net (not HV-*named*) still gets the same specific
        attribution -- no net class is exempt from the fail-closed gate,
        and the rule attribution doesn't depend on the net's class."""
        grid = _walled_grid()
        design_rules = DesignRules()
        design_rules.net_classes["HighVoltage"] = NetClassRules(
            name="HighVoltage",
            clearance_mm=6.0,
            trace_width_mm=3.0,
            via_diameter_mm=1.2,
            via_drill_mm=0.6,
            safety_category="HV",
        )
        design_rules.net_class_assignments["ISO_FB_HIGH"] = "HighVoltage"

        channel_path = ChannelPath(
            net_name="ISO_FB_HIGH",
            channel_sequence=["ch_0"],
            waypoints=[(0.0, 0.0), (29.0, 0.0)],
            total_length=29.0,
            preferred_layer="F.Cu",
        )

        result = run_astar_pathfinding(
            ChannelMapping({"ISO_FB_HIGH": channel_path}),
            grid,
            design_rules=design_rules,
            max_iter=10_000,
        )

        report = result.failure_reports["ISO_FB_HIGH"]
        assert report.rule_id == RULE_ID_FORCED_SEGMENT_FAIL_CLOSED
        assert report.attribution_gap is False
        # domain is sourced from net_classification's name-pattern helpers
        # (per U1's explicit constraint), not from design_rules'
        # class-level safety_category -- "ISO_FB_HIGH" doesn't match any
        # HV name pattern, so domain is honestly "signal", not a fabricated
        # "hv" inferred from the netclass assignment.
        assert report.domain == "signal"


class TestGenuineAttributionGap:
    """Edge case: a failure with no identifiable specific rule."""

    def test_insufficient_waypoints_is_an_honest_gap_not_a_fabricated_rule(self):
        """A channel path with fewer than two waypoints can't even enter
        A* search (_astar_route/_astar_route_multilayer's early-return
        guard) -- this is a channel-topology anomaly, not a rule the
        system evaluated and failed to discharge. It must be reported as
        attribution_gap=True, never assigned a plausible-sounding rule_id.
        """
        grid = _walled_grid()
        channel_path = ChannelPath(
            net_name="ORPHAN_NET",
            channel_sequence=["ch_0"],
            waypoints=[(0.0, 0.0)],  # single waypoint: no segment to search
            total_length=0.0,
            preferred_layer="F.Cu",
        )

        result = run_astar_pathfinding(
            ChannelMapping({"ORPHAN_NET": channel_path}),
            grid,
            design_rules=DesignRules(),
            max_iter=10_000,
        )

        assert "ORPHAN_NET" in result.failed_nets
        report = result.failure_reports["ORPHAN_NET"]
        assert report.rule_id is None, (
            "No specific rule was evaluated for this net -- naming one "
            "would be fabrication"
        )
        assert report.attribution_gap is True
        assert report.domain == classify_net_type("ORPHAN_NET")

    def test_rip_up_budget_exhaustion_is_an_honest_gap(self):
        """Rip-up budget exhaustion is a known, specific *mechanism*
        (``run_astar_pathfinding``'s leftover-``reroute_queue`` handling
        calls ``record_failure(net_name, "rip_up_limit", [], None)`` with
        no rule_id/attribution_gap override), but it's a routing-algorithm
        resource limit, not a safety rule the system failed to discharge.
        Pin that ``record_failure``'s actual call shape for this reason
        produces an honest gap, not a fabricated rule_id.
        """
        pinned = RoutingFailureReport(
            net_name="STUCK_NET",
            failure_reason="rip_up_limit",
            blocking_nets=[],
            attempted_ripups=2,
            congestion_region=None,
        )
        assert pinned.rule_id is None
        assert pinned.attribution_gap is True


class TestProverErrorFailsClosedHonestly:
    """Error path: an internal exception during a discharge attempt."""

    def test_exception_during_attempt_route_declines_fail_closed(self):
        grid = _walled_grid()
        channel_path = ChannelPath(
            net_name="CRASHY_NET",
            channel_sequence=["ch_0"],
            waypoints=[(0.0, 0.0), (29.0, 0.0)],
            total_length=29.0,
            preferred_layer="F.Cu",
        )

        with mock.patch(
            "temper_placer.router_v6._astar_reconstruct._astar_route_with_ripup",
            side_effect=RuntimeError("simulated internal failure"),
        ):
            result = run_astar_pathfinding(
                ChannelMapping({"CRASHY_NET": channel_path}),
                grid,
                design_rules=DesignRules(),
                max_iter=10_000,
            )

        assert "CRASHY_NET" not in result.routed_paths, (
            "An exception during discharge must never be read as proven-safe"
        )
        assert "CRASHY_NET" in result.failed_nets, (
            "An exception during discharge must decline the net, never "
            "silently drop it"
        )
        report = result.failure_reports["CRASHY_NET"]
        assert report.failure_reason == FAILURE_REASON_PROVER_ERROR
        assert report.rule_id is None, (
            "An internal exception doesn't tell us which safety rule (if "
            "any) would have failed -- naming one would be fabrication"
        )
        assert report.attribution_gap is True


class TestRuleIdAttributionGapConsistency:
    """attribution_gap is a computed property (``rule_id is None``), not a
    separately-threaded field -- the rule_id/attribution_gap contradiction
    the earlier __post_init__ validation rejected at runtime is now
    structurally impossible: there is no ``attribution_gap`` constructor
    parameter at all, so no call site can pass a value that disagrees with
    ``rule_id``."""

    def test_attribution_gap_is_not_a_constructor_parameter(self):
        """The consistency invariant is enforced by construction, not by a
        runtime check -- passing attribution_gap explicitly is a TypeError,
        not a value that could silently disagree with rule_id."""
        with pytest.raises(TypeError, match="attribution_gap"):
            RoutingFailureReport(
                net_name="X",
                failure_reason="no_path",
                blocking_nets=[],
                attempted_ripups=0,
                congestion_region=None,
                rule_id=RULE_ID_FORCED_SEGMENT_FAIL_CLOSED,
                attribution_gap=True,  # type: ignore[call-arg]
            )

    def test_default_construction_is_the_honest_gap_state(self):
        """A caller that forgets to set rule_id entirely still gets a valid,
        honest report -- never a silent implicit rule claim."""
        report = RoutingFailureReport(
            net_name="X",
            failure_reason="congestion",
            blocking_nets=[],
            attempted_ripups=0,
            congestion_region=None,
        )
        assert report.rule_id is None
        assert report.attribution_gap is True

    def test_named_rule_derives_attribution_gap_false(self):
        report = RoutingFailureReport(
            net_name="X",
            failure_reason="no_path",
            blocking_nets=[],
            attempted_ripups=0,
            congestion_region=None,
            rule_id=RULE_ID_FORCED_SEGMENT_FAIL_CLOSED,
        )
        assert report.rule_id == RULE_ID_FORCED_SEGMENT_FAIL_CLOSED
        assert report.attribution_gap is False


class TestFullRunNoUnattributedDeclines:
    """Integration: every declined net in a real run carries a non-empty,
    non-fabricated reason -- either a specific rule_id or an explicit
    attribution_gap, never a blank."""

    def test_every_failure_report_has_a_consistent_attribution(self):
        grid = _walled_grid()
        nets = {
            "NET_A": ChannelPath(
                net_name="NET_A",
                channel_sequence=["ch_0"],
                waypoints=[(0.0, 0.0), (29.0, 0.0)],
                total_length=29.0,
                preferred_layer="F.Cu",
            ),
            "NET_B": ChannelPath(
                net_name="NET_B",
                channel_sequence=["ch_1"],
                waypoints=[(0.0, 5.0), (29.0, 5.0)],
                total_length=29.0,
                preferred_layer="F.Cu",
            ),
        }

        result = run_astar_pathfinding(
            ChannelMapping(nets),
            grid,
            design_rules=DesignRules(),
            max_iter=10_000,
        )

        assert result.failure_reports, "expected both nets to fail against the wall"
        for net_name, report in result.failure_reports.items():
            # No unattributed decline: either a specific rule_id (and
            # attribution_gap=False), or an explicit attribution_gap=True
            # (and rule_id=None). __post_init__ already enforces this
            # invariant at construction time; this loop is the "100% of
            # entries carry a structured, non-blank reason" check across a
            # real multi-net run.
            if report.attribution_gap:
                assert report.rule_id is None
            else:
                assert report.rule_id, (
                    f"{net_name}: attribution_gap=False but rule_id is falsy"
                )
            assert report.domain in {"ground", "power", "hv", "signal"}
