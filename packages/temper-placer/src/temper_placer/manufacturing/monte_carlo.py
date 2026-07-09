"""
Monte Carlo simulation for statistical tolerance analysis.

This module provides tools to estimate yield probability and identify
manufacturing failure modes using statistical sampling of process variations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np


@dataclass
class DistributionParams:
    """Parameters for a tolerance distribution."""
    mean: float
    std_dev: float = 0.0
    distribution: str = 'normal'  # 'normal', 'uniform'
    min_val: float | None = None
    max_val: float | None = None


@dataclass
class ManufacturingVariables:
    """All manufacturing parameters that vary during production."""
    etch_tolerance: DistributionParams | None = None
    drill_tolerance: DistributionParams | None = None
    registration_x: DistributionParams | None = None
    registration_y: DistributionParams | None = None
    copper_thickness: DistributionParams | None = None
    dielectric_thickness: DistributionParams | None = None


@dataclass
class MonteCarloConfig:
    """Configuration for Monte Carlo simulation."""
    num_samples: int = 1000
    seed: int = 42
    report_percentiles: tuple[float, ...] = (0.01, 0.1, 0.5, 0.9, 0.99)


@dataclass
class MonteCarloResult:
    """Results of a statistical tolerance simulation."""
    num_samples: int
    yield_probability: float
    failure_modes: list[tuple[str, float]] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)


class MonteCarloSimulator:
    """Run Monte Carlo tolerance simulations using JAX-accelerated sampling."""

    def __init__(
        self,
        variables: ManufacturingVariables,
        config: MonteCarloConfig = MonteCarloConfig()
    ):
        self.variables = variables
        self.config = config
        self._rng = np.random.default_rng(config.seed)

    def sample_parameters(self, n: int) -> dict[str, np.ndarray]:
        """
        Generate n samples of all manufacturing parameters.

        Args:
            n: Number of samples to generate.

        Returns:
            Dictionary mapping parameter names to numpy arrays of shape (n,).
        """
        samples = {}
        rng = self._rng

        for name in [
            'etch_tolerance', 'drill_tolerance', 'registration_x',
            'registration_y', 'copper_thickness', 'dielectric_thickness'
        ]:
            params = getattr(self.variables, name)
            if params is None:
                continue

            if params.distribution == 'normal':
                samples[name] = rng.normal(params.mean, params.std_dev, size=n)
            elif params.distribution == 'uniform':
                min_v = params.min_val if params.min_val is not None else params.mean - 1.0
                max_v = params.max_val if params.max_val is not None else params.mean + 1.0
                samples[name] = rng.uniform(min_v, max_v, size=n)

        return samples

    def run_clearance_simulation(
        self,
        positions: np.ndarray,
        bounds: np.ndarray,
        required_clearance: float,
    ) -> MonteCarloResult:
        """
        Run statistical clearance simulation.

        Args:
            positions: (N, 2) nominal component positions.
            bounds: (N, 2) nominal component (width, height).
            required_clearance: Minimum required gap (mm).

        Returns:
            MonteCarloResult with yield probability.
        """
        n_samples = self.config.num_samples
        samples = self.sample_parameters(n_samples)

        # 1. Expand dimensions for vectorization
        # [S, N, 2]
        etch = samples.get('etch_tolerance', np.zeros(n_samples))
        reg_x = samples.get('registration_x', np.zeros(n_samples))
        reg_y = samples.get('registration_y', np.zeros(n_samples))

        # Apply registration to positions: [S, N, 2]
        s_pos = positions[None, :, :] + np.stack([reg_x, reg_y], axis=-1)[:, None, :]

        # Apply etching to bounds: [S, N, 2]
        # Etching reduces clearance (effectively expands components)
        s_widths = bounds[None, :, 0] + 2 * etch[:, None]
        s_heights = bounds[None, :, 1] + 2 * etch[:, None]

        # 2. Vectorized overlap check for each sample
        # This is memory intensive: [S, N, N]
        # But for small N and S=1000 it's fine.

        dx = np.abs(s_pos[:, :, None, 0] - s_pos[:, None, :, 0])
        dy = np.abs(s_pos[:, :, None, 1] - s_pos[:, None, :, 1])

        mw = (s_widths[:, :, None] + s_widths[:, None, :]) / 2.0
        mh = (s_heights[:, :, None] + s_heights[:, None, :]) / 2.0

        # Separation
        sep_x = dx - mw
        sep_y = dy - mh

        # Sample distance = max(sep_x, sep_y)
        dist = np.maximum(sep_x, sep_y)

        # Mask out self-comparison (set to high value)
        n = positions.shape[0]
        mask = np.eye(n, dtype=bool)[None, :, :]
        dist = np.where(mask, 1e6, dist)

        # Check if min distance < required_clearance for each sample
        # [S]
        min_dists = np.min(dist, axis=(1, 2))
        passes = min_dists >= required_clearance

        yield_prob = np.mean(passes.astype(np.float32))

        return MonteCarloResult(
            num_samples=n_samples,
            yield_probability=float(yield_prob),
            stats={
                "mean_min_clearance": float(np.mean(min_dists)),
                "std_min_clearance": float(np.std(min_dists)),
            }
        )
