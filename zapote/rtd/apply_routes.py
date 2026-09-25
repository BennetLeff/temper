"""Replay agent-authored polylines through the existing KiCad block adapter.

No path planning, placement choice, or engineering verdict is performed here.
Pad references only resolve exact native coordinates; all bends are explicit.
"""
from pathlib import Path
import hashlib
import json
import sys
import tempfile
import pcbnew

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'harness-lab'))
import block_native
import buck_native


def _replay(board_path, instruction_path, receipt_path):
    before = hashlib.sha256(board_path.read_bytes()).hexdigest()
    instruction = json.loads(instruction_path.read_text())
    board = buck_native.load(board_path)
    pads = {}
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            aliases = [fp.GetReference()]
            source_id = fp.GetFieldText('SourceInstance')
            if source_id and source_id not in aliases:
                aliases.append(source_id)
            for alias in aliases:
                key = alias + '.' + pad.GetNumber()
                if key in pads:
                    # Duplicate physical pads need an explicit coordinate selection.
                    pads[key] = None
                else:
                    pads[key] = (list(pcbnew.ToMM(pad.GetPosition())), pad.GetNetname())
    receipts = []
    for operation in instruction['nets']:
        net = operation['net']
        segments = []
        for path in operation['paths']:
            points = []
            for point in path['points']:
                if isinstance(point, str):
                    match = pads[point]
                    if match is None:
                        raise ValueError('ambiguous duplicate pad: ' + point)
                    location, actual_net = match
                    if actual_net != net:
                        raise ValueError(f'{point}: expected {net}, actual {actual_net}')
                    points.append(location)
                else:
                    points.append(point)
            for start, end in zip(points, points[1:]):
                if start == end:
                    raise ValueError(f'zero-length explicit segment on {net}: {start}')
                segments.append({'start_mm': start, 'end_mm': end,
                    'width_mm': path['width_mm'], 'layer': path['layer']})
        vias = operation.get('vias', [])
        zones = operation.get('zones', [])
        if operation.get('mode', 'replace') == 'replace':
            block_native.replace_copper(board_path, net, segments, vias, zones)
        else:
            # Use the established adapter to construct new copper on a scratch
            # board, then transfer only that net's new native objects. Existing
            # destination copper UUIDs and geometry remain untouched.
            with tempfile.TemporaryDirectory(prefix='zapote-copper-') as tmp:
                scratch = Path(tmp) / 'new.kicad_pcb'
                scratch.write_bytes(board_path.read_bytes())
                block_native.replace_copper(scratch, net, segments, vias, zones)
                source = buck_native.load(scratch)
                target = buck_native.load(board_path)
                for zone in target.Zones():
                    zone.UnFill()
                for item in source.GetTracks():
                    if item.GetNetname() != net:
                        continue
                    copy = item.Duplicate()
                    copy = pcbnew.Cast_to_PCB_VIA(copy) if item.Type() == pcbnew.PCB_VIA_T else pcbnew.Cast_to_PCB_TRACK(copy)
                    copy.SetNet(target.FindNet(net))
                    target.Add(copy)
                for zone in source.Zones():
                    if zone.GetNetname() == net and not zone.GetIsRuleArea():
                        copy = pcbnew.Cast_to_ZONE(zone.Duplicate())
                        copy.SetNet(target.FindNet(net))
                        target.Add(copy)
                buck_native.save(target, board_path)
        receipts.append({'net': net, 'segments': segments, 'vias': vias, 'zones': zones, 'mode': operation.get('mode', 'replace')})
    receipt_path.write_text(json.dumps({'input_board_sha256': before,
        'instruction_sha256': hashlib.sha256(instruction_path.read_bytes()).hexdigest(),
        'adapter_sha256': hashlib.sha256((REPO / 'harness-lab/block_native.py').read_bytes()).hexdigest(),
        'buck_native_sha256': hashlib.sha256((REPO / 'harness-lab/buck_native.py').read_bytes()).hexdigest(),
        'replay_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'output_board_sha256': hashlib.sha256(board_path.read_bytes()).hexdigest(),
        'operations': receipts}, indent=2) + '\n')


def run(board_path, instruction_path, receipt_path):
    # A failed explicit operation must not leave a partially edited candidate.
    with tempfile.TemporaryDirectory(prefix='zapote-route-transaction-') as tmp:
        scratch = Path(tmp) / board_path.name
        scratch.write_bytes(board_path.read_bytes())
        pending_receipt = Path(tmp) / 'receipt.json'
        _replay(scratch, instruction_path, pending_receipt)
        board_path.write_bytes(scratch.read_bytes())
        receipt_path.write_bytes(pending_receipt.read_bytes())


if __name__ == '__main__':
    run(*(Path(arg) for arg in sys.argv[1:]))
