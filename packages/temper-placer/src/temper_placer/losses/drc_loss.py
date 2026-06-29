"""
DRC (Design Rule Check) loss function with caching.

This module provides:
- DRCLoss: Loss function that wraps KiCad DRC validation
- Caching to avoid running expensive DRC on every epoch
- Violation history tracking for visualization

DRC is non-differentiable, so this loss function returns a cached penalty
value. It's designed for periodic evaluation during optimization.
"""

from __future__ import annotations

import contextlib
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import jax.numpy as jnp
from jax import Array

from temper_placer.losses.base import LossContext, LossFunction, LossResult
from temper_placer.validation.drc import (
    DRCResult,
    DRCViolation,
    KiCadDRCValidator,
)


@dataclass
class DRCCacheEntry:
    """
    Cached DRC result with metadata.

    Attributes:
        penalty: Computed penalty value.
        epoch: Epoch when DRC was run.
        result: Full DRCResult (optional, for detailed analysis).
        elapsed_ms: Time taken for DRC.
    """

    penalty: float
    epoch: int
    result: DRCResult | None = None
    elapsed_ms: float = 0.0


@dataclass
class DRCHistory:
    """
    History of DRC evaluations during optimization.

    Useful for tracking progress and visualization.

    Attributes:
        entries: List of (epoch, penalty) tuples.
        violation_counts: List of (epoch, errors, warnings) tuples.
        total_evaluations: Total number of DRC runs.
        total_time_ms: Total time spent on DRC.
    """

    entries: list[tuple[int, float]] = field(default_factory=list)
    violation_counts: list[tuple[int, int, int]] = field(default_factory=list)
    total_evaluations: int = 0
    total_time_ms: float = 0.0

    def add(
        self,
        epoch: int,
        penalty: float,
        errors: int = 0,
        warnings: int = 0,
        elapsed_ms: float = 0.0,
    ) -> None:
        """Add a new DRC evaluation to history."""
        self.entries.append((epoch, penalty))
        self.violation_counts.append((epoch, errors, warnings))
        self.total_evaluations += 1
        self.total_time_ms += elapsed_ms

    def best_penalty(self) -> float:
        """Get the minimum penalty achieved."""
        if not self.entries:
            return float("inf")
        return min(p for _, p in self.entries)

    def latest_penalty(self) -> float:
        """Get the most recent penalty."""
        if not self.entries:
            return float("inf")
        return self.entries[-1][1]

    def improvement_trend(self, window: int = 5) -> float:
        """
        Calculate improvement trend over recent evaluations.

        Returns:
            Positive = improving, negative = worsening, 0 = stable.
        """
        if len(self.entries) < 2:
            return 0.0

        recent = self.entries[-window:]
        if len(recent) < 2:
            return 0.0

        # Linear regression slope (negative slope = improving)
        n = len(recent)
        sum_x = sum(i for i in range(n))
        sum_y = sum(p for _, p in recent)
        sum_xy = sum(i * p for i, (_, p) in enumerate(recent))
        sum_x2 = sum(i * i for i in range(n))

        denominator = n * sum_x2 - sum_x * sum_x
        if denominator == 0:
            return 0.0

        slope = (n * sum_xy - sum_x * sum_y) / denominator
        return -slope  # Negate so positive = improving

    def summary(self) -> str:
        """Get a summary of DRC history."""
        if not self.entries:
            return "No DRC evaluations yet"

        lines = [
            f"DRC History: {self.total_evaluations} evaluations in {self.total_time_ms:.0f}ms",
            f"  Best penalty: {self.best_penalty():.2f}",
            f"  Latest penalty: {self.latest_penalty():.2f}",
            f"  Trend: {self.improvement_trend():.3f} (positive = improving)",
        ]

        if self.violation_counts:
            _, errors, warnings = self.violation_counts[-1]
            lines.append(f"  Latest: {errors} errors, {warnings} warnings")

        return "\n".join(lines)


class DRCLoss(LossFunction):
    """
    Loss function that evaluates DRC periodically and caches results.

    DRC is expensive (hundreds of ms to seconds) and non-differentiable,
    so we only run it every N epochs. Between runs, we return the cached
    penalty value.

    Example:
        drc_loss = DRCLoss(
            validator=KiCadDRCValidator(),
            pcb_exporter=my_exporter_function,
            eval_interval=50,  # Run DRC every 50 epochs
        )

        # In training loop:
        result = drc_loss(positions, rotations, context)
        # result.value is the cached penalty

        # Check history:
        print(drc_loss.history.summary())

    Attributes:
        validator: KiCadDRCValidator instance.
        pcb_exporter: Function to export current placement to a temp PCB file.
        eval_interval: Epochs between DRC evaluations.
        base_penalty: Penalty to use when DRC is not available.
        cache_results: Whether to cache full DRCResult objects.
    """

    def __init__(
        self,
        validator: KiCadDRCValidator | None = None,
        pcb_exporter: Callable[[Array, Array, LossContext], Path] | None = None,
        eval_interval: int = 50,
        base_penalty: float = 0.0,
        cache_results: bool = False,
        fail_penalty: float = 100.0,
    ):
        """
        Initialize DRC loss.

        Args:
            validator: KiCadDRCValidator instance. If None, creates default.
            pcb_exporter: Function that takes (positions, rotations, context)
                and returns path to exported PCB file. If None, DRC is skipped.
            eval_interval: Run DRC every N epochs.
            base_penalty: Default penalty when DRC can't be run.
            cache_results: Store full DRCResult objects (uses more memory).
            fail_penalty: Penalty for failed DRC runs.
        """
        self._validator = validator or KiCadDRCValidator()
        self._pcb_exporter = pcb_exporter
        self._eval_interval = max(1, eval_interval)
        self._base_penalty = base_penalty
        self._cache_results = cache_results
        self._fail_penalty = fail_penalty

        # Cache state
        self._cache: DRCCacheEntry | None = None
        self._history = DRCHistory()

        # Track last evaluation epoch
        self._last_evalepoch: int = -1

    @property
    def name(self) -> str:
        return "drc_loss"

    @property
    def validator(self) -> KiCadDRCValidator:
        """Get the DRC validator."""
        return self._validator

    @property
    def history(self) -> DRCHistory:
        """Get the DRC evaluation history."""
        return self._history

    @property
    def eval_interval(self) -> int:
        """Get the evaluation interval."""
        return self._eval_interval

    @eval_interval.setter
    def eval_interval(self, value: int) -> None:
        """Set the evaluation interval."""
        self._eval_interval = max(1, value)

    @property
    def cached_penalty(self) -> float:
        """Get the currently cached penalty value."""
        if self._cache is None:
            return self._base_penalty
        return self._cache.penalty

    @property
    def cached_result(self) -> DRCResult | None:
        """Get the cached DRC result (if cache_results=True)."""
        if self._cache is None:
            return None
        return self._cache.result

    def is_available(self) -> bool:
        """Check if DRC validation is available."""
        return self._validator.is_available() and self._pcb_exporter is not None

    def should_evaluate(self, epoch: int) -> bool:
        """Check if DRC should be evaluated at this epoch."""
        if not self.is_available():
            return False

        # First epoch always evaluates
        if self._cache is None:
            return True

        # Check interval
        return (epoch - self._last_eval_epoch) >= self._eval_interval

    def evaluate(
        self,
        positions: Array,
        rotations: Array,
        context: LossContext,
        epoch: int = 0,
    ) -> DRCCacheEntry:
        """
        Force DRC evaluation regardless of interval.

        This is useful for final validation or manual checks.

        Args:
            positions: (N, 2) component positions.
            rotations: (N, 4) soft one-hot rotations.
            context: LossContext with netlist and board.
            epoch: Current epoch for history tracking.

        Returns:
            DRCCacheEntry with penalty and optional result.
        """
        if not self.is_available() or self._pcb_exporter is None:
            return DRCCacheEntry(
                penalty=self._base_penalty,
                epoch=epoch,
                result=None,
                elapsed_ms=0.0,
            )

        start_time = time.time()

        try:
            # Export current placement to temp PCB
            pcb_path = self._pcb_exporter(positions, rotations, context)

            # Run DRC
            result = self._validator.run_drc(pcb_path)

            # Compute penalty
            if result.success:
                penalty = self._validator.compute_penalty(result)
            else:
                penalty = self._fail_penalty

            elapsed_ms = (time.time() - start_time) * 1000

            # Create cache entry
            entry = DRCCacheEntry(
                penalty=penalty,
                epoch=epoch,
                result=result if self._cache_results else None,
                elapsed_ms=elapsed_ms,
            )

            # Update history
            self._history.add(
                epoch=epoch,
                penalty=penalty,
                errors=result.error_count if result.success else 0,
                warnings=result.warning_count if result.success else 0,
                elapsed_ms=elapsed_ms,
            )

            # Update cache
            self._cache = entry
            self._last_eval_epoch = epoch

            # Clean up temp file if needed
            if pcb_path.exists() and pcb_path.parent == Path(tempfile.gettempdir()):
                with contextlib.suppress(Exception):
                    pcb_path.unlink()

            return entry

        except Exception:
            elapsed_ms = (time.time() - start_time) * 1000
            return DRCCacheEntry(
                penalty=self._fail_penalty,
                epoch=epoch,
                result=None,
                elapsed_ms=elapsed_ms,
            )

    def __call__(
        self,
        positions: Array,  # noqa: ARG002
        rotations: Array,  # noqa: ARG002
        context: LossContext,  # noqa: ARG002
        epoch: int = 0,  # noqa: ARG002
        total_epochs: int = 1,  # noqa: ARG002
        net_virtual_nodes: Array | None = None,  # noqa: ARG002
        **_kwargs: Any,
    ) -> LossResult:
        """
        Compute DRC loss (returns cached value between evaluations).

        Note: This method doesn't know the current epoch. For epoch-aware
        evaluation, use evaluate() directly and call set_cached_penalty().

        Args:
            positions: (N, 2) component positions.
            rotations: (N, 4) soft one-hot rotations.
            context: LossContext.

        Returns:
            LossResult with cached penalty value.
        """
        penalty = self.cached_penalty

        breakdown: dict[str, Array] = {
            "drc_penalty": jnp.array(penalty),
            "drc_cached_epoch": jnp.array(self._last_eval_epoch, dtype=jnp.float32),
        }

        if self._cache is not None and self._cache.result is not None:
            breakdown["drc_errors"] = jnp.array(self._cache.result.error_count, dtype=jnp.float32)
            breakdown["drc_warnings"] = jnp.array(
                self._cache.result.warning_count, dtype=jnp.float32
            )

        return LossResult(
            value=jnp.array(penalty),
            breakdown=breakdown,
        )

    def compute_with_epoch(
        self,
        positions: Array,
        rotations: Array,
        context: LossContext,
        epoch: int,
    ) -> LossResult:
        """
        Compute DRC loss with epoch-aware caching.

        This is the recommended method for use in training loops.

        Args:
            positions: (N, 2) component positions.
            rotations: (N, 4) soft one-hot rotations.
            context: LossContext.
            epoch: Current training epoch.

        Returns:
            LossResult with penalty value (fresh or cached).
        """
        if self.should_evaluate(epoch):
            entry = self.evaluate(positions, rotations, context, epoch)
            self._cache = entry
            self._last_eval_epoch = epoch

        return self(positions, rotations, context)

    def set_cached_penalty(self, penalty: float, epoch: int) -> None:
        """
        Manually set the cached penalty.

        Useful when DRC is run externally (e.g., in a callback).

        Args:
            penalty: Penalty value to cache.
            epoch: Epoch to associate with this penalty.
        """
        self._cache = DRCCacheEntry(penalty=penalty, epoch=epoch)
        self._last_eval_epoch = epoch

    def reset_cache(self) -> None:
        """Clear the cached penalty and history."""
        self._cache = None
        self._last_eval_epoch = -1
        self._history = DRCHistory()

    def get_violations(self) -> list[DRCViolation]:
        """
        Get violations from the last DRC run.

        Returns:
            List of DRCViolation objects (empty if no cached result).
        """
        if self._cache is None or self._cache.result is None:
            return []
        return self._cache.result.violations

    def to_dict(self) -> dict[str, Any]:
        """
        Get DRC loss state as a dictionary.

        Useful for logging and checkpointing.
        """
        return {
            "name": self.name,
            "eval_interval": self._eval_interval,
            "is_available": self.is_available(),
            "cached_penalty": self.cached_penalty,
            "last_eval_epoch": self._last_eval_epoch,
            "history": {
                "total_evaluations": self._history.total_evaluations,
                "total_time_ms": self._history.total_time_ms,
                "best_penalty": self._history.best_penalty() if self._history.entries else None,
                "latest_penalty": self._history.latest_penalty() if self._history.entries else None,
            },
        }


def create_drc_loss(
    _pcb_template_path: Path | None = None,
    eval_interval: int = 50,
    severity_weights: dict[str, float] | None = None,
    violation_weights: dict[str, float] | None = None,
) -> DRCLoss:
    """
    Factory function to create a DRCLoss with common settings.

    Args:
        _pcb_template_path: Path to template PCB for export.
        eval_interval: Epochs between DRC evaluations.
        severity_weights: Custom severity weights for penalty.
        violation_weights: Custom violation type weights.

    Returns:
        Configured DRCLoss instance.
    """
    validator = KiCadDRCValidator(
        severity_weights=severity_weights,
        violation_weights=violation_weights,
    )

    # Note: pcb_exporter must be provided separately since it depends on
    # the specific PCB export implementation

    return DRCLoss(
        validator=validator,
        pcb_exporter=None,  # Must be set by user
        eval_interval=eval_interval,
    )


# Export for convenience
__all__ = [
    "DRCLoss",
    "DRCCacheEntry",
    "DRCHistory",
    "create_drc_loss",
]
