from __future__ import annotations

from temper_placer.placer.cp_sat import creepage_lower_bounds as lower_bounds


def test_thin_boundary_preserves_necessary_only_report(monkeypatch) -> None:
    monkeypatch.setattr(
        lower_bounds.temper_orchestration,
        "analyze_creepage_lower_bounds_py",
        lambda *_args: (
            3,
            3,
            1,
            [3],
            10.0,
            10.0,
            20.0,
            20.0,
            [(10.0, [0], ["A", "B", "C"], 3, 1200.0, 900.0, 30.0, 30.0)],
            False,
        ),
    )

    report = lower_bounds.analyze_creepage_lower_bounds(
        [("A", 10.0, 10.0), ("B", 10.0, 10.0), ("C", 10.0, 10.0)],
        [("A", "B", 10.0), ("A", "C", 10.0), ("B", "C", 10.0)],
        20.0,
        20.0,
    )

    assert not report.passes_necessary_conditions
    assert report.quotient_class_sizes == (3,)
    assert report.threshold_bounds[0].component_refs == ("A", "B", "C")
