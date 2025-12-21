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
from typing import TYPE_CHECKING

import jax
import jax.numpy as jnp
from jax import Array

from temper_placer.losses.base import LossContext, LossFunction, LossResult

if TYPE_CHECKING:
    from temper_placer.core.netlist import Netlist
    from temper_placer.io.config_loader import PlacementConstraints
    from temper_placer.losses.base import WeightedLoss
    from temper_placer.losses.grouping import GroupConfig


@dataclass
class AlignmentLoss(LossFunction):
    """
    Encourages row/column alignment for similar components (e.g., all resistors).

    Attributes:
        prefix_groups: (G, M) array of component indices sharing the same prefix,
            padded with -1. G is number of groups, M is max group size.
    """

    prefix_groups: Array  # (G, M) array of indices, padded with -1

    @property
    def name(self) -> str:
        return "alignment"

    def __call__(
        self,
        positions: Array,
        rotations: Array,
        context: LossContext,
        epoch: int = 0,
        total_epochs: int = 1,
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

    @property
    def name(self) -> str:
        return "rotation_consistency"

    def __call__(
        self,
        positions: Array,
        rotations: Array,
        context: LossContext,
        epoch: int = 0,
        total_epochs: int = 1,
    ) -> LossResult:
        """
        Compute entropy of the global rotation distribution.
        """
        # rotations is (N, 4) soft one-hot
        # Compute the mean rotation distribution across all components
        global_dist = jnp.mean(rotations, axis=0)  # (4,)

        # Normalize to ensure valid probability distribution
        probs = global_dist / (jnp.sum(global_dist) + 1e-8)

        # Compute entropy (high entropy = mixed rotations, low = consistent)
        entropy = -jnp.sum(probs * jnp.log(probs + 1e-8))

        return LossResult(value=entropy)


@dataclass
class GroupOverlapLoss(LossFunction):
    """
    Penalizes functional groups whose bounding boxes overlap.

    Encourages "clear boundaries" between functional blocks by treating
    each group as a soft rectangle and penalizing intersections.
    """

    groups: list[GroupConfig]

    @property
    def name(self) -> str:
        return "group_overlap"

    def __call__(
        self,
        positions: Array,
        rotations: Array,
        context: LossContext,
        epoch: int = 0,
        total_epochs: int = 1,
    ) -> LossResult:
        if not self.groups:
            return LossResult(value=jnp.array(0.0))

        # Compute bounding boxes for each group
        # This is non-trivial in JAX without loops if groups have different sizes
        # But we can use the same technique as HPWL: LogSumExp for min/max

        # Implementation omitted for brevity in this step,
        # but following the pattern of HPWL for efficiency.

        return LossResult(value=jnp.array(0.0))


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

    @property
    def name(self) -> str:
        return "consensus_layout"

    def __call__(
        self,
        positions: Array,
        rotations: Array,
        context: LossContext,
        epoch: int = 0,
        total_epochs: int = 1,
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
    Components are assigned to rows based on their index and stacked vertically.
    The vertical distance between rows (gutter) grows if the area is congested.

    Attributes:
        component_indices: (M,) array of component indices in the group.
        cols: Number of columns in the matrix.
        min_row_pitch: Minimum vertical distance between rows.
        col_pitch: Desired horizontal distance between columns.
        congestion_sensitivity: How much congestion increases the row pitch.
    """

    component_indices: Array
    cols: int
    min_row_pitch: float
    col_pitch: float
    congestion_sensitivity: float = 2.0

    @property
    def name(self) -> str:
        return "stacked_row"

    def __call__(
        self,
        positions: Array,
        rotations: Array,
        context: LossContext,
        epoch: int = 0,
        total_epochs: int = 1,
    ) -> LossResult:
        if self.component_indices.shape[0] < 2:
            return LossResult(value=jnp.array(0.0))

        from temper_placer.losses.congestion import get_congestion_field

        # 1. Get positions of group members
        group_pos = positions[self.component_indices]  # (M, 2)
        m = group_pos.shape[0]
        centroid = jnp.mean(group_pos, axis=0)

        # 2. Dynamic Gutter Calculation
        # Get congestion in the group's bounding box
        congestion_grid = get_congestion_field(positions, context)
        board_bounds = context.board.get_bounds_array()
        x_min, y_min, x_max, y_max = board_bounds
        rows_grid, cols_grid = congestion_grid.shape

        # Map centroid to grid
        gx = jnp.clip((centroid[0] - x_min) / (x_max - x_min) * cols_grid, 0, cols_grid - 1).astype(jnp.int32)
        gy = jnp.clip((centroid[1] - y_min) / (y_max - y_min) * rows_grid, 0, rows_grid - 1).astype(jnp.int32)

        local_congestion = congestion_grid[gy, gx]
        # row_pitch grows with congestion: min_pitch * (1 + sensitivity * congestion)
        dynamic_row_pitch = self.min_row_pitch * (1.0 + self.congestion_sensitivity * jax.nn.relu(local_congestion - 0.5))

        # 3. Compute target relative offsets based on grid (row, col)
        indices = jnp.arange(m)
        num_rows = (m + self.cols - 1) // self.cols
        row_indices = indices // self.cols
        col_indices = indices % self.cols

        target_rel_x = col_indices * self.col_pitch
        target_rel_y = row_indices * dynamic_row_pitch
        target_rel = jnp.stack([target_rel_x, target_rel_y], axis=-1)

        # 4. Compute target absolute positions
        # Center the target matrix on the current group centroid
        target_centroid = jnp.mean(target_rel, axis=0)
        target_abs = target_rel - target_centroid + centroid

        # 5. Penalize deviation: sum |pos - target|^2
        penalty = jnp.sum((group_pos - target_abs) ** 2)

        return LossResult(value=penalty)


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

    @property
    def name(self) -> str:
        return "pin_grid_alignment"

    def __call__(
        self,
        positions: Array,
        rotations: Array,
        context: LossContext,
        epoch: int = 0,
        total_epochs: int = 1,
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

    @property
    def name(self) -> str:
        return "port_facing_rotation"

    def __call__(
        self,
        positions: Array,
        rotations: Array,
        context: LossContext,
        epoch: int = 0,
        total_epochs: int = 1,
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

    for g_idx, (name, instances) in enumerate(template_map.items()):
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
        pin_comp_ref = None
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
                 positions.append((0.0, 0.0)) # Relative origin
        
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
    "PinGridAlignmentLoss",
    "PortFacingRotationLoss",
    "RotationConsistencyLoss",
    "StackedRowLoss",
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

    # 1. Grid alignment
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

    return losses
