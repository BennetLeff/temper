"""Native KiCad object transfer for an explicitly authored overlay instruction.

No placement/routing search: the JSON instruction names every replaced ref,
copper UUID to delete, and source copper object to import. KiCad serializes.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

import pcbnew

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "harness-lab"))
import buck_native


def apply(base_path: Path, section_path: Path, instruction_path: Path, output: Path) -> None:
    instruction = json.loads(instruction_path.read_text())
    board = buck_native.load(base_path)
    section = buck_native.load(section_path)
    existing = buck_native.footprints(board)
    incoming = buck_native.footprints(section)
    deleted = []
    objects = {o.m_Uuid.AsString(): o for o in list(board.GetTracks()) + list(board.Zones())}
    for uid in instruction["delete_copper_uuids"]:
        item = objects.get(uid)
        if item is None:
            raise ValueError("missing explicitly removed copper " + uid)
        if isinstance(item, pcbnew.ZONE):
            board.Remove(item)
        else:
            board.Delete(item)
        deleted.append(uid)
    for replacement in instruction["replace_footprints"]:
        ref = replacement["reference"]
        before = existing[ref]
        if before.m_Uuid.AsString() != replacement["old_uuid"]:
            raise ValueError("footprint changed since instruction: " + ref)
        after = pcbnew.Cast_to_FOOTPRINT(incoming[ref].Duplicate(False))
        for pad in after.Pads():
            name = pad.GetNetname()
            net = board.FindNet(name)
            if net is None:
                net = pcbnew.NETINFO_ITEM(board, name)
                board.Add(net)
            pad.SetNet(net)
        board.Remove(before)
        board.Add(after)
    for source in instruction["import_copper"]:
        donor = buck_native.load(Path(source["board"]))
        selected = {o.m_Uuid.AsString(): o for o in donor.GetTracks()}
        for uid in source["uuids"]:
            original = selected[uid]
            item = original.Duplicate(False)
            target_net = source["net_map"][original.GetNetname()]
            net = board.FindNet(target_net)
            if net is None:
                raise ValueError("unknown destination net " + target_net)
            item.SetNet(net)
            board.Add(item)
    output.parent.mkdir(parents=True, exist_ok=True)
    buck_native.save(board, output)
    (output.parent / "overlay-operation.json").write_text(json.dumps({
        "base": str(base_path), "section": str(section_path),
        "instruction": str(instruction_path), "deleted_copper": deleted,
        "replaced_refs": [r["reference"] for r in instruction["replace_footprints"]],
    }, indent=2) + "\n")


if __name__ == "__main__":
    apply(*(Path(arg) for arg in sys.argv[1:]))
