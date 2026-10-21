# Revision D verification receipt

Verified on 2026-10-20 with KiCad 10.0.4. Board SHA256:

`eb2b4cf88b29e294e98f1766a12dccc939111215430d9607c3cb765b6c7ed8dc`

Rev D is the Rev C board plus R94 (22 Ω R_iso), R95/R96 (1 Ω LDO inputs), R83 = 1.74 MΩ and ±12 V rail monitors; see `../docs/rev-d-decision.md`. Rows marked *Rev C* were produced on the Rev C board (SHA256 `5ec3e6e0…`) and cover circuitry Rev D did not change.

| Check | Result | Evidence |
|---|---|---|
| Native schematic ERC, all severities | 0 violations across six sheets | `erc.json` |
| Native PCB DRC, all track errors and schematic parity | 0 violations,0 unconnected,0 parity findings | `drc.json` |
| Independent audit (Rev D) | 576 source pins = native pads = exported netlist; no non-GND In1 copper; OPA2810/THS4551 input relief on In1/In2/B; bypass 2.031–2.050 mm; R_iso topology | `independent-verification-rev-d.json` (`python independent_check.py D` with KiCad Python) |
| Independent native audit (*Rev C*) | Separate checks on the Rev C frozen board | `independent-erc-rev-c.json`, `independent-drc-rev-c.json`, `independent-layout-rev-c.json` |
| Source/schematic/PCB pin and part parity | 184 fitted components match | `cad-bom-parity.json` |
| Native coordinates and audited CPL rotations | 173 SMT placements, 55 BOM lines match | `cad-bom-parity.json`, `placement-library-audit.md` |
| Ground/analog layout | No non-GND In1 tracks; OPA/FDA signal relief and compact feedback preserved | `independent-layout-rev-c.json` |
| Via/SMT drill intersection audit | 15 intended filled/capped vias; no unexpected intersections | `via-in-pad-process.json` |
| Manufacturing exports and visual review | Four copper layers, masks, paste, silk, outline, PTH/NPTH drills and six schematic pages | `visual-review.json` |
| Firmware and host | D-riso22 identity; feedback 22 Ω + RF‖100 pF; calibration schema 5; RAILS gross-fault check; firmware build, PIO and boxcar checks, hot loop 88/120 cycles; 29 Rust tests and Clippy pass | `../firmware/verification/`, `../host/verification/` |
| Coupled amplifier simulation (*Rev C*) | True DC, AC and transient data, exact models, negative false-OP regression and declaration-order identity checks | `solver-resolution-fixed-local/README.md` |
| Return-ratio method | Bilateral matrix de-embedding, analytic stable/unstable controls, complete crossing enumeration, independent controlled-source cuts | `stability-full-chain/` |
| FDA model/corner cross-check (*Rev C*) | Current and original TI models,134 standalone cases; selected-network minimum59.19° | `fda-independent/README.md` |
| Bounded switched ADC load (*Rev C*) |640ns acquisition recovery below half-LSB comparison threshold;140ns negative control fails; actual input/CM windows checked | `adc-switched-load/README.md` |

The complete analog scope and acceptance results are in [the revision C report](../docs/analog-validation-rev-c.md). Raw data, logs and generators distinguish numerical convergence, loop margin, finite-time boundedness and acquisition recovery. None establishes physical-board accuracy, noise, process/temperature corners or arbitrary fixture stability. The original false operating point and the superseded FDA topology are retained as labelled historical evidence; they are not accepted manufacturing circuits.

The project has no custom ERC/DRC exclusions or suppressed error severities. KiCad's default inactive categories remain listed in its JSON reports. Geometry checks do not replace measured signal integrity.

The firmware verifier checks 120-cycle sampling frames,16 serial clock edges, dual-lane bit order, count bounds and late-READY handling. USB enumeration, ADC pattern acquisition and DUT measurements require hardware. Source settling remains 1 second. The host requires revision D-riso22 calibration identity and uses complex feedback impedance, including R94, on all ranges.

The board requires four-layer resin-filled, copper-capped, planarized via-in-pad processing. Vendor DFM acceptance and final placement preview remain ordering steps. Solder inspection, rail/startup checks, all-range scope tests, source-off noise measurements and independent calibration standards remain physical qualification. No manufacturer upload or purchase has occurred.

The package SHA256 manifest pins the delivered files. Revisions A and B are separately archived and superseded; Rev C is superseded by D (snapshot commit ff1ffb45b).
