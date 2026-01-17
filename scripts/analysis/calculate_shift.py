
# Script to calculate the required shift for U_GATE
# Based on coordinates found in previous steps

def calculate_shift():
    # Coordinates from inspection
    d1_pad1 = (42.06, 29.83) # Assume AC_L
    d2_pad1 = (37.62, 45.00) # Assume AC_L (connected to D1)
    
    u_gate_center = (28.84, 30.53)
    u_gate_width_half = 4.5 # From pad inspection (24.34 to 28.84 is 4.5)
    u_gate_right_edge_x = u_gate_center[0] + u_gate_width_half # 33.34
    
    # The AC_L net connects D1 and D2.
    # The leftmost point of the ideal connection (straight line) is likely D2_pad1_x = 37.62.
    # Actually, the router might bow out, but let's assume the tightest bound is the component pads themselves.
    
    ac_l_leftmost_x = min(d1_pad1[0], d2_pad1[0]) # 37.62
    
    print(f"U_GATE Right Edge X: {u_gate_right_edge_x:.2f} mm")
    print(f"AC_L Leftmost Pad X: {ac_l_leftmost_x:.2f} mm (D2 Pad 1)")
    
    current_gap = ac_l_leftmost_x - u_gate_right_edge_x
    print(f"Current Gap: {current_gap:.2f} mm")
    
    required_gap = 6.0
    print(f"Required Gap: {required_gap:.2f} mm")
    
    if current_gap < required_gap:
        deficit = required_gap - current_gap
        print(f"Deficit: {deficit:.2f} mm")
        
        # Add safety margin (e.g. 1mm)
        margin = 1.0
        shift = deficit + margin
        print(f"\nRECOMMENDATION: Move U_GATE Left by at least {shift:.2f} mm")
        
        new_u_gate_x = u_gate_center[0] - shift
        print(f"New U_GATE X Center: {new_u_gate_x:.2f} mm")
    else:
        print("Gap is sufficient.")

if __name__ == "__main__":
    calculate_shift()
