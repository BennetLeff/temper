import jax.numpy as jnp

from temper_placer.core.board import Board
from temper_placer.core.design_rules import DesignRules
from temper_placer.core.differential_pair import DifferentialPairConstraint
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.routing.maze_router import MazeRouter


class TestDiffPairIntegration:
    def test_rrr_routes_diff_pair(self):
        # 20x20mm board
        board = Board(width=20.0, height=20.0)

        # Components U1 (left) and U2 (right)
        components = [
            Component(
                ref="U1",
                footprint="TEST",
                bounds=(2.0, 2.0),
                pins=[
                    Pin("1", "1", (1.5, 0.5), net="DP"), # Pins outside body
                    Pin("2", "2", (1.5, -0.5), net="DN"),
                ],
                initial_position=(5.0, 10.0),
                # Pins at (6.5, 10.5) and (6.5, 9.5)
            ),
            Component(
                ref="U2",
                footprint="TEST",
                bounds=(2.0, 2.0),
                pins=[
                    Pin("1", "1", (-1.5, 0.5), net="DP"),
                    Pin("2", "2", (-1.5, -0.5), net="DN"),
                ],
                initial_position=(15.0, 10.0),
                # Pins at (13.5, 10.5) and (13.5, 9.5)
            ),
        ]

        nets = [
            Net("DP", [("U1", "1"), ("U2", "1")]),
            Net("DN", [("U1", "2"), ("U2", "2")]),
        ]
        netlist = Netlist(components=components, nets=nets)

        # Positions array (N, 2)
        positions = jnp.array([[5.0, 10.0], [15.0, 10.0]])

        # Design Rules with Diff Pair
        rules = DesignRules()
        rules.differential_pairs.append(DifferentialPairConstraint(
            net_pos="DP",
            net_neg="DN",
            spacing_mm=1.0, # Match pin pitch for this test
            coupling_tolerance_mm=0.5
        ))

        # Use coarser grid for performance
        router = MazeRouter.from_board(board, cell_size_mm=0.5, design_rules=rules)

        assignments = {} # Use default layer

        # Route
        routes = router.rrr_route_all_nets(
            netlist,
            positions,
            net_order=["DP", "DN"],
            assignments=assignments,
            max_iterations=1
        )

        assert "DP" in routes
        assert "DN" in routes
        assert routes["DP"].success, f"DP failed: {routes['DP'].failure_reason}"
        assert routes["DN"].success, f"DN failed: {routes['DN'].failure_reason}"

        # Check that path length > 0
        assert len(routes["DP"].cells) > 0
        assert len(routes["DN"].cells) > 0

        # Verify that we used find_path_diff_pair (implicit check: concurrent routing)
        # If routed individually with RRR, they might not be coupled well or might fail constraints if enforced.
        # But here we just check basic connectivity success.

        print(f"DP Length: {routes['DP'].length}")
        print(f"DN Length: {routes['DN'].length}")
