"""Transfer explicitly selected source instances and their new designators.

Keeps existing copper and non-selected footprint geometry. Source instance
identity, not a coincidentally unchanged reference, selects each object.
"""
from pathlib import Path
import hashlib
import json
import sys
import pcbnew
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'harness-lab'))
import buck_native


def apply(board_path, section_path, old_manifest_path, manifest_path, receipt_path):
    before = hashlib.sha256(board_path.read_bytes()).hexdigest()
    old = json.loads(old_manifest_path.read_text())
    new = json.loads(manifest_path.read_text())
    old_map = {c['reference']: c['instance_path'] for c in old['full_bridge']['components']}
    new_map = {c['instance_path']: c['reference'] for c in new['full_bridge']['components']}
    replacements = {c['instance_path'] for c in new['bridge']['components']}
    board = buck_native.load(board_path)
    section = buck_native.load(section_path)
    incoming = buck_native.footprints(section)
    removed, renamed, added = [], [], []
    for fp in list(board.GetFootprints()):
        ref = fp.GetReference()
        path = old_map[ref]
        if path in replacements:
            removed.append({'instance': path, 'reference': ref, 'uuid': fp.m_Uuid.AsString()})
            board.Remove(fp)
        else:
            fp.SetReference(new_map[path])
            fp.SetField('SourceInstance', path)
            fp.SetField('MPN', new['source_attributes'][path]['mpn'])
            fp.SetValue(new['source_attributes'][path]['mpn'])
            renamed.append({'instance': path, 'old_reference': ref, 'reference': new_map[path], 'uuid': fp.m_Uuid.AsString()})
    for path in sorted(replacements):
        ref = new_map[path]
        fp = pcbnew.Cast_to_FOOTPRINT(incoming[ref].Duplicate(False))
        for pad in fp.Pads():
            name = pad.GetNetname()
            net = board.FindNet(name)
            if net is None:
                net = pcbnew.NETINFO_ITEM(board, name)
                board.Add(net)
            pad.SetNet(net)
        board.Add(fp)
        added.append({'instance': path, 'reference': ref, 'uuid': fp.m_Uuid.AsString()})
    # Explicit source correction: both existing safety consumers use one
    # physical REF2025 output; old source applied two conflicting aliases.
    new_ref = board.FindNet('SHARED_REF_2V5')
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if pad.GetNetname() == 'OCP2_VREF_2V5':
                pad.SetNet(new_ref)
    for item in board.GetTracks():
        if item.GetNetname() == 'OCP2_VREF_2V5':
            item.SetNet(new_ref)
    buck_native.save(board, board_path)
    receipt_path.write_text(json.dumps({'input_board_sha256': before,
        'source_manifest_sha256': hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        'section_sha256': hashlib.sha256(section_path.read_bytes()).hexdigest(),
        'adapter_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'output_board_sha256': hashlib.sha256(board_path.read_bytes()).hexdigest(),
        'removed_footprints': removed, 'renamed_footprints': renamed,
        'added_footprints': added, 'net_rename': {'OCP2_VREF_2V5': 'SHARED_REF_2V5'}},indent=2)+'\n')


if __name__ == '__main__':
    apply(*(Path(x) for x in sys.argv[1:]))
