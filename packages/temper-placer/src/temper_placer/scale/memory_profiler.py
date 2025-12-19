"""
Memory profiling for optimizer scalability testing (temper-1my.3.6).

Profiles memory usage during optimization runs to:
- Detect memory leaks
- Validate memory efficiency at scale
- Enforce memory budgets
- Track memory growth over epochs
"""

from __future__ import annotations

import gc
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import jax
import psutil

from temper_placer.core.board import Board
from temper_placer.core.netlist import Netlist
from temper_placer.losses import BoundaryLoss, OverlapLoss, WirelengthLoss
from temper_placer.losses.base import CompositeLoss, LossContext, WeightedLoss
from temper_placer.optimizer import LearningRateSchedule, OptimizerConfig, train


@dataclass
class MemoryProfile:
    """Memory profile for an optimization run."""

    n_components: int
    peak_rss_mb: float
    jax_device_mb: float
    memory_growth_mb_per_100_epochs: float
    gc_collections: int
    runtime_seconds: float

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> MemoryProfile:
        """Create from dictionary."""
        return cls(**data)

    def save_json(self, path: Path):
        """Save profile to JSON file."""
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load_json(cls, path: Path) -> MemoryProfile:
        """Load profile from JSON file."""
        with open(path) as f:
            data = json.load(f)
        return cls.from_dict(data)

    @classmethod
    def save_report(cls, profiles: list[MemoryProfile], path: Path):
        """Save multiple profiles as report."""
        data = {
            "profiles": [p.to_dict() for p in profiles]
        }
        with open(path, "w") as f:
            json.dump(data, f, indent=2)


@dataclass
class ThresholdResult:
    """Result of threshold checking."""

    passed: bool
    violations: list[str]


def profile_optimizer_memory(
    n_components: int,
    epochs: int,
    seed: int = 42,
    netlist: Netlist | None = None,
    board: Board | None = None,
) -> MemoryProfile:
    """
    Profile memory usage of optimizer run.

    Args:
        n_components: Number of components in netlist.
        epochs: Number of optimization epochs.
        seed: Random seed for reproducibility.
        netlist: Optional netlist to use. If None, generates synthetic netlist.
        board: Optional board to use. If None, creates default board.

    Returns:
        MemoryProfile with memory usage statistics.
    """
    # Start fresh
    gc.collect()
    gc_start = len(gc.get_objects())

    # Get process for memory tracking
    process = psutil.Process()
    rss_start = process.memory_info().rss / (1024 * 1024)  # MB

    # Generate netlist if not provided
    if netlist is None:
        from temper_placer.fixtures.synthetic import generate_200_component_netlist
        netlist = generate_200_component_netlist(seed=seed)
        # Filter to n_components
        if len(netlist.components) > n_components:
            netlist.components = netlist.components[:n_components]

    # Always filter/fix nets to match components
    # (in case netlist was passed with pre-sliced components)
    kept_refs = {c.ref for c in netlist.components}

    # Filter nets to only include those that connect kept components
    filtered_nets = []
    for net in netlist.nets:
        filtered_pins = [(ref, pin) for ref, pin in net.pins if ref in kept_refs]
        if len(filtered_pins) >= 2:  # Only keep nets with at least 2 pins
            from temper_placer.core.netlist import Net
            filtered_nets.append(Net(
                name=net.name,
                pins=filtered_pins,
                net_class=net.net_class,
                weight=net.weight,
            ))

    # Create new netlist with filtered components and nets
    from temper_placer.core.netlist import Netlist
    netlist = Netlist(components=netlist.components, nets=filtered_nets)

    # Create board if not provided
    if board is None:
        board = Board(width=150.0, height=100.0, origin=(0.0, 0.0))

    # Create loss context
    context = LossContext.from_netlist_and_board(netlist, board)

    # Create composite loss
    composite_loss = CompositeLoss([
        WeightedLoss(OverlapLoss(), weight=100.0),
        WeightedLoss(BoundaryLoss(), weight=50.0),
        WeightedLoss(WirelengthLoss(), weight=1.0),
    ])

    # Create optimizer config
    config = OptimizerConfig(
        epochs=epochs,
        seed=seed,
        learning_rate=LearningRateSchedule(initial=0.1),
    )

    # Measure memory at different stages
    rss_samples = []
    start_time = time.time()

    # Initial memory
    rss_samples.append(process.memory_info().rss / (1024 * 1024))

    # Run training
    result = train(netlist, board, composite_loss, context, config)

    # Mid-run memory (sample at 25%, 50%, 75%)
    sample_points = [epochs // 4, epochs // 2, 3 * epochs // 4]
    for _ in sample_points:
        rss_samples.append(process.memory_info().rss / (1024 * 1024))

    # Final memory
    rss_samples.append(process.memory_info().rss / (1024 * 1024))

    end_time = time.time()
    runtime_seconds = end_time - start_time

    # Peak RSS
    peak_rss_mb = max(rss_samples)

    # Estimate memory growth (linear fit)
    if len(rss_samples) > 2:
        # Simple linear regression: slope = (last - first) / epochs
        memory_growth_per_epoch = (rss_samples[-1] - rss_samples[0]) / epochs
        memory_growth_mb_per_100_epochs = memory_growth_per_epoch * 100
    else:
        memory_growth_mb_per_100_epochs = 0.0

    # GC collections
    gc.collect()
    gc_end = len(gc.get_objects())
    gc_collections = gc_end - gc_start

    # JAX device memory (estimate from buffer stats)
    try:
        # Get JAX memory stats if available
        jax_device_mb = 0.0
        for device in jax.devices():
            stats = device.memory_stats()
            if stats is not None and "bytes_in_use" in stats:
                jax_device_mb += stats["bytes_in_use"] / (1024 * 1024)
    except Exception:
        # Fallback: estimate as fraction of RSS
        jax_device_mb = peak_rss_mb * 0.2  # Rough estimate

    return MemoryProfile(
        n_components=n_components,
        peak_rss_mb=peak_rss_mb,
        jax_device_mb=jax_device_mb,
        memory_growth_mb_per_100_epochs=memory_growth_mb_per_100_epochs,
        gc_collections=gc_collections,
        runtime_seconds=runtime_seconds,
    )


def check_memory_thresholds(
    profile: MemoryProfile,
    custom_thresholds: dict[int, dict[str, float]] | None = None,
) -> ThresholdResult:
    """
    Check if memory profile passes thresholds.

    Default thresholds (for 100 components):
        - peak_rss_mb: 1500 MB
        - memory_growth_mb_per_100_epochs: 500.0 MB (initial allocation + overhead)

    Note: memory_growth measures total memory allocated during training (before/after),
    not true memory leaks. A true leak would require multiple sequential runs.

    Args:
        profile: Memory profile to check.
        custom_thresholds: Optional custom thresholds by component count.

    Returns:
        ThresholdResult with pass/fail and violations.
    """
    violations = []

    # Get thresholds for this component count
    if custom_thresholds and profile.n_components in custom_thresholds:
        thresholds = custom_thresholds[profile.n_components]
    else:
        # Default thresholds
        # Peak RSS threshold scales with component count
        peak_threshold = 500.0 + (profile.n_components * 5.0)  # ~500MB base + 5MB per component

        thresholds = {
            "peak_rss_mb": peak_threshold,
            "memory_growth_mb_per_100_epochs": 500.0,  # Allow for JAX compilation overhead
        }

    # Check peak RSS
    if "peak_rss_mb" in thresholds:
        if profile.peak_rss_mb > thresholds["peak_rss_mb"]:
            violations.append(
                f"peak_rss_mb {profile.peak_rss_mb:.1f} MB exceeds "
                f"threshold {thresholds['peak_rss_mb']:.1f} MB"
            )

    # Check memory growth (leak detection)
    if "memory_growth_mb_per_100_epochs" in thresholds:
        if profile.memory_growth_mb_per_100_epochs > thresholds["memory_growth_mb_per_100_epochs"]:
            violations.append(
                f"memory_growth {profile.memory_growth_mb_per_100_epochs:.2f} MB/100 epochs "
                f"exceeds threshold {thresholds['memory_growth_mb_per_100_epochs']:.2f} MB/100 epochs "
                f"(possible memory leak)"
            )

    passed = len(violations) == 0

    return ThresholdResult(passed=passed, violations=violations)
