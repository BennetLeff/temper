# Validation and replay

From the repository root:

```sh
CARGO_TARGET_DIR=/private/tmp/zapote-rtd-target make -C zapote check
CARGO_TARGET_DIR=/private/tmp/zapote-rtd-target cargo run --manifest-path zapote/Cargo.toml --bin zapote-thermal -- zapote/thermal-sense/candidate/source-manifest.json zapote/thermal-sense/evidence/native-final.json zapote/thermal-sense/sensor-contract.json
```

The thermal CLI is strict: PASS exits 0; FAIL or INDETERMINATE exits 1. The digital milestone permits zero hard findings with explicit qualification gaps; it does not turn INDETERMINATE into PASS. Inspect individual findings rather than swallowing command failures. `make check` runs regressions and common saved-board gates; it is not full electrical qualification.

Rust covers exact component/value/sensor identities, complete source and native pin-net topology and connectivity, strict source mapping, conditional trip/release calculations, physical stackup, saved-document binding, 0.2 mm copper spacing and ≤5 mm bypass-to-supply pad-centre locality. Locality is not extracted loop impedance. Native pad shapes, zones and connectivity are trusted from the pinned KiCad extractor; shared binding checks do not independently reconstruct every field. Native ERC/DRC/parity provides a separate check.

`tools/build_source.py NEW_DIRECTORY` compiles with Atopile 0.2.69. `tools/build_native.py NEW_DIRECTORY` consumes successful `source-build-02`, poses and outline to produce the strict unrouted skeleton. Retain the successful build's `.net`, `.csv`, layouts and manifest even though general repository ignore rules match `build/`.

Native initialization and source-field synchronization reuse current-sense adapters. Shared `zapote/tools/refresh_native_footprints.py` reloads original KiCad library footprints, preserving source identity and requiring unchanged native pad centres. This preserves real library metadata, pad body orientation and text semantics. Then `zapote/rtd/apply_routes.py` applies explicit `routes-05.json` vertices and zone definitions transactionally. `tools/finish_board.py` sets fabrication text; `tools/draw_schematic.py` emits the functional schematic. `zapote/current-sense/tools/extract_current_sense_native.py` extracts final evidence; the existing source/schematic oracle verifies all pin nets.

`routes-01.json` is a rejected adapter-schema attempt: it used `at_mm` where vias require `position_mm`. No partial board was saved. The first valid routing had only silk findings; text fixes are retained separately from final evidence. Final native results are `evidence/final-native-revb-01..03/` with all severities, all track errors and schematic parity enabled.

The native library roundtrip test runs in KiCad's Python. It uses a 37° asymmetric native placement, verifies native pad positions/body angles/net preservation, and rejects a 0.1 mm displaced pad without changing board bytes. No independent trigonometric convention is used as its oracle.

After any source, board or model edit, regenerate the relevant evidence and freeze a new manifest. Existing unit manifests describe their historical bytes; shared harness evolution does not retroactively recertify their old receipts. No claim is made of 100–1000 times commercial CAD coverage: the gain demonstrated here is specific source/model/geometry consistency checks and defect controls.

## Rev B open-wire controls

The source now has 27 components, 76 pins and 13 nets. `evidence/rust-final-revb.json` records the current model report. Native final evidence is `evidence/native-final.json` (also retained as `native-final-revb.json`). Rev A's candidate and reports remain under `revisions/reva/`; its original Git commit is the authority for historical manifest paths.

Rev B routing attempts 03 and 04 are retained with failing native reports. Attempt 05 resolves the crossings, refills the native ground zone and passes all native checks. Exact final input bytes are recorded in `evidence/final-manifest-revb.json`; `final-manifest.json` is historical Rev A evidence.

New Rust controls reject the old 17-component census, the 3.32kΩ coil bias, reversed open-comparator input, an unsafe rail threshold, oversized filter capacitance and altered qualification allowances. The settling control must fail the electrical timing rule, not only the exact-part rule. Independent numerical references check the new coil hot thresholds and open/cold margins. Fault cases compute comparator voltages for both prior HOT states before the OR result.

Replaying uses the saved poses and explicit route vertices; an agent still owns changes in placement and routing. The validators accept or reject the saved result. Native zone filling is `pcbnew.ZONE_FILLER(board).Fill(board.Zones())`, followed by native save and extraction.

For bench qualification, use resistor substitution at J1/J2 across the modeled supply range: valid 0 °C/25 °C resistance, heating trip/release, open each lead, short to ground/supply, and reconnect. Measure each FAULT pin and SENSE rise time from a discharged filter. Keep the heater disconnected. Characterize added cable/receiver leakage and capacitance before relying on the 10 ms model. These tests remain NOT RUN.
