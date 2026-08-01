"""Differential tests: temper-quality-oracle Rust routing-quality score vs
the pure-Python reference (temper_placer/metrics/routing_quality.py,
Wave 4 Phase A #1 — the composite routing-quality score).

The pre-migration implementation is pinned here as an oracle (verbatim
semantics, including the exact f64 operation order: left-to-right
sum ``(completion_score + drc_score) + efficiency_score``, the Python
``max(0.0, min(1.0, x))`` clamp, and int→float promotion at the exact
same points).  Any change to the Rust kernel
(packages/temper-quality-oracle/src/routing_quality.rs) or the Python
delegation that disagrees with the oracle fails here, bit-exactly.

The direct ``temper_quality_oracle`` pins fail first (the crate is not
yet built with the new function); the module-level pins exercise the
full delegation path once wired.
"""

from __future__ import annotations

import random

import pytest
import temper_quality_oracle as _tqo

from temper_placer.metrics.routing_quality import (
    RoutingQualityScore,
    evaluate_routing_quality,
)

# ---------------------------------------------------------------------------
# Oracle (pre-migration implementation, verbatim)
# ---------------------------------------------------------------------------


def _oracle_score(completion, vias, drc, net_count):
    """Verbatim scalar core of the pre-migration scoring math."""
    completion_score = completion * 60
    drc_score = 20 if drc == 0 else 0
    if net_count > 0:
        vias_per_net = vias / net_count
        via_penalty = max(0.0, min(1.0, (vias_per_net - 2) / 8))
        efficiency_score = 20 * (1.0 - via_penalty)
    else:
        efficiency_score = 20.0
    return completion_score + drc_score + efficiency_score


def _oracle_evaluate_routing_quality(routing_result, drc_result):
    """Verbatim pre-migration ``evaluate_routing_quality``."""
    completion = routing_result.completion_rate
    vias = routing_result.total_vias
    length = routing_result.total_wirelength
    drc = drc_result.error_count

    is_acceptable = completion >= 0.8 and drc == 0

    completion_score = completion * 60
    drc_score = 20 if drc == 0 else 0

    net_count = len(routing_result.routed_nets) + len(routing_result.failed_nets)
    if net_count > 0:
        vias_per_net = vias / net_count
        via_penalty = max(0.0, min(1.0, (vias_per_net - 2) / 8))
        efficiency_score = 20 * (1.0 - via_penalty)
    else:
        efficiency_score = 20.0

    score = completion_score + drc_score + efficiency_score

    return RoutingQualityScore(
        completion_rate=completion,
        via_count=vias,
        total_length=length,
        drc_violations=drc,
        is_acceptable=is_acceptable,
        score=float(score),
    )


class _ResultStub:
    """Attribute stub standing in for VerificationResult / DrcResult."""

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


def _random_input(rng):
    completion = rng.choice(
        [
            rng.uniform(0.0, 1.0),
            rng.choice([0.0, 0.5, 0.79, 0.8, 0.81, 1.0]),
        ]
    )
    vias = rng.randint(0, 500)
    drc = rng.randint(0, 20)
    net_count = rng.randint(0, 200)
    return completion, vias, drc, net_count


# ---------------------------------------------------------------------------
# Direct Rust pins (bit-exact float equality)
# ---------------------------------------------------------------------------

_RNG = random.Random(0xC0FFEE)


@pytest.mark.parametrize("seed", range(20))
def test_direct_score_bit_exact(seed):
    """Rust kernel score == oracle score, bit-exact, over random inputs."""
    rng = random.Random(seed)
    for _ in range(50):
        completion, vias, drc, net_count = _random_input(rng)
        expected = _oracle_score(completion, vias, drc, net_count)
        got = _tqo.routing_quality_score_py(completion, vias, drc, net_count)
        assert got == expected, (
            f"score mismatch on completion={completion!r} vias={vias} "
            f"drc={drc} net_count={net_count}: rust={got!r} oracle={expected!r}"
        )


def test_direct_score_known_values():
    """Hand-computed values (exact f64 in both implementations)."""
    # completion=1.0, vias=0, drc=0, net_count=10: completion 60 + drc 20
    # + efficiency (0 vias/net => via_penalty 0 => 20) = 100.0
    assert _tqo.routing_quality_score_py(1.0, 0, 0, 10) == 100.0
    # completion=0.5 => completion_score 30.0; drc=3 => drc_score 0;
    # net_count=0 => efficiency 20.0  => 50.0
    assert _tqo.routing_quality_score_py(0.5, 10, 3, 0) == 50.0
    # via_penalty clamp upper: vias=100, net_count=10 => vias_per_net=10.0
    # => (10-2)/8 = 1.0 => via_penalty 1.0 => efficiency 0.0
    assert _tqo.routing_quality_score_py(0.0, 100, 0, 10) == 20.0
    # via_penalty clamp lower: vias=0, net_count=10 => (0-2)/8 = -0.25 => 0.0
    assert _tqo.routing_quality_score_py(0.0, 0, 0, 10) == 40.0
    # boundary: completion=0.8 => 48.0, drc=0 => 20.0, vias=2 net=1 => 0 pen
    assert _tqo.routing_quality_score_py(0.8, 2, 0, 1) == 88.0


def test_direct_score_int_float_promotion():
    """int via/net inputs promote identically to the Python true-division."""
    # vias/net_count with net_count == 0 is never reached in the kernel
    # (guarded by net_count > 0), so a direct 0 net_count returns 20.0 eff.
    # 15.0 (completion) + 20.0 (drc) + 20.0 (zero-net eff) == 55.0
    assert _tqo.routing_quality_score_py(0.25, 0, 0, 0) == 55.0


# ---------------------------------------------------------------------------
# Module-level pins (full delegation path)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("seed", range(10))
def test_module_level_bit_exact(seed):
    """evaluate_routing_quality (delegating) == oracle, full dataclass."""
    rng = random.Random(1000 + seed)
    for _ in range(25):
        completion, vias, drc, net_count = _random_input(rng)
        routed_n = rng.randint(0, net_count)
        routed_nets = [f"N{i}" for i in range(routed_n)]
        failed_nets = [f"F{i}" for i in range(net_count - routed_n)]
        routing_result = _ResultStub(
            completion_rate=completion,
            total_vias=vias,
            total_wirelength=rng.uniform(0.0, 2000.0),
            routed_nets=routed_nets,
            failed_nets=failed_nets,
        )
        drc_result = _ResultStub(error_count=drc)

        expected = _oracle_evaluate_routing_quality(routing_result, drc_result)
        got = evaluate_routing_quality(routing_result, drc_result)

        assert got.completion_rate == expected.completion_rate
        assert got.via_count == expected.via_count
        assert got.total_length == expected.total_length
        assert got.drc_violations == expected.drc_violations
        assert got.is_acceptable == expected.is_acceptable
        assert got.score == expected.score, (
            f"score mismatch: rust={got.score!r} oracle={expected.score!r} "
            f"on completion={completion!r} vias={vias} drc={drc} net_count={net_count}"
        )
        assert got.to_dict() == expected.to_dict()


def test_module_level_threshold_sweep():
    """Completion sweep around the 0.8 acceptability threshold."""
    for completion in (0.0, 0.5, 0.79, 0.8, 0.81, 0.99, 1.0):
        routing_result = _ResultStub(
            completion_rate=completion,
            total_vias=4,
            total_wirelength=120.0,
            routed_nets=["N1", "N2", "N3", "N4"],
            failed_nets=["N5"],
        )
        drc_result = _ResultStub(error_count=0)
        expected = _oracle_evaluate_routing_quality(routing_result, drc_result)
        got = evaluate_routing_quality(routing_result, drc_result)
        assert got == expected
        assert got.is_acceptable == (completion >= 0.8)
