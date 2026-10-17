"""Synchronize source pin assignments while retaining existing native geometry.

Existing packages must be unchanged. New parts use an explicit pose instruction.
This is source/native transport; it performs no placement or routing search.
"""
from pathlib import Path
import hashlib
import json
import sys
import pcbnew

board_path, manifest_path, section_path, poses_path, receipt_path = map(Path, sys.argv[1:])
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
before = sha(board_path)
manifest = json.loads(manifest_path.read_text())
poses = json.loads(poses_path.read_text())
io = pcbnew.PCB_IO_KICAD_SEXPR()
board = io.LoadBoard(str(board_path), None)
for zone in board.Zones():
    zone.UnFill()
section = io.LoadBoard(str(section_path), None)
existing = {f.GetFieldText('SourceInstance'): f for f in board.GetFootprints()}
incoming = {f.GetFieldText('SourceInstance'): f for f in section.GetFootprints()}
components = {c['instance_path']: c for c in manifest['bridge']['components']}
if set(existing) - set(components):
    raise ValueError('source removed existing footprints; explicit deletion required')
for instance, fp in existing.items():
    lib_id = fp.GetFPID()
    if str(lib_id.GetLibNickname()) + ':' + str(lib_id.GetLibItemName()) != components[instance]['footprint']:
        raise ValueError('package replacement requires an explicit operation: ' + instance)
changes = []
for instance, comp in components.items():
    donor = incoming[instance]
    fp = existing.get(instance)
    added = fp is None
    if added:
        lib, name = comp['footprint'].split(':', 1)
        fp = pcbnew.FootprintLoad(str(section_path.parent / 'candidate-libs' / (lib + '.pretty')), name)
        fp.SetFPID(pcbnew.LIB_ID(lib, name))
        pose = poses[instance]
        fp.SetOrientationDegrees(pose[2])
        fp.SetPosition(pcbnew.VECTOR2I(*[pcbnew.FromMM(v) for v in pose[:2]]))
        board.Add(fp)
    prior = {'reference': fp.GetReference(), 'pads': {p.GetNumber(): p.GetNetname() for p in fp.Pads()}}
    fp.SetReference(comp['reference'])
    fp.SetPath(donor.GetPath())
    attrs = manifest['source_attributes'][instance]
    fp.SetValue(attrs['mpn'])
    for key, value in [('MPN', attrs['mpn']), ('SourceInstance', instance), ('SourceValue', str(attrs.get('value') or '')), ('Datasheet', '')]:
        fp.SetField(key, value)
    for field in fp.GetFields():
        if field.GetName() != 'Reference':
            field.SetVisible(False)
    pad_nets = {p.GetNumber(): p.GetNetname() for p in donor.Pads()}
    if set(pad_nets) != {p.GetNumber() for p in fp.Pads()}:
        raise ValueError('source/native pad census changed: ' + instance)
    for pad in fp.Pads():
        name = pad_nets[pad.GetNumber()]
        net = board.FindNet(name)
        if net is None:
            net = pcbnew.NETINFO_ITEM(board, name)
            board.Add(net)
        pad.SetNet(net)
    changes.append({'instance': instance, 'added': added, 'before': prior,
        'reference': fp.GetReference(), 'pads': pad_nets})
io.SaveBoard(str(board_path), board)
receipt_path.write_text(json.dumps({'input_board_sha256': before, 'output_board_sha256': sha(board_path),
    'manifest_sha256': sha(manifest_path), 'section_sha256': sha(section_path),
    'poses_sha256': sha(poses_path), 'replay_sha256': sha(Path(__file__)),
    'operations': changes, 'kicad_version': pcbnew.Version()}, indent=2) + '\n')
