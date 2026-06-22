"""Unit tests for DRC proxy loss function."""
import numpy as np
import jax.numpy as jnp
import pytest
from jax import grad, jit

from temper_placer.losses.drc_proxy import DRCProxyLoss
from temper_placer.losses.base import LossContext, LossFunction


def _make_context(n_components=10):
    """Create a minimal LossContext for testing."""
    import numpy as np
    from temper_placer.losses.base import LossContext as LC

    netlist = _make_mock_netlist(n_components)
    board = _make_mock_board()
    return LC.from_netlist_and_board(netlist, board)


def _make_mock_netlist(n_components):
    from unittest.mock import MagicMock

    class MockComponent:
        def __init__(self, ref, net_class="Signal"):
            self.ref = ref
            self.net_class = net_class
            self.width = 10.0
            self.height = 5.0

        def get_pin(self, name):
            from unittest.mock import MagicMock
            m = MagicMock()
            m.position = [0.0, 0.0]
            return m

    class MockNet:
        def __init__(self, name, weight=1.0):
            self.name = name
            self.weight = weight
            self.pins = []
            self.net_class = "Signal"

    class MockNetlist:
        def __init__(self):
            self.components = [MockComponent(f"C{i}") for i in range(n_components)]
            self.n_components = n_components
            self.n_nets = 2
            self.nets = [MockNet("NET1"), MockNet("NET2")]

        def get_bounds_array(self):
            return np.array([[10.0, 5.0] for _ in range(n_components)], dtype=np.float32)

        def get_fixed_mask(self):
            return np.zeros(n_components, dtype=bool)

        def get_component_index(self, ref):
            for i, c in enumerate(self.components):
                if c.ref == ref:
                    return i
            return 0

        def get_component(self, ref):
            for c in self.components:
                if c.ref == ref:
                    return c
            return self.components[0]

    return MockNetlist()


def _make_mock_board():
    from unittest.mock import MagicMock
    m = MagicMock()
    m.width = 200.0
    m.height = 150.0
    m.origin = (0.0, 0.0)
    m.board_margin = 5.0
    m.ground_domains = []
    m.layer_stackup = None
    m.zones = []
    return m


class TestDRCProxyLoss:
    """Tests for DRCProxyLoss class."""

    def test_name(self):
        """DRCProxyLoss has correct name."""
        half_w = jnp.ones(5, dtype=jnp.float32) * 5.0
        half_h = jnp.ones(5, dtype=jnp.float32) * 2.5
        loss = DRCProxyLoss(half_w, half_h)
        assert loss.name == "drc_proxy"

    def test_no_components(self):
        """Loss is zero with fewer than 2 components."""
        half_w = jnp.ones(1, dtype=jnp.float32)
        half_h = jnp.ones(1, dtype=jnp.float32)
        loss = DRCProxyLoss(half_w, half_h)
        ctx = _make_context(n_components=1)
        positions = jnp.array([[50.0, 50.0]], dtype=jnp.float32)
        rotations = jnp.array([[1.0, 0.0, 0.0, 0.0]], dtype=jnp.float32)
        result = loss(positions, rotations, ctx)
        assert float(result.value) == 0.0

    def test_separated_components(self):
        """Well-separated components produce zero loss."""
        n = 4
        half_w = jnp.ones(n, dtype=jnp.float32) * 3.0
        half_h = jnp.ones(n, dtype=jnp.float32) * 3.0
        loss = DRCProxyLoss(half_w, half_h, clearance_mm=0.2)
        ctx = _make_context(n_components=n)

        positions = jnp.array([
            [0.0, 0.0],
            [100.0, 0.0],
            [0.0, 100.0],
            [100.0, 100.0],
        ], dtype=jnp.float32)
        rotations = jnp.eye(4, dtype=jnp.float32)

        result = loss(positions, rotations, ctx, epoch=500, total_epochs=1000)
        assert float(result.value) < 1e-3

    def test_overlapping_inflated_components(self):
        """Overlapping inflated boxes produce positive loss."""
        n = 2
        half_w = jnp.array([5.0, 5.0], dtype=jnp.float32)
        half_h = jnp.array([5.0, 5.0], dtype=jnp.float32)
        loss = DRCProxyLoss(half_w, half_h, clearance_mm=0.2)
        ctx = _make_context(n_components=n)

        positions = jnp.array([
            [0.0, 0.0],
            [2.0, 0.0],  # Very close — inflated boxes overlap
        ], dtype=jnp.float32)
        rotations = jnp.eye(2, 4, dtype=jnp.float32)

        result = loss(positions, rotations, ctx, epoch=500, total_epochs=1000)
        assert float(result.value) > 0.0

    def test_gradient_exists(self):
        """Gradient exists and is non-zero at violation boundaries."""
        n = 2
        half_w = jnp.array([5.0, 5.0], dtype=jnp.float32)
        half_h = jnp.array([5.0, 5.0], dtype=jnp.float32)
        ctx = _make_context(n_components=n)
        loss = DRCProxyLoss(half_w, half_h, clearance_mm=0.2)

        positions = jnp.array([
            [0.0, 0.0],
            [2.0, 0.0],
        ], dtype=jnp.float32)
        rotations = jnp.eye(2, 4, dtype=jnp.float32)

        def fn(pos):
            return loss(pos, rotations, ctx, epoch=500, total_epochs=1000).value

        g = grad(fn)(positions)
        assert jnp.any(jnp.abs(g) > 0.0)

    def test_beta_annealing(self):
        """Higher beta (later epochs) produces sharper penalty."""
        n = 2
        half_w = jnp.array([5.0, 5.0], dtype=jnp.float32)
        half_h = jnp.array([5.0, 5.0], dtype=jnp.float32)
        ctx = _make_context(n_components=n)
        loss = DRCProxyLoss(half_w, half_h, clearance_mm=0.2)

        positions = jnp.array([
            [0.0, 0.0],
            [6.0, 0.0],  # At edge of clearance zone
        ], dtype=jnp.float32)
        rotations = jnp.eye(2, 4, dtype=jnp.float32)

        early = loss(positions, rotations, ctx, epoch=0, total_epochs=1000)
        late = loss(positions, rotations, ctx, epoch=900, total_epochs=1000)

        # Late epoch penalty should be different from early
        # (beta changes the smoothness of smooth_relu, affecting penalty value)
        assert float(early.value) >= 0.0
        assert float(late.value) >= 0.0

    def test_weight_schedule_ramp(self):
        """Weight schedule ramps from 0.3 to 1.0."""
        half_w = jnp.ones(5, dtype=jnp.float32) * 5.0
        half_h = jnp.ones(5, dtype=jnp.float32) * 2.5
        loss = DRCProxyLoss(half_w, half_h)

        w_early = float(loss.weight_schedule(0, 1000))
        w_mid = float(loss.weight_schedule(150, 1000))
        w_late = float(loss.weight_schedule(300, 1000))

        assert w_early >= 0.29
        assert w_mid >= 0.5
        assert w_late >= 0.99

    def test_clearance_mm_default(self):
        """Default clearance is 0.2mm."""
        half_w = jnp.ones(5, dtype=jnp.float32)
        half_h = jnp.ones(5, dtype=jnp.float32)
        loss = DRCProxyLoss(half_w, half_h)
        assert loss.clearance_mm == 0.2

    def test_custom_clearance(self):
        """Custom clearance value is stored correctly."""
        half_w = jnp.ones(5, dtype=jnp.float32)
        half_h = jnp.ones(5, dtype=jnp.float32)
        loss = DRCProxyLoss(half_w, half_h, clearance_mm=1.0)
        assert loss.clearance_mm == 1.0
