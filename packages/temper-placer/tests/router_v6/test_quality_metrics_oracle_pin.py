"""Integrity of the cluster-F pinned oracle (gate G1's precondition).

The differential suite (``test_quality_metrics_rust_differential.py``) proves
that the Rust kernel reproduces the oracle.  That proof is worth nothing if the
oracle has drifted from the code it claims to pin, or if the corpus numbers it
compares against were quietly re-baselined.  This file closes both holes, and
is the only one of the three cluster-F suites that is **green before the Rust
exists**:

* :func:`test_oracle_is_verbatim_copy` re-runs ``git show`` against the pinned
  base commit and asserts every copied symbol is byte-identical.
* :func:`test_oracle_omits_only_io_delegation` asserts the omitted symbols are
  exactly the documented pure-I/O set -- so a future edit cannot quietly drop
  a kernel and call it "delegation".
* The corpus-pin tests assert the oracle still reproduces the numbers recorded
  in ``_quality_metrics_cases.CORPUS_BOARDS``.
* :func:`test_signature_discriminates` proves the comparator this cluster
  relies on is not silently degrading into ``==``.
* The ``test_trap_*`` measurements quantify the catalog §2 divergence classes
  (B3/B4/B5/B7) that cluster F is exposed to, so the Rust side has numbers to
  aim at rather than claims.
* The benchmark-corpus containment assertions (R1b) prove the perf A/B can
  never time an input the differential has not compared.

Why a fourth file exists
------------------------
The differential suite is required to be **entirely red** until the Rust
lands, so that a skip can never be mistaken for a pass.  Tests that must be
green today therefore cannot live in it.  That includes the trap measurements
and the corpus-containment assertions, which PR #732 keeps inside its
differential -- they are single-arm assertions about CPython and about the
corpus, so leaving them there would make the differential report
"381 failed, 8 passed" and turn its red state into something you have to read
a count to confirm.  Splitting them out keeps "red" and "green" as whole-file
properties, which is what makes the red state checkable at a glance.
"""

from __future__ import annotations

import ast
import math
import subprocess
from pathlib import Path

import pytest

import tests.router_v6._quality_metrics_fixtures as FX
import tests.router_v6._quality_metrics_py_oracle as ORACLE
from tests.router_v6._quality_metrics_cases import (
    ANGLE_CASES,
    BENCH_ANGLE_CASES,
    BENCH_CORPUS_BOARDS,
    BENCH_DISTANCE_PAIRS,
    BENCH_SCENARIOS,
    CORPUS_BOARDS,
    DISTANCE_PAIRS,
    SCENARIOS,
    random_distance_pairs,
)
from tests.router_v6._signature import sig

# The commit the oracle is pinned to.  Changing this is a re-pin, not an edit:
# it must be accompanied by a fresh `git show` of every symbol below.
BASE_SHA = "15110feccc6ec9389f0777d3cff1ce9f81b11068"

_ROOT = "packages/temper-placer/src/temper_placer/router_v6"

#: Symbols copied verbatim, per source file, in source order.
PINNED_SYMBOLS: dict[str, tuple[str, ...]] = {
    f"{_ROOT}/metrics/slop_linter.py": (
        "lint_hairpin_turns",
        "lint_zigzag_patterns",
        "lint_isolated_vias",
        "lint_single_net_detours",
        "lint_all",
        "_parse_pcb",
        "_load_traces_by_net",
        "_order_traces",
        "_vector",
        "_angle_between",
        "_distance_mm",
    ),
    f"{_ROOT}/quality/corridor.py": (
        "Channel",
        "TrackSegment",
        "_compute_consolidation",
        "_compute_spread",
        "_Courtyard",
        "_compute_courtyards",
        "_identify_channels",
        "_assign_tracks_to_channels",
        "_overlap",
        "_gap",
        "_point_in_rect",
    ),
    f"{_ROOT}/quality/via_count.py": (
        "ViaCounts",
        "classify_vias_from_parse",
        "_classify_vias",
        "_get_component_bboxes",
        "_get_board_bbox",
        "_is_via_in_bbox",
        "_is_via_near_board_edge",
        "count_signal_vias_from_routing",
    ),
}

#: Symbols deliberately NOT copied.  Every one is pure I/O delegation; the
#: oracle header explains each.  Asserted exhaustively so a kernel cannot be
#: dropped under cover of this list.
OMITTED_SYMBOLS: dict[str, tuple[str, ...]] = {
    f"{_ROOT}/metrics/slop_linter.py": (),
    f"{_ROOT}/quality/corridor.py": (
        "_parse_pcb",
        "corridor_consolidation_score",
        "track_spread_score",
        "corridor_consolidation_from_parse",
        "track_spread_from_parse",
    ),
    f"{_ROOT}/quality/via_count.py": (
        "_parse_pcb",
        "count_signal_vias",
        "count_thermal_vias",
        "count_stitching_vias",
        "classify_vias",
    ),
}

_REPO_ROOT = Path(__file__).resolve().parents[4]


def _git_show(path: str) -> str:
    return subprocess.run(
        ["git", "show", f"{BASE_SHA}:{path}"],
        capture_output=True,
        text=True,
        check=True,
        cwd=_REPO_ROOT,
    ).stdout


def _source_segments(src: str) -> dict[str, str]:
    """Map top-level def/class name -> its exact source text."""
    tree = ast.parse(src)
    lines = src.splitlines()
    out: dict[str, str] = {}
    for node in tree.body:
        name = getattr(node, "name", None)
        if name is None:
            continue
        decorators = getattr(node, "decorator_list", [])
        start = (min(d.lineno for d in decorators) - 1) if decorators else (node.lineno - 1)
        out[name] = "\n".join(lines[start : node.end_lineno])
    return out


@pytest.fixture(scope="module")
def oracle_segments() -> dict[str, str]:
    return _source_segments(Path(ORACLE.__file__).read_text())


@pytest.mark.parametrize("path", sorted(PINNED_SYMBOLS))
def test_oracle_is_verbatim_copy(path: str, oracle_segments: dict[str, str]) -> None:
    """Every pinned symbol is byte-identical to the source at ``BASE_SHA``.

    This is the assertion that makes the "do not edit" header enforceable
    rather than aspirational.
    """
    upstream = _source_segments(_git_show(path))
    for name in PINNED_SYMBOLS[path]:
        assert name in upstream, f"{path}: {name} no longer exists at {BASE_SHA}"
        assert name in oracle_segments, f"oracle is missing {name} from {path}"
        assert oracle_segments[name] == upstream[name], (
            f"{path}::{name} has DRIFTED from the pinned base {BASE_SHA}. "
            "The oracle must be a verbatim copy -- re-pin it from a new base "
            "commit rather than editing it in place."
        )


@pytest.mark.parametrize("path", sorted(PINNED_SYMBOLS))
def test_oracle_omits_only_io_delegation(path: str) -> None:
    """Pinned + omitted accounts for every top-level symbol in each source.

    Prevents a future edit from dropping a compute kernel and describing it as
    delegation: anything that is neither pinned nor on the documented omission
    list fails here.
    """
    upstream = set(_source_segments(_git_show(path)))
    accounted = set(PINNED_SYMBOLS[path]) | set(OMITTED_SYMBOLS[path])
    unaccounted = upstream - accounted
    assert not unaccounted, (
        f"{path}: {sorted(unaccounted)} is neither pinned in the oracle nor on "
        "the documented I/O-delegation omission list"
    )


@pytest.mark.parametrize("path", sorted(OMITTED_SYMBOLS))
def test_omitted_symbols_contain_no_arithmetic(path: str) -> None:
    """Each omitted symbol really is delegation: no arithmetic, no comparison.

    The justification for omitting them is that they carry zero of the
    bit-exactness risk the differential exists to manage.  That is checked, not
    asserted: an omitted function whose *body* contains a ``BinOp``,
    ``Compare`` or ``BoolOp`` would be a kernel in disguise.

    Only the body is walked.  Annotations are not code: ``float | None`` parses
    as a ``BinOp`` and would otherwise flag every one of these signatures.
    """
    src = _git_show(path)
    tree = ast.parse(src)
    for node in tree.body:
        if getattr(node, "name", None) not in OMITTED_SYMBOLS[path]:
            continue
        offenders = [
            type(sub).__name__
            for stmt in node.body
            for sub in ast.walk(stmt)
            if isinstance(sub, (ast.BinOp, ast.Compare, ast.BoolOp))
            and not isinstance(sub, ast.expr_context)
        ]
        assert not offenders, (
            f"{path}::{node.name} was omitted from the oracle as pure I/O "
            f"delegation but its body contains {offenders}"
        )


# ---------------------------------------------------------------------------
# Corpus pins -- the oracle still produces the numbers the corpus records.
# ---------------------------------------------------------------------------


def _parse(board: dict):
    from temper_placer.io.kicad_parser import parse_kicad_pcb

    return parse_kicad_pcb(_REPO_ROOT / board["pcb"])


@pytest.mark.parametrize("board", CORPUS_BOARDS, ids=lambda b: b["board_id"])
def test_corpus_via_counts_match_pin(board: dict) -> None:
    counts = ORACLE._classify_vias(_parse(board))
    assert sig(counts.signal) == sig(board["via_signal"])
    assert sig(counts.thermal) == sig(board["via_thermal"])
    assert sig(counts.stitching) == sig(board["via_stitching"])
    assert sig(counts.total) == sig(board["via_total"])


@pytest.mark.parametrize("board", CORPUS_BOARDS, ids=lambda b: b["board_id"])
def test_corpus_via_total_matches_human_reference_baseline(board: dict) -> None:
    """The one free parity check the recorded baselines actually provide.

    ``power_pcb_dataset/corpus/*/human_reference.yaml`` records a ``via_count``
    metric.  It equals ``ViaCounts.total`` on all five boards, so it
    corroborates the oracle's total independently of anything in this branch.

    It corroborates ONLY the total.  The baselines were extracted at
    ``extractor_version: 804b808a`` and predate
    ``human_reference_extractor``'s cluster-F metrics, so they contain no
    ``signal_via_count``, ``thermal_via_count``, ``stitching_via_count``,
    ``corridor_consolidation_score`` or ``track_spread_score`` to check
    against.  :func:`test_baselines_lack_cluster_f_metrics` pins that absence
    so the gap cannot be mistaken for coverage.
    """
    counts = ORACLE._classify_vias(_parse(board))
    assert float(counts.total) == board["human_reference_via_count"]


@pytest.mark.parametrize("board", CORPUS_BOARDS, ids=lambda b: b["board_id"])
def test_baselines_lack_cluster_f_metrics(board: dict) -> None:
    """Pin the *absence* of cluster-F metrics from the recorded baselines.

    An honestly named gap.  If a future extraction adds them, this test fails
    and the differential should gain five more free parity cases per board.
    """
    import yaml

    path = _REPO_ROOT / Path(board["pcb"]).parent / "human_reference.yaml"
    metrics = yaml.safe_load(path.read_text())["metrics"]
    absent = {
        "signal_via_count",
        "thermal_via_count",
        "stitching_via_count",
        "corridor_consolidation_score",
        "track_spread_score",
    }
    present = absent & set(metrics)
    assert not present, (
        f"{board['board_id']}: human_reference.yaml now records {sorted(present)}. "
        "These are free parity cases -- add them to CORPUS_BOARDS and to the "
        "differential suite."
    )


@pytest.mark.parametrize("board", CORPUS_BOARDS, ids=lambda b: b["board_id"])
def test_corpus_corridor_scores_match_pin(board: dict) -> None:
    result = _parse(board)
    consolidation = ORACLE._compute_consolidation(result, None, None, None)
    spread = ORACLE._compute_spread(result, None, None, None)
    assert consolidation.hex() == board["consolidation_hex"]
    assert spread.hex() == board["spread_hex"]


@pytest.mark.parametrize("board", CORPUS_BOARDS, ids=lambda b: b["board_id"])
def test_corpus_lint_counts_match_pin(board: dict) -> None:
    findings = ORACLE.lint_all(_REPO_ROOT / board["pcb"])
    assert len(findings) == board["lint_total"]
    by_type: dict[str, int] = {}
    for finding in findings:
        by_type[finding["type"]] = by_type.get(finding["type"], 0) + 1
    assert by_type == board["lint_by_type"]


@pytest.mark.parametrize("board", CORPUS_BOARDS, ids=lambda b: b["board_id"])
def test_corpus_shapes_match_pin(board: dict) -> None:
    result = _parse(board)
    assert len(result.vias) == board["n_vias"]
    assert len(result.traces) == board["n_traces"]
    assert len(result.netlist.components) == board["n_components"]
    assert len(ORACLE._load_traces_by_net(_REPO_ROOT / board["pcb"])) == board["n_nets"]


def test_corridor_is_degenerate_on_four_of_five_corpus_boards() -> None:
    """Pin defect (2): the corridor kernels are dead on real boards.

    Courtyards come from ``comp.initial_position`` (board-relative) while
    tracks come from ``trace.start``/``.end`` (page-absolute), so on four of
    the five corpus boards no track is ever assigned to any channel and both
    scores collapse to their empty-input constants.

    This is pinned, not fixed -- fixing it would break the verbatim oracle.
    The value of pinning it is that the Rust port must reproduce the
    degeneracy, and that a later coordinate-frame fix will fail here loudly
    instead of silently changing a published metric.
    """
    degenerate = [
        b["board_id"]
        for b in CORPUS_BOARDS
        if b["consolidation_hex"] == (1.0).hex() and b["spread_hex"] == (0.0).hex()
    ]
    assert sorted(degenerate) == [
        "bitaxe_ultra",
        "minimal",
        "rp2040_designguide",
        "temper",
    ]


def test_identify_channels_else_arm_is_unreachable() -> None:
    """Pin defect (3): both ``else`` arms of ``_identify_channels`` are dead.

    ``gap`` is ``cb.y_min - ca.y_max``; the guard ``gap > min_gap_width_mm``
    with a positive threshold already implies ``ca.y_max < cb.y_min``, so the
    ``if`` always wins.  The consequence is a real behavioural asymmetry the
    Rust port must reproduce: a channel is found only when the earlier-listed
    component is the lower (or left) one.
    """
    lower_first = [
        ORACLE._Courtyard(ref="U1", x_min=0.0, y_min=0.0, x_max=10.0, y_max=0.0),
        ORACLE._Courtyard(ref="U2", x_min=0.0, y_min=5.0, x_max=10.0, y_max=15.0),
    ]
    upper_first = list(reversed(lower_first))
    min_gap = 3.0 * (0.2 + 0.15)
    assert len(ORACLE._identify_channels(lower_first, min_gap)) == 1
    assert len(ORACLE._identify_channels(upper_first, min_gap)) == 0


def test_classify_vias_signal_accumulator_is_dead() -> None:
    """Pin defect (1): ``_classify_vias``'s ``signal`` accumulator is dead.

    ``signal`` is unconditionally overwritten by ``total - thermal -
    stitching``, so the ``is_signal_net`` branch cannot affect the result.
    Witness: a board of vias on nets that are neither signal, thermal, nor
    stitching still reports every one of them as ``signal``.
    """
    result = FX.build(
        {
            "traces": [],
            # Power nets, mid-board: not thermal (wrong net), not stitching
            # (not ground, not near an edge), and NOT signal either.
            "vias": [
                ((50.0, 50.0), "+3V3", ("F.Cu", "B.Cu")),
                ((50.0, 50.0), "+5V", ("F.Cu", "B.Cu")),
            ],
            "components": [],
            "board": (100.0, 100.0),
        }
    )
    counts = ORACLE._classify_vias(result)
    assert counts.thermal == 0
    assert counts.stitching == 0
    assert counts.signal == 2  # despite is_signal_net() being False for both
    assert not ORACLE.is_signal_net("+3V3")


def test_zigzag_window_all_call_is_never_reachable_empty() -> None:
    """Resolves ``scripts/check_vacuous_gates.py``'s finding at this file's
    ``lint_zigzag_patterns`` line ``alternating = all(dirs[j] != dirs[j + 1]
    for j in range(len(dirs) - 1))`` -- NOT a real defect, proven here rather
    than fixed in place.

    That gate flags any unguarded ``all(...)`` because ``all(())`` is
    vacuously ``True``.  It cannot see that ``dirs`` there is built from
    ``window = turns[start : start + 3]`` for ``start in range(len(turns) -
    3 + 1)`` -- and Python slicing guarantees ``len(seq[a : a + N]) == N``
    whenever ``0 <= a <= len(seq) - N``, exactly the range that loop
    produces for ``a``. So whenever the loop body executes at all, ``window``
    (and ``dirs``, built one-to-one from it) has EXACTLY 3 elements, never
    fewer -- ``range(len(dirs) - 1)`` is ``range(2)``, never empty. When
    ``len(turns) < 3``, ``range(len(turns) - 3 + 1)`` is itself empty, so the
    loop body -- and the flagged line -- never executes at all that trip.
    There is no path to an empty ``dirs`` reaching that ``all()``.

    ``lint_zigzag_patterns`` is a byte-pinned symbol (verified by
    ``test_oracle_is_verbatim_copy`` above); it cannot be edited to add an
    inline guard the gate's syntactic heuristic would recognize without
    breaking the pin. This test is this module's existing "Known defects,
    deliberately preserved" convention applied to a *non*-defect: prove the
    property structurally instead of guarding it inline, since the site
    itself must stay verbatim. The proof is generic over ``turns`` length
    (not tied to any specific board/content), because the claim is about
    Python's slicing semantics, not about any one input.
    """
    for n in range(0, 25):
        turns = list(range(n))  # content is irrelevant -- only length matters
        window_count = 0
        for start in range(len(turns) - 3 + 1):
            window = turns[start : start + 3]
            assert len(window) == 3, f"n={n} start={start}: window had {len(window)} elements"
            dirs = list(window)
            assert len(dirs) - 1 >= 1, "range(len(dirs) - 1) would be empty here"
            window_count += 1
        # The loop -- and the flagged all() -- runs at all iff n >= 3.
        assert (window_count > 0) == (n >= 3)


def test_single_layer_mode_is_at_its_default() -> None:
    """``_classify_vias`` has a hidden module-global input; pin it.

    ``is_ground_net``/``is_signal_net`` branch on
    ``net_classification._SINGLE_LAYER_MODE``.  Every corpus pin above was
    taken with it ``False``.  The Rust port must take this as an explicit
    input rather than inheriting a process global.
    """
    from temper_placer.router_v6 import net_classification

    assert net_classification._SINGLE_LAYER_MODE is False


# ---------------------------------------------------------------------------
# Comparator self-test -- ``_signature.sig`` must not degrade into ``==``.
# ---------------------------------------------------------------------------


def test_signature_discriminates() -> None:
    """The discriminations the cluster-F differential depends on.

    ``_signature.py`` is vendored from PR #732 (unmerged at the time of
    writing); this is a compact restatement of the self-test that lives there,
    covering the cases cluster F actually relies on.
    """
    # signed zero
    assert sig(0.0) != sig(-0.0)
    # 1-ulp neighbours
    assert sig(1.0) != sig(math.nextafter(1.0, 2.0))
    # bool vs int
    assert sig(True) != sig(1)
    # int vs float that compare equal
    assert sig(1) != sig(1.0)
    # tuple vs list
    assert sig((1, 2)) != sig([1, 2])
    # NaN is equal to itself under sig (unlike ==), which is what lets the
    # differential assert NaN parity at all
    assert sig(float("nan")) == sig(float("nan"))
    assert float("nan") != float("nan")
    # dict ORDER is part of the value -- the property that catches a Rust port
    # which sorts the per-net map
    assert sig({"a": 1, "b": 2}) != sig({"b": 2, "a": 1})
    # strings and None round-trip
    assert sig("x") != sig(None)
    # inf vs finite
    assert sig(float("inf")) != sig(1e308)


# ---------------------------------------------------------------------------
# Trap measurements (catalog §2) — these quantify the divergence classes
# rather than asserting them, so the Rust side has numbers to aim at.
# ---------------------------------------------------------------------------


def test_trap_hypot_is_not_naive_sqrt() -> None:
    """B4: CPython ``math.hypot`` differs from ``sqrt(dx*dx + dy*dy)``.

    Measured, not assumed.  Every ``_distance_mm`` and ``_angle_between`` call
    site is the Dekker form; a Rust port using ``f64::hypot`` or the naive
    square-root diverges on this fraction of ordinary board coordinates.
    """
    disagreements = 0
    pairs = random_distance_pairs(5000, seed=424242)
    for ax, ay, bx, by in pairs:
        dx, dy = ax - bx, ay - by
        if math.hypot(dx, dy) != math.sqrt(dx * dx + dy * dy):
            disagreements += 1
    assert disagreements > 0, (
        "math.hypot and the naive sqrt agreed on all 5000 sampled pairs; the "
        "B4 trap would then be inert for this cluster and this test should be "
        "re-examined rather than deleted"
    )


def test_trap_variadic_min_keeps_first_nan() -> None:
    """B5: the discriminating witness for ``_is_via_near_board_edge``.

    CPython's variadic ``min`` returns its FIRST argument when that argument is
    NaN (every later ``<`` comparison is False), but returns a real value when
    the NaN arrives later.  A Rust fold over ``f64::min`` discards NaN and
    answers the same in both cases.
    """
    board = (0.0, 0.0, 100.0, 100.0)
    nan = float("nan")
    nan_first = FX.FakeVia(position=(nan, 1.0), net="GND", layers=("F.Cu", "B.Cu"))
    nan_later = FX.FakeVia(position=(1.0, nan), net="GND", layers=("F.Cu", "B.Cu"))
    assert ORACLE._is_via_near_board_edge(nan_first, board, 5.0) is False
    assert ORACLE._is_via_near_board_edge(nan_later, board, 5.0) is True


def test_trap_angle_clamp_keeps_first_on_nan() -> None:
    """B5: ``max(-1.0, min(1.0, NaN))`` is ``1.0``, so the angle is ``0.0``.

    ``f64::clamp`` panics on a NaN input and ``t.max(-1.0).min(1.0)`` yields
    NaN; only the oracle's min-then-max nesting gives ``0.0``.
    """
    nan = float("nan")
    angle = ORACLE._angle_between(((0.0, 0.0), (nan, 0.0)), ((0.0, 0.0), (1.0, 0.0)))
    assert angle == 0.0
    assert min(1.0, nan) == 1.0
    assert max(-1.0, 1.0) == 1.0


def test_trap_description_formatting_rounds_half_to_even() -> None:
    """B3: the ``description`` strings use CPython's half-to-even formatting.

    ``0.125`` renders as ``0.12`` under Python's ``:.2f`` but as ``0.13`` under
    Rust's ``format!("{:.2}")``.  These strings are compared by the scenario
    tests above, so this divergence class is live for this cluster even though
    ``round()`` is never called.
    """
    assert f"{0.125:.2f}" == "0.12"
    assert f"{0.375:.2f}" == "0.38"
    assert f"{2.5:.0f}" == "2"


def test_order_traces_is_insertion_order_sensitive() -> None:
    """Non-vacuity guard for the differential's ``_order_traces`` assertions.

    Those assertions compare the full ordered chain.  That only means anything
    if reordering the input can actually change the output -- otherwise any
    implementation would satisfy them.  It can.
    """
    segments = [(2.0, 0.0, 3.0, 0.0), (0.0, 0.0, 1.0, 0.0), (1.0, 0.0, 2.0, 0.0)]
    a = ORACLE._order_traces(FX.as_trace_dicts(segments))
    b = ORACLE._order_traces(FX.as_trace_dicts(list(reversed(segments))))
    assert [t["start"] for t in a] != [t["start"] for t in b]


def test_trap_channel_threshold_grouping() -> None:
    """B7: ``3.0 * (a + b)`` is not ``3.0 * a + 3.0 * b``.

    The channel threshold must be computed with the oracle's grouping.
    """
    assert 3.0 * (0.2 + 0.15) != 3.0 * 0.2 + 3.0 * 0.15
    assert 3.0 * (0.2 + 0.15) != 1.05


# ---------------------------------------------------------------------------
# Corpus containment (R1b) — the benchmark can never outrun the differential
# ---------------------------------------------------------------------------


def test_benchmark_corpus_is_covered_by_differential() -> None:
    """Every input the perf A/B will time has been compared bit-for-bit here.

    PR #714 passed its differential at iterations ``[0, 1, 2, 8, 17, 100]`` and
    then failed CI on a benchmark that ran 120.  This containment assertion is
    what makes that class of gap unreachable for cluster F.
    """
    assert set(map(tuple, BENCH_DISTANCE_PAIRS)) <= set(map(tuple, DISTANCE_PAIRS))
    assert set(map(tuple, BENCH_ANGLE_CASES)) <= set(map(tuple, ANGLE_CASES))
    assert {n for n, _ in BENCH_SCENARIOS} <= {n for n, _ in SCENARIOS}
    assert {b["board_id"] for b in BENCH_CORPUS_BOARDS} <= {b["board_id"] for b in CORPUS_BOARDS}


def test_benchmark_corpus_is_non_empty() -> None:
    """Containment is vacuous if the benchmark corpus is empty."""
    assert BENCH_DISTANCE_PAIRS
    assert BENCH_ANGLE_CASES
    assert BENCH_SCENARIOS
    assert BENCH_CORPUS_BOARDS
