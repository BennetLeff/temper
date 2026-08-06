"""The single source of the topological perf A/B's inputs.

``benchmarks/perf_ab.py`` imports this module by path and the differential
(``test_topological_rust_differential.py``) imports it as a sibling, so the
benchmark cannot reach an input the behavioral A/B has not compared. That is
the #714 gate made structural: the differential parametrised force refinement
over ``iterations in [0, 1, 2, 8, 17, 100]`` on its own small graphs while the
benchmark ran ``(120, 0.05)`` on a 26-component one, and the only gate that
ever executed the benchmark's parameters was the perf job.

The builders take the graph *class* rather than importing one, because the two
arms need the same construction over two different classes: the live
(Rust-delegating) ``TopologicalGraph`` and the pinned Python oracle's.

Nothing here may be sorted or otherwise reordered: force refinement accumulates
with a naive ``+=`` and is order-sensitive by construction (see
``test_mr6_force_refinement_is_order_sensitive_by_construction``), so the
insertion order below *is* part of the fixture.
"""

from __future__ import annotations

import random
from typing import Any

# Fixed shape and seed: the A/B ratio is only comparable across runs if both
# arms see byte-identical input every time.
BENCH_SEED = 20260804
BENCH_N = 26
BENCH_ITERATIONS = 120
BENCH_LEARNING_RATE = 0.05
BENCH_ZONE_BOUNDS = (-200.0, -200.0, 200.0, 200.0)


def build_graph(graph_cls: Any, n: int = BENCH_N) -> tuple[Any, list[str]]:
    """A deterministic connected constraint graph of ``n`` components.

    ``refs`` is a list, and every mutation below walks it in list order, so the
    resulting edge order is a function of ``n`` alone -- no set or dict
    iteration participates, and the order does not move with PYTHONHASHSEED.
    """
    rng = random.Random(BENCH_SEED)
    refs = [f"U{i:02d}" for i in range(n)]
    g = graph_cls()
    for ref in refs:
        g.add_component(ref)
    # a spanning chain keeps it connected, plus deterministic extra chords
    for i in range(n - 1):
        g.add_adjacency(refs[i], refs[i + 1], 4.0 + (i % 5), f"adj{i}")
    for k in range(n):
        a, b = rng.randrange(n), rng.randrange(n)
        if a != b:
            g.add_separation(refs[a], refs[b], 12.0 + (k % 7), f"sep{k}")
    return g, refs


def bench_positions(refs: list[str]) -> dict[str, tuple[float, float]]:
    """Starting coordinates for the force-refinement A/B."""
    return {ref: (0.7 * i - 9.0, -0.4 * i + 5.0) for i, ref in enumerate(refs)}


def bench_zones(zone_cls: Any) -> dict[str, Any]:
    """The single containment zone every component is assigned to."""
    return {"Z": zone_cls(name="Z", bounds=BENCH_ZONE_BOUNDS)}


def bench_zone_assignments(refs: list[str]) -> dict[str, str]:
    return dict.fromkeys(refs, "Z")
