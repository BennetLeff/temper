# Gang-relief revision (2026-10-08)

U4 (VSSOP-8, 0.5 mm pitch) now carries KiCad's `allow_soldermask_bridges`
attribute, on the board and in the vendored footprint
(`../../gang_relief_2026_10_08.py`, which records the decision). At 2 oz JLC
makes no mask dam between pads closer than 0.20 mm; U4's pads are 0.15 mm
apart. Nothing else changed.

`native.json` is a fresh `current-sense/tools/extract_current_sense_native.py`
export. It is identical to `../silk-legend-2026-10-08/native.json` apart from
board identity.
