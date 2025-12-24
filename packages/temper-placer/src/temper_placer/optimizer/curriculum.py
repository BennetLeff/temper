"""
Curriculum learning for multi-phase placement optimization.

This module provides functions for defining and managing curriculum schedules
that progressively introduce constraints during training. The curriculum helps
the optimizer avoid local minima by:

1. Starting with spread/exploration (find rough positions)
2. Adding feasibility constraints (no overlap, in bounds)
3. Adding design rules (clearance, thermal)
4. Adding performance objectives (wirelength, loop area)
5. Fine-tuning with all constraints

Each phase has different loss weights that transition smoothly.
"""

from dataclasses import dataclass

from temper_placer.optimizer.config import CurriculumPhase, get_default_loss_weights


def create_default_phases(total_epochs: int = 8000) -> list[CurriculumPhase]:
    """
    Create the default 5-phase curriculum for Temper PCB placement.

    The phases are designed for the Temper induction cooker with emphasis on:
    - HV-LV isolation (10mm clearance, safety critical)
    - IGBT thermal placement (near heatsink edge)
    - Gate drive loop minimization (EMI)

    Args:
        total_epochs: Total training epochs (phases scale proportionally).

    Returns:
        List of CurriculumPhase instances.
    """
    # Scale phase boundaries to total epochs
    scale = total_epochs / 8000.0

    return [
        # Phase 1: Spread and exploration (0-12.5%)
        CurriculumPhase(
            name="spread",
            start_epoch=0,
            end_epoch=int(1000 * scale),
            loss_weights={
                "spread": 10.0,
                "rotation_entropy": 5.0,
                "boundary": 1.0,  # Soft boundary to allow exploration
            },
            temperature_override=5.0,  # High temperature for exploration
        ),
        # Phase 2: Feasibility (12.5-37.5%)
        CurriculumPhase(
            name="feasibility",
            start_epoch=int(1000 * scale),
            end_epoch=int(3000 * scale),
            loss_weights={
                "spread": 5.0,
                "overlap": 1000.0,  # CRITICAL: Must never overlap
                "boundary": 500.0,  # Strong boundary enforcement
                "rotation_entropy": 1.0,  # Reduce entropy
            },
        ),
        # Phase 3: Design rules (37.5-62.5%)
        CurriculumPhase(
            name="design_rules",
            start_epoch=int(3000 * scale),
            end_epoch=int(5000 * scale),
            loss_weights={
                "overlap": 1000.0,  # CRITICAL: Must never overlap
                "boundary": 500.0,  # Strong boundary enforcement
                "clearance": 80.0,  # HV-LV clearance (safety critical)
                "thermal": 30.0,  # IGBT near edge
                "zone": 50.0,  # Components in zones (lower than overlap)
            },
        ),
        # Phase 4: Performance (62.5-87.5%)
        CurriculumPhase(
            name="performance",
            start_epoch=int(5000 * scale),
            end_epoch=int(7000 * scale),
            loss_weights={
                "overlap": 1000.0,  # CRITICAL: Must never overlap
                "boundary": 500.0,  # Strong boundary enforcement
                "clearance": 80.0,
                "thermal": 30.0,
                "zone": 50.0,  # Components in zones (lower than overlap)
                "wirelength": 10.0,  # Minimize total wirelength
                "loop_area": 40.0,  # Minimize gate drive loops
                "congestion": 5.0,  # Balance routing
            },
        ),
        # Phase 5: Refinement (87.5-100%)
        CurriculumPhase(
            name="refinement",
            start_epoch=int(7000 * scale),
            end_epoch=int(8000 * scale),
            loss_weights={
                "overlap": 1000.0,  # CRITICAL: Must never overlap
                "boundary": 500.0,  # Strong boundary enforcement
                "clearance": 80.0,
                "thermal": 30.0,
                "zone": 50.0,  # Components in zones (lower than overlap)
                "wirelength": 10.0,
                "loop_area": 40.0,
                "congestion": 5.0,
                "ground_crossing": 20.0,  # Avoid crossing ground splits
            },
            temperature_override=0.1,  # Low temperature for exploitation
        ),
    ]


def create_fast_phases(total_epochs: int = 100) -> list[CurriculumPhase]:
    """
    Create a fast 3-phase curriculum for testing.

    This is a simplified curriculum for unit tests and quick experiments.

    Args:
        total_epochs: Total epochs (typically 100 for tests).

    Returns:
        List of CurriculumPhase instances.
    """
    return [
        CurriculumPhase(
            name="spread",
            start_epoch=0,
            end_epoch=int(total_epochs * 0.3),
            loss_weights={
                "spread": 10.0,
                "boundary": 1.0,
            },
            temperature_override=3.0,
        ),
        CurriculumPhase(
            name="feasibility",
            start_epoch=int(total_epochs * 0.3),
            end_epoch=int(total_epochs * 0.7),
            loss_weights={
                "overlap": 100.0,
                "boundary": 50.0,
            },
        ),
        CurriculumPhase(
            name="refinement",
            start_epoch=int(total_epochs * 0.7),
            end_epoch=total_epochs,
            loss_weights={
                "overlap": 100.0,
                "boundary": 50.0,
                "wirelength": 10.0,
            },
            temperature_override=0.5,
        ),
    ]


def get_active_phase(
    epoch: int,
    phases: list[CurriculumPhase],
) -> CurriculumPhase | None:
    """
    Get the currently active phase for a given epoch.

    Args:
        epoch: Current training epoch.
        phases: List of curriculum phases.

    Returns:
        Active CurriculumPhase or None if no phase is active.
    """
    for phase in phases:
        if phase.start_epoch <= epoch < phase.end_epoch:
            return phase
    return None


def get_phase_progress(
    epoch: int,
    phase: CurriculumPhase,
) -> float:
    """
    Get progress through a phase as a fraction [0, 1].

    Args:
        epoch: Current epoch.
        phase: Current phase.

    Returns:
        Progress fraction (0 = start, 1 = end).
    """
    total = phase.end_epoch - phase.start_epoch
    if total <= 0:
        return 1.0
    progress = (epoch - phase.start_epoch) / total
    return max(0.0, min(1.0, progress))


def interpolate_weights(
    weights_a: dict[str, float],
    weights_b: dict[str, float],
    t: float,
) -> dict[str, float]:
    """
    Interpolate between two weight dictionaries.

    Args:
        weights_a: Starting weights.
        weights_b: Ending weights.
        t: Interpolation parameter [0, 1].

    Returns:
        Interpolated weights.
    """
    all_keys = set(weights_a.keys()) | set(weights_b.keys())
    result = {}
    for key in all_keys:
        a = weights_a.get(key, 0.0)
        b = weights_b.get(key, 0.0)
        result[key] = a + t * (b - a)
    return result


def smooth_transition_weights(
    epoch: int,
    phases: list[CurriculumPhase],
    transition_epochs: int = 100,
) -> dict[str, float]:
    """
    Get weights with smooth transitions between phases.

    This function blends weights during phase transitions to avoid
    sudden jumps that could destabilize training.

    Args:
        epoch: Current epoch.
        phases: List of curriculum phases.
        transition_epochs: Number of epochs for transitions.

    Returns:
        Dict of loss weights for the current epoch.
    """
    # Find current and next phase
    current_phase = None
    next_phase = None

    for i, phase in enumerate(phases):
        if phase.start_epoch <= epoch < phase.end_epoch:
            current_phase = phase
            if i + 1 < len(phases):
                next_phase = phases[i + 1]
            break

    if current_phase is None:
        # Before first phase or after last phase
        if phases and epoch < phases[0].start_epoch:
            return phases[0].loss_weights
        elif phases and epoch >= phases[-1].end_epoch:
            return phases[-1].loss_weights
        return get_default_loss_weights()

    # Check if we're in a transition zone
    epochs_to_end = current_phase.end_epoch - epoch

    if next_phase is not None and epochs_to_end <= transition_epochs:
        # Smoothly transition to next phase
        t = 1.0 - (epochs_to_end / transition_epochs)
        # Use smooth step for gradual transition
        t = t * t * (3.0 - 2.0 * t)
        return interpolate_weights(
            current_phase.loss_weights,
            next_phase.loss_weights,
            t,
        )

    return current_phase.loss_weights


@dataclass
class CurriculumState:
    """
    Tracks curriculum progress during training.

    This class provides a convenient interface for curriculum management,
    including phase detection, weight calculation, and logging.

    Attributes:
        phases: List of curriculum phases.
        transition_epochs: Number of epochs for smooth transitions.
        current_phase_name: Name of current phase (for logging).
        current_phase_idx: Index of current phase.
    """

    phases: list[CurriculumPhase]
    transition_epochs: int = 100
    current_phase_name: str | None = None
    current_phase_idx: int = -1

    def get_weights(self, epoch: int) -> dict[str, float]:
        """
        Get loss weights for the current epoch.

        Args:
            epoch: Current training epoch.

        Returns:
            Dict mapping loss name to weight.
        """
        return smooth_transition_weights(epoch, self.phases, self.transition_epochs)

    def get_temperature(self, epoch: int, default_temp: float) -> float:
        """
        Get temperature for current epoch, respecting phase overrides.

        Args:
            epoch: Current epoch.
            default_temp: Default temperature from schedule.

        Returns:
            Temperature to use for Gumbel-Softmax.
        """
        phase = get_active_phase(epoch, self.phases)
        if phase is not None and phase.temperature_override is not None:
            return phase.temperature_override
        return default_temp

    def get_learning_rate(self, epoch: int, default_lr: float) -> float:
        """
        Get learning rate for current epoch, respecting phase overrides.

        Args:
            epoch: Current epoch.
            default_lr: Default learning rate from schedule.

        Returns:
            Learning rate to use.
        """
        phase = get_active_phase(epoch, self.phases)
        if phase is not None and phase.learning_rate_override is not None:
            return phase.learning_rate_override
        return default_lr

    def update(self, epoch: int) -> bool:
        """
        Update curriculum state and check for phase change.

        Args:
            epoch: Current epoch.

        Returns:
            True if phase changed, False otherwise.
        """
        phase = get_active_phase(epoch, self.phases)
        if phase is None:
            new_name = None
            new_idx = -1
        else:
            new_name = phase.name
            new_idx = self.phases.index(phase)

        changed = new_name != self.current_phase_name
        self.current_phase_name = new_name
        self.current_phase_idx = new_idx
        return changed

    def get_progress_string(self, epoch: int) -> str:
        """
        Get a human-readable progress string.

        Args:
            epoch: Current epoch.

        Returns:
            Progress string like "Phase: feasibility (45%)"
        """
        phase = get_active_phase(epoch, self.phases)
        if phase is None:
            return "Phase: none"
        progress = get_phase_progress(epoch, phase)
        return f"Phase: {phase.name} ({progress * 100:.0f}%)"
