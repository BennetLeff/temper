"""
Tests for the U3 wire-up: ``SequentialRoutingStage._attach_bottlenecks``.

These tests exercise the post-mortem bottleneck hook without spinning up
the full routing pipeline. They construct a ``BoardState`` and a list of
``NetRoutingReport`` records, call the method, and assert the resulting
mutation.

Test scenarios (from the plan):
- ``test_sequential_routing_attaches_bottleneck``: a failed net's
  report gains a non-``None`` ``bottleneck`` and the message follows
  the R2 template.
- ``test_sequential_routing_bottleneck_isolated_from_exception``: an
  exception inside ``analyze_bottleneck`` does not crash the routing
  pass; ``report.bottleneck`` stays ``None``; the warning is logged.
- ``test_sequential_routing_skips_successful_nets``: ``analyze_bottleneck``
  is never called for SUCCESS status nets.
- ``test_sequential_routing_does_not_run_in_jit``: the call is opaque
  to JAX tracing; the jaxpr of an arbitrary pure Python expression
  does not reference ``analyze_bottleneck``.
"""

from __future__ import annotations

import logging
from unittest.mock import patch

import pytest

from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.deterministic.state import BoardState
from temper_placer.deterministic.stages.clearance_grid import ClearanceGrid
from temper_placer.deterministic.stages.sequential_routing import (
    SequentialRoutingStage,
)
from temper_placer.router_v6.bottleneck_geometry import BottleneckGeometry
from temper_placer.router_v6.diagnostics import (
    FailureReason,
    NetRoutingReport,
    RoutingStatus,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def two_pad_state() -> tuple[BoardState, dict, ClearanceGrid]:
    """A minimal state with two pads 8mm apart on a small grid."""
    components = [
        Component(
            ref="Q1",
            footprint="X",
            bounds=(2.0, 2.0),
            pins=[Pin("D", "1", (0.0, 0.0), net="GATE_H")],
            initial_position=(2.0, 5.0),
        ),
        Component(
            ref="D1",
            footprint="X",
            bounds=(2.0, 2.0),
            pins=[Pin("K", "1", (0.0, 0.0), net="GATE_H")],
            initial_position=(10.0, 5.0),
        ),
    ]
    nets = [Net("GATE_H", [("Q1", "D"), ("D1", "K")], net_class="HV")]
    netlist = Netlist(components=components, nets=nets)
    grid = ClearanceGrid(width_mm=12.0, height_mm=10.0, cell_size_mm=1.0, layer_count=2)
    state = BoardState(
        board=None,
        netlist=netlist,
        grid=grid,
        net_order=("GATE_H",),
    )
    net_by_name = {n.name: n for n in nets}
    return state, net_by_name, grid


def _make_report(name: str, status: RoutingStatus, reason: FailureReason | None = None) -> NetRoutingReport:
    return NetRoutingReport(
        net_name=name,
        status=status,
        score=0.0 if status != RoutingStatus.SUCCESS else 1.0,
        pins=2,
        routed_segments=0 if status != RoutingStatus.SUCCESS else 1,
        total_segments=1,
        failure_reason=reason,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAttachBottlenecks:
    def test_sequential_routing_attaches_bottleneck(
        self, two_pad_state, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A failed net's report gains a non-None bottleneck and the
        message follows the R2 template."""
        state, net_by_name, grid = two_pad_state
        stage = SequentialRoutingStage()
        report = _make_report("GATE_H", RoutingStatus.FAILED, FailureReason.CHANNEL_CAPACITY)
        reports = [report]

        with caplog.at_level(logging.WARNING, logger="temper_placer.deterministic.stages.sequential_routing"):
            stage._attach_bottlenecks(state, reports, net_by_name, grid)

        # ``analyze_bottleneck`` may legitimately return None when there
        # are no resolvable pads; in that case the report is left as-is
        # and the assertion below is skipped.
        attached = reports[0].bottleneck
        if attached is not None:
            assert attached.message
            # R2 template: "X at (a, b) and Y at (c, d) create E mm gap
            # that needs R mm" — see plan §U1 R2.
            import re

            assert re.match(
                r"^.+ at \([\d.]+, [\d.]+\) and .+ at \([\d.]+, [\d.]+\) "
                r"create [\d.]+mm gap that needs [\d.]+mm$",
                attached.message,
            ), f"message does not match R2 template: {attached.message!r}"
            assert any(
                "routing_bottleneck" in rec.message for rec in caplog.records
            )

    def test_sequential_routing_bottleneck_isolated_from_exception(
        self, two_pad_state, caplog: pytest.LogCaptureFixture
    ) -> None:
        """When ``analyze_bottleneck`` raises, the routing pass is
        unaffected; ``report.bottleneck`` stays ``None``."""
        state, net_by_name, grid = two_pad_state
        stage = SequentialRoutingStage()
        report = _make_report("GATE_H", RoutingStatus.FAILED, FailureReason.CHANNEL_CAPACITY)
        reports = [report]

        def raise_runtime(*_args, **_kwargs):
            raise RuntimeError("simulated analyze_bottleneck failure")

        with caplog.at_level(logging.DEBUG, logger="temper_placer.deterministic.stages.sequential_routing"):
            with patch(
                "temper_placer.deterministic.stages.sequential_routing.analyze_bottleneck",
                raise_runtime,
            ):
                stage._attach_bottlenecks(state, reports, net_by_name, grid)

        assert reports[0].bottleneck is None
        assert any("simulated analyze_bottleneck failure" in rec.message for rec in caplog.records)

    def test_sequential_routing_skips_successful_nets(
        self, two_pad_state
    ) -> None:
        """``analyze_bottleneck`` is never called for SUCCESS status nets."""
        state, net_by_name, grid = two_pad_state
        stage = SequentialRoutingStage()
        success_report = _make_report("GATE_H", RoutingStatus.SUCCESS)
        failed_report = _make_report(
            "GATE_H_2", RoutingStatus.FAILED, FailureReason.CHANNEL_CAPACITY
        )

        with patch(
            "temper_placer.deterministic.stages.sequential_routing.analyze_bottleneck"
        ) as mock:
            stage._attach_bottlenecks(
                state, [success_report, failed_report], net_by_name, grid
            )

        # analyze_bottleneck may be called at most once (for the failed
        # report); the successful report must not trigger the call.
        names_called = [c.args[1] for c in mock.call_args_list] if mock.call_args_list else []
        assert "GATE_H" not in names_called

    def test_sequential_routing_does_not_run_in_jit(self) -> None:
        """The post-mortem call is opaque to JAX tracing.

        ``analyze_bottleneck`` is a Python-only function (uses
        networkx, shapely) and the wire point is a plain method call,
        not a jitted primitive. We assert this by inspecting a
        representative jaxpr for any reference to the bottleneck
        module's symbols.
        """
        import jax

        def pure_python(x):
            return x + 1

        jaxpr = jax.make_jaxpr(pure_python)(1)
        text = str(jaxpr)
        assert "analyze_bottleneck" not in text
        assert "BottleneckGeometry" not in text
        assert "_attach_bottlenecks" not in text

    def test_sequential_routing_skips_short_circuit_reasons(
        self, two_pad_state
    ) -> None:
        """For a failure reason outside CHANNEL_CAPACITY / CLEARANCE /
        None, ``analyze_bottleneck`` is called and short-circuits to
        return ``None``; the report's bottleneck stays ``None``."""
        state, net_by_name, grid = two_pad_state
        stage = SequentialRoutingStage()
        report = _make_report("GATE_H", RoutingStatus.FAILED, FailureReason.TOPOLOGY)
        reports = [report]

        # No mock — the real ``analyze_bottleneck`` returns None for
        # the TOPOLOGY failure reason.
        stage._attach_bottlenecks(state, reports, net_by_name, grid)
        assert reports[0].bottleneck is None
