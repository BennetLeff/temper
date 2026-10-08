"""Bind saved footprint instances to the generated native schematic UUIDs."""
from pathlib import Path
import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
import pcbnew
board_path, schematic_path, netlist_path, receipt_path = map(Path, sys.argv[1:])
before = hashlib.sha256(board_path.read_bytes()).hexdigest()
root_uuid = re.search(r'\(uuid "([^"]+)"\)', schematic_path.read_text()).group(1)
netlist = ET.parse(netlist_path).getroot()
paths = {comp.attrib['ref']: '/' + root_uuid + comp.find('sheetpath').attrib['tstamps'] + comp.findtext('tstamps') for comp in netlist.find('components')}
board = pcbnew.PCB_IO_KICAD_SEXPR().LoadBoard(str(board_path), None)
for fp in board.GetFootprints():
    fp.SetPath(pcbnew.KIID_PATH(paths[fp.GetReference()]))
pcbnew.PCB_IO_KICAD_SEXPR().SaveBoard(str(board_path), board)
receipt_path.write_text(json.dumps({'input_board_sha256': before,
    'schematic_sha256': hashlib.sha256(schematic_path.read_bytes()).hexdigest(),
    'netlist_sha256': hashlib.sha256(netlist_path.read_bytes()).hexdigest(),
    'binding_script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    'output_board_sha256': hashlib.sha256(board_path.read_bytes()).hexdigest(),
    'instance_paths': paths},indent=2)+'\n')
