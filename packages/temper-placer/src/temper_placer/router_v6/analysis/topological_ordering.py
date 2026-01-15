from __future__ import annotations
import math
import networkx as nx

class TopologicalOrderer:
    """
    Determines the routing sequence for nets to maximize completion.
    
    Uses a combination of:
    1. Static heuristic scoring (density, pin count)
    2. Topological constraint analysis (dependency graphs)
    """
    
    def compute_order(
        self, 
        nets: dict[str, list[tuple[float, float]]], 
        dependencies: list[tuple[str, str]] | None = None,
        board_centroid: tuple[float, float] | None = None
    ) -> tuple[list[str], list[list[str]]]:
        """
        Compute routing order and identify irreducible conflicts.
        
        Returns:
            (order, strongly_connected_components)
        """
        # 1. Calculate base scores for all nets
        scores = {}
        for net_name, pads in nets.items():
            scores[net_name] = self._calculate_base_score(pads, board_centroid)
            
        # 2. Build Dependency Graph
        G = nx.DiGraph()
        G.add_nodes_from(nets.keys())
        if dependencies:
            for early, late in dependencies:
                if early in nets and late in nets:
                    G.add_edge(early, late)
                    
        # 3. Check for cycles via SCC (Tarjan's equivalent)
        sccs = list(nx.strongly_connected_components(G))
        real_sccs = [list(scc) for scc in sccs if len(scc) > 1]
        
        # 4. Priority-based topological sort
        order = []
        temp_G = G.copy()
        remaining = set(nets.keys())
        
        while remaining:
            candidates = [n for n in remaining if temp_G.in_degree(n) == 0]
            
            if not candidates:
                if not remaining: break
                # Cycle! Break it by picking the highest score node in an SCC
                # Find nodes involved in cycles
                cycle_nodes = set()
                for scc in real_sccs:
                    for node in scc:
                        if node in remaining:
                            cycle_nodes.add(node)
                
                if cycle_nodes:
                    candidates = list(cycle_nodes)
                else:
                    candidates = list(remaining)
                
            best_net = max(candidates, key=lambda n: scores[n])
            
            order.append(best_net)
            remaining.remove(best_net)
            temp_G.remove_node(best_net)
            
        return order, real_sccs

    def detect_conflicts(
        self, 
        nets: dict[str, list[tuple[float, float]]],
        routing_space: any = None
    ) -> list[tuple[str, str]]:
        """
        Determine if order matters between net pairs by checking for intersecting ideal paths.
        """
        from shapely.geometry import LineString
        dependencies = []
        
        # For this experiment, we'll use straight-line approximations for "order matters"
        # In a real tool, we'd use A* on an empty board.
        paths = {}
        for name, pads in nets.items():
            if len(pads) >= 2:
                paths[name] = LineString(pads)
                
        names = list(paths.keys())
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                n1, n2 = names[i], names[j]
                p1, p2 = paths[n1], paths[n2]
                
                if p1.intersects(p2):
                    # Conflict! One must be routed first.
                    # Heuristic: The one with more pins or smaller bbox should go first
                    s1 = self._calculate_base_score(nets[n1])
                    s2 = self._calculate_base_score(nets[n2])
                    
                    if s1 >= s2:
                        dependencies.append((n1, n2))
                    else:
                        dependencies.append((n2, n1))
        return dependencies

    def detect_topological_constraints(self, nets: dict[str, list[tuple[float, float]]]) -> list[tuple[str, str]]:
        """
        Automatically detect topological dependencies.
        Example: If Net A's bounding box is entirely inside Net B's, A should be routed first.
        """
        from shapely.geometry import MultiPoint, Polygon
        
        dependencies = []
        net_hulls = {}
        
        # 1. Compute hulls for all nets
        for name, pads in nets.items():
            if len(pads) >= 2:
                points = MultiPoint(pads)
                # Bounding box or convex hull
                net_hulls[name] = points.convex_hull
                
        # 2. Check for nesting (n^2 but usually nets list is small enough)
        names = list(net_hulls.keys())
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                n1, n2 = names[i], names[j]
                h1, h2 = net_hulls[n1], net_hulls[n2]
                
                # If h1 is inside h2, n1 MUST be routed before n2 to avoid being trapped
                if h2.contains(h1):
                    dependencies.append((n1, n2))
                elif h1.contains(h2):
                    dependencies.append((n2, n1))
                    
        return dependencies

    def _calculate_base_score(self, pads: list[tuple[float, float]], board_centroid: tuple[float, float] | None = None) -> float:
        """
        Calculate a priority score for a net.
        Higher score = Route earlier.
        """
        if not pads:
            return 0.0
            
        num_pins = len(pads)
        
        # Calculate bounding box
        xs = [p[0] for p in pads]
        ys = [p[1] for p in pads]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        width = max_x - min_x
        height = max_y - min_y
        area = width * height
        
        # 1. Density/Complexity Score
        density_score = num_pins / (area + 1.0)
        pin_score = num_pins * 100.0
        
        # 2. Centroid Distance (Radial Priority)
        # Nets near the center should be routed first to avoid being trapped
        center_score = 0.0
        if board_centroid:
            net_center_x = (min_x + max_x) / 2.0
            net_center_y = (min_y + max_y) / 2.0
            dist = math.sqrt((net_center_x - board_centroid[0])**2 + (net_center_y - board_centroid[1])**2)
            # Inverse distance: 100 / (dist + 1)
            center_score = 100.0 / (dist + 1.0)
        
        # Total Score
        return pin_score + density_score + center_score
