"""Deterministic component-aware terminal-tree planning properties."""

from itertools import permutations

from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.router_v6.connectivity import CopperPad, PadIdentity
from temper_placer.router_v6.constraints_geometry import Point
from temper_placer.router_v6.terminal_tree import plan_terminal_tree


def _pad(index: int, x: int, y: int) -> CopperPad:
    return CopperPad(PadIdentity("U1", str(index), "NET", x, y, (0,)), Point(x, y), "rect", (1, 1))


def test_planner_uses_existing_component_attachment_and_stable_ties():
    pads = [_pad(2, 10, 0), _pad(1, 0, 0), _pad(3, 0, 10)]

    plan = plan_terminal_tree(pads)

    assert plan.root == _pad(1, 0, 0).identity
    assert [(edge.source.pad, edge.target.pad) for edge in plan.edges] == [("1", "2"), ("1", "3")]


@given(
    st.lists(
        st.tuples(st.integers(-10, 10), st.integers(-10, 10)),
        min_size=2,
        max_size=6,
        unique=True,
    )
)
@settings(max_examples=50, deadline=30_000)
def test_planned_tree_is_acyclic_connected_and_permutation_invariant(points):
    pads = [_pad(index, x, y) for index, (x, y) in enumerate(points)]
    expected = plan_terminal_tree(pads)

    assert len(expected.edges) == len(pads) - 1
    attached = {expected.root}
    for edge in expected.edges:
        assert edge.source in attached
        assert edge.target not in attached
        attached.add(edge.target)
    assert attached == {pad.identity for pad in pads}

    for order in permutations(pads):
        actual = plan_terminal_tree(order)
        assert actual == expected
