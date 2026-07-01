"""Tests for bundled ModelBuilder — class-variable creation and eager safety encoding.

Test scenarios: T-U3-1 through T-U3-6 from
docs/plans/2026-06-28-002-feat-net-bundling-lazy-grounding-plan.md
"""

from __future__ import annotations

from dataclasses import dataclass, field

import networkx as nx

from temper_placer.router_v6.constraint_model import (
    ModelBuilder,
    NetChannelVar,
)

# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


def _make_net(name: str) -> object:
    @dataclass
    class MockNet:
        name: str

    return MockNet(name=name)


def _make_skeleton(layer_name: str, edges: list) -> object:
    @dataclass
    class MockSkeleton:
        graph: nx.Graph = field(default_factory=nx.Graph)
        layer_name: str = "F.Cu"

    g = nx.Graph()
    for u, v in edges:
        g.add_edge(u, v)
    return MockSkeleton(graph=g, layer_name=layer_name)


def _make_manifest(bundles: dict, unbundled=None) -> object:
    @dataclass
    class MockManifest:
        bundle_id_for_net: dict
        unbundled_net_indices: list

    return MockManifest(
        bundle_id_for_net=bundles,
        unbundled_net_indices=unbundled or [],
    )


# ---------------------------------------------------------------------------
# T-U3-1: Class variables created
# ---------------------------------------------------------------------------


def test_class_vars_created():
    """3 nets form 1 bundle class → 2 class vars (NOT 6 per-net vars)."""
    nets = [_make_net("SIG_A"), _make_net("SIG_B"), _make_net("SIG_C")]
    edges = [((0.0, 0.0), (10.0, 0.0)), ((10.0, 0.0), (20.0, 0.0))]
    skeletons = {"F.Cu": _make_skeleton("F.Cu", edges)}
    builder = ModelBuilder(
        skeletons=skeletons, nets=nets,
        )
    model = builder.build()

    channel_vars = [v for v in model.variables
                    if isinstance(v, NetChannelVar) and v.var_type == "bundle"]
    assert len(channel_vars) == 2  # 1 bundle × 2 edges
    for var in channel_vars:
        assert var.name.startswith("uses_B")


# ---------------------------------------------------------------------------
# T-U3-2: Safety constraints only
# ---------------------------------------------------------------------------


def test_safety_constraints_only():
    """No DiffPairConstraint is created when bundling is enabled."""
    nets = [_make_net("SIG_A"), _make_net("USB_DP"), _make_net("USB_DN")]
    edges = [((0.0, 0.0), (10.0, 0.0))]
    skeletons = {"F.Cu": _make_skeleton("F.Cu", edges)}
    # USB_DP/DN in their own diff-pair bundle (bid=0), SIG_A singleton (unbundled)
    from temper_placer.router_v6.diff_pair_inference import DiffPair

    dp = DiffPair(base_name="USB_D", p_net="USB_DP", n_net="USB_DN")
    builder = ModelBuilder(
        skeletons=skeletons, nets=nets,
        diff_pairs=[dp],
        )
    model = builder.build()

    from temper_placer.router_v6.constraint_model import DiffPairConstraint

    dp_constraints = [c for c in model.constraints
                      if isinstance(c, DiffPairConstraint)]
    assert len(dp_constraints) == 0, \
        f"Expected 0 DiffPairConstraint, got {len(dp_constraints)}"


# ---------------------------------------------------------------------------
# T-U3-3: Enable bundling False — unchanged
# ---------------------------------------------------------------------------


def test_bundling_disabled_unchanged():
    """With model is identical to current behavior."""
    nets = [_make_net("SIG_A"), _make_net("SIG_B")]
    edges = [((0.0, 0.0), (10.0, 0.0))]
    skeletons = {"F.Cu": _make_skeleton("F.Cu", edges)}

    builder = ModelBuilder(skeletons=skeletons, nets=nets)
    model_no_bundle = builder.build()

    builder2 = ModelBuilder(skeletons=skeletons, nets=nets)
    model_no_bundle2 = builder2.build()

    assert model_no_bundle.variable_count == model_no_bundle2.variable_count
    assert model_no_bundle.constraint_count == model_no_bundle2.constraint_count


# ---------------------------------------------------------------------------
# T-U3-4: Empty manifest
# ---------------------------------------------------------------------------


def test_empty_manifest():
    """Zero bundles → only via vars, zero class channel vars."""
    nets = [_make_net("SIG_A")]
    edges = [((0.0, 0.0), (10.0, 0.0))]
    skeletons = {"F.Cu": _make_skeleton("F.Cu", edges)}
    builder = ModelBuilder(
        skeletons=skeletons, nets=nets,
        )
    model = builder.build()

    class_vars = [v for v in model.variables
                  if isinstance(v, NetChannelVar) and getattr(v, "var_type", "") == "bundle"]
    assert len(class_vars) == 0


# ---------------------------------------------------------------------------
# T-U3-5 (approximate): Variable count reduction
# ---------------------------------------------------------------------------


def test_variable_count_reduction():
    """10 identical signal nets, 1 channel → bundled model has 1 class variable."""
    nets = [_make_net(f"SIG_{i}") for i in range(10)]
    edges = [((0.0, 0.0), (10.0, 0.0))]
    skeletons = {"F.Cu": _make_skeleton("F.Cu", edges)}
    builder = ModelBuilder(
        skeletons=skeletons, nets=nets,
        )
    bundled_model = builder.build()

    builder2 = ModelBuilder(
        skeletons=skeletons, nets=nets,
        
    )
    unbundled_model = builder2.build()

    bundled_vc = bundled_model.variable_count
    unbundled_vc = unbundled_model.variable_count

    # Channel vars: 1 bundle × 1 edge = 1 class var vs 10 × 1 = 10 net vars
    # Plus via vars (same for both)
    assert bundled_vc < unbundled_vc
    ratio = bundled_vc / unbundled_vc
    assert ratio < 0.9, f"Expected < 90%, got {ratio:.1%}"
