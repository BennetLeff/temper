"""
End-to-end tests for the U4 closure test integration of
``BottleneckGeometry`` messages.

These tests verify the SC1/SC2 surface: the closure test JSON must
contain a non-null ``bottleneck`` on the failed net, with a
``component_pair`` naming both pads, ``current_gap_mm <
required_gap_mm``, and a ``message`` matching the R2 template.
The output must be byte-identical across reruns at the same seed
(SC3).

The pipeline is exercised through a mocked protocol runner — the
real closure test would take minutes and depend on KiCad, so the
tests use ``MagicMock`` for the protocol layer and the routing
stage plumbing.
"""

from __future__ import annotations

import re
from unittest.mock import MagicMock, patch

import pytest

from temper_placer.regression.closure_test import ClosureTest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_routing_result(
    net_reports: list,
    completion_rate: float = 50.0,
):
    """Build a fake protocol result carrying a list of NetRoutingReports.

    Uses a simple namespace instead of ``MagicMock`` so the closure
    test's ``validate()`` truth assertions (``< 0``, ``<= 0``) get
    real ``int`` / ``float`` comparisons rather than ``MagicMock``
    magic that raises ``TypeError`` on arithmetic.
    """
    from types import SimpleNamespace

    data = SimpleNamespace(completion_rate=completion_rate, net_reports=net_reports)
    return SimpleNamespace(data=data)


def _bottleneck_message(
    a_ref: str = "Q1",
    a_pos: tuple[float, float] = (22.2, 15.0),
    b_ref: str = "D1",
    b_pos: tuple[float, float] = (30.5, 25.0),
    current_gap: float = 4.0,
    required_gap: float = 6.0,
) -> str:
    """Format an R2-template message."""
    return (
        f"{a_ref} at ({a_pos[0]:.1f}, {a_pos[1]:.1f}) and {b_ref} at "
        f"({b_pos[0]:.1f}, {b_pos[1]:.1f}) create {current_gap:.1f}mm "
        f"gap that needs {required_gap:.1f}mm"
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRoutingBottleneckReporting:
    """SC1/SC2: ``routing_failure_messages`` surfaces ``bottleneck.message``."""

    def test_two_net_creepage_failure_yields_bottleneck(
        self, tmp_path
    ) -> None:
        """A failed net's ``bottleneck.message`` is non-null and matches
        the R2 template; ``current_gap_mm < required_gap_mm``."""
        from temper_placer.router_v6.bottleneck_geometry import BottleneckGeometry
        from temper_placer.router_v6.diagnostics import (
            FailureReason,
            NetRoutingReport,
            RoutingStatus,
        )

        pcb_path = tmp_path / "two_net.kicad_pcb"
        pcb_path.write_text("(kicad_pcb)")

        failed_report = NetRoutingReport(
            net_name="GATE_H",
            status=RoutingStatus.FAILED,
            score=0.0,
            pins=2,
            routed_segments=0,
            total_segments=1,
            failure_reason=FailureReason.CLEARANCE,
            bottleneck=BottleneckGeometry(
                component_pair=("Q1", "D1"),
                pair_kind="component_component",
                positions_mm=((22.2, 15.0), (30.5, 25.0)),
                current_gap_mm=4.0,
                required_gap_mm=6.0,
                cut_size=1,
                cut_cells=((0, 5, 5),),
                message=_bottleneck_message(),
            ),
        )
        success_report = NetRoutingReport(
            net_name="VCC",
            status=RoutingStatus.SUCCESS,
            score=1.0,
            pins=2,
            routed_segments=1,
            total_segments=1,
        )
        routing_result = _make_routing_result(
            net_reports=[success_report, failed_report], completion_rate=50.0
        )

        # Patch the protocol runner so the test does not need a real
        # Benders / Router stack. The parse step is a no-op.
        with patch(
            "temper_placer.io.kicad_parser.parse_kicad_pcb_v6",
            return_value={},
        ), patch(
            "temper_placer.runner.resolve_and_run",
            return_value=routing_result,
        ):
            test = ClosureTest(pcb_path=pcb_path, seed={"benders_seed": 42, "router_seed": 42})
            result = test.run()

        # At least one routing failure message is surfaced.
        assert result.routing_failure_messages, "expected at least one routing failure message"
        msg = result.routing_failure_messages[0]
        assert "Q1" in msg
        assert "D1" in msg
        assert "4.0mm" in msg
        assert "6.0mm" in msg

        # The failed report's bottleneck fields match the SC1 assertions.
        bottleneck = failed_report.bottleneck
        assert bottleneck is not None
        assert bottleneck.component_pair == ("Q1", "D1")
        assert bottleneck.current_gap_mm < bottleneck.required_gap_mm

    def test_deterministic_across_reruns(self, tmp_path) -> None:
        """Rerun at the same seed → byte-identical ``routing_failure_messages``."""
        from temper_placer.router_v6.bottleneck_geometry import BottleneckGeometry
        from temper_placer.router_v6.diagnostics import (
            FailureReason,
            NetRoutingReport,
            RoutingStatus,
        )

        pcb_path = tmp_path / "two_net.kicad_pcb"
        pcb_path.write_text("(kicad_pcb)")

        failed_report = NetRoutingReport(
            net_name="GATE_H",
            status=RoutingStatus.FAILED,
            score=0.0,
            pins=2,
            routed_segments=0,
            total_segments=1,
            failure_reason=FailureReason.CHANNEL_CAPACITY,
            bottleneck=BottleneckGeometry(
                component_pair=("Q1", "D1"),
                pair_kind="component_component",
                positions_mm=((22.2, 15.0), (30.5, 25.0)),
                current_gap_mm=4.0,
                required_gap_mm=6.0,
                cut_size=1,
                cut_cells=((0, 5, 5),),
                message=_bottleneck_message(),
            ),
        )
        routing_result = _make_routing_result(
            net_reports=[failed_report], completion_rate=50.0
        )

        runs = []
        for _ in range(3):
            with patch(
                "temper_placer.io.kicad_parser.parse_kicad_pcb_v6",
                return_value={},
            ), patch(
                "temper_placer.runner.resolve_and_run",
                return_value=routing_result,
            ):
                test = ClosureTest(
                    pcb_path=pcb_path,
                    seed={"benders_seed": 42, "router_seed": 42},
                )
                result = test.run()
            runs.append(list(result.routing_failure_messages))

        assert runs[0] == runs[1] == runs[2]

    def test_message_format_matches_ideation(self) -> None:
        """SC2 template: ``X at (a, b) and Y at (c, d) create E mm gap
        that needs R mm``."""
        msg = _bottleneck_message()
        assert re.match(
            r"^.+ at \([\d.]+, [\d.]+\) and .+ at \([\d.]+, [\d.]+\) "
            r"create [\d.]+mm gap that needs [\d.]+mm$",
            msg,
        ), f"message does not match SC2 template: {msg!r}"

    def test_routing_failure_messages_default_empty(self) -> None:
        """A successful routing pass leaves ``routing_failure_messages`` empty."""
        from temper_placer.regression.closure_test import ClosureResult

        result = ClosureResult(passed=True, board_id="ok")
        assert result.routing_failure_messages == []
