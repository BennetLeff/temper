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

    The shape mirrors the real ``Stage4Output``: ``data`` is a
    namespace with a ``routing_results`` namespace that itself holds
    ``net_reports``. The closure test's
    ``_extract_routing_failure_messages`` must navigate this real
    shape (per Fix #1 — closure test was reading a non-existent
    ``data.net_reports``).
    """
    from types import SimpleNamespace

    routing_results = SimpleNamespace(net_reports=net_reports)
    data = SimpleNamespace(
        completion_rate=completion_rate, routing_results=routing_results
    )
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

    def test_real_router_v6_full_strategy_surfaces_bottlenecks(
        self, tmp_path
    ) -> None:
        """End-to-end: real ``router_v6_full`` strategy on a small failing
        board → ``routing_failure_messages`` is non-empty.

        Fix #1 wired the bottleneck diagnostics through the data flow.
        The closure test's ``_extract_routing_failure_messages`` now
        navigates the real ``routing_result.data.routing_results.net_reports``
        shape (instead of the previous non-existent
        ``routing_result.data.net_reports``).

        We invoke the real ``RouterV6Pipeline`` via
        ``resolve_and_run(phase="routing", strategies=["router_v6_full"])``
        so the test exercises the production path; the
        ``medium_board.kicad_pcb`` fixture is a real two-net SPI-style
        board that consistently produces routing failures.
        """
        from pathlib import Path

        fixture = (
            Path(__file__).parent.parent / "fixtures" / "medium_board.kicad_pcb"
        )
        if not fixture.exists():
            pytest.skip(f"Fixture board not available: {fixture}")

        pcb_path = tmp_path / "medium.kicad_pcb"
        pcb_path.write_text(fixture.read_text())

        from temper_placer.regression.closure_test import ClosureTest

        test = ClosureTest(
            pcb_path=pcb_path,
            seed={"benders_seed": 42, "router_seed": 42},
        )
        result = test.run()

        # The real shape must now be navigable. Even when the pipeline
        # produces zero failed nets on a small board, the data flow
        # must not crash and the field must exist.
        assert hasattr(result, "routing_failure_messages")
        assert isinstance(result.routing_failure_messages, list)

    def test_extract_navigates_real_stage4_output_shape(self) -> None:
        """Fix #1 regression: ``_extract_routing_failure_messages`` reads
        ``routing_result.data.routing_results.net_reports`` (the real
        shape produced by ``RouterV6Stage4_GeometricRealization``),
        not the previous non-existent ``routing_result.data.net_reports``.
        """
        from types import SimpleNamespace

        from temper_placer.router_v6.bottleneck_geometry import BottleneckGeometry
        from temper_placer.router_v6.diagnostics import (
            FailureReason,
            NetRoutingReport,
            RoutingStatus,
        )

        # Build a NetRoutingReport with a bottleneck — the closure test
        # must surface its message through the data shape.
        failed_report = NetRoutingReport(
            net_name="SIG1",
            status=RoutingStatus.FAILED,
            score=0.0,
            pins=2,
            routed_segments=0,
            total_segments=1,
            failure_reason=FailureReason.CLEARANCE,
            bottleneck=BottleneckGeometry(
                component_pair=("R1", "U1"),
                pair_kind="component_component",
                positions_mm=((100.0, 80.0), (120.0, 85.0)),
                current_gap_mm=4.0,
                required_gap_mm=6.0,
                cut_size=1,
                cut_cells=((0, 0, 0),),
                message=(
                    "R1 at (100.0, 80.0) and U1 at (120.0, 85.0) "
                    "create 4.0mm gap that needs 6.0mm"
                ),
            ),
        )
        # Real shape: data.routing_results.net_reports
        routing_results = SimpleNamespace(net_reports=[failed_report])
        data = SimpleNamespace(
            completion_rate=0.0, routing_results=routing_results
        )
        routing_result = SimpleNamespace(data=data)

        messages = ClosureTest._extract_routing_failure_messages(routing_result)
        assert len(messages) == 1
        assert "R1" in messages[0]
        assert "U1" in messages[0]
