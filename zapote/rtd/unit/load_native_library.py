"""Load source-selected library shapes with KiCad's native placement transform.

The skeleton supplies net membership and schematic paths; the explicit pose file
supplies every placement. No geometry decisions or routing search occur here.
"""
from pathlib import Path
import hashlib
import json
import sys
import pcbnew

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / 'harness-lab'))
import buck_native

board_path, manifest_path, poses_path, receipt_path = map(Path, sys.argv[1:])
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
before = sha(board_path)
manifest = json.loads(manifest_path.read_text())
poses = json.loads(poses_path.read_text())
board = buck_native.load(board_path)
if board.GetTracks() or len(list(board.Zones())):
    raise ValueError('native library loading requires an unrouted skeleton')
existing = {fp.GetReference(): fp for fp in board.GetFootprints()}
changes = []
for comp in manifest['bridge']['components']:
    ref, instance = comp['reference'], comp['instance_path']
    old = existing[ref]
    nickname, name = comp['footprint'].split(':', 1)
    library = board_path.parent / 'candidate-libs' / (nickname + '.pretty')
    fp = pcbnew.FootprintLoad(str(library), name)
    if fp is None:
        raise ValueError('native library load failed: ' + comp['footprint'])
    fp.SetFPID(pcbnew.LIB_ID(nickname, name))
    fp.SetReference(ref)
    fp.SetPath(old.GetPath())
    fp.SetExcludedFromBOM(old.IsExcludedFromBOM())
    attrs = manifest['source_attributes'][instance]
    # The generated KiCad symbol exports MPN as Value; SourceValue retains
    # the engineering value independently (e.g. 430 ohm tolerance).
    fp.SetValue(attrs['mpn'])
    fp.SetField('MPN', attrs['mpn'])
    fp.SetField('SourceInstance', instance)
    fp.SetField('SourceValue', str(attrs.get('value') or ''))
    fp.SetField('Datasheet', '')  # Generated source symbol has no datasheet field.
    for field in fp.GetFields():
        if field.GetName() != 'Reference':
            field.SetVisible(False)
    pose = poses[instance]
    fp.SetOrientationDegrees(pose[2])
    fp.SetPosition(buck_native.position(*pose[:2]))
    nets = {p.GetNumber(): p.GetNetname() for p in old.Pads()}
    for pad in fp.Pads():
        pad.SetNet(board.FindNet(nets[pad.GetNumber()]))
    board.Remove(old)
    board.Add(fp)
    changes.append({'instance': instance, 'reference': ref,
        'library_sha256': sha(library / (name + '.kicad_mod')), 'pose': pose})
buck_native.save(board, board_path)
receipt_path.write_text(json.dumps({'input_board_sha256': before,
    'output_board_sha256': sha(board_path), 'manifest_sha256': sha(manifest_path),
    'poses_sha256': sha(poses_path), 'replay_sha256': sha(Path(__file__)),
    'buck_native_sha256': sha(REPO / 'harness-lab/buck_native.py'),
    'kicad_version': pcbnew.Version(), 'operations': changes}, indent=2) + '\n')
