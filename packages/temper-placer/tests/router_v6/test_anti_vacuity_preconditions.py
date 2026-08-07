"""
R10 anti-vacuity tests for the router pipeline's non-emptiness preconditions.

Context: docs/evidence/2026-08-07-router-silent-noop-diagnosis.md traced an
eleven-day silent-noop bug through two independent mechanisms:

- Bug A: ``_extract_stackup()`` misclassifies every copper layer as
  ``"plane"`` once the board has zone pours on plane-required nets (a
  single zone condemns the whole physical layer -- see
  docs/solutions/logic-errors/single-zone-condemns-whole-copper-layer-plane-2026-07-29.md).
  ``compute_routing_space()`` then drops every layer, so
  ``routing_spaces == {}``.
- Bug B: ``ChannelSkeletonStage`` hardcodes F.Cu/B.Cu only, so even a
  routing_spaces with usable inner layers never gets a skeleton for them.
- Neither ``validate_routing_space`` nor ``validate_channel_skeleton``
  could ever have caught this: both iterate a (possibly empty) dict with
  no non-emptiness check in front, so an empty dict vacuously produces
  zero failures -- and even a validator that *did* report a failure was
  print-only-when-verbose, never enforced.

This suite tests the fix for the *detection* layer only (validators,
stage preconditions, ``ModelBuilder.build()``'s own precondition) -- NOT
the underlying plane-classification bug itself (Bug A) or the F.Cu/B.Cu
hardcode (Bug B), both of which are out of scope here (a concurrent
change owns ``obstacle_map.py``, ``channel_skeleton.py``, and
``kicad_parser``'s ``_extract_stackup``; this suite does not import or
exercise the real KiCad parser at all).

Every fixture below is synthetic (hand-built ``ParsedPCB``/``BoardState``
objects), deliberately NOT the real ``pcb/temper.kicad_pcb`` -- per the
task brief, the production board's current routing genuinely produces an
empty model today (Bug A is still live on it), so a test asserting
against its *current* state would invert the moment the concurrent fix
lands. These fixtures reproduce the historical failure's *shape*
(a stackup where every layer classifies as "plane") independently of
whatever the real board's classifier does on any given day.

Groups:
  TestRoutingSpaceEmptyPrecondition   -- RoutingSpaceStage.run() raises
                                          RoutingSpaceEmptyError on the
                                          historical failure shape, not on
                                          a healthy board or a board with
                                          nothing to route.
  TestValidateRoutingSpaceVacuity     -- validate_routing_space distinguishes
                                          "validated N layers" from "had
                                          nothing to validate."
  TestChannelSkeletonVacuityGuard     -- vacuity_guards.validate_channel_skeleton_nonvacuous,
                                          the fatal companion validator that
                                          covers Bug B without touching
                                          channel_skeleton.py.
  TestConstraintModelEmptyPrecondition -- ModelBuilder.build() raises
                                          ConstraintModelEmptyError when a
                                          non-empty skeleton set (with real
                                          nets) produces zero variables.
  TestStage2OrchestratorAntiVacuity   -- end-to-end: the real orchestrator,
                                          not a hand-rolled substitute,
                                          halts on the historical failure
                                          shape (TestFailBeforePassAfter
                                          pattern, per
                                          scripts/tests/test_check_isolation_keepout.py).
"""

from __future__ import annotations

import networkx as nx
import pytest
from shapely.geometry import MultiPolygon

from temper_placer.core.netlist import Net
from temper_placer.deterministic.state import BoardState
from temper_placer.router_v6.channel_skeleton import ChannelSkeleton
from temper_placer.router_v6.constraint_model import ConstraintModelEmptyError, ModelBuilder
from temper_placer.router_v6.routing_space import (
    RoutingSpace,
    RoutingSpaceEmptyError,
    RoutingSpaceStage,
    validate_routing_space,
)
from temper_placer.router_v6.stage0_data import LayerInfo, ParsedPCB, StackupInfo
from temper_placer.router_v6.stage2_orchestrator import Stage2Orchestrator
from temper_placer.router_v6.stage_validators import (
    VALIDATOR_REGISTRY,
    FatalStageDRCFailure,
    StageDRCFailure,
    assert_no_fatal_failures,
    register_validator,
    run_validators,
)
from temper_placer.router_v6.vacuity_guards import validate_channel_skeleton_nonvacuous


def _ensure_registered(stage_name: str, validator_fn) -> None:
    """Idempotently guarantee *validator_fn* is registered for
    *stage_name*, regardless of whether some other test module (e.g.
    ``test_stage_validators.py``'s ``TestValidatorRegistry``, which calls
    the global ``clear_validators()`` in its own setup/teardown) already
    ran and wiped the process-wide ``VALIDATOR_REGISTRY`` before this
    module's tests execute. ``register_validator`` on its own is
    append-only and not naturally idempotent, so this checks membership
    first rather than re-decorating unconditionally."""
    if validator_fn not in VALIDATOR_REGISTRY.get(stage_name, []):
        register_validator(stage_name)(validator_fn)


# ---------------------------------------------------------------------------
# Fixtures / builders
# ---------------------------------------------------------------------------


class _MockBoardGeometry:
    """Minimal board_geometry shim -- same shape test_routing_space.py uses
    to satisfy ``_get_board_polygon``'s fallback path without a real
    ``core.board.Board``."""

    def __init__(self) -> None:
        self.bounds = (0, 0, 100, 100)
        self.width = 100
        self.height = 100
        self.origin = (0.0, 0.0)


def _all_plane_stackup() -> StackupInfo:
    """The exact historical failure shape: every physical layer
    misclassified as ``"plane"`` -- see
    docs/solutions/logic-errors/single-zone-condemns-whole-copper-layer-plane-2026-07-29.md.
    ``compute_routing_space()`` filters on ``layer_type not in ["signal",
    "mixed"]``, so this stackup makes it drop all four layers."""
    return StackupInfo(
        layers=[
            LayerInfo(index=0, name="F.Cu", layer_type="plane", thickness_um=35, plane_net="GND"),
            LayerInfo(index=1, name="In1.Cu", layer_type="plane", thickness_um=35, plane_net="GND"),
            LayerInfo(index=2, name="In2.Cu", layer_type="plane", thickness_um=35, plane_net="GND"),
            LayerInfo(index=3, name="B.Cu", layer_type="plane", thickness_um=35, plane_net="GND"),
        ],
        total_thickness_mm=1.6,
        layer_count=4,
    )


def _healthy_stackup() -> StackupInfo:
    """A normal 4-layer stackup: outer layers signal, inner layers mixed --
    ``compute_routing_space()`` keeps all four."""
    return StackupInfo(
        layers=[
            LayerInfo(index=0, name="F.Cu", layer_type="signal", thickness_um=35),
            LayerInfo(index=1, name="In1.Cu", layer_type="mixed", thickness_um=35),
            LayerInfo(index=2, name="In2.Cu", layer_type="mixed", thickness_um=35),
            LayerInfo(index=3, name="B.Cu", layer_type="signal", thickness_um=35),
        ],
        total_thickness_mm=1.6,
        layer_count=4,
    )


def _make_pcb(stackup: StackupInfo, nets: list[Net], components: list | None = None) -> ParsedPCB:
    pcb = ParsedPCB(
        components=components or [],
        nets=nets,
        design_rules=None,
        stackup=stackup,
        zones=[],
        board=None,
        source_path=None,
    )
    pcb.board_geometry = _MockBoardGeometry()
    return pcb


def _routable_net(name: str) -> Net:
    """A net with >=2 pins -- i.e. one that actually needs a route."""
    return Net(name=name, pins=[("U1", "1"), ("U2", "1")])


def _routing_space(layer_name: str, routing_area: float) -> RoutingSpace:
    return RoutingSpace(
        layer_name=layer_name,
        available_area=MultiPolygon(),
        total_area=10000.0,
        obstacle_area=0.0,
        routing_area=routing_area,
    )


def _skeleton_with_nodes(layer_name: str, n_nodes: int) -> ChannelSkeleton:
    g = nx.Graph()
    for i in range(n_nodes):
        g.add_node((float(i), 0.0))
    return ChannelSkeleton(graph=g, layer_name=layer_name, total_length=0.0)


# ---------------------------------------------------------------------------
# TestRoutingSpaceEmptyPrecondition
# ---------------------------------------------------------------------------


class TestRoutingSpaceEmptyPrecondition:
    def test_all_plane_layers_with_routable_nets_raises(self) -> None:
        """The historical failure shape: every layer classifies as plane,
        board has real nets to route -> RoutingSpaceStage must fail loudly,
        not silently hand back an empty dict."""
        pcb = _make_pcb(_all_plane_stackup(), nets=[_routable_net("SIG1"), _routable_net("SIG2")])
        state = BoardState(_parsed_pcb=pcb, _escape_vias=())
        with pytest.raises(RoutingSpaceEmptyError) as excinfo:
            RoutingSpaceStage().run(state)
        message = str(excinfo.value)
        assert "0 routing spaces" in message
        assert "2 routable net" in message
        assert "SIG1" in message

    def test_healthy_board_does_not_raise(self) -> None:
        pcb = _make_pcb(_healthy_stackup(), nets=[_routable_net("SIG1")])
        state = BoardState(_parsed_pcb=pcb, _escape_vias=())
        result = RoutingSpaceStage().run(state)
        assert result.routing_spaces
        assert "F.Cu" in result.routing_spaces
        assert "In1.Cu" in result.routing_spaces

    def test_all_plane_layers_with_no_routable_nets_does_not_raise(self) -> None:
        """An empty routing_spaces on a board with nothing routable is a
        legitimately empty result, not this bug's shape -- must not raise."""
        pcb = _make_pcb(_all_plane_stackup(), nets=[])
        state = BoardState(_parsed_pcb=pcb, _escape_vias=())
        result = RoutingSpaceStage().run(state)
        assert result.routing_spaces == {}

    def test_single_pin_nets_do_not_count_as_routable(self) -> None:
        """A net with exactly one pin needs nothing from Stage 2 -- must
        not trip the precondition on an otherwise-empty result."""
        pcb = _make_pcb(_all_plane_stackup(), nets=[Net(name="UNCONNECTED", pins=[("U1", "1")])])
        state = BoardState(_parsed_pcb=pcb, _escape_vias=())
        result = RoutingSpaceStage().run(state)
        assert result.routing_spaces == {}


# ---------------------------------------------------------------------------
# TestValidateRoutingSpaceVacuity
# ---------------------------------------------------------------------------


class TestValidateRoutingSpaceVacuity:
    """Defense-in-depth: validate_routing_space is called directly here,
    bypassing RoutingSpaceStage entirely, to prove the validator ITSELF
    distinguishes vacuous-empty from healthy-empty -- not just the stage
    wrapper around it."""

    def test_empty_routing_spaces_with_routable_nets_is_fatal(self) -> None:
        pcb = _make_pcb(_all_plane_stackup(), nets=[_routable_net("SIG1")])
        state = BoardState(_parsed_pcb=pcb, routing_spaces={})
        failures = validate_routing_space(state)
        assert len(failures) == 1
        assert failures[0].fatal is True
        assert "VACUOUS" in failures[0].reason

    def test_empty_routing_spaces_with_no_routable_nets_is_clean(self) -> None:
        pcb = _make_pcb(_all_plane_stackup(), nets=[])
        state = BoardState(_parsed_pcb=pcb, routing_spaces={})
        assert validate_routing_space(state) == []

    def test_healthy_routing_spaces_produces_no_failures(self) -> None:
        state = BoardState(routing_spaces={"F.Cu": _routing_space("F.Cu", 500.0)})
        assert validate_routing_space(state) == []

    def test_negative_area_still_flagged_non_fatally(self) -> None:
        """Existing per-item check preserved: a negative routing_area is
        still flagged, but distinctly from the vacuity finding (and not
        fatal -- it's a per-item geometry bug, not "nothing was checked")."""
        state = BoardState(routing_spaces={"F.Cu": _routing_space("F.Cu", -1.0)})
        failures = validate_routing_space(state)
        assert len(failures) == 1
        assert failures[0].fatal is False
        assert "Negative routing area" in failures[0].reason

    def test_none_routing_spaces_is_fatal(self) -> None:
        state = BoardState(routing_spaces=None)
        failures = validate_routing_space(state)
        assert len(failures) == 1
        assert failures[0].fatal is True


# ---------------------------------------------------------------------------
# TestChannelSkeletonVacuityGuard
# ---------------------------------------------------------------------------


class TestChannelSkeletonVacuityGuard:
    """vacuity_guards.validate_channel_skeleton_nonvacuous -- registered
    against the "ChannelSkeleton" stage name without touching
    channel_skeleton.py (see vacuity_guards.py's module docstring)."""

    def test_empty_skeletons_with_positive_routing_area_is_fatal(self) -> None:
        state = BoardState(
            routing_spaces={"F.Cu": _routing_space("F.Cu", 500.0)},
            channel_skeletons={},
        )
        failures = validate_channel_skeleton_nonvacuous(state)
        assert len(failures) == 1
        assert failures[0].fatal is True
        assert "VACUOUS" in failures[0].reason

    def test_all_zero_node_skeletons_with_positive_routing_area_is_fatal(self) -> None:
        state = BoardState(
            routing_spaces={"F.Cu": _routing_space("F.Cu", 500.0)},
            channel_skeletons={"F.Cu": _skeleton_with_nodes("F.Cu", 0)},
        )
        failures = validate_channel_skeleton_nonvacuous(state)
        assert len(failures) == 1
        assert failures[0].fatal is True

    def test_healthy_skeleton_produces_no_failures(self) -> None:
        state = BoardState(
            routing_spaces={"F.Cu": _routing_space("F.Cu", 500.0)},
            channel_skeletons={"F.Cu": _skeleton_with_nodes("F.Cu", 3)},
        )
        assert validate_channel_skeleton_nonvacuous(state) == []

    def test_one_healthy_layer_among_several_is_not_flagged(self) -> None:
        """At least one non-empty skeleton among several routable layers
        is enough -- this guard targets total silence, not per-layer
        completeness (that's validate_channel_skeleton's job)."""
        state = BoardState(
            routing_spaces={
                "F.Cu": _routing_space("F.Cu", 500.0),
                "In1.Cu": _routing_space("In1.Cu", 500.0),
            },
            channel_skeletons={"F.Cu": _skeleton_with_nodes("F.Cu", 3)},
        )
        assert validate_channel_skeleton_nonvacuous(state) == []

    def test_zero_routing_area_does_not_trigger(self) -> None:
        state = BoardState(
            routing_spaces={"F.Cu": _routing_space("F.Cu", 0.0)},
            channel_skeletons={},
        )
        assert validate_channel_skeleton_nonvacuous(state) == []

    def test_empty_routing_spaces_does_not_trigger(self) -> None:
        """RoutingSpaceStage's own precondition owns this case -- this
        guard only starts once Stage 2.2 found real routable area."""
        state = BoardState(routing_spaces={}, channel_skeletons={})
        assert validate_channel_skeleton_nonvacuous(state) == []


# ---------------------------------------------------------------------------
# TestConstraintModelEmptyPrecondition
# ---------------------------------------------------------------------------


class TestConstraintModelEmptyPrecondition:
    def _skeletons(self) -> dict[str, ChannelSkeleton]:
        g = nx.Graph()
        g.add_node((0.0, 0.0))
        g.add_node((10.0, 0.0))
        g.add_edge((0.0, 0.0), (10.0, 0.0))
        return {"F.Cu": ChannelSkeleton(graph=g, layer_name="F.Cu", total_length=10.0)}

    def test_geographic_pruning_with_unreachable_pins_raises(self) -> None:
        """A non-empty skeleton with real nets, but geographic pruning
        (enable_geographic_pruning=True) combined with a pcb that has no
        components -- so every net's pin_positions resolve to [] and
        _is_candidate_edge rejects every edge/via -- produces a
        zero-variable model despite having something to build from."""
        skeletons = self._skeletons()
        nets = [_routable_net("SIG1")]
        pcb = _make_pcb(_healthy_stackup(), nets, components=[])
        builder = ModelBuilder(
            skeletons=skeletons,
            nets=nets,
            pcb=pcb,
            enable_geographic_pruning=True,
        )
        with pytest.raises(ConstraintModelEmptyError) as excinfo:
            builder.build()
        message = str(excinfo.value)
        assert "0 variables" in message
        assert "F.Cu" in message
        assert "SIG1" in message

    def test_without_pruning_same_inputs_do_not_raise(self) -> None:
        """Same skeletons/nets, pruning off (the default) -- every
        (net, edge) pair unconditionally gets a variable, so the model is
        never empty for this input shape."""
        skeletons = self._skeletons()
        nets = [_routable_net("SIG1")]
        builder = ModelBuilder(skeletons=skeletons, nets=nets)
        model = builder.build()
        assert model.variable_count > 0

    def test_empty_skeletons_does_not_raise(self) -> None:
        """Scoped deliberately: an empty skeleton set producing an empty
        model is Stage 2.3's failure mode (guarded by
        vacuity_guards.validate_channel_skeleton_nonvacuous), not this
        precondition's -- ModelBuilder must not raise here."""
        nets = [_routable_net("SIG1")]
        builder = ModelBuilder(skeletons={}, nets=nets)
        model = builder.build()
        assert model.variable_count == 0

    def test_empty_nets_does_not_raise(self) -> None:
        """A board with skeletons but genuinely zero nets has nothing to
        build a model from -- not this bug's shape."""
        skeletons = self._skeletons()
        builder = ModelBuilder(skeletons=skeletons, nets=[])
        model = builder.build()
        assert model.variable_count == 0


# ---------------------------------------------------------------------------
# TestAssertNoFatalFailures
# ---------------------------------------------------------------------------


class TestAssertNoFatalFailures:
    """Unit coverage for stage_validators.assert_no_fatal_failures -- the
    mechanism that makes ``fatal=True`` load-bearing instead of another
    advisory print statement (see Stage2Orchestrator.run())."""

    def test_no_failures_is_a_no_op(self) -> None:
        assert_no_fatal_failures("SomeStage", [])

    def test_non_fatal_failures_do_not_raise(self) -> None:
        failures = [
            StageDRCFailure(field="x", value=1, reason="minor", stage="SomeStage")
        ]
        assert_no_fatal_failures("SomeStage", failures)

    def test_fatal_failure_raises_with_detail(self) -> None:
        failures = [
            StageDRCFailure(field="x", value=1, reason="minor", stage="SomeStage"),
            StageDRCFailure(
                field="routing_spaces",
                value={},
                reason="VACUOUS: nothing was validated",
                stage="RoutingSpace",
                fatal=True,
            ),
        ]
        with pytest.raises(FatalStageDRCFailure) as excinfo:
            assert_no_fatal_failures("RoutingSpace", failures)
        message = str(excinfo.value)
        assert "RoutingSpace" in message
        assert "1 fatal" in message
        assert "VACUOUS" in message

    def test_channel_skeleton_vacuity_guard_wired_through_run_validators(self) -> None:
        """End-to-end through the SAME chain Stage2Orchestrator.run() uses
        (run_validators -> assert_no_fatal_failures) for the "ChannelSkeleton"
        stage name specifically -- proves the registration in
        vacuity_guards.py actually reaches the enforcement point, not just
        that the function returns the right list in isolation."""
        _ensure_registered("ChannelSkeleton", validate_channel_skeleton_nonvacuous)
        state = BoardState(
            routing_spaces={"F.Cu": _routing_space("F.Cu", 500.0)},
            channel_skeletons={},
        )
        drc_failures = run_validators("ChannelSkeleton", state)
        with pytest.raises(FatalStageDRCFailure):
            assert_no_fatal_failures("ChannelSkeleton", drc_failures)

    def test_channel_skeleton_healthy_wired_through_run_validators(self) -> None:
        _ensure_registered("ChannelSkeleton", validate_channel_skeleton_nonvacuous)
        state = BoardState(
            routing_spaces={"F.Cu": _routing_space("F.Cu", 500.0)},
            channel_skeletons={"F.Cu": _skeleton_with_nodes("F.Cu", 3)},
        )
        drc_failures = run_validators("ChannelSkeleton", state)
        assert_no_fatal_failures("ChannelSkeleton", drc_failures)  # must not raise


# ---------------------------------------------------------------------------
# TestStage2OrchestratorAntiVacuity
# ---------------------------------------------------------------------------


class TestStage2OrchestratorAntiVacuity:
    """End-to-end through the REAL orchestrator (the one
    ``_pipeline_grid.py``'s ``_run_stage2`` actually uses in production),
    not a hand-rolled substitute -- proves the wiring, not just the unit.
    Mirrors TestFailBeforePassAfter in
    scripts/tests/test_check_isolation_keepout.py."""

    def test_before_all_plane_board_fails(self) -> None:
        pcb = _make_pcb(
            _all_plane_stackup(), nets=[_routable_net("SIG1"), _routable_net("SIG2")]
        )
        orchestrator = Stage2Orchestrator(verbose=False)
        with pytest.raises(RoutingSpaceEmptyError):
            orchestrator.run(pcb, escape_vias=[])

    def test_after_healthy_board_reaches_routing_space_stage_cleanly(self) -> None:
        """Not a full 8-stage run (later micro-stages carry their own,
        unrelated preconditions this suite does not own) -- this proves
        specifically that a healthy stackup does NOT trip
        RoutingSpaceEmptyError or the fatal vacuity validator the way the
        "before" board does."""
        pcb = _make_pcb(_healthy_stackup(), nets=[_routable_net("SIG1")])
        orchestrator = Stage2Orchestrator(verbose=False)
        # Only the first two micro-stages (ObstacleMap, RoutingSpace) are
        # exercised through the real orchestrator machinery by truncating
        # its stage list -- avoids coupling this test to unrelated stages'
        # own fixture requirements (e.g. design_rules) while still driving
        # the actual Stage2Orchestrator.run() loop, including
        # assert_no_fatal_failures, for the two stages this suite owns.
        orchestrator._stages = orchestrator._stages[:2]
        state = orchestrator.run(pcb, escape_vias=[])
        assert state.routing_spaces
        assert "F.Cu" in state.routing_spaces
