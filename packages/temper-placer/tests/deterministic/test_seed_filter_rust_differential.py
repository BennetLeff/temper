"""Differential test: deterministic seed_filter, Rust vs oracle.

Wave 4, **Phase 5** (deterministic hubs slice). ``filter_seed`` — the pure
accept/reject loop over a seed candidate — moves to
``temper_design_bundle_python.deterministic_hubs.filter_seed_kernel``. The
Python module keeps its public API and delegates.

Bit-exactness pins:
- The kernel iterates the seed **in insertion order** (Python ``dict`` order,
  which the kernel preserves by iterating the ``PyDict`` — no sort is applied;
  the oracle's ``for ref, position in seed.items()`` is first-failure short
  circuit, so a permutation of the seed changes which ref is reported, but the
  accept/reject OUTCOME is order-invariant — the shuffled-seed test pins that
  empirically).
- ``score_at`` inside the kernel uses the same CPython floor-division as the
  BottleneckMap kernel (pinned by the bottleneck_map differential; cross-module
  parity asserted here for a bounded corpus).
- Empty seed trivially accepts (vacuity guard: asserted explicitly).
- ``score >= limit`` rejects at equality (strict comparator pinned).
"""

from __future__ import annotations

import random

import pytest
import temper_design_bundle_python as _tdb
import tests.deterministic._seed_filter_py_oracle as _oracle
from tests.core._contract_canon import canon, canon_call

# Rust symbols under test — must exist or this file fails to collect (RED).
_DH = _tdb.deterministic_hubs
RS_FILTER = _DH.filter_seed_kernel


def _oracle_map(cell=1.0, w=2, h=2, origin=(0.0, 0.0), scores=(0.1, 0.1, 0.1, 0.1)):
    return _oracle.BottleneckMap(
        cell_size_mm=cell, width=w, height=h, origin_xy=origin, scores=tuple(scores)
    )


def _rs_filter(seed, m, threshold, hv_threshold, hv_refs):
    return RS_FILTER(
        dict(seed),
        m.cell_size_mm,
        m.width,
        m.height,
        m.origin_xy[0],
        m.origin_xy[1],
        list(m.scores),
        threshold,
        hv_threshold,
        set(hv_refs),
    )


def _rand_seed(seed, n=8):
    rng = random.Random(seed)
    return {
        f"R{i}": (round(rng.uniform(-5, 5), 3), round(rng.uniform(-5, 5), 3)) for i in range(n)
    }


@pytest.mark.parametrize("seed", [0, 1, 2, 3, 5])
@pytest.mark.parametrize("thresholds", [(0.7, 0.5), (0.2, 0.9), (1.0, 0.0)])
def test_filter_seed_parity(seed, thresholds):
    m = _oracle_map(scores=(0.1, 0.8, 0.6, 0.2))
    seed_dict = _rand_seed(seed)
    hv_refs = frozenset(rng_choice(list(seed_dict), random.Random(seed + 99)))
    threshold, hv_threshold = thresholds
    o = _oracle.filter_seed(seed_dict, m, threshold, hv_threshold, hv_refs)
    s = _rs_filter(seed_dict, m, threshold, hv_threshold, hv_refs)
    assert s == o, f"filter divergence for seed {seed}: {s} vs {o}"


def _rng_choice(items, rng):
    return [items[i] for i in sorted(rng.sample(range(len(items)), max(1, len(items) // 2)))]


def rng_choice(items, rng):
    return _rng_choice(items, rng)


def test_filter_seed_outcome_order_invariant():
    """Shuffling the seed dict must not change the accept/reject outcome
    (first-failure short-circuit reports a DIFFERENT ref, but the boolean
    outcome is a fold over the same per-ref results)."""
    m = _oracle_map(scores=(0.1, 0.8, 0.6, 0.2))
    base = {"A": (0.5, 0.5), "B": (1.5, 0.5), "C": (0.5, 1.5), "D": (1.5, 1.5)}
    items = list(base.items())
    outcomes = set()
    for perm in random.sample(
        list(__import__("itertools").permutations(items)), min(24, 24)
    ):
        seed = dict(perm)
        o = _oracle.filter_seed(seed, m, 0.7, 0.5, frozenset({"A"}))
        s = _rs_filter(seed, m, 0.7, 0.5, frozenset({"A"}))
        outcomes.add((s, o))
    assert len(outcomes) == 1, f"outcome not order-invariant: {outcomes}"


def test_filter_seed_boundary_and_empty():
    m = _oracle_map(scores=(0.7,))
    # score == threshold rejects on both sides
    assert _oracle.filter_seed({"R1": (0.5, 0.5)}, m, 0.7, 0.5, frozenset()) is False
    assert _rs_filter({"R1": (0.5, 0.5)}, m, 0.7, 0.5, frozenset()) is False
    # empty seed is accepted (vacuously) on both sides
    m2 = _oracle_map(scores=(0.9,))
    assert _oracle.filter_seed({}, m2, 0.7, 0.5, frozenset()) is True
    assert _rs_filter({}, m2, 0.7, 0.5, frozenset()) is True
    # OOB clamps to 0.0 on both sides
    m3 = _oracle_map(scores=(0.9,))
    assert _oracle.filter_seed({"R1": (999.0, 999.0)}, m3, 0.7, 0.5, frozenset()) is True
    assert _rs_filter({"R1": (999.0, 999.0)}, m3, 0.7, 0.5, frozenset()) is True


def test_filter_seed_int_vs_float_positions():
    """Integer-typed positions (e.g. (65, 5)) must behave identically to their
    float twins — int-vs-float cannot hide behind numeric equality."""
    m = _oracle_map(cell=1.0, w=4, h=4, scores=tuple(0.5 for _ in range(16)))
    seed_int = {"R1": (1, 1)}
    seed_float = {"R1": (1.0, 1.0)}
    for threshold, hv_threshold, hv_refs in [(0.7, 0.5, frozenset()), (0.4, 0.6, frozenset())]:
        assert _rs_filter(seed_int, m, threshold, hv_threshold, hv_refs) == _oracle.filter_seed(
            seed_int, m, threshold, hv_threshold, hv_refs
        )
        assert _rs_filter(seed_float, m, threshold, hv_threshold, hv_refs) == _oracle.filter_seed(
            seed_float, m, threshold, hv_threshold, hv_refs
        )


def test_filter_seed_nonfinite_position_error_parity():
    """NaN/±inf seed positions raise the exact Python errors on both sides
    (the kernel's internal score lookup must not silently saturate)."""
    m = _oracle_map(scores=(0.1, 0.1, 0.1, 0.1))
    for pos in [
        (float("nan"), 0.5),
        (float("inf"), 0.5),
        (float("-inf"), 0.5),
        (1e308, 1e-320),  # quotient overflows to +inf -> OverflowError
    ]:
        o = canon_call(_oracle.filter_seed, {"R1": pos}, m, 0.7, 0.5, frozenset())
        s = canon_call(_rs_filter, {"R1": pos}, m, 0.7, 0.5, frozenset())
        assert s == o, f"non-finite divergence for {pos}: {s} vs {o}"


def test_filter_seed_cross_module_score_parity():
    """The kernel's internal score lookup must agree with the oracle's
    BottleneckMap.score_at over a small corpus (cross-module pin)."""
    from temper_placer.deterministic.bottleneck_map import BottleneckMap as ShimMap

    m_oracle = _oracle.BottleneckMap(
        cell_size_mm=2.0, width=3, height=3, origin_xy=(0.0, 0.0), scores=(0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)
    )
    m_shim = ShimMap(
        cell_size_mm=2.0, width=3, height=3, origin_xy=(0.0, 0.0), scores=(0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)
    )
    for (x, y) in [(0.0, 0.0), (2.0, 2.0), (1.9, 1.9), (5.9, 5.9), (6.0, 0.0), (-1.0, 1.0)]:
        seed = {"T": (x, y)}
        assert canon(_rs_filter(seed, m_shim, 1.0, 1.0, frozenset())) == canon(
            _oracle.filter_seed(seed, m_oracle, 1.0, 1.0, frozenset())
        )
