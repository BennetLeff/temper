# Silk-to-pad revision (2026-10-08)

The R5 reference moved below the part, to (63.0, 38.95) mm. At 1.0 mm it sat
0.03 mm from C4's pad, below JLC's "Pad To Silkscreen 0.15mm". The move used
`zapote/tools/silk_legend_minimums.py ... --move-field R5 63.0 38.95`.
Nothing else on the board changed.

`native.json` is a fresh export by
`current-sense/tools/extract_current_sense_native.py`. It is identical to
`../silk-legend-2026-10-08/native.json` apart from board identity.
