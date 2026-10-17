# Validation and replay

From the repository root:

```sh
CARGO_TARGET_DIR=/private/tmp/zapote-rtd-target make -C zapote check
CARGO_TARGET_DIR=/private/tmp/zapote-rtd-target cargo run --manifest-path zapote/Cargo.toml --bin zapote-thermal -- zapote/thermal-sense/candidate/source-manifest.json zapote/thermal-sense/evidence/native-final.json zapote/thermal-sense/sensor-contract.json
```

The thermal CLI is strict: PASS exits 0; FAIL or INDETERMINATE exits 1. The digital milestone permits zero hard findings with explicit qualification gaps; it does not turn INDETERMINATE into PASS. Inspect individual findings rather than swallowing command failures. `make check` runs regressions and common saved-board gates; it is not full electrical qualification.

Rust covers exact component/value/sensor identities, complete source and native pin-net topology and connectivity, strict source mapping, conditional trip/release calculations, physical stackup, saved-document binding, 0.2 mm copper spacing and ≤5 mm bypass-to-supply pad-centre locality. Locality is not extracted loop impedance. Native pad shapes, zones and connectivity are trusted from the pinned KiCad extractor; shared binding checks do not independently reconstruct every field. Native ERC/DRC/parity provides a separate check.

`tools/build_source.py NEW_DIRECTORY` compiles with Atopile 0.2.69. `tools/build_native.py NEW_DIRECTORY` consumes successful `source-build-01`, poses and outline to produce the strict unrouted skeleton. Retain the successful build's `.net`, `.csv`, layouts and manifest even though general repository ignore rules match `build/`.

Native initialization and source-field synchronization reuse current-sense adapters. Shared `zapote/tools/refresh_native_footprints.py` reloads original KiCad library footprints, preserving source identity and requiring unchanged native pad centres. This preserves real library metadata, pad body orientation and text semantics. Then `zapote/rtd/apply_routes.py` applies explicit `routes-02.json` vertices and zone definitions transactionally. `tools/finish_board.py` sets fabrication text; `tools/draw_schematic.py` emits the functional schematic. `zapote/current-sense/tools/extract_current_sense_native.py` extracts final evidence; the existing source/schematic oracle verifies all pin nets.

`routes-01.json` is a rejected adapter-schema attempt: it used `at_mm` where vias require `position_mm`. No partial board was saved. The first valid routing had only silk findings; text fixes are retained separately from final evidence. Final native results are `evidence/final-native-01..03/` with all severities, all track errors and schematic parity enabled.

The native library roundtrip test runs in KiCad's Python. It uses a 37° asymmetric native placement, verifies native pad positions/body angles/net preservation, and rejects a 0.1 mm displaced pad without changing board bytes. No independent trigonometric convention is used as its oracle.

After any source, board or model edit, regenerate the relevant evidence and freeze a new manifest. Existing unit manifests describe their historical bytes; shared harness evolution does not retroactively recertify their old receipts. No claim is made of 100–1000 times commercial CAD coverage: the gain demonstrated here is specific source/model/geometry consistency checks and defect controls.
