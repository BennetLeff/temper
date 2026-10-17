# 01 D1 board parasitic extraction — round 4 result

- Board: `native-15/section.kicad_pcb`, SHA-256 `a3ac1249f5052afe52944804cdc3f6ef0e8f895668360e79c1fa7b6fb7322155`
- Date: 2026-09-28; KiCad 10.0.4; FastHenry source commit `363e43ed57ad3b9affa11cba5a86624fad0edaa9`, binary SHA-256 `79c7faac90f8aeb2ac5d805b66f2e4dd70baf3988af0fe3444e3d1fcf83184a4`; agent operator
- Evidence class: native KiCad geometry oracle, analytic calibration, unqualified extraction prototypes
- Verdict: **BLOCKED — software/extraction acceptance**. No board inductance matrix or SPICE include is accepted. This is not evidence of a physical board failure.

## Summary

The native board export was repaired to respect KiCad `FlashLayer`, explicit zone holes, plated barrels and global drill voids. The old round-3 B3 copper export contains 198 distinct net-bearing pad/layer shapes that native KiCad suppresses; its copper and thermal results need re-extraction and re-solve before use. The reported Q3.1/In1 overlap is between an *unflashed* nominal pad and LEG_RET copper, not a board short.

FastHenry's `.units mm` input needs `sigma=5.8e4` for copper at 5.8×10⁷ S/m. The historical fixtures used `5.8e7`, making their resistance 1000 times too small. Corrected independent wire and plane fixtures pass dimensional checks. The fitted 0.125 mm leg-A board prototype still omits 1,327 narrow planar links and 8 barrel spoke landings; its cropped power planes also cross the extraction boundary. No solved board matrix may feed D2 or C1.

## Method and assumptions

- `export_native_copper.py` reads the frozen KiCad board through pcbnew. It exports only pad/via annuli for which native `FlashLayer(layer)` is true and retains physical through-barrels separately. It uses `Unfracture` to expose zone hole rings. `audit_geometry.py` subtracts physical drills from the **final** net/layer union, so a same-net zone cannot refill a PTH bore. The current native export is `extraction/native15-flashed-copper.json.gz`, SHA-256 `fd0b8e6dd5e003543099d6e445e269fa8d73863291409a35828c9b85f17b369d`.
- Copper thicknesses used in prototype decks are F/B 70 µm and internal 61 µm (board stackup). Barrel plating 18 µm is an **estimate**, not a measured finished hole wall. Copper conductivity 5.8×10⁷ S/m is an **assumption** for calibration, not a temperature-adjusted measurement.
- Twelve signed conductive ports per leg separate the bus capacitor branches, switch node, source, returns, gate output, gate resistor-to-gate, and gate return. `port-map.json` records flashed planar layers and the separate physical component-side terminal layer. External capacitors, resistors, MOSFETs and driver channels are not shorted by the copper model. A C38.1 component terminal is on the F-side PTH barrel while its only flashed planar annulus is In2.Cu.
- The diagnostic coupled deck uses an explicit orthogonal edge mesh, eight barrel wall sectors and local pad spokes. The 0.125 mm deck has `nhinc=1` and 10 MHz only. Its finite-width rectangle fitting and crop are unqualified. No numeric board L or R from it is reported as a design input.

## Results

| Check | Result | Evidence |
| --- | --- | --- |
| Native port identity | 24 signed ports across both legs, 13 nets; pad net/XY/flashed-layer checks pass | `port-map.json`, `flash-oracle.json`, `geometry-feasibility.json` |
| Earlier export correction | 2149 → 1859 primitives; 198 distinct net-bearing pad/layer shapes in old B3 export are suppressed by native KiCad | `export-diff.json`, `native-kicad-overlap.json` |
| FastHenry units, 50 mm × 1 mm² copper at 1 Hz | Analytic R = 0.00086206897 Ω; corrected mm and metre decks both give 0.000862069 Ω. Legacy mm deck gives 0.000000862153 Ω | `extraction/solver-units/result.json` |
| Independent 50 × 10 mm, 0.5 mm gap two-plate check at 10 MHz | 20/40/80-grid L = 2.750707/2.947884/3.080333 nH; 40→80 change 4.493%; uniform-current estimate 3.141593 nH. Fine-grid R = 0.00356669 Ω ≥ analytic two-plate DC floor 0.00282646 Ω | `extraction/physical-plane-pair/result.json` |
| 0.125 mm native mask feasibility | A/B have zero component-count and topology mismatches. A/B cell-center counts 225,918/200,139 across net/layers. This is only a raster test, not a field solve. | `extraction/tile-estimate-0p125.json` |
| 0.125 mm fitted coupled leg A deck | 227,732 nodes, 446,853 segments, 51,106,297 deck bytes; 13 true gap-crossing centerlines skipped; 1,327 edges and 8 spokes omitted when fitted width fell below 5 µm. No board solve performed. | `extraction/coupled-a-p0p125-fit-nh1/result.json` |
| Crop boundary | Leg A BUS_P/In2 copper cuts the left/right crop at 18.542/42.400 mm; HV_RET/In1 at 27.890/26.809 mm; SW_A/F at the right by 4.466 mm. Leg B also cuts shared bus and return planes. | `crop-audit.json` |
| 0.0625 mm feasibility | A/B cell-center counts 905,856/799,827 and at least 907,005/800,000 aligned seam connections; no topological mismatch in the raster. This is approximately four times the 0.125 mm mask, before crop enlargement, thickness refinement, or three-frequency solve. | `extraction/tile-estimate-0p0625.json` |

The exact hashed local decks, solver logs, matrices from calibration fixtures and prototype summaries are recorded in `raw-manifest.json` (109 ignored raw files including preserved pre-lint sources, about 83 MiB on disk). Their continued local presence is necessary to rerun the diagnostics. The historical 5/5 fixture match is labelled `HISTORICAL_UNQUALIFIED_REGRESSION_ONLY` in `extraction/fixture-rerun.json`: it checks executable reproduction of the wrong-unit baseline, not physics. Older uncorrected crop/deck outputs are likewise diagnostics only. **No accepted `inductance_matrix.json` or `spice_coupled.inc` exists.**

## Sensitivity and acceptance gap

The 0.125 mm raster repairs component topology, but its finite-width conducting paths do not yet survive the edge/annulus fit. A mesh with some omitted links may still numerically connect its terminals through other routes; that does not prove the correct local current distribution. Crop edges cut substantial native planes, so a matrix from that ROI would also omit spreading and remote tank-current injection. The present SW_A port is the local Q2.3→Q3.2 copper branch; T1.1 at (206.55, 76.08) lies outside its ROI. Separate leg matrices also share BUS_P/HV_RET/LEG_RET copper and cannot simply be summed for simultaneous two-leg excitation.

At 10 and 30 MHz copper skin depths are about 20.9 and 12.1 µm, respectively, smaller than the 61–70 µm layer thickness. `nhinc=1` therefore cannot qualify AC resistance. No passivity, positive-semidefinite R/L, two-mesh self/mutual ≤5% check, enlarged-crop sensitivity, 1/10/30 MHz sweep, or package-inductance double-count check has been completed for a board matrix. The validated two-plate fixture is not a substitute for any of these board-specific gates. The source and binary hash checks in the physical fixture scripts fail closed on a changed solver.

## Open items and physical confirmation

1. Replace the approximate rectilinear planar/annulus contact mesh with a native-conductor-contained mesh that preserves every narrow connection and proves bore/antipad exclusion. Check every emitted finite-width element against native KiCad copper, then re-audit each signed port and full 3-D connectivity. Calibrate pad spokes and 18 µm assumed plating against known via structures or measured plating.
2. Extend each ROI until boundary currents and every material self/mutual term change by less than the D1 tolerance, or solve the full relevant nets with an explicit boundary/current-source model. Include remote switch-node branches if the claimed tank path requires them.
3. Solve two in-plane meshes and thickness refinements at 1, 10 and 30 MHz. Extract the complete R+jωL matrix with an unambiguous current-reference convention. Check reciprocity, passivity, positive semidefiniteness, convergence, package separation and external component insertion before creating a D2/C1 include. Retain the bulk/local capacitor ESL 5–20 nH as a separately labelled assumption until sourced.
4. Measure actual switch-node and Kelvin source Vgs/Vds simultaneously on prototype hardware under controlled current before deciding the false-turn-on cause or a gate-drive change. This D1 software block alone makes no safety or hardware verdict.

Round-3 B3 copper/thermal findings that used the old export should be regenerated after `FlashLayer`/bore correction. The audit identifies affected power nets BUS_P, HV_RET, LEG_RET, SW_A and SW_B, but does not establish the magnitude or direction of their numerical changes.

## Reproduce

Run from this directory. `FASTHENRY` points to the pinned built executable; the physical fixtures reject a different source commit or binary. The board and round-3 input hashes are checked by the scripts. KiCad's Python is needed only for the native export/oracle; Miniforge Python has the Shapely/Numpy analysis dependencies.

```sh
FASTHENRY=/tmp/ps-r3-decision.5sy79t/fieldsolver/FastHenry2/bin/fasthenry
KIPY=/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3
PY=/Users/bennet/Miniforge3/bin/python3
$KIPY export_native_copper.py --board ../../../../native-15/section.kicad_pcb --output extraction/native15-flashed-copper.json.gz
$KIPY verify_flash_export.py --board ../../../../native-15/section.kicad_pcb --export extraction/native15-flashed-copper.json.gz --output flash-oracle.json
$KIPY verify_kicad_overlap.py --board ../../../../native-15/section.kicad_pcb --output native-kicad-overlap.json
$PY audit_geometry.py
$PY audit_export_diff.py
$PY audit_crop.py
$PY validate_solver_units.py --solver "$FASTHENRY"
$PY validate_plane_pair.py --solver "$FASTHENRY"
$PY estimate_tiling.py --pitch 0.125
$PY estimate_tiling.py --pitch 0.0625
$PY build_coupled_prototype.py --solver "$FASTHENRY" --pitch 0.125 --fit-width
$PY write_raw_manifest.py
```

The last build command creates and audits an **unqualified** deck; do not add `--solve` or use a resulting Z matrix as board inductance. `run_fixtures.py` is a separate, explicitly historical wrong-unit executable-regression check. `raw-manifest.json` has the exact source/deck/log SHA-256 values. Raw runs stay ignored under `extraction/`; the compact JSON reports and scripts are the handback.

Coordinator integration preserved original scripts and manifest under ignored `extraction/source-before-lint/`, removed unused imports, normalized import ordering, renamed unused loop variables and made existing `zip(strict=False)` defaults explicit. The independent wire fixture was rerun and reproduced its numerical result; the current manifest binds the cleaned sources. These edits do not qualify any board prototype.
