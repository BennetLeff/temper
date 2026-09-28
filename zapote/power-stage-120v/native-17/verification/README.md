# Native-17 verification, 2026-09-28: through-hole outer lands restored

Native-15 could not be assembled. **23 of its 116 plated through-hole pads
had no copper on either outer layer** (C38–C41, the J8/J10 studs, J3.2,
J4.3/4.7/4.8, PS2.2, D1.2, D2.2), and another 65 lacked one outer land. The
round-4 review (D1's native `FlashLayer` audit) exposed it.

**Cause.** `scripts/gen_pcb_skeleton.py` loaded footprints with kiutils 1.4.8,
which sets `removeUnusedLayers` when the token is present, so KiCad 7+'s
`(remove_unused_layers no)` became true and was written as a bare
`(remove_unused_layers)`, without `keep_end_layers`. KiCad then removed every
unconnected layer, outer ones included. Every power-stage board since native-08
carried it; KiCad's DRC and our JLCPCB check both accepted it.

**Fixes.**
- `scripts/gen_pcb_skeleton.py::_load_footprint` reads both flags by value
  (tests: `scripts/tests/test_gen_pcb_skeleton_pad_flags.py`). The generator
  is shared with the current-sense, thermal-sense, gate-drive and interlock
  builds; the RTD, thermal-sense and current-sense candidate boards also
  carry the old flag and need their own rebuild.
- `tools/pth_layer_policy.py` (run by `tools/build_native.py`) sets a
  deliberate policy on every PTH pad: **keep both outer lands, remove inner
  rings where nothing connects** (`remove_unused_layers yes`,
  `keep_end_layers yes`). The earlier routing depended on absent inner rings
  for mains/HOT spacing; keeping them absent on purpose preserves that
  insulation, while every pad gets its solder lands.
- `tools/jlc_dfm_check.py` now fails any PTH pad without copper on both
  F.Cu and B.Cu (tests: `tests/test_jlc_dfm_outer_lands.py`). On native-15
  it reports 88 failures.

**Reroutes forced by the restored outer lands** (`tools/routes.py`,
`tools/routes_aux.py`):
- J1.1/J1.2 mains tracks start on the far side of their own pad (3.48 mm L–N).
- AC neutral's main-current B.Cu run between J1 and F1 is **3.0 mm** (was
  3.6 mm), centred to leave 3.325 mm to each line land; its In2 parallel stays
  3.6 mm. About 14 % less neutral copper in that channel; task 04 should
  re-screen it.
- J3 L_FILT stub moved 0.25 mm; the REF25 feed to U5 moved 0.15 mm off C41;
  a LEG_RET track now goes around D2.2 instead of through it (it was a short
  once D2.2 had its F.Cu land).

Native-16 is the placement. Against native-14 only the pad flags differ;
poses, pads and footprints are identical, and the placement metrics are
identical.

Electrical board SHA-256: `33fe1cffedd2478941a8cfe628d80e02e3787221f12bd85044400fbe46f54d66`.
The active board is the presentation revision (labels and 3D models),
`16e8b70bb7f2bc9020ea574022c13661cd09640ca3a52db1ff43f9f6db976162`, with copper
identical to the electrical board.

| Check | Result |
| --- | --- |
| PTH outer lands | 116/116 on both F.Cu and B.Cu (native-15: 28/116) |
| Full DRC, fill + three repeats | 0 copper findings, 0 schematic mismatch; 3 L1/J3 silk overlaps; 36 library notices (the pad policy intentionally differs from stock footprints); board stable |
| Opens | Only the intended R5 Kelvin split; pad clusters identical to native-15 |
| Barrier | 0 (Rust) and 0 (pinned oracle) |
| Parity / copper identity / stackup / JLCPCB (with the new outer-land gate) / hardware surface | PASS / PASS / pass / PASS / 0 hits |
| Power screens | Unchanged (0.886 / 0.457) |
| Presentation board | Copper identical; same DRC counts and gates; 135 labels, 24 models |
| Board tests | 46/46 (retargeted to native-16/17; 2 new) |

Copper exports made with `IsOnLayer` (the round-2 export used by round-3 A4,
B3 and the solver topology check; `tools/copper_dump.py`) count every pad on
every layer. That was wrong for native-08..15, and remains an over-count of
unconnected inner rings on native-17. The barrier check is unaffected in
direction (it only ever sees more copper). Copper-current and thermal work
must use a `FlashLayer`-aware export.

Not a fabrication or powered-operation release.
