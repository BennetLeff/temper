"""Manufacturing margin loss function for optimizer integration.

This loss penalizes tight manufacturing margins, encouraging the optimizer
to maximize safety margins beyond minimum DRC requirements. Instead of
hard pass/fail DRC checks, this provides smooth gradients that guide
components toward placements with comfortable manufacturing tolerances.

The loss function:
- Is zero when margins are comfortable (> target threshold)
- Increases smoothly as margins decrease
- Penalizes heavily when margins approach zero or go negative

This integrates with the Level 2 tolerance model from
temper_placer.manufacturing.tolerances to use per-feature tolerances.

Related issues: temper-6vj.6
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import jax
import jax.numpy as jnp
from jax import Array

from temper_placer.geometry.transform import batch_get_rotated_bounds
from temper_placer.losses.base import LossContext, LossFunction, LossResult

if TYPE_CHECKING:
    from temper_placer.manufacturing.tolerances import ToleranceTable


@dataclass(frozen=True)
class ManufacturingMarginConfig:
    """Configuration for manufacturing margin loss.

    Attributes:
        target_margin_mm: Target margin (comfortable zone). Loss is near zero
            when actual margins exceed this value.
        min_margin_mm: Minimum acceptable margin. Loss increases rapidly
            below this threshold.
        weight: Base weight multiplier for the loss.
        violation_penalty_scale: Extra penalty scale for violations (negative margins).
        use_tolerances: If True, adjust required clearances based on tolerance model.
        etch_tolerance_mm: Etch tolerance to add to clearance requirements.
            Only used if use_tolerances is True.
    """

    target_margin_mm: float = 0.1
    min_margin_mm: float = 0.05
    weight: float = 10.0
    violation_penalty_scale: float = 100.0
    use_tolerances: bool = True
    etch_tolerance_mm: float = 0.05
    fiducial_regex: str = "^FID"
    fiducial_margin_mm: float = 1.0


def compute_margin_loss(
    actual_values: Array,
    required_values: Array,
    target_margin: float,
    violation_penalty_scale: float = 100.0,
) -> Array:
    """Compute loss that penalizes tight manufacturing margins.

    Uses softplus for smooth transition that:
    - Is near zero when margin > target
    - Increases linearly when margin approaches zero
    - Adds quadratic penalty for violations (negative margins)

    Args:
        actual_values: (N,) array of actual measurements (e.g., clearances).
        required_values: (N,) array of minimum required values.
        target_margin: Target margin above required values.
        violation_penalty_scale: Scale factor for violation (negative margin) penalty.

    Returns:
        Scalar loss value.
    """
    # Compute margins (positive = passing with margin)
    margins = actual_values - required_values  # (N,)

    # Normalize by target margin for consistent scaling
    normalized_margins = margins / jnp.maximum(target_margin, 1e-6)

    # Softplus penalty: log(1 + exp(-x * scale))
    # - Near zero when x >> 0 (comfortable margin)
    # - Linear in -x when x << 0 (tight or violated)
    # Scale factor of 5.0 gives good transition sharpness
    penalty = jnp.sum(jax.nn.softplus(-normalized_margins * 5.0))

    # Extra quadratic penalty for violations (negative margins)
    violations = jnp.maximum(0.0, -margins)
    violation_penalty = jnp.sum(violations**2) * violation_penalty_scale

    return penalty + violation_penalty


def compute_pairwise_clearances(
    positions: Array,
    widths: Array,
    heights: Array,
) -> tuple[Array, Array, Array]:
    """Compute pairwise edge-to-edge clearances between all components.

    Uses axis-aligned bounding box distances (same as ClearanceLoss).

    Args:
        positions: (N, 2) component center positions.
        widths: (N,) component widths.
        heights: (N,) component heights.

    Returns:
        Tuple of:
        - clearances: (N*(N-1)/2,) array of unique pairwise clearances
        - idx_i: (N*(N-1)/2,) first component index for each pair
        - idx_j: (N*(N-1)/2,) second component index for each pair
    """
    n = positions.shape[0]

    # Half dimensions
    half_w = widths / 2.0  # (N,)
    half_h = heights / 2.0  # (N,)

    # Pairwise position differences
    diff = positions[:, None, :] - positions[None, :, :]  # (N, N, 2)
    abs_dx = jnp.abs(diff[:, :, 0])  # (N, N)
    abs_dy = jnp.abs(diff[:, :, 1])  # (N, N)

    # Combined half-dimensions
    combined_half_w = half_w[:, None] + half_w[None, :]  # (N, N)
    combined_half_h = half_h[:, None] + half_h[None, :]  # (N, N)

    # Edge separations
    sep_x = abs_dx - combined_half_w  # (N, N)
    sep_y = abs_dy - combined_half_h  # (N, N)

    # Box-to-box distance
    both_positive = (sep_x > 0) & (sep_y > 0)
    corner_dist = jnp.sqrt(jnp.maximum(sep_x, 0.0) ** 2 + jnp.maximum(sep_y, 0.0) ** 2 + 1e-8)

    only_x_positive = (sep_x > 0) & (sep_y <= 0)
    only_y_positive = (sep_x <= 0) & (sep_y > 0)

    edge_dist = jnp.where(
        both_positive,
        corner_dist,
        jnp.where(
            only_x_positive,
            sep_x,
            jnp.where(only_y_positive, sep_y, jnp.maximum(sep_x, sep_y)),
        ),
    )  # (N, N)

    # Extract upper triangle (unique pairs, excluding self-pairs)
    triu_indices = jnp.triu_indices(n, k=1)
    clearances = edge_dist[triu_indices]
    idx_i = triu_indices[0]
    idx_j = triu_indices[1]

    return clearances, idx_i, idx_j


class ManufacturingMarginLoss(LossFunction):
    """Loss function that penalizes tight manufacturing margins.

    This loss encourages the optimizer to maximize margins beyond minimum
    DRC requirements, making designs more robust to manufacturing variability.

    The loss computes pairwise clearances between all components and penalizes
    any that fall below the target margin threshold. It can optionally use
    the Level 2 tolerance model to adjust requirements based on copper weight
    and layer type.

    Example:
        >>> config = ManufacturingMarginConfig(target_margin_mm=0.15, weight=10.0)
        >>> loss_fn = ManufacturingMarginLoss(config)
        >>> result = loss_fn(positions, rotations, context)
        >>> print(f"Manufacturing margin loss: {result.value}")

    Attributes:
        config: Configuration for margin thresholds and penalties.
        min_clearance_mm: Minimum clearance requirement to check against.
    """

    def __init__(
        self,
        config: ManufacturingMarginConfig | None = None,
        min_clearance_mm: float = 0.2,
    ):
        """Initialize ManufacturingMarginLoss.

        Args:
            config: Configuration for margin thresholds. Uses defaults if None.
            min_clearance_mm: Minimum clearance requirement (mm). Components
                should maintain this clearance plus the target margin.
        """
        self.config = config or ManufacturingMarginConfig()
        self.min_clearance_mm = min_clearance_mm

    @property
    def name(self) -> str:
        return "manufacturing_margin"

    def __call__(
        self,
        positions: Array,
        rotations: Array,
        context: LossContext,
        epoch: int = 0,
        total_epochs: int = 1,
        net_virtual_nodes: Array | None = None,
        **_kwargs: Any,
    ) -> LossResult:
        """Compute manufacturing margin loss.

        Args:
            positions: (N, 2) component center positions.
            rotations: (N, 4) soft one-hot rotation indicators.
            context: LossContext with netlist, board, and constraints.
            epoch: Current training epoch (for curriculum learning).
            total_epochs: Total training epochs.

        Returns:
            LossResult with scalar loss value and breakdown.
        """
        # Get rotation-aware bounds
        bounds = context.bounds  # (N, 2)
        widths, heights = batch_get_rotated_bounds(bounds[:, 0], bounds[:, 1], rotations)

        # Compute all pairwise clearances
        clearances, idx_i, idx_j = compute_pairwise_clearances(positions, widths, heights)

        # Determine required clearance for each pair
        # Default: use uniform minimum clearance
        base_required = jnp.full_like(clearances, self.min_clearance_mm)

        # Apply fiducial clearance if present
        if context.fiducial_indices is not None and context.fiducial_indices.shape[0] > 0:
            n_comp = positions.shape[0]

            # Create boolean mask for fiducials (N,)
            is_fiducial = jnp.zeros((n_comp,), dtype=jnp.bool_)
            is_fiducial = is_fiducial.at[context.fiducial_indices].set(True)

            # Get fiducial status for each pair (i, j)
            # idx_i and idx_j come from compute_pairwise_clearances
            # Only apply if ONE or BOTH are fiducials?
            # Usually we want clearance *around* fiducial from *other* components.
            # So if either is fiducial, use larger margin.
            is_fid_i = is_fiducial[idx_i]
            is_fid_j = is_fiducial[idx_j]
            is_fid_pair = is_fid_i | is_fid_j

            # Use fiducial margin where applicable
            base_required = jnp.where(
                is_fid_pair,
                self.config.fiducial_margin_mm,
                base_required
            )

        # Optionally add etch tolerance to requirements
        if self.config.use_tolerances:
            # Worst-case clearance shrinks by 2x etch (both sides expand)
            tolerance_margin = 2.0 * self.config.etch_tolerance_mm
            required = base_required + tolerance_margin
        else:
            required = base_required

        # Compute margin loss
        loss_value = compute_margin_loss(
            actual_values=clearances,
            required_values=required,
            target_margin=self.config.target_margin_mm,
            violation_penalty_scale=self.config.violation_penalty_scale,
        )

        # Apply weight
        weighted_loss = self.config.weight * loss_value

        # Compute statistics for breakdown
        margins = clearances - required
        min_margin = jnp.min(margins)
        mean_margin = jnp.mean(margins)
        n_violations = jnp.sum(margins < 0)
        n_tight = jnp.sum((margins >= 0) & (margins < self.config.target_margin_mm))

        breakdown = {
            "min_margin": min_margin,
            "mean_margin": mean_margin,
            "n_violations": n_violations,
            "n_tight_margins": n_tight,
            "n_pairs": jnp.array(clearances.shape[0], dtype=jnp.float32),
        }

        return LossResult(value=weighted_loss, breakdown=breakdown)

    def weight_schedule(self, epoch: int, total_epochs: int) -> float:
        """Manufacturing margin is introduced after initial placement.

        Starts at 50% weight, reaches full weight at 30% of training.
        This allows components to spread out first before optimizing margins.

        Args:
            epoch: Current epoch.
            total_epochs: Total epochs.

        Returns:
            Weight multiplier (0.5 to 1.0).
        """
        progress = epoch / jnp.maximum(total_epochs, 1)
        result = jnp.where(progress < 0.3, 0.5 + progress * (0.5 / 0.3), 1.0)
        return result  # Return JAX array, not Python float


def create_manufacturing_margin_loss(
    config: ManufacturingMarginConfig | None = None,
    min_clearance_mm: float = 0.2,
    tolerance_table: ToleranceTable | None = None,
) -> ManufacturingMarginLoss:
    """Factory function to create a ManufacturingMarginLoss.

    This is the recommended way to create the loss function, as it allows
    for future integration with the tolerance table.

    Args:
        config: Configuration for margin thresholds.
        min_clearance_mm: Minimum clearance requirement (mm).
        tolerance_table: Optional ToleranceTable for per-feature tolerances.
            Currently stored for future use but not actively used.

    Returns:
        Configured ManufacturingMarginLoss instance.

    Example:
        >>> from temper_placer.losses import create_manufacturing_margin_loss
        >>> loss = create_manufacturing_margin_loss(
        ...     config=ManufacturingMarginConfig(target_margin_mm=0.1),
        ...     min_clearance_mm=0.15,
        ... )
    """
    # Future: use tolerance_table to compute per-pair requirements
    # based on copper weight and layer type
    _ = tolerance_table  # Reserved for future use

    return ManufacturingMarginLoss(config=config, min_clearance_mm=min_clearance_mm)


def compute_manufacturability_score(
    positions: Array,
    widths: Array,
    heights: Array,
    min_clearance_mm: float = 0.2,
    target_margin_mm: float = 0.1,
) -> float:
    """Compute a manufacturability score for a placement.

    Score ranges from 0.0 (not manufacturable) to 1.0+ (excellent margins).
    A score of 1.0 means all clearances have at least the target margin.

    Args:
        positions: (N, 2) component positions.
        widths: (N,) component widths.
        heights: (N,) component heights.
        min_clearance_mm: Minimum required clearance.
        target_margin_mm: Target margin above minimum.

    Returns:
        Manufacturability score (0.0 to 1.0+).

    Example:
        >>> score = compute_manufacturability_score(positions, widths, heights)
        >>> if score < 0.8:
        ...     print("Warning: Tight manufacturing margins")
    """
    clearances, _, _ = compute_pairwise_clearances(positions, widths, heights)

    if clearances.shape[0] == 0:
        return 1.0  # No pairs to check

    # Compute margins relative to requirement
    margins = clearances - min_clearance_mm

    # Score = min margin / target margin
    # Score of 1.0 means minimum margin equals target
    # Score > 1.0 means all margins exceed target (excellent)
    # Score < 1.0 means at least one margin is below target
    # Score < 0 means at least one violation
    min_margin = float(jnp.min(margins))
    score = min_margin / target_margin_mm if target_margin_mm > 0 else 0.0

    return max(0.0, score)  # Clamp to non-negative
