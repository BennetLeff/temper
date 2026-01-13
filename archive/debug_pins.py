

from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.core.board import Board

def inspect_nets():
    pcb_path = "routed_v11.kicad_pcb" # Or v10, doesn't matter for netlist
    # Actually need to load unrouted board to get pins?
    # Or just load netlist.
    
    # We need the Component placement to get pin positions.
    # Load 'placed_board.kicad_pcb' (which is input to router).
    # But I don't know the exact name used in validation.
    # Validation uses `pre_routed_v5.kicad_pcb` or similiar.
    
    res = parse_kicad_pcb("pre_routed_v5.kicad_pcb")
    components = res.netlist.components
    
    print("Checking Net Pin Counts:")
    hd_nets = ["SPI_MISO", "SPI_MOSI", "SPI_CLK", "SPI_CS_A", "I_SENSE", "V_SENSE", "PWM_H", "PWM_L", "GATE_H", "GATE_L"]
    
    for net in hd_nets:
        # manual finding
        pins = []
        for comp in components:
            for pin in comp.pins:
                if pin.net == net:
                    cx, cy = comp.initial_position
                    rot = comp.initial_rotation or 0
                    side = comp.initial_side or 0
                    import math
                    px, py = pin.absolute_position((cx, cy), rot * (math.pi/2), side)
                    pins.append((px, py))
        
        print(f"Net {net}: {len(pins)} pins")

if __name__ == "__main__":
    inspect_nets()
