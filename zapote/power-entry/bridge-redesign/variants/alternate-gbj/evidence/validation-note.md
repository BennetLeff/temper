# GBJ2510-F validation receipt

- Exact part: Diodes Incorporated GBJ2510-F, datasheet `sources/Diodes-GBJ2510.pdf` (SHA-256 `c7d9657711588ecf8d9adf4e1438435d488b21b7733e99caaead3c2490728a02`).
- Physical pin map: pin 1 = PLUS, pins 2/3 = AC, pin 4 = MINUS. The schematic, PCB pads, and source manifest carry this mapping.
- Board SHA-256: `fd624e37be053e5140256fcbcb8ab84e330b42d1fbff3a01f92fa8d8a205447b`.
- Native KiCad 10 ERC: 0 errors / 0 warnings (the embedded GBJ symbol and owned symbol library are synchronized).
- Native KiCad 10 DRC: 0 violations, 0 unconnected items, 0 schematic-parity issues (`drc-fresh.rpt`).
- Fresh native and manufacturing extraction: `native-fresh.json`, `manufacturing-fresh.json`; both bind the board SHA above.
- Rust power-entry checks: source graph, stackup, document binding, saved bytes, connectivity, native clearance profile, and nominal model all pass; overall result remains `indeterminate` because the harness does not claim thermal/copper capacity.
- Rust PFC checks: waveform checks pass; branch copper and pad-contact checks remain `indeterminate` pending the coupled Gmsh/Elmer thermal model. No explicit current-screen failure was emitted for this alternate.
- Top/bottom renders: `render/alternate-gbj-top.png`, `render/alternate-gbj-bottom.png`.
