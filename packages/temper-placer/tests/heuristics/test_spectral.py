import numpy as np
import pytest
from temper_placer.core.board import Board, LayerStackup
from temper_placer.core.netlist import Component, Net, Netlist
from temper_placer.heuristics.base import PlacementConstraints, PlacementContext, ComponentPlacement
from temper_placer.heuristics.spectral import SpectralPlacementHeuristic


class TestSpectralHeuristic:
    def create_simple_context(self) -> PlacementContext:
        """Create a context with a simple connected graph."""
        # 3 components in a line: U1 -- U2 -- U3
        u1 = Component(ref="U1", footprint="DIP-8", bounds=(10.0, 10.0), fixed=False)
        u2 = Component(ref="U2", footprint="DIP-8", bounds=(10.0, 10.0), fixed=False)
        u3 = Component(ref="U3", footprint="DIP-8", bounds=(10.0, 10.0), fixed=False)

        # Connections
        net1 = Net(name="N1", pins=[("U1", "1"), ("U2", "1")])
        net2 = Net(name="N2", pins=[("U2", "2"), ("U3", "1")])

        netlist = Netlist()
        netlist.components = [u1, u2, u3]
        netlist.nets = [net1, net2]
        netlist.build_indices()

        # 100x100 board
        board = Board(width=100.0, height=100.0)

        return PlacementContext(
            netlist=netlist,
            board=board,
            constraints=PlacementConstraints(),  # Use default constraints
        )

    def test_spectral_placement_success(self):
        """Verify spectral placement generates valid coordinates."""
        context = self.create_simple_context()
        heuristic = SpectralPlacementHeuristic(confidence=0.5)

        result = heuristic.apply(context)

        assert result.success
        assert len(result.placements) == 3

        # Check basic properties
        u1_pos = result.placements["U1"].position
        u2_pos = result.placements["U2"].position
        u3_pos = result.placements["U3"].position

        for ref, p in [("U1", u1_pos), ("U2", u2_pos), ("U3", u3_pos)]:
            assert 0 <= p[0] <= 100, f"{ref} X out of bounds"
            assert 0 <= p[1] <= 100, f"{ref} Y out of bounds"

        d_12 = np.linalg.norm(np.array(u1_pos) - np.array(u2_pos))
        d_23 = np.linalg.norm(np.array(u2_pos) - np.array(u3_pos))
        d_13 = np.linalg.norm(np.array(u1_pos) - np.array(u3_pos))

        assert d_12 > 1.0, "Components too close"
        assert d_23 > 1.0, "Components too close"
        assert d_13 > 1.0, "Components too close"
        assert np.linalg.norm(np.array(u1_pos)) > 0.001

    def test_spectral_respects_fixed_components(self):
        """Verify fixed components are ignored (not moved)."""
        context = self.create_simple_context()
        context.current_placements["U1"] = ComponentPlacement(
            ref="U1", position=(10.0, 10.0), rotation=0
        )

        heuristic = SpectralPlacementHeuristic()
        result = heuristic.apply(context)

        assert "U1" not in result.placements
        assert "U2" in result.placements
        assert "U3" in result.placements

    def test_empty_graph_handling(self):
        """Verify graceful handling of empty graph."""
        netlist = Netlist()
        board = Board(width=100.0, height=100.0)
        context = PlacementContext(netlist=netlist, board=board, constraints=PlacementConstraints())

        heuristic = SpectralPlacementHeuristic()
        result = heuristic.apply(context)

        assert result.success
        assert len(result.placements) == 0

    def test_spectral_disconnected_components(self):
        """Test that spectral layout handles disconnected components without stacking them."""
        # 2 components on Net A, 2 components on Net B
        components = [
            Component(ref="R1", footprint="0603", bounds=(1, 1)),
            Component(ref="R2", footprint="0603", bounds=(1, 1)),
            Component(ref="R3", footprint="0603", bounds=(1, 1)),
            Component(ref="R4", footprint="0603", bounds=(1, 1)),
        ]
        nets = [
            Net(name="A", pins=[("R1", "1"), ("R2", "1")]),
            Net(name="B", pins=[("R3", "1"), ("R4", "1")]),
        ]
        netlist = Netlist(components=components, nets=nets)
        board = Board(width=100, height=100, origin=(0, 0), zones=[], ground_domains=[], 
                      layer_stackup=LayerStackup.default_4layer())
        
        from temper_placer.io.config_loader import PlacementConstraints
        constraints = PlacementConstraints(board_margin_mm=5.0)
        context = PlacementContext(netlist=netlist, board=board, constraints=constraints)
        
        heuristic = SpectralPlacementHeuristic()
        result = heuristic.apply(context)
        
        assert result.success is True
        assert len(result.placements) == 4
        
        pos1 = result.placements["R1"].position
        pos3 = result.placements["R3"].position
        
        dist = ((pos1[0] - pos3[0])**2 + (pos1[1] - pos3[1])**2)**0.5
        # If they are stacked at origin or center, dist might be 0.
        assert dist > 1.0, f"Disconnected components stacked at {pos1} and {pos3}"

    def test_spectral_bipartition(self):
        """Test that spectral layout separates two tightly connected clusters."""
        # Cluster A: U1, U2, U3 (tightly connected)
        # Cluster B: U4, U5, U6 (tightly connected)
        # Connector: Net between U1 and U4
        components = [Component(ref=f"U{i}", footprint="0603", bounds=(1, 1)) for i in range(1, 7)]
        nets = [
            Net(name="A1", pins=[("U1", "1"), ("U2", "1")]),
            Net(name="A2", pins=[("U2", "2"), ("U3", "1")]),
            Net(name="A3", pins=[("U3", "2"), ("U1", "2")]),
            Net(name="B1", pins=[("U4", "1"), ("U5", "1")]),
            Net(name="B2", pins=[("U5", "2"), ("U6", "1")]),
            Net(name="B3", pins=[("U6", "2"), ("U4", "2")]),
            Net(name="CONN", pins=[("U1", "3"), ("U4", "3")]),
        ]
        netlist = Netlist(components=components, nets=nets)
        board = Board(width=100, height=100)
        from temper_placer.io.config_loader import PlacementConstraints
        context = PlacementContext(netlist=netlist, board=board, constraints=PlacementConstraints())
        
        heuristic = SpectralPlacementHeuristic()
        result = heuristic.apply(context)
        
        # Check that Cluster A and Cluster B are far apart
        # Mean of A
        pos_a = np.mean([result.placements[f"U{i}"].position for i in range(1, 4)], axis=0)
        # Mean of B
        pos_b = np.mean([result.placements[f"U{i}"].position for i in range(4, 7)], axis=0)
        
        dist = np.linalg.norm(pos_a - pos_b)
        # They should be significantly separated on the 100x100 board
        assert dist > 20.0, f"Clusters not well separated: dist={dist}"