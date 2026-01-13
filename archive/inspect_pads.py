
from kiutils.board import Board
import sys

def inspect_pads():
    board = Board.from_file("pre_routed_v5.kicad_pcb")
    print(f"Loaded board with {len(board.footprints)} footprints")
    
    for i, fp in enumerate(board.footprints[:5]):
        print(f"Footprint {i}: {fp.entryName}")
        for j, pad in enumerate(fp.pads[:3]):
            print(f"  Pad {j}: Shape={pad.shape}, Layers={pad.layers}")

if __name__ == "__main__":
    inspect_pads()
