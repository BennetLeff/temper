from kiutils.board import Board
try:
    board = Board.from_file('pcb/temper_deterministic_final.kicad_pcb')
    print("Successfully loaded with kiutils")
except Exception as e:
    print(f"Failed to load with kiutils: {e}")
