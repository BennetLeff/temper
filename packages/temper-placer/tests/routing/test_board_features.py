from temper_placer.core.board import Board, MountingHole
from temper_placer.routing.maze_router import MazeRouter


class TestBoardFeatureBlocking:
    def test_block_keepouts(self):
        """Test that keepout zones are blocked on all layers."""
        # Create a board with a keepout zone (x, y, w, h)
        # Note: Board.keepouts is (x_min, y_min, x_max, y_max)
        board = Board(
            width=100.0,
            height=100.0,
            origin=(0.0, 0.0),
            keepouts=[(20.0, 20.0, 40.0, 40.0)]
        )

        # Grid size 1.0mm
        router = MazeRouter.from_board(board, cell_size_mm=1.0)

        # Method to be implemented
        router.block_board_features(board)

        # Check center of keepout
        assert router.occupancy[30, 30, 0] == -1

        # Check outside keepout
        assert router.occupancy[10, 10, 0] == 0
        assert router.occupancy[50, 50, 0] == 0

        # Check all layers
        if router.num_layers > 1:
            assert router.occupancy[30, 30, 1] == -1

    def test_block_mounting_holes(self):
        """Test that mounting holes are blocked with radius."""
        board = Board(
            width=100.0,
            height=100.0,
            origin=(0.0, 0.0),
            mounting_holes=[
                MountingHole(position=(50.0, 50.0), diameter=3.0, keepout_radius=5.0)
            ]
        )

        router = MazeRouter.from_board(board, cell_size_mm=1.0)

        # Method to be implemented
        router.block_board_features(board)

        # Check center (50, 50)
        assert router.occupancy[50, 50, 0] == -1

        # Check at radius 4mm (inside keepout)
        # (54, 50) is distance 4 from center
        assert router.occupancy[54, 50, 0] == -1

        # Check at radius 6mm (outside keepout)
        # (56, 50) is distance 6 from center
        assert router.occupancy[56, 50, 0] == 0

    def test_block_multiple_features(self):
        """Test blocking both keepouts and mounting holes."""
        board = Board(
            width=100.0,
            height=100.0,
            origin=(0.0, 0.0),
            keepouts=[(10.0, 10.0, 20.0, 20.0)],
            mounting_holes=[
                MountingHole(position=(80.0, 80.0), diameter=3.0, keepout_radius=4.0)
            ]
        )

        router = MazeRouter.from_board(board, cell_size_mm=1.0)
        router.block_board_features(board)

        # Check keepout
        assert router.occupancy[15, 15, 0] == -1

        # Check mounting hole
        assert router.occupancy[80, 80, 0] == -1
        assert router.occupancy[82, 80, 0] == -1
