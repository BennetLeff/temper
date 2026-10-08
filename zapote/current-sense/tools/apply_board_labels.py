"""Transport explicitly authored board/reference label positions through KiCad."""
import hashlib
import json
from pathlib import Path
import sys
import pcbnew

board_path, instruction_path, receipt_path = map(Path, sys.argv[1:])
instruction = json.loads(instruction_path.read_text())
before = hashlib.sha256(board_path.read_bytes()).hexdigest()
io = pcbnew.PCB_IO_KICAD_SEXPR()
board = io.LoadBoard(str(board_path), None)
instances = {f.GetFieldText('SourceInstance'): f for f in board.GetFootprints()}
if set(instruction['references']) != set(instances):
    raise ValueError('label instruction must cover exact source component census')
for instance, at in instruction['references'].items():
    ref = instances[instance].Reference()
    ref.SetTextAngle(pcbnew.EDA_ANGLE(0, pcbnew.DEGREES_T))
    ref.SetPosition(pcbnew.VECTOR2I(*[pcbnew.FromMM(v) for v in at]))
    ref.SetTextSize(pcbnew.VECTOR2I(pcbnew.FromMM(.9), pcbnew.FromMM(.9)))
    ref.SetTextThickness(pcbnew.FromMM(.12))
    ref.SetVisible(True)
for entry in instruction['board_text']:
    item = pcbnew.PCB_TEXT(board)
    item.SetText(entry['text'])
    item.SetPosition(pcbnew.VECTOR2I(*[pcbnew.FromMM(v) for v in entry['at']]))
    item.SetTextSize(pcbnew.VECTOR2I(pcbnew.FromMM(entry['size']), pcbnew.FromMM(entry['size'])))
    item.SetTextThickness(pcbnew.FromMM(.15))
    item.SetLayer(pcbnew.F_SilkS)
    board.Add(item)
io.SaveBoard(str(board_path), board)
receipt_path.write_text(json.dumps({'input_board_sha256':before,'output_board_sha256':hashlib.sha256(board_path.read_bytes()).hexdigest(),'instructions_sha256':hashlib.sha256(instruction_path.read_bytes()).hexdigest(),'adapter_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'kicad_version':pcbnew.Version(),'scope':'native label placement only'},indent=2)+'\n')
