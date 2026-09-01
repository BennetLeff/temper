"""Focused tests for explicit-path creepage replay resumption."""

from __future__ import annotations

from pathlib import Path

import pytest

from temper_placer.placer.cp_sat.creepage_cut_replay import (
    decode_creepage_cut_replay,
    encode_creepage_cut_replay,
)
from temper_placer.placer.cp_sat.creepage_replay_campaign import (
    ReplayAttemptOutcome,
    ReplayCampaignStatus,
)
from temper_placer.placer.cp_sat.creepage_replay_resume import (
    run_resumable_creepage_replay_campaign,
)

_BOARD = "board-sha256"
_INPUT = "input-sha256"


def _seed_checkpoint(path: Path, cuts: list[tuple[str, str, float]]) -> None:
    path.write_text(
        encode_creepage_cut_replay(cuts, board_identity=_BOARD, input_identity=_INPUT),
        encoding="utf-8",
    )


def test_resume_loads_prior_cuts_and_checkpoints_each_completed_attempt(tmp_path) -> None:
    path = tmp_path / "replay.json"
    _seed_checkpoint(path, [("B", "A", 1.0)])
    seen: list[tuple[tuple[str, str, float], ...]] = []
    outcomes = iter(
        [
            ReplayAttemptOutcome(
                "unknown",
                cuts=(("D", "C", 2.0),),
                violations=(("C", "D", 2.0),),
            ),
            ReplayAttemptOutcome("feasible", placement={"A": (1.0, 2.0)}),
        ]
    )

    def attempt(prior_cuts, _remaining):
        seen.append(prior_cuts)
        if len(seen) == 2:
            assert decode_creepage_cut_replay(
                path.read_text(encoding="utf-8"),
                expected_board_identity=_BOARD,
                expected_input_identity=_INPUT,
            ) == (("A", "B", 1.0), ("C", "D", 2.0))
        return next(outcomes)

    result = run_resumable_creepage_replay_campaign(
        attempt,
        replay_path=path,
        expected_board_identity=_BOARD,
        expected_input_identity=_INPUT,
        timeout_s=10.0,
        clock=iter([0.0, 0.1, 0.2, 0.3, 0.4]).__next__,
    )

    assert result.status is ReplayCampaignStatus.SUCCESS
    assert result.placement == {"A": (1.0, 2.0)}
    assert seen == [
        (("A", "B", 1.0),),
        (("A", "B", 1.0), ("C", "D", 2.0)),
    ]
    assert decode_creepage_cut_replay(
        path.read_text(encoding="utf-8"),
        expected_board_identity=_BOARD,
        expected_input_identity=_INPUT,
    ) == result.cuts


def test_progressive_selector_receives_index_and_full_inventory(tmp_path) -> None:
    path = tmp_path / "replay.json"
    _seed_checkpoint(path, [("A", "B", 1.0), ("C", "D", 2.0)])
    selected: list[tuple[int, tuple[tuple[str, str, float], ...]]] = []
    outcomes = iter(
        [
            ReplayAttemptOutcome("unknown", cuts=(("E", "F", 3.0),)),
            ReplayAttemptOutcome("feasible", placement={"complete": True}),
        ]
    )

    def selector(inventory, index):
        selected.append((index, inventory))
        return inventory[:1] if index == 0 else inventory[1:2]

    seen_attempts = []

    def attempt(cuts, _remaining):
        seen_attempts.append(cuts)
        return next(outcomes)

    result = run_resumable_creepage_replay_campaign(
        attempt,
        replay_path=path,
        expected_board_identity=_BOARD,
        expected_input_identity=_INPUT,
        cut_selector=selector,
        timeout_s=10.0,
        clock=iter([0.0, 0.1, 0.2, 0.3, 0.4]).__next__,
    )

    assert result.status is ReplayCampaignStatus.SUCCESS
    assert selected == [
        (0, (("A", "B", 1.0), ("C", "D", 2.0))),
        (1, (("A", "B", 1.0), ("C", "D", 2.0), ("E", "F", 3.0))),
    ]
    assert seen_attempts == [
        (("A", "B", 1.0),),
        (("C", "D", 2.0),),
    ]
    assert result.cuts == (("A", "B", 1.0), ("C", "D", 2.0), ("E", "F", 3.0))


def test_selector_stronger_row_fails_closed_and_preserves_checkpoint(tmp_path) -> None:
    path = tmp_path / "replay.json"
    _seed_checkpoint(path, [("A", "B", 1.0)])
    original = path.read_text(encoding="utf-8")

    result = run_resumable_creepage_replay_campaign(
        lambda _cuts, _remaining: pytest.fail("selector must reject before attempt"),
        replay_path=path,
        expected_board_identity=_BOARD,
        expected_input_identity=_INPUT,
        cut_selector=lambda _inventory, _index: [("A", "B", 2.0)],
        timeout_s=1.0,
        clock=iter([0.0, 0.1]).__next__,
    )

    assert result.status is ReplayCampaignStatus.INVALID
    assert result.reason == "invalid_attempt_result"
    assert result.placement is None
    assert path.read_text(encoding="utf-8") == original


def test_attempt_exception_preserves_last_good_checkpoint(tmp_path) -> None:
    path = tmp_path / "replay.json"
    _seed_checkpoint(path, [("A", "B", 1.0)])
    original = path.read_text(encoding="utf-8")

    def attempt(_cuts, _remaining):
        raise RuntimeError("interrupted attempt")

    result = run_resumable_creepage_replay_campaign(
        attempt,
        replay_path=path,
        expected_board_identity=_BOARD,
        expected_input_identity=_INPUT,
        timeout_s=1.0,
        clock=iter([0.0, 0.1]).__next__,
    )

    assert result.status is ReplayCampaignStatus.INVALID
    assert result.reason == "attempt_error"
    assert result.placement is None
    assert path.read_text(encoding="utf-8") == original


def test_missing_checkpoint_requires_explicit_empty_start(tmp_path) -> None:
    path = tmp_path / "replay.json"
    kwargs = {
        "replay_path": path,
        "expected_board_identity": _BOARD,
        "expected_input_identity": _INPUT,
        "timeout_s": 1.0,
        "clock": iter([0.0, 0.1, 0.2]).__next__,
    }
    with pytest.raises(ValueError, match="allow_empty_start"):
        run_resumable_creepage_replay_campaign(
            lambda _cuts, _remaining: ReplayAttemptOutcome(
                "feasible", placement={"complete": True}
            ),
            **kwargs,
        )

    result = run_resumable_creepage_replay_campaign(
        lambda _cuts, _remaining: ReplayAttemptOutcome(
            "feasible", placement={"complete": True}
        ),
        allow_empty_start=True,
        **kwargs,
    )
    assert result.status is ReplayCampaignStatus.SUCCESS
    assert path.is_file()
    assert decode_creepage_cut_replay(
        path.read_text(encoding="utf-8"),
        expected_board_identity=_BOARD,
        expected_input_identity=_INPUT,
    ) == ()
