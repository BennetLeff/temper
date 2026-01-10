
from kiutils.board import Board as KiBoard
import sys

def main():
    path = '/Users/bennet/Desktop/temper/piantor_production.kicad_pcb'
    try:
        print(f"Loading {path}...")
        board = KiBoard.from_file(path)
        print("Loaded successfully")
        
        output = '/Users/bennet/Desktop/temper/test_diag.kicad_pcb'
        print(f"Saving to {output}...")
        board.to_file(output)
        print("Saved successfully")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
