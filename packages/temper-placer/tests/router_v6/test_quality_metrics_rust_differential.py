"""R1a differential: router_v6 cluster F (quality metrics) vs its pinned oracle.

**THIS SUITE IS DELIBERATELY RED.**  It is the gate-G1 artifact: the
differential pinning the pre-migration implementation is written *before* the
Rust, so git history proves test-before-code.  Every test here calls
:func:`rust`, which raises ``AssertionError`` until
``temper_quality_oracle`` exports the cluster-F kernels.  When the Rust lands,
the same file goes green with no edits.

Why not ``pytest.importorskip``
-------------------------------
A skip is not a red.  ``importorskip`` would make this file report "passed"
in a run where nothing was compared, which is precisely the failure mode G1
exists to prevent -- and it would keep reporting that if the Rust extension
later went missing or stale.  There is no existing repo convention for a
pending-Rust differential (every other ``*_rust_differential.py`` on ``main``
was committed alongside working Rust), so this file establishes one:

* the crate import is attempted once at module scope and its failure is
  **recorded, not raised**, so collection still succeeds and every test is
  individually visible as a failure rather than one collection error hiding
  the file;
* :func:`rust` converts "symbol missing" into ``AssertionError`` at the point
  of use, so the red is a normal assertion failure with an actionable message;
* :func:`test_rust_symbols_exist` states the whole contract in one place.

Arms
----
* **oracle** -- ``tests/router_v6/_quality_metrics_py_oracle.py``, a verbatim
  copy of the three modules as of ``15110feccc6ec9389f0777d3cff1ce9f81b11068``.
* **rust** -- ``temper_quality_oracle``'s cluster-F kernels (not yet written).

Comparison is by **type-carrying signature** (``tests/router_v6/_signature``):
``float.hex()`` per float, concrete type name per leaf.  **No tolerance
anywhere** -- gate G2 requires bit-exact ``==``, and none of these kernels is
itself non-deterministic, so no 1-ulp band is claimed for any of them.

Traps this suite's corpus is built around (catalog §2)
------------------------------------------------------
* **B4** -- ``_distance_mm`` and ``_angle_between`` use CPython's Dekker
  ``math.hypot``, not libm ``hypot`` and not ``sqrt(dx*dx + dy*dy)``.
* **B5** -- ``_angle_between``'s ``max(-1.0, min(1.0, ...))`` and
  ``_is_via_near_board_edge``'s **variadic** ``min`` over four distances.
* **B3** -- the ``:.1f``/``:.2f`` ``description`` strings round half-to-even.
* **B7** -- ``sum()`` order in ``lint_single_net_detours``; the grouped
  ``3.0 * (track_width + min_clearance)`` threshold.

The ``test_trap_*`` measurements that quantify each of these live in
``test_quality_metrics_oracle_pin.py``, not here: they assert facts about
CPython and need no Rust arm, so keeping them here would leave this file
reporting a handful of passes and make its red state a number to read rather
than a property to see.
"""

from __future__ import annotations

import pytest

import tests.router_v6._quality_metrics_fixtures as FX
import tests.router_v6._quality_metrics_py_oracle as ORACLE
from tests.router_v6._quality_metrics_cases import (
    ANGLE_CASES,
    BBOX_CASES,
    CORPUS_BOARDS,
    DISTANCE_PAIRS,
    EDGE_MARGIN_CASES,
    ORDER_TRACE_SETS,
    SCENARIOS,
    random_angle_cases,
    random_distance_pairs,
    random_trace_set,
)
from tests.router_v6._signature import sig

# ---------------------------------------------------------------------------
# The Rust arm.  Recorded, not raised, so collection succeeds and each test
# fails individually (see the module docstring).
# ---------------------------------------------------------------------------
try:  # pragma: no cover - exercised by whichever branch is true
    import temper_quality_oracle as _rs

    _IMPORT_ERROR: str | None = None
except ImportError as exc:  # pragma: no cover
    _rs = None
    _IMPORT_ERROR = str(exc)


#: The kernels the Rust side must export for this cluster.  Names follow the
#: ``<module>_<function>_py`` convention used by the landed differentials.
REQUIRED_RUST_SYMBOLS = (
    # metrics/slop_linter
    "slop_distance_mm_py",
    "slop_vector_py",
    "slop_angle_between_py",
    "slop_order_traces_py",
    "slop_load_traces_by_net_py",
    "slop_lint_hairpin_turns_py",
    "slop_lint_zigzag_patterns_py",
    "slop_lint_isolated_vias_py",
    "slop_lint_single_net_detours_py",
    "slop_lint_all_py",
    # quality/via_count
    "via_count_get_component_bboxes_py",
    "via_count_get_board_bbox_py",
    "via_count_is_via_in_bbox_py",
    "via_count_is_via_near_board_edge_py",
    "via_count_classify_vias_py",
)


def rust(name: str):
    """Return the Rust kernel ``name``, or fail loudly.

    This is the single point at which the suite's RED state is produced.  It
    raises ``AssertionError`` -- never ``skip`` -- so an un-migrated or stale
    extension is reported as a failure.
    """
    if _rs is None:
        raise AssertionError(
            f"temper_quality_oracle is not importable ({_IMPORT_ERROR}); the "
            f"cluster-F Rust kernels (needed: {name}) have not been written "
            "yet. This suite is expected to be RED until they are -- see "
            "gate G1 in docs/wave4-discipline-contract.md."
        )
    fn = getattr(_rs, name, None)
    if fn is None:
        raise AssertionError(
            f"temper_quality_oracle is missing {name!r}. Expected cluster-F "
            f"exports: {', '.join(REQUIRED_RUST_SYMBOLS)}"
        )
    return fn


def test_rust_symbols_exist() -> None:
    """The whole cluster-F Rust contract, stated once.

    RED until the migration lands.  Green afterwards with no edit to this file.
    """
    assert _rs is not None, (
        f"temper_quality_oracle is not importable: {_IMPORT_ERROR}. "
        "Cluster-F (quality metrics) has not been migrated yet."
    )
    missing = [n for n in REQUIRED_RUST_SYMBOLS if not hasattr(_rs, n)]
    assert not missing, f"temper_quality_oracle is missing {missing}"


# ---------------------------------------------------------------------------
# slop_linter — scalar geometry helpers
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case", DISTANCE_PAIRS, ids=range(len(DISTANCE_PAIRS)))
def test_distance_mm_bit_exact(case) -> None:
    ax, ay, bx, by = case
    expected = ORACLE._distance_mm((ax, ay), (bx, by))
    assert sig(rust("slop_distance_mm_py")(ax, ay, bx, by)) == sig(expected)


@pytest.mark.parametrize("case", DISTANCE_PAIRS, ids=range(len(DISTANCE_PAIRS)))
def test_vector_bit_exact(case) -> None:
    ax, ay, bx, by = case
    expected = ORACLE._vector((ax, ay), (bx, by))
    assert sig(rust("slop_vector_py")(ax, ay, bx, by)) == sig(expected)


@pytest.mark.parametrize("case", ANGLE_CASES, ids=range(len(ANGLE_CASES)))
def test_angle_between_bit_exact(case) -> None:
    expected = ORACLE._angle_between(
        ((case[0], case[1]), (case[2], case[3])),
        ((case[4], case[5]), (case[6], case[7])),
    )
    assert sig(rust("slop_angle_between_py")(*case)) == sig(expected)


def test_distance_mm_random_sweep() -> None:
    fn = rust("slop_distance_mm_py")
    for ax, ay, bx, by in random_distance_pairs(2000):
        assert sig(fn(ax, ay, bx, by)) == sig(ORACLE._distance_mm((ax, ay), (bx, by)))


def test_angle_between_random_sweep() -> None:
    fn = rust("slop_angle_between_py")
    for case in random_angle_cases(2000):
        expected = ORACLE._angle_between(
            ((case[0], case[1]), (case[2], case[3])),
            ((case[4], case[5]), (case[6], case[7])),
        )
        assert sig(fn(*case)) == sig(expected)


# ---------------------------------------------------------------------------
# slop_linter — _order_traces (insertion-order dependent)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name,segments", ORDER_TRACE_SETS, ids=[n for n, _ in ORDER_TRACE_SETS])
def test_order_traces_bit_exact(name: str, segments) -> None:
    """Ordering is a value here, not a presentation detail.

    ``_order_traces`` is greedy over the input list and breaks ties by earliest
    index, so a Rust port that iterates a different way produces a different
    (still plausible) chain.  The signature comparison covers the full ordered
    sequence, including which segments were reversed.
    """
    expected = ORACLE._order_traces(FX.as_trace_dicts(segments))
    got = rust("slop_order_traces_py")(list(segments))
    assert sig([(t["start"], t["end"]) for t in expected]) == sig(got)


def test_order_traces_random_sweep() -> None:
    fn = rust("slop_order_traces_py")
    for n in (2, 3, 5, 8, 13, 21, 34):
        segments = random_trace_set(n)
        expected = ORACLE._order_traces(FX.as_trace_dicts(segments))
        assert sig([(t["start"], t["end"]) for t in expected]) == sig(fn(list(segments)))


# ---------------------------------------------------------------------------
# via_count — classification helpers
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case", BBOX_CASES, ids=range(len(BBOX_CASES)))
def test_is_via_in_bbox_bit_exact(case) -> None:
    x, y, bboxes = case
    via = FX.FakeVia(position=(x, y), net="N", layers=("F.Cu", "B.Cu"))
    expected = ORACLE._is_via_in_bbox(via, bboxes)
    assert sig(rust("via_count_is_via_in_bbox_py")(x, y, list(bboxes))) == sig(expected)


@pytest.mark.parametrize("case", EDGE_MARGIN_CASES, ids=range(len(EDGE_MARGIN_CASES)))
def test_is_via_near_board_edge_bit_exact(case) -> None:
    vx, vy, x_min, y_min, x_max, y_max, margin = case
    via = FX.FakeVia(position=(vx, vy), net="GND", layers=("F.Cu", "B.Cu"))
    expected = ORACLE._is_via_near_board_edge(via, (x_min, y_min, x_max, y_max), margin)
    got = rust("via_count_is_via_near_board_edge_py")(vx, vy, x_min, y_min, x_max, y_max, margin)
    assert sig(got) == sig(expected)


# ---------------------------------------------------------------------------
# Whole-board scenarios — all three modules on synthetic inputs
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name,scenario", SCENARIOS, ids=[n for n, _ in SCENARIOS])
def test_classify_vias_bit_exact(name: str, scenario) -> None:
    expected = ORACLE._classify_vias(FX.build(scenario))
    got = rust("via_count_classify_vias_py")(scenario)
    assert sig(got) == sig((expected.signal, expected.thermal, expected.stitching, expected.total))


@pytest.mark.parametrize("name,scenario", SCENARIOS, ids=[n for n, _ in SCENARIOS])
def test_lint_all_bit_exact(name: str, scenario, monkeypatch) -> None:
    """``lint_all`` end-to-end, including every ``description`` string.

    The strings are compared, not ignored: they carry the ``:.1f``/``:.2f``
    formatting that catalog B3 makes divergent between the two languages.
    """
    FX.patched_parse(monkeypatch, ORACLE, FX.build(scenario))
    expected = ORACLE.lint_all("<synthetic>")
    assert sig(rust("slop_lint_all_py")(scenario)) == sig(expected)


@pytest.mark.parametrize("name,scenario", SCENARIOS, ids=[n for n, _ in SCENARIOS])
def test_lint_per_check_bit_exact(name: str, scenario, monkeypatch) -> None:
    """Each linter separately, so a failure names the artifact class."""
    FX.patched_parse(monkeypatch, ORACLE, FX.build(scenario))
    for oracle_fn, rust_name in (
        (ORACLE.lint_hairpin_turns, "slop_lint_hairpin_turns_py"),
        (ORACLE.lint_zigzag_patterns, "slop_lint_zigzag_patterns_py"),
        (ORACLE.lint_isolated_vias, "slop_lint_isolated_vias_py"),
        (ORACLE.lint_single_net_detours, "slop_lint_single_net_detours_py"),
    ):
        assert sig(rust(rust_name)(scenario)) == sig(oracle_fn("<synthetic>"))


def test_lint_all_ordering_follows_insertion_order(monkeypatch) -> None:
    """Finding ORDER tracks parser trace order, and must not be sorted.

    ``many_nets_insertion_order`` and ``..._swapped`` are the same four traces
    in two orders.  A Rust port that sorts its per-net map produces the same
    finding SET in a different sequence, which this catches and a set-based
    comparison would not.
    """
    by_name = dict(SCENARIOS)
    fn = rust("slop_lint_all_py")
    a_scenario = by_name["many_nets_insertion_order"]
    b_scenario = by_name["many_nets_insertion_order_swapped"]

    FX.patched_parse(monkeypatch, ORACLE, FX.build(a_scenario))
    oracle_a = ORACLE.lint_all("<synthetic>")
    FX.patched_parse(monkeypatch, ORACLE, FX.build(b_scenario))
    oracle_b = ORACLE.lint_all("<synthetic>")

    assert [f["net_name"] for f in oracle_a] != [f["net_name"] for f in oracle_b]
    assert sig(fn(a_scenario)) == sig(oracle_a)
    assert sig(fn(b_scenario)) == sig(oracle_b)


# ---------------------------------------------------------------------------
# Real corpus boards — the end-to-end parity cases
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("board", CORPUS_BOARDS, ids=lambda b: b["board_id"])
def test_corpus_board_parity(board: dict) -> None:
    """All three modules against the five real ``power_pcb_dataset`` boards."""
    from pathlib import Path

    from temper_placer.io.kicad_parser import parse_kicad_pcb

    repo_root = Path(__file__).resolve().parents[4]
    pcb = repo_root / board["pcb"]
    result = parse_kicad_pcb(pcb)

    counts = ORACLE._classify_vias(result)
    assert sig(rust("via_count_classify_vias_py")(str(pcb))) == sig(
        (counts.signal, counts.thermal, counts.stitching, counts.total)
    )
    assert sig(rust("slop_lint_all_py")(str(pcb))) == sig(ORACLE.lint_all(pcb))
