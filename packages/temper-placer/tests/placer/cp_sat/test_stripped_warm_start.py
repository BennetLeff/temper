"""Tests for the stripped-to-production warm-start adapter."""

from __future__ import annotations

from types import SimpleNamespace

from temper_placer.placer.cp_sat import stripped_warm_start as bridge
from temper_placer.placer.cp_sat.stripped_creepage_solver import (
    StrippedCreepageSolveResult,
    StrippedCreepageSolveStatus,
)


def _return(value):
    def fake(*_args, **_kwargs):
        return value

    return fake


def _netlist() -> SimpleNamespace:
    return SimpleNamespace(
        components=[
            SimpleNamespace(ref="A", bounds=(4.0, 2.0)),
            SimpleNamespace(ref="B", bounds=(3.0, 1.0)),
        ]
    )


def _board() -> SimpleNamespace:
    return SimpleNamespace(width=20.0, height=10.0)


def test_verified_lower_left_boxes_become_center_hints(monkeypatch) -> None:
    monkeypatch.setattr(bridge, "_requirement_inputs", _return([("A", "B", 6.0)]))
    solve = StrippedCreepageSolveResult(
        StrippedCreepageSolveStatus.OPTIMAL,
        {"A": (1.0, 2.0, 0), "B": (10.0, 4.0, 0)},
        0.1,
    )
    monkeypatch.setattr(bridge, "solve_stripped_creepage", _return(solve))

    result = bridge.solve_stripped_creepage_warm_start(_netlist(), _board(), object())

    assert result.usable
    assert result.requirement_count == 1
    assert result.hints == {"A": (3.0, 3.0, 0), "B": (11.5, 4.5, 0)}


def test_non_feasible_stripped_result_returns_no_hints(monkeypatch) -> None:
    monkeypatch.setattr(bridge, "_requirement_inputs", _return([]))
    solve = StrippedCreepageSolveResult(
        StrippedCreepageSolveStatus.UNKNOWN,
        {},
        1.0,
        "solver timed out",
    )
    monkeypatch.setattr(bridge, "solve_stripped_creepage", _return(solve))

    result = bridge.solve_stripped_creepage_warm_start(_netlist(), _board(), object())

    assert not result.usable
    assert result.hints == {}
    assert result.solve is solve
    assert "timed out" in (result.message or "")


def test_adapter_rejects_unexpected_rotation(monkeypatch) -> None:
    monkeypatch.setattr(bridge, "_requirement_inputs", _return([]))
    solve = StrippedCreepageSolveResult(
        StrippedCreepageSolveStatus.FEASIBLE,
        {"A": (1.0, 2.0, 1), "B": (10.0, 4.0, 0)},
        0.1,
    )
    monkeypatch.setattr(bridge, "solve_stripped_creepage", _return(solve))

    result = bridge.solve_stripped_creepage_warm_start(_netlist(), _board(), object())

    assert not result.usable
    assert result.hints == {}
    assert "rotation" in (result.message or "")


def test_requirement_generation_failure_fails_closed(monkeypatch) -> None:
    monkeypatch.setattr(
        bridge,
        "_requirement_inputs",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("bad rules")),
    )

    result = bridge.solve_stripped_creepage_warm_start(_netlist(), _board(), object())

    assert not result.usable
    assert result.solve is None
    assert result.requirement_count == 0
    assert "bad rules" in (result.message or "")


def test_prepared_production_instance_uses_its_plain_instance_data(monkeypatch) -> None:
    instance = SimpleNamespace(
        components=(("A", 4.0, 2.0), ("B", 3.0, 1.0)),
        requirements=(("A", "B", 6.0),),
        board_width_mm=20.0,
        board_height_mm=10.0,
    )
    solve = StrippedCreepageSolveResult(
        StrippedCreepageSolveStatus.FEASIBLE,
        {"A": (1.0, 2.0, 0), "B": (10.0, 4.0, 0)},
        0.1,
    )
    calls = []

    def fake_solve(*args, **kwargs):
        calls.append((args, kwargs))
        return solve

    monkeypatch.setattr(bridge, "solve_stripped_creepage", fake_solve)

    result = bridge.solve_production_stripped_instance_warm_start(instance)

    assert result.usable
    assert result.hints == {"A": (3.0, 3.0, 0), "B": (11.5, 4.5, 0)}
    assert calls[0][0][:4] == (
        (("A", 4.0, 2.0), ("B", 3.0, 1.0)),
        (("A", "B", 6.0),),
        20.0,
        10.0,
    )
    assert calls[0][1]["allow_rotations"] is False
