from __future__ import annotations

import pytest

from temper_placer.placer.cp_sat.progressive_creepage_cuts import select_progressive_creepage_cuts

_CUTS = [("U2", "K1", 4.0), ("A1", "R3", 12.6), ("Q1", "K1", 12.6), ("Q2", "K1", 8.0)]


def test_strongest_first_ties_and_canonical_output() -> None:
    assert select_progressive_creepage_cuts(_CUTS, attempt_index=0, initial_batch_size=2) == (("A1", "R3", 12.6), ("K1", "Q1", 12.6))


def test_growth_cap_duplicates_and_always_active() -> None:
    assert len(select_progressive_creepage_cuts(_CUTS, attempt_index=1, initial_batch_size=1, growth_per_attempt=1)) == 2
    assert len(select_progressive_creepage_cuts(_CUTS, attempt_index=99, max_active_cuts=3)) == 3
    assert select_progressive_creepage_cuts([("K1", "U2", 1), ("U2", "K1", 9)], attempt_index=0, initial_batch_size=1) == (("K1", "U2", 9.0),)
    assert len(select_progressive_creepage_cuts(_CUTS, attempt_index=0, initial_batch_size=1, always_active_refs=["U2"], always_active_pairs=[("Q1", "K1")], max_active_cuts=3)) == 3


@pytest.mark.parametrize("value", [-1, True, 1.5])
def test_parameter_validation(value: object) -> None:
    with pytest.raises(ValueError):
        select_progressive_creepage_cuts(_CUTS, attempt_index=value)  # type: ignore[arg-type]
