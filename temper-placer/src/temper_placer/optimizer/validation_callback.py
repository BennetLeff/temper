"""
Validation callback for training loop integration.

This module provides:
- ValidationCallback: Periodic validation during training
- ValidationConfig: Configuration for validation behavior
- ValidationResult: Results from validation runs

DRC and other non-differentiable validation is handled via callbacks,
not as loss terms, because:
1. They don't provide gradient signals
2. They are computationally expensive (100ms-1s per run)
3. They should run at scheduled intervals, not every epoch
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from jax import Array

from temper_placer.losses.base import LossContext
from temper_placer.losses.drc_loss import DRCHistory, DRCLoss
from temper_placer.validation.drc import KiCadDRCValidator

logger = logging.getLogger(__name__)


@dataclass
class ValidationConfig:
    """
    Configuration for validation during training.

    Attributes:
        enabled: Whether to run validation.
        drc_enabled: Enable DRC validation (requires kicad-cli).
        drc_interval: Run DRC every N epochs.
        drc_template_pcb: Path to template PCB for DRC.
        drc_board_origin: Board origin offset (x, y) in mm.
        fail_on_drc_errors: Stop training if DRC has errors above threshold.
        max_drc_errors: Maximum allowed DRC errors before stopping.
        spice_enabled: Enable SPICE validation (requires ngspice).
        spice_interval: Run SPICE validation every N epochs.
        log_validation: Log validation results to console.
    """

    enabled: bool = True
    drc_enabled: bool = True
    drc_interval: int = 100
    drc_template_pcb: Optional[Path] = None
    drc_board_origin: Tuple[float, float] = (0.0, 0.0)
    fail_on_drc_errors: bool = False
    max_drc_errors: int = 0
    spice_enabled: bool = False
    spice_interval: int = 200
    log_validation: bool = True


@dataclass
class ValidationResult:
    """
    Result from a single validation run.

    Attributes:
        epoch: Epoch when validation was run.
        elapsed_ms: Time taken for validation.
        drc_penalty: DRC penalty value (if DRC was run).
        drc_errors: Number of DRC errors.
        drc_warnings: Number of DRC warnings.
        spice_results: SPICE validation results (if SPICE was run).
        passed: Whether validation passed all checks.
        messages: Any warning or error messages.
    """

    epoch: int
    elapsed_ms: float = 0.0
    drc_penalty: float = 0.0
    drc_errors: int = 0
    drc_warnings: int = 0
    spice_results: Dict[str, float] = field(default_factory=dict)
    passed: bool = True
    messages: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging/serialization."""
        return {
            "epoch": self.epoch,
            "elapsed_ms": self.elapsed_ms,
            "drc_penalty": self.drc_penalty,
            "drc_errors": self.drc_errors,
            "drc_warnings": self.drc_warnings,
            "spice_results": self.spice_results,
            "passed": self.passed,
            "messages": self.messages,
        }


class ValidationCallback:
    """
    Callback for periodic validation during training.

    This callback runs DRC and/or SPICE validation at configured intervals.
    It tracks validation history and can optionally stop training on failures.

    Example:
        >>> from temper_placer.io import create_pcb_exporter
        >>>
        >>> config = ValidationConfig(
        ...     drc_enabled=True,
        ...     drc_interval=50,
        ...     drc_template_pcb=Path("board.kicad_pcb"),
        ... )
        >>> callback = ValidationCallback(config)
        >>>
        >>> # In training loop:
        >>> result = callback(epoch, positions, rotations, context)
        >>> if result is not None:
        ...     print(f"DRC penalty: {result.drc_penalty}")

    Attributes:
        config: ValidationConfig instance.
        drc_loss: DRCLoss instance (created if DRC enabled).
        history: List of ValidationResult from each run.
    """

    def __init__(
        self,
        config: Optional[ValidationConfig] = None,
        drc_loss: Optional[DRCLoss] = None,
        on_result: Optional[Callable[[ValidationResult], None]] = None,
    ):
        """
        Initialize validation callback.

        Args:
            config: Validation configuration.
            drc_loss: Pre-configured DRCLoss (optional, created if None).
            on_result: Optional callback invoked after each validation.
        """
        self.config = config or ValidationConfig()
        self._drc_loss = drc_loss
        self._on_result = on_result
        self._history: List[ValidationResult] = []
        self._initialized = False

    def _lazy_init(self, context: LossContext) -> None:
        """Initialize DRC components on first use."""
        if self._initialized:
            return

        if self.config.drc_enabled and self._drc_loss is None:
            if self.config.drc_template_pcb is None:
                logger.warning("DRC enabled but no template PCB path provided")
                self.config.drc_enabled = False
            else:
                # Import here to avoid circular dependency
                from temper_placer.io.placement_exporter import create_pcb_exporter

                # Create PCB exporter
                exporter = create_pcb_exporter(
                    template_pcb=self.config.drc_template_pcb,
                    board_origin=self.config.drc_board_origin,
                )

                # Create DRCLoss with exporter
                self._drc_loss = DRCLoss(
                    validator=KiCadDRCValidator(),
                    pcb_exporter=exporter,
                    eval_interval=self.config.drc_interval,
                )

        self._initialized = True

    @property
    def drc_loss(self) -> Optional[DRCLoss]:
        """Get the DRCLoss instance (may be None if not configured)."""
        return self._drc_loss

    @property
    def drc_history(self) -> Optional[DRCHistory]:
        """Get DRC evaluation history."""
        if self._drc_loss is not None:
            return self._drc_loss.history
        return None

    @property
    def history(self) -> List[ValidationResult]:
        """Get all validation results."""
        return self._history

    def should_validate(self, epoch: int) -> bool:
        """Check if validation should run at this epoch."""
        if not self.config.enabled:
            return False

        # Check DRC interval
        if self.config.drc_enabled:
            if epoch == 0 or epoch % self.config.drc_interval == 0:
                return True

        # Check SPICE interval
        if self.config.spice_enabled:
            if epoch == 0 or epoch % self.config.spice_interval == 0:
                return True

        return False

    def __call__(
        self,
        epoch: int,
        positions: Array,
        rotations: Array,
        context: LossContext,
    ) -> Optional[ValidationResult]:
        """
        Run validation if scheduled for this epoch.

        Args:
            epoch: Current training epoch.
            positions: (N, 2) component positions.
            rotations: (N, 4) soft one-hot rotations.
            context: LossContext with netlist and board.

        Returns:
            ValidationResult if validation was run, None otherwise.
        """
        if not self.should_validate(epoch):
            return None

        self._lazy_init(context)

        start_time = time.time()
        messages: List[str] = []
        passed = True

        # Initialize result values
        drc_penalty = 0.0
        drc_errors = 0
        drc_warnings = 0
        spice_results: Dict[str, float] = {}

        # Run DRC validation
        if self.config.drc_enabled and self._drc_loss is not None:
            if self._drc_loss.is_available():
                try:
                    entry = self._drc_loss.evaluate(positions, rotations, context, epoch)
                    drc_penalty = entry.penalty

                    if entry.result is not None:
                        drc_errors = entry.result.error_count
                        drc_warnings = entry.result.warning_count

                    # Check failure threshold
                    if self.config.fail_on_drc_errors and drc_errors > self.config.max_drc_errors:
                        passed = False
                        messages.append(
                            f"DRC errors ({drc_errors}) exceed threshold ({self.config.max_drc_errors})"
                        )

                    if self.config.log_validation:
                        logger.info(
                            f"[Epoch {epoch}] DRC: penalty={drc_penalty:.2f}, "
                            f"errors={drc_errors}, warnings={drc_warnings}"
                        )

                except Exception as e:
                    messages.append(f"DRC validation failed: {e}")
                    if self.config.log_validation:
                        logger.warning(f"[Epoch {epoch}] DRC failed: {e}")
            else:
                if self.config.log_validation:
                    logger.debug(f"[Epoch {epoch}] DRC not available (kicad-cli not found)")

        # Run SPICE validation (placeholder for future implementation)
        if self.config.spice_enabled:
            # TODO: Implement SPICE validation integration
            pass

        elapsed_ms = (time.time() - start_time) * 1000

        result = ValidationResult(
            epoch=epoch,
            elapsed_ms=elapsed_ms,
            drc_penalty=drc_penalty,
            drc_errors=drc_errors,
            drc_warnings=drc_warnings,
            spice_results=spice_results,
            passed=passed,
            messages=messages,
        )

        self._history.append(result)

        if self._on_result is not None:
            self._on_result(result)

        return result

    def reset(self) -> None:
        """Reset validation history and DRC cache."""
        self._history = []
        if self._drc_loss is not None:
            self._drc_loss.reset_cache()

    def summary(self) -> str:
        """Get a summary of validation history."""
        if not self._history:
            return "No validations run yet"

        lines = [f"Validation Summary ({len(self._history)} runs)"]

        # DRC summary
        if self.config.drc_enabled:
            drc_penalties = [r.drc_penalty for r in self._history if r.drc_penalty > 0]
            if drc_penalties:
                lines.append(
                    f"  DRC penalty: min={min(drc_penalties):.2f}, "
                    f"max={max(drc_penalties):.2f}, "
                    f"last={drc_penalties[-1]:.2f}"
                )

            total_errors = sum(r.drc_errors for r in self._history)
            if total_errors > 0:
                lines.append(f"  Total DRC errors: {total_errors}")

        # Pass/fail
        failed = [r for r in self._history if not r.passed]
        if failed:
            lines.append(f"  Failed validations: {len(failed)}/{len(self._history)}")
        else:
            lines.append("  All validations passed")

        return "\n".join(lines)


def create_validation_callback(
    template_pcb: Optional[Path] = None,
    board_origin: Tuple[float, float] = (0.0, 0.0),
    drc_interval: int = 100,
    on_result: Optional[Callable[[ValidationResult], None]] = None,
) -> ValidationCallback:
    """
    Factory function to create a ValidationCallback for DRC.

    This is a convenience function for the common case of DRC-only validation.

    Args:
        template_pcb: Path to template PCB file.
        board_origin: Board origin offset.
        drc_interval: Run DRC every N epochs.
        on_result: Optional callback for each validation result.

    Returns:
        Configured ValidationCallback.
    """
    config = ValidationConfig(
        enabled=True,
        drc_enabled=template_pcb is not None,
        drc_interval=drc_interval,
        drc_template_pcb=template_pcb,
        drc_board_origin=board_origin,
        spice_enabled=False,
    )

    return ValidationCallback(config=config, on_result=on_result)


__all__ = [
    "ValidationConfig",
    "ValidationResult",
    "ValidationCallback",
    "create_validation_callback",
]
