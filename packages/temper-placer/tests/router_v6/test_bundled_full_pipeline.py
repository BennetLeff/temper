"""Regression test for the full bundled *pipeline* path -- not just
``ModelBuilder`` in isolation.

Why this test exists (docs/evidence/2026-08-07-sat-model-reduction-options.md
Sec 3.1): the bundled encoding's PyO3 entrypoint
(``temper_rust_router.solve_topology_rust_bundled``) was dropped by the
2026-07-08 ``temper-rust-router-core`` crate split and went **undetected for
three weeks**, because every test exercising ``enable_bundling=True``
instantiated ``ModelBuilder`` directly -- never ``RouterV6Pipeline`` (or its
``_run_stage3``) -- so none of them ever executed the
``from temper_rust_router import solve_topology_rust_bundled`` import line
that actually broke. A model-level unit test cannot catch a wiring
regression one layer up from the model.

This test drives ``RouterV6Pipeline._run_stage3`` directly (mirroring
``docs/evidence/2026-08-07-sat-model-reduction-options.md``'s own §3.4
"live-measurement methodology": ``route_pcb()`` still doesn't expose
``enable_bundling`` -- see ``_adapter_convert.py`` -- so the pipeline must
be driven directly) on a small synthetic 2-net board designed to actually
bundle (identical footprints -> guaranteed Jaccard=1.0 overlap, same
net_class/safety_category -> guaranteed TypeSignature match), and asserts
two things no ModelBuilder-only test can:

1. ``BundleAnalyzer`` really ran as part of the pipeline's own Stage 3 wiring
   (observed via its own verbose "Bundle analysis: ..." print, not a
   monkeypatched stand-in) and actually produced a bundle -- not just an
   all-singleton manifest.
2. Control reaches the Rust solve call boundary: the
   ``from temper_rust_router import solve_topology_rust_bundled`` import
   really executes. As of this task, that binding is still missing (see the
   evidence doc's recommendation ordering: fix grouping/vectorization/
   capacity-collision first, measure, and only then decide whether restoring
   the binding is worth it -- this task did not restore it), so today this
   test asserts the specific, expected ``ImportError`` naming the missing
   symbol. If a future change restores ``solve_topology_rust_bundled``, this
   test should be updated to assert a successful solve instead -- but it
   will keep failing loudly (for the RIGHT reason: an unexpected exception
   type, or the bundle-analysis print going missing) if the wiring rots
   again in the meantime, which is the property that was missing for three
   weeks.
"""

from __future__ import annotations

import networkx as nx
import pytest

from temper_placer.core.netlist import Component, Net, Pin
from temper_placer.router_v6.channel_skeleton import ChannelSkeleton
from temper_placer.router_v6.channel_widths import ChannelWidths
from temper_placer.router_v6.pipeline import RouterV6Pipeline, Stage2Output
from temper_placer.router_v6.stage0_data import DesignRules, LayerInfo, ParsedPCB, StackupInfo


def _make_grid_skeleton(x_range, y_range, spacing=5.0) -> ChannelSkeleton:
    g = nx.Graph()
    xs = [x_range[0] + i * spacing for i in range(int((x_range[1] - x_range[0]) / spacing) + 1)]
    ys = [y_range[0] + i * spacing for i in range(int((y_range[1] - y_range[0]) / spacing) + 1)]
    for x in xs:
        for y in ys:
            g.add_node((x, y))
    for x in xs:
        for i in range(len(ys) - 1):
            g.add_edge((x, ys[i]), (x, ys[i + 1]), weight=spacing)
    for y in ys:
        for i in range(len(xs) - 1):
            g.add_edge((xs[i], y), (xs[i + 1], y), weight=spacing)
    return ChannelSkeleton(graph=g, layer_name="F.Cu", total_length=g.size(weight="weight"))


def _build_two_net_bundle_candidate_board() -> tuple[ParsedPCB, Stage2Output]:
    """A 2-net board designed to bundle: SIG_A and SIG_B have IDENTICAL pin
    footprints (same positions), so their geometric footprints coincide
    exactly (Jaccard = 1.0 > the 0.5 threshold), and both are ordinary
    unassigned nets (net_class="signal", safety_category=None) so their
    TypeSignatures match too.
    """
    pin_kwargs = dict(width=1.0, height=1.0, shape="rect", layer="F.Cu")
    pin_a1 = Pin(name="1", number="1", position=(0.0, 0.0), net="SIG_A", **pin_kwargs)
    pin_a2 = Pin(name="1", number="1", position=(0.0, 0.0), net="SIG_A", **pin_kwargs)
    pin_b1 = Pin(name="1", number="1", position=(0.0, 0.0), net="SIG_B", **pin_kwargs)
    pin_b2 = Pin(name="1", number="1", position=(0.0, 0.0), net="SIG_B", **pin_kwargs)

    comp_kwargs = dict(footprint="R_0402", bounds=(1.0, 1.0), initial_rotation=0)
    comp_a1 = Component(ref="A1", pins=[pin_a1], initial_position=(10.0, 10.0), **comp_kwargs)
    comp_a2 = Component(ref="A2", pins=[pin_a2], initial_position=(20.0, 10.0), **comp_kwargs)
    comp_b1 = Component(ref="B1", pins=[pin_b1], initial_position=(10.0, 10.0), **comp_kwargs)
    comp_b2 = Component(ref="B2", pins=[pin_b2], initial_position=(20.0, 10.0), **comp_kwargs)

    net_a = Net(name="SIG_A", pins=[("A1", "1"), ("A2", "1")])
    net_b = Net(name="SIG_B", pins=[("B1", "1"), ("B2", "1")])

    layers = [LayerInfo(index=0, name="F.Cu", layer_type="signal", thickness_um=35)]
    rules = DesignRules(
        net_classes={},
        net_class_assignments={},
        default_clearance_mm=0.2,
        default_trace_width_mm=0.2,
        default_via_diameter_mm=0.6,
        default_via_drill_mm=0.3,
    )
    pcb = ParsedPCB(
        components=[comp_a1, comp_a2, comp_b1, comp_b2],
        nets=[net_a, net_b],
        design_rules=rules,
        stackup=StackupInfo(layers=layers, total_thickness_mm=1.6, layer_count=1),
        zones=[],
        board=None,
        source_path=None,
    )

    class _MockBoard:
        width = 30.0
        height = 30.0
        origin = (0.0, 0.0)

        def get_bounds_array(self):
            return [0.0, 0.0, 30.0, 30.0]

    pcb.board_geometry = _MockBoard()

    skeletons = {"F.Cu": _make_grid_skeleton((0, 30), (0, 30), spacing=5.0)}
    channel_widths = {
        "F.Cu": ChannelWidths(
            layer_name="F.Cu",
            node_widths={},
            edge_widths={},
            min_width=1.0,
            max_width=1.0,
            avg_width=1.0,
        )
    }

    stage2 = Stage2Output(
        obstacle_maps={},
        routing_spaces={},
        skeletons=skeletons,
        channel_widths=channel_widths,
        occupancy_grids={},
        layer_capacities={},
        routing_demand=None,
        bottleneck_analysis=None,
    )
    return pcb, stage2


def test_bundled_pipeline_reaches_rust_solve_boundary(capsys):
    pcb, stage2 = _build_two_net_bundle_candidate_board()

    pipeline = RouterV6Pipeline(
        verbose=True,
        enable_theta_star=False,
        enable_lazy_theta_star=False,
        enable_smoothing=False,
        enable_bundling=True,
        enable_zone_pours=False,
    )

    # As of this task, solve_topology_rust_bundled is still missing (see
    # this module's docstring) -- so the real, current, expected outcome is
    # this specific ImportError. Update this block if that binding is ever
    # restored: assert a successful Stage3Output instead, but keep the
    # capsys assertion below either way.
    with pytest.raises(ImportError, match="solve_topology_rust_bundled"):
        pipeline._run_stage3(pcb, stage2)

    captured = capsys.readouterr()
    assert "Bundle analysis:" in captured.out, (
        "RouterV6Pipeline._run_stage3 must actually invoke BundleAnalyzer "
        "when enable_bundling=True -- this is the exact wiring that "
        "silently rotted for 3 weeks undetected because no test drove the "
        "pipeline itself with bundling on, only ModelBuilder directly."
    )
    assert "1 bundle classes for 2 nets" in captured.out, (
        "SIG_A/SIG_B have identical footprints and matching TypeSignatures "
        "by construction -- they must actually bundle, not just reach the "
        "analyzer without producing a bundle."
    )
