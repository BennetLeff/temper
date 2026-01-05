import logging
from dataclasses import dataclass, replace
from typing import List, Tuple, Set, Dict, Any

from ..state import BoardState
from .base import Stage
from ...routing.constraints.geometry import Point
from ...routing.constraints.spatial_index import Track, Via, Pad
from ...routing.topology import UnionFind

logger = logging.getLogger(__name__)

@dataclass
class ConnectivityViolation:
    """Represents a connectivity error on the PCB."""
    type: str  # "orphan_island", "dangling_track", "unconnected_pad"
    net: str
    location: Point
    description: str

class ConnectivityValidationError(Exception):
    """Raised when connectivity violations exceed configured thresholds."""
    pass

class ConnectivityValidationStage(Stage):
    """
    Validates net connectivity, detecting unconnected pads, 
    dangling tracks, and isolated copper islands.
    """

    def __init__(self, fail_on_violations: bool = False):
        self.fail_on_violations = fail_on_violations

    @property
    def name(self) -> str:
        return "connectivity_validation"

    def run(self, state: BoardState) -> BoardState:
        if not state.drc_oracle:
            logger.warning("No DRCOracle in state, skipping connectivity validation")
            return state

        geom = state.drc_oracle.geometry
        violations = []

        # Group all geometry by net
        nets: Dict[str, Dict[str, List[Any]]] = {}
        
        for pad in geom.pads:
            if pad.net not in nets: nets[pad.net] = {"pads": [], "tracks": [], "vias": []}
            nets[pad.net]["pads"].append(pad)
            
        for track in geom.tracks:
            if track.net not in nets: nets[track.net] = {"pads": [], "tracks": [], "vias": []}
            nets[track.net]["tracks"].append(track)
            
        for via in geom.vias:
            if via.net not in nets: nets[via.net] = {"pads": [], "tracks": [], "vias": []}
            nets[via.net]["vias"].append(via)

        # Validate each net
        for net_name, net_items in nets.items():
            if not net_name or net_name == "NoNet":
                continue
            
            net_violations = self._validate_net_connectivity(net_name, net_items)
            violations.extend(net_violations)

        # Log summary
        self._log_summary(violations)

        if self.fail_on_violations and violations:
            raise ConnectivityValidationError(f"{len(violations)} connectivity violations found")

        return replace(state, connectivity_violations=tuple(violations))

    def _validate_net_connectivity(self, net_name: str, items: Dict[str, List[Any]]) -> List[ConnectivityViolation]:
        pads = items["pads"]
        tracks = items["tracks"]
        vias = items["vias"]
        
        all_items = pads + tracks + vias
        if not all_items:
            return []

        # Map items to integer IDs for UnionFind
        item_to_id = {id(item): i for i, item in enumerate(all_items)}
        id_to_item = {i: item for i, item in enumerate(all_items)}
        
        uf = UnionFind()
        for i in range(len(all_items)):
            uf.find(i)

        # Build connectivity graph
        # This is O(N^2) currently, can be optimized with spatial indexing if needed
        # but for a single net it's usually small.
        
        # 1. Check Track-Track connectivity
        for i, t1 in enumerate(tracks):
            for j, t2 in enumerate(tracks[i+1:], i+1):
                if self._tracks_touch(t1, t2):
                    uf.union(item_to_id[id(t1)], item_to_id[id(t2)])
        
        # 2. Check Track-Via connectivity
        for t in tracks:
            for v in vias:
                if self._track_touches_via(t, v):
                    uf.union(item_to_id[id(t)], item_to_id[id(v)])

        # 3. Check Track-Pad connectivity
        for t in tracks:
            for p in pads:
                if self._track_touches_pad(t, p):
                    uf.union(item_to_id[id(t)], item_to_id[id(p)])

        # 4. Check Via-Pad connectivity
        for v in vias:
            for p in pads:
                if self._via_touches_pad(v, p):
                    uf.union(item_to_id[id(v)], item_to_id[id(p)])
        
        # 5. Check Via-Via connectivity (stacking)
        for i, v1 in enumerate(vias):
            for j, v2 in enumerate(vias[i+1:], i+1):
                if v1.center == v2.center:
                    uf.union(item_to_id[id(v1)], item_to_id[id(v2)])

        violations = []
        
        # Find components and identify those with/without pads
        components = uf.get_components()
        components_with_pads = {}
        components_without_pads = {}
        
        for root, members in components.items():
            island_pads = [id_to_item[m] for m in members if isinstance(id_to_item[m], Pad)]
            if island_pads:
                components_with_pads[root] = island_pads
            else:
                components_without_pads[root] = members

        # 1. Report all copper islands with no pads as orphans
        for root, members in components_without_pads.items():
            rep_item = id_to_item[members[0]]
            loc = self._get_item_location(rep_item)
            violations.append(ConnectivityViolation(
                type="orphan_island",
                net=net_name,
                location=loc,
                description=f"Isolated copper island for net {net_name} with no pads"
            ))

        # 2. If there are multiple islands with pads, report them as unconnected
        if len(components_with_pads) > 1:
            # Sort roots to be deterministic, keep the one with most pads as "primary"
            sorted_roots = sorted(
                components_with_pads.keys(), 
                key=lambda r: (len(components_with_pads[r]), r), 
                reverse=True
            )
            for root in sorted_roots[1:]:
                island_pads = components_with_pads[root]
                loc = island_pads[0].center
                violations.append(ConnectivityViolation(
                    type="unconnected_pad",
                    net=net_name,
                    location=loc,
                    description=f"Pad {island_pads[0].id} and {len(island_pads)-1} others are not connected to the main group of net {net_name}"
                ))
        elif len(components_with_pads) == 0 and (tracks or vias):
            # Already handled by components_without_pads, but just to be sure we don't miss net-level error
            pass

        # Check for dangling tracks
        # A track is dangling if at least one of its endpoints is not connected to anything else
        # in the same net (pad, via, or another track).
        # Note: A single track connecting two pads is NOT dangling.
        
        # To find dangling tracks, we need to check degree of connectivity at endpoints
        for t in tracks:
            start_connected = False
            end_connected = False
            
            # Check start point
            for other in all_items:
                if other is t: continue
                if self._point_touches_item(t.start, other, exclude_track=t):
                    start_connected = True
                    break
            
            # Check end point
            for other in all_items:
                if other is t: continue
                if self._point_touches_item(t.end, other, exclude_track=t):
                    end_connected = True
                    break
                    
            if not start_connected or not end_connected:
                # One end is open. 
                # Exception: if it's the ONLY track and it connects two pads? 
                # No, if it connects to a pad, _point_touches_item would be true.
                violations.append(ConnectivityViolation(
                    type="dangling_track",
                    net=net_name,
                    location=t.start if not start_connected else t.end,
                    description=f"Track segment in net {net_name} has a dangling endpoint"
                ))

        return violations

    def _tracks_touch(self, t1: Track, t2: Track) -> bool:
        if t1.layer != t2.layer: return False
        # Exact endpoint match for grid router
        return (t1.start == t2.start or t1.start == t2.end or 
                t1.end == t2.start or t1.end == t2.end)

    def _track_touches_via(self, t: Track, v: Via) -> bool:
        # Vias are on all layers in this simplified model or we check them
        return t.start == v.center or t.end == v.center

    def _track_touches_pad(self, t: Track, p: Pad) -> bool:
        if t.layer != p.layer: return False
        # Check if either endpoint is inside the pad
        from ...routing.constraints.geometry import point_to_rotated_rect_distance
        return (point_to_rotated_rect_distance(t.start, p.rot_rect) <= 1e-4 or 
                point_to_rotated_rect_distance(t.end, p.rot_rect) <= 1e-4)

    def _via_touches_pad(self, v: Via, p: Pad) -> bool:
        # Pad is on a specific layer, Via connects layers. 
        # Typically vias connect all layers or a range.
        from ...routing.constraints.geometry import point_to_rotated_rect_distance
        return point_to_rotated_rect_distance(v.center, p.rot_rect) <= 1e-4

    def _point_touches_item(self, pt: Point, item: Any, exclude_track: Track = None) -> bool:
        if isinstance(item, Track):
            if exclude_track and item.layer != exclude_track.layer: return False
            return pt == item.start or pt == item.end
        if isinstance(item, Via):
            return pt == item.center
        if isinstance(item, Pad):
            if exclude_track and item.layer != exclude_track.layer: return False
            from ...routing.constraints.geometry import point_to_rotated_rect_distance
            return point_to_rotated_rect_distance(pt, item.rot_rect) <= 1e-4
        return False

    def _get_item_location(self, item: Any) -> Point:
        if hasattr(item, "center"): return item.center
        if hasattr(item, "start"): return item.start
        return Point(0, 0)

    def _log_summary(self, violations: List[ConnectivityViolation]):
        if not violations:
            logger.info("Connectivity validation passed: 0 violations")
            return

        by_type = {}
        for v in violations:
            by_type[v.type] = by_type.get(v.type, 0) + 1

        logger.warning(f"Connectivity validation: {len(violations)} violations")
        for vtype, count in sorted(by_type.items(), key=lambda x: -x[1]):
            logger.warning(f"  {vtype}: {count}")
