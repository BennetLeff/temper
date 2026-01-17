"""
Component Clustering for Hierarchical Placement.

Groups components into logical modules based on connectivity and classification.
"""
from dataclasses import dataclass
from typing import List, Dict, Set, Any

@dataclass
class Cluster:
    name: str
    seed_ref: str
    component_refs: List[str]
    classification: str  # "HV", "LV", "MIXED"

class ComponentClusterer:
    """
    Groups components into functional clusters.
    """
    def __init__(self, components_data: List[Dict[str, Any]]):
        self.components = {c["ref"]: c for c in components_data}
        self.adj = self._build_adjacency()
        
    def _build_adjacency(self) -> Dict[str, Set[str]]:
        """Build component adjacency graph from nets."""
        adj = {ref: set() for ref in self.components}
        
        # Build map of net -> components
        net_map = {}
        for ref, data in self.components.items():
            for net in data.get("nets", []):
                # Ignore power/ground for clustering purposes (too highly connected)
                if net in ["GND", "PGND", "CGND", "+3V3", "+5V", "+15V"]:
                    continue
                if net not in net_map:
                    net_map[net] = []
                net_map[net].append(ref)
                
        # Connect components sharing a signal net
        for refs in net_map.values():
            for i in range(len(refs)):
                for j in range(i + 1, len(refs)):
                    adj[refs[i]].add(refs[j])
                    adj[refs[j]].add(refs[i])
                    
        return adj

    def cluster(self) -> List[Cluster]:
        """Run clustering algorithm."""
        clusters = []
        assigned = set()
        
        # 1. Define Seeds manually (for robust MVP)
        seeds = [
            ("HV_Power", "Q1", ["Q2", "J_AC_IN", "D1", "D2", "C_BUS1", "C_BUS2", "J_COIL"]),
            ("Gate_Drive", "U_GATE", []),
            ("MCU_Core", "U_MCU", ["J_USB", "J_DEBUG"]),
            ("Analog", "U_CT", ["U_OPAMP_CT", "MAX31865", "J_NTC"]),
            ("LV_Power", "U_BUCK", ["U_LDO_5V", "U_LDO_3V3"]),
        ]
        
        for name, seed_ref, forced_members in seeds:
            if seed_ref not in self.components:
                continue
                
            members = [seed_ref]
            assigned.add(seed_ref)
            
            # Add forced members
            for m in forced_members:
                if m in self.components and m not in assigned:
                    members.append(m)
                    assigned.add(m)
            
            # Greedy expansion: Absorb unassigned neighbors (Passives priority)
            # Iterate multiple times to catch chains
            changed = True
            while changed:
                changed = False
                current_members = list(members) # Snapshot
                for member in current_members:
                    for neighbor in self.adj[member]:
                        if neighbor not in assigned:
                            # Heuristic: Prefer absorbing small passives (R, C, L, D)
                            is_passive = neighbor.startswith(("R", "C", "L", "D", "JP", "TP"))
                            # Heuristic: Also absorb if it strongly belongs to the cluster
                            
                            if is_passive:
                                members.append(neighbor)
                                assigned.add(neighbor)
                                changed = True
            
            # Determine classification
            cls = "LV"
            for m in members:
                if self.components[m].get("classification") == "HV":
                    cls = "HV"
                    break
            
            clusters.append(Cluster(name, seed_ref, members, cls))
            
        # Handle leftovers
        leftovers = [r for r in self.components if r not in assigned]
        if leftovers:
            # Assign leftovers to nearest cluster or create Misc
            # For simplicity MVP, create Misc
            clusters.append(Cluster("Misc", leftovers[0], leftovers, "LV"))
            
        return clusters
