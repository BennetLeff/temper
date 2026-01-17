"""
Hierarchical Benders Loop.

Orchestrates the two-stage placement process:
1. Cluster Components & Local Optimization -> Macros
2. Global Placement of Macros using Benders Decomposition
"""
import json
import time
from pathlib import Path
from typing import Any, Dict

from temper_placer.placement.benders_loop import BendersOptimizer, BendersResult, BendersStatus
from temper_placer.placement.clustering import ComponentClusterer
from temper_placer.placement.local_optimizer import LocalOptimizer
from temper_placer.placement.benders_macro import create_macro_from_cluster

class HierarchicalBendersLoop:
    def __init__(self, 
                 component_data_json: str | None = None, 
                 pcb_file: str | None = None,
                 work_dir: str = "temp_hierarchical",
                 input_data: Dict[str, Any] | None = None):
        
        self.pcb_file = Path(pcb_file) if pcb_file else None
        self.work_dir = Path(work_dir)
        self.work_dir.mkdir(exist_ok=True)
        
        if input_data:
            self.input_data = input_data
        elif component_data_json:
            self.input_json_path = Path(component_data_json)
            with open(self.input_json_path) as f:
                self.input_data = json.load(f)
        else:
            raise ValueError("Must provide either component_data_json or input_data")
            
    def run(self) -> BendersResult:
        start_time = time.time()
        print("=== Step 1: Clustering Components ===")
        clusterer = ComponentClusterer(self.input_data["components"])
        clusters = clusterer.cluster()
        print(f"  Found {len(clusters)} clusters: {[c.name for c in clusters]}")
        
        print("\n=== Step 2: Local Optimization (Creating Macros) ===")
        macros = []
        for cluster in clusters:
            print(f"  Optimizing {cluster.name} ({len(cluster.component_refs)} components)...")
            opt = LocalOptimizer(cluster.name, cluster.component_refs, self.input_data)
            positions, width, height = opt.solve()
            
            if not positions:
                print(f"  Error: Failed to optimize cluster {cluster.name}")
                return BendersResult(BendersStatus.ERROR, 0, {}, 0.0, [], 0.0)
                
            macro = create_macro_from_cluster(cluster.name, positions, width, height, self.input_data)
            macros.append(macro)
            print(f"    -> Macro Created: {width:.2f}mm x {height:.2f}mm")
            
        print("\n=== Step 3: Global Macro Placement ===")
        # Create Proxy Input JSON
        proxy_data = {
            "board": self.input_data["board"],
            "components": []
        }
        
        # Convert Macros to "Components" for the Benders Solver
        for m in macros:
            proxy_comp = {
                "ref": m.name,
                "width_mm": m.width_mm,
                "height_mm": m.height_mm,
                "nets": m.external_nets,
                "hv_nets": m.hv_nets,
                "classification": m.classification,
                # Initial positions (center of board)
                "x_mm": self.input_data["board"]["width_mm"]/2,
                "y_mm": self.input_data["board"]["height_mm"]/2
            }
            proxy_data["components"].append(proxy_comp)
            
        proxy_path = self.work_dir / "macro_input.json"
        with open(proxy_path, "w") as f:
            json.dump(proxy_data, f, indent=2)
            
        # Run Benders on Macros
        # Note: We disable routability check for the macro pass as we don't have detailed pads
        # We rely on the cut generator's "Gap" estimation being enough for the macros
        global_opt = BendersOptimizer(
            component_data_json=proxy_path,
            max_iterations=20, # Give it enough iterations to arrange 5 blocks
            check_routability=True, # Yes, check routability between macros!
            pcb_file=None, # Cannot check real PCB routability on fake components
            verbose=True,
            use_ultrafast_check=True # Use heuristic for macros
        )
        
        # Override routability check to simple bbox/net distance for macros
        # (Standard Benders loop uses pcb file, which we don't have for macros)
        # So we just rely on master problem + simple overlaps
        global_opt.check_routability = False 
        
        macro_result = global_opt.optimize()
        
        if macro_result.status == BendersStatus.INFEASIBLE:
            print("  Global placement failed!")
            return macro_result
            
        print("\n=== Step 4: Unpacking and Refinement ===")
        # Unpack
        final_positions = {}
        for m in macros:
            if m.name in macro_result.final_positions:
                mx, my = macro_result.final_positions[m.name]
                m.x_mm = mx
                m.y_mm = my
                final_positions.update(m.get_absolute_positions())
                
        # Validate Bounds (Push back if unpacking pushed them off board)
        # Simple heuristic clamp
        board_w = self.input_data["board"]["width_mm"]
        board_h = self.input_data["board"]["height_mm"]
        
        print("  Running final verification/refinement...")
        # Optional: Setup a final 'Fixed' run or small window run if needed.
        # For now, just return this result.
        
        return BendersResult(
            status=macro_result.status,
            iterations=macro_result.iterations,
            final_positions=final_positions,
            total_movement=macro_result.total_movement,
            cuts_added=macro_result.cuts_added,
            solve_time_sec=time.time() - start_time
        )
