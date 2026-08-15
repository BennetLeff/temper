"""Coverage-paydown wave 20: topological force/graph/initial-placement/
propagation/zone-solver, heuristics (structural/style/organizational) pure
helpers, io (kicad_exporter, dsn_schema), placer (deterministic/template/
adjustment/cp_sat gate), metrics (quality/physics), and validation
(tht_check/geometric).

Every target is a pure function, dataclass method, or cheaply-constructed
observer reachable from ``tests/core/`` without a live ngspice/kicad-cli
backend or a full solve.  Each target is exercised directly so the CI-exact
coverage run records non-zero line coverage and the entry becomes removable
from ``.coverage-allowlist``.

Do NOT edit ``.coverage-allowlist`` here -- the orchestrator applies the
removals after CI-exact verification.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from kiutils.board import Board as KiBoard

from temper_placer.core.board import Board, Zone
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.core.state import PlacementState
from temper_placer.heuristics.organizational import (
    identify_decoupling_caps,
    identify_functional_modules,
)
from temper_placer.heuristics.structural import create_keepout_mask
from temper_placer.heuristics.style import extract_signal_chains
from temper_placer.io.config_loader import ComponentGroup, PlacementConstraints
from temper_placer.io.dsn_schema import embed_schema_header, extract_schema_hash
from temper_placer.io.export_types import TraceSegment, TraceVia
from temper_placer.io.kicad_exporter import (
    add_segments_to_board,
    add_vias_to_board,
    path_to_segments,
    path_to_vias,
    snap_to_nearest_pad,
)
from temper_placer.metrics.physics import (
    measure_emi,
    measure_geometric,
    measure_routability,
    measure_thermal,
)
from temper_placer.metrics.quality import (
    congestion_score,
    connectivity_clustering_score,
)
from temper_placer.pcl.constraints import (
    AdjacentConstraint,
    ConstraintTier,
    SeparatedConstraint,
)
from temper_placer.pcl.parser import ConstraintCollection
from temper_placer.placer.adjustment import adjust_for_congestion
from temper_placer.placer.cp_sat.audit import Placement
from temper_placer.placer.cp_sat.gate import AcceptanceGate, GateResult
from temper_placer.placer.deterministic import (
    place_by_proximity,
    place_in_zone_center,
    place_power_stage_template,
)
from temper_placer.placer.template import (
    ComponentTemplate,
    HalfBridgeTemplate,
    load_template_from_yaml,
)
from temper_placer.router_v6.congestion import CongestionResult
from temper_placer.router_v6.grid_converter import GridCell
from temper_placer.topological.force_refinement import (
    apply_force_refinement,
    compute_adjacency_force,
    compute_boundary_force,
    compute_separation_force,
)
from temper_placer.topological.graph import TopologicalGraph, build_topological_graph
from temper_placer.topological.initial_placement import (
    generate_initial_placement,
    identify_clusters,
    place_cluster,
    place_components_in_zone,
)
from temper_placer.topological.propagation import ConstraintPropagator, DistanceBound
from temper_placer.topological.zone_solver import ZoneAssignment, ZoneSolver
from temper_placer.validation.geometric import GeometricValidator, validate_placement
from temper_placer.validation.tht_check import validate_hole_clearance

# ---------------------------------------------------------------------------
# Shared fixtures / helpers
# ---------------------------------------------------------------------------


def _board(**kw: Any) -> Board:
    defaults = {"width": 100.0, "height": 100.0, "origin": (0.0, 0.0)}
    defaults.update(kw)
    return Board(**defaults)


def _netlist(*refs: str) -> Netlist:
    return Netlist(
        components=[Component(ref=r, footprint="0603", bounds=(2.0, 1.0)) for r in refs],
        nets=[],
    )


def _placement(refs: list[tuple[str, float, float]]) -> PlacementState:
    arr = np.array([[x, y] for _, x, y in refs], dtype=np.float32)
    return PlacementState.from_positions(arr)


def _constraints() -> ConstraintCollection:
    return ConstraintCollection(
        constraints=[
            AdjacentConstraint(
                a="Q1",
                b="Q2",
                max_distance_mm=5.0,
                tier=ConstraintTier.HARD,
                because="Must be close for commutation loop area",
            ),
            SeparatedConstraint(
                a="Q1",
                b="U1",
                min_distance_mm=20.0,
                tier=ConstraintTier.HARD,
                because="Need isolation between power and logic",
            ),
        ]
    )


@dataclass
class RoutePathStub:
    """Duck-typed RoutePath consumed by kicad_exporter.path_to_segments/vias."""

    net: str
    cells: list[Any] = field(default_factory=list)
    cell_size: float = 0.2
    layer_name: str = "F.Cu"
    segments: list[Any] = field(default_factory=list)
    coordinates: list[Any] = field(default_factory=list)


@dataclass
class _QualityContext:
    """Minimal context for metrics.quality.connectivity_clustering_score."""

    net_pin_indices: Any = field(default_factory=lambda: np.array([[0, 1]], dtype=np.int64))
    net_pin_mask: Any = field(default_factory=lambda: np.array([[True, True]], dtype=bool))


# ---------------------------------------------------------------------------
# topological/force_refinement.py
# ---------------------------------------------------------------------------


class TestForceRefinement:
    def test_compute_adjacency_force_attracts_when_far(self):
        fa, fb = compute_adjacency_force(
            np.array([0.0, 0.0]), np.array([20.0, 0.0]), target_distance=10.0
        )
        assert fa.shape == (2,)
        assert fb.shape == (2,)
        # Both forces point toward each other.
        assert fa[0] > 0
        assert fb[0] < 0

    def test_compute_separation_force_repels_when_close(self):
        fa, fb = compute_separation_force(
            np.array([0.0, 0.0]), np.array([1.0, 0.0]), min_distance=5.0
        )
        assert fa.shape == (2,)
        assert fb.shape == (2,)
        assert fa[0] < 0
        assert fb[0] > 0

    def test_compute_boundary_force_pushes_back_inside(self):
        zone = Zone(name="Z", bounds=(0.0, 0.0, 100.0, 100.0))
        force = compute_boundary_force(np.array([150.0, 50.0]), zone)
        assert force.shape == (2,)
        # Position is outside on +x; force should push toward -x.
        assert force[0] < 0

    def test_apply_force_refinement_empty_and_iterations_zero(self):
        assert apply_force_refinement({}, TopologicalGraph(), {}, {}) == {}
        tg = TopologicalGraph()
        tg.add_component("U1")
        assert apply_force_refinement(
            {"U1": (5.0, 5.0)}, tg, {}, {}, iterations=0
        ) == {"U1": (5.0, 5.0)}

    def test_apply_force_refinement_pulls_adjacent_together(self):
        zone = Zone(name="Z", bounds=(0.0, 0.0, 100.0, 100.0))
        tg = TopologicalGraph()
        tg.add_component("U1")
        tg.add_component("U2")
        tg.add_adjacency("U1", "U2", max_distance=5.0, constraint_id="c1")
        result = apply_force_refinement(
            {"U1": (0.0, 0.0), "U2": (50.0, 0.0)},
            tg,
            {"Z": zone},
            {"U1": "Z", "U2": "Z"},
            iterations=10,
        )
        assert set(result) == {"U1", "U2"}
        # Adjacent pair should be closer than its 50mm start.
        dx = abs(result["U1"][0] - result["U2"][0])
        assert dx < 50.0


# ---------------------------------------------------------------------------
# topological/graph.py
# ---------------------------------------------------------------------------


class TestTopologicalGraphV20:
    def test_from_pcl_and_build_topological_graph(self):
        col = _constraints()
        g = TopologicalGraph.from_pcl(col)
        assert sorted(g.graph.nodes()) == ["Q1", "Q2", "U1"]
        g2 = build_topological_graph(col)
        assert sorted(g2.graph.nodes()) == ["Q1", "Q2", "U1"]

    def test_get_neighbors_with_and_without_filter(self):
        tg = TopologicalGraph()
        tg.add_component("U1")
        tg.add_component("U2")
        tg.add_component("U3")
        tg.add_adjacency("U1", "U2", max_distance=5.0, constraint_id="c1")
        tg.add_separation("U1", "U3", min_distance=10.0, constraint_id="c2")
        assert tg.get_neighbors("U1") == ["U2", "U3"]
        assert tg.get_neighbors("U1", edge_type="adjacent") == ["U2"]
        assert tg.get_neighbors("U1", edge_type="separated") == ["U3"]
        assert tg.get_neighbors("U3") == []

    def test_get_adjacency_cluster_transitive(self):
        tg = TopologicalGraph()
        for ref in ("A", "B", "C", "D"):
            tg.add_component(ref)
        tg.add_adjacency("A", "B", max_distance=5.0, constraint_id="c1")
        tg.add_adjacency("B", "C", max_distance=5.0, constraint_id="c2")
        tg.add_separation("A", "D", min_distance=10.0, constraint_id="c3")
        cluster = tg.get_adjacency_cluster("A")
        assert cluster == {"A", "B", "C"}
        assert "D" not in cluster


# ---------------------------------------------------------------------------
# topological/initial_placement.py
# ---------------------------------------------------------------------------


class TestInitialPlacement:
    def test_place_components_in_zone_circular(self):
        zone = Zone(name="Z", bounds=(0.0, 0.0, 100.0, 100.0))
        pos = place_components_in_zone(zone, ["Q1", "Q2"], {"Q1": (10, 10), "Q2": (10, 10)})
        assert set(pos) == {"Q1", "Q2"}
        for _ref, (x, y) in pos.items():
            assert 0.0 <= x <= 100.0
            assert 0.0 <= y <= 100.0

    def test_place_components_in_zone_empty(self):
        zone = Zone(name="Z", bounds=(0.0, 0.0, 100.0, 100.0))
        assert place_components_in_zone(zone, [], {}) == {}

    def test_identify_clusters_adjacency_only(self):
        col = _constraints()
        g = TopologicalGraph.from_pcl(col)
        clusters = identify_clusters(g, ["Q1", "Q2", "U1"])
        cluster_sets = sorted([frozenset(c) for c in clusters], key=lambda s: sorted(s)[0])
        assert cluster_sets == [frozenset({"Q1", "Q2"}), frozenset({"U1"})]

    def test_identify_clusters_empty(self):
        assert identify_clusters(TopologicalGraph(), []) == []

    def test_place_cluster_within_zone(self):
        zone = Zone(name="Z", bounds=(0.0, 0.0, 100.0, 100.0))
        col = _constraints()
        g = TopologicalGraph.from_pcl(col)
        pos = place_cluster({"Q1", "Q2"}, zone, g, {"Q1": (10, 10), "Q2": (10, 10)}, 0, 1)
        assert set(pos) == {"Q1", "Q2"}

    def test_place_cluster_empty(self):
        zone = Zone(name="Z", bounds=(0.0, 0.0, 100.0, 100.0))
        assert place_cluster(set(), zone, TopologicalGraph(), {}, 0, 1) == {}

    def test_generate_initial_placement(self):
        zone = Zone(name="HV", bounds=(0.0, 0.0, 100.0, 100.0))
        col = _constraints()
        g = TopologicalGraph.from_pcl(col)
        assignment = ZoneSolver([zone], [], ["Q1", "Q2"]).solve()
        ip = generate_initial_placement(
            g, assignment, [zone], {"Q1": (10, 10), "Q2": (10, 10)}, force_iterations=3
        )
        assert set(ip.positions) == {"Q1", "Q2"}
        assert ip.zone_assignments == {"Q1": "HV", "Q2": "HV"}
        assert len(ip.clusters) == 1

    def test_generate_initial_placement_empty_assignment(self):
        empty = ZoneAssignment(assignments={}, unassigned=[], conflicts=[])
        ip = generate_initial_placement(
            TopologicalGraph(), empty, [], {}, force_iterations=3
        )
        assert ip.positions == {}


# ---------------------------------------------------------------------------
# topological/propagation.py
# ---------------------------------------------------------------------------


class TestConstraintPropagator:
    def test_propagate_and_get_bound(self):
        col = _constraints()
        g = TopologicalGraph.from_pcl(col)
        prop = ConstraintPropagator(g)
        assert prop.propagate() is True
        bound = prop.get_bound("Q1", "Q2")
        assert isinstance(bound, DistanceBound)
        assert bound.max_distance <= 5.0

    def test_get_infeasible_pairs_empty_when_feasible(self):
        col = _constraints()
        g = TopologicalGraph.from_pcl(col)
        prop = ConstraintPropagator(g)
        prop.propagate()
        assert prop.get_infeasible_pairs() == []

    def test_get_infeasible_pairs_detects_conflict(self):
        tg = TopologicalGraph()
        tg.add_component("A")
        tg.add_component("B")
        # adjacent(A, B, 5mm) AND separated(A, B, 10mm) -> infeasible
        tg.add_adjacency("A", "B", max_distance=5.0, constraint_id="c1")
        tg.add_separation("A", "B", min_distance=10.0, constraint_id="c2")
        prop = ConstraintPropagator(tg)
        feasible = prop.propagate()
        pairs = prop.get_infeasible_pairs()
        assert (feasible is False) or len(pairs) > 0
        assert len(pairs) >= 1


# ---------------------------------------------------------------------------
# topological/zone_solver.py
# ---------------------------------------------------------------------------


class TestZoneSolver:
    def test_solve_assigns_all_components(self):
        zones = [Zone(name="HV", bounds=(0, 0, 50, 50)), Zone(name="MCU", bounds=(60, 0, 110, 50))]
        solver = ZoneSolver(zones, [], ["Q1", "Q2", "U1"])
        assignment = solver.solve()
        assert set(assignment.assignments) == {"Q1", "Q2", "U1"}
        assert assignment.unassigned == []
        assert assignment.conflicts == []
        for _ref, zone_name in assignment.assignments.items():
            assert zone_name in {"HV", "MCU"}

    def test_solve_reports_no_valid_zones(self):
        from temper_placer.pcl.constraints import EnclosingConstraint

        zones = [Zone(name="HV", bounds=(0, 0, 50, 50))]
        constraints = [
            EnclosingConstraint(
                outer="NOPE",
                inner=["Q1"],
                tier=ConstraintTier.HARD,
                because="Must live in the missing zone",
            )
        ]
        solver = ZoneSolver(zones, constraints, ["Q1"])
        assignment = solver.solve()
        assert assignment.conflicts
        assert assignment.unassigned == ["Q1"]


# ---------------------------------------------------------------------------
# heuristics/structural.py, style.py, organizational.py
# ---------------------------------------------------------------------------


class TestHeuristicPureHelpers:
    def test_create_keepout_mask_shape_and_content(self):
        board = _board()
        constraints = PlacementConstraints(board_margin_mm=2.0)
        mask = create_keepout_mask(board, constraints, resolution_mm=2.0)
        assert mask.ndim == 2
        assert mask.dtype == np.bool_
        # Board margin carves a border, so interior should be mostly valid.
        assert mask.sum() > 0
        assert mask.size > 0

    def test_create_keepout_mask_with_mounting_hole(self):
        board = _board()
        constraints = PlacementConstraints(board_margin_mm=0.0)
        mask = create_keepout_mask(board, constraints, resolution_mm=2.0)
        full = mask.sum()
        # A keepout region in the center should reduce the valid cell count.
        board_ko = Board(
            width=100.0, height=100.0, origin=(0.0, 0.0), keepouts=[(40.0, 40.0, 60.0, 60.0)]
        )
        mask_ko = create_keepout_mask(board_ko, constraints, resolution_mm=2.0)
        assert mask_ko.sum() < full

    def test_extract_signal_chains_traces_input_to_ic(self):
        comps = [
            Component(ref="JIN1", footprint="CONN-2", bounds=(5, 5)),
            Component(ref="U1", footprint="QFN-32", bounds=(5, 5)),
            Component(ref="R1", footprint="0603", bounds=(2, 1)),
        ]
        nl = Netlist(components=comps, nets=[Net(name="SIG", pins=[("JIN1", "1"), ("U1", "1")])])
        chains = extract_signal_chains(nl, PlacementConstraints())
        assert len(chains) >= 2
        refs = [n.ref for n in chains]
        assert "JIN1" in refs
        assert "U1" in refs

    def test_identify_decoupling_caps_by_power_net(self):
        comps = [
            Component(ref="C_DEC1", footprint="0603", bounds=(2, 1)),
            Component(ref="U2", footprint="QFN-32", bounds=(5, 5)),
        ]
        nl = Netlist(
            components=comps,
            nets=[
                Net(name="VCC", pins=[("C_DEC1", "1"), ("U2", "1")]),
                Net(name="GND", pins=[("C_DEC1", "2")]),
            ],
        )
        caps = identify_decoupling_caps(nl)
        assert caps == {"C_DEC1": "U2"}

    def test_identify_functional_modules_groups_and_prefix(self):
        comps = [
            Component(ref="MCU_1", footprint="QFN-32", bounds=(5, 5)),
            Component(ref="MCU_2", footprint="QFN-32", bounds=(5, 5)),
            Component(ref="GATE_1", footprint="SOIC-8", bounds=(4, 5)),
            Component(ref="GATE_2", footprint="SOIC-8", bounds=(4, 5)),
        ]
        nl = Netlist(components=comps, nets=[])
        constraints = PlacementConstraints(
            component_groups=[ComponentGroup(name="g1", components=["MCU_1", "MCU_2"])]
        )
        modules = identify_functional_modules(nl, constraints)
        names = {m.name: m.components for m in modules}
        assert "g1" in names
        assert set(names["g1"]) == {"MCU_1", "MCU_2"}
        assert "GATE_module" in names


# ---------------------------------------------------------------------------
# io/dsn_schema.py + io/kicad_exporter.py
# ---------------------------------------------------------------------------


class TestIoHelpers:
    def test_extract_schema_hash_roundtrip(self):
        embedded = embed_schema_header('(net 0 "GND")', "abc123")
        assert extract_schema_hash(embedded) == "abc123"
        # Text without a schema header returns None.
        assert extract_schema_hash('(net 0 "GND")') is None

    def test_path_to_segments_from_cells(self):
        path = RoutePathStub(
            net="GND",
            cells=[GridCell(0, 0, 0), GridCell(1, 0, 0), GridCell(2, 0, 0)],
            cell_size=1.0,
        )
        segments = path_to_segments(path, origin=(0, 0), cell_size=1.0, trace_width=0.25)
        assert len(segments) == 1
        assert segments[0].net == "GND"
        assert segments[0].layer == "F.Cu"

    def test_path_to_segments_layer_transition_skipped(self):
        path = RoutePathStub(
            net="SIG",
            cells=[
                GridCell(0, 0, 0),
                GridCell(1, 0, 0),
                GridCell(1, 0, 1),
                GridCell(2, 0, 1),
            ],
            cell_size=1.0,
        )
        segments = path_to_segments(path, origin=(0, 0), cell_size=1.0, trace_width=0.25)
        assert len(segments) == 2

    def test_path_to_segments_from_segments_fallback(self):
        path = RoutePathStub(net="SIG", segments=[(0, 0), (5, 5), (10, 5)])
        segments = path_to_segments(path, origin=(0, 0), cell_size=1.0, trace_width=0.25)
        assert len(segments) == 2

    def test_path_to_vias_single_transition(self):
        path = RoutePathStub(
            net="CLK", cells=[GridCell(0, 0, 0), GridCell(1, 0, 0), GridCell(1, 0, 1)], cell_size=1.0
        )
        vias = path_to_vias(path, origin=(0, 0), cell_size=1.0)
        assert len(vias) == 1
        assert vias[0].net == "CLK"
        assert set(vias[0].layers) == {"F.Cu", "In1.Cu"}

    def test_snap_to_nearest_pad_within_tolerance(self):
        snapped = snap_to_nearest_pad(0.03, 0.02, [(0.0, 0.0), (5.0, 5.0)], tolerance=0.15)
        assert snapped == (0.0, 0.0)

    def test_add_segments_and_vias_to_board(self):
        kb = KiBoard()
        added = add_segments_to_board(
            kb, [TraceSegment(net="GND", start=(0, 0), end=(1, 1), width=0.25, layer="F.Cu")]
        )
        assert added == 1
        assert len(kb.traceItems) == 1
        added_vias = add_vias_to_board(
            kb, [TraceVia(net="GND", position=(1, 1), size=0.8, drill=0.4, layers=["F.Cu", "In1.Cu"])]
        )
        assert added_vias == 1
        assert len(kb.traceItems) == 2


# ---------------------------------------------------------------------------
# placer/deterministic.py + template.py + adjustment.py
# ---------------------------------------------------------------------------


class TestPlacerDeterministic:
    @pytest.fixture
    def power_board(self) -> Board:
        return Board(
            width=100.0,
            height=100.0,
            zones=[
                Zone(name="power_zone", bounds=(0.0, 0.0, 50.0, 50.0)),
                Zone(name="MCU", bounds=(50.0, 0.0, 100.0, 50.0)),
            ],
        )

    def test_place_by_proximity(self, power_board: Board):
        nl = _netlist("Q1", "Q2", "C1")
        result = place_by_proximity(nl, power_board, target_ref="Q1", refs_to_place=["C1"])
        assert "C1" in result.placed_refs

    def test_place_by_proximity_missing_target(self, power_board: Board):
        nl = _netlist("Q1")
        with pytest.raises(ValueError):
            place_by_proximity(nl, power_board, target_ref="NOPE", refs_to_place=[])

    def test_place_in_zone_center(self, power_board: Board):
        nl = _netlist("Q1", "C1")
        result = place_in_zone_center(nl, power_board, refs_to_place=["Q1", "C1"], zone_name="MCU")
        assert set(result.placed_refs) == {"Q1", "C1"}

    def test_place_in_zone_center_missing_zone(self, power_board: Board):
        nl = _netlist("Q1")
        with pytest.raises(ValueError):
            place_in_zone_center(nl, power_board, refs_to_place=["Q1"], zone_name="NOPE")

    def test_place_power_stage_template(self, power_board: Board):
        nl = _netlist("Q1", "Q2", "C1")
        template = HalfBridgeTemplate.create_vertical()
        result = place_power_stage_template(nl, power_board, template, zone_name="power_zone")
        assert "Q1" in result.placed_refs
        assert "Q2" in result.placed_refs


class TestTemplate:
    def test_get_anchor_position(self):
        template = HalfBridgeTemplate.create_vertical()
        anchor = template.get_anchor_position()
        assert anchor is not None
        assert anchor.ref == "Q1"

    def test_get_anchor_position_missing_returns_none(self):
        template = ComponentTemplate(name="t", components=[])
        assert template.get_anchor_position() is None

    def test_apply_places_relative_to_anchor(self):
        template = HalfBridgeTemplate.create_vertical()
        applied = template.apply(10.0, 10.0, rotation=0)
        assert applied["Q1"] == (10.0, 10.0, 0)
        assert applied["Q2"][0] == 10.0
        assert applied["Q2"][1] < 10.0  # Q2 is below Q1

    def test_create_vertical_has_six_components(self):
        template = HalfBridgeTemplate.create_vertical()
        assert len(template.components) == 6
        assert template.anchor_point == "Q1"

    def test_load_template_from_yaml(self, tmp_path: Path):
        yaml_path = tmp_path / "tmpl.yaml"
        yaml_path.write_text(
            "name: test_tmpl\n"
            "anchor_point: Q1\n"
            "components:\n"
            "  - ref: Q1\n    x: 0.0\n    y: 0.0\n    rotation: 0\n"
            "  - ref: Q2\n    x: 0.0\n    y: -15.0\n    rotation: 0\n"
        )
        template = load_template_from_yaml(yaml_path)
        assert template.name == "test_tmpl"
        assert template.anchor_point == "Q1"
        assert len(template.components) == 2


class TestAdjustForCongestion:
    def test_no_bottlenecks_returns_copy(self):
        nl = _netlist("Q1", "C1")
        board = _board()
        positions = np.array([[10.0, 10.0], [20.0, 20.0]], dtype=np.float32)
        congestion = CongestionResult(
            bottlenecks=[], grid=type("Grid", (), {"cell_size_mm": 1.0, "origin": (0.0, 0.0)})()
        )
        result = adjust_for_congestion(positions, nl, board, congestion)
        assert result is not positions
        np.testing.assert_array_equal(result, positions)


# ---------------------------------------------------------------------------
# placer/cp_sat/gate.py
# ---------------------------------------------------------------------------


class TestAcceptanceGate:
    def _placement(self) -> Placement:
        return Placement(
            positions_mm={"Q1": (10.0, 10.0)},
            sizes_mm={"Q1": (5.0, 5.0)},
            rotations={"Q1": 0},
        )

    def test_inner_gate_passes_empty_constraints(self):
        gate = AcceptanceGate()
        report = gate.inner_gate(self._placement(), [])
        assert report.all_pass is True

    def test_truth_gate_requires_path(self):
        gate = AcceptanceGate()
        with pytest.raises(ValueError):
            gate.truth_gate()

    def test_truth_gate_missing_file_reports_error(self):
        gate = AcceptanceGate()
        result = gate.truth_gate(Path("/tmp/opencode/definitely_missing_xyz.kicad_pcb"))
        assert result.error_count == 1

    def test_accept_with_missing_pcb(self):
        gate = AcceptanceGate()
        accepted, audit, drc = gate.accept(
            self._placement(),
            [],
            pcb_path=Path("/tmp/opencode/definitely_missing_xyz.kicad_pcb"),
        )
        assert accepted is False
        assert audit.all_pass is True
        assert drc is not None

    def test_gate_result_properties(self):
        assert GateResult(inner_passed=True, truth_passed=True).accepted is True
        assert GateResult(inner_passed=True, truth_passed=False).accepted is False
        assert GateResult(inner_passed=True, truth_passed=False).disagreement_signal is True
        assert GateResult(inner_passed=False, truth_passed=None).accepted is False


# ---------------------------------------------------------------------------
# metrics/quality.py + metrics/physics.py
# ---------------------------------------------------------------------------


class TestMetrics:
    def test_congestion_score_returns_one(self):
        st = _placement([("Q1", 10.0, 10.0), ("C1", 50.0, 50.0)])
        nl = _netlist("Q1", "C1")
        assert congestion_score(st, nl, _board(), None) == 1.0

    def test_connectivity_clustering_score(self):
        comps = [
            Component(ref="Q1", footprint="TO-247", bounds=(16, 21)),
            Component(ref="C1", footprint="0805", bounds=(2, 1.2)),
        ]
        nl = Netlist(components=comps, nets=[Net(name="N1", pins=[("Q1", "1"), ("C1", "1")])])
        st = _placement([("Q1", 10.0, 10.0), ("C1", 50.0, 50.0)])
        score = connectivity_clustering_score(st, nl, _QualityContext())
        assert 0.0 <= score <= 1.0

    def test_measure_geometric(self):
        comps = [
            Component(ref="Q1", footprint="TO-247", bounds=(16, 21), net_class="HighVoltage"),
            Component(ref="C1", footprint="0805", bounds=(2, 1.2)),
        ]
        nl = Netlist(components=comps, nets=[])
        st = _placement([("Q1", 10.0, 10.0), ("C1", 50.0, 50.0)])
        metrics = measure_geometric(st, nl, _board())
        assert metrics.overlap_count == 0

    def test_measure_emi_empty_and_loop(self):
        st = _placement([("Q1", 0.0, 0.0), ("C1", 10.0, 0.0), ("C2", 10.0, 10.0)])
        nl = _netlist("Q1", "C1", "C2")
        assert measure_emi(st, nl, None) is not None
        assert measure_emi(st, nl, []) is not None
        emi = measure_emi(st, nl, [["Q1", "C1", "C2"]])
        assert emi.total_loop_area_mm2 > 0

    def test_measure_routability(self):
        st = _placement([("Q1", 10.0, 10.0), ("C1", 50.0, 50.0)])
        nl = _netlist("Q1", "C1")
        metrics = measure_routability(st, nl, _board())
        assert 0.0 <= metrics.completion_pct <= 100.0

    def test_measure_thermal_empty_and_loaded(self):
        st = _placement([("Q1", 10.0, 10.0)])
        nl = _netlist("Q1")
        empty = measure_thermal(st, nl, _board())
        # Empty power_dissipation short-circuits: the kernel is never called
        # and the ambient temperature is returned as the max junction temp.
        # Default ambient is the 60 °C design-limit (ENVIRONMENTAL_SPEC.md
        # derating zero-power point; thermal decision 2026-08-15 §6.4).
        assert empty.max_junction_temp_c == 60.0
        loaded = measure_thermal(st, nl, _board(), power_dissipation={"Q1": 5.0})
        assert loaded.max_junction_temp_c > 0.0


# ---------------------------------------------------------------------------
# validation/tht_check.py + validation/geometric.py
# ---------------------------------------------------------------------------


class TestValidation:
    def test_validate_hole_clearance_collision(self):
        q1 = Component(ref="Q1", footprint="TO-247", bounds=(16, 21))
        q1.pads = [Pin(name="1", number="1", position=(0.0, 0.0), drill=1.0)]  # type: ignore[attr-defined]
        c1 = Component(ref="C1", footprint="0805", bounds=(2, 1.2))
        c1.pads = [Pin(name="1", number="1", position=(0.0, 0.0), drill=1.0)]  # type: ignore[attr-defined]
        nl = Netlist(components=[q1, c1], nets=[])
        msgs = validate_hole_clearance(nl, [(10.0, 10.0), (10.0, 10.0)], min_clearance=0.25)
        assert len(msgs) >= 1

    def test_validate_hole_clearance_no_pads(self):
        q1 = Component(ref="Q1", footprint="TO-247", bounds=(16, 21))
        q1.pads = []  # type: ignore[attr-defined]
        c1 = Component(ref="C1", footprint="0805", bounds=(2, 1.2))
        c1.pads = []  # type: ignore[attr-defined]
        nl = Netlist(components=[q1, c1], nets=[])
        assert validate_hole_clearance(nl, [(0.0, 0.0), (50.0, 50.0)]) == []

    def test_geometric_validator_name_and_validate(self):
        st = _placement([("Q1", 20.0, 20.0), ("C1", 40.0, 40.0)])
        nl = _netlist("Q1", "C1")
        board = _board()
        validator = GeometricValidator()
        assert validator.name == "GeometricValidator"
        result = validator.validate(st, nl, board)
        assert result is not None

    def test_validate_placement_convenience(self):
        st = _placement([("Q1", 20.0, 20.0), ("C1", 40.0, 40.0)])
        nl = _netlist("Q1", "C1")
        result = validate_placement(st, nl, _board())
        assert result is not None
