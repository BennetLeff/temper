from __future__ import annotations

from dataclasses import dataclass

import pytest

from temper_placer.placer.cp_sat.creepage_replay_campaign import (
    ReplayAttemptOutcome,
    ReplayCampaignStatus,
    adapt_cpsat_placement_result,
    run_creepage_replay_campaign,
)


def test_campaign_progression_and_stall() -> None:
    outcomes = iter([
        ReplayAttemptOutcome("unknown", [("U2", "K1", 4.0)], [("K1", "U2", 4.0)]),
        ReplayAttemptOutcome("feasible", [("K1", "U2", 3.0)], placement={"K1": (1, 2)}),
    ])
    seen = []
    result = run_creepage_replay_campaign(
        lambda cuts, _remaining: (seen.append(cuts) or next(outcomes)),
        clock=iter([0.0, .1, .2, .3, .4]).__next__,
    )
    assert result.status is ReplayCampaignStatus.SUCCESS
    assert result.placement == {"K1": (1, 2)}
    assert seen == [(), (("K1", "U2", 4.0),)]
    stalled = run_creepage_replay_campaign(
        lambda _cuts, _remaining: ReplayAttemptOutcome("unknown"),
        clock=iter([0.0, .1, .2]).__next__,
    )
    assert stalled.reason == "no_cut_progress" and stalled.placement is None


@dataclass
class _Result:
    status: str
    positions: dict[str, tuple[float, float]]
    decomposed_creepage_cuts: list[tuple[str, str, float]]
    decomposed_creepage_remaining_violations: list[tuple[str, str, float, float]]


def test_adapter_projects_193_cuts_and_30_production_violations() -> None:
    adapted = adapt_cpsat_placement_result(
        _Result(
            "unknown", {"K1": (1, 2)},
            [(f"K{i}", f"U{i}", float(i)) for i in range(193)],
            [(f"K{i}", f"U{i}", float(i), .5) for i in range(30)],
        )
    )
    assert adapted.placement is None
    assert len(tuple(adapted.cuts)) == 193
    assert len(tuple(adapted.violations)) == 30


def test_adapter_success_exposes_positions_and_malformed_fails_closed() -> None:
    assert adapt_cpsat_placement_result(_Result("optimal", {"K1": (1, 2)}, [], [])).placement == {"K1": (1, 2)}
    with pytest.raises(ValueError, match="four values"):
        adapt_cpsat_placement_result(_Result("optimal", {}, [], [("A", "B", 1.0)]))  # type: ignore[list-item]
