# Step 0: four-layer assumptions in the native-21 toolchain (read-only audit, 2026-10-14)

Nothing was run. Two findings were re-checked by hand: `prototype-closure/pcb/build_native21.py:148` copies
`native-20/stackup.json` over `native-21/stackup.json` on every build (the two are identical), and B3
`thermal.py:43` reads `native-17/stackup.json` and at :368 drops via barrels on any layer not in `CU_INDEX`, silently.

## Where the stack comes from
`build_native21.py` (lines 6, 30, 75, 148) takes the layer table and `(stackup ...)` from `native-20/section.kicad_pcb`
(KiCad-9 ids F 0, In1 4, In2 6, B 2; dielectrics 0.4355 / 0.5 / 0.4355). Editing `native-21/stackup.json` alone is
reverted by the next build. Six layers need the builder to write the stackup from native-21's own file.

## By effort
| Effort | File | Assumption |
|---|---|---|
| HARD | `validation-plan/sim-kit/04-current/sheet_solver.py:57-61, 296-311` | `LAYER_Z_MM` fixed to JLC041622-7628; In3 / In4 raise KeyError in via-barrel splitting (drives Kelvin and task 04) |
| HARD | `validation-results/04-board-current-thermal/round5-native21/b3/thermal.py:40-49, 273, 368, 387-435` | seven fixed sheets, `CU_INDEX` {0, 2, 4, 6}, reads native-17's stackup; unknown layers silently dropped (`b3_c28_h25_peak_C`) |
| HARD | `validation-results/02-protection-timing/coil-pickup/s21b/loops.py:19-20` | `Z` for F / In1 / In2 / B = 0.47 / 1.03 / 1.50 mm (does not match stackup.json; to reconcile) |
| HARD | `.../coil-pickup/s21b/run_ocp.py:10-11, 21-24, 56-81` | F8 loops: In1 = KELVIN_P pour, In2 = KELVIN_N image return |
| HARD | `native-21/layout/gates/return_path19.py:10-11, 46-50, 213` | `ADJ` reference table from the 0.4355 / 0.5 dielectrics |
| HARD (roles) | `native-21/layout/patches21.py` (317 hits), `incr21.py:351, 639-665`, `route21.py:137, 263` | In1 = hv_ret / leg_ret / n_ls / ocp_kelvin_p / v3v3; In2 = bus_p / selv_gnd; `L4` / `CU4` tuples |
| MODERATE | `gates/xfer_spots.py:12-15, 44`, `gates/bypass_check.py:9, 26, 41-46`, `audit.rs:901` (comment) | In1 v3v3 / In2 selv_gnd planes 0.5 mm apart |
| MODERATE | `validation-results/02-protection-timing/kelvin/kelvin_plane.py:17, 113, 126`; `round5-native21/run_board.py:43-45, 67` | 70 / 61 um copper; z from the sheet solver |
| MODERATE | `round5-native21/summarize.py:41, 140` | `order` dict F..B; In3 breaks the sort |
| MODERATE | `08-manufacturing-package/native-21/stage18-res-a-creepage/res_a_creepage18.py:16-20, 40-42` | OUTER / INNER tuples; the through-laminate argument to re-run with two more inner layers |
| MODERATE | `02-protection-timing/shoot-through-f1/f1_containment.py:44, 288-289` (imported by `s21_necks.py`) | `CU_T` by four names |
| MODERATE | `native-21/layout/plan_board_only21.py:84-88` | SELV inner pours = (In1, In2) |
| TRIVIAL | `apply_copper21.py:36, 67, 101`, `tools/export_power_copper.py:32`, `gates/chain.sh` (Gerber --layers), `gates/trim_tails.py:191`, `plot_copper.py:68` (2x2 grid), `geom21.py`, `maze21.py`, `place.py`, `rules21.py`, `barrier21.py`, `tools/jlc_dfm_check.py:18, 37` | layer lists, size limit text |
| docs | `native-21/stackup.json`, `FAB-JLCPCB.md`, `fab/FAB-NOTE.md`, `owner-items/order/ORDER-PACKAGE.md`, `native-21/FLOORPLAN.md` | "JLC041622-7628", "4 layers" |
| none | `write_rules21.py` / `section.kicad_dru` (`(layer outer)`), `dump_pads.py`, `tools/copper_dump.py` (`CuStack()`), barrier gates (Python and `zapote-drc/src/power_barrier.rs`), `fill_hash.py`, `scorecard.py`, `d5_audit.py`, `via_in_pad.py`, `verify_source.py`, `kelvin_budget.py`, `review_fab.py`, `bom_cpl_jlc.py` | layer-count agnostic |

## Refactor before any six-layer pass (behaviour-neutral on four layers; prove it by re-scoring s32 unchanged)
1. `native-21/stackup.json` is the single source: ordered copper names, thicknesses, z-centres, plane roles.
   `build_native21.py` writes `(layers)` / `(stackup)` from it and stops copying native-20's.
2. `native-21/layout/layers21.py` exports `CU`, `OUTER`, `INNER`, `Z_MM`, `T_UM`, `ADJ` (nearest-first from z) and
   `PLANE_ROLE`; the layout scripts, gates, `export_power_copper.py` and chain.sh's Gerber list use it.
3. The sheet solver, B3, `loops.py` and `f1_containment.py` take z and thickness from the stackup.
4. Fail loudly on unknown layers (B3 :368 filter, `summarize.py` order) instead of dropping them.
5. Planes looked up by role, not layer name.
The refactor is worth doing even if six layers is rejected: B3 reading native-17's stack and silently dropping
layers is a latent error.
