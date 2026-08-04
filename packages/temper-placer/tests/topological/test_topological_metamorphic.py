"""R1d metamorphic relations for the Rust-backed topological package.

Six relations, each an input transformation with a predicted output
transformation. These catch classes of error a differential cannot: the
differential only proves Rust reproduces Python on the inputs it was handed,
while these constrain behaviour across whole families of related inputs.

1. **Node relabelling** -- renaming components permutes the answer and nothing
   else. Catches any accidental dependence on the *content* of a ref (hash
   order, lexicographic assumptions) rather than the graph structure.
2. **Edge-order permutation** -- reordering the constraint edges leaves the
   cluster decomposition and the propagated bounds unchanged. This is the
   relation that pins down which results are allowed to be order-sensitive:
   clustering and propagation are order-invariant, force refinement is *not*
   (naive ``+=``), and relation 6 states that asymmetry explicitly rather than
   hiding it.
3. **Coordinate translation** -- translating every position and the zone box
   by the same vector translates the refined positions by that vector.
4. **Reflection** -- mirroring x about the zone's axis mirrors the result.
5. **Distance scaling** -- scaling every constraint distance by a power of two
   scales the propagated bounds exactly (powers of two keep this bit-exact).
6. **Force-order sensitivity is real** -- a witness that edge order *does*
   change refined positions, so relation 2's silence about force refinement is
   a measured fact rather than an untested assumption.
"""

from __future__ import annotations

import math

from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

import temper_placement_topology as _rust  # noqa: F401 -- Rust-backed guard
from temper_placer.core.board import Zone
from temper_placer.topological import (
    ConstraintPropagator,
    TopologicalGraph,
    apply_force_refinement,
    identify_clusters,
)
from tests.topological._topo_strategies import build_graph, graph_specs, position_maps

SETTINGS = settings(
    max_examples=150,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
)


def _g(comps, adj, sep):
    return build_graph(TopologicalGraph, comps, adj, sep)


def _bounds_matrix(comps, g, max_iterations=100):
    p = ConstraintPropagator(g)
    p.propagate(max_iterations=max_iterations)
    return {
        (a, b): (p.get_bound(a, b).min_distance, p.get_bound(a, b).max_distance)
        for a in comps
        for b in comps
    }


def _canonical_clusters(clusters):
    return sorted(tuple(sorted(c)) for c in clusters)


# ---------------------------------------------------------------------------
# MR1 -- node relabelling invariance
# ---------------------------------------------------------------------------


@given(graph_specs())
@SETTINGS
def test_mr1_relabelling_permutes_clusters_and_nothing_else(spec):
    comps, adj, sep = spec
    rename = {c: f"Z{i:03d}" for i, c in enumerate(comps)}

    base = _g(comps, adj, sep)
    renamed = _g(
        [rename[c] for c in comps],
        [(rename[a], rename[b], d, cid) for a, b, d, cid in adj],
        [(rename[a], rename[b], d, cid) for a, b, d, cid in sep],
    )

    got = _canonical_clusters(
        [{rename[r] for r in c} for c in identify_clusters(base, list(comps))]
    )
    want = _canonical_clusters(identify_clusters(renamed, [rename[c] for c in comps]))
    assert got == want


@given(graph_specs())
@SETTINGS
def test_mr1b_relabelling_preserves_propagated_bounds(spec):
    comps, adj, sep = spec
    rename = {c: f"Z{i:03d}" for i, c in enumerate(comps)}

    base = _bounds_matrix(comps, _g(comps, adj, sep))
    renamed = _bounds_matrix(
        [rename[c] for c in comps],
        _g(
            [rename[c] for c in comps],
            [(rename[a], rename[b], d, cid) for a, b, d, cid in adj],
            [(rename[a], rename[b], d, cid) for a, b, d, cid in sep],
        ),
    )
    for (a, b), val in base.items():
        assert renamed[(rename[a], rename[b])] == val


# ---------------------------------------------------------------------------
# MR2 -- edge-order permutation invariance (clustering + propagation)
# ---------------------------------------------------------------------------


@given(graph_specs(), st.randoms(use_true_random=False))
@SETTINGS
def test_mr2_edge_order_does_not_change_clusters(spec, rnd):
    comps, adj, sep = spec
    assume(len(adj) > 1)
    shuffled = list(adj)
    rnd.shuffle(shuffled)

    a_clusters = _canonical_clusters(identify_clusters(_g(comps, adj, sep), list(comps)))
    b_clusters = _canonical_clusters(
        identify_clusters(_g(comps, shuffled, sep), list(comps))
    )
    assert a_clusters == b_clusters


@given(graph_specs(), st.randoms(use_true_random=False))
@SETTINGS
def test_mr2b_edge_order_does_not_change_propagated_bounds(spec, rnd):
    comps, adj, sep = spec
    assume(len(adj) + len(sep) > 1)
    sa, ss = list(adj), list(sep)
    rnd.shuffle(sa)
    rnd.shuffle(ss)

    base = _bounds_matrix(comps, _g(comps, adj, sep))
    perm = _bounds_matrix(comps, _g(comps, sa, ss))
    assert base == perm


# ---------------------------------------------------------------------------
# MR3 -- coordinate translation equivariance
# ---------------------------------------------------------------------------


@given(
    graph_specs(),
    st.data(),
    st.tuples(
        st.sampled_from([-1024.0, -64.0, -2.0, 0.0, 2.0, 64.0, 1024.0]),
        st.sampled_from([-1024.0, -64.0, -2.0, 0.0, 2.0, 64.0, 1024.0]),
    ),
)
@SETTINGS
def test_mr3_translation_is_equivariant(spec, data, shift):
    """Translating positions and the zone by the same vector translates the
    refined positions by that vector.

    **This relation is asserted within a tolerance, and that is not a
    loosening -- it is the mathematically correct form.** Exact translation
    equivariance is false in IEEE-754: the refinement loop computes
    ``positions += forces * lr`` each iteration, and ``(p + d) + f`` does not
    equal ``(p + f) + d`` in general once ``p + d`` has been rounded to a
    coarser exponent. Asserting ``==`` here would be asserting something
    untrue of the *Python* implementation too, so it would test the assertion
    rather than the port.

    The bit-exact statement of the same idea is MR4 below: reflection is an
    exact sign flip, every operation on the path is sign-symmetric, and so
    that relation *is* asserted with ``==``.

    The tolerance is relative to the translated magnitude, which is where the
    lost precision actually lives.
    """
    comps, adj, sep = spec
    g = _g(comps, adj, sep)
    positions = data.draw(position_maps(comps))
    dx, dy = shift

    zone = Zone(name="Z", bounds=(-2048.0, -2048.0, 2048.0, 2048.0))
    shifted_zone = Zone(
        name="Z", bounds=(-2048.0 + dx, -2048.0 + dy, 2048.0 + dx, 2048.0 + dy)
    )
    assign = dict.fromkeys(comps, "Z")

    base = apply_force_refinement(
        dict(positions), g, {"Z": zone}, dict(assign), iterations=12, learning_rate=0.05
    )
    moved = apply_force_refinement(
        {k: (x + dx, y + dy) for k, (x, y) in positions.items()},
        g,
        {"Z": shifted_zone},
        dict(assign),
        iterations=12,
        learning_rate=0.05,
    )
    for ref in comps:
        bx, by = base[ref]
        mx, my = moved[ref]
        assert math.isfinite(mx) and math.isfinite(my)
        # ulp-scaled bound: the error is accumulated rounding of the shift,
        # so it scales with the translated magnitude, not with the answer.
        tol_x = 1e-9 * max(1.0, abs(bx), abs(dx))
        tol_y = 1e-9 * max(1.0, abs(by), abs(dy))
        assert abs(mx - (bx + dx)) <= tol_x, f"{ref}: x not equivariant under translation"
        assert abs(my - (by + dy)) <= tol_y, f"{ref}: y not equivariant under translation"


# ---------------------------------------------------------------------------
# MR4 -- reflection equivariance
# ---------------------------------------------------------------------------


@given(graph_specs(), st.data())
@SETTINGS
def test_mr4_x_reflection_is_equivariant(spec, data):
    """Mirroring x about 0 (an exact sign flip) mirrors the refined x and
    leaves y untouched."""
    comps, adj, sep = spec
    g = _g(comps, adj, sep)
    positions = data.draw(position_maps(comps))
    zone = Zone(name="Z", bounds=(-2048.0, -2048.0, 2048.0, 2048.0))
    assign = dict.fromkeys(comps, "Z")

    base = apply_force_refinement(
        dict(positions), g, {"Z": zone}, dict(assign), iterations=12, learning_rate=0.05
    )
    mirrored = apply_force_refinement(
        {k: (-x, y) for k, (x, y) in positions.items()},
        g,
        {"Z": zone},
        dict(assign),
        iterations=12,
        learning_rate=0.05,
    )
    for ref in comps:
        bx, by = base[ref]
        mx, my = mirrored[ref]
        assert mx == -bx, f"{ref}: x not equivariant under reflection"
        assert my == by, f"{ref}: y changed under an x-only reflection"


# ---------------------------------------------------------------------------
# MR5 -- distance scaling
# ---------------------------------------------------------------------------


@given(graph_specs(), st.sampled_from([0.25, 0.5, 2.0, 4.0, 16.0]))
@SETTINGS
def test_mr5_power_of_two_distance_scaling_scales_the_bounds(spec, k):
    """Scaling every constraint distance by a power of two scales every finite
    propagated bound by the same factor, exactly -- the propagation is built
    from ``min``, ``max``, ``+`` and ``-``, all of which commute with an exact
    binary scaling in the absence of overflow."""
    comps, adj, sep = spec
    assume(adj or sep)

    base = _bounds_matrix(comps, _g(comps, adj, sep))
    scaled = _bounds_matrix(
        comps,
        _g(
            comps,
            [(a, b, d * k, cid) for a, b, d, cid in adj],
            [(a, b, d * k, cid) for a, b, d, cid in sep],
        ),
    )
    for pair, (mn, mx) in base.items():
        smn, smx = scaled[pair]
        if math.isfinite(mn):
            assert smn == mn * k, f"{pair}: min bound did not scale"
        if math.isfinite(mx):
            assert smx == mx * k, f"{pair}: max bound did not scale"
        else:
            assert math.isinf(smx)


# ---------------------------------------------------------------------------
# MR6 -- force refinement is deliberately NOT order-invariant
# ---------------------------------------------------------------------------


def test_mr6_force_refinement_is_order_sensitive_by_construction():
    """Witness that edge order changes refined positions.

    Force accumulation is a naive ``+=`` over a float64 array, which is not
    associative, so the refined positions genuinely depend on edge insertion
    order. That is *pre-existing Python behaviour*, faithfully reproduced --
    the Rust kernel consumes the caller's edge order instead of imposing one.

    This test exists so MR2's restriction to clustering and propagation is a
    measured boundary rather than an assumption: if a future change made
    refinement order-invariant (e.g. by sorting edges, or by switching to a
    compensated sum), this fails and forces that behaviour change to be
    stated rather than absorbed silently.
    """
    comps = ["H", "A", "B", "C", "D", "E", "F", "G", "I"]
    edges = [("H", n, 0.1 * (k + 1), f"c{k}") for k, n in enumerate(comps[1:])]
    positions = {ref: (0.1 * i, 0.3 * i) for i, ref in enumerate(comps)}
    zone = Zone(name="Z", bounds=(-1e3, -1e3, 1e3, 1e3))
    assign = dict.fromkeys(comps, "Z")

    forward = apply_force_refinement(
        dict(positions), _g(comps, edges, []), {"Z": zone}, dict(assign), 60, 0.1
    )
    reverse = apply_force_refinement(
        dict(positions), _g(comps, list(reversed(edges)), []), {"Z": zone}, dict(assign), 60, 0.1
    )

    assert forward != reverse, (
        "edge order no longer affects force refinement -- the naive `+=` "
        "accumulation this port reproduces has been replaced by an "
        "order-invariant reduction. That is a real behaviour change and must "
        "be recorded, not absorbed."
    )
