
import sys
import os
import pcbnew
import wx

def fill_zones(pcb_file):
    # Initialize wxApp to prevent "create wxApp before calling this" error
    # This is required because pcbnew may initialize GUI components (fonts, etc.)
    app = wx.App(False)
    
    if not os.path.exists(pcb_file):
        print(f"Error: File {pcb_file} not found")
        sys.exit(1)
        
    abs_pcb = os.path.abspath(pcb_file)
    print(f"Loading {abs_pcb}...")
    try:
        board = pcbnew.LoadBoard(abs_pcb)
    except Exception as e:
        print(f"Caught exception during LoadBoard: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    if board is None:
        print(f"Error: Failed to load board from {abs_pcb}. The file might be corrupted or incompatible.")
        # Sometimes pcbnew doesn't raise but returns None. 
        # We've printed enough to know it failed.
        sys.exit(1)
    
    print(f"Found {len(board.Zones())} zones.")
    print("Refilling all zones...")
    filler = pcbnew.ZONE_FILLER(board)
    filler.Fill(board.Zones())
    
    print(f"Saving {pcb_file}...")
    board.Save(pcb_file)
    print("Success: Zones filled.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 fill_zones.py <pcb_file>")
        sys.exit(1)
    fill_zones(sys.argv[1])
