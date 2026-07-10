
import numpy as np
import pytest

from temper_placer.manufacturing.monte_carlo import (
    DistributionParams,
    ManufacturingVariables,
    MonteCarloConfig,
    MonteCarloSimulator,
)


def test_parameter_sampling():
    """Verify that sampling produces values from the correct distributions."""
    variables = ManufacturingVariables(
        etch_tolerance=DistributionParams(mean=0.05, std_dev=0.01),
        drill_tolerance=DistributionParams(mean=0.1, min_val=0.05, max_val=0.15, distribution='uniform')
    )

    simulator = MonteCarloSimulator(variables, config=MonteCarloConfig(num_samples=10000))
    samples = simulator.sample_parameters(10000)

    # Normal distribution
    etch = samples['etch_tolerance']
    assert np.mean(etch) == pytest.approx(0.05, abs=0.001)
    assert np.std(etch) == pytest.approx(0.01, abs=0.001)

    # Uniform distribution
    drill = samples['drill_tolerance']
    assert np.min(drill) >= 0.05
    assert np.max(drill) <= 0.15
    assert np.mean(drill) == pytest.approx(0.1, abs=0.002)

def test_monte_carlo_yield_calculation():
    """Verify yield probability calculation for a controlled case."""
    # Two components at 10.05mm center-to-center.
    # Sizes are 10x10. Nominal gap = 0.05mm.
    # Required clearance = 0.05mm.
    # If etch_tolerance > 0, they fail.

    positions = np.array([[0.0, 0.0], [10.05, 0.0]])
    bounds = np.array([[10.0, 10.0], [10.0, 10.0]])

    # 50% etch > 0
    variables = ManufacturingVariables(
        etch_tolerance=DistributionParams(mean=0.0, std_dev=0.01)
    )

    simulator = MonteCarloSimulator(variables, config=MonteCarloConfig(num_samples=1000))
    result = simulator.run_clearance_simulation(positions, bounds, required_clearance=0.05)

    # Since mean etch is 0, approx 50% should be positive (failure) and 50% negative (pass)
    # Actually etch > 0 reduces gap. Gap = 0.05 - 2*etch.
    # Pass if 0.05 - 2*etch >= 0.05  => 2*etch <= 0 => etch <= 0.
    assert result.yield_probability == pytest.approx(0.5, abs=0.1)

