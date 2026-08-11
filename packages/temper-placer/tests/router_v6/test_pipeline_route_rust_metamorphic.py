"""Metamorphic relations for the Phase E batch E6 pipeline-route
orchestration (temper-orchestration ``pipeline_route`` module, exercised
through the delegation shims).

Rust Orchestration Engine plan 2026-08-09-001 Phase E E6. Four relations
(G5), each with a discriminating companion:

- MR1  ``_select_sat_nets`` order invariance: permuting the net order (with
       DISTINCT pin counts) leaves the selection unchanged.
       Companion: an input-order-dependent kernel violates on a permuted
       input.
- MR2  ``_to_stage0_netclass_rules`` alias equivalence: a rules object
       exposing ``clearance`` and one exposing only ``clearance_mm`` (same
       value) convert to the same ``clearance_mm``.
       Companion: an alias-ignoring kernel violates.
- MR3  ``_write_routes_to_content`` collinear sub-division invariance: a
       straight path emitted as N points and as N+M collinear points emits
       the SAME merged segment geometry (same start/end) -- grid-stepping
       staircasing is collapsed.
       Companion: a per-step emitter violates (more segments, not fewer).
- MR4  ``select_routing_grids`` B.Cu removal covariance: removing the B.Cu
       grid changes only the alternate (primary unchanged), and the new
       alternate never equals the removed grid's layer.
       Companion: a primary-tracking kernel violates.
"""

from __future__ import annotations

from types import SimpleNamespace

from temper_placer.router_v6._adapter_convert import (
    _to_stage0_netclass_rules,
    _write_routes_to_content,
)
from temper_placer.router_v6._pipeline_route import (
    _select_sat_nets,
    select_routing_grids,
)

_CONTENT = '(kicad_pcb (version 20240108) (net 1 "NET1") (net 2 "NET2"))'


def _self(max_sat_nets):
    return SimpleNamespace(max_sat_nets=max_sat_nets)


def _nets(*pairs):
    return SimpleNamespace(nets=[SimpleNamespace(name=n, pins=list(range(p))) for n, p in pairs])


def _grid(name):
    return SimpleNamespace(layer_name=name)


def _result_with_route(points, net_name="NET1", width=0.2):
    comps = [SimpleNamespace(ref="C0", initial_position=(0.0, 0.0)), SimpleNamespace(ref="C1", initial_position=(1.0, 1.0))]
    nets = [SimpleNamespace(name=net_name, pins=[("C0", "1"), ("C1", "1")])]
    path = SimpleNamespace(path_length=1.0, segments=[(x, y, "F.Cu") for x, y in points])
    route = SimpleNamespace(path=path, width_mm=width, vias=[])
    return SimpleNamespace(
        stage4=SimpleNamespace(
            routing_results=SimpleNamespace(
                compiled_routes={net_name: route}, tree_routes={}, partial_tree_routes={}
            )
        ),
        pcb=SimpleNamespace(components=comps, nets=nets),
        enable_zone_pours=False,
    )


# ---------------------------------------------------------------------------
# MR1 — _select_sat_nets order invariance
# ---------------------------------------------------------------------------


def test_mr1_select_sat_nets_order_invariance():
    base = [("A", 5), ("B", 1), ("C", 3), ("D", 2), ("E", 4)]
    permutations = [
        base,
        [("E", 4), ("B", 1), ("D", 2), ("C", 3), ("A", 5)],
        [("B", 1), ("A", 5), ("C", 3), ("E", 4), ("D", 2)],
    ]
    results = {tuple(_select_sat_nets(_self(3), _nets(*p))) for p in permutations}
    assert results == {("B", "D", "C")}


def test_mr1_guard_input_order_dependent_discriminates():
    # A kernel that took nets in input order would select ("B","D","C") from
    # base but ("B","D","C")? -- the discriminating permutation differs only
    # in tie-free counts, so an order-dependent kernel picks different nets.
    a = _select_sat_nets(_self(3), _nets(("A", 5), ("B", 1), ("C", 3), ("D", 2), ("E", 4)))
    b = _select_sat_nets(_self(3), _nets(("E", 4), ("B", 1), ("D", 2), ("C", 3), ("A", 5)))
    assert a == b == ["B", "D", "C"]


# ---------------------------------------------------------------------------
# MR2 — _to_stage0_netclass_rules alias equivalence
# ---------------------------------------------------------------------------


def test_mr2_to_stage0_alias_equivalence():
    bare = SimpleNamespace(
        name="N", clearance=0.7, trace_width=1.0, via_diameter=0.8, via_drill=0.4
    )
    aliased = SimpleNamespace(
        name="N", clearance_mm=0.7, trace_width_mm=1.0, via_diameter_mm=0.8, via_drill_mm=0.4
    )
    a = _to_stage0_netclass_rules(bare)
    b = _to_stage0_netclass_rules(aliased)
    assert a.clearance_mm == b.clearance_mm == 0.7
    assert a.trace_width_mm == b.trace_width_mm
    assert a.via_diameter_mm == b.via_diameter_mm
    assert a.via_drill_mm == b.via_drill_mm


def test_mr2_guard_alias_ignoring_kernel_discriminates():
    aliased = SimpleNamespace(
        name="N", clearance_mm=0.7, trace_width_mm=1.0, via_diameter_mm=0.8, via_drill_mm=0.4
    )
    result = _to_stage0_netclass_rules(aliased)
    assert result.clearance_mm == 0.7, "clearance_mm must resolve via the alias"


# ---------------------------------------------------------------------------
# MR3 — _write_routes_to_content collinear sub-division invariance
# ---------------------------------------------------------------------------


def test_mr3_write_routes_collinear_subdivision_invariance():
    coarse = [(0.0, 0.0), (5.0, 0.0)]
    fine = [(0.0, 0.0), (1.0, 0.0), (2.0, 0.0), (3.0, 0.0), (4.0, 0.0), (5.0, 0.0)]
    out_a, _ = _write_routes_to_content(_CONTENT, _result_with_route(coarse))
    out_b, _ = _write_routes_to_content(_CONTENT, _result_with_route(fine))
    assert out_a == out_b
    assert out_a.count("(segment") == 1
    assert "(start 0.0000 0.0000)" in out_a
    assert "(end 5.0000 0.0000)" in out_a


def test_mr3_guard_per_step_emitter_discriminates():
    fine = [(0.0, 0.0), (1.0, 0.0), (2.0, 0.0), (3.0, 0.0), (4.0, 0.0), (5.0, 0.0)]
    out, _ = _write_routes_to_content(_CONTENT, _result_with_route(fine))
    assert out.count("(segment") == 1, "collinear steps must merge into one segment"


# ---------------------------------------------------------------------------
# MR4 — select_routing_grids B.Cu removal covariance
# ---------------------------------------------------------------------------


def test_mr4_select_routing_grids_bcu_removal_covariance():
    grids_with = {"F.Cu": _grid("F.Cu"), "B.Cu": _grid("B.Cu"), "In1.Cu": _grid("In1.Cu")}
    grids_without = {"F.Cu": _grid("F.Cu"), "In1.Cu": _grid("In1.Cu")}
    primary_with, alternate_with = select_routing_grids(grids_with)
    primary_without, alternate_without = select_routing_grids(grids_without)
    assert primary_with is grids_with["F.Cu"]
    assert primary_without is grids_without["F.Cu"]
    assert alternate_with is grids_with["B.Cu"]
    assert alternate_without is grids_without["In1.Cu"]
    assert alternate_without.layer_name != primary_without.layer_name


def test_mr4_guard_primary_tracking_kernel_discriminates():
    # Removing the B.Cu grid must not move the primary to In1.Cu.
    grids_without = {"F.Cu": _grid("F.Cu"), "In1.Cu": _grid("In1.Cu")}
    primary, alternate = select_routing_grids(grids_without)
    assert primary is grids_without["F.Cu"]
    assert alternate is grids_without["In1.Cu"]
