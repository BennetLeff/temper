"""
Differential Pair Router Module

Implements dual-front A* algorithm for routing differential pairs with:
- Tight coupling enforcement (pairs route together)
- Length matching (skew minimization)
- Impedance control (constant separation)

This addresses the EXP-06-A gap where standard router splits pairs around obstacles.
"""

from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Set
from enum import Enum
import heapq


@dataclass(frozen=True)
class DiffPairState:
    """
    7D state space for differential pair routing.

    Tracks position and layer for both P (positive) and N (negative) traces
    plus their current separation.

    Attributes:
        pos_x: P trace X coordinate (grid cells)
        pos_y: P trace Y coordinate
        pos_layer: P trace layer index
        neg_x: N trace X coordinate
        neg_y: N trace Y coordinate
        neg_layer: N trace layer index
        separation_mm: Current spacing between traces
    """

    pos_x: int
    pos_y: int
    pos_layer: int
    neg_x: int
    neg_y: int
    neg_layer: int
    separation_mm: float

    def __hash__(self):
        """Enable use in sets and dicts. Separation rounded to avoid float issues."""
        return hash(
            (
                self.pos_x,
                self.pos_y,
                self.pos_layer,
                self.neg_x,
                self.neg_y,
                self.neg_layer,
                round(self.separation_mm, 3),  # Round to 0.001mm precision
            )
        )


@dataclass
class DiffPairPath:
    """
    Result of differential pair routing.

    Contains the routed paths for both traces plus metrics for validation.
    """

    pos_cells: List[Tuple[int, int, int]]  # P trace: [(x, y, layer), ...]
    neg_cells: List[Tuple[int, int, int]]  # N trace: [(x, y, layer), ...]

    coupling_ratio: float  # % of path within target separation
    max_skew_mm: float  # Maximum length difference
    avg_separation_mm: float  # Average spacing

    success: bool
    failure_reason: Optional[str] = None

    def __post_init__(self):
        """Calculate derived metrics."""
        if self.success:
            # Basic validation
            if len(self.pos_cells) == 0 or len(self.neg_cells) == 0:
                self.success = False
                self.failure_reason = "Empty path"


class NeighborType(Enum):
    """Type of neighbor generation for differential pairs."""

    BOTH_MOVE_TOGETHER = "both_move"  # Ideal: maintain coupling
    POS_MOVES_NEG_WAITS = "pos_moves"  # Divergence: P navigates obstacle
    NEG_MOVES_POS_WAITS = "neg_moves"  # Divergence: N navigates obstacle
    BOTH_CHANGE_LAYER = "both_via"  # Via transition together
    DIVERGE = "diverge"  # Last resort: split paths


@dataclass
class SearchNode:
    """
    Node in the A* search tree.

    Tracks cost and parent information for path reconstruction.
    """

    state: DiffPairState
    g_cost: float  # Actual cost from start
    h_cost: float  # Heuristic cost to goal
    parent: Optional["SearchNode"] = None
    neighbor_type: Optional[NeighborType] = None

    @property
    def f_cost(self) -> float:
        """Total estimated cost."""
        return self.g_cost + self.h_cost

    def __lt__(self, other):
        """Priority queue ordering by f-cost."""
        return self.f_cost < other.f_cost


class DiffPairRouter:
    """
    Dual-front A* router for differential pairs.

    Routes P and N traces simultaneously while maintaining coupling
    and length matching constraints.
    """

    def __init__(
        self,
        grid_size: Tuple[int, int, int],  # (width, height, layers)
        cell_size_mm: float,
        target_separation_mm: float = 0.2,
        trace_width_mm: float = 0.127,  # EXP-3: For minimum spacing enforcement
        clearance_mm: float = 0.10,  # EXP-3: For minimum spacing enforcement
        max_divergence_mm: float = 1.0,
        max_skew_mm: float = 0.5,
        coupling_weight: float = 5.0,  # Reduced from 10.0 to allow more divergence exploration
        skew_weight: float = 5.0,
        beam_width: int = 2000,  # Phase 2C: Beam search limit (increased from 1000)
        beam_prune_threshold: float = 2.0,  # Only prune when frontier > beam_width * threshold
    ):
        """
        Initialize differential pair router.

        Args:
            grid_size: Grid dimensions (nx, ny, nz)
            cell_size_mm: Size of each grid cell in mm
            target_separation_mm: Desired P-N spacing
            trace_width_mm: Width of traces (for minimum spacing enforcement)
            clearance_mm: Required edge-to-edge clearance
            max_divergence_mm: Maximum allowed divergence
            max_skew_mm: Maximum allowed length mismatch
            coupling_weight: Penalty weight for separation deviation
            skew_weight: Penalty weight for length mismatch
            beam_width: Max states to keep per frontier expansion (Phase 2C)
            beam_prune_threshold: Prune when frontier exceeds beam_width * threshold (default 2.0)
        """
        self.grid_size = grid_size
        self.cell_size_mm = cell_size_mm
        self.target_separation_mm = target_separation_mm
        self.trace_width_mm = trace_width_mm
        self.clearance_mm = clearance_mm
        self.max_divergence_mm = max_divergence_mm
        self.max_skew_mm = max_skew_mm
        self.coupling_weight = coupling_weight
        self.skew_weight = skew_weight
        self.beam_width = beam_width
        self.beam_prune_threshold = beam_prune_threshold

        # EXP-3: Calculate minimum safe center-to-center spacing
        # Edge-to-edge must be >= clearance_mm
        # center_to_center = trace_width + clearance (for parallel traces)
        self.min_safe_separation_mm = trace_width_mm + clearance_mm

        # EXP-3: Validate configuration - warn if target < minimum safe
        if target_separation_mm < self.min_safe_separation_mm:
            import warnings

            warnings.warn(
                f"target_separation_mm ({target_separation_mm:.3f}mm) < "
                f"min_safe_separation_mm ({self.min_safe_separation_mm:.3f}mm). "
                f"Router may fail to find paths or create DRC violations. "
                f"Recommend target_separation_mm >= {self.min_safe_separation_mm:.3f}mm",
                UserWarning,
            )

        # Statistics
        self.states_explored = 0
        self.states_pruned = 0
        self.beam_pruned = 0  # Phase 2C: Track beam search pruning
        self.spacing_pruned = 0  # EXP-3: Track states rejected for spacing violations

    def route_pair(
        self,
        start_pins: Tuple[Tuple[float, float], Tuple[float, float]],  # ((p_x, p_y), (n_x, n_y))
        goal_pins: Tuple[Tuple[float, float], Tuple[float, float]],
        obstacles: Set[Tuple[int, int, int]],  # Set of blocked cells
        enable_length_matching: bool = True,  # Phase 3: apply serpentine tuning
    ) -> DiffPairPath:
        """
        Route a differential pair from start to goal pins using dual-front A*.

        Args:
            start_pins: (P_start, N_start) pin positions in mm
            goal_pins: (P_goal, N_goal) pin positions in mm
            obstacles: Set of blocked grid cells

        Returns:
            DiffPairPath with routing result
        """
        # Reset statistics
        self.states_explored = 0
        self.states_pruned = 0
        self.spacing_pruned = 0
        self.beam_pruned = 0

        # Convert mm to grid coordinates
        start_pos = self._mm_to_grid(start_pins[0])
        start_neg = self._mm_to_grid(start_pins[1])
        goal_pos = self._mm_to_grid(goal_pins[0])
        goal_neg = self._mm_to_grid(goal_pins[1])

        # Create start and goal states (assume layer 0 initially)
        start_sep = self._calculate_separation((*start_pos, 0), (*start_neg, 0))
        goal_sep = self._calculate_separation((*goal_pos, 0), (*goal_neg, 0))

        # EXP-3: Validate start and goal spacing
        if start_sep < self.min_safe_separation_mm:
            return DiffPairPath(
                pos_cells=[],
                neg_cells=[],
                coupling_ratio=0.0,
                max_skew_mm=0.0,
                avg_separation_mm=0.0,
                success=False,
                failure_reason=f"Start pins too close: {start_sep:.3f}mm < {self.min_safe_separation_mm:.3f}mm minimum",
            )

        if goal_sep < self.min_safe_separation_mm:
            return DiffPairPath(
                pos_cells=[],
                neg_cells=[],
                coupling_ratio=0.0,
                max_skew_mm=0.0,
                avg_separation_mm=0.0,
                success=False,
                failure_reason=f"Goal pins too close: {goal_sep:.3f}mm < {self.min_safe_separation_mm:.3f}mm minimum",
            )

        start_state = DiffPairState(
            pos_x=start_pos[0],
            pos_y=start_pos[1],
            pos_layer=0,
            neg_x=start_neg[0],
            neg_y=start_neg[1],
            neg_layer=0,
            separation_mm=start_sep,
        )

        goal_state = DiffPairState(
            pos_x=goal_pos[0],
            pos_y=goal_pos[1],
            pos_layer=0,
            neg_x=goal_neg[0],
            neg_y=goal_neg[1],
            neg_layer=0,
            separation_mm=goal_sep,
        )

        # Initialize forward and backward frontiers
        forward_frontier = []
        backward_frontier = []

        forward_start = SearchNode(
            state=start_state, g_cost=0.0, h_cost=self._heuristic(start_state, goal_state)
        )
        backward_start = SearchNode(
            state=goal_state, g_cost=0.0, h_cost=self._heuristic(goal_state, start_state)
        )

        heapq.heappush(forward_frontier, forward_start)
        heapq.heappush(backward_frontier, backward_start)

        # Track visited states with g-costs
        forward_visited = {start_state: forward_start}
        backward_visited = {goal_state: backward_start}

        # Search loop (alternate between forward and backward)
        max_iterations = 100000
        iteration = 0

        while forward_frontier and backward_frontier and iteration < max_iterations:
            iteration += 1

            # Expand forward front
            if forward_frontier:
                current = heapq.heappop(forward_frontier)
                self.states_explored += 1

                # Check if we've met the backward front
                if current.state in backward_visited:
                    # Fronts met! Reconstruct path
                    return self._reconstruct_path(
                        current,
                        backward_visited[current.state],
                        forward_visited,
                        backward_visited,
                        enable_length_matching,
                    )

                # Generate and process neighbors
                for next_state, neighbor_type, cost_delta in self._generate_coupled_neighbors(
                    current.state, obstacles
                ):
                    g_new = current.g_cost + cost_delta

                    if (
                        next_state not in forward_visited
                        or g_new < forward_visited[next_state].g_cost
                    ):
                        h_new = self._heuristic(next_state, goal_state)
                        next_node = SearchNode(
                            state=next_state,
                            g_cost=g_new,
                            h_cost=h_new,
                            parent=current,
                            neighbor_type=neighbor_type,
                        )
                        forward_visited[next_state] = next_node
                        heapq.heappush(forward_frontier, next_node)

            # Phase 2C: Beam search pruning (limit frontier size)
            # Only prune when frontier significantly exceeds beam_width to reduce overhead
            prune_trigger = int(self.beam_width * self.beam_prune_threshold)
            if len(forward_frontier) > prune_trigger:
                # Keep only top beam_width states by f-cost
                forward_frontier = heapq.nsmallest(self.beam_width, forward_frontier)
                heapq.heapify(forward_frontier)
                self.beam_pruned += 1

            # Expand backward front
            if backward_frontier:
                current = heapq.heappop(backward_frontier)
                self.states_explored += 1

                # Check if we've met the forward front
                if current.state in forward_visited:
                    # Fronts met! Reconstruct path
                    return self._reconstruct_path(
                        forward_visited[current.state],
                        current,
                        forward_visited,
                        backward_visited,
                        enable_length_matching,
                    )

                # Generate and process neighbors (reverse direction)
                for next_state, neighbor_type, cost_delta in self._generate_coupled_neighbors(
                    current.state, obstacles
                ):
                    g_new = current.g_cost + cost_delta

                    if (
                        next_state not in backward_visited
                        or g_new < backward_visited[next_state].g_cost
                    ):
                        h_new = self._heuristic(next_state, start_state)
                        next_node = SearchNode(
                            state=next_state,
                            g_cost=g_new,
                            h_cost=h_new,
                            parent=current,
                            neighbor_type=neighbor_type,
                        )
                        backward_visited[next_state] = next_node
                        heapq.heappush(backward_frontier, next_node)

            # Phase 2C: Beam search pruning (limit frontier size)
            # Only prune when frontier significantly exceeds beam_width to reduce overhead
            if len(backward_frontier) > prune_trigger:
                # Keep only top beam_width states by f-cost
                backward_frontier = heapq.nsmallest(self.beam_width, backward_frontier)
                heapq.heapify(backward_frontier)
                self.beam_pruned += 1

        # No path found
        return DiffPairPath(
            pos_cells=[],
            neg_cells=[],
            coupling_ratio=0.0,
            max_skew_mm=0.0,
            avg_separation_mm=0.0,
            success=False,
            failure_reason=f"No path found after {iteration} iterations. "
            f"Explored {self.states_explored} states, "
            f"pruned {self.states_pruned} (coupling), "
            f"{self.spacing_pruned} (min spacing), "
            f"{self.beam_pruned} (beam search).",
        )

    def _mm_to_grid(self, pos_mm: Tuple[float, float]) -> Tuple[int, int]:
        """Convert position in mm to grid coordinates."""
        return (int(pos_mm[0] / self.cell_size_mm), int(pos_mm[1] / self.cell_size_mm))

    def _reconstruct_path(
        self,
        forward_node: SearchNode,
        backward_node: SearchNode,
        forward_visited: dict,
        backward_visited: dict,
        enable_length_matching: bool = True,
    ) -> DiffPairPath:
        """
        Reconstruct path when forward and backward fronts meet.

        Args:
            forward_node: Meeting point from forward search
            backward_node: Meeting point from backward search
            forward_visited: Forward search visited states
            backward_visited: Backward search visited states

        Returns:
            DiffPairPath with complete routing
        """
        # Extract paths by following parent pointers
        forward_path = []
        current = forward_node
        while current is not None:
            forward_path.append(current.state)
            current = current.parent
        forward_path.reverse()

        # Backward path: built by following parent pointers from backward_node
        # backward_node is at meeting point, parents go toward goal
        # So backward_path will be: [meeting, meeting+1, ..., goal]
        backward_path = []
        current = backward_node
        while current is not None:
            backward_path.append(current.state)
            current = current.parent

        # Skip the meeting point (first element) since it's already in forward_path
        if backward_path:
            backward_path = backward_path[1:]

        # Combine paths: [start → meeting] + [meeting+1 → goal]
        full_path = forward_path + backward_path

        # Extract P and N cell lists
        pos_cells = [(s.pos_x, s.pos_y, s.pos_layer) for s in full_path]
        neg_cells = [(s.neg_x, s.neg_y, s.neg_layer) for s in full_path]

        # Calculate metrics
        coupling_ratio = self._calculate_coupling_ratio(full_path)
        max_skew = abs(len(pos_cells) - len(neg_cells)) * self.cell_size_mm
        avg_sep = sum(s.separation_mm for s in full_path) / len(full_path)

        result = DiffPairPath(
            pos_cells=pos_cells,
            neg_cells=neg_cells,
            coupling_ratio=coupling_ratio,
            max_skew_mm=max_skew,
            avg_separation_mm=avg_sep,
            success=True,
        )

        # Phase 3: Apply length matching if enabled
        if enable_length_matching and max_skew > self.max_skew_mm:
            from temper_placer.routing.serpentine import apply_length_matching

            result = apply_length_matching(result, self.cell_size_mm, self.max_skew_mm)

        return result

    def _calculate_coupling_ratio(self, path: List[DiffPairState]) -> float:
        """Calculate percentage of path within target separation."""
        if not path:
            return 0.0

        tolerance = 0.1  # mm (10% of 1mm target)
        coupled_cells = sum(
            1 for state in path if abs(state.separation_mm - self.target_separation_mm) <= tolerance
        )

        return (coupled_cells / len(path)) * 100.0

    def _generate_coupled_neighbors(
        self,
        state: DiffPairState,
        obstacles: Set[Tuple[int, int, int]],
    ) -> List[Tuple[DiffPairState, NeighborType, float]]:
        """
        Generate valid neighbor states for differential pair.

        Returns list of (next_state, neighbor_type, cost_delta) tuples.

        Neighbor types in priority order:
        1. BOTH_MOVE_TOGETHER: Ideal - maintain coupling
        2. BOTH_CHANGE_LAYER: Via transition together
        3. POS/NEG_MOVES_*_WAITS: Temporary divergence
        4. DIVERGE: Last resort

        Args:
            state: Current state
            obstacles: Blocked cells

        Returns:
            List of valid neighbors with transition costs
        """
        neighbors = []

        # Movement directions: N, S, E, W (no diagonal for now)
        directions = [(0, 1), (0, -1), (1, 0), (-1, 0)]

        # Cost constants
        BASE_MOVE_COST = self.cell_size_mm
        VIA_COST = 2.0  # mm equivalent cost
        # FIX: Reduced from 5.0 to 1.0 - allows offset transition exploration
        # Without this, the router cannot change P-N relative offset from vertical to horizontal
        # (required when start pins are vertically aligned but goal pins are horizontally aligned)
        DIVERGENCE_COST = 1.0

        # 1. BOTH_MOVE_TOGETHER: P and N move in same direction (ideal)
        for dx, dy in directions:
            new_pos_x = state.pos_x + dx
            new_pos_y = state.pos_y + dy
            new_neg_x = state.neg_x + dx
            new_neg_y = state.neg_y + dy

            # Check bounds
            if not self._in_bounds((new_pos_x, new_pos_y, state.pos_layer)):
                continue
            if not self._in_bounds((new_neg_x, new_neg_y, state.neg_layer)):
                continue

            # Check obstacles
            if (new_pos_x, new_pos_y, state.pos_layer) in obstacles:
                continue
            if (new_neg_x, new_neg_y, state.neg_layer) in obstacles:
                continue

            # CRITICAL: P and N must not occupy the same cell (prevents shorts)
            if (
                new_pos_x == new_neg_x
                and new_pos_y == new_neg_y
                and state.pos_layer == state.neg_layer
            ):
                continue

            # Calculate new separation
            new_sep = self._calculate_separation(
                (new_pos_x, new_pos_y, state.pos_layer), (new_neg_x, new_neg_y, state.neg_layer)
            )

            # EXP-3: Enforce minimum safe spacing to prevent DRC violations
            # Traces must maintain edge-to-edge clearance >= clearance_mm
            if new_sep < self.min_safe_separation_mm:
                self.spacing_pruned += 1
                continue

            # Coupling penalty
            sep_penalty = self.coupling_weight * abs(new_sep - self.target_separation_mm)

            # Prune if too diverged
            if abs(new_sep - self.target_separation_mm) > self.max_divergence_mm:
                self.states_pruned += 1
                continue

            new_state = DiffPairState(
                pos_x=new_pos_x,
                pos_y=new_pos_y,
                pos_layer=state.pos_layer,
                neg_x=new_neg_x,
                neg_y=new_neg_y,
                neg_layer=state.neg_layer,
                separation_mm=new_sep,
            )

            cost = BASE_MOVE_COST + sep_penalty
            neighbors.append((new_state, NeighborType.BOTH_MOVE_TOGETHER, cost))

        # 2. BOTH_CHANGE_LAYER: Via transition together (maintains coupling)
        for new_layer in range(self.grid_size[2]):
            if new_layer == state.pos_layer:
                continue

            # Both traces via to same new layer
            new_sep = self._calculate_separation(
                (state.pos_x, state.pos_y, new_layer), (state.neg_x, state.neg_y, new_layer)
            )

            # EXP-3: Enforce minimum safe spacing
            if new_sep < self.min_safe_separation_mm:
                self.spacing_pruned += 1
                continue

            # Check if vias would be blocked
            if (state.pos_x, state.pos_y, new_layer) in obstacles:
                continue
            if (state.neg_x, state.neg_y, new_layer) in obstacles:
                continue

            new_state = DiffPairState(
                pos_x=state.pos_x,
                pos_y=state.pos_y,
                pos_layer=new_layer,
                neg_x=state.neg_x,
                neg_y=state.neg_y,
                neg_layer=new_layer,
                separation_mm=new_sep,
            )

            sep_penalty = self.coupling_weight * abs(new_sep - self.target_separation_mm)
            cost = 2 * VIA_COST + sep_penalty  # 2 vias
            neighbors.append((new_state, NeighborType.BOTH_CHANGE_LAYER, cost))

        # 3. POS_MOVES_NEG_WAITS: P navigates obstacle, N waits
        for dx, dy in directions:
            new_pos_x = state.pos_x + dx
            new_pos_y = state.pos_y + dy

            if not self._in_bounds((new_pos_x, new_pos_y, state.pos_layer)):
                continue
            if (new_pos_x, new_pos_y, state.pos_layer) in obstacles:
                continue

            # CRITICAL: P must not move to N's current position (prevents shorts)
            if (
                new_pos_x == state.neg_x
                and new_pos_y == state.neg_y
                and state.pos_layer == state.neg_layer
            ):
                continue

            new_sep = self._calculate_separation(
                (new_pos_x, new_pos_y, state.pos_layer), (state.neg_x, state.neg_y, state.neg_layer)
            )

            # EXP-3: Enforce minimum safe spacing
            if new_sep < self.min_safe_separation_mm:
                self.spacing_pruned += 1
                continue

            # Prune if too diverged
            if abs(new_sep - self.target_separation_mm) > self.max_divergence_mm:
                self.states_pruned += 1
                continue

            new_state = DiffPairState(
                pos_x=new_pos_x,
                pos_y=new_pos_y,
                pos_layer=state.pos_layer,
                neg_x=state.neg_x,
                neg_y=state.neg_y,
                neg_layer=state.neg_layer,
                separation_mm=new_sep,
            )

            sep_penalty = self.coupling_weight * abs(new_sep - self.target_separation_mm)
            cost = BASE_MOVE_COST + sep_penalty + DIVERGENCE_COST
            neighbors.append((new_state, NeighborType.POS_MOVES_NEG_WAITS, cost))

        # 4. NEG_MOVES_POS_WAITS: N navigates obstacle, P waits
        for dx, dy in directions:
            new_neg_x = state.neg_x + dx
            new_neg_y = state.neg_y + dy

            if not self._in_bounds((new_neg_x, new_neg_y, state.neg_layer)):
                continue
            if (new_neg_x, new_neg_y, state.neg_layer) in obstacles:
                continue

            # CRITICAL: N must not move to P's current position (prevents shorts)
            if (
                new_neg_x == state.pos_x
                and new_neg_y == state.pos_y
                and state.neg_layer == state.pos_layer
            ):
                continue

            new_sep = self._calculate_separation(
                (state.pos_x, state.pos_y, state.pos_layer), (new_neg_x, new_neg_y, state.neg_layer)
            )

            # EXP-3: Enforce minimum safe spacing
            if new_sep < self.min_safe_separation_mm:
                self.spacing_pruned += 1
                continue

            # Prune if too diverged
            if abs(new_sep - self.target_separation_mm) > self.max_divergence_mm:
                self.states_pruned += 1
                continue

            new_state = DiffPairState(
                pos_x=state.pos_x,
                pos_y=state.pos_y,
                pos_layer=state.pos_layer,
                neg_x=new_neg_x,
                neg_y=new_neg_y,
                neg_layer=state.neg_layer,
                separation_mm=new_sep,
            )

            sep_penalty = self.coupling_weight * abs(new_sep - self.target_separation_mm)
            cost = BASE_MOVE_COST + sep_penalty + DIVERGENCE_COST
            neighbors.append((new_state, NeighborType.NEG_MOVES_POS_WAITS, cost))

        return neighbors

    def _in_bounds(self, pos: Tuple[int, int, int]) -> bool:
        """Check if position is within grid bounds."""
        x, y, layer = pos
        return (
            0 <= x < self.grid_size[0]
            and 0 <= y < self.grid_size[1]
            and 0 <= layer < self.grid_size[2]
        )

    def _calculate_separation(
        self,
        pos: Tuple[int, int, int],
        neg: Tuple[int, int, int],
    ) -> float:
        """Calculate Euclidean distance between P and N positions in mm."""
        dx = (pos[0] - neg[0]) * self.cell_size_mm
        dy = (pos[1] - neg[1]) * self.cell_size_mm
        # Ignore Z difference for separation (same-layer spacing matters)
        return (dx**2 + dy**2) ** 0.5

    def _heuristic(
        self,
        state: DiffPairState,
        goal: DiffPairState,
    ) -> float:
        """
        Admissible heuristic for A*.

        Uses max of P and N manhattan distances plus offset mismatch penalty.
        The offset mismatch term guides the search to change P-N relative offset
        early rather than near the goal (where it becomes impossible).
        """
        h_pos = abs(state.pos_x - goal.pos_x) + abs(state.pos_y - goal.pos_y)
        h_neg = abs(state.neg_x - goal.neg_x) + abs(state.neg_y - goal.neg_y)

        # Base heuristic: max ensures we don't underestimate (admissible)
        h_distance = max(h_pos, h_neg) * self.cell_size_mm

        # FIX: Add offset mismatch penalty
        # Current P-N offset (in grid cells)
        current_offset_x = state.pos_x - state.neg_x
        current_offset_y = state.pos_y - state.neg_y

        # Goal P-N offset (in grid cells)
        goal_offset_x = goal.pos_x - goal.neg_x
        goal_offset_y = goal.pos_y - goal.neg_y

        # Offset mismatch (how many divergent moves needed to change alignment)
        offset_mismatch = abs(current_offset_x - goal_offset_x) + abs(
            current_offset_y - goal_offset_y
        )

        # Each offset change requires at minimum one divergent move (cost = cell_size)
        # Using a small weight (0.5) to stay admissible while guiding the search
        h_offset = offset_mismatch * self.cell_size_mm * 0.5

        return h_distance + h_offset


# Phase 2A TODO:
# [ ] Implement _generate_coupled_neighbors()
# [ ] Add unit tests for DiffPairState hashing
# [ ] Add unit tests for neighbor generation
# [ ] Implement priority queue wrapper if needed
# [ ] Benchmark state space size for typical boards
