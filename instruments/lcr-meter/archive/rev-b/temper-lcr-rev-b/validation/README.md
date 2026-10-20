# Revision B verification receipt

Verified on 2026-10-20 with KiCad 10.0.4. Board SHA256:

`15546293b47b16b7edba8a79bdc3feafe582b2b85618be469d930ba27e1816d9`

| Check | Result | Evidence |
|---|---|---|
| Native schematic ERC, all severities | 0 violations across six sheets | `erc.json` |
| Native PCB DRC, all track errors and schematic parity | 0 violations, 0 unconnected items, 0 parity findings | `drc.json` |
| Independent native ERC/DRC run | Same zero findings on the same board hash | `independent-erc-final.json`, `independent-drc-final.json` |
| Source/schematic/PCB pin and part parity | 167 fitted components match | `cad-bom-parity.json` |
| Native coordinates and audited CPL rotations | 156 SMT placements, 52 BOM lines match | `cad-bom-parity.json`, `placement-library-audit.md` |
| Inner ground reference | No non-GND In1 tracks; intentional amplifier relief retained | `independent-layout-final.json` |
| OPA2810 layout geometry | All 12 signal-pin centers relieved on underlying copper; four added 10 nF bypass caps 2.031–2.050 mm from supply pads | `independent-layout-final.json` |
| Via/SMT drill intersection audit | 13 intended filled/capped vias; no unexpected intersections | `via-in-pad-process.json` |
| Manufacturing export and visual review | Four copper layers, masks, paste, silkscreen, outline, plated/non-plated drills and six schematic pages inspected | `native-export-log.txt`, `visual-review.json` |
| Firmware build and UF2 | Official Pico SDK build succeeds; UF2 layout and assembled PIO timing verified | `../firmware/verification/` |
| Rust host | 10 tests pass; Clippy passes; binary/source hashes verified | `../host/verification/` |
| Analog simulation | Bounded source, range/feedback and filter models recorded; full coupled model convergence not established | `spice-rev-b/results.md` |

The project has no custom ERC/DRC exclusions or suppressed error severities. KiCad's default inactive check categories are explicitly listed in the native JSON reports. Geometry checks are not a substitute for measured signal integrity or analog accuracy.

The firmware verifier checks exact 120-cycle sampling frames, 16 serial clock edges, dual-lane bit order, count bounds and late-READY fault handling. USB enumeration, ADC pattern acquisition and real DUT measurements still require the fabricated board. Source settling is 1 second after excitation changes.

The manufacturing files require four-layer resin-filled, copper-capped, planarized via-in-pad processing. Vendor DFM acceptance, final placement preview, solder inspection, rail checks, stability tests, source-off noise measurements and calibration with an independent check standard remain physical qualification steps. This package does not claim a calibrated accuracy, milliohm ESR resolution, mains safety qualification or TI's reference-design performance.

All receipt files and manufacturing artifacts are included in the package SHA256 manifest. Revision A reports are retained only in the separate archive.
