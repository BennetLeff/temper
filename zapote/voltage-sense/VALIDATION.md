# Validation scope and replay

From the repository root:

```sh
CARGO_TARGET_DIR=/private/tmp/zapote-rtd-target make -C zapote check
CARGO_TARGET_DIR=/private/tmp/zapote-rtd-target cargo run --manifest-path zapote/Cargo.toml --bin zapote-voltage -- zapote/voltage-sense/candidate/source-manifest.json zapote/voltage-sense/evidence/native-final.json
```

**The voltage CLI is strict:** PASS exits 0; FAIL or INDETERMINATE exits 1. The accepted digital milestone currently returns INDETERMINATE with **zero fail findings**, because physical/model applicability gaps remain. This is deliberate and tested at the command boundary. Do not use an unconditional `|| true` to accept a future report; inspect its rule statuses. `make check` runs regression tests and the common saved-board gates; it does not assert full electrical qualification.

The common `zapote-board` CLI hashes and checks actual saved board bytes, including explicit physical stackup consistency. RTD, current-sense and voltage boards are registered. Missing data fails closed. Buck's legacy frozen PCB has no explicit stackup and is not silently grandfathered as passing this new gate; it remains outside this maintained-unit registry.

Voltage Rust checks cover exact 17-component MPN/value identities, all 42 source/native pin nets, strict pin mapping, complete native connectivity clusters, source-derived ADC and OVP bounds, top-resistor normal/single-short stress, the 1.6 mm stackup, fabrication copper spacing at 0.2 mm, and ≤5 mm supply/reference capacitor pad-centre locality. The latter is a placement check, not an extracted loop-inductance certificate. KiCad's separate ERC/DRC/parity checks use full severity and all track errors.

Saved-document binding compares component MPN/pad nets and complete straight-trace/via UUID/geometry/net censuses against embedded KiCad bytes. It rejects rehashed contradictory board/export pairs. World pad shapes, zone geometry and copper connectivity are still supplied by the pinned native KiCad extractor; this is an explicit trust boundary, not independent verification of every export field. The binding entrypoint currently supports this KiCad 10 board format and rejects arcs. Whole-cooker isolation, EMI, analog accuracy and protection timing are outside these construction checks.

## Construction replay

`tools/build_source.py NEW_DIRECTORY` compiles with pinned Atopile 0.2.69 using the existing adapter. `tools/build_native.py NEW_DIRECTORY` consumes retained successful `source-build-04`, exact poses/outline and strict export. Native output is an unrouted source-derived skeleton. It is not the final candidate.

The candidate then uses existing native initialization, source-field sync, explicit `routes-02.json` application and zone fill. `tools/refresh_native_footprints.py` reloads original native library footprints and refuses any change in routed pad centres, restoring library metadata/pad/text semantics lost by the skeleton transport. It changes footprint UUIDs while preserving source instance/reference/path, net assignment and copper positions. `tools/draw_schematic.py` authors the final functional drawing; the source-netlist oracle independently checks it. See receipts for exact commands/inputs. Earlier route/library attempts are retained as rejection evidence, not replay acceptance.

Use `zapote/current-sense/tools/extract_current_sense_native.py` after any PCB edit, then rerun Rust, source/schematic equality and native checks. A changed hash requires a new evidence manifest. Native reports alone do not bind later edits. Final native checks are under `evidence/final-native-01..03/`; obsolete attempts remain explicitly separate.

No claim is made that Zapote already has 100–1000 times another CAD tool's coverage. The demonstrated gain here is enforcing source/model/document consistency and retaining specific negative controls.
