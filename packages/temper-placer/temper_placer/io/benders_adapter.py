"""
Adapter to convert internal Board/Netlist models to Benders Input format.
"""
from typing import Dict, Any, List
from temper_placer.core.board import Board
from temper_placer.core.netlist import Netlist

class BendersAdapter:
    @staticmethod
    def convert(board: Board, netlist: Netlist) -> Dict[str, Any]:
        """
        Convert Board and Netlist objects to the dictionary format 
        required by the Benders Optimizer.
        """
        # 1. Board Info
        # Board origin is handled at parser/writer level usually, but we include it
        # Board in Benders is usually 0-based, so we just pass width/height
        input_data = {
            "board": {
                "width_mm": board.width,
                "height_mm": board.height,
                "origin": [board.origin[0], board.origin[1]]
            },
            "coordinate_system": "center",
            "hv_nets": [], # To be populated
            "components": []
        }
        
        # 2. Identify HV Nets (Heuristic or from Rules)
        # For MVP, we hardcode common HV power nets if they aren't explicitly tagged
        # ideally this comes from 'constraints', passed in if available. 
        # For now, use a robust set of known HV nets for Temper.
        known_hv = {"AC_L", "AC_N", "DC_BUS+", "DC_BUS-", "SW_NODE", "VCC_BOOT", "GATE_H", "GATE_L"}
        input_data["hv_nets"] = list(known_hv)
        
        # 3. Components
        for comp in netlist.components:
            # Extract nets
            nets = []
            c_hv_nets = []
            is_hv = False
            
            for pin in comp.pins:
                if pin.net and pin.net not in nets:
                    nets.append(pin.net)
                    if pin.net in known_hv:
                        c_hv_nets.append(pin.net)
                        is_hv = True
                        
            # Classification
            # Logic: If touches HV net -> HV, else LV
            classification = "HV" if is_hv else "LV"
            
            # Dimensions
            # comp.width / height might be available directly if parser populated them
            w = getattr(comp, "width", 5.0) 
            h = getattr(comp, "height", 5.0)
            
            # Position (Initial)
            x = comp.initial_position[0]
            y = comp.initial_position[1]
            
            comp_data = {
                "ref": comp.ref,
                "width_mm": w,
                "height_mm": h,
                "center_x_mm": x,
                "center_y_mm": y,
                "nets": nets,
                "hv_nets": c_hv_nets,
                "classification": classification
            }
            input_data["components"].append(comp_data)
            
        return input_data
