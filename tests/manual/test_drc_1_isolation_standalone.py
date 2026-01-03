"""Standalone test for DRC-1: Net Isolation."""

import sys
import os

# Set up path
test_dir = os.path.dirname(os.path.abspath(__file__))
repo_root = os.path.dirname(os.path.dirname(test_dir))
sys.path.insert(0, os.path.join(repo_root, "packages/temper-placer/src"))

# Patch out problematic imports before loading
import types

# Create mock modules
mock_modules = {
    "jax": types.ModuleType("jax"),
    "jax.numpy": types.ModuleType("jax.numpy"),
    "jaxlib": types.ModuleType("jaxlib"),
    "flax": types.ModuleType("flax"),
    "flax.struct": types.ModuleType("flax.struct"),
    "flax.linen": types.ModuleType("flax.linen"),
    "optax": types.ModuleType("optax"),
    "chex": types.ModuleType("chex"),
    "temper_placer": types.ModuleType("temper_placer"),
    "temper_placer.core": types.ModuleType("temper_placer.core"),
    "temper_placer.core.board": types.ModuleType("temper_placer.core.board"),
    "temper_placer.core.netlist": types.ModuleType("temper_placer.core.netlist"),
    "temper_placer.core.hypergraph": types.ModuleType("temper_placer.core.hypergraph"),
    "temper_placer.routing": types.ModuleType("temper_placer.routing"),
    "temper_placer.routing.fast_router": types.ModuleType("temper_placer.routing.fast_router"),
    "temper_placer.routing.via_array": types.ModuleType("temper_placer.routing.via_array"),
    "temper_placer.routing.safety_distances": types.ModuleType(
        "temper_placer.routing.safety_distances"
    ),
    "temper_placer.routing.constraints": types.ModuleType("temper_placer.routing.constraints"),
    "temper_placer.routing.layer_assignment": types.ModuleType(
        "temper_placer.routing.layer_assignment"
    ),
    "temper_placer.routing.post_processing": types.ModuleType(
        "temper_placer.routing.post_processing"
    ),
    "temper_placer.routing.post_processing.funnel_smoother": types.ModuleType(
        "temper_placer.routing.post_processing.funnel_smoother"
    ),
    "temper_placer.io": types.ModuleType("temper_placer.io"),
    "temper_placer.io.export_types": types.ModuleType("temper_placer.io.export_types"),
    "temper_placer.io.placement_exporter": types.ModuleType("temper_placer.io.placement_exporter"),
    "temper_placer.losses": types.ModuleType("temper_placer.losses"),
    "temper_placer.losses.base": types.ModuleType("temper_placer.losses.base"),
    "temper_placer.losses.types": types.ModuleType("temper_placer.losses.types"),
    "temper_placer.losses.aesthetic": types.ModuleType("temper_placer.losses.aesthetic"),
    "temper_placer.extraction": types.ModuleType("temper_placer.extraction"),
    "temper_placer.extraction.hypergraph_factory": types.ModuleType(
        "temper_placer.extraction.hypergraph_factory"
    ),
    "temper_placer.core.net_graph": types.ModuleType("temper_placer.core.net_graph"),
}

# Add mock numpy
mock_modules["numpy"] = types.ModuleType("numpy")
mock_modules["numpy"].np = None

for name, mod in mock_modules.items():
    sys.modules[name] = mod

# Set attributes
mock_modules["jax"].numpy = mock_modules["jax.numpy"]
mock_modules["jax"].Array = object
mock_modules["jax.numpy"] = mock_modules["numpy"]
mock_modules["flax"].struct = mock_modules["flax.struct"]


# Set up LayerStackup mock
class MockLayer:
    def __init__(self, name, type_):
        self.name = name
        self.type = type_


class MockLayerStackup:
    def __init__(self, layers):
        self.layers = layers

    @staticmethod
    def default_2layer():
        return MockLayerStackup([MockLayer("L1", "signal"), MockLayer("L4", "signal")])

    @staticmethod
    def default_4layer():
        return MockLayerStackup(
            [
                MockLayer("L1", "signal"),
                MockLayer("L2", "plane"),
                MockLayer("L3", "plane"),
                MockLayer("L4", "signal"),
            ]
        )

    def is_plane_layer(self, layer_idx):
        return layer_idx in [1, 2] if hasattr(self, "layers") and len(self.layers) > 2 else False


mock_modules["temper_placer.core.board"].LayerStackup = MockLayerStackup

# Now import the actual maze_router
exec(
    open(
        os.path.join(repo_root, "packages/temper-placer/src/temper_placer/routing/maze_router.py")
    ).read()
)


# Run test
def test_net_isolation():
    """Verify that nets cannot cross each other (strict isolation)."""
    print("Testing DRC-1: Net Isolation...")

    # 10x10 grid, 1 layer (to force collision)
    router = MazeRouter(
        grid_size=(10, 10),
        cell_size_mm=1.0,
        num_layers=1,
        soft_blocking=True,  # RRR mode (usually allows shorts)
    )

    # Net A: Horizontal (1, 5) -> (8, 5)
    # Net B: Vertical (5, 1) -> (5, 8)
    # They MUST cross at (5, 5)

    pins_a = [(1.0, 5.0), (8.0, 5.0)]
    pins_b = [(5.0, 1.0), (5.0, 8.0)]

    print("Routing Net A...")
    path_a = router.route_net_rrr("NET_A", pins_a, None)
    if not path_a.success:
        print("FAIL: Net A failed to route")
        return False

    print(f"Net A routed: {len(path_a.cells)} cells")

    # Verify owner
    if router.cell_owner.get((5, 5, 0)) != "NET_A":
        print(f"FAIL: Ownership not registered! Owner at (5,5): {router.cell_owner.get((5, 5, 0))}")
        return False

    print(f"Cell (5,5,0) owned by: {router.cell_owner.get((5, 5, 0))}")

    print("Routing Net B (Should fail due to strict isolation)...")
    path_b = router.route_net_rrr("NET_B", pins_b, None)

    if path_b.success:
        print("FAIL: Net B routed successfully (Short created!)")
        cells_a = set((c.x, c.y) for c in path_a.cells)
        cells_b = set((c.x, c.y) for c in path_b.cells)
        intersection = cells_a.intersection(cells_b)
        print(f"Intersection cells: {intersection}")
        print(f"Path A: {sorted(list(cells_a))}")
        print(f"Path B: {sorted(list(cells_b))}")
        print(f"Occupancy at (5,5,0): {router.occupancy[5, 5, 0]}")
        print(f"Cell Owner at (5,5,0): {router.cell_owner.get((5, 5, 0))}")
        return False
    else:
        print("SUCCESS: Net B failed to route (Isolation working)")
        print(f"Failure Reason: {path_b.failure_reason}")
        return True


if __name__ == "__main__":
    success = test_net_isolation()
    sys.exit(0 if success else 1)
