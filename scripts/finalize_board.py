import sys
import os

try:
    import pcbnew
    import wx
    app = wx.App(False) 
except ImportError:
    print("Error: pcbnew/wx module not found. Run with KiCad python.")
    sys.exit(1)

def finalize_board(input_path, output_path):
    if not os.path.exists(input_path):
        print(f"Error: {input_path} not found.")
        sys.exit(1)
        
    print(f"Loading {input_path}...")
    try:
        board = pcbnew.LoadBoard(input_path)
    except Exception as e:
        print(f"Error loading board: {e}")
        sys.exit(1)

    # 1. Update Design Rules
    print("Updating Design Rules...")
    settings = board.GetDesignSettings()
    
    val_0_15 = pcbnew.FromMM(0.15)
    val_0_3 = pcbnew.FromMM(0.3)
    
    # Global Minima
    settings.m_MinClearance = int(val_0_15)
    settings.m_MinTrackWidth = int(val_0_15)
    
    # Min Drill (0.3mm standard)
    if hasattr(settings, 'm_MinThroughDrill'):
        settings.m_MinThroughDrill = int(val_0_3)
    elif hasattr(settings, 'SetMinThroughDrill'):
        settings.SetMinThroughDrill(val_0_3)

    # Update Default NetClass
    if hasattr(settings, 'm_NetSettings'):
        ns = settings.m_NetSettings
        
        default_nc = ns.GetDefaultNetclass()
        if default_nc:
            if hasattr(default_nc, 'SetClearance'):
                default_nc.SetClearance(val_0_15)
                default_nc.SetTrackWidth(val_0_15)
            else:
                default_nc.m_Clearance = int(val_0_15)
                default_nc.m_TrackWidth = int(val_0_15)
        
        # Update HighCurrent
        if ns.HasNetclass("HighCurrent"):
            hc_nc = ns.GetNetClassByName("HighCurrent")
            if hc_nc:
                 # Ensure strictness
                val_0_3 = pcbnew.FromMM(0.3)
                if hasattr(hc_nc, 'SetClearance'):
                    hc_nc.SetViaDrill(val_0_3)
                else:
                    hc_nc.m_ViaDrill = int(val_0_3)

    # 2. Fill Zones
    print("Filling Zones...")
    filler = pcbnew.ZONE_FILLER(board)
    zones = list(board.Zones())
    if zones:
        filler.Fill(zones)
        print(f"Filled {len(zones)} zones.")
    else:
        print("No zones found.")

    # 3. Save
    print(f"Saving to {output_path}...")
    pcbnew.SaveBoard(output_path, board)
    print("Done.")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python finalize_board.py <input> <output>")
        sys.exit(1)
    finalize_board(sys.argv[1], sys.argv[2])
