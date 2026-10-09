"""Write the fab pass's copy of a board, without local clearance overrides.

KiCad 10.0.4 applies a pad or footprint local clearance before any custom
rule: a 0.05 mm pad override hid a 0.10 mm gap from a 0.16 mm `zapote fab`
clearance rule (measured 2026-10-08), so the copy carries no footprint or
pad local clearance. A zone's own clearance does not mask the rule (a fill
0.05 mm from a track was reported with the zone at 0.05 mm), so zones keep it;
DRC does not refill zones, so copper is unchanged.

With MASK_WEB_MM the copy's minimum solder-mask web is set to the vendor's
figure, so KiCad's solder_mask_bridge check reports openings that merge across
nets (KiCad has no custom-rule constraint for it). Prints JSON: the cleared
overrides and the board's own and applied web widths.

Usage: <kicad python> fab_board_copy.py IN.kicad_pcb OUT.kicad_pcb [MASK_WEB_MM]
"""
import json
import sys

import pcbnew


def overrides(board):
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        yield "footprint", ref, fp
        for pad in fp.Pads():
            yield "pad", "%s.%s" % (ref, pad.GetNumber()), pad


source, target = sys.argv[1], sys.argv[2]
mask_web = float(sys.argv[3]) if len(sys.argv) > 3 else None
board = pcbnew.LoadBoard(source)
settings = board.GetDesignSettings()
web = {"board": pcbnew.ToMM(settings.m_SolderMaskMinWidth), "applied": None}
if mask_web is not None:
    settings.m_SolderMaskMinWidth = pcbnew.FromMM(mask_web)
    web["applied"] = mask_web
cleared = []
for kind, ident, item in overrides(board):
    value = item.GetLocalClearance()
    if value is not None:
        cleared.append({"kind": kind, "item": ident, "clearance_mm": pcbnew.ToMM(value)})
        item.SetLocalClearance(None)
pcbnew.SaveBoard(target, board)
saved = pcbnew.LoadBoard(target)
left = [ident for _, ident, item in overrides(saved) if item.GetLocalClearance() is not None]
if left:
    sys.exit("local clearance survived the copy: %s" % ", ".join(left))
print(json.dumps({"cleared": cleared, "solder_mask_min_web_mm": web}))
