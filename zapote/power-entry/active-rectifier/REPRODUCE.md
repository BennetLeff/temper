# Inspect and reproduce this construction checkpoint

Run from the repository root of this branch. KiCad used here was **10.0.4**,
with its bundled Python/pcbnew. The source compiler was Atopile **0.2.69**.
The strict bridge extension must be fresh before rebuilding native artifacts.

## Current diode-side ECO replay

The current PCB uses `source-04` and the exact feedback ECO recorded in
`evidence/vsense-diode-side-02`. Full fresh-skeleton integration currently
produces unrelated route errors; its failed candidate is retained there.
Do not treat the older construction recipe below as a successful replay of
the current PCB.

To reproduce the precise PCB edit in an empty scratch directory, extract
`zapote/power-entry/active-rectifier/candidate/section.kicad_pcb` from commit
`a2536ee140c8bd368a4bb16a464e36620df2858f`, preserving that relative path.
Its SHA-256 must be `e274d8ad1181f426f731f170e46202e16f969bb751538837a45ee221c3b09ceb`.
Apply `evidence/vsense-diode-side-02/feedback-eco.patch` with `git apply` from
the scratch root. The resulting SHA-256 must be
`a725929a65e1756b0ad36c39373b6ab993335818344a19721cdc4b7c07ef7ab7`.
This exact replay was verified independently. Use the local library tables,
project and freshly generated `source-04` schematic for the checks below.
`routes.json` also records the actual F.Cu feeder, B.Cu polyline and via;
changing its net name alone would have left it pointing at the bank trunk.

## Recheck the committed candidate

```sh
AR=zapote/power-entry/active-rectifier
KICAD=/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli
PCB_PY=/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3
mkdir -p /tmp/zapote-active-recheck
"$KICAD" sch erc --severity-all --format json --output /tmp/zapote-active-recheck/erc.json "$AR/candidate/section.kicad_sch"
"$KICAD" pcb drc --all-track-errors --schematic-parity --severity-all --format json --output /tmp/zapote-active-recheck/drc.json "$AR/candidate/section.kicad_pcb"
"$PCB_PY" zapote/current-sense/tools/extract_current_sense_native.py --repo . --board "$AR/candidate/section.kicad_pcb" --output /tmp/zapote-active-recheck/native.json
cargo build --locked --offline --manifest-path zapote/Cargo.toml -p zapote-harness --bins
# Use the binaries from this checkout's configured shared Cargo target directory.
/Users/bennet/Desktop/temper/target-shared/debug/zapote-board "$AR/candidate/section.kicad_pcb"
/Users/bennet/Desktop/temper/target-shared/debug/zapote-power-entry "$AR/candidate/source-manifest.json" /tmp/zapote-active-recheck/native.json "$AR/candidate/section.kicad_pcb"
/Users/bennet/Desktop/temper/target-shared/debug/zapote-unit-run "$AR/units.json" /tmp/zapote-active-recheck/common "$KICAD" "$PCB_PY" --all
```

The last two commands now evaluate the active contract. They are expected to
report the three TEA package-spacing failures and explicit qualification gaps;
see RUST-INTEGRATION.md. A non-green construction result is intentional evidence,
not a waived failure.
On this host native DRC needed execution outside the sandbox. Library tables and
candidate-libs must remain alongside the board. Do not copy only the PCB file.

Verify retained construction inputs before replay:

```sh
shasum -a 256 -c zapote/power-entry/active-rectifier/evidence/rust-integration-01/construction-inputs.sha256
```

This verifies the committed input set only. An intentional source/layout change
requires a new recorded construction and new evidence; do not call an old
receipt a check of new bytes.

## Construction replay

Use a scratch checkout: these commands overwrite the candidate and stage receipts.
The scripts serialize explicit authored choices; they are not a placer/router.

1. `python3 "$AR/tools/build_source.py" /tmp/zapote-active-source-fresh`
   uses the existing pinned source transport and requires its uv/compiler cache.
   `source-01` and `source-02` retain the failed cache/environment attempts;
   `source-03` is the successful compiled input used for this checkpoint.
2. `.venv/bin/python "$AR/tools/build_native.py" /tmp/zapote-active-source-fresh /tmp/zapote-active-native-fresh`
   uses the existing strict source-to-native bridge, `poses.json`, `outline.json`
   and retained libraries. This emits a skeleton, not the final PCB.
3. **Promote the fresh inputs before integration.** Apply the legacy text
   normalization described below to `/tmp/zapote-active-native-fresh/section.kicad_pcb`.
   Then copy that normalized file to `$AR/native-source-unrouted.kicad_pcb`,
   the fresh `source-manifest.json` to `$AR/candidate/source-manifest.json`, and
   the fresh `candidate-libs/` and `fp-lib-table` into `$AR/candidate/`.
   Copy the unmodified fresh generation manifest to a new evidence file before
   updating final construction metadata. Integration reads these paths directly;
   omitting this promotion would silently replay the old skeleton.
   Use `/tmp/zapote-active-source-fresh` as the schematic source below.
   To replay only the retained construction, skip steps 1–3's promotion and use
   `$AR/source-03` instead. The following commands replay that retained input:
   ```sh
   "$PCB_PY" "$AR/tools/integrate_board.py"
   "$PCB_PY" "$AR/tools/apply_routes.py"
   "$PCB_PY" "$AR/tools/finalize_metadata.py"
   "$KICAD" pcb drc --refill-zones --save-board --all-track-errors --schematic-parity --severity-all --format json --output /tmp/zapote-active-recheck/replayed-drc.json "$AR/candidate/section.kicad_pcb"
   python3 "$AR/tools/draw_schematic.py" --repo . --source "$AR/source-03" --output "$AR/candidate" --receipt /tmp/zapote-active-recheck/schematic-generation.json
   ```
   `integrate_board.py` always starts from the retained passive shunt-repair
   board and `native-source-unrouted.kicad_pcb`, so do not run `apply_routes.py`
   twice without reintegration. The integration preserves baseline stackup,
   removes explicitly named copper, applies source nets/poses, and expands the
   outline. Native zone refill is mandatory; pcbnew's headless zone filler
   crashed on this host.
4. Re-extract native data, rerun checks and render after every modification.
   New pcbnew objects may receive new UUIDs: compare electrical/geometry results,
   not an assertion of byte-identical random IDs. Refresh final construction
   metadata with new checks; never repurpose an older receipt.

Fresh-skeleton integration still has a manual normalization step: generated
legacy `fp_text reference`/`fp_text value` entries conflict with modern properties
in inherited footprints (U8 loaded as REF**). The retained
`native-source-unrouted.kicad_pcb` has those legacy entries removed. Review and
remove those entries from a newly generated skeleton before replacing the
retained one, preserving modern Reference/Value properties and all geometry.
This step is documented, not claimed as an automated end-to-end replay.

The provisional fuse footprint generator uses official KiCad Library Tools
KicadModTree. Mechanical dimensions and allowances remain unverified; regenerating
it is not a mechanical qualification. The existing saved footprint is retained
in both the source library and candidate's local library.
