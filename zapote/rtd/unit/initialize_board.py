"""Apply Astra's explicit standalone stack and manufacturing settings via KiCad."""
from pathlib import Path
import hashlib
import json
import shutil
import sys
import pcbnew

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / 'harness-lab'))
import buck_native

board_path, contract_path, receipt_path = map(Path, sys.argv[1:])
c = json.loads(contract_path.read_text())
before = hashlib.sha256(board_path.read_bytes()).hexdigest()
b = buck_native.load(board_path)
if b.GetTracks() or len(list(b.Zones())):
    raise ValueError('unit initialization requires a source-generated board without copper')
b.SetCopperLayerCount(len(c['copper_layers']))
b.GetDesignSettings().SetBoardThickness(pcbnew.FromMM(c['nominal_board_thickness_mm']))
buck_native.save(b, board_path)
# The KiCad10 SWIG build does not expose BOARD_STACKUP. Serialize the explicit
# authored stack, then reload it with native KiCad to validate the file.
stack = '''(stackup
 (layer "F.SilkS" (type "Top Silk Screen"))
 (layer "F.Paste" (type "Top Solder Paste"))
 (layer "F.Mask" (type "Top Solder Mask") (thickness 0.01))
 (layer "F.Cu" (type "copper") (thickness 0.035))
 (layer "dielectric 1" (type "prepreg") (thickness 0.2) (material "FR4") (epsilon_r 4.5) (loss_tangent 0.02))
 (layer "In1.Cu" (type "copper") (thickness 0.035))
 (layer "dielectric 2" (type "core") (thickness 1.04) (material "FR4") (epsilon_r 4.5) (loss_tangent 0.02))
 (layer "In2.Cu" (type "copper") (thickness 0.035))
 (layer "dielectric 3" (type "prepreg") (thickness 0.2) (material "FR4") (epsilon_r 4.5) (loss_tangent 0.02))
 (layer "B.Cu" (type "copper") (thickness 0.035))
 (layer "B.Mask" (type "Bottom Solder Mask") (thickness 0.01))
 (layer "B.Paste" (type "Bottom Solder Paste"))
 (layer "B.SilkS" (type "Bottom Silk Screen"))
 (copper_finish "ENIG") (dielectric_constraints no))'''
text=board_path.read_text()
start=text.find('(stackup')
if start >= 0:
    depth=0
    for end in range(start,len(text)):
        depth += (text[end]=='(')-(text[end]==')')
        if depth==0:
            text=text[:start]+stack+text[end+1:]
            break
else:
    text=text.replace('(setup', '(setup\n'+stack,1)
board_path.write_text(text)
b=buck_native.load(board_path)
assert b.GetCopperLayerCount()==4
buck_native.save(b,board_path)
project={'meta':{'filename':board_path.with_suffix('.kicad_pro').name,'version':1},
 'board':{'design_settings':{'rules':{
 'min_clearance':c['minimum_copper_clearance_mm'], 'min_track_width':c['minimum_track_width_mm'],
 'min_via_annular_width':c['minimum_annular_ring_mm'],'min_via_diameter':c['through_via_diameter_mm'],
 'min_through_hole_diameter':c['through_via_drill_mm'],'min_copper_edge_clearance':c['copper_edge_clearance_mm'],
 'min_hole_clearance':.25,'min_hole_to_hole':.25,'min_silk_clearance':.1,'min_text_height':.8,'min_text_thickness':.08}}},
 'net_settings':{'classes':[{'name':'Default','clearance':c['minimum_copper_clearance_mm'],
 'track_width':c['minimum_track_width_mm'],'via_diameter':c['through_via_diameter_mm'],'via_drill':c['through_via_drill_mm'],'wire_width':6,'bus_width':12,'line_style':0}]}}
board_path.with_suffix('.kicad_pro').write_text(json.dumps(project,indent=2)+'\n')
board_path.with_suffix('.kicad_dru').write_text('(version 1)\n# Standalone SELV RTD carrier. Numeric constraints are in the adjacent project.\n')
lib=board_path.parent/'candidate-libs'
if (lib/'fp-lib-table').exists():
    shutil.copy2(lib/'fp-lib-table',board_path.parent/'fp-lib-table')
    if (lib/'libs').exists():
        shutil.copytree(lib/'libs',board_path.parent/'libs',dirs_exist_ok=True)
receipt={'status':'initialized-unrouted','input_board_sha256':before,'output_board_sha256':hashlib.sha256(board_path.read_bytes()).hexdigest(),
 'instruction_sha256':hashlib.sha256(contract_path.read_bytes()).hexdigest(),'replay_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
 'kicad_version':pcbnew.Version(),'layers':c['copper_layers'],'physical_tests':'NOT RUN'}
receipt_path.write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt))
