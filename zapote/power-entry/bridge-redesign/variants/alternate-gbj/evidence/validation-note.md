# GBJ2510-F validation receipt

- Exact part: Diodes Incorporated GBJ2510-F, datasheet `sources/Diodes-GBJ2510.pdf` (SHA-256 `c7d9657711588ecf8d9adf4e1438435d488b21b7733e99caaead3c2490728a02`).
- Physical pin map: pin 1 = PLUS, pins 2/3 = AC, pin 4 = MINUS. The schematic, PCB pads, and source manifest carry this mapping.
- Fresh KiCad netlist proof: `netlist-pin-proof.json` (XML SHA-256 `f951983ef3e264fc97acd901a94404fe79f260a55fd52a947eb843a61fdd70b8`) verifies U1 pin 1=plus, pin 2=ac1, pin 3=ac2, pin 4=minus and the GBJ2510-F value/footprint.
- Fresh source export: `../source-build/resolved-components.json` (SHA-256 `e3afc20a58548ec679b5e0015b46f94bc489fbfbe64307850e3aae2550718dff`); `source-graph-proof.json` verifies all 54 compiler components and both retained graph views against the routed manifest with no identity mismatches.
- Board SHA-256: `fd624e37be053e5140256fcbcb8ab84e330b42d1fbff3a01f92fa8d8a205447b`.
- Native KiCad 10 ERC: 0 errors / 0 warnings (the embedded GBJ symbol and owned symbol library are synchronized).
- Native KiCad 10 DRC: 0 violations, 0 unconnected items, 0 schematic-parity issues (`drc-fresh.rpt`).
- Fresh native and manufacturing extraction: `native-fresh.json`, `manufacturing-fresh.json`; both bind the board SHA above.
- Rust power-entry checks: source graph, stackup, document binding, saved bytes, connectivity, native clearance profile, and nominal model all pass; overall result remains `indeterminate` because the harness does not claim thermal/copper capacity.
- Rust PFC checks: waveform checks pass; branch copper and pad-contact checks remain `indeterminate` pending the coupled Gmsh/Elmer thermal model. No explicit current-screen failure was emitted for this alternate.
- Top/bottom renders: `render/alternate-gbj-top.png`, `render/alternate-gbj-bottom.png`.
- Superseded intermediate extraction files are retained under `history/` and are excluded from acceptance inputs.
