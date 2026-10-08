"""Apply an explicitly authored rectangular outline through native KiCad."""
from pathlib import Path
import hashlib
import json
import sys
import pcbnew
board_path, instruction_path, receipt_path = map(Path, sys.argv[1:])
before = hashlib.sha256(board_path.read_bytes()).hexdigest()
io = pcbnew.PCB_IO_KICAD_SEXPR()
board = io.LoadBoard(str(board_path), None)
x1,y1,x2,y2 = json.loads(instruction_path.read_text())['outline_mm']
if not x1 < x2 or not y1 < y2:
    raise ValueError('invalid rectangular outline')
for edge in list(board.GetDrawings()):
    if edge.GetLayer() == pcbnew.Edge_Cuts:
        board.Remove(edge)
points=[(x1,y1),(x2,y1),(x2,y2),(x1,y2),(x1,y1)]
for start,end in zip(points,points[1:]):
    edge=pcbnew.PCB_SHAPE(board)
    edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
    edge.SetStart(pcbnew.VECTOR2I(*[pcbnew.FromMM(v) for v in start]))
    edge.SetEnd(pcbnew.VECTOR2I(*[pcbnew.FromMM(v) for v in end]))
    edge.SetWidth(pcbnew.FromMM(.05))
    edge.SetLayer(pcbnew.Edge_Cuts)
    board.Add(edge)
io.SaveBoard(str(board_path),board)
receipt_path.write_text(json.dumps({'input_board_sha256':before,'output_board_sha256':hashlib.sha256(board_path.read_bytes()).hexdigest(),'outline_mm':[x1,y1,x2,y2],'instruction_sha256':hashlib.sha256(instruction_path.read_bytes()).hexdigest(),'adapter_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},indent=2)+'\n')
