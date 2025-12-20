from __future__ import annotations
from typing import TYPE_CHECKING, List, Dict, Tuple, Optional
from dataclasses import dataclass

if TYPE_CHECKING:
    from temper_placer.core.netlist import Netlist, Net
    from temper_placer.core.loop import LoopCollection

def get_net_priority(
    net: Net,
    loops: Optional[LoopCollection] = None
) -> Tuple[int, int, int, str]:
    """Calculate deterministic priority for a net.
    
    Priority order:
    1. Criticality (Loop membership): nets in loops first
    2. Net Class: HighVoltage (1) > Power (2) > GateDrive (3) > Signal (4)
    3. Pin Count: More pins = harder to route = higher priority
    4. Alphabetical: Tie-breaker
    
    Returns a tuple suitable for sorting (lower values = higher priority).
    """
    # 1. Loop membership (0 if in a loop, 1 if not)
    in_loop = 0
    if loops:
        for loop in loops.loops:
            if net.name in [p.net_name for p in loop.pins]:
                in_loop = 0
                break
        else:
            in_loop = 1
    else:
        in_loop = 1
        
    # 2. Net Class
    class_map = {
        "HighVoltage": 1,
        "Power": 2,
        "GateDrive": 3,
        "Signal": 4
    }
    class_pri = class_map.get(net.net_class, 5)
    
    # 3. Pin Count (descending, so we use -count)
    pin_count_pri = -len(net.pins)
    
    # 4. Alphabetical
    name_pri = net.name
    
    return (in_loop, class_pri, pin_count_pri, name_pri)

def order_nets(
    netlist: Netlist,
    loops: Optional[LoopCollection] = None
) -> List[str]:
    """Order nets for deterministic routing verification."""
    nets = list(netlist.nets)
    
    # Sort by priority
    nets.sort(key=lambda n: get_net_priority(n, loops))
    
    return [n.name for n in nets]

def assign_layers(
    netlist: Netlist,
    ordered_nets: List[str]
) -> Dict[str, int]:
    """Assign layers to nets based on constraints and priority.
    
    Rules (4-layer induction cooker):
    - HighVoltage -> L1 (Top) only
    - GateDrive -> Prefer L1, then L4
    - Power -> L1 or L4
    - Signal -> Prefer L4, then L1
    """
    assignments = {}
    
    # 0-based indices: 0=L1, 1=L2(GND), 2=L3(PWR), 3=L4
    
    for net_name in ordered_nets:
        net = netlist.get_net(net_name)
        
        if net.net_class == "HighVoltage":
            assignments[net_name] = 0
        elif net.net_class == "GateDrive":
            assignments[net_name] = 0 # Prefer L1
        elif net.net_class == "Power":
            assignments[net_name] = 0 # Prefer L1
        else:
            assignments[net_name] = 3 # Prefer L4
            
    return assignments