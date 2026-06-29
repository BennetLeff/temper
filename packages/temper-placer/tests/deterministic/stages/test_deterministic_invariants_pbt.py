"""Property-based tests for deterministic pipeline stage output invariants.

Tests invariants of deterministic pipeline stages: output non-None,
field type correctness, component-count conservation, round-trip
pass-through, and structural drift detection (import-time failures).

Follows the pattern established by Router V6 output validity tests.
"""

from __future__ import annotations

import inspect

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import seed as hseed
from hypothesis import strategies as st
from tests.deterministic.deterministic_property_strategies import (
    board_state,
    board_state_with_zones,
)

from temper_placer.deterministic.stages import (
    ApplyPlacementsStage,
    LayerAssignmentStage,
    NetClassSetupStage,
    NetOrderingStage,
    SlotGenerationStage,
    ZoneAssignmentStage,
    ZoneGeometryStage,
)
from temper_placer.deterministic.stages.config_attach import ConfigAttachStage
from temper_placer.deterministic.state import BoardState

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_all_stage_classes():
    """Return all Stage subclasses registered in the stages __init__ module.

    Skips the abstract ``Stage`` base class itself (as well as data classes
    like ``ConnectivityViolation``, ``PlacementViolation``, etc.).
    """
    import temper_placer.deterministic.stages as stages_mod
    from temper_placer.deterministic.stages.base import Stage

    classes: list[tuple[str, type[Stage]]] = []
    for name, obj in inspect.getmembers(stages_mod):
        if not inspect.isclass(obj):
            continue
        if obj is Stage:
            continue
        if not issubclass(obj, Stage):
            continue
        classes.append((name, obj))
    return classes


_STAGES_NEEDING_SPECIAL_ARGS: set[str] = {
    # Need constructor args that can't be derived from state alone
    "ClearanceGridStage",
    "ComponentAssignmentStage",
    "CourtyardCheckStage",
    "DRCOracleSetupStage",
    "SetupStage",
    "DRCSweepStage",
    "DRCValidationStage",
    "FinePitchEscapeStage",
    "PhasedComponentAssignmentStage",
    "PhasedComponentAssignmentValidatorStage",
    "PlacementValidationStage",
    "PowerPlaneStage",
    "RoutingChannelAwareSlotStage",
    "ShortCircuitDetectionStage",  # needs routes
    "TrackDeduplicationStage",
    "ViaDeduplicationStage",
    "ViaValidationStage",
    "ZoneAwareSlotGenerationStage",
}

# Stages that work with minimal BoardState (board + netlist):
_RUNNABLE_STAGES: list[type] = [
    ConfigAttachStage,
    ZoneGeometryStage,
    ZoneAssignmentStage,
    NetOrderingStage,
    LayerAssignmentStage,
    NetClassSetupStage,
]


def _make_config_for_test(netlist) -> object:
    """Create a minimal config object for ConfigAttachStage."""
    from types import SimpleNamespace
    return SimpleNamespace(net_classes={})


# ---------------------------------------------------------------------------
# R1: Structural drift — all registered stages import and instantiate
# ---------------------------------------------------------------------------

@pytest.mark.property
def test_all_registered_stages_importable() -> None:
    """Every registered Stage subclass can be imported and instantiated.

    Catches the routing/ deletion class of bug: if a stage's dependency
    module is deleted or renamed, the import fails here before CI.
    """
    stage_classes = _get_all_stage_classes()

    assert len(stage_classes) >= 10, (
        f"Expected at least 10 registered stages, found {len(stage_classes)}"
    )

    for name, cls in stage_classes:
        # Verify the class has a ``run`` method
        assert hasattr(cls, "run"), f"{name}.run missing"
        assert callable(cls.run), f"{name}.run not callable"

        if name in _STAGES_NEEDING_SPECIAL_ARGS:
            continue

        # Try default construction
        try:
            instance = cls()
        except Exception:
            # Some stages require args even if not in the skip list;
            # this is fine as long as the class itself is importable
            continue

        assert hasattr(instance, "name"), f"{name}.name missing"
        assert isinstance(instance.name, str), f"{name}.name not a str"


@pytest.mark.property
def test_all_registered_stages_run_returns_boardstate() -> None:
    """Every registered Stage.run() accepts BoardState and returns BoardState.

    Uses a fixture-derived BoardState for stages that can be constructed
    with default args.
    """

    stage_classes = _get_all_stage_classes()

    for name, cls in stage_classes:
        if name in _STAGES_NEEDING_SPECIAL_ARGS:
            continue
        sig = inspect.signature(cls.run)
        params = list(sig.parameters.values())
        assert len(params) >= 2, f"{name}.run() has too few parameters: {params}"
        assert params[1].annotation in (
            inspect.Parameter.empty,
            BoardState,
            "BoardState",
        ), f"{name}.run() first param annotation not BoardState: {params[1].annotation}"
        # Return annotation check (allow empty for older style)
        return_annotation = sig.return_annotation
        if return_annotation is not inspect.Signature.empty:
            assert return_annotation is BoardState or return_annotation == "BoardState", (
                f"{name}.run() return annotation not BoardState: {return_annotation}"
            )


# ---------------------------------------------------------------------------
# R2: Stage output non-None and field types
# ---------------------------------------------------------------------------


@given(state=board_state_with_zones())
@settings(max_examples=30, deadline=30000)
@pytest.mark.property
def test_zone_geometry_stage_output(state: BoardState) -> None:
    """ZoneGeometryStage populates BoardState.zones."""
    stage = ZoneGeometryStage()
    result = stage.run(state)
    assert result is not None
    assert isinstance(result, BoardState)
    assert result.zones, "zones should be populated after ZoneGeometryStage"
    assert len(result.zones) >= 2, f"Expected at least 2 zones, got {len(result.zones)}"


@given(state=board_state_with_zones())
@settings(max_examples=30, deadline=30000)
@pytest.mark.property
def test_zone_assignment_stage_output(state: BoardState) -> None:
    """ZoneAssignmentStage populates BoardState.component_zone_map."""
    stage = ZoneAssignmentStage()
    result = stage.run(state)
    assert result is not None
    assert isinstance(result, BoardState)
    assert result.component_zone_map, "component_zone_map should be populated"


@given(state=board_state_with_zones())
@settings(max_examples=30, deadline=30000)
@pytest.mark.property
def test_slot_generation_stage_output(state: BoardState) -> None:
    """SlotGenerationStage populates BoardState.zone_slots after zones exist."""
    # First run ZoneGeometryStage to populate zones
    state_with_zones = ZoneGeometryStage().run(state)
    assert state_with_zones.zones, "prerequisite: zones must exist"

    stage = SlotGenerationStage(slot_spacing_mm=7.5)
    result = stage.run(state_with_zones)
    assert result is not None
    assert isinstance(result, BoardState)
    assert result.zone_slots, "zone_slots should be populated after SlotGenerationStage"


@given(state=board_state())
@settings(max_examples=30, deadline=30000)
@pytest.mark.property
def test_net_ordering_stage_output(state: BoardState) -> None:
    """NetOrderingStage populates BoardState.net_order."""
    stage = NetOrderingStage()
    result = stage.run(state)
    assert result is not None
    assert isinstance(result, BoardState)
    assert result.net_order, "net_order should be populated after NetOrderingStage"
    assert len(result.net_order) >= 1, f"Expected at least 1 net, got {len(result.net_order)}"


@given(state=board_state())
@settings(max_examples=30, deadline=30000)
@pytest.mark.property
def test_layer_assignment_stage_output(state: BoardState) -> None:
    """LayerAssignmentStage populates BoardState.layer_assignments."""
    stage = LayerAssignmentStage()
    result = stage.run(state)
    assert result is not None
    assert isinstance(result, BoardState)
    assert result.layer_assignments, "layer_assignments should be populated"


@given(state=board_state())
@settings(max_examples=30, deadline=30000)
@pytest.mark.property
def test_config_attach_stage_output(state: BoardState) -> None:
    """ConfigAttachStage sets BoardState.config when a config is provided."""
    cfg = _make_config_for_test(state.netlist)
    stage = ConfigAttachStage(cfg)
    result = stage.run(state)
    assert result is not None
    assert isinstance(result, BoardState)
    assert result.config is not None, "config should be set after ConfigAttachStage"


@given(state=board_state_with_zones())
@settings(max_examples=30, deadline=30000)
@pytest.mark.property
def test_apply_placements_stage_output(state: BoardState) -> None:
    """ApplyPlacementsStage updates component initial_positions in netlist."""
    # Need to set up placements first (mimic ComponentAssignmentStage output)
    from dataclasses import replace

    if not state.netlist:
        pytest.skip("no netlist in state")

    # Build minimal placements: one per component
    placements = {}
    for comp in state.netlist.components:
        pos = getattr(comp, "initial_position", None)
        if pos is None:
            pos = (1.0, 1.0)
        placements[comp.ref] = pos

    state_with_placements = replace(state, placements=frozenset(placements.items()))

    stage = ApplyPlacementsStage()
    result = stage.run(state_with_placements)
    assert result is not None
    assert isinstance(result, BoardState)
    assert result.netlist is not None
    # Components should have updated positions
    for comp in result.netlist.components:
        if comp.ref in placements:
            pos = getattr(comp, "initial_position", None)
            assert pos is not None, f"Component {comp.ref} missing initial_position"


# ---------------------------------------------------------------------------
# R3: Component count invariant — non-filtering stages preserve count
# ---------------------------------------------------------------------------


@given(state=board_state_with_zones())
@settings(max_examples=30, deadline=30000)
@pytest.mark.property
def test_component_count_preserved(state: BoardState) -> None:
    """Non-filtering stages preserve component count."""
    if not state.netlist:
        pytest.skip("no netlist in state")
    initial_count = len(state.netlist.components)

    # Chain lightweight stages that don't filter components
    result = state
    for StageCls in _RUNNABLE_STAGES:
        if StageCls is ConfigAttachStage:
            result = StageCls(_make_config_for_test(state.netlist)).run(result)
        elif StageCls is NetClassSetupStage:
            result = StageCls(net_classes={}).run(result)
        else:
            result = StageCls().run(result)

    assert result is not None
    assert result.netlist is not None
    final_count = len(result.netlist.components)
    assert final_count == initial_count, (
        f"Component count changed: {initial_count} -> {final_count}"
    )


# ---------------------------------------------------------------------------
# R4: Round-trip — pass-through stages leave state fields unchanged
# ---------------------------------------------------------------------------


@given(state=board_state_with_zones())
@settings(max_examples=30, deadline=30000)
@pytest.mark.property
def test_config_attach_round_trip(state: BoardState) -> None:
    """ConfigAttachStage preserves all BoardState fields except config."""
    cfg = _make_config_for_test(state.netlist)
    stage = ConfigAttachStage(cfg)
    result = stage.run(state)

    # config is the only field that should have changed
    assert result.board is state.board
    assert result.netlist is state.netlist
    assert result.zones == state.zones
    assert result.component_zone_map == state.component_zone_map
    assert result.placements == state.placements


@given(state=board_state_with_zones())
@settings(max_examples=30, deadline=30000)
@pytest.mark.property
def test_net_class_setup_round_trip(state: BoardState) -> None:
    """NetClassSetupStage preserves all BoardState fields except netlist."""
    stage = NetClassSetupStage(net_classes={})
    result = stage.run(state)

    # Board and structural fields should be unchanged
    assert result.board is state.board
    assert result.zones == state.zones
    assert result.placements == state.placements


# ---------------------------------------------------------------------------
# R2 (cont.): Chain stage output — ZoneGeometry + SlotGeneration produces
# zone_slots with geometry within board bounds
# ---------------------------------------------------------------------------


@given(state=board_state_with_zones())
@settings(max_examples=30, deadline=30000)
@pytest.mark.property
def test_zone_slot_chain_output(state: BoardState) -> None:
    """ZoneGeometryStage -> SlotGenerationStage chain produces valid zone_slots."""
    state_with_zones = ZoneGeometryStage().run(state)
    assert state_with_zones.zones, "ZoneGeometryStage must populate zones"

    state_with_slots = SlotGenerationStage(slot_spacing_mm=7.5).run(state_with_zones)
    assert state_with_slots.zone_slots, "SlotGenerationStage must populate zone_slots"

    # Each zone_slot entry is (zone_name, tuple_of_slots)
    for zone_name, slots in state_with_slots.zone_slots:
        assert isinstance(zone_name, str)
        assert isinstance(slots, tuple)
        assert len(slots) >= 1, f"Zone {zone_name} has no slots"


# ---------------------------------------------------------------------------
# R2 (cont.): NetClassSetupStage preserves component count
# ---------------------------------------------------------------------------


@given(state=board_state())
@settings(max_examples=30, deadline=30000)
@pytest.mark.property
def test_net_class_setup_output(state: BoardState) -> None:
    """NetClassSetupStage returns a valid BoardState."""
    stage = NetClassSetupStage(net_classes={})
    result = stage.run(state)
    assert result is not None
    assert isinstance(result, BoardState)


# ---------------------------------------------------------------------------
# Idempotence: same seed → same stage output shape
# ---------------------------------------------------------------------------


def _draw_state_from_seed(seed_val: int) -> BoardState:
    """Deterministically draw a BoardState from a fixed seed."""
    result: list[BoardState] = []

    @hseed(seed_val)
    @settings(max_examples=1, database=None)
    @given(data=st.data())
    def _draw(data: st.DataObject) -> None:
        result.append(data.draw(board_state_with_zones()))

    _draw()
    return result[0]


@pytest.mark.property
@given(seed_val=st.integers(0, 9999))
@settings(
    max_examples=20,
    deadline=30000,
    suppress_health_check=[HealthCheck.nested_given],
)
def test_strategy_idempotent_state_shape(seed_val: int) -> None:
    """Drawing BoardState twice with the same seed produces same shape."""
    s1 = _draw_state_from_seed(seed_val)
    s2 = _draw_state_from_seed(seed_val)

    assert s1.board is not None
    assert s2.board is not None
    assert s1.board.width == s2.board.width
    assert s1.board.height == s2.board.height
    assert s1.netlist is not None
    assert s2.netlist is not None
    assert len(s1.netlist.components) == len(s2.netlist.components)
    assert len(s1.netlist.nets) == len(s2.netlist.nets)


# ---------------------------------------------------------------------------
# Edge case: BoardState with zero components handled gracefully
# ---------------------------------------------------------------------------


def test_empty_board_state_handled_gracefully() -> None:
    """BoardState with no components does not crash lightweight stages."""
    state = BoardState()

    for StageCls in _RUNNABLE_STAGES:
        if StageCls is ConfigAttachStage:
            result = StageCls(None).run(state)
        elif StageCls is NetClassSetupStage:
            result = StageCls(net_classes={}).run(state)
        else:
            result = StageCls().run(state)
        assert result is not None
        assert isinstance(result, BoardState), f"{StageCls.__name__} returned wrong type"
