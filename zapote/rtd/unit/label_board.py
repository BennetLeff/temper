"""Replay explicit assembly reference and unit-interface label positions."""
from pathlib import Path
import hashlib
import json
import sys
import pcbnew

board_path, instruction_path, receipt_path = map(Path, sys.argv[1:])
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
before = sha(board_path)
board = pcbnew.PCB_IO_KICAD_SEXPR().LoadBoard(str(board_path), None)
instruction = json.loads(instruction_path.read_text())
by_id = {f.GetFieldText('SourceInstance'): f for f in board.GetFootprints()}
for instance, point in instruction['references'].items():
    field = by_id[instance].Reference()
    field.SetPosition(pcbnew.VECTOR2I(*[pcbnew.FromMM(v) for v in point]))
    field.SetTextAngle(pcbnew.EDA_ANGLE(0, pcbnew.DEGREES_T))
    field.SetTextSize(pcbnew.VECTOR2I(pcbnew.FromMM(.8), pcbnew.FromMM(.8)))
    field.SetTextThickness(pcbnew.FromMM(.12))
for label in instruction['labels']:
    matches = [d for d in board.GetDrawings()
        if isinstance(d, pcbnew.PCB_TEXT) and d.GetText() == label['text']]
    if len(matches) > 1:
        raise ValueError('ambiguous existing label: ' + label['text'])
    text = matches[0] if matches else pcbnew.PCB_TEXT(board)
    text.SetText(label['text'])
    text.SetPosition(pcbnew.VECTOR2I(*[pcbnew.FromMM(v) for v in label['position_mm']]))
    text.SetTextSize(pcbnew.VECTOR2I(pcbnew.FromMM(.8), pcbnew.FromMM(.8)))
    text.SetTextThickness(pcbnew.FromMM(.12))
    text.SetLayer(pcbnew.F_SilkS)
    if not matches:
        board.Add(text)
pcbnew.PCB_IO_KICAD_SEXPR().SaveBoard(str(board_path), board)
receipt_path.write_text(json.dumps({'input_board_sha256': before,
    'output_board_sha256': sha(board_path), 'instruction_sha256': sha(instruction_path),
    'replay_sha256': sha(Path(__file__)), 'kicad_version': pcbnew.Version()}, indent=2) + '\n')
