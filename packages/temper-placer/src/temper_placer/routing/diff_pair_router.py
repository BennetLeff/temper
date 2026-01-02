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
        return hash((
            self.pos_x, self.pos_y, self.pos_layer,
            self.neg_x, self.neg_y, self.neg_layer,
            round(self.separation_mm, 3)  # Round to 0.001mm precision
        ))


@dataclass
class DiffPairPath:
    """
    Result of differential pair routing.
    
    Contains the routed paths for both traces plus metrics for validation.
    """
    pos_cells: List[Tuple[int, int, int]]  # P trace: [(x, y, layer), ...]
    neg_cells: List[Tuple[int, int, int]]  # N trace: [(x, y, layer), ...]
    
    coupling_ratio: float  # % of path within target separation
    max_skew_mm: float     # Maximum length difference
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
    BOTH_MOVE_TOGETHER = "both_move"      # Ideal: maintain coupling
    POS_MOVES_NEG_WAITS = "pos_moves"     # Divergence: P navigates obstacle
    NEG_MOVES_POS_WAITS = "neg_moves"     # Divergence: N navigates obstacle
    BOTH_CHANGE_LAYER = "both_via"        # Via transition together
    DIVERGE = "diverge"                    # Last resort: split paths


@dataclass
class SearchNode:
    """
    Node in the A* search tree.
    
    Tracks cost and parent information for path reconstruction.
    """
    state: DiffPairState
    g_cost: float           # Actual cost from start
    h_cost: float           # Heuristic cost to goal
    parent: Optional['SearchNode'] = None
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
        max_divergence_mm: float = 1.0,
        max_skew_mm: float = 0.5,
        coupling_weight: float = 10.0,
        skew_weight: float = 5.0,
    ):
        """
        Initialize differential pair router.
        
        Args:
            grid_size: Grid dimensions (nx, ny, nz)
            cell_size_mm: Size of each grid cell in mm
            target_separation_mm: Desired P-N spacing
            max_divergence_mm: Maximum allowed divergence
            max_skew_mm: Maximum allowed length mismatch
            coupling_weight: Penalty weight for separation deviation
            skew_weight: Penalty weight for length mismatch
        """
        self.grid_size = grid_size
        self.cell_size_mm = cell_size_mm
        self.target_separation_mm = target_separation_mm
        self.max_divergence_mm = max_divergence_mm
        self.max_skew_mm = max_skew_mm
        self.coupling_weight = coupling_weight
        self.skew_weight = skew_weight
        
        # Statistics
        self.states_explored = 0
        self.states_pruned = 0
    
    def route_pair(
        self,
        start_pins: Tuple[Tuple[float, float], Tuple[float, float]],  # ((p_x, p_y), (n_x, n_y))
        goal_pins: Tuple[Tuple[float, float], Tuple[float, float]],
        obstacles: Set[Tuple[int, int, int]],  # Set of blocked cells
    ) -> DiffPairPath:
        """
        Route a differential pair from start to goal pins.
        
        Uses dual-front A* search to find coupled path.
        
        Args:
            start_pins: (P_start, N_start) pin positions in mm
            goal_pins: (P_goal, N_goal) pin positions in mm
            obstacles: Set of blocked grid cells
            
        Returns:
            DiffPairPath with routing result
        """
        # TODO: Implement dual-front A*
        # This is a skeleton - actual implementation in Phase 2B
        
        return DiffPairPath(
            pos_cells=[],
            neg_cells=[],
            coupling_ratio=0.0,
            max_skew_mm=0.0,
            avg_separation_mm=0.0,
            success=False,
            failure_reason="Not yet implemented"
        )
    
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
        DIVERGENCE_COST = 5.0  # High penalty for splitting
        
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
            
            # Calculate new separation
            new_sep = self._calculate_separation(
                (new_pos_x, new_pos_y, state.pos_layer),
                (new_neg_x, new_neg_y, state.neg_layer)
            )
            
            # Coupling penalty
            sep_penalty = self.coupling_weight * abs(new_sep - self.target_separation_mm)
            
            # Prune if too diverged
            if abs(new_sep - self.target_separation_mm) > self.max_divergence_mm:
                self.states_pruned += 1
                continue
            
            new_state = DiffPairState(
                pos_x=new_pos_x, pos_y=new_pos_y, pos_layer=state.pos_layer,
                neg_x=new_neg_x, neg_y=new_neg_y, neg_layer=state.neg_layer,
                separation_mm=new_sep
            )
            
            cost = BASE_MOVE_COST + sep_penalty
            neighbors.append((new_state, NeighborType.BOTH_MOVE_TOGETHER, cost))
        
        # 2. BOTH_CHANGE_LAYER: Via transition together (maintains coupling)
        for new_layer in range(self.grid_size[2]):
            if new_layer == state.pos_layer:
                continue
            
            # Both traces via to same new layer
            new_sep = self._calculate_separation(
                (state.pos_x, state.pos_y, new_layer),
                (state.neg_x, state.neg_y, new_layer)
            )
            
            # Check if vias would be blocked
            if (state.pos_x, state.pos_y, new_layer) in obstacles:
                continue
            if (state.neg_x, state.neg_y, new_layer) in obstacles:
                continue
            
            new_state = DiffPairState(
                pos_x=state.pos_x, pos_y=state.pos_y, pos_layer=new_layer,
                neg_x=state.neg_x, neg_y=state.neg_y, neg_layer=new_layer,
                separation_mm=new_sep
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
            
            new_sep = self._calculate_separation(
                (new_pos_x, new_pos_y, state.pos_layer),
                (state.neg_x, state.neg_y, state.neg_layer)
            )
            
            # Prune if too diverged
            if abs(new_sep - self.target_separation_mm) > self.max_divergence_mm:
                self.states_pruned += 1
                continue
            
            new_state = DiffPairState(
                pos_x=new_pos_x, pos_y=new_pos_y, pos_layer=state.pos_layer,
                neg_x=state.neg_x, neg_y=state.neg_y, neg_layer=state.neg_layer,
                separation_mm=new_sep
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
            
            new_sep = self._calculate_separation(
                (state.pos_x, state.pos_y, state.pos_layer),
                (new_neg_x, new_neg_y, state.neg_layer)
            )
            
            # Prune if too diverged
            if abs(new_sep - self.target_separation_mm) > self.max_divergence_mm:
                self.states_pruned += 1
                continue
            
            new_state = DiffPairState(
                pos_x=state.pos_x, pos_y=state.pos_y, pos_layer=state.pos_layer,
                neg_x=new_neg_x, neg_y=new_neg_y, neg_layer=state.neg_layer,
                separation_mm=new_sep
            )
            
            sep_penalty = self.coupling_weight * abs(new_sep - self.target_separation_mm)
            cost = BASE_MOVE_COST + sep_penalty + DIVERGENCE_COST
            neighbors.append((new_state, NeighborType.NEG_MOVES_POS_WAITS, cost))
        
        return neighbors
    
    def _in_bounds(self, pos: Tuple[int, int, int]) -> bool:
        """Check if position is within grid bounds."""
        x, y, layer = pos
        return (0 <= x < self.grid_size[0] and
                0 <= y < self.grid_size[1] and
                0 <= layer < self.grid_size[2])
    
    def _calculate_separation(
        self,
        pos: Tuple[int, int, int],
        neg: Tuple[int, int, int],
    ) -> float:
        """Calculate Euclidean distance between P and N positions in mm."""
        dx = (pos[0] - neg[0]) * self.cell_size_mm
        dy = (pos[1] - neg[1]) * self.cell_size_mm
        # Ignore Z difference for separation (same-layer spacing matters)
        return (dx ** 2 + dy ** 2) ** 0.5
    
    def _heuristic(
        self,
        state: DiffPairState,
        goal: DiffPairState,
    ) -> float:
        """
        Admissible heuristic for A*.
        
        Uses max of P and N manhattan distances to ensure admissibility.
        """
        h_pos = abs(state.pos_x - goal.pos_x) + abs(state.pos_y - goal.pos_y)
        h_neg = abs(state.neg_x - goal.neg_x) + abs(state.neg_y - goal.neg_y)
        
        # Max ensures we don't underestimate (admissible)
        return max(h_pos, h_neg) * self.cell_size_mm


# Phase 2A TODO:
# [ ] Implement _generate_coupled_neighbors()
# [ ] Add unit tests for DiffPairState hashing
# [ ] Add unit tests for neighbor generation
# [ ] Implement priority queue wrapper if needed
# [ ] Benchmark state space size for typical boards
