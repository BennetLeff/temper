"""Placement output must not depend on PYTHONHASHSEED.

Several placement heuristics used to derive an *ordered* decision from an
*unordered* container. `set`/`frozenset` iteration order for `str` keys depends
on PYTHONHASHSEED, which CPython randomises per process, so the x/y coordinates
of clustered components differed between two runs of the same code on the same
input:

    seed=0 -> ['AA5','AA3','AA1','AA6','AA4','AA7','AA2']
    seed=1 -> ['AA4','AA7','AA6','AA3','AA1','AA5','AA2']
    seed=2 -> ['AA2','AA4','AA5','AA7','AA1','AA3','AA6']

That order became `FunctionalModule.components`, and each component's polar
angle is chosen by index (`angle = 2*pi*i/n`), so every clustered component
landed somewhere different.

The three regression-tested sites, all of which now re-project through netlist
order via `heuristics.base.order_refs_by_netlist`:

* `organizational._find_highly_connected_groups` -- a `set` difference over
  net refs, feeding module composition and therefore polar angles.
* `structural.CriticalLoopHeuristic._place_loop_components` -- a `set` of loop
  components feeding both the polar angle index and the floating-point
  accumulation order of the centroid `sum()`.
* `topological_init.TopologicalInitializationHeuristic` -- a `set` of unplaced
  refs seeding zone-assignment insertion order, which becomes cluster order,
  which selects each cluster's sub-region via `cluster_index`.

WHY SUBPROCESSES: PYTHONHASHSEED is fixed for the life of a process. Calling a
heuristic twice in one process can never detect this class of bug -- both calls
observe the same hash seed and always agree. Each seed therefore needs a fresh
interpreter.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

# Enough seeds that agreement is not luck. Set iteration order over the 8-12
# refs used below takes many distinct values; 32 independent seeds agreeing
# byte-for-byte is strong evidence the order no longer depends on the seed.
SEEDS = [str(s) for s in range(32)]


# The payload runs in a fresh interpreter. It exercises all three sites and
# prints one JSON object. Floats are emitted via repr() so the comparison is
# exact (repr round-trips a float bit-for-bit) rather than tolerance-based --
# a coordinate that moves by one ULP is still a determinism bug.
_PAYLOAD = r"""
import json

from temper_placer.core.board import Board, Zone
from temper_placer.core.netlist import Component, Net, Netlist
from temper_placer.heuristics.base import PlacementContext
from temper_placer.heuristics.organizational import (
    FunctionalModuleClusteringHeuristic,
    identify_functional_modules,
)
from temper_placer.heuristics.structural import CriticalLoopHeuristic
from temper_placer.heuristics.topological_init import (
    TopologicalInitializationHeuristic,
)
from temper_placer.io.config_loader import PlacementConstraints
from temper_placer._constraint_types.topology import CriticalLoop

# Deliberately NOT in lexicographic order: netlist order and sorted order
# differ here, so a fix that silently sorted instead of preserving netlist
# order would produce a different (but still stable) answer, and the recorded
# expectations below would catch the swap.
REFS = ["AA7", "AA3", "AA10", "AA1", "AA5", "AA2", "AA9", "AA4", "AA8", "AA6"]

components = [
    Component(ref=r, footprint="R_0402", bounds=(1.0, 0.5)) for r in REFS
]
# Two shared signal nets over the same refs -> shared-net count >= 2 -> the
# refs land in one highly-connected group.
nets = [
    Net(name="SIG1", pins=[(r, "1") for r in REFS], net_class="Signal"),
    Net(name="SIG2", pins=[(r, "2") for r in REFS], net_class="Signal"),
]
netlist = Netlist(components=components, nets=nets)

board = Board(
    width=100.0,
    height=100.0,
    zones=[Zone(name="MAIN", bounds=(5.0, 5.0, 90.0, 90.0))],
)
constraints = PlacementConstraints(
    board_margin_mm=5.0,
    critical_loops=[CriticalLoop(name="LOOP1", nets=["SIG1", "SIG2"])],
)

out = {}

# --- Site 1: organizational module composition -------------------------------
modules = identify_functional_modules(netlist, constraints)
out["module_components"] = [m.components for m in modules]

# ...and the coordinates that composition produces.
ctx = PlacementContext(board=board, netlist=netlist, constraints=constraints)
res = FunctionalModuleClusteringHeuristic().apply(ctx)
out["clustering_xy"] = {
    ref: [repr(p.position[0]), repr(p.position[1])]
    for ref, p in res.placements.items()
}

# --- Site 2: structural critical-loop placement ------------------------------
# Pre-place three refs so the centroid runs through the order-dependent
# floating-point sum() as well as the polar-angle index.
from temper_placer.heuristics.base import ComponentPlacement

seeded = {
    "AA10": (11.0, 61.0),
    "AA2": (37.5, 23.25),
    "AA6": (68.125, 44.0625),
}
ctx_loop = PlacementContext(
    board=board,
    netlist=netlist,
    constraints=constraints,
    current_placements={
        ref: ComponentPlacement(ref=ref, position=xy, rotation=0, confidence=1.0)
        for ref, xy in seeded.items()
    },
)
res_loop = CriticalLoopHeuristic().apply(ctx_loop)
out["loop_xy"] = {
    ref: [repr(p.position[0]), repr(p.position[1])]
    for ref, p in res_loop.placements.items()
}

# --- Site 3: topological initialization --------------------------------------
ctx_topo = PlacementContext(board=board, netlist=netlist, constraints=constraints)
res_topo = TopologicalInitializationHeuristic().apply(ctx_topo)
out["topo_xy"] = {
    ref: [repr(p.position[0]), repr(p.position[1])]
    for ref, p in res_topo.placements.items()
}

print(json.dumps(out, sort_keys=True))
"""


def _run_under_seed(seed: str) -> dict:
    """Run the payload in a fresh interpreter with the given PYTHONHASHSEED."""
    env = dict(os.environ)
    env["PYTHONHASHSEED"] = seed
    proc = subprocess.run(
        [sys.executable, "-c", _PAYLOAD],
        capture_output=True,
        text=True,
        env=env,
        timeout=180,
    )
    assert proc.returncode == 0, (
        f"payload failed under PYTHONHASHSEED={seed}:\n{proc.stderr[-4000:]}"
    )
    return json.loads(proc.stdout.strip().splitlines()[-1])


@pytest.fixture(scope="module")
def results_by_seed() -> dict[str, dict]:
    """Payload output for every seed. Module-scoped: 32 interpreters is the
    expensive part, and all assertions below read the same data."""
    return {seed: _run_under_seed(seed) for seed in SEEDS}


def test_payload_actually_exercises_all_three_sites(results_by_seed):
    """Guard against a vacuous pass.

    If a refactor made any of these three heuristics return nothing, the
    determinism assertions below would compare empty dicts and pass while
    testing nothing. Assert each site produced real output first.
    """
    sample = results_by_seed["0"]

    assert sample["module_components"], "no functional modules were identified"
    assert any(len(m) >= 8 for m in sample["module_components"]), (
        f"expected a module large enough for angle assignment to vary, got "
        f"{[len(m) for m in sample['module_components']]}"
    )
    for key in ("clustering_xy", "loop_xy", "topo_xy"):
        assert len(sample[key]) >= 2, f"{key} placed too few components: {sample[key]}"


@pytest.mark.parametrize("key", ["module_components", "clustering_xy", "loop_xy", "topo_xy"])
def test_placement_is_byte_identical_across_hash_seeds(results_by_seed, key):
    """Every seed must produce byte-identical output for each site."""
    baseline_seed = SEEDS[0]
    baseline = json.dumps(results_by_seed[baseline_seed][key], sort_keys=True)

    mismatches = []
    for seed in SEEDS[1:]:
        actual = json.dumps(results_by_seed[seed][key], sort_keys=True)
        if actual != baseline:
            mismatches.append((seed, actual))

    assert not mismatches, (
        f"{key} depends on PYTHONHASHSEED: {len(mismatches)} of {len(SEEDS) - 1} "
        f"other seeds disagree with seed={baseline_seed}.\n"
        f"  seed={baseline_seed}: {baseline}\n"
        + "\n".join(f"  seed={s}: {a}" for s, a in mismatches[:3])
    )


def test_canonical_order_is_netlist_order_not_sorted(results_by_seed):
    """Pin down *which* order became canonical.

    Netlist order is the chosen convention (it matches
    `structural.identify_thermal_components` and the `ref_to_idx` index basis
    used across the pipeline). The refs are deliberately named so that netlist
    order and lexicographic order differ -- this test fails if someone
    "fixes" a future site with sorted() instead.
    """
    netlist_order = ["AA7", "AA3", "AA10", "AA1", "AA5", "AA2", "AA9", "AA4", "AA8", "AA6"]

    modules = results_by_seed["0"]["module_components"]
    big = max(modules, key=len)

    expected = [r for r in netlist_order if r in set(big)]
    assert big == expected, (
        f"module composition is no longer in netlist order.\n"
        f"  got:      {big}\n"
        f"  expected: {expected}\n"
        f"  (sorted() would give: {sorted(big)})"
    )
    assert big != sorted(big), (
        "test is vacuous: netlist order and sorted order coincide, so this "
        "assertion cannot distinguish them"
    )
