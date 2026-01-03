    def find_path_diff_pair(
        self,
        net_pos: str,
        net_neg: str,
        start_pos: tuple[float, float],
        end_pos: tuple[float, float],
        start_neg: tuple[float, float],
        end_neg: tuple[float, float],
        spacing_mm: float = 0.2,
        coupling_tolerance_mm: float = 0.5,
        p_scale: float = 1.0,
        enable_length_matching: bool = True,
        serpentine_params: "SerpentineParams | None" = None,
    ) -> tuple[RoutePath, RoutePath]:
        """Route a differential pair using Dual-Front A* search.

        This implements joint state space pathfinding where both traces are
        routed simultaneously to maintain coupling.

        Args:
            net_pos: Positive net name (e.g., 'USB_D+')
            net_neg: Negative net name (e.g., 'USB_D-')
            start_pos: Starting position (x,y) for positive net in mm
            end_pos: Ending position (x,y) for positive net in mm
            start_neg: Starting position (x,y) for negative net in mm
            end_neg: Ending position (x,y) for negative net in mm
            spacing_mm: Nominal gap between traces
            coupling_tolerance_mm: Maximum allowed deviation from spacing
            p_scale: Congestion scaling factor
            enable_length_matching: Apply serpentine insertion to equalize lengths
            serpentine_params: Configuration for meander insertion (uses defaults if None)

        Returns:
            Tuple of (path_pos, path_neg) RoutePath objects
        """
        # Convert world coordinates to grid cells
        sx_pos, sy_pos = self._world_to_grid(*start_pos)
        ex_pos, ey_pos = self._world_to_grid(*end_pos)
        sx_neg, sy_neg = self._world_to_grid(*start_neg)
        ex_neg, ey_neg = self._world_to_grid(*end_neg)

        # Start on layer 0 for both
        start_state = DiffPairCell(
            pos=GridCell(sx_pos, sy_pos, 0),
            neg=GridCell(sx_neg, sy_neg, 0)
        )
        goal_pos = GridCell(ex_pos, ey_pos, 0)
        goal_neg = GridCell(ex_neg, ey_neg, 0)

        # Prepare cost arrays for fast access
        self._prepare_cost_arrays()

        # A* data structures
        open_set: list[tuple[float, DiffPairCell]] = []
        heapq.heappush(open_set, (0.0, start_state))
        
        came_from: dict[DiffPairCell, DiffPairCell] = {}
        g_score: dict[DiffPairCell, float] = {start_state: 0.0}
        
        # Heuristic: max of individual Manhattan distances
        def h(state: DiffPairCell) -> float:
            return max(
                self._heuristic(state.pos, goal_pos),
                self._heuristic(state.neg, goal_neg)
            )
        
        f_score: dict[DiffPairCell, float] = {start_state: h(start_state)}
        visited = set()

        # Coupling penalty weight
        coupling_weight = 10.0
        spacing_cells = spacing_mm / self.cell_size

        # Helper: Generate valid neighbor pairs
        def get_diff_pair_neighbors(state: DiffPairCell) -> list[DiffPairCell]:
            """Generate neighbor states maintaining coupling constraints."""
            neighbors = []
            
            # Movement directions: N, S, E, W, same layer transitions
            moves = [(0, 1), (0, -1), (1, 0), (-1, 0), (0, 0)]
            
            # Both traces can move independently but must maintain spacing
            for dx_pos, dy_pos in moves:
                for dx_neg, dy_neg in moves:
                    # Skip if both stationary
                    if dx_pos == 0 and dy_pos == 0 and dx_neg == 0 and dy_neg == 0:
                        continue
                    
                    new_pos = GridCell(
                        state.pos.x + dx_pos,
                        state.pos.y + dy_pos,
                        state.pos.layer
                    )
                    new_neg = GridCell(
                        state.neg.x + dx_neg,
                        state.neg.y + dy_neg,
                        state.neg.layer
                    )
                    
                    # Bounds check
                    if not (0 <= new_pos.x < self.grid_size[0] and 
                           0 <= new_pos.y < self.grid_size[1]):
                        continue
                    if not (0 <= new_neg.x < self.grid_size[0] and
                           0 <= new_neg.y < self.grid_size[1]):
                        continue
                    
                    # Check spacing constraint
                    dx = new_pos.x - new_neg.x
                    dy = new_pos.y - new_neg.y
                    dist_cells = math.sqrt(dx*dx + dy*dy)
                    deviation = abs(dist_cells - spacing_cells)
                    
                    # Prune states that violate coupling tolerance
                    if deviation * self.cell_size > coupling_tolerance_mm:
                        continue
                    
                    new_state = DiffPairCell(pos=new_pos, neg=new_neg)
                    neighbors.append(new_state)
            
            return neighbors

        # Dual-Front A* search
        iterations = 0
        max_iterations = 100000
        
        while open_set and iterations < max_iterations:
            iterations += 1
            
            current_f, current = heapq.heappop(open_set)
            
            # Goal check: both traces reached their targets
            if current.pos == goal_pos and current.neg == goal_neg:
                # Reconstruct paths
                path_pos_cells = []
                path_neg_cells = []
                state = current
                
                while state in came_from:
                    path_pos_cells.append(state.pos)
                    path_neg_cells.append(state.neg)
                    state = came_from[state]
                
                path_pos_cells.append(start_state.pos)
                path_neg_cells.append(start_state.neg)
                path_pos_cells.reverse()
                path_neg_cells.reverse()
                
                # Clear cost arrays
                self._clear_cost_arrays()
                
                # Calculate path metrics
                via_count_pos = sum(1 for i in range(len(path_pos_cells)-1) 
                                   if path_pos_cells[i].layer != path_pos_cells[i+1].layer)
                via_count_neg = sum(1 for i in range(len(path_neg_cells)-1)
                                   if path_neg_cells[i].layer != path_neg_cells[i+1].layer)
                
                length_pos = len(path_pos_cells) * self.cell_size
                length_neg = len(path_neg_cells) * self.cell_size
                
                path_pos = RoutePath(
                    net=net_pos,
                    cells=path_pos_cells,
                    length=length_pos,
                    via_count=via_count_pos,
                    success=True
                )
                path_neg = RoutePath(
                    net=net_neg,
                    cells=path_neg_cells,
                    length=length_neg,
                    via_count=via_count_neg,
                    success=True
                )
                
                # Apply length matching if enabled
                if enable_length_matching:
                    from temper_placer.routing.post_processing.length_matcher import (
                        LengthMatcher,
                        SerpentineParams,
                    )
                    
                    matcher = LengthMatcher()
                    params = serpentine_params or SerpentineParams()
                    path_pos, path_neg = matcher.match_differential_pair_lengths(
                        path_pos, path_neg, params
                    )
                
                logger.info(f"Differential pair {net_pos}/{net_neg} routed successfully "
                          f"({iterations} iterations, {len(path_pos_cells)} cells)")
                return path_pos, path_neg
            
            if current in visited:
                continue
            visited.add(current)
            
            # Explore neighbors
            for neighbor in get_diff_pair_neighbors(current):
                if neighbor in visited:
                    continue
                
                # Calculate cost for both traces
                cost_pos = self._get_neighbor_cost(current.pos, neighbor.pos, p_scale=p_scale)
                cost_neg = self._get_neighbor_cost(current.neg, neighbor.neg, p_scale=p_scale)
                
                # Check if either path is blocked
                if cost_pos >= 1e9 or cost_neg >= 1e9:
                    continue
                
                # Coupling penalty: penalize deviation from nominal spacing
                dx = neighbor.pos.x - neighbor.neg.x
                dy = neighbor.pos.y - neighbor.neg.y
                actual_spacing = math.sqrt(dx*dx + dy*dy) * self.cell_size
                coupling_penalty = coupling_weight * abs(actual_spacing - spacing_mm)
                
                # Total cost: sum of individual costs + coupling penalty
                tentative_g = g_score[current] + cost_pos + cost_neg + coupling_penalty
                
                if neighbor not in g_score or tentative_g < g_score[neighbor]:
                    came_from[neighbor] = current
                    g_score[neighbor] = tentative_g
                    f = tentative_g + h(neighbor)
                    f_score[neighbor] = f
                    heapq.heappush(open_set, (f, neighbor))
        
        # Failed to route
        self._clear_cost_arrays()
        
        failure_reason = "max iterations" if iterations >= max_iterations else "no path found"
        logger.warning(f"Differential pair {net_pos}/{net_neg} failed: {failure_reason}")
        
        path_pos = RoutePath(net=net_pos, cells=[], length=0, via_count=0, 
                            success=False, failure_reason=failure_reason)
        path_neg = RoutePath(net=net_neg, cells=[], length=0, via_count=0,
                            success=False, failure_reason=failure_reason)
        
        return path_pos, path_neg
