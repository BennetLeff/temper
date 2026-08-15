"""Selective-SAT `net_filter` on `ModelBuilder` (2026-08-15).

`max_sat_nets` / `_select_sat_nets` used to compute the top-N net subset
and then never pass it anywhere: `ModelBuilder.build()` encoded EVERY net,
so the Stage 3 CNF always carried the `|nets| x |edges|` Sinz term and the
monolith was sized to a measured 182-200 GB demand
(`docs/evidence/2026-08-15-stage3-memory-blowup-investigation.md`; the
single-net controlled experiment collapses the model to 59,008 vars /
12,284 clauses and SAT in 4.6 ms).

The fix: `ModelBuilder(net_filter=[...])` (Python shim) threads the list of
net *names* into the Rust builder (`temper-design-bundle/src/
model_builder.rs`), which then creates variables / capacity terms / layer
constraints ONLY for the named nets. Net indices are NOT renumbered -- a
filtered model keeps the original `pcb.nets` indices, so variable names
(`uses_N{idx}_...`) and the downstream index-based consumers
(`extract_topology`'s `net_names.get(ni)`, `var_to_net`) stay consistent.

Non-selected nets get no SAT topology and fall through to Stage 4's
existing `fallback_channel_path` A* path -- the identical path nets the
solver leaves unassigned take today (`map_topology_to_channels` drops nets
with an empty channel sequence before the pipeline's fallback fires).
"""

from __future__ import annotations

import networkx as nx
import pytest

from temper_placer.core.netlist import Component, Net, Pin
from temper_placer.router_v6.channel_skeleton import ChannelSkeleton
from temper_placer.router_v6.channel_widths import ChannelWidths
from temper_placer.router_v6.constraint_model import ModelBuilder
from temper_placer.router_v6.stage0_data import DesignRules, NetClassRules, ParsedPCB


# ---------------------------------------------------------------------------
# Shared fixtures (mirror test_constraint_model_builder_rust_differential.py)
# ---------------------------------------------------------------------------


def _sk(layer_name: str, edges) -> ChannelSkeleton:
    g = nx.Graph()
    for u, v in edges:
        g.add_edge(u, v)
    return ChannelSkeleton(graph=g, layer_name=layer_name, total_length=10.0)


def _rules() -> DesignRules:
    classes = {
        "W0.1": NetClassRules(
            name="W0.1", clearance_mm=0.0, trace_width_mm=0.1, via_diameter_mm=0.3,
            via_drill_mm=0.15,
        ),
        "W0.2": NetClassRules(
            name="W0.2", clearance_mm=0.0, trace_width_mm=0.2, via_diameter_mm=0.3,
            via_drill_mm=0.15,
        ),
    }
    return DesignRules(
        net_classes=classes,
        net_class_assignments={"AAA": "W0.1", "BBB": "W0.2", "CCC": "W0.1", "DDD": "W0.2"},
        default_clearance_mm=0.0,
        default_trace_width_mm=0.2,
        default_via_diameter_mm=0.3,
        default_via_drill_mm=0.15,
    )


def _capacity_inputs():
    """4 nets, one skeleton edge on L1, per-edge capacity 0.5."""
    skeletons = {"L1": _sk("L1", [((0.0, 0.0), (10.0, 0.0))])}
    nets = [Net(name=n, pins=[]) for n in ("AAA", "BBB", "CCC", "DDD")]
    widths = {
        "L1": ChannelWidths(
            layer_name="L1",
            node_widths={},
            edge_widths={((0.0, 0.0), (10.0, 0.0)): 0.5},
            min_width=0.5,
            max_width=0.5,
            avg_width=0.5,
        )
    }
    return skeletons, nets, widths, _rules()


def _build(net_filter):
    skeletons, nets, widths, rules = _capacity_inputs()
    return ModelBuilder(
        skeletons=skeletons,
        nets=nets,
        channel_widths=widths,
        design_rules=rules,
        net_filter=net_filter,
    ).build()


def _var_net_indices(model) -> set[int]:
    return {v.net_idx for v in model.variables}


# ---------------------------------------------------------------------------
# Channel variables
# ---------------------------------------------------------------------------


def test_net_filter_subsets_channel_vars() -> None:
    """Only the named nets get NetChannelVars."""
    model = _build(net_filter=["AAA", "BBB"])
    assert _var_net_indices(model) == {0, 1}
    names = {v.name for v in model.variables}
    assert not any(n.startswith("uses_N2_") or n.startswith("uses_N3_") for n in names)


def test_net_filter_none_is_full_model() -> None:
    """net_filter=None (the default) must keep today's full-model behavior."""
    model = _build(net_filter=None)
    assert _var_net_indices(model) == {0, 1, 2, 3}


def test_net_filter_preserves_original_net_indices() -> None:
    """Filtering must NOT renumber: CCC keeps its pcb.nets index 2."""
    model = _build(net_filter=["CCC"])
    assert _var_net_indices(model) == {2}
    names = {v.name for v in model.variables}
    assert all(n.startswith("uses_N2_") for n in names)


# ---------------------------------------------------------------------------
# Capacity constraints (the |nets| x |edges| Sinz term)
# ---------------------------------------------------------------------------


def test_net_filter_subsets_capacity_terms() -> None:
    """CapacityConstraint terms reference only the selected nets' vars."""
    model = _build(net_filter=["AAA", "BBB"])
    cons = [c for c in model.constraints if type(c).__name__ == "CapacityConstraint"]
    assert cons, "expected at least one capacity constraint"
    for c in cons:
        term_nets = {v.net_idx for v, _w in c.terms}
        assert term_nets <= {0, 1}, f"terms reference non-selected nets: {term_nets}"
        # 2 selected nets on the single edge -> exactly 2 terms per channel
        assert len(c.terms) == 2, f"expected 2 terms, got {len(c.terms)}: {c.terms}"


def test_net_filter_none_capacity_terms_all_four_nets() -> None:
    """Regression guard: unfiltered capacity terms still carry all 4 nets."""
    model = _build(net_filter=None)
    cons = [c for c in model.constraints if type(c).__name__ == "CapacityConstraint"]
    assert cons
    for c in cons:
        term_nets = {v.net_idx for v, _w in c.terms}
        assert term_nets == {0, 1, 2, 3}


def test_net_filter_single_net_capacity_terms() -> None:
    """One selected net -> one term per channel (Sinz never fires with 1)."""
    model = _build(net_filter=["DDD"])
    cons = [c for c in model.constraints if type(c).__name__ == "CapacityConstraint"]
    assert cons
    for c in cons:
        assert len(c.terms) == 1
        assert c.terms[0][0].net_idx == 3


# ---------------------------------------------------------------------------
# Via vars
# ---------------------------------------------------------------------------


def test_net_filter_subsets_via_vars() -> None:
    skeletons, nets, _, rules = _capacity_inputs()
    model = ModelBuilder(
        skeletons=skeletons,
        nets=nets,
        design_rules=rules,
        enable_via_vars=True,
        net_filter=["AAA"],
    ).build()
    via = [v for v in model.variables if type(v).__name__ == "ViaVar"]
    assert via, "expected via vars"
    assert {v.net_idx for v in via} == {0}


# ---------------------------------------------------------------------------
# Layer constraints
# ---------------------------------------------------------------------------


def _layer_inputs():
    skeletons = {
        "F.Cu": _sk("F.Cu", [((0.0, 0.0), (10.0, 0.0))]),
        "B.Cu": _sk("B.Cu", [((0.0, 0.0), (0.0, 10.0))]),
    }
    nets = [Net(name="N1", pins=[])]
    pin = Pin(name="1", number="1", position=(0.0, 0.0), net="N1", layer="F.Cu", is_pth=False)
    comp = Component(
        ref="U1", footprint="FP", bounds=(1.0, 1.0), pins=[pin], initial_position=(0.0, 0.0)
    )
    pcb = ParsedPCB(
        components=[comp],
        nets=nets,
        zones=[],
        board=None,
        design_rules=None,
        stackup=None,
        source_path=None,
    )
    return skeletons, nets, None, None, pcb


def test_net_filter_keeps_selected_net_layer_constraints() -> None:
    skeletons, nets, widths, rules, pcb = _layer_inputs()
    model = ModelBuilder(
        skeletons=skeletons,
        nets=nets,
        channel_widths=widths,
        design_rules=rules,
        pcb=pcb,
        net_filter=["N1"],
    ).build()
    layer_cons = [c for c in model.constraints if type(c).__name__ == "LayerConstraint"]
    assert layer_cons, "selected net's layer constraints must be present"
    assert all(c.net_idx == 0 for c in layer_cons)


def test_net_filter_drops_unselected_net_layer_constraints() -> None:
    """A filter selecting no net yields zero layer constraints AND trips the
    R10 non-emptiness guard -- loud, not a silent empty model (the pipeline
    never sends an empty filter: `_select_sat_nets` returns None when the
    cap >= net count, and `max_sat_nets=0` short-circuits to None)."""
    skeletons, nets, widths, rules, pcb = _layer_inputs()
    builder = ModelBuilder(
        skeletons=skeletons,
        nets=nets,
        channel_widths=widths,
        design_rules=rules,
        pcb=pcb,
        net_filter=["OTHER_NET"],
    )
    with pytest.raises(Exception, match="produced 0 variables"):
        builder.build()


# ---------------------------------------------------------------------------
# Filter + geographic pruning (the two per-net reducers must compose)
# ---------------------------------------------------------------------------


def test_net_filter_composes_with_geographic_pruning() -> None:
    skeletons = {
        "L1": _sk("L1", [((0.0, 0.0), (10.0, 0.0)), ((500.0, 0.0), (510.0, 0.0))]),
    }
    nets = [Net(name="N1", pins=[]), Net(name="N2", pins=[])]
    pins1 = [Pin(name="1", number="1", position=(0.0, 0.0), net="N1", layer="F.Cu", is_pth=True)]
    pins2 = [Pin(name="1", number="1", position=(1000.0, 0.0), net="N2", layer="F.Cu", is_pth=True)]
    comps = [
        Component(ref="U1", footprint="FP", bounds=(1.0, 1.0), pins=pins1,
                  initial_position=(0.0, 0.0)),
        Component(ref="U2", footprint="FP", bounds=(1.0, 1.0), pins=pins2,
                  initial_position=(1000.0, 0.0)),
    ]
    pcb = ParsedPCB(
        components=comps,
        nets=nets,
        zones=[],
        board=None,
        design_rules=None,
        stackup=None,
        source_path=None,
    )
    model = ModelBuilder(
        skeletons=skeletons,
        nets=nets,
        pcb=pcb,
        enable_geographic_pruning=True,
        net_filter=["N1"],
    ).build()
    # N1 (index 0) is near the first edge and selected; N2 (index 1) is
    # excluded by BOTH the filter and (on the far edge) the pruning
    # predicate -- no N2 variable may exist either way.
    assert _var_net_indices(model) == {0}
    names = {v.name for v in model.variables}
    assert not any(n.startswith("uses_N1_") for n in names)
