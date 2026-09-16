"""Apply the reviewed explicit shunt trace edit through pcbnew."""
import sys
import pcbnew
board_path = sys.argv[1]
io = pcbnew.PCB_IO_KICAD_SEXPR()
board = io.LoadBoard(board_path, None)
trace = next(t for t in board.GetTracks() if t.m_Uuid.AsString() == "e45ca754-66c7-4204-987e-e69d5ed1af44")
trace.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(75.3), pcbnew.FromMM(132)))
trace.SetWidth(pcbnew.FromMM(5.3))
io.SaveBoard(board_path, board)
