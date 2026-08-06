"""Tests for ``scripts/check_drc_determinism.py``.

The point of these tests is anti-vacuity. A determinism harness that reports
"reproducible" no matter what it is fed is worse than no harness: it converts
"we never looked" into "we checked and it was fine". So the tests here are
weighted towards proving the harness can FAIL -- that injected variance of
several different shapes is actually detected -- rather than towards proving
it passes on identical input.

The two properties that make this harness non-vacuous, and that a future
refactor must not quietly drop:

1. It compares the SET of violations, not only the count. Two runs can agree
   on "199 shorting_items" and disagree about which 199.
2. It normalises net *names* away before comparing, but nothing else. KiCad
   assigns an arbitrary member net to each shorted copper cluster and that
   choice is unstable run to run; if that cosmetic difference were not
   normalised it would mark every category unstable and drown out the real
   signal. Normalising it too aggressively (e.g. also dropping the measured
   distance) would hide real differences instead.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import check_drc_determinism as cdd  # noqa: E402


def _violation(message: str, items: list[str]) -> dict:
    return {"message": message, "items": items}


def _run(**categories: list[dict]) -> dict:
    return dict(categories)


CLEARANCE_A = _violation(
    "Clearance violation (clearance 0.2000 mm; actual 0.1226 mm)",
    ["Track [sclk] on B.Cu, length 0.1000 mm", "Track [gnd] on B.Cu, length 0.6000 mm"],
)
CLEARANCE_B = _violation(
    "Clearance violation (clearance 0.2000 mm; actual 0.0851 mm)",
    ["Via [gnd] on F.Cu - B.Cu", "Pad 1 [+3V3] of C9 on F.Cu"],
)


def test_identical_runs_are_reported_reproducible() -> None:
    runs = [_run(clearance=[CLEARANCE_A, CLEARANCE_B])] * 4
    report = cdd.analyse(runs)
    assert [r["category"] for r in report] == ["clearance"]
    assert report[0]["count_stable"] and report[0]["set_stable"]


def test_a_changed_count_is_detected() -> None:
    runs = [
        _run(clearance=[CLEARANCE_A, CLEARANCE_B]),
        _run(clearance=[CLEARANCE_A]),
    ]
    (row,) = cdd.analyse(runs)
    assert not row["count_stable"]
    assert row["counts"] == {1: 1, 2: 1}


def test_a_swapped_violation_at_a_constant_count_is_detected() -> None:
    """The failure mode a count-only ceiling cannot see: same total, different
    violations. This is not hypothetical -- pcb/temper.kicad_pcb exhibits it in
    ``clearance`` at a constant 378."""
    other = _violation(
        "Clearance violation (clearance 0.2000 mm; actual 0.0000 mm)",
        ["Via [gnd] on F.Cu - B.Cu", "Track [y] on F.Cu, length 9.2000 mm"],
    )
    runs = [
        _run(clearance=[CLEARANCE_A, CLEARANCE_B]),
        _run(clearance=[CLEARANCE_A, other]),
    ]
    (row,) = cdd.analyse(runs)
    assert row["count_stable"], "counts are equal -- that is the whole point"
    assert not row["set_stable"]


def test_report_order_alone_is_not_flagged() -> None:
    """kicad-cli does not promise a stable report order, and order is not the
    thing being measured -- flagging it would make the harness cry wolf."""
    runs = [
        _run(clearance=[CLEARANCE_A, CLEARANCE_B]),
        _run(clearance=[CLEARANCE_B, CLEARANCE_A]),
    ]
    (row,) = cdd.analyse(runs)
    assert row["set_stable"]


def test_renaming_a_shorted_cluster_net_is_normalised_away() -> None:
    """KiCad reports the same physical track as [sclk] on one run and [cs_n] on
    the next, because the two nets are shorted and the cluster's name is picked
    arbitrarily. That must not read as a violation-set change."""
    renamed = _violation(
        CLEARANCE_A["message"],
        ["Track [cs_n] on B.Cu, length 0.1000 mm", "Track [gnd] on B.Cu, length 0.6000 mm"],
    )
    runs = [_run(clearance=[CLEARANCE_A]), _run(clearance=[renamed])]
    (row,) = cdd.analyse(runs)
    assert row["set_stable"]
    # ...but it is still visible when asked for explicitly.
    assert cdd.net_churn(runs) == {"Track [] on B.Cu, length 0.1000 mm": ["cs_n", "sclk"]}


def test_net_blinding_happens_before_item_sorting() -> None:
    """Regression guard. If items are sorted before nets are blinded, renaming
    one net reorders the pair and the violation looks different -- which would
    reintroduce exactly the false positive the previous test rules out."""
    a = cdd.violation_identity("clearance", "m", ["Track [aaa]", "Track [zzz]"], blind_nets=True)
    b = cdd.violation_identity("clearance", "m", ["Track [zzz]", "Track [aaa]"], blind_nets=True)
    assert a == b


def test_measured_distance_is_not_normalised_away() -> None:
    """The same pair reported at a different computed distance is a real
    difference, not a cosmetic one."""
    nearer = _violation(
        "Clearance violation (clearance 0.2000 mm; actual 0.0100 mm)", CLEARANCE_A["items"]
    )
    runs = [_run(clearance=[CLEARANCE_A]), _run(clearance=[nearer])]
    (row,) = cdd.analyse(runs)
    assert not row["set_stable"]


def test_a_category_appearing_in_only_some_runs_is_detected() -> None:
    runs = [_run(clearance=[CLEARANCE_A], creepage=[CLEARANCE_B]), _run(clearance=[CLEARANCE_A])]
    report = {r["category"]: r for r in cdd.analyse(runs)}
    assert report["clearance"]["set_stable"]
    assert not report["creepage"]["count_stable"]
    assert report["creepage"]["counts"] == {0: 1, 1: 1}


def test_synthetic_injection_makes_a_stable_measurement_unstable() -> None:
    """End-to-end anti-vacuity: the --inject-variance=synthetic path must turn a
    perfectly reproducible board into a NOT-REPRODUCIBLE report."""
    stable = _run(clearance=[CLEARANCE_A, CLEARANCE_B])
    runs = []
    for index in range(4):
        run = {k: list(v) for k, v in stable.items()}
        if index % 2 == 1:
            for violations in run.values():
                if violations:
                    violations.pop()
                    break
        runs.append(run)
    assert cdd.render(cdd.analyse(runs), runs) is False
    # ...and without the injection the identical harness passes.
    clean = [{k: list(v) for k, v in stable.items()} for _ in range(4)]
    assert cdd.render(cdd.analyse(clean), clean) is True
