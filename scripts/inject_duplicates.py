"""
Script to inject duplicates into a PCB file to test deduplication.
"""

from pathlib import Path
from kiutils.board import Board
from kiutils.items.gritems import GrText
from kiutils.items.common import Position

def inject_duplicates(input_path: Path, output_path: Path):
    board = Board.from_file(str(input_path))
    
    # Add some duplicate text
    text_item = GrText(
        text="DUPLICATE_TEXT",
        position=Position(X=100.0, Y=100.0),
        layer="F.SilkS"
    )
    
    # Add it 3 times
    board.graphicItems.append(text_item)
    board.graphicItems.append(text_item)
    board.graphicItems.append(text_item)
    
    # Add a component duplicate text (simulated)
    if board.footprints:
        fp = board.footprints[0]
        if fp.graphicItems:
            # Duplicate the first text item
            fp.graphicItems.append(fp.graphicItems[0])
            print(f"Injected duplicate text in footprint {fp.ref or 'unknown'}")

    board.to_file(str(output_path))
    print(f"Created dirty PCB at {output_path} with injected duplicates.")

if __name__ == "__main__":
    inject_duplicates(Path("hypergraph_demo.kicad_pcb"), Path("dirty.kicad_pcb"))
