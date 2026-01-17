"""
Local Optimizer for Component Clusters.

Optimizes the placement of a single cluster of components to minimize
wirelength and area, creating a compact 'Macro'.
"""
from ortools.linear_solver import pywraplp
from typing import List, Dict, Tuple, Any

class LocalOptimizer:
    def __init__(self, cluster_name: str, component_refs: List[str], input_data: Dict):
        self.name = cluster_name
        self.refs = component_refs
        self.data = input_data
        self.components = {c["ref"]: c for c in input_data["components"] if c["ref"] in self.refs}
        
    def solve(self, time_limit_sec: float = 5.0) -> Tuple[Dict[str, Tuple[float, float]], float, float]:
        """
        Solve local placement.
        Returns:
            positions: {ref: (x, y)} relative to center
            width: bounding box width
            height: bounding box height
        """
        solver = pywraplp.Solver.CreateSolver("SCIP")
        if not solver:
            raise RuntimeError("SCIP solver unavailable")
            
        solver.SetTimeLimit(int(time_limit_sec * 1000))
        
        # Variables: x, y for each component
        x = {}
        y = {}
        min_clearance = 0.5 # mm tight packing
        
        # Calculate rough area to set bounds
        total_area = sum(c["width_mm"] * c["height_mm"] for c in self.components.values())
        side = max(20.0, (total_area ** 0.5) * 2) # Heuristic bound
        
        for ref in self.refs:
            x[ref] = solver.IntVar(-int(side*100), int(side*100), f"x_{ref}")
            y[ref] = solver.IntVar(-int(side*100), int(side*100), f"y_{ref}")
            
        # Constraints: Non-overlap
        sorted_refs = sorted(self.refs)
        for i in range(len(sorted_refs)):
            for j in range(i + 1, len(sorted_refs)):
                c1_ref = sorted_refs[i]
                c2_ref = sorted_refs[j]
                c1 = self.components[c1_ref]
                c2 = self.components[c2_ref]
                
                # Big-M for non-overlap
                # Separate in X OR Y
                pins1 = len(c1.get("nets", []))
                pins2 = len(c2.get("nets", []))
                max_pins = max(pins1, pins2)
                padding = 2.0 + (max_pins / 10.0) * 1.0
                padding = min(5.0, padding)
                
                # print(f"DEBUG: Padding {c1_ref}-{c2_ref} = {padding:.2f}mm")
                
                w_sum = (c1["width_mm"] + c2["width_mm"]) / 2 + padding
                h_sum = (c1["height_mm"] + c2["height_mm"]) / 2 + padding
                
                ws_int = int(w_sum * 100)
                hs_int = int(h_sum * 100)
                
                b1 = solver.BoolVar(f"b_left_{c1_ref}_{c2_ref}")
                b2 = solver.BoolVar(f"b_right_{c1_ref}_{c2_ref}")
                b3 = solver.BoolVar(f"b_below_{c1_ref}_{c2_ref}")
                b4 = solver.BoolVar(f"b_above_{c1_ref}_{c2_ref}")
                
                M = 1000000
                solver.Add(x[c1_ref] + ws_int <= x[c2_ref] + M * (1 - b1))
                solver.Add(x[c2_ref] + ws_int <= x[c1_ref] + M * (1 - b2))
                solver.Add(y[c1_ref] + hs_int <= y[c2_ref] + M * (1 - b3))
                solver.Add(y[c2_ref] + hs_int <= y[c1_ref] + M * (1 - b4))
                
                solver.Add(b1 + b2 + b3 + b4 >= 1)

        # Objective: Minimise HPWL of internal nets + Bounding Box
        # Identify internal nets
        # For MVP: Just minimize sum of distances between all components in cluster
        # + Minimize Max X/Y (Area)
        
        obj_expr = 0
        
        # Pull towards center (minimize coordinate magnitude)
        for ref in self.refs:
            # Absolute value trick: z >= x, z >= -x
            abs_x = solver.IntVar(0, int(side*100), f"abs_x_{ref}")
            abs_y = solver.IntVar(0, int(side*100), f"abs_y_{ref}")
            solver.Add(abs_x >= x[ref])
            solver.Add(abs_x >= -x[ref])
            solver.Add(abs_y >= y[ref])
            solver.Add(abs_y >= -y[ref])
            
            obj_expr += abs_x + abs_y
            
        solver.Minimize(obj_expr)
        
        status = solver.Solve()
        
        results = {}
        min_x, max_x = float('inf'), float('-inf')
        min_y, max_y = float('inf'), float('-inf')
        
        if status in [pywraplp.Solver.OPTIMAL, pywraplp.Solver.FEASIBLE]:
            for ref in self.refs:
                px = x[ref].solution_value() / 100.0
                py = y[ref].solution_value() / 100.0
                results[ref] = (px, py)
                
                c = self.components[ref]
                min_x = min(min_x, px - c["width_mm"]/2)
                max_x = max(max_x, px + c["width_mm"]/2)
                min_y = min(min_y, py - c["height_mm"]/2)
                max_y = max(max_y, py + c["height_mm"]/2)
                
            width = max_x - min_x
            height = max_y - min_y
            
            # Recenter results
            cx = (min_x + max_x) / 2
            cy = (min_y + max_y) / 2
            for ref in results:
                rx, ry = results[ref]
                results[ref] = (rx - cx, ry - cy)
                
            return results, width, height
        else:
            print(f"Cluster {self.name} solve failed: {status}")
            return {}, 0, 0
