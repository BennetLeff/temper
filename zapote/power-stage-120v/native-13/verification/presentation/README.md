# Native-13 labels and models, 2026-09-27

The owner's native-09 presentation revision, carried onto native-13 (same label file as native-11) and brought
to the JLCPCB legend minimum. The active file is `native-13/section.kicad_pcb`.

- Input: the electrically verified native-13, board SHA-256
  `ce1cf6361d1f30a8345d58b01b3511c695c7212d2c621808bc6dabe5b73960b6`
  (`../README.md`).
- Output: `8056fc952675bc6987bcc9d32c12a88eebc4cec9bc3696f8cbd4876700a39129`.
- Designators: all 135 are on F.Silkscreen at **1.0 mm text / 0.15 mm stroke**,
  which is JLCPCB's minimum; native-09 had 0.8 / 0.12. Positions come from
  `tools/place_reference_labels.py`. It keeps an authored position when the
  larger text clears every pad (≥ 0.2 mm), silkscreen graphic, footprint text,
  other label and the board edge. Otherwise it searches rings within 3.8 mm of
  the courtyard. Result: 21 new labels placed, 55 authored ones moved, and 2
  (R13, R31) kept at their authored spots, which DRC shows are clean.
  `tools/apply_reference_labels.py` now refuses text below the minimum and
  takes the part count from `build-receipt.json`.
- Models: `tools/apply_3d_models.py` with the unchanged `models3d/` maps. The
  21 new parts use KiCad stock models.

| Check | Result | Evidence |
| --- | --- | --- |
| Copper unchanged | Copper-item digest and census identical to the electrical record | `copper.json` vs `../copper.json` |
| Full DRC, three runs | 0 copper findings, 0 silk-over-copper, 0 schematic mismatch; 28 library + 3 silk overlaps (the pre-existing L1/J3 outlines); 1 intended R5 open | `drc-1..3.json` |
| Barrier, parity, copper identity, stackup, JLCPCB | 0 / PASS / PASS / pass / PASS | `barrier.json`, `source-parity.json`, `copper-identity.json`, `stackup.json`, `jlc-dfm.json` |
| Label test | 135 visible, ≤ 4 mm from courtyard, ≥ 1.0 mm / 0.15 mm, metadata hidden | `tests/test_reference_labels.py` |

The remaining silkscreen overlaps are where the L1 and J3 outlines touch. They
merge on the printed legend and have no copper or assembly effect. Trimming
them needs a footprint override or a J3 move, and both would mean a re-route.

Previews: [3D assembly](../../previews/assembly-3d.png),
[reference drawing](../../previews/reference-labels.png),
[front](../../previews/front.png).
