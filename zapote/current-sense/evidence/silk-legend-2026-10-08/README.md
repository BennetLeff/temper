# Silk legend revision (2026-10-08)

The candidate board's silkscreen text was raised to JLCPCB's legend minimums
(1.0 mm height, 0.15 mm stroke) by `zapote/tools/silk_legend_minimums.py`
under `fab-profiles/jlcpcb-2layer-2oz.json`. Nothing else on the board changed.

`native.json` is a fresh export of the revised board by
`current-sense/tools/extract_current_sense_native.py`. The same extractor gives
identical output for the previous board, apart from board identity, so silk
changed no measurement. The previous export stays where it was, as history.

`composite.json` was built by `cargo run -p zapote-harness --example
current_sense_input` from the unchanged source manifest, profile and model and
this export. With the previous export, the same command reproduces
`../acceptance-stackup-v2/input.json` byte for byte.
