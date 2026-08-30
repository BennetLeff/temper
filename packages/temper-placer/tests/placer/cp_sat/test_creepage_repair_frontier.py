"""Focused tests for conflict-cover repair preparation."""

from types import SimpleNamespace

from temper_placer.placer.cp_sat import creepage_repair_frontier


def _component(ref: str, x: float) -> SimpleNamespace:
    return SimpleNamespace(ref=ref, initial_position=(x, 5.0), bounds=(2.0, 2.0))


def test_preparation_freezes_exactly_the_cover_complement(monkeypatch) -> None:
    netlist = SimpleNamespace(
        components=[_component("A", 1.0), _component("B", 2.0), _component("C", 3.0)]
    )
    monkeypatch.setattr(
        creepage_repair_frontier,
        "verify_generated_creepage",
        lambda *_args: [("A", "B", 12.6, 0.0), ("B", "C", 6.0, 1.0)],
    )
    monkeypatch.setattr(
        creepage_repair_frontier.temper_orchestration,
        "plan_creepage_repair_frontier_py",
        lambda _rows: ["B"],
    )

    result = creepage_repair_frontier.prepare_initial_creepage_repair(netlist, object())

    assert result.movable_refs == frozenset({"B"})
    assert result.fixed_positions == {"A": (1.0, 5.0, 0), "C": (3.0, 5.0, 0)}
    assert result.replay_cuts == (("A", "B", 12.6), ("B", "C", 6.0))
    assert result.expanded_movable_refs == frozenset({"A", "B", "C"})


def test_uncovered_rust_frontier_fails_closed(monkeypatch) -> None:
    import pytest

    netlist = SimpleNamespace(components=[_component("A", 1.0), _component("B", 2.0)])
    monkeypatch.setattr(
        creepage_repair_frontier,
        "verify_generated_creepage",
        lambda *_args: [("A", "B", 12.6, 0.0)],
    )
    monkeypatch.setattr(
        creepage_repair_frontier.temper_orchestration,
        "plan_creepage_repair_frontier_py",
        lambda _rows: [],
    )

    with pytest.raises(ValueError, match="failed to cover"):
        creepage_repair_frontier.prepare_initial_creepage_repair(netlist, object())


def test_components_outside_model_board_are_forced_movable(monkeypatch) -> None:
    netlist = SimpleNamespace(components=[_component("A", 2.0), _component("B", 20.0)])
    monkeypatch.setattr(creepage_repair_frontier, "verify_generated_creepage", lambda *_args: [])
    monkeypatch.setattr(
        creepage_repair_frontier.temper_orchestration,
        "plan_creepage_repair_frontier_py",
        lambda _rows: [],
    )

    result = creepage_repair_frontier.prepare_initial_creepage_repair(
        netlist, object(), SimpleNamespace(width=10.0, height=10.0)
    )

    assert result.movable_refs == frozenset({"B"})
    assert result.fixed_positions == {"A": (2.0, 5.0, 0)}
