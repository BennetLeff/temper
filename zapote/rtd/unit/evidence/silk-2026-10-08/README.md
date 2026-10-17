# RTD silk revision (2026-10-08)

The board's silkscreen now meets JLCPCB's legend and pad-to-silkscreen minimums:
- 40 texts raised to 1.0 mm high with a 0.15 mm stroke, keeping character width
  (`zapote/tools/silk_legend_minimums.py`, `fab-profiles/jlcpcb-4layer-1oz.json`);
- J2's silk outline, pin-1 chamfer and marker moved 0.1 mm clear of its pads,
  on the board and in the vendored `candidate-libs` footprint
  (`../../silk_pad_clearance_2026_10_08.py`).

Copper, pads and nets are unchanged. The source manifest still describes the
source-build input. The vendored J2 footprint now differs from that input in
silkscreen only.

- `native.json`: a fresh `rtd/native_measure.py` export. Every measurement equals
  `../return-rust-01/native.json`; only board and extractor identity differ.
- `acceptance-input.json`: `../acceptance-final/input.json` re-bound to this export
  by `zapote/tools/rebind_composite.py`, which refuses unless the measurements are equal.
- The model qualification was replayed against it into
  `rtd/model-correctness/qualified-input-silk-2026-10-08/`; see `REPLAY.md`.
