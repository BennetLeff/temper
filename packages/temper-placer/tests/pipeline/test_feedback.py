import pytest
import jax.numpy as jnp
from temper_placer.pipeline.feedback import FeedbackGenerator, FailureType, RoutingDiagnostic, RoutabilityReport
from temper_placer.core.state import PlacementState
from temper_placer.core.netlist import Netlist, Component, Net, Pin

@pytest.fixture
def mock_state():
    # Setup a minimal netlist and state
    c1 = Component(ref="U1", footprint="SOIC-8", bounds=(5, 5))
    c2 = Component(ref="R1", footprint="R0603", bounds=(1.6, 0.8))
    
    # Add pins
    c1.pins.append(Pin(name="1", number="1", position=(-2.0, -2.0), net="SIG1"))
    c2.pins.append(Pin(name="1", number="1", position=(-0.5, 0.0), net="SIG1"))
    
    netlist = Netlist(
        components=[c1, c2],
        nets=[Net(name="SIG1", pins=[("U1", "1"), ("R1", "1")])]
    )
    
    state = PlacementState(
        positions=jnp.array([[10.0, 10.0], [20.0, 10.0]]),
        rotation_logits=jnp.zeros((2, 4))
    )
    state.netlist = netlist 
    return state

def test_generate_no_path_adjustment(mock_state):
    gen = FeedbackGenerator()
    
    diagnostic = RoutingDiagnostic(
        failure_type=FailureType.NO_PATH,
        net="SIG1",
        blocking_elements=["U1"],
        message="Path blocked"
    )
    
    report = RoutabilityReport(
        total_congestion=0,
        max_congestion=0,
        bottleneck_cells=[],
        unrouted_estimate=1,
        advice=[],
        feasible=False,
        diagnostics=[diagnostic]
    )
    
    adjustments = gen.generate(report, mock_state)
    
    assert len(adjustments) == 1
    assert adjustments[0].component == "U1"
    assert adjustments[0].adjustment_type == "move"
    assert adjustments[0].direction is not None

def test_generate_congestion_adjustment(mock_state):
    gen = FeedbackGenerator()
    
    diagnostic = RoutingDiagnostic(
        failure_type=FailureType.CONGESTION,
        blocking_elements=["R1"],
        location=(15.0, 10.0),
        message="High congestion"
    )
    
    report = RoutabilityReport(
        total_congestion=10,
        max_congestion=5,
        bottleneck_cells=[],
        unrouted_estimate=2,
        advice=[],
        feasible=False,
        diagnostics=[diagnostic]
    )
    
    adjustments = gen.generate(report, mock_state)
    
    assert len(adjustments) == 1
    assert adjustments[0].component == "R1"
    assert adjustments[0].adjustment_type == "spread"