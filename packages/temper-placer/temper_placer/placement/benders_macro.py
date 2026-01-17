"""
Macro Component Definition for Benders Decomposition.

Represents a grouped cluster of components as a single rigid body
for the global placement stage.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

@dataclass
class BendersMacro:
    name: str  # e.g., "Cluster_MCU_Core"
    width_mm: float
    height_mm: float
    component_positions: Dict[str, Tuple[float, float]]  # Relative to center (dx, dy)
    external_nets: List[str]  # Nets connecting to other macros
    hv_nets: List[str]  # HV nets contained or connected
    classification: str # "HV", "LV"
    
    # Global position (assigned by Master Problem)
    x_mm: float = 0.0
    y_mm: float = 0.0
    
    def get_absolute_positions(self) -> Dict[str, Tuple[float, float]]:
        """
        Unpack the macro to absolute board coordinates.
        """
        abs_pos = {}
        for ref, (dx, dy) in self.component_positions.items():
            abs_pos[ref] = (self.x_mm + dx, self.y_mm + dy)
        return abs_pos

def create_macro_from_cluster(cluster_name: str, 
                              local_results: Dict[str, Tuple[float, float]], 
                              width: float, 
                              height: float,
                              input_data: Dict) -> BendersMacro:
    """
    Factory to create a Macro from local optimization results.
    """
    components = {c["ref"]: c for c in input_data["components"]}
    
    # Identify external nets (nets that appear in other clusters would be external)
    # For now, just collect all unique nets
    all_nets = set()
    hv_nets = set()
    classification = "LV"
    
    for ref in local_results.keys():
        c = components[ref]
        nets = c.get("nets", [])
        all_nets.update(nets)
        c_hv = c.get("hv_nets", [])
        hv_nets.update(c_hv)
        if c.get("classification") == "HV":
            classification = "HV"
            
    return BendersMacro(
        name=cluster_name,
        width_mm=width,
        height_mm=height,
        component_positions=local_results,
        external_nets=list(all_nets),
        hv_nets=list(hv_nets),
        classification=classification
    )
