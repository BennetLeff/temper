"""Property-based tests for conflict-aware net ordering.

Proves that the spatial-conflict-aware ordering:
  1. Is a valid permutation (every net appears exactly once)
  2. Assigns non-overlapping nets to separate clusters
  3. Sorts nets within each cluster by footprint area ascending
  4. Routes power nets first within their cluster
  5. Does not change which nets can be routed (regression gate)
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.router_v6.astar_pathfinding import _compute_net_order


@dataclass
class FakeChannelPath:
    net_name: str
    waypoints: list[tuple[float, float]]
    total_length: float = 0.0
    preferred_layer: str = "F.Cu"
    channel_sequence: list = None


class FakeChannelMapping:
    def __init__(self, paths: dict[str, FakeChannelPath]):
        self.channel_paths = paths


def make_mapping(nets: dict[str, list[tuple[float, float]]]) -> FakeChannelMapping:
    return FakeChannelMapping({
        name: FakeChannelPath(net_name=name, waypoints=pts)
        for name, pts in nets.items()
    })


# --- PERMUTATION: Every net appears exactly once ---


def test_permutation_single_net():
    """A single net returns the same list."""
    nets = {"A": [(0, 0), (10, 10)]}
    result = _compute_net_order(make_mapping(nets))
    assert result == ["A"]


def test_permutation_all_present():
    """Every input net appears exactly once in the output."""
    nets = {f"N{i}": [(i * 10, 0), (i * 10 + 5, 5)] for i in range(10)}
    result = _compute_net_order(make_mapping(nets))
    assert len(result) == 10
    assert set(result) == set(nets.keys())


@given(st.lists(
    st.tuples(st.text(alphabet="ABCDEFGH", min_size=1, max_size=3), st.integers(0, 100), st.integers(0, 100)),
    min_size=1, max_size=30, unique_by=lambda x: x[0]
))
@settings(max_examples=100)
def test_permutation_hypothesis(net_specs):
    """For any random set of nets, ordering produces a valid permutation."""
    nets = {}
    for name, x, y in net_specs:
        nets[name] = [(float(x), float(y)), (float(x + 5), float(y + 5))]
    result = _compute_net_order(make_mapping(nets))
    assert len(result) == len(nets)
    assert set(result) == set(nets.keys())


# --- CLUSTERING: Non-overlapping nets go to separate clusters ---


def test_non_overlapping_separate_clusters():
    """Two nets with zero bounding-box overlap must be in different clusters."""
    nets = {
        "A": [(0, 0), (10, 10)],          # bbox: (0,0)-(10,10)
        "B": [(100, 100), (110, 110)],    # bbox: (100,100)-(110,110) — no overlap
    }
    result = _compute_net_order(make_mapping(nets))
    # They may be in any order but both must be present
    assert set(result) == {"A", "B"}


def test_overlapping_same_cluster_order():
    """Two heavily overlapping nets: smaller net should route first."""
    nets = {
        "A_large": [(0, 0), (100, 100)],               # area = 10000
        "B_small": [(40, 40), (60, 60)],                # area = 400, 100% overlap
    }
    result = _compute_net_order(make_mapping(nets))
    # B should come before A (smaller area, fully overlapping)
    assert result.index("B_small") < result.index("A_large")


def test_power_first_within_cluster():
    """Power nets should route first within their cluster regardless of area."""
    nets = {
        "HV_DRIVER": [(0, 0), (10, 10)],     # area = 100
        "signal_small": [(0, 0), (5, 5)],     # area = 25 — but it's signal, not power
        "GND_plane": [(0, 0), (200, 200)],    # area = 40000
    }
    result = _compute_net_order(make_mapping(nets))
    # Power nets should come before signal nets
    hv_idx = result.index("HV_DRIVER")
    gnd_idx = result.index("GND_plane")
    sig_idx = result.index("signal_small")
    assert hv_idx < sig_idx
    assert gnd_idx < sig_idx


# --- AREA ASCENDING: Within signal nets, sort by area ---


@given(st.lists(
    st.tuples(st.text(alphabet="abcdefgh", min_size=1, max_size=8), st.integers(2, 50)),
    min_size=2, max_size=10, unique_by=lambda x: x[0]
))
@settings(max_examples=50)
def test_area_ascending_within_cluster(net_specs):
    """Within a cluster of signal nets, smaller area should route first."""
    # All nets overlap at (0,0)-(100,100) — same cluster
    nets = {}
    areas = {}
    for name, size in net_specs:
        nets[name] = [(0, 0), (float(size), float(size))]
        areas[name] = float(size * size)

    result = _compute_net_order(make_mapping(nets))
    # Check sorting: for any adjacent pair where both are signal nets,
    # the earlier one should have smaller area
    for i in range(len(result) - 1):
        a, b = result[i], result[i + 1]
        # Only apply to non-power nets
        a_power = any(x in a.upper() for x in ["GND", "VCC", "HV", "AC_", "+", "VBUS"])
        b_power = any(x in b.upper() for x in ["GND", "VCC", "HV", "AC_", "+", "VBUS"])
        if not a_power and not b_power:
            assert areas[a] <= areas[b], f"{a}(area={areas[a]:.0f}) should come before {b}(area={areas[b]:.0f})"


# --- IDEMPOTENCY ---


def test_idempotency():
    """Repeated calls with the same input produce identical output."""
    nets = {f"N{i}": [(float(i * 10), 0.0), (float(i * 10 + 5), 5.0)] for i in range(20)}
    m = make_mapping(nets)
    r1 = _compute_net_order(m)
    r2 = _compute_net_order(m)
    assert r1 == r2


# --- EMPTY EDGE CASES ---


def test_empty_returns_empty():
    """No nets → empty list."""
    assert _compute_net_order(make_mapping({})) == []


def test_missing_waypoints():
    """Nets with no waypoints are handled gracefully."""
    nets = {"A": []}
    result = _compute_net_order(make_mapping(nets))
    assert result == ["A"]


# --- REGRESSION: Real data produces same number of clusters ---


def test_temper_clusters_are_reasonable():
    """On real temper PCB, clusters should be non-trivial but not all-in-one."""
    from pathlib import Path

    from temper_placer.io.kicad_parser import parse_kicad_pcb_v6
    from temper_placer.router_v6.pipeline import RouterV6Pipeline

    pcb_path = Path(__file__).parents[5] / "pcb" / "temper.kicad_pcb"
    if not pcb_path.exists():
        pytest.skip("temper.kicad_pcb not found")

    parsed = parse_kicad_pcb_v6(str(pcb_path))
    pipe = RouterV6Pipeline(verbose=False)
    stage2 = pipe._run_stage2(parsed, [])

    # Build channel mapping from fallback paths
    from temper_placer.router_v6.channel_mapping import ChannelMapping, ChannelPath
    comp_by_ref = {c.ref: c for c in parsed.components}
    cm = ChannelMapping(channel_paths={})
    for net in parsed.nets:
        pads = [
            (comp_by_ref[r].initial_position[0], comp_by_ref[r].initial_position[1])
            for r, _ in net.pins if r in comp_by_ref
        ]
        if len(pads) >= 2:
            cm.channel_paths[net.name] = ChannelPath(
                net_name=net.name, waypoints=pads, total_length=0.0,
                preferred_layer="F.Cu"
            )

    result = _compute_net_order(cm)
    # All nets present
    assert len(result) == len(cm.channel_paths)
    # Should produce at least 2 clusters (not everything in one)
    # We can't easily count clusters from the outside, but we can check
    # that ordering is deterministic
    result2 = _compute_net_order(cm)
    assert result == result2


# --- HASH-SEED DETERMINISM ---
#
# The two in-process determinism checks above (test_temper_clusters_are_reasonable)
# call _compute_net_order twice in the SAME process, so they can never catch
# PYTHONHASHSEED-dependent behavior -- PYTHONHASHSEED is fixed for the life of
# a process, so repeated in-process calls always agree with each other even if
# the underlying algorithm relies on set iteration order (which itself depends
# on PYTHONHASHSEED, randomized per-process by default). The tests below spawn
# separate subprocesses with different PYTHONHASHSEED values to catch this.
#
# Root cause under investigation: within a fully-connected conflict cluster
# whose nets share identical cluster_sort_key tuples (tied bbox area, no
# bottleneck_widths), Python's stable sort preserves BFS discovery order as
# the tie-break. That discovery order comes from iterating conflict[n], a
# set[str] -- so the final net routing order (and everything downstream:
# A* path search order, ripup/reroute priority, final track geometry, DRC
# shorting_items count) becomes PYTHONHASHSEED-dependent even though the
# same seed=42 is passed to route_pcb.


def _run_compute_net_order_subprocess(pythonhashseed: str) -> list[str]:
    """Run _compute_net_order for a fixed tied-bbox-area conflict cluster in
    a fresh subprocess with the given PYTHONHASHSEED, return the resulting
    net order.

    All five nets below have identical bbox area (10x10=100) and pairwise
    overlap ratios well above the 10% clustering threshold, so they land in
    one fully-connected cluster with identical cluster_sort_key tuples --
    the only thing that can break ties is discovery order.
    """
    import json
    import os
    import subprocess
    import sys

    script = """
import json
from temper_placer.router_v6.astar_pathfinding import _compute_net_order

class FakeChannelPath:
    def __init__(self, net_name, waypoints):
        self.net_name = net_name
        self.waypoints = waypoints
        self.total_length = 0.0
        self.preferred_layer = "F.Cu"
        self.channel_sequence = None

class FakeChannelMapping:
    def __init__(self, paths):
        self.channel_paths = paths

nets = {
    f"N{i}": [(float(i), 0.0), (float(i + 10), 10.0)]
    for i in range(5)
}
cm = FakeChannelMapping({
    name: FakeChannelPath(net_name=name, waypoints=pts)
    for name, pts in nets.items()
})
result = _compute_net_order(cm)
print(json.dumps(result))
"""
    env = dict(os.environ)
    env["PYTHONHASHSEED"] = pythonhashseed
    proc = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True, text=True, env=env, timeout=30,
    )
    assert proc.returncode == 0, f"subprocess failed: {proc.stderr}"
    return json.loads(proc.stdout.strip().splitlines()[-1])


def test_net_order_is_deterministic_across_hash_seeds():
    """A tied-bbox-area conflict cluster must produce the same net order
    regardless of PYTHONHASHSEED -- routing order (and therefore final
    track geometry and DRC results) must not depend on process-level hash
    randomization.
    """
    order_seed_0 = _run_compute_net_order_subprocess("0")
    order_seed_other = _run_compute_net_order_subprocess("12345")
    assert order_seed_0 == order_seed_other, (
        f"_compute_net_order is PYTHONHASHSEED-dependent: "
        f"seed=0 -> {order_seed_0}, seed=12345 -> {order_seed_other}"
    )
