import dataclasses

import networkx as nx
import pytest

from temper_placer.core.netlist import Net
from temper_placer.router_v6.channel_skeleton import ChannelSkeleton
from temper_placer.router_v6.channel_widths import ChannelWidths
from temper_placer.router_v6.constraint_model import ModelBuilder, NetChannelVar, ViaVar
from temper_placer.router_v6.diff_pair_inference import DiffPair
from temper_placer.router_v6.stage0_data import DesignRules, NetClassRules


@pytest.fixture
def mock_skeletons():
    # Layer 1 Skeleton
    g1 = nx.Graph()
    g1.add_node((0, 0))
    g1.add_node((10, 0))
    g1.add_edge((0, 0), (10, 0))  # Edge 1

    sk1 = ChannelSkeleton(graph=g1, layer_name="L1", total_length=10.0)

    # Layer 2 Skeleton (same nodes)
    g2 = nx.Graph()
    g2.add_node((0, 0))
    g2.add_node((10, 0))
    g2.add_edge((0, 0), (10, 0))  # Edge 1

    sk2 = ChannelSkeleton(graph=g2, layer_name="L2", total_length=10.0)

    return {"L1": sk1, "L2": sk2}


@pytest.fixture
def mock_nets():
    return [Net(name="NET1", pins=[]), Net(name="NET2", pins=[])]


def test_model_variable_count_default_skips_via_vars(mock_skeletons, mock_nets):
    """Default (``enable_via_vars`` unset, i.e. False): no ViaVar is created.

    2026-08-07 (docs/evidence/2026-08-07-via-var-characterization.md): the
    default flipped from "always create" to "opt-in" because ViaVar is
    unconstrained -- see ViaVar's own docstring and
    ``test_via_vars_unreferenced_by_any_constraint`` below. Only channel
    vars remain: 2 nets * 2 layers * 1 edge = 4.
    """
    builder = ModelBuilder(mock_skeletons, mock_nets)
    model = builder.build()

    assert model.variable_count == 4
    assert [v for v in model.variables if isinstance(v, ViaVar)] == []


def test_model_variable_count_via_vars_opted_in(mock_skeletons, mock_nets):
    builder = ModelBuilder(mock_skeletons, mock_nets, enable_via_vars=True)
    model = builder.build()

    # Channel vars = 2 nets * 2 layers * 1 edge = 4
    # Nodes: 2 unique locations ((0,0), (10,0))
    # Via vars = 2 nets * 2 nodes = 4
    # Total = 8
    assert model.variable_count == 8


def test_channel_vars(mock_skeletons, mock_nets):
    builder = ModelBuilder(mock_skeletons, mock_nets, enable_via_vars=True)
    model = builder.build()

    # Check specific var existence
    # L1 edge 0
    # Net 0
    # ID depends on sorted nodes and index
    # Note: Edge enumeration order in nx is not guaranteed stable across runs unless added deterministically,
    # but in this simple case it's fine.

    # We can iterate model.variables and count types
    channel_vars = [v for v in model.variables if isinstance(v, NetChannelVar)]
    assert len(channel_vars) == 4

    via_vars = [v for v in model.variables if isinstance(v, ViaVar)]
    assert len(via_vars) == 4


def test_via_vars_unique_nodes(mock_skeletons, mock_nets):
    # Add a node only in L2
    mock_skeletons["L2"].graph.add_node((5, 5))

    builder = ModelBuilder(mock_skeletons, mock_nets, enable_via_vars=True)
    model = builder.build()

    # Unique nodes: (0,0), (10,0), (5,5) -> 3 nodes
    # Via vars = 2 nets * 3 nodes = 6

    via_vars = [v for v in model.variables if isinstance(v, ViaVar)]
    assert len(via_vars) == 6


def _find_via_var_references(obj, seen=None) -> list:
    """Recursively scan a constraint object's dataclass fields for any live
    reference to a ``ViaVar`` instance, or any string that looks like a via
    variable name (``via_N...``). Generic on purpose: it does not hardcode
    which ``Constraint`` subclasses exist, so it stays a true structural
    check of "does this constraint touch a via var" rather than an
    enumeration that silently stops covering new constraint types.
    """
    if seen is None:
        seen = set()
    if id(obj) in seen:
        return []
    seen.add(id(obj))

    hits: list = []
    if isinstance(obj, ViaVar):
        hits.append(obj)
    elif isinstance(obj, str):
        if obj.startswith("via_"):
            hits.append(obj)
    elif dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        for f in dataclasses.fields(obj):
            hits.extend(_find_via_var_references(getattr(obj, f.name), seen))
    elif isinstance(obj, (list, tuple, set, frozenset)):
        for item in obj:
            hits.extend(_find_via_var_references(item, seen))
    elif isinstance(obj, dict):
        for k, v in obj.items():
            hits.extend(_find_via_var_references(k, seen))
            hits.extend(_find_via_var_references(v, seen))
    return hits


def test_via_vars_unreferenced_by_any_constraint(mock_skeletons):
    """Locks in the soundness finding behind ``enable_via_vars`` defaulting
    to False (2026-08-07,
    docs/evidence/2026-08-07-via-var-characterization.md): no Constraint
    this builder produces ever references a ViaVar.

    Forces via-var creation ON (``enable_via_vars=True``) and exercises
    both constraint-producing paths that read real design data --
    ``_create_capacity_constraints`` (via ``design_rules``/``channel_widths``)
    and ``_create_diff_pair_constraints`` (via ``diff_pairs``) -- then
    structurally scans every produced constraint for any reference to a
    ViaVar. If a future change ever wires ViaVar into a constraint (e.g. a
    via-density/drill-spacing capacity term), this test starts failing --
    which is the intended signal to revisit ``ViaVar``'s docstring and
    ``ModelBuilder.enable_via_vars``'s default.
    """
    nets = [Net(name=n, pins=[]) for n in ("P", "N")]
    design_rules = DesignRules(
        net_classes={
            "Signal": NetClassRules(
                name="Signal",
                clearance_mm=0.1,
                trace_width_mm=0.2,
                via_diameter_mm=0.3,
                via_drill_mm=0.15,
            )
        },
        net_class_assignments={"P": "Signal", "N": "Signal"},
        default_clearance_mm=0.1,
        default_trace_width_mm=0.2,
        default_via_diameter_mm=0.3,
        default_via_drill_mm=0.15,
    )
    widths = {
        "L1": ChannelWidths(
            layer_name="L1",
            node_widths={},
            edge_widths={((0, 0), (10, 0)): 10.0},
            min_width=10.0,
            max_width=10.0,
            avg_width=10.0,
        ),
        "L2": ChannelWidths(
            layer_name="L2",
            node_widths={},
            edge_widths={((0, 0), (10, 0)): 10.0},
            min_width=10.0,
            max_width=10.0,
            avg_width=10.0,
        ),
    }
    diff_pairs = [DiffPair(base_name="PN", p_net="P", n_net="N")]

    builder = ModelBuilder(
        mock_skeletons,
        nets,
        channel_widths=widths,
        design_rules=design_rules,
        diff_pairs=diff_pairs,
        enable_via_vars=True,
    )
    model = builder.build()

    assert any(isinstance(v, ViaVar) for v in model.variables), (
        "test setup bug: expected via vars to have been created"
    )
    assert model.constraints, "test setup bug: expected at least one constraint to have been created"

    hits = []
    for c in model.constraints:
        hits.extend(_find_via_var_references(c))
    assert hits == [], f"a constraint referenced a via var, contradicting ViaVar's docstring: {hits}"
