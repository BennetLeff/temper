import jax.numpy as jnp
import pytest

from temper_placer.core.board import Board, LayerStackup, Layer
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.losses.base import LossContext
from temper_placer.losses.wirelength import WirelengthLoss


@pytest.fixture
def simple_context():
    # Explicitly use 1-layer stackup to avoid RHWL scaling (division by 2)
    layer_stackup = LayerStackup(layers=[Layer("F.Cu", "signal", is_routable=True)])
    board = Board(width=100.0, height=100.0, layer_stackup=layer_stackup)

    c1 = Component(
        "C1", "R0603", (1.0, 0.5), pins=[Pin("1", "1", (-0.5, 0)), Pin("2", "2", (0.5, 0))]
    )
    c2 = Component(
        "C2", "R0603", (1.0, 0.5), pins=[Pin("1", "1", (-0.5, 0)), Pin("2", "2", (0.5, 0))]
    )
    c3 = Component(
        "C3", "R0603", (1.0, 0.5), pins=[Pin("1", "1", (-0.5, 0)), Pin("2", "2", (0.5, 0))]
    )

    # Net A: C1-C2 (weight 1.0)
    # Net B: C2-C3 (weight 1.0)
    net_a = Net("NetA", [("C1", "2"), ("C2", "1")], weight=1.0)
    net_b = Net("NetB", [("C2", "2"), ("C3", "1")], weight=1.0)

    netlist = Netlist([c1, c2, c3], [net_a, net_b])

    return LossContext.from_netlist_and_board(netlist, board)


def test_wirelength_default_weights(simple_context):
    # Use legacy alpha=10.0 for backward compatible expected values
    loss_fn = WirelengthLoss(alpha=10.0)

    # Positions: C1(0,0), C2(10,0), C3(20,0)
    # Net A length ~ 10
    # Net B length ~ 10
    positions = jnp.array([[0.0, 0.0], [10.0, 0.0], [20.0, 0.0]])
    rotations = jnp.array([[1.0, 0, 0, 0], [1.0, 0, 0, 0], [1.0, 0, 0, 0]])

    result = loss_fn(positions, rotations, simple_context)

    # Approx 18.3 (Geometric 9.0 + 9.0 = 18.0)
    assert 18.0 < result.value < 19.0


def test_wirelength_custom_weights(simple_context):
    # Override NetA weight to 10.0
    loss_fn = WirelengthLoss(alpha=10.0, net_weights={"NetA": 10.0})

    positions = jnp.array([[0.0, 0.0], [10.0, 0.0], [20.0, 0.0]])
    rotations = jnp.array([[1.0, 0, 0, 0], [1.0, 0, 0, 0], [1.0, 0, 0, 0]])

    result = loss_fn(positions, rotations, simple_context)

    # Net A (10.0 * 9) + Net B (1.0 * 9) = 90 + 9 = 99.0
    # Soft max approx adds a bit
    assert 99.0 < result.value < 102.0


def test_wirelength_net_class_weights(simple_context):
    # Assign net classes
    simple_context.netlist.nets[0].net_class = "HighSpeed"  # NetA
    simple_context.netlist.nets[1].net_class = "Power"  # NetB

    # Re-create context to pick up net classes?
    # Net classes are on components usually, but Net has net_class too.
    # LossContext uses Component net_class for HV/LV indices.
    # Net.net_class is stored in Net object.

    # Test weight by net_class
    loss_fn = WirelengthLoss(alpha=10.0, net_weights={"HighSpeed": 5.0, "Power": 0.5})

    positions = jnp.array([[0.0, 0.0], [10.0, 0.0], [20.0, 0.0]])
    rotations = jnp.array([[1.0, 0, 0, 0], [1.0, 0, 0, 0], [1.0, 0, 0, 0]])

    result = loss_fn(positions, rotations, simple_context)

    # Net A (HighSpeed): 5.0 * 9 = 45
    # Net B (Power): 0.5 * 9 = 4.5
    # Total = 49.5
    assert 49.0 < result.value < 51.0


class TestWirelengthAlphaAnnealing:
    """Tests for alpha annealing behavior in WirelengthLoss."""

    def test_alpha_annealing_defaults(self):
        """Test default annealing parameters."""
        loss = WirelengthLoss()
        assert loss.alpha_start == 1.0
        assert loss.alpha_end == 20.0
        assert loss.alpha_warmup == 0.2

    def test_alpha_annealing_constant_during_warmup(self):
        """Test alpha is constant during warmup phase."""
        loss = WirelengthLoss(alpha_start=1.0, alpha_end=20.0, alpha_warmup=0.2)
        total_epochs = 1000

        # Epochs 0-199 (first 20%) should have alpha = 1.0
        assert loss._get_alpha(0, total_epochs) == 1.0
        assert loss._get_alpha(50, total_epochs) == 1.0
        assert loss._get_alpha(100, total_epochs) == 1.0
        assert loss._get_alpha(199, total_epochs) == 1.0

    def test_alpha_annealing_increases_after_warmup(self):
        """Test alpha increases after warmup phase."""
        loss = WirelengthLoss(alpha_start=1.0, alpha_end=20.0, alpha_warmup=0.2)
        total_epochs = 1000

        # Epoch 200 should start annealing
        alpha_200 = loss._get_alpha(200, total_epochs)
        alpha_500 = loss._get_alpha(500, total_epochs)
        alpha_800 = loss._get_alpha(800, total_epochs)
        alpha_999 = loss._get_alpha(999, total_epochs)

        # Alpha should increase over epochs
        assert alpha_200 > 1.0
        assert alpha_500 > alpha_200
        assert alpha_800 > alpha_500
        assert alpha_999 > alpha_800

        # Final alpha should be close to alpha_end
        assert abs(alpha_999 - 20.0) < 0.5

    def test_alpha_annealing_linear_interpolation(self):
        """Test that annealing uses linear interpolation."""
        loss = WirelengthLoss(alpha_start=2.0, alpha_end=12.0, alpha_warmup=0.0)
        total_epochs = 10

        # With warmup=0, annealing starts at epoch 0
        # At epoch 5 (50%), alpha should be 7.0 (midpoint)
        assert loss._get_alpha(5, total_epochs) == pytest.approx(7.0, abs=0.1)

        # At epoch 0, alpha should be 2.0
        assert loss._get_alpha(0, total_epochs) == 2.0

        # At epoch 10, alpha should be 12.0
        assert loss._get_alpha(10, total_epochs) == 12.0

    def test_alpha_legacy_compatibility(self):
        """Test backward compatibility with legacy alpha parameter."""
        # When alpha is provided, it should be used for both start and end
        loss_legacy = WirelengthLoss(alpha=15.0)
        assert loss_legacy.alpha_start == 15.0
        assert loss_legacy.alpha_end == 15.0
        assert loss_legacy.alpha_warmup == 1.0  # No annealing

        # Alpha should be constant at 15.0 regardless of epoch
        assert loss_legacy._get_alpha(0, 1000) == 15.0
        assert loss_legacy._get_alpha(500, 1000) == 15.0
        assert loss_legacy._get_alpha(999, 1000) == 15.0

    def test_alpha_annealing_with_custom_parameters(self):
        """Test annealing with custom start/end/warmup values."""
        loss = WirelengthLoss(alpha_start=5.0, alpha_end=50.0, alpha_warmup=0.1)
        total_epochs = 1000

        # First 100 epochs at alpha=5.0
        assert loss._get_alpha(0, total_epochs) == 5.0
        assert loss._get_alpha(99, total_epochs) == 5.0
        assert loss._get_alpha(100, total_epochs) > 5.0

        # Progress should be monotonic
        alpha_values = [loss._get_alpha(e, total_epochs) for e in range(0, 1000, 100)]
        for i in range(1, len(alpha_values)):
            assert (
                alpha_values[i] >= alpha_values[i - 1] - 0.001
            )  # Allow small floating point error

    def test_alpha_annealing_edge_cases(self):
        """Test alpha annealing edge cases."""
        loss = WirelengthLoss(alpha_start=1.0, alpha_end=20.0, alpha_warmup=0.2)

        # Single epoch
        assert loss._get_alpha(0, 1) == 1.0

        # Total epochs = 0 (should not crash)
        assert loss._get_alpha(0, 0) == 1.0

        # Epoch beyond total_epochs (should cap at alpha_end)
        assert loss._get_alpha(2000, 1000) == 20.0

    def test_high_alpha_approximates_true_hpwl(self):
        """Test that high alpha produces values closer to true HPWL."""
        # True HPWL for simple 2-pin net is just the Manhattan distance
        # With very high alpha, LogSumExp approaches max/min exactly

        layer_stackup = LayerStackup(layers=[Layer("F.Cu", "signal", is_routable=True)])
        board = Board(width=100.0, height=100.0, layer_stackup=layer_stackup)

        c1 = Component(
            "C1", "R0603", (1.0, 0.5), pins=[Pin("1", "1", (-0.5, 0)), Pin("2", "2", (0.5, 0))]
        )
        c2 = Component(
            "C2", "R0603", (1.0, 0.5), pins=[Pin("1", "1", (-0.5, 0)), Pin("2", "2", (0.5, 0))]
        )

        # Net from (0,0) to (10,0) - true HPWL is 10.0
        net = Net("NetA", [("C1", "2"), ("C2", "1")], weight=1.0)
        netlist = Netlist([c1, c2], [net])
        context = LossContext.from_netlist_and_board(netlist, board)

        positions = jnp.array([[0.0, 0.0], [10.0, 0.0]])
        rotations = jnp.array([[1.0, 0, 0, 0], [1.0, 0, 0, 0]])

        # Low alpha (smooth) should give higher value due to LogSumExp approximation
        loss_low = WirelengthLoss(alpha=1.0)
        result_low = loss_low(positions, rotations, context)

        # High alpha (sharp) should give value closer to true HPWL (10.0)
        loss_high = WirelengthLoss(alpha=100.0)
        result_high = loss_high(positions, rotations, context)

        # High alpha should be closer to or equal true HPWL
        assert result_high.value <= result_low.value + 0.5
        assert 9.9 < result_high.value < 10.2  # Close to true HPWL of 10.0
