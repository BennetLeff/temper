"""TDD/PBT tests for safety-ordered DRC campaign controls."""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from temper_placer.regression.drc_campaign import CampaignState, evaluate_campaign


def _state() -> CampaignState:
    return CampaignState(("creepage", "clearance", "track_width"))


def test_active_category_must_decrease() -> None:
    result = evaluate_campaign(_state(), {"creepage": 10, "clearance": 4}, {"creepage": 10, "clearance": 0})

    assert result.passed is False
    assert "did not decrease" in result.reason


def test_active_category_closes_at_zero() -> None:
    result = evaluate_campaign(_state(), {"creepage": 10, "clearance": 4}, {"creepage": 0, "clearance": 4})

    assert result.passed is True
    assert result.closed is True
    assert dict(result.tightened_ceilings)["creepage"] == 0


def test_unrelated_category_increase_requires_approval() -> None:
    result = evaluate_campaign(
        _state(),
        {"creepage": 10, "clearance": 4},
        {"creepage": 9, "clearance": 5},
    )

    assert result.passed is False
    assert "Ceiling-Approval:" in result.reason


def test_approved_increase_is_visible_and_progresses() -> None:
    result = evaluate_campaign(
        _state(),
        {"creepage": 10, "clearance": 4},
        {"creepage": 9, "clearance": 5},
        ceiling_approval=True,
    )

    assert result.passed is True
    assert result.increases == (("clearance", 1),)


@given(extra=st.integers(min_value=0, max_value=10))
def test_adding_unchanged_inactive_category_does_not_change_verdict(extra: int) -> None:
    base = evaluate_campaign(_state(), {"creepage": 10}, {"creepage": 9})
    with_extra = evaluate_campaign(
        _state(),
        {"creepage": 10, "diagnostic": extra},
        {"creepage": 9, "diagnostic": extra},
    )

    assert base.passed == with_extra.passed
    assert base.closed == with_extra.closed
