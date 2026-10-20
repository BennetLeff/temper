# Revision C verification receipt

Verified on 2026-10-20 with KiCad10.0.4. Frozen board SHA256:

`5ec3e6e067f73a08efbb5d3a82cc95439b8d753906139bb5f17a92de7c31a9c0`

| Check | Result | Evidence |
|---|---|---|
| Native schematic ERC, all severities | 0 violations across six sheets | `erc.json` |
| Native PCB DRC, all track errors and schematic parity | 0 violations,0 unconnected,0 parity findings | `drc.json` |
| Independent native audit | Separate checks on the same frozen board | `independent-erc-rev-c.json`, `independent-drc-rev-c.json`, `independent-layout-rev-c.json` |
| Source/schematic/PCB pin and part parity |175 fitted components match | `cad-bom-parity.json` |
| Native coordinates and audited CPL rotations |164 SMT placements,53 BOM lines match | `cad-bom-parity.json`, `placement-library-audit.md` |
| Ground/analog layout | No non-GND In1 tracks; OPA/FDA signal relief and compact feedback preserved | `independent-layout-rev-c.json` |
| Via/SMT drill intersection audit |15 intended filled/capped vias; no unexpected intersections | `via-in-pad-process.json` |
| Manufacturing exports and visual review | Four copper layers, masks, paste, silk, outline, PTH/NPTH drills and six schematic pages | `visual-review.json` |
| Firmware and host | Rev C-local100p feedback model, calibration schema3; firmware build/PIO checks,12 Rust tests and Clippy pass | `../firmware/verification/`, `../host/verification/` |
| Coupled amplifier simulation | True DC, AC and transient data, exact models, negative false-OP regression and declaration-order identity checks | `solver-resolution-fixed-local/README.md` |
| Return-ratio method | Bilateral matrix de-embedding, analytic stable/unstable controls, complete crossing enumeration, independent controlled-source cuts | `stability-full-chain/` |
| FDA model/corner cross-check | Current and original TI models,134 standalone cases; selected-network minimum59.19° | `fda-independent/README.md` |
| Bounded switched ADC load |640ns acquisition recovery below half-LSB comparison threshold;140ns negative control fails; actual input/CM windows checked | `adc-switched-load/README.md` |

The complete analog scope and acceptance results are in [the revision C report](../docs/analog-validation-rev-c.md). Raw data, logs and generators distinguish numerical convergence, loop margin, finite-time boundedness and acquisition recovery. None establishes physical-board accuracy, noise, process/temperature corners or arbitrary fixture stability. The original false operating point and the superseded FDA topology are retained as labelled historical evidence; they are not accepted manufacturing circuits.

The project has no custom ERC/DRC exclusions or suppressed error severities. KiCad's default inactive categories remain listed in its JSON reports. Geometry checks do not replace measured signal integrity.

The firmware verifier checks120-cycle sampling frames,16 serial clock edges, dual-lane bit order, count bounds and late-READY handling. USB enumeration, ADC pattern acquisition and DUT measurements require hardware. Source settling remains1second. The host requires revision C-local100p calibration identity and uses complex feedback impedance on all ranges.

The board requires four-layer resin-filled, copper-capped, planarized via-in-pad processing. Vendor DFM acceptance and final placement preview remain ordering steps. Solder inspection, rail/startup checks, all-range scope tests, source-off noise measurements and independent calibration standards remain physical qualification. No manufacturer upload or purchase has occurred.

The package SHA256 manifest pins the delivered files. Revisions A and B are separately archived and superseded.
