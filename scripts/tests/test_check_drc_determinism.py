"""Anti-vacuity tests for the Rust-backed DRC determinism harness."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import check_drc_determinism as cdd  # noqa: E402


def _item(description: str, x: float = 1.0, y: float = 2.0) -> dict:
    return {"description": description, "pos": {"x": x, "y": y}}


def _violation(category: str, message: str, items: list[dict]) -> dict:
    return {"type": category, "description": message, "items": items}


def _run(**categories: list[dict]) -> dict:
    return dict(categories)


CLEARANCE_A = _violation(
    "clearance",
    "Clearance violation (clearance 0.2000 mm; actual 0.1226 mm)",
    [
        _item("Track [sclk] on B.Cu, length 0.1000 mm"),
        _item("Track [gnd] on B.Cu, length 0.6000 mm"),
    ],
)
CLEARANCE_B = _violation(
    "clearance",
    "Clearance violation (clearance 0.2000 mm; actual 0.0851 mm)",
    [_item("Via [gnd] on F.Cu - B.Cu"), _item("Pad 1 [+3V3] of C9 on F.Cu")],
)


def _creepage(*, actual: str = "10.2975", track_length: str = "0.8485") -> dict:
    return _violation(
        "creepage",
        "Creepage violation (rule 'HighVoltageSignal to LV' creepage "
        f"12.6000 mm; actual {actual} mm)",
        [
            _item("Pad 2 [discharge.r_snub1-p2] of R14 on F.Cu", 130.0, 87.5),
            _item(f"Track [V_BUS_SENSE] on F.Cu, length {track_length} mm", 139.1, 87.5),
        ],
    )


def test_identical_runs_are_reported_reproducible() -> None:
    (row,) = cdd.analyse([_run(clearance=[CLEARANCE_A, CLEARANCE_B])] * 3)
    assert row["count_stable"] and row["set_stable"] and row["raw_set_stable"]
    assert row["intersection_size"] == row["union_size"] == 2


def test_a_changed_count_is_detected() -> None:
    (row,) = cdd.analyse(
        [_run(clearance=[CLEARANCE_A, CLEARANCE_B]), _run(clearance=[CLEARANCE_A])]
    )
    assert not row["count_stable"]
    assert not row["set_stable"]
    assert row["counts"] == {1: 1, 2: 1}


def test_a_swapped_violation_at_a_constant_count_is_detected() -> None:
    other = _violation(
        "clearance",
        "Clearance violation (clearance 0.2000 mm; actual 0.0000 mm)",
        [_item("Via [gnd] on F.Cu - B.Cu"), _item("Track [y] on F.Cu, length 9.2000 mm")],
    )
    (row,) = cdd.analyse(
        [_run(clearance=[CLEARANCE_A, CLEARANCE_B]), _run(clearance=[CLEARANCE_A, other])]
    )
    assert row["count_stable"]
    assert not row["set_stable"]


def test_report_order_alone_is_not_flagged() -> None:
    (row,) = cdd.analyse(
        [_run(clearance=[CLEARANCE_A, CLEARANCE_B]), _run(clearance=[CLEARANCE_B, CLEARANCE_A])]
    )
    assert row["set_stable"] and row["raw_set_stable"]


def test_provider_only_creepage_churn_is_semantically_stable_and_raw_visible() -> None:
    (row,) = cdd.analyse(
        [
            _run(creepage=[_creepage(track_length="0.8485")]),
            _run(creepage=[_creepage(track_length="11.9000")]),
            _run(creepage=[_creepage(track_length="0.8485")]),
        ]
    )
    assert row["count_stable"]
    assert row["set_stable"]
    assert not row["raw_set_stable"]
    assert row["raw_intersection_size"] == 0
    assert row["raw_union_size"] == 2


def test_measured_distance_is_not_normalised_away() -> None:
    (row,) = cdd.analyse(
        [_run(creepage=[_creepage()]), _run(creepage=[_creepage(actual="10.1975")])]
    )
    assert not row["set_stable"]


def test_a_category_appearing_in_only_some_runs_is_detected() -> None:
    report = {
        row["category"]: row
        for row in cdd.analyse(
            [_run(clearance=[CLEARANCE_A], creepage=[_creepage()]), _run(clearance=[CLEARANCE_A])]
        )
    }
    assert report["clearance"]["set_stable"]
    assert not report["creepage"]["count_stable"]
    assert report["creepage"]["counts"] == {0: 1, 1: 1}


def test_raw_warning_items_are_preserved_for_rust_identity() -> None:
    warning = {
        "type": "silk_overlap",
        "severity": "warning",
        "description": "Silkscreen overlap",
        "items": [_item("Segment of R1 on F.Silkscreen")],
    }
    grouped = cdd._group_raw_report({"violations": [warning]})
    assert grouped["W:silk_overlap"][0]["items"] == warning["items"]
    assert grouped["W:silk_overlap"][0]["type"] == "W:silk_overlap"


def test_synthetic_injection_makes_a_stable_measurement_unstable() -> None:
    stable = _run(clearance=[CLEARANCE_A, CLEARANCE_B])
    runs = []
    for index in range(4):
        run = {key: list(values) for key, values in stable.items()}
        if index % 2 == 1:
            next(iter(run.values())).pop()
        runs.append(run)
    assert cdd.render(cdd.analyse(runs), runs) is False
    clean = [{key: list(values) for key, values in stable.items()} for _ in range(4)]
    assert cdd.render(cdd.analyse(clean), clean) is True
