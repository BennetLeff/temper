"""
Geometric Nudger - Post-processing optimization for DRC compliance.

Transforms grid-based routing into DRC-clean geometric routing by applying
repulsive forces from DRC violations and moving connectivity nodes.
"""

from dataclasses import dataclass
from typing import Dict, List, Set, Tuple
import math

from temper_placer.routing.constraints.drc_oracle import DRCOracle, Violation
from temper_placer.routing.constraints.geometry import Point
from temper_placer.routing.constraints.spatial_index import Track, Via, Pad, PCBGeometry
from temper_placer.routing.post_processing.forces import calculate_repulsive_force, ForceVector, compute_forces


@dataclass
class Node:
    """A connection point in the routing topology (Track end or Via center)."""
    id: str  # Unique ID
    x: float
    y: float
    fixed: bool = False
    net: str = ""
    
    # List of (geometry_id, endpoint_type) tuples
    # endpoint_type: "start", "end", "center"
    connected_refs: List[Tuple[str, str]] = None
    
    def __post_init__(self):
        if self.connected_refs is None:
            self.connected_refs = []


class GeometricNudger:
    def __init__(self, oracle: DRCOracle):
        self.oracle = oracle
        self.nodes: Dict[str, Node] = {}
        self.node_spatial_index: Dict[Tuple[float, float], str] = {}
        
    def _get_or_create_node(self, x: float, y: float, net: str, fixed: bool = False) -> str:
        """Get existing node ID at (x,y) or create new one."""
        key = (round(x, 4), round(y, 4))
        if key in self.node_spatial_index:
            node_id = self.node_spatial_index[key]
            # If we request a fixed node, upgrade existing to fixed
            if fixed:
                self.nodes[node_id].fixed = True
            return node_id
            
        node_id = f"node_{len(self.nodes)}"
        node = Node(id=node_id, x=x, y=y, net=net, fixed=fixed)
        self.nodes[node_id] = node
        self.node_spatial_index[key] = node_id
        return node_id

    def build_topology(self):
        """Build node graph from DRCOracle geometry."""
        self.nodes.clear()
        self.node_spatial_index.clear()
        
        # Process Tracks
        for track in self.oracle.geometry.tracks:
            # Check if start/end are on pads
            start_fixed = self._is_on_pad(track.start, track.net)
            end_fixed = self._is_on_pad(track.end, track.net)
            
            start_id = self._get_or_create_node(track.start.x, track.start.y, track.net, start_fixed)
            end_id = self._get_or_create_node(track.end.x, track.end.y, track.net, end_fixed)
            
            self.nodes[start_id].connected_refs.append((track.id, "start"))
            self.nodes[end_id].connected_refs.append((track.id, "end"))
            
        # Process Vias
        for via in self.oracle.geometry.vias:
            fixed = self._is_on_pad(via.center, via.net)
            node_id = self._get_or_create_node(via.center.x, via.center.y, via.net, fixed)
            self.nodes[node_id].connected_refs.append((via.id, "center"))

    def _is_on_pad(self, point: Point, net: str) -> bool:
        """Check if a point lies on a pad of the same net."""
        pads = self.oracle.geometry.query_pads_near(point, 0.1)
        for pad in pads:
            if pad.net == net:
                if point.distance_to(pad.center) < pad.radius + 0.05: # Slight tolerance
                    return True
        return False

    def optimize(self, iterations: int = 50, step_size: float = 0.5):
        """Run the nudging optimization loop."""
        self.build_topology()
        
        for i in range(iterations):
            violations = self.oracle.validate_all()
            if not violations:
                print(f"Converged in {i} iterations!")
                break
                
            if i % 10 == 0:
                print(f"Iteration {i}: {len(violations)} violations")

            
            # 1. Aggregate geometry forces
            geom_forces = compute_forces(self.oracle, [v.geometry_a_id for v in violations] + [v.geometry_b_id for v in violations])

            # 2. Distribute forces to Nodes
            node_forces: Dict[str, ForceVector] = {nid: ForceVector.zero() for nid in self.nodes}
            
            for gid, force in geom_forces.items():
                geom = self.oracle.geometry.get_geometry_by_id(gid)
                if not geom:
                    continue
                
                # We need to find which nodes connect to this geom
                # We iterate nodes? No, slow.
                # Better: Iterate nodes and pull force from geom? No.
                # Since we don't have back-pointers from geom to nodes easily without a map,
                # let's look up the nodes based on geom current pos.
                
                if isinstance(geom, Track):
                    start_node = self._get_node_by_pos(geom.start)
                    end_node = self._get_node_by_pos(geom.end)
                    
                    half = ForceVector(force.fx * 0.5, force.fy * 0.5, force.magnitude * 0.5)
                    if start_node:
                        node_forces[start_node.id] = node_forces[start_node.id] + half
                    if end_node:
                        node_forces[end_node.id] = node_forces[end_node.id] + half
                        
                elif isinstance(geom, Via):
                    node = self._get_node_by_pos(geom.center)
                    if node:
                        node_forces[node.id] = node_forces[node.id] + force

            # 3. Move Nodes
            max_move = 0.0
            for node_id, force in node_forces.items():
                node = self.nodes[node_id]
                if node.fixed:
                    continue
                    
                if force.magnitude < 1e-6:
                    continue
                    
                dx = force.fx * step_size
                dy = force.fy * step_size
                move_dist = math.sqrt(dx*dx + dy*dy)
                
                CLAMP = 0.2  # Max 0.2mm per step for stability
                if move_dist > CLAMP:
                    dx *= (CLAMP / move_dist)
                    dy *= (CLAMP / move_dist)
                    move_dist = CLAMP
                
                node.x += dx
                node.y += dy
                max_move = max(max_move, move_dist)
            
            # 4. Update Geometry and Rebuild Index
            self._sync_geometry_from_nodes()
            # Note: _sync clears node_spatial_index, so _get_node_by_pos works for next iter
            self.oracle.geometry.rebuild_index()
            
            if max_move < 0.001:
                print("Converged (movement < tolerance)")
                break

    def _get_node_by_pos(self, pos: Point) -> Node | None:
        key = (round(pos.x, 4), round(pos.y, 4))
        nid = self.node_spatial_index.get(key)
        if nid:
            return self.nodes[nid]
        return None

    def _sync_geometry_from_nodes(self):
        """Update geometry objects processing node positions."""
        self.node_spatial_index.clear()
        
        for node in self.nodes.values():
            # Update spatial index for next lookup
            key = (round(node.x, 4), round(node.y, 4))
            self.node_spatial_index[key] = node.id
            
            for gid, ref_type in node.connected_refs:
                geom = self.oracle.geometry.get_geometry_by_id(gid)
                if not geom:
                    continue
                    
                if isinstance(geom, Track):
                    if ref_type == "start":
                        geom.start = Point(node.x, node.y)
                    elif ref_type == "end":
                        geom.end = Point(node.x, node.y)
                elif isinstance(geom, Via):
                    if ref_type == "center":
                        geom.center = Point(node.x, node.y)
        
