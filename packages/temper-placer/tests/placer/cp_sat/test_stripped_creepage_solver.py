"""Focused tests for the exact stripped component-box model."""

from __future__ import annotations

import pytest

from temper_placer.placer.cp_sat import stripped_creepage_solver as solver


def _normalised(_components, _requirements, _width, _height, _units):
    return (
        [("A", 200, 200), ("B", 200, 200)],
        [("A", "B", 100)],
        2100,
        200,
    )


def test_fixed_model_is_exhaustively_verified(monkeypatch: pytest.MonkeyPatch) -> None:
    verified = []
    monkeypatch.setattr(solver._to, "normalize_stripped_creepage_py", _normalised)

    def verify(*args):
        verified.append(args[-2])

    monkeypatch.setattr(solver._to, "verify_stripped_creepage_py", verify)
    result = solver.solve_stripped_creepage(
        [("A", 2.0, 2.0), ("B", 2.0, 2.0)],
        [("A", "B", 1.0)],
        21.0,
        2.0,
        timeout_s=2.0,
        num_search_workers=1,
    )
    assert result.feasible
    assert set(result.placements) == {"A", "B"}
    assert verified


def test_rotation_is_represented_and_verifier_can_reject(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        solver._to,
        "normalize_stripped_creepage_py",
        lambda *_args: ([("A", 600, 200)], [], 200, 600),
    )
    monkeypatch.setattr(
        solver._to,
        "verify_stripped_creepage_py",
        lambda *_args: (_ for _ in ()).throw(ValueError("remaining violation")),
    )
    result = solver.solve_stripped_creepage(
        [("A", 6.0, 2.0)], [], 2.0, 6.0, allow_rotations=True, num_search_workers=1
    )
    assert result.status is solver.StrippedCreepageSolveStatus.MODEL_INVALID
    assert not result.placements


def test_invalid_rust_instance_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    def reject(*_args):
        raise ValueError("unknown component")

    monkeypatch.setattr(solver._to, "normalize_stripped_creepage_py", reject)
    result = solver.solve_stripped_creepage([], [], 10.0, 10.0)
    assert result.status is solver.StrippedCreepageSolveStatus.MODEL_INVALID
    assert not result.placements
