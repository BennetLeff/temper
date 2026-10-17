#!/usr/bin/env python3
"""Thermal-relief spokes on low-current THT pads in the native-21 pours, in place.

    KICAD_PY native-21/layout/pad_reliefs21.py <board.kicad_pcb>

Independent review 2026-10-08, M3: every THT pad joined its 2 oz pours solidly, so the low-current
pins (J4's grounds, PE, the SELV / LS rails, the TCO loop) are hard to hand-solder and rework.
Those get 4 spokes, 0.5 mm wide with a 0.5 mm gap. 0.5 mm of 2 oz copper carries several amps per
spoke, more than any of these nets draws. Pins on power-current nets stay solid:
- bus, returns, switch nodes, tank, mains and rectifier, which carry 15-45 A;
- the REDCUBE studs, which are reflow-soldered THR parts.
"""
import sys

import pcbnew  # type: ignore[import-not-found]

SOLID = {"bus_p", "hv_ret", "leg_ret", "sw_a", "sw_b", "res_a", "coil_feed", "rect_p", "rect_n",
         "l_filt", "n_filt", "l_f", "ac_l_in", "ac_n_in"}
board = pcbnew.LoadBoard(sys.argv[1])
mm = pcbnew.FromMM
n = 0
for fp in board.GetFootprints():
    for pad in fp.Pads():
        if pad.GetAttribute() != pcbnew.PAD_ATTRIB_PTH or not pad.GetNetname() or pad.GetNetname() in SOLID:
            continue
        pad.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_THERMAL)
        pad.SetLocalThermalSpokeWidthOverride(mm(0.5))
        pad.SetThermalGap(mm(0.5))   # KiCad 10's SetLocalThermalGapOverride takes std::optional, which SWIG rejects
        n += 1
pcbnew.SaveBoard(sys.argv[1], board)
check = pcbnew.LoadBoard(sys.argv[1])
got = sum(p.GetLocalZoneConnection() == pcbnew.ZONE_CONNECTION_THERMAL and p.GetThermalGap() == mm(0.5)
          for fp in check.GetFootprints() for p in fp.Pads())
if got != n:
    sys.exit(f"pad_reliefs21: {got} of {n} reliefs survived the save")
print(f"thermal reliefs on {n} low-current THT pads")
