import sys
from pathlib import Path
from kiutils.board import Board as KiBoard

def debug_kicad_file(pcb_path: str):
    ki_board = KiBoard.from_file(pcb_path)
    
    edge_cuts = [g for g in ki_board.graphicItems if g.layer == "Edge.Cuts"]
    print(f"Edge Cuts: {len(edge_cuts)}")
    
    if not edge_cuts:
        origin = (0.0, 0.0)
    else:
        x_min = float("inf")
        for item in edge_cuts:
            if hasattr(item, "start"):
                x_min = min(x_min, item.start.X)
        origin = (x_min, 0.0) # simplified
        
    print(f"Origin: {origin}, type of origin[0]: {type(origin[0])}")

    for fp in ki_board.footprints:
        print(f"Footprint: {fp.libId}, X={fp.position.X}, type={type(fp.position.X)}")
        diff = fp.position.X - origin[0]
        print(f"Diff: {diff}")
        break

if __name__ == "__main__":
    debug_kicad_file(sys.argv[1])