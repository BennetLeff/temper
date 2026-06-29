"""
Aesthetic loss functions for professional PCB layouts.

This module implements losses that improve the visual quality and
manufacturability of the placement by:
- Encouraging row/column alignment of similar components
- Promoting consistent component orientations
- Snapping components to a global manufacturing grid
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
    from temper_placer.core.netlist import Netlist
    from temper_placer.io.config_loader import PlacementConstraints
    from temper_placer.losses.base import WeightedLoss
    from temper_placer.losses.grid import GridAlignmentLoss


from temper_placer.losses.grid import GridAlignmentLoss


@dataclass
class WhitespaceLoss(LossFunction):
    """
    Penalize uneven distribution of empty space.

    Calculates component density on a grid using differentiable overlap.
    Minimizes the variance of the free space ratio per cell.

    Attributes:
        grid_shape: (rows, cols) grid resolution.
        target_density: Optional target density. If None, aims for uniform.
    """

    grid_shape: tuple[int, int] = (10, 10)
    target_density: float | None = None

    def __call__(
        self,
        positions: Array,
        rotations: Array,
        context: LossContext,
        epoch: int = 0,
        total_epochs: int = 1,
        net_virtual_nodes: Array | None = None,
        **kwargs: Any,
    ) -> LossResult:
        # Get component bounds
        bounds = context.netlist.get_bounds_array()
        widths, heights = batch_get_rotated_bounds(bounds[:, 0], bounds[:, 1], rotations)

        # Grid setup
        board_bounds = context.board.get_relative_bounds_array()
        x_min, y_min, x_max, y_max = board_bounds
        rows, cols = self.grid_shape

        # Calculate cell bounds
        cell_w = (x_max - x_min) / cols
        cell_h = (y_max - y_min) / rows
        cell_area = cell_w * cell_h

        # Grid centers
        grid_x = jnp.linspace(x_min + cell_w / 2, x_max - cell_w / 2, cols)
        grid_y = jnp.linspace(y_min + cell_h / 2, y_max - cell_h / 2, rows)

        # Differentiable overlap calculation
        # Component boxes: [pos_x - w/2, pos_y - h/2, pos_x + w/2, pos_y + h/2]
        c_min_x = positions[:, 0] - widths / 2
        c_max_x = positions[:, 0] + widths / 2
        c_min_y = positions[:, 1] - heights / 2
        c_max_y = positions[:, 1] + heights / 2

        # Cell boxes
        g_min_x = grid_x - cell_w / 2
        g_max_x = grid_x + cell_w / 2
        g_min_y = grid_y - cell_h / 2
        g_max_y = grid_y + cell_h / 2

        # Compute overlap for each (comp, cell_x) and (comp, cell_y)
        # Smooth max/min for gradients:
        # overlap_1d = soft_relu(min(c_max, g_max) - max(c_min, g_min))
        # Using simpler approximation: Gaussian or Sigmoid?
        # Let's use soft_relu of the linear overlap for simplicity and robustness.

        def soft_relu(x):
            return jnp.logaddexp(0.0, x * 10.0) / 10.0  # sharpen factor 10

        # Broadcast: (N, 1) vs (1, Cols)
        overlap_x_raw = jnp.minimum(c_max_x[:, None], g_max_x[None, :]) - jnp.maximum(
            c_min_x[:, None], g_min_x[None, :]
        )
        overlap_x = soft_relu(overlap_x_raw)  # (N, Cols)

        # Broadcast: (N, 1) vs (1, Rows)
        overlap_y_raw = jnp.minimum(c_max_y[:, None], g_max_y[None, :]) - jnp.maximum(
            c_min_y[:, None], g_min_y[None, :]
        )
        overlap_y = soft_relu(overlap_y_raw)  # (N, Rows)

        # Outer product to get (N, Rows, Cols)
        # Area = overlap_x * overlap_y
        area_grid = overlap_y[:, :, None] * overlap_x[:, None, :]  # (N, Rows, Cols)

        # Sum occupied area per cell
        occupied_area = jnp.sum(area_grid, axis=0)  # (Rows, Cols)

        # Density (fraction occupied)
        density = occupied_area / cell_area

        # Coefficient of Variation of density (std / mean)
        mean_den = jnp.mean(density) + 1e-6
        std_den = jnp.std(density)
        cv = std_den / mean_den

        return LossResult(value=cv)


@dataclass
class AlignmentLoss(LossFunction):
    """
    Encourages row/column alignment for similar components (e.g., all resistors).

    Attributes:
        prefix_groups: (G, M) array of component indices sharing the same prefix,
            padded with -1. G is number of groups, M is max group size.
    """

    prefix_groups: Array  # (G, M) array of indices, padded with -1

    def __call__(
        self,
        positions: Array,
        rotations: Array,
        context: LossContext,
        epoch: int = 0,
        total_epochs: int = 1,
        net_virtual_nodes: Array | None = None,
        **kwargs: Any,
    ) -> LossResult:
        """
        Compute alignment penalty for each prefix group.

        For each group, we penalize the variance in either X or Y (whichever is smaller),
        encouraging components to form either a horizontal row or a vertical column.
        """

        def compute_group_loss(group_indices):
            # Mask for valid indices (not -1)
            mask = group_indices != -1
            group_pos = positions[group_indices]  # (M, 2)

            # Count valid components in this group
            n_valid = jnp.sum(mask)

            # Compute mean position of valid components
            # Use jnp.where to handle empty groups safely
            sum_pos = jnp.sum(group_pos * mask[:, None], axis=0)
            mean_pos = sum_pos / jnp.maximum(n_valid, 1.0)

            # Compute variance in x and y
            diff_sq = (group_pos - mean_pos) ** 2 * mask[:, None]
            var = jnp.sum(diff_sq, axis=0) / jnp.maximum(n_valid, 1.0)  # (2,)

            # Penalty is min of x-variance and y-variance
            # (encourages alignment to either axis)
            # Only apply if group has at least 2 components
            penalty = jnp.minimum(var[0], var[1])
            return jnp.where(n_valid < 2, 0.0, penalty)

        # Vectorize over all prefix groups
        if self.prefix_groups.shape[0] == 0:
            return LossResult(value=jnp.array(0.0))

        group_losses = jax.vmap(compute_group_loss)(self.prefix_groups)
        total = jnp.sum(group_losses)

        return LossResult(
            value=total,
            breakdown={
                "per_group": group_losses,
            },
        )


@dataclass
class RotationConsistencyLoss(LossFunction):
    """
    Encourages a consistent orientation for components across the board.

    Professional layouts often avoid having a "jumble" of orientations.
    This loss penalizes the entropy of the global orientation distribution,
    pushing the design toward a single dominant orientation (or two).
    """

    def __call__(
        self,
        positions: Array,
        rotations: Array,
        context: LossContext,
        epoch: int = 0,
        total_epochs: int = 1,
        net_virtual_nodes: Array | None = None,
        **kwargs: Any,
    ) -> LossResult:
        """
        Compute entropy of the rotation distribution, optionally grouped by type.
        """
        # (N, 4) soft one-hot

        total_entropy = jnp.array(0.0)

        # 1. Global consistency (default fallback or weighted component)
        global_dist = jnp.mean(rotations, axis=0)  # (4,)
        probs = global_dist / (jnp.sum(global_dist) + 1e-8)
        global_entropy = -jnp.sum(probs * jnp.log(probs + 1e-8))

        # 2. Per-type consistency (if available)
        if context.component_type_indices:
            type_entropy_sum = jnp.array(0.0)
            count = 0.0

            for _type_name, indices in context.component_type_indices.items():
                if len(indices) < 2:
                    continue

                # Extract rotations for this group
                type_rots = rotations[indices] # (K, 4)
                type_dist = jnp.mean(type_rots, axis=0)
                type_probs = type_dist / (jnp.sum(type_dist) + 1e-8)
                type_entropy = -jnp.sum(type_probs * jnp.log(type_probs + 1e-8))

                type_entropy_sum += type_entropy
                count += 1.0

            # If we have types, mix type entropy with global entropy
            # Weight type entropy more heavily as it is more specific
            total_entropy = type_entropy_sum / count if count > 0 else global_entropy
        else:
            total_entropy = global_entropy

        return LossResult(value=total_entropy)


@dataclass
class MirrorSymmetryLoss(LossFunction):
    """
    Enforces mirror symmetry between pairs of components.

    For each pair (a, b), requires that 'b' is the reflection of 'a'
    across a specified axis and center line.

    Attributes:
        pairs: (P, 2) array of component indices (a, b).
        axis: 0 for X-axis (vertical reflection), 1 for Y-axis (horizontal reflection).
        center: The coordinate of the reflection line.
    """

    pairs: Array  # (P, 2)
    axis: int = 0
    center: float = 0.0

    def __call__(
        self,
        positions: Array,
        rotations: Array,
        context: LossContext,
        epoch: int = 0,
        total_epochs: int = 1,
        net_virtual_nodes: Array | None = None,
        **kwargs: Any,
    ) -> LossResult:
        if self.pairs.shape[0] < 1:
            return LossResult(value=jnp.array(0.0))

        idx_a = self.pairs[:, 0]
        idx_b = self.pairs[:, 1]

        pos_a = positions[idx_a]
        pos_b = positions[idx_b]

        # Calculate expected position of b (reflected a)
        # reflected_x = 2 * center - x
        expected_pos_b = pos_a.at[:, self.axis].set(2 * self.center - pos_a[:, self.axis])

        # In other axis, they should match
        # reflected_y = y (if axis=0)
        # So we just compare the whole vector.

        diff = pos_b - expected_pos_b
        penalty = jnp.sum(diff**2)

        return LossResult(value=penalty)


@dataclass
class VisualGroupingLoss(LossFunction):
    """
    Promotes tight functional clustering with clear boundaries between groups.

    1. Intra-group: Minimizes the variance of components within each group (tight clusters).
    2. Inter-group: Penalizes overlap/proximity between different functional groups.

    Attributes:
        group_indices: (G, M) array of component indices in each group, padded with -1.
        min_gap: Minimum desired gap between different groups (mm).
        intra_weight: Relative weight of tight clustering vs separation.
    """

    group_indices: Array  # (G, M) array, padded with -1
    min_gap: float = 10.0
    intra_weight: float = 1.0

    def __call__(
        self,
        positions: Array,
        rotations: Array,
        context: LossContext,
        epoch: int = 0,
        total_epochs: int = 1,
        net_virtual_nodes: Array | None = None,
        **kwargs: Any,
    ) -> LossResult:
        if self.group_indices.shape[0] < 1:
            return LossResult(value=jnp.array(0.0))

        def compute_group_metrics(indices):
            mask = indices != -1
            group_pos = positions[jnp.where(mask, indices, 0)]
            n_valid = jnp.sum(mask)

            # 1. Intra-group clustering (Variance)
            centroid = jnp.sum(group_pos * mask[:, None], axis=0) / jnp.maximum(n_valid, 1.0)
            diff_sq = (group_pos - centroid) ** 2 * mask[:, None]
            variance = jnp.sum(diff_sq) / jnp.maximum(n_valid, 1.0)

            # 2. Group Bounding Box (via LogSumExp for differentiability)
            # bb = [min_x, min_y, max_x, max_y]
            alpha = 10.0  # sharpness

            # Mask out invalid components by setting to very high/low values for min/max
            pos_x = group_pos[:, 0]
            pos_y = group_pos[:, 1]

            # Soft Min/Max (stable)
            min_x = -jax.scipy.special.logsumexp(-alpha * pos_x, b=mask) / alpha
            max_x = jax.scipy.special.logsumexp(alpha * pos_x, b=mask) / alpha
            min_y = -jax.scipy.special.logsumexp(-alpha * pos_y, b=mask) / alpha
            max_y = jax.scipy.special.logsumexp(alpha * pos_y, b=mask) / alpha

            return variance, jnp.array([min_x, min_y, max_x, max_y])

        # Vmap over all groups
        intra_losses, group_bbs = jax.vmap(compute_group_metrics)(self.group_indices)

        total_intra = jnp.sum(intra_losses)

        # Inter-group separation
        # Penalize if group_bbs are closer than min_gap
        n_groups = self.group_indices.shape[0]
        total_inter = 0.0

        if n_groups > 1:
            # Pairwise group distance
            # bb: [min_x, min_y, max_x, max_y]
            # dist_x = max(0, max(bb1_min_x, bb2_min_x) - min(bb1_max_x, bb2_max_x))
            # But we want separation, so:
            # dist_x = max(bb2_min_x - bb1_max_x, bb1_min_x - bb2_max_x)

            def group_dist_sq(i, j):
                bb1 = group_bbs[i]
                bb2 = group_bbs[j]

                # Max of separation in X and Y
                dx = jnp.maximum(bb2[0] - bb1[2], bb1[0] - bb2[2])
                dy = jnp.maximum(bb2[1] - bb1[3], bb1[1] - bb2[3])

                # If both are negative, they overlap.
                # Distance is max(dx, dy)
                dist = jnp.maximum(dx, dy)

                # Penalty if distance < min_gap
                return jnp.square(jnp.maximum(0.0, self.min_gap - dist))

            # Sum over all pairs
            i_indices, j_indices = jnp.triu_indices(n_groups, k=1)
            pair_penalties = jax.vmap(lambda i, j: group_dist_sq(i, j))(i_indices, j_indices)
            total_inter = jnp.sum(pair_penalties)

        return LossResult(
            value=self.intra_weight * total_intra + total_inter,
            breakdown={
                "intra_group": total_intra,
                "inter_group": total_inter,
            },
        )


@dataclass
class ConsensusLayoutLoss(LossFunction):
    """
    Enforces identical internal layouts for isomorphic component groups.

    For a set of groups sharing the same 'template_group' ID, this loss
    calculates the mean relative positions of all components and pulls
    each group toward that consensus shape.

    Attributes:
        template_groups: (G, K, M) array where G is number of template types,
            K is number of instances of that type, and M is max group size.
            Contains component indices, padded with -1.
    """

    template_groups: Array  # (G, K, M)

    def __call__(
        self,
        positions: Array,
        rotations: Array,
        context: LossContext,
        epoch: int = 0,
        total_epochs: int = 1,
        net_virtual_nodes: Array | None = None,
        **kwargs: Any,
    ) -> LossResult:
        if self.template_groups.shape[0] == 0:
            return LossResult(value=jnp.array(0.0))

        def compute_template_type_loss(instances):
            # instances is (K, M) indices
            # 1. Get absolute positions: (K, M, 2)
            # Use where to handle -1 indices safely
            safe_indices = jnp.where(instances == -1, 0, instances)
            abs_pos = positions[safe_indices]
            mask = instances != -1  # (K, M)

            # 2. Compute centroids for each instance: (K, 2)
            n_in_group = jnp.sum(mask, axis=1, keepdims=True)
            centroids = jnp.sum(abs_pos * mask[:, :, None], axis=1) / jnp.maximum(n_in_group, 1.0)

            # 3. Compute relative positions: (K, M, 2)
            rel_pos = abs_pos - centroids[:, None, :]

            # 4. Compute consensus relative positions (mean across instances): (M, 2)
            # Count how many instances each component index M has
            n_instances = jnp.sum(mask, axis=0, keepdims=True)  # (1, M)
            consensus_rel = jnp.sum(rel_pos * mask[:, :, None], axis=0) / jnp.maximum(
                n_instances.T, 1.0
            )

            # 5. Penalize deviation from consensus: sum |rel_pos - consensus_rel|^2
            deviation = (rel_pos - consensus_rel[None, :, :]) ** 2
            penalty = jnp.sum(deviation * mask[:, :, None])

            return penalty

        # Sum over all template types
        total_penalty = jnp.sum(jax.vmap(compute_template_type_loss)(self.template_groups))

        return LossResult(value=total_penalty)


@dataclass
class StackedRowLoss(LossFunction):
    """
    Organizes a functional group into a 2D matrix of stacked rows with dynamic gutters.

    Useful for large banks of components (e.g., decoupling caps, LED drivers).
    The vertical distance between rows (gutter) grows based on the number of
    nets passing between rows.

    Attributes:
        component_indices: (M,) array of component indices in the group.
        cols: Number of columns in the matrix.
        min_row_pitch: Minimum vertical distance between rows.
        col_pitch: Desired horizontal distance between columns.
        net_crossing_weight: mm of extra gutter per net crossing.
    """

    component_indices: Array
    cols: int
    min_row_pitch: float
    col_pitch: float
    net_crossing_weight: float = 0.5

    def __call__(
        self,
        positions: Array,
        rotations: Array,
        context: LossContext,
        epoch: int = 0,
        total_epochs: int = 1,
        net_virtual_nodes: Array | None = None,
        **kwargs: Any,
    ) -> LossResult:
        if self.component_indices.shape[0] < 2:
            return LossResult(value=jnp.array(0.0))

        # 1. Map group components to row indices
        m = self.component_indices.shape[0]
        num_rows = (m + self.cols - 1) // self.cols
        indices = jnp.arange(m)
        group_row_indices = indices // self.cols
        group_col_indices = indices % self.cols

        # 2. Count nets crossing each gutter
        # A gutter exists between row i and i+1
        n_comps = positions.shape[0]
        comp_to_row = jnp.full((n_comps,), -1)
        comp_to_row = comp_to_row.at[self.component_indices].set(group_row_indices)

        # Row assignments for all pins in all nets
        pin_rows = comp_to_row[context.net_pin_indices]
        pin_rows = jnp.where(context.net_pin_mask, pin_rows, -1)

        def count_crossings(gutter_idx):
            # Net crosses if it has pins in row <= gutter_idx AND pins elsewhere
            # (either in a higher row or outside the group)
            has_below = jnp.any((pin_rows <= gutter_idx) & (pin_rows != -1), axis=1)
            has_above_or_out = jnp.any((pin_rows > gutter_idx) | (pin_rows == -1), axis=1)
            # Only count nets that actually connect to this set of components
            return jnp.sum(has_below & has_above_or_out)

        # Calculate row offsets
        if num_rows > 1:
            crossing_counts = jax.vmap(count_crossings)(jnp.arange(num_rows - 1))
            gutters = self.min_row_pitch + self.net_crossing_weight * crossing_counts
            row_offsets = jnp.concatenate([jnp.array([0.0]), jnp.cumsum(gutters)])
        else:
            row_offsets = jnp.array([0.0])
            crossing_counts = jnp.array([])

        # 3. Compute target positions
        target_rel_x = group_col_indices * self.col_pitch
        target_rel_y = row_offsets[group_row_indices]
        target_rel = jnp.stack([target_rel_x, target_rel_y], axis=-1)

        # 4. Center the target matrix on the current group centroid
        group_pos = positions[self.component_indices]
        centroid = jnp.mean(group_pos, axis=0)
        target_centroid = jnp.mean(target_rel, axis=0)
        target_abs = target_rel - target_centroid + centroid

        # 5. Penalize deviation: sum |pos - target|^2
        penalty = jnp.sum((group_pos - target_abs) ** 2)

        return LossResult(
            value=penalty,
            breakdown={
                "crossing_counts": crossing_counts,
            },
        )


@dataclass
class PinGridAlignmentLoss(LossFunction):
    """
    Penalizes component pins that are not aligned to the manufacturing grid.

    This ensures that traces exiting pads will be straight, avoiding 'wiggles'
    or stair-stepping in the final routing.

    Attributes:
        grid_size: Grid spacing in mm.
    """

    grid_size: float = 0.5

    def __call__(
        self,
        positions: Array,
        rotations: Array,
        context: LossContext,
        epoch: int = 0,
        total_epochs: int = 1,
        net_virtual_nodes: Array | None = None,
        **kwargs: Any,
    ) -> LossResult:
        # 1. Compute absolute pin positions
        # Use existing logic from HPWL/Wirelength
        # pin_comp_positions: (M, P, 2)
        pin_comp_positions = positions[context.net_pin_indices]

        # Compute rotation angles from soft one-hot: (N,)
        angles = jnp.array([0.0, jnp.pi / 2, jnp.pi, 3 * jnp.pi / 2])
        comp_angles = jnp.sum(rotations * angles[None, :], axis=1)  # (N,)
        pin_angles = comp_angles[context.net_pin_indices]

        # Rotate pin offsets
        cos_a = jnp.cos(pin_angles)
        sin_a = jnp.sin(pin_angles)
        px, py = context.net_pin_offsets[:, :, 0], context.net_pin_offsets[:, :, 1]
        rx = px * cos_a - py * sin_a
        ry = px * sin_a + py * cos_a
        pin_positions = pin_comp_positions + jnp.stack([rx, ry], axis=-1)

        # 2. Compute grid distance for all valid pins
        mask = context.net_pin_mask
        x_off = jnp.mod(pin_positions[:, :, 0], self.grid_size)
        y_off = jnp.mod(pin_positions[:, :, 1], self.grid_size)
        dist_x = jnp.minimum(x_off, self.grid_size - x_off)
        dist_y = jnp.minimum(y_off, self.grid_size - y_off)

        # 3. Sum squared distances for masked pins
        penalty = jnp.sum((dist_x**2 + dist_y**2) * mask)

        return LossResult(value=penalty)


@dataclass
class PortFacingRotationLoss(LossFunction):
    """
    Encourages component groups to rotate so their 'primary_pin' faces their
    electrical source/destination.

    Attributes:
        group_indices: (G, M) array of component indices in each group.
        primary_pin_offsets: (G, 2) local (x,y) offset of the primary pin relative to group centroid.
        target_indices: (G, K) indices of target components to face (e.g., connected net).
    """

    group_indices: Array  # (G, M)
    primary_pin_offsets: Array  # (G, 2)
    target_indices: Array  # (G, K)

    def __call__(
        self,
        positions: Array,
        rotations: Array,
        context: LossContext,
        epoch: int = 0,
        total_epochs: int = 1,
        net_virtual_nodes: Array | None = None,
        **kwargs: Any,
    ) -> LossResult:
        if self.group_indices.shape[0] == 0:
            return LossResult(value=jnp.array(0.0))

        def compute_group_facing_loss(g_idx):
            indices = self.group_indices[g_idx]
            mask = indices != -1
            safe_indices = jnp.where(mask, indices, 0)

            # 1. Get Group Centroid
            group_pos = positions[safe_indices]
            n_valid = jnp.sum(mask)
            centroid = jnp.sum(group_pos * mask[:, None], axis=0) / jnp.maximum(n_valid, 1.0)

            # 2. Get Group Rotation (Average)
            angles = jnp.array([0.0, jnp.pi / 2, jnp.pi, 3 * jnp.pi / 2])
            group_rotations = rotations[safe_indices]  # (M, 4)
            comp_angles = jnp.sum(group_rotations * angles[None, :], axis=1)  # (M,)
            avg_angle = jnp.sum(comp_angles * mask) / jnp.maximum(n_valid, 1.0)

            # 3. Get Target Centroid
            t_indices = self.target_indices[g_idx]
            t_mask = t_indices != -1
            t_safe_indices = jnp.where(t_mask, t_indices, 0)

            target_pos_arr = positions[t_safe_indices]
            n_targets = jnp.sum(t_mask)
            target_centroid = jnp.sum(target_pos_arr * t_mask[:, None], axis=0) / jnp.maximum(
                n_targets, 1.0
            )

            # 4. Vector from Group to Target
            target_vec = target_centroid - centroid

            # 5. Rotated Primary Pin Vector
            p_local = self.primary_pin_offsets[g_idx]
            cos_a = jnp.cos(avg_angle)
            sin_a = jnp.sin(avg_angle)
            p_rotated = jnp.array(
                [
                    p_local[0] * cos_a - p_local[1] * sin_a,
                    p_local[0] * sin_a + p_local[1] * cos_a,
                ]
            )

            # 6. Cosine Distance
            p_norm = p_rotated / (jnp.linalg.norm(p_rotated) + 1e-6)
            t_norm = target_vec / (jnp.linalg.norm(target_vec) + 1e-6)

            # Penalty = 1.0 - cosine_similarity (0 if aligned, 2 if opposite)
            penalty = 1.0 - jnp.dot(p_norm, t_norm)

            # Zero out penalty if no targets
            return jnp.where(n_targets > 0, penalty, 0.0)

        # Sum over all groups
        total_penalty = jnp.sum(
            jax.vmap(compute_group_facing_loss)(jnp.arange(self.group_indices.shape[0]))
        )

        return LossResult(value=total_penalty)


def get_template_groups(netlist: Netlist, constraints: PlacementConstraints) -> Array:
    """
    Groups component indices that should share a common layout template.

    Identifies groups either by explicit 'template_group' tags in constraints
    or by automatic topological isomorphism detection.

    Returns:
        (G, K, M) array of indices, padded with -1.
    """
    from collections import defaultdict

    template_map = defaultdict(list)

    # 1. Use explicit template tags from constraints
    for group in constraints.component_groups:
        if group.template_group:
            indices = [netlist.get_component_index(ref) for ref in group.components]
            template_map[group.template_group].append(indices)

    # 2. Add auto-detected isomorphic groups (if not already in a template)
    # TODO: Implement auto-detection merge logic if needed

    if not template_map:
        return jnp.zeros((0, 0, 0), dtype=jnp.int32)

    # Normalize dimensions for padding
    g_count = len(template_map)
    k_max = max(len(instances) for instances in template_map.values())
    m_max = max(len(group) for instances in template_map.values() for group in instances)

    # Create padded array (G, K, M)
    result = jnp.full((g_count, k_max, m_max), -1, dtype=jnp.int32)

    for g_idx, (_name, instances) in enumerate(template_map.items()):
        for k_idx, indices in enumerate(instances):
            for m_idx, comp_idx in enumerate(indices):
                result = result.at[g_idx, k_idx, m_idx].set(comp_idx)

    return result


def get_prefix_groups(netlist: Netlist, exceptions: list[str] | None = None) -> Array:
    """
    Groups components by their reference designator prefix (e.g., 'R', 'C').

    Args:
        netlist: The netlist to analyze.
        exceptions: List of component refs to exclude from alignment.

    Returns:
        (G, M) array of component indices, padded with -1.
    """
    import re

    groups_dict = {}
    exceptions = exceptions or []

    for i, comp in enumerate(netlist.components):
        if comp.ref in exceptions:
            continue

        # Extract prefix (all letters at start)
        match = re.match(r"^([a-zA-Z]+)", comp.ref)
        if not match:
            continue
        prefix = match.group(1)

        # Ignore common single-instance prefixes or very large ones?
        # For now, just group everything by prefix
        if prefix not in groups_dict:
            groups_dict[prefix] = []
        groups_dict[prefix].append(i)

    # Filter for groups with at least 2 members
    valid_groups = [g for g in groups_dict.values() if len(g) > 1]
    if not valid_groups:
        return jnp.zeros((0, 0), dtype=jnp.int32)

    # Convert to padded array (G, M)
    max_len = max(len(g) for g in valid_groups)
    padded = [g + [-1] * (max_len - len(g)) for g in valid_groups]
    return jnp.array(padded, dtype=jnp.int32)


def get_port_facing_data(
    netlist: Netlist, constraints: PlacementConstraints
) -> tuple[Array, Array, Array]:
    """
    Prepare data for PortFacingRotationLoss.

    Returns:
        group_indices: (G, M) array of component indices in each group.
        primary_pin_offsets: (G, 2) local (x,y) offset of the primary pin relative to group centroid.
        target_indices: (G, K) indices of target components to face.
    """
    groups_with_pin = [g for g in constraints.component_groups if g.primary_pin]
    if not groups_with_pin:
        return (
            jnp.zeros((0, 0), dtype=jnp.int32),
            jnp.zeros((0, 2), dtype=jnp.float32),
            jnp.zeros((0, 0), dtype=jnp.int32),
        )

    # 1. Prepare lists for construction
    g_indices_list = []
    pin_offsets_list = []
    t_indices_list = []

    for group in groups_with_pin:
        # Get group component indices
        g_comp_indices = [netlist.get_component_index(ref) for ref in group.components]
        g_indices_list.append(g_comp_indices)

        # Find primary pin component and offset
        pin_name = group.primary_pin

        # Check if primary_pin is "Ref:Pin" or just "Pin" (implying unique in group?)
        # Constraint documentation usually implies "PinName" on one of the components.
        # But which one? The group might have multiple components.
        # We assume primary_pin format is either "PinName" (and we search) or "Ref:PinName".

        target_comp = None
        target_pin_obj = None

        if ":" in pin_name:
            ref, pin = pin_name.split(":")
            if ref in group.components:
                target_comp = netlist.get_component(ref)
                target_pin_obj = target_comp.get_pin(pin)
        else:
            # Search all components in group for this pin
            for ref in group.components:
                comp = netlist.get_component(ref)
                p = comp.get_pin(pin_name)
                if p:
                    target_comp = comp
                    target_pin_obj = p
                    break

        if not target_comp or not target_pin_obj:
            # Skip invalid groups (warn in logs in real app)
            continue

        # Calculate approximate group centroid for offset calculation
        # We rely on initial_positions if available, else assume 0
        # If components don't have initial positions, we treat the pin-bearing component as center

        # Collect available positions
        positions = []
        for ref in group.components:
            c = netlist.get_component(ref)
            if c.initial_position:
                positions.append(c.initial_position)
            elif c == target_comp:
                positions.append((0.0, 0.0))  # Relative origin

        if positions:
            centroid_x = sum(p[0] for p in positions) / len(positions)
            centroid_y = sum(p[1] for p in positions) / len(positions)
        else:
            centroid_x, centroid_y = 0.0, 0.0

        # Target component position (relative to world 0 if using initial positions)
        # But we need relative to centroid.

        comp_x, comp_y = 0.0, 0.0
        if target_comp.initial_position:
            comp_x, comp_y = target_comp.initial_position

        # Pin offset relative to component center
        px, py = target_pin_obj.position

        # Pin offset relative to group centroid
        # P_global = C_global + P_local_to_C
        # P_rel_G = P_global - G_global = (C_global - G_global) + P_local_to_C

        off_x = (comp_x - centroid_x) + px
        off_y = (comp_y - centroid_y) + py

        pin_offsets_list.append([off_x, off_y])

        # Find targets (components connected to this pin, EXCLUDING group members)
        net_name = target_pin_obj.net
        targets = []
        if net_name:
            net = netlist.get_net(net_name)
            for ref, _ in net.pins:
                if ref not in group.components:
                    targets.append(netlist.get_component_index(ref))

        t_indices_list.append(targets)

    # Pad and convert to arrays
    if not g_indices_list:
        return (
            jnp.zeros((0, 0), dtype=jnp.int32),
            jnp.zeros((0, 2), dtype=jnp.float32),
            jnp.zeros((0, 0), dtype=jnp.int32),
        )

    # Pad groups
    max_g = max(len(g) for g in g_indices_list)
    g_arr = jnp.array([g + [-1] * (max_g - len(g)) for g in g_indices_list], dtype=jnp.int32)

    # Offsets
    off_arr = jnp.array(pin_offsets_list, dtype=jnp.float32)

    # Pad targets
    max_t = max(len(t) for t in t_indices_list) if t_indices_list else 0
    if max_t == 0:
        t_arr = jnp.full((len(t_indices_list), 0), -1, dtype=jnp.int32)
    else:
        t_arr = jnp.array([t + [-1] * (max_t - len(t)) for t in t_indices_list], dtype=jnp.int32)

    return g_arr, off_arr, t_arr


__all__ = [
    "AlignmentLoss",
    "ConsensusLayoutLoss",
    "MirrorSymmetryLoss",
    "PinGridAlignmentLoss",
    "PortFacingRotationLoss",
    "RotationConsistencyLoss",
    "StackedRowLoss",
    "VisualGroupingLoss",
    "WhitespaceLoss",
    "create_aesthetic_losses",
    "get_prefix_groups",
    "get_template_groups",
    "get_port_facing_data",
]


def create_aesthetic_losses(
    netlist: Netlist,
    constraints: PlacementConstraints,
) -> list[WeightedLoss]:
    """
    Create aesthetic losses based on constraints.

    Args:
        netlist: Component netlist.
        constraints: Full placement constraints from YAML.

    Returns:
        List of WeightedLoss instances.
    """
    from temper_placer.losses.base import WeightedLoss

    losses = []
    aesthetic_cfg = constraints.aesthetics

    # 1. Grid alignment (Component Centers)
    if aesthetic_cfg.grid_weight > 0:
        losses.append(
            WeightedLoss(
                GridAlignmentLoss(grid_size=aesthetic_cfg.grid_size_mm),
                weight=aesthetic_cfg.grid_weight,
            )
        )

    # 1b. Pin Grid alignment
    if aesthetic_cfg.grid_weight > 0:
        losses.append(
            WeightedLoss(
                PinGridAlignmentLoss(grid_size=aesthetic_cfg.grid_size_mm),
                weight=aesthetic_cfg.grid_weight,
            )
        )

    # 2. Row/Column alignment by prefix
    if aesthetic_cfg.alignment_weight > 0 and aesthetic_cfg.align_by_prefix:
        prefix_groups = get_prefix_groups(netlist, exceptions=aesthetic_cfg.prefix_exceptions)
        if prefix_groups.shape[0] > 0:
            losses.append(
                WeightedLoss(
                    AlignmentLoss(prefix_groups=prefix_groups),
                    weight=aesthetic_cfg.alignment_weight,
                )
            )

    # 3. Consensus Layout (Identical Subcircuits)
    if aesthetic_cfg.consensus_weight > 0:
        template_groups = get_template_groups(netlist, constraints)
        if template_groups.shape[0] > 0:
            losses.append(
                WeightedLoss(
                    ConsensusLayoutLoss(template_groups=template_groups),
                    weight=aesthetic_cfg.consensus_weight,
                )
            )

    # 4. Rotation consistency
    if aesthetic_cfg.rotation_consistency_weight > 0:
        losses.append(
            WeightedLoss(
                RotationConsistencyLoss(),
                weight=aesthetic_cfg.rotation_consistency_weight,
            )
        )

    # 5. Port Facing Rotation
    # Use a high default weight for structural constraints if not explicitly configured
    # Reuse consensus_weight as it is also a structural constraint
    weight = aesthetic_cfg.consensus_weight if aesthetic_cfg.consensus_weight > 0 else 1.0

    group_indices, pin_offsets, target_indices = get_port_facing_data(netlist, constraints)
    if group_indices.shape[0] > 0:
        losses.append(
            WeightedLoss(
                PortFacingRotationLoss(
                    group_indices=group_indices,
                    primary_pin_offsets=pin_offsets,
                    target_indices=target_indices,
                ),
                weight=weight * 5.0,  # Boost weight as this is usually critical
            )
        )

    # 6. Stacked Row Layout
    for group in constraints.component_groups:
        if group.stacked_layout:
            indices = jnp.array([netlist.get_component_index(ref) for ref in group.components])
            if indices.shape[0] >= 2:
                # Default parameters for stacking
                # These could be made configurable in ComponentGroup later
                losses.append(
                    WeightedLoss(
                        StackedRowLoss(
                            component_indices=indices,
                            cols=int(jnp.sqrt(indices.shape[0])),  # Approx square matrix by default
                            min_row_pitch=10.0,
                            col_pitch=10.0,
                            net_crossing_weight=0.5,
                        ),
                        weight=aesthetic_cfg.consensus_weight * 2.0,
                    )
                )

    # 7. Whitespace Distribution
    if aesthetic_cfg.whitespace_weight > 0:
        losses.append(
            WeightedLoss(
                WhitespaceLoss(grid_shape=(10, 10)),
                weight=aesthetic_cfg.whitespace_weight,
            )
        )

    # 8. Visual Grouping
    if aesthetic_cfg.grouping_weight > 0 and constraints.component_groups:
        # Prepare group indices
        g_indices = []
        for group in constraints.component_groups:
            indices = [netlist.get_component_index(ref) for ref in group.components]
            g_indices.append(indices)

        # Pad
        max_len = max(len(g) for g in g_indices)
        padded = [g + [-1] * (max_len - len(g)) for g in g_indices]
        group_arr = jnp.array(padded, dtype=jnp.int32)

        losses.append(
            WeightedLoss(
                VisualGroupingLoss(group_indices=group_arr, min_gap=10.0),
                weight=aesthetic_cfg.grouping_weight,
            )
        )

    # 9. Mirror Symmetry
    if aesthetic_cfg.symmetry_weight > 0:
        from temper_placer.losses.grouping import find_isomorphic_pairs

        isomorphic_pairs = find_isomorphic_pairs(netlist)
        if isomorphic_pairs:
            # find_isomorphic_pairs returns (a1, b1, a2, b2)
            # We can treat (a1, a2) and (b1, b2) as symmetric pairs
            pairs = []
            for a1, b1, a2, b2 in isomorphic_pairs:
                pairs.append([a1, a2])
                pairs.append([b1, b2])

            # Remove duplicates and convert to array
            unique_pairs = []
            seen = set()
            for p in pairs:
                p_tuple = tuple(sorted(p))
                if p_tuple not in seen:
                    unique_pairs.append(p)
                    seen.add(p_tuple)

            if unique_pairs:
                board_bounds = jnp.array(
                    [0.0, 0.0, constraints.board_width_mm, constraints.board_height_mm]
                )
                center_x = (board_bounds[0] + board_bounds[2]) / 2.0

                losses.append(
                    WeightedLoss(
                        MirrorSymmetryLoss(
                            pairs=jnp.array(unique_pairs),
                            axis=0,  # Vertical axis (mirror X)
                            center=center_x,
                        ),
                        weight=aesthetic_cfg.symmetry_weight,
                    )
                )

    return losses
