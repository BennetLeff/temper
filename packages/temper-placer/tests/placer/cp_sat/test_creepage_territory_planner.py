"""Python-boundary tests for the Rust weighted-twin quotient."""

import pytest

from temper_placer.placer.cp_sat.creepage_territory_planner import (
    plan_creepage_displacement_groups,
    plan_creepage_territories,
)


def test_weighted_twins_collapse_without_losing_exact_requirements() -> None:
    plan = plan_creepage_territories(
        ["X", "B2", "A2", "B1", "A1"],
        [
            ("A1", "B1", 12.6),
            ("A1", "B2", 12.6),
            ("A2", "B1", 12.6),
            ("A2", "B2", 12.6),
            ("B1", "B2", 2.0),
            ("A1", "X", 0.5),
            ("A2", "X", 0.5),
        ],
    )

    assert plan == (
        [["A1", "A2"], ["B1", "B2"], ["X"]],
        [(0, 1, 12.6), (0, 2, 0.5)],
        [(0, 0.0), (1, 2.0), (2, 0.0)],
    )


def test_duplicate_edges_are_max_reduced() -> None:
    assert plan_creepage_territories(["A", "B"], [("A", "B", 2.0), ("B", "A", 12.6)])[2] == [
        (0, 12.6)
    ]


def test_unknown_cut_reference_fails_closed() -> None:
    with pytest.raises(ValueError, match="unknown component"):
        plan_creepage_territories(["A", "B"], [("A", "C", 2.0)])


def test_displacement_groups_are_grouping_only_view_of_rust_quotient() -> None:
    refs = ["X", "B2", "A2", "B1", "A1"]
    cuts = [
        ("A1", "B1", 12.6),
        ("A1", "B2", 12.6),
        ("A2", "B1", 12.6),
        ("A2", "B2", 12.6),
        ("B1", "B2", 2.0),
        ("A1", "X", 0.5),
        ("A2", "X", 0.5),
    ]

    groups = plan_creepage_displacement_groups(refs, cuts)

    assert groups == [["A1", "A2"], ["B1", "B2"], ["X"]]
    assert groups == plan_creepage_displacement_groups(list(reversed(refs)), list(reversed(cuts)))


def test_displacement_groups_reject_unknown_cut_reference() -> None:
    with pytest.raises(ValueError, match="unknown component"):
        plan_creepage_displacement_groups(["A", "B"], [("A", "C", 2.0)])
