from dataclasses import dataclass
from typing import Any

# Partial imports to avoid circular deps if possible, or use types
from temper_placer.core.netlist import Netlist


@dataclass
class RoutingViolation:
    violation_type: str  # SHORT, OPEN, DANGLING, CLEARANCE
    net_name: str
    location: tuple[float, float, int]
    message: str

class RoutingValidator:
    def __init__(self, cell_size_mm: float, grid_size: tuple[int, int], num_layers: int):
        self.cell_size = cell_size_mm
        self.grid_size = grid_size
        self.num_layers = num_layers
        self.occupancy_map: dict[tuple[int, int, int], str] = {}
        self.violations: list[RoutingViolation] = []

    def _grid_to_world(self, gx: int, gy: int) -> tuple[float, float]:
        return (str(gx * self.cell_size), str(gy * self.cell_size)) # Approximation for reporting

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

            for cell in cells:
                # cell has x, y, layer
                key = (cell.x, cell.y, cell.layer)

                if key in self.occupancy_map:
                    other_net = self.occupancy_map[key]
                    if other_net != net_name:
                        # SHORT DETECTED
                        self.violations.append(RoutingViolation(
                            violation_type="SHORT",
                            net_name=net_name,
                            location=(cell.x * self.cell_size, cell.y * self.cell_size, cell.layer),
                            message=f"Short between {net_name} and {other_net} at ({cell.x}, {cell.y})"
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
                path_set = {(c.x, c.y, c.layer) for c in cells}

                for comp_ref, pin_name in net.pins:
                    comp = netlist.get_component(comp_ref)
                    pin = comp.get_pin(pin_name)
                    c_pos = comp_pos_map[comp_ref]

                    # Assume rotation 0 for now as per loop assumptions
                    px, py = pin.absolute_position(c_pos, 0.0)
                    gx = int(round(px / self.cell_size))
                    gy = int(round(py / self.cell_size))

                    # Check if (gx, gy) on ANY layer is in path
                    # (Pins usually connect to all layers or specific ones? THT=All, SMD=Top/Bot)
                    # Simplified: Check Top or Bottom or match specific
                    found = False
                    for l in range(self.num_layers):
                        if (gx, gy, l) in path_set:
                            found = True
                            break
                    # Also check neighbors if strictness fails? (Pin mapping drift)
                    if not found:
                         # Radius check
                         for dx in [-1, 0, 1]:
                             for dy in [-1, 0, 1]:
                                 for l in range(self.num_layers):
                                     if (gx+dx, gy+dy, l) in path_set:
                                         found = True
                                         break
                                 if found: break
                             if found: break

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
