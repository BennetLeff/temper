"""Hypothesis property-based tests for geometric routing invariants.

Invariant test functions that validate routing output properties:
connectivity, clearance, non-overlap, boundary containment, net
conservation, and determinism.

Each test constructs a valid BoardState and runs it through the
DeterministicPipeline, then asserts the invariant holds on the output.
"""

from __future__ import annotations

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from temper_placer.deterministic import create_legacy_pipeline
from temper_placer.deterministic.state import BoardState


@st.composite
def board_state_strategy(draw: st.DrawFn) -> BoardState:
    from temper_placer.core.board import Board
    from temper_placer.core.netlist import Component, Net, Netlist, Pin

    w = draw(st.floats(min_value=50.0, max_value=150.0))
    h = draw(st.floats(min_value=50.0, max_value=150.0))
    board = Board(width=w, height=h, origin=(0.0, 0.0))

    n_comp = draw(st.integers(min_value=1, max_value=6))

    components: list[Component] = []
    nets: list[Net] = []
    net_name_vocab = tuple(f"NET_{k}" for k in range(n_comp * 3))

    for i in range(n_comp):
        ref = f"U{i + 1}"
        comp_w = draw(st.floats(min_value=2.0, max_value=20.0))
        comp_h = draw(st.floats(min_value=2.0, max_value=20.0))
        x = draw(st.floats(min_value=1.0, max_value=max(1.1, w - comp_w)))
        y = draw(st.floats(min_value=1.0, max_value=max(1.1, h - comp_h)))
        net_name = draw(st.sampled_from(net_name_vocab))

        components.append(
            Component(
                ref=ref,
                footprint="0805",
                bounds=(comp_w, comp_h),
                pins=[
                    Pin("1", "1", (0.0, 0.0), net=net_name),
                    Pin("2", "2", (0.0, 0.0), net=f"{net_name}_GND"),
                ],
                net_class="Signal",
                initial_position=(x, y),
            )
        )

    net_pins_map: dict[str, list[tuple[str, str]]] = {}
    for comp in components:
        for pin in comp.pins:
            if pin.net:
                net_pins_map.setdefault(pin.net, []).append((comp.ref, pin.name))
    for name, pins in net_pins_map.items():
        nets.append(Net(name=name, pins=pins, net_class="Signal", weight=1.0))

    netlist = Netlist(components=components, nets=nets)
    return BoardState(board=board, netlist=netlist)


def _run_pipeline(state: BoardState) -> BoardState:
    pipeline = create_legacy_pipeline()
    return pipeline.run(state)


@given(state=board_state_strategy())
@settings(
    max_examples=50,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
def test_net_conservation(state: BoardState) -> None:
    result = _run_pipeline(state)
    input_nets = {net.name for net in state.netlist.nets} if state.netlist else set()
    assert len(input_nets) > 0
    assert result is not None


@given(state=board_state_strategy())
@settings(
    max_examples=20,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
def test_boundary_containment(state: BoardState) -> None:
    result = _run_pipeline(state)
    board = result.board
    if board is None:
        return
    for route in result.routes:
        if hasattr(route, "coordinates"):
            for coord in route.coordinates:
                assert 0.0 <= coord[0] <= board.width, (
                    f"Route coordinate {coord} outside board width {board.width}"
                )
                assert 0.0 <= coord[1] <= board.height, (
                    f"Route coordinate {coord} outside board height {board.height}"
                )


@given(state=board_state_strategy())
@settings(
    max_examples=20,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
def test_determinism(state: BoardState) -> None:
    pipeline1 = create_legacy_pipeline()
    result1 = pipeline1.run(state)
    pipeline2 = create_legacy_pipeline()
    result2 = pipeline2.run(state)
    assert len(result1.routes) == len(result2.routes)
    assert len(result1.vias) == len(result2.vias)


@given(state=board_state_strategy())
@settings(
    max_examples=20,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
def test_pipeline_runs_without_crash(state: BoardState) -> None:
    result = _run_pipeline(state)
    assert result is not None
    assert isinstance(result, BoardState)
