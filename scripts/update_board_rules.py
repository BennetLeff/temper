import sys
import os

# Ensure pcbnew can be imported
try:
    import pcbnew
except ImportError:
    print("Error: pcbnew module not found. Make sure to run this script with KiCad's python interpreter.")
    sys.exit(1)

def update_board_rules(pcb_path):
    if not os.path.exists(pcb_path):
        print(f"Error: File {pcb_path} not found.")
        sys.exit(1)
        
    print(f"Loading {pcb_path}...")
    
    # Initialize wx App to prevent "traits assertion failed"
    try:
        import wx
        app = wx.App(False) 
    except ImportError:
        pass

    try:
        board = pcbnew.LoadBoard(pcb_path)
    except Exception as e:
        print(f"Failed to load board: {e}")
        sys.exit(1)
        
    if board is None:
        print("Error: pcbnew.LoadBoard returned None. File might be corrupted or incompatible.")
        sys.exit(1)

    settings = board.GetDesignSettings()
    print(f"Settings API: {[d for d in dir(settings) if 'Clearance' in d]}")
    # sys.exit(1)
    
    # 0.15mm
    val_0_15 = pcbnew.FromMM(0.15)
    val_0_6  = pcbnew.FromMM(0.6) # Default Via Dia
    val_0_3  = pcbnew.FromMM(0.3) # Default Via Drill
    
    print(f"Setting rules to 0.15mm...")
    
    # Global Minima (using direct member access)
    settings.m_MinClearance = int(val_0_15)
    settings.m_MinTrackWidth = int(val_0_15)
    
    # Defaults? (Usually handled by 'Default' netclass in modern KiCad)
    # Check if members exist for fallback defaults (KiCad 5/6 legacy)
    if hasattr(settings, 'm_DefaultClearance'):
        settings.m_DefaultClearance = int(val_0_15)
    if hasattr(settings, 'm_DefaultTrackWidth'):
        settings.m_DefaultTrackWidth = int(val_0_15)
    
    # Update 'Default' netclass explicitly
    if hasattr(settings, 'm_NetSettings'):
        ns = settings.m_NetSettings
        
        # Update Default
        default_nc = ns.GetDefaultNetclass()
        if default_nc:
            print("Updating 'Default' NetClass...")
            if hasattr(default_nc, 'SetClearance'):
                default_nc.SetClearance(val_0_15)
                default_nc.SetTrackWidth(val_0_15)
                default_nc.SetViaDiameter(val_0_6)
                default_nc.SetViaDrill(val_0_3)
            else:
                default_nc.m_Clearance = int(val_0_15)
                default_nc.m_TrackWidth = int(val_0_15)
                default_nc.m_ViaDia = int(val_0_6)
                default_nc.m_ViaDrill = int(val_0_3)

        # Update HighCurrent
        if ns.HasNetclass("HighCurrent"):
            hc_nc = ns.GetNetClassByName("HighCurrent")
            if hc_nc:
                print("Enforcing 'HighCurrent' NetClass to 0.25mm...")
                val_0_25 = pcbnew.FromMM(0.25)
                if hasattr(hc_nc, 'SetClearance'):
                    hc_nc.SetClearance(val_0_25)
                else:
                    hc_nc.m_Clearance = int(val_0_25)
    
    board.Save(pcb_path)
    print(f"Saved updated board to {pcb_path}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python update_board_rules.py <pcb_file>")
        sys.exit(1)
    update_board_rules(sys.argv[1])
