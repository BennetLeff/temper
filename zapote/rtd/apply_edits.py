"""Apply explicit Astra placements and copper UUID deletions, recording geometry."""
import hashlib
import json
from pathlib import Path
import sys
import pcbnew
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'harness-lab'))
import block_native
import buck_native

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def pins(fp):
    return [{'pad': p.GetNumber(), 'net': p.GetNetname(), 'position_mm': list(pcbnew.ToMM(p.GetPosition()))} for p in fp.Pads()]

def run(board_path, instruction_path, receipt_path):
    instruction = json.loads(instruction_path.read_text())
    before = sha(board_path)
    board = buck_native.load(board_path)
    instances = {f.GetFieldText('SourceInstance'): f for f in board.GetFootprints()}
    objects = {o.m_Uuid.AsString(): o for o in list(board.GetTracks()) + list(board.Zones())}
    # Validate the whole explicit edit before changing the saved candidate.
    for instance in instruction['placements']:
        if instance not in instances:
            raise ValueError('unknown source instance ' + instance)
    for uid in instruction['delete_copper_uuids']:
        if uid not in objects:
            raise ValueError('unknown copper ' + uid)
    for zone in board.Zones():
        zone.UnFill()
    removed = []
    for uid in instruction['delete_copper_uuids']:
        obj = objects[uid]
        removed.append({'uuid': uid, 'net': obj.GetNetname(), 'position_mm': list(pcbnew.ToMM(obj.GetPosition()))})
        board.Delete(obj)
    changed = []
    for instance, pose in instruction['placements'].items():
        fp = instances[instance]
        old = {'position_mm': list(pcbnew.ToMM(fp.GetPosition())), 'angle_deg': fp.GetOrientationDegrees(), 'pads': pins(fp)}
        fp.SetOrientationDegrees(pose[2])
        fp.SetPosition(buck_native.position(*pose[:2]))
        changed.append({'instance': instance, 'reference': fp.GetReference(), 'uuid': fp.m_Uuid.AsString(), 'before': old,
            'after': {'position_mm': list(pcbnew.ToMM(fp.GetPosition())), 'angle_deg': fp.GetOrientationDegrees(), 'pads': pins(fp)}})
    buck_native.save(board, board_path)
    receipt_path.write_text(json.dumps({'input_board_sha256': before, 'output_board_sha256': sha(board_path),
        'instruction_sha256': sha(instruction_path), 'replay_sha256': sha(Path(__file__)),
        'buck_native_sha256': sha(REPO / 'harness-lab/buck_native.py'), 'placements': changed, 'removed_copper': removed}, indent=2) + '\n')

if __name__ == '__main__':
    run(*(Path(p) for p in sys.argv[1:]))
