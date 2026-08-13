"""Metamorphic relations for the U-H adapter-marshalling surface
(temper-orchestration ``pipeline_route`` kernels exercised through the
production ``router_v6/_adapter_convert.py`` shims).

Rust Orchestration Engine plan 2026-08-09-001, Phase E E6 follow-on (unit
U-H). Four relations, each claimed BIT-EXACT over the shim surface and each
with a discriminating companion that would fail against a naive kernel:

- MR1  `_write_routes_to_content` — appending an UNRESOLVABLE pin (a
       comp_ref absent from the board) to a net leaves the emitted content
       byte-identical: the pad-positions walk skips the missing component,
       so the net's position list (and therefore its payload's pad count)
       is unchanged. (Metamorphic input: the pin list grows; the output is
       invariant.)
- MR2  `_write_routes_to_content` — PERMUTING the pin order within a net
       leaves the emitted content byte-identical: the emission consumes
       only ``len(pad_positions[net])``, never the position order (zone
       pours off).
- MR3  `_build_routing_result` — appending a report whose
       ``drc_violations == 0`` (or whose attribute is missing) leaves the
       DRC-violation list unchanged (the ``> 0`` guard).
- MR4  `_build_routing_result` — appending a report whose bottleneck has a
       pair_kind OUTSIDE ``("component_edge", "component_keepout")`` (or a
       missing bottleneck) leaves the congestion-region list unchanged.
"""

from __future__ import annotations

from types import SimpleNamespace

from temper_placer.router_v6._adapter_convert import (
    _build_routing_result,
    _write_routes_to_content,
)

_CONTENT = '(kicad_pcb (version 20240108) (net 1 "NET1") (net 2 "NET2"))'


def _comp(ref, pins=None, position=(0.0, 0.0)):
    if pins is None:
        return SimpleNamespace(ref=ref, initial_position=position)
    return SimpleNamespace(
        ref=ref,
        initial_position=position,
        get_pin=lambda name: SimpleNamespace(position=pins[name]) if name in pins else None,
    )


def _net(name, pins):
    return SimpleNamespace(name=name, pins=pins)


def _pcb(comps, nets):
    return SimpleNamespace(components=list(comps), nets=list(nets))


def _result(pcb, compiled):
    return SimpleNamespace(
        stage4=SimpleNamespace(
            routing_results=SimpleNamespace(
                compiled_routes=dict(compiled), tree_routes={}, partial_tree_routes={}
            )
        ),
        pcb=pcb,
        enable_zone_pours=False,
    )


def _routed_result(pcb):
    path = SimpleNamespace(path_length=1.0, segments=[(0.0, 0.0, "F.Cu"), (1.0, 0.0, "F.Cu")])
    route = SimpleNamespace(path=path, width_mm=0.2, vias=[])
    return _result(pcb, {"NET1": route})


def _routing_result(compiled=None, reports=None):
    rr = SimpleNamespace(
        compiled_routes=compiled or {},
        failed_nets=[],
        net_reports=list(reports or []),
    )
    return SimpleNamespace(stage4=SimpleNamespace(routing_results=rr), completion_rate=0.5)


# ---------------------------------------------------------------------------
# MR1 — an unresolvable pin is a no-op for the emitted content
# ---------------------------------------------------------------------------


def test_mr1_unresolvable_pin_is_content_invariant():
    base_pcb = _pcb(
        [_comp("C0", position=(0.0, 0.0)), _comp("C1", position=(1.0, 0.0))],
        [_net("NET1", [("C0", "1"), ("C1", "1")])],
    )
    grown_pcb = _pcb(
        [_comp("C0", position=(0.0, 0.0)), _comp("C1", position=(1.0, 0.0))],
        # "C9" is absent from the board -> the pad walk skips it.
        [_net("NET1", [("C0", "1"), ("C1", "1"), ("C9", "1")])],
    )
    base_content, _ = _write_routes_to_content(_CONTENT, _routed_result(base_pcb))
    grown_content, _ = _write_routes_to_content(_CONTENT, _routed_result(grown_pcb))
    assert grown_content == base_content, "an unresolvable pin must not change the output"


def test_mr1_discriminating_companion():
    # Sanity: the SAME metamorphic setup DOES move the output when the pin
    # resolves -- i.e. the relation is not vacuous (pad count feeds the
    # payload's emission guard, so 1 vs 2 pads flips the segment emission).
    one_pad_pcb = _pcb(
        [_comp("C0", position=(0.0, 0.0))],
        [_net("NET1", [("C0", "1")])],
    )
    two_pad_pcb = _pcb(
        [_comp("C0", position=(0.0, 0.0)), _comp("C1", position=(1.0, 0.0))],
        [_net("NET1", [("C0", "1"), ("C1", "1")])],
    )
    one, _ = _write_routes_to_content(_CONTENT, _routed_result(one_pad_pcb))
    two, _ = _write_routes_to_content(_CONTENT, _routed_result(two_pad_pcb))
    assert one != two, "the pad-count guard must discriminate the relation"


# ---------------------------------------------------------------------------
# MR2 — pin-order permutation is content-invariant
# ---------------------------------------------------------------------------


def test_mr2_pin_order_permutation_is_content_invariant():
    pcb_a = _pcb(
        [_comp("C0", position=(0.0, 0.0)), _comp("C1", position=(1.0, 0.0))],
        [_net("NET1", [("C0", "1"), ("C1", "1")])],
    )
    pcb_b = _pcb(
        [_comp("C0", position=(0.0, 0.0)), _comp("C1", position=(1.0, 0.0))],
        [_net("NET1", [("C1", "1"), ("C0", "1")])],
    )
    content_a, pads_a = _write_routes_to_content(_CONTENT, _routed_result(pcb_a))
    content_b, pads_b = _write_routes_to_content(_CONTENT, _routed_result(pcb_b))
    assert content_b == content_a, "pin order must not change the emitted content"
    assert len(pads_a["NET1"]) == len(pads_b["NET1"]) == 2
    assert pads_a["NET1"] != pads_b["NET1"], "the position LISTS differ (order) -- the content does not"


def test_mr2_discriminating_companion():
    # A kernel that keyed emission off the FIRST pad position would diverge
    # under this permutation; pin the invariant that the emitted segment is
    # independent of which pad comes first.
    pcb = _pcb(
        [_comp("C0", position=(0.0, 0.0)), _comp("C1", position=(5.0, 5.0))],
        [_net("NET1", [("C1", "1"), ("C0", "1")])],
    )
    content, pads = _write_routes_to_content(_CONTENT, _routed_result(pcb))
    assert pads["NET1"][0] == (5.0, 5.0), "permuted pin order surfaces in pad_positions"
    assert "(segment" in content, "the routed net still emits segments"


# ---------------------------------------------------------------------------
# MR3 — a zero-violation report is violations-invariant
# ---------------------------------------------------------------------------


def test_mr3_zero_violation_report_is_invariant():
    base = _routing_result(reports=[SimpleNamespace(net_name="A", drc_violations=2)])
    grown = _routing_result(
        reports=[
            SimpleNamespace(net_name="A", drc_violations=2),
            SimpleNamespace(net_name="B", drc_violations=0),  # no-op
            SimpleNamespace(net_name="C"),  # missing attr -> 0 -> no-op
        ]
    )
    base_result = _build_routing_result(base)
    grown_result = _build_routing_result(grown)
    assert grown_result.drc_violations == base_result.drc_violations
    assert [v.net_name for v in grown_result.drc_violations] == ["A"]


def test_mr3_discriminating_companion():
    base = _routing_result(reports=[])
    grown = _routing_result(reports=[SimpleNamespace(net_name="B", drc_violations=3)])
    base_result = _build_routing_result(base)
    grown_result = _build_routing_result(grown)
    assert len(grown_result.drc_violations) == 1 != len(base_result.drc_violations), (
        "a REAL violation must change the list (relation not vacuous)"
    )


# ---------------------------------------------------------------------------
# MR4 — a non-collected bottleneck kind is regions-invariant
# ---------------------------------------------------------------------------


def test_mr4_non_collected_bottleneck_is_invariant():
    base = _routing_result(
        reports=[
            SimpleNamespace(
                net_name="N1",
                bottleneck=SimpleNamespace(pair_kind="component_edge", component_pair=("A", "B")),
            )
        ]
    )
    grown = _routing_result(
        reports=[
            SimpleNamespace(
                net_name="N1",
                bottleneck=SimpleNamespace(pair_kind="component_edge", component_pair=("A", "B")),
            ),
            SimpleNamespace(
                net_name="N2",
                bottleneck=SimpleNamespace(pair_kind="component_component", component_pair=("C", "D")),
            ),
            SimpleNamespace(net_name="N3"),  # missing bottleneck -> no-op
            SimpleNamespace(net_name="N4", bottleneck=None),  # None -> no-op
        ]
    )
    base_result = _build_routing_result(base)
    grown_result = _build_routing_result(grown)
    assert grown_result.congestion_regions == base_result.congestion_regions
    assert [r.net_name for r in grown_result.congestion_regions] == ["N1"]


def test_mr4_discriminating_companion():
    base = _routing_result(reports=[])
    grown = _routing_result(
        reports=[
            SimpleNamespace(
                net_name="N2",
                bottleneck=SimpleNamespace(pair_kind="component_keepout", component_pair=("C", "D")),
            )
        ]
    )
    base_result = _build_routing_result(base)
    grown_result = _build_routing_result(grown)
    assert len(grown_result.congestion_regions) == 1 != len(base_result.congestion_regions), (
        "a collected bottleneck kind must change the list (relation not vacuous)"
    )
