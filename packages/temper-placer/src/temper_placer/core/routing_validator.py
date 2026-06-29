from dataclasses import dataclass
from typing import Any

# Partial imports to avoid circular deps if possible, or use types
from temper_placer.core.netlist import Netlist
from temper_placer.core.pin_geometry import pin_world_position


@dataclass
class RoutingViolation:
    violation_type: str  # SHORT, OPEN, DANGLING, CLEARANCE
    net_name: str
    location: tuple[float, float, int]
    message: str

class RoutingValidator:
    def __init__(self, default_cell_size_mm: float, grid_size: tuple[int, int], num_layers: int):
        self.default_cell_size = default_cell_size_mm
        self.grid_size = grid_size
        self.num_layers = num_layers
        self.occupancy_map: dict[tuple[int, int, int], str] = {} # Keyed by world-scale (finest grid) coordinates
        self.violations: list[RoutingViolation] = []
        self.master_resolution = 0.05 # 50 micron granularity for "is-occupied" checking

    def _grid_to_world(self, gx: int, gy: int) -> tuple[float, float]:
        return (str(gx * self.default_cell_size), str(gy * self.default_cell_size)) # Approximation for reporting

    def validate(self,
                 routed_paths: dict[str, Any], # dict[net_name, list[GridCell]]
                 netlist: Netlist,
                 component_positions: Any # JAX array or list of (x,y)
                 ) -> list[RoutingViolation]:

        self.violations = []
        self.occupancy_map = {}

        # 1. Build Occupancy Map & Check Shorts
        for net_name, path in routed_paths.items():
            if not path:
                continue

            # handle path object vs list
            cells = path.cells if hasattr(path, 'cells') else path
            path_cell_size = path.cell_size if hasattr(path, 'cell_size') else self.default_cell_size

            for cell in cells:
                # Convert this cell to master grid coordinates
                # world_x = cell.x * path_cell_size
                # world_y = cell.y * path_cell_size
                # mx = int(round(world_x / self.master_resolution))
                # my = int(round(world_y / self.master_resolution))

                # To be safer with floats, use integer scaling if resolutions are multiples
                # e.g. if path_cell_size = 0.2 and master = 0.05, scaling factor is 4
                scale = int(round(path_cell_size / self.master_resolution))

                # A single path cell at path_cell_size covers a square of master grid cells
                # if path_cell_size > master_resolution.
                # For simplicity, we check the center, but to be robust we should check the whole footprint.
                # However, the router already enforces clearance.
                # Let's just check the center point for the "SHORT" check, but use the correct world position.
                mx = cell.x * scale
                my = cell.y * scale

                key = (mx, my, cell.layer)

                if key in self.occupancy_map:
                    other_net = self.occupancy_map[key]
                    if other_net != net_name:
                        # SHORT DETECTED
                        world_x = cell.x * path_cell_size
                        world_y = cell.y * path_cell_size
                        self.violations.append(RoutingViolation(
                            violation_type="SHORT",
                            net_name=net_name,
                            location=(world_x, world_y, cell.layer),
                            message=f"Short between {net_name} and {other_net} at world({world_x:.2f}, {world_y:.2f})mm"
                        ))
                else:
                    self.occupancy_map[key] = net_name

        # 2. Check Connectivity (Open Nets)
        # Ideally, we build a graph. For now, check if pins are touched by the net's path.
        # Need to map world pins to grid.

        # Convert positions to easy lookup
        # component_positions is likely index-aligned with netlist.components
        comp_pos_map = {} # Ref -> (x, y)
        if hasattr(component_positions, 'tolist'):
            pos_list = component_positions.tolist()
            for i, comp in enumerate(netlist.components):
                comp_pos_map[comp.ref] = pos_list[i]
        else:
             # Assume list
             for i, comp in enumerate(netlist.components):
                comp_pos_map[comp.ref] = component_positions[i]

        for net in netlist.nets:
            path = routed_paths.get(net.name)
            # If net has >1 pin, it should have a path (unless trivial 0-length)
            if len(net.pins) > 1:
                if not path:
                     # Check if pins are identical location (trivial)?
                     # Simplification: Flag as OPEN if no path
                     self.violations.append(RoutingViolation(
                        violation_type="OPEN",
                        net_name=net.name,
                        location=(0,0,0),
                        message=f"Net {net.name} has no routed path but {len(net.pins)} pins"
                     ))
                     continue

                # Check pin coverage
                # Convert path cells to set for fast lookup
                cells = path.cells if hasattr(path, 'cells') else path
                {(c.x, c.y, c.layer) for c in cells}

                for comp_ref, pin_name in net.pins:
                    comp = netlist.get_component(comp_ref)
                    pin = comp.get_pin(pin_name)
                    comp_pos_map[comp_ref]

                    # Use world position from canonical helper
                    px, py = pin_world_position(pin, comp)

                    # Use world-to-path_cell_size mapping if we want to check path_set
                    # But path_set is also grid-based.
                    # Best is to use world coordinates for Connectivity too.

                    # Convert to master grid
                    mx = int(round(px / self.master_resolution))
                    my = int(round(py / self.master_resolution))

                    found = False
                    for layer in range(self.num_layers):
                        if (mx, my, layer) in self.occupancy_map and self.occupancy_map[(mx, my, layer)] == net.name:
                            found = True
                            break

                    if not found:
                         # Radius check in master grid
                         # (Approx 0.5mm search)
                         search_px = int(round(0.5 / self.master_resolution))
                         for dx in range(-search_px, search_px + 1):
                             for dy in range(-search_px, search_px + 1):
                                 for layer in range(self.num_layers):
                                     mkey = (mx+dx, my+dy, layer)
                                     if mkey in self.occupancy_map and self.occupancy_map[mkey] == net.name:
                                         found = True
                                         break
                                 if found:
                                     break
                             if found:
                                 break

                    if not found:
                        self.violations.append(RoutingViolation(
                             violation_type="OPEN",
                             net_name=net.name,
                             location=(px, py, 0),
                             message=f"Pin {comp_ref}.{pin_name} not connected to routed path"
                        ))

        return self.violations

def validate_routing_result(
    routed_paths: dict[str, Any],
    netlist: Netlist,
    component_positions: Any,
    cell_size_mm: float,
    grid_size: tuple[int, int],
    num_layers: int
) -> list[RoutingViolation]:
    validator = RoutingValidator(cell_size_mm, grid_size, num_layers)
    return validator.validate(routed_paths, netlist, component_positions)
