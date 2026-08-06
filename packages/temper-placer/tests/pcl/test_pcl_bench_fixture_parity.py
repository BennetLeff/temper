"""The #714 gate: the differential covers the benchmark's exact parameters.

PR #714 verified bit-parity on macOS, passed its differential at iterations
``[0,1,2,8,17,100]``, and then failed on Linux CI because its benchmark ran
120 iterations at lr 0.05 -- parameters the differential never drove.

This file closes that hole structurally rather than by convention: it imports
``_pcl_bench_fixture``, the *same* module ``benchmarks/perf_ab.py`` imports,
and asserts full oracle parity over every input the benchmark will time. The
benchmark therefore cannot reach an input this test has not already compared,
because there is only one source of inputs.

Platform caveat, stated rather than assumed: this ran on darwin/arm64 only.
Linux libm is not exercised here. The PCL kernels do no transcendental math
(``resolve`` is a boolean tree walk; the unit conversion is a single IEEE-754
multiply by an exactly-representable-in-both-languages decimal double), so
there is no libm surface for the platforms to differ on -- but "no libm calls"
is the argument, not "we measured Linux".
"""

from __future__ import annotations

import tests.pcl._parse_utils_py_oracle as _parse_oracle
import tests.pcl._tag_dispatch_py_oracle as _tag_oracle
from tests.pcl._pcl_bench_fixture import (
    bench_distance_inputs,
    bench_expr_specs,
    bench_netlist,
    bench_tier_inputs,
    build_expr,
)
from tests.pcl._pclsig import assert_same, call_signature

from temper_placer.pcl import _parse_utils as live_parse
from temper_placer.pcl import tag_dispatch as live


def _norm(sig):
    if sig[0] == "raise":
        return ("raise", sig[2], sig[3])
    return sig


def test_benchmark_netlist_sweep_is_bit_identical_for_every_benchmark_expression():
    """Every (expression, component) pair the benchmark times, compared."""
    nl = bench_netlist()
    assert len(nl.components) == 400
    for spec in bench_expr_specs():
        live_expr = build_expr(spec, live)
        oracle_expr = build_expr(spec, _tag_oracle)
        got = [c.ref for c in live.components(live_expr, nl)]
        want = [c.ref for c in _tag_oracle.components(oracle_expr, nl)]
        assert_same(got, want, context=f"components({spec!r})")
        # ...and per-component, so a compensating pair of errors cannot hide.
        for comp in nl.components:
            assert_same(
                live.resolve(live_expr, comp),
                _tag_oracle.resolve(oracle_expr, comp),
                context=f"resolve({spec!r}, {comp.ref})",
            )


def test_benchmark_distance_inputs_are_bit_identical():
    for value in bench_distance_inputs():
        got = _norm(call_signature(live_parse._parse_distance_with_unit, value))
        want = _norm(call_signature(_parse_oracle._parse_distance_with_unit, value))
        assert got == want, f"input={value!r}"


def test_benchmark_tier_inputs_are_bit_identical():
    for value in bench_tier_inputs():
        got = _norm(call_signature(live_parse._parse_tier, value))
        want = _norm(call_signature(_parse_oracle._parse_tier, value))
        assert got == want, f"input={value!r}"


def test_the_benchmark_workload_is_not_degenerate():
    """A benchmark that matches nothing would time an empty loop.

    Guards against a fixture edit quietly turning the perf number into noise.
    """
    nl = bench_netlist()
    hit_counts = [len(live.components(build_expr(spec, live), nl)) for spec in bench_expr_specs()]
    assert all(n > 0 for n in hit_counts), hit_counts
    assert max(hit_counts) < len(nl.components), "every expression matches everything"
    # The distance corpus must exercise BOTH the value and the error paths.
    outcomes = {
        call_signature(live_parse._parse_distance_with_unit, v)[0] for v in bench_distance_inputs()
    }
    assert outcomes == {"return", "raise"}, outcomes
