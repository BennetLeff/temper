import pcbnew
import os

def create_board():
    board = pcbnew.BOARD()
    
    # Add GND net
    net = pcbnew.NETINFO_ITEM(board, "GND", 1)
    board.Add(net)
    
    # Add a zone
    zone = board.AddArea(None, 1, pcbnew.F_Cu, pcbnew.VECTOR2I(0, 0), pcbnew.ZONE_FILLER_POLYGON_STYLE_POLYGON)
    outline = zone.Outline()
    outline.Append(0, 0)
    outline.Append(20000000, 0) # 20mm
    outline.Append(20000000, 20000000)
    outline.Append(0, 20000000)
    
    # Fill settings
    settings = zone.GetFillSettings()
    settings.SetMinThickness(100000) # 0.1mm
    
    filler = pcbnew.ZONE_FILLER(board)
    filler.Fill(board.Zones())
    
    # Save
    pcbnew.SaveBoard("experiments/reference_zone.kicad_pcb", board)
    print("Created reference_zone.kicad_pcb")

if __name__ == "__main__":
    if not os.path.exists("experiments"):
        os.makedirs("experiments")
    create_board()
