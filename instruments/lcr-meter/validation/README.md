# Verification receipts

## Revision E verification receipt

Board `cad/temper-lcr.kicad_pcb` after the USB-C power change (2026-10-21: DC jack J2 and Q1 removed; U16 TPS2553, R110, C113 added; four-terminal BNCs and K4 as before), SHA256:

`59c20647beec2d5a4480cda42255b8ca427aacd131cd31dc3989663aa7a9617a`

KiCad 10.0.4. Rows marked *USB-C* were rerun on this file. The other rows were produced on the previous board (`af615c841`, SHA256 `80d44838…`); the USB-C change moved no analog part or copper, so they carry over. Rev E is the TIDA-060029 analog core with a TAC5112 codec in place of the AD9833, both THS4551s and the ADS9224R; latching range relays K1–K3; four-terminal BNC jacks; K4 internal 1 kΩ reference ([rev-e-plan](../docs/rev-e-plan.md)).

| Check | Result | Evidence |
|---|---|---|
| Native schematic ERC, all severities | 0 violations (*USB-C*) | `erc.json` |
| Native PCB DRC, all track errors, zones refilled, schematic parity | 0 violations, 0 unconnected, 0 parity findings (*USB-C*) | `drc.json` |
| Independent audit (Rev E) | 624 source pins = 624 native pads = 624 netlist nodes (*USB-C*); four-terminal topology (J3 DUT_HI, J7 HPOT → U6.5, J8 LPOT → U7.5, J9 DUT_LO → R94 → TIA_SUM); op-amp input plane relief on In1/In2/B; OPA2810 bypass 2.031–2.050 mm; 0 findings | `independent-verification-rev-e.json` (`python independent_check.py E` with KiCad Python) |
| Source/schematic/PCB parts and placements | 204 fitted components, 197 SMT placements, 62 SMT lines (*consolidation*: 23 extended; U2 GD25Q16E CPL offset 270°, RMS 0.05 mm; *USB-C*: U16 CPL offset 180°, RMS 0.21 mm against the LCSC land record); pin parity and coordinates PASS; keyed-part rotation offsets applied | `cad-bom-parity.json`, `placement-library-audit.md` |
| Layout audit | Supply-pin decoupling distances (codec 1.3–3.9 mm), vias per exposed pad (U1 8, U11 6, U12 6, U13 9, U14 4), regulator support-part distances, feedback-trace lengths | `layout-audit-rev-e.json` (`cad/tools/audit_layout.py`) |
| Via/SMT drill and ring audit (*cost pass*) | 33 thermal vias in the five exposed pads, tented on B.Mask; no other via drill or via ring on any SMT land (R3.2, C44.1, R101.1, U16.2, Y1.4 moved off); all 278 vias tented; no POFV | `via-in-pad-process.json` (`cad/audit_dfm.py`) |
| USB-C power entry (*USB-C*) | VBUS from J1 down the west strip (0.8 mm F.Cu) to U16 IN; C113 1 µF 0.9 mm from IN; EN tied to IN; R110 24 kΩ (limit 1.0–1.16 A, SLVS841F eq. 1); OUT to C80 through two via pairs and B.Cu under the J5 3V3 feed; region plot inspected | `cad/tools/rev_e_routes.py`, `layout-audit-rev-e.json` (U16.6 to C80 6.1 mm) |
| Visual review of the exported layers | F.Cu, In1 (GND), In2, B.Cu, both masks, paste and the assembly drawing opened and checked; no findings (one cosmetic Fab-text overlap) | `visual-review-rev-e.json` |
| Extracted parasitics, BNC board | HCUR 12.9 pF, LCUR 7.5, HPOT 8.9, LPOT 10.9 pF to ground; HPOT–HCUR 0.24 pF | `layout-parasitics/README-rev-e.md` (`reve_bnc`) |
| Rail monitor window (*host*) | Worst healthy readings +12 V 10.42–13.18 V, −12 V 10.71–13.87 V (the old 10.8 / 13.2 V edges could refuse a healthy board); host windows 10.2–13.4 / 10.5–14.1 V; calibration-to-use limit 8.6 / 9.7 %; 2 host tests tie the constants to the JSON | `power-spurs/rail_monitor_window.py`, `../host/tests/cli.rs` |
| Source stage U5 (*consolidation*) | 280 pF as two 560 pF in series with 0.5 pF midpoint stray and 1.5 nH per part: 59.73° (60.13° with 270 pF; 58.74° at 2 pF / 3 nH); 85 kHz −0.025 dB / −0.56°; method reproduces the committed `codecbase` TIA row (19.5149 MHz / 95.04°) | `stability-full-chain/source_stage.py` |
| Loop stability, as built | 360 cases (no cable, 1 m RG-58 on all four jacks, 100–1000 pF lumped, K4 closed), stress relay parasitics: every loop ≥ 45°; worst drive 46.83°, TIA 57.21° | `stability-full-chain/` (`kelvincng100`), `../docs/rev-e-front-end.md` |
| Regulators, Rev E part set | 45 of 46 rows pass at the USB corners (VBUS 4.40–5.5 V, 4.32 V after U16), including R95/R96 headroom at 2× load, now 1.083 V (*consolidation*: LDO dividers rebuilt; was the FLAG at 0.951 V). The FLAG is a new, stricter row that adds divider TCR over 25 ± 35 °C: 0.970 V against the 1 V PSRR-curve condition (0.838 V on the previous dividers); dropout (0.6 V) holds | `power-spurs/regulator_check.json` (*USB-C*) |
| Interference, codec chain | SOF: 0 dB at whole kHz, −51 to −54 dB on the half-kHz grid; switcher collision chance 0.01–0.09 % per frequency (Rev D 2 %); DAC images at the modulator rate: pessimistic up to 0.75 % on a coil, settled by bring-up gate B-E1; USB VBUS (*USB-C*): a coherent line of ≥ 25 mV at 60.5 kHz (9 µF; ≥ 0.44 V for the other parts) needed for 10⁻⁴ | `power-spurs/README-rev-e.md`, `rev_e_spurs.json` (*new 2026-10-21*) |
| Accuracy map (simulation) | ≤ 0.2 % (typical and corner) 3.16 Ω–10 kΩ at every frequency 50 Hz–85 kHz | `rev-e-accuracy-map/` |
| Firmware (Rev E) | Host tests both builds; PIO model of `tdm`/`tdm375` with negative controls; hot-loop bound 209 of 640 cycles | `../firmware-rev-e/verification/` |
| Host | 3 + 26 + 32 tests pass (*rerun 2026-10-21*, `cargo test --release`); clippy `-D warnings` in `build.sh` | `../host/` |

**Not established by any of this:** physical-board accuracy, noise, solder quality, codec behaviour at 187.5 kHz (clock acceptance, wideband response to 85 kHz, CM_TOL with wideband), relay-internal capacitances, the DAC-image level, and the self-capacitance of the calibration standards. Those are bring-up items ([bring-up-rev-e.md](../docs/bring-up-rev-e.md)). Ordering steps still open: JLC re-quote at 140 × 105 mm, POFV via option, vendor DFM and the placement-preview approval. No manufacturer upload or purchase has occurred.

## Revision D verification receipt (superseded by Rev E; kept as history)

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
| Native coordinates and audited CPL rotations | 173 SMT placements, 58 BOM lines match | `cad-bom-parity.json`, `placement-library-audit.md` |
| Ground/analog layout | No non-GND In1 tracks; OPA/FDA signal relief and compact feedback preserved | `independent-layout-rev-c.json` |
| Via/SMT drill intersection audit | 54 intended filled/capped vias on 17 pads (5–9 per exposed pad); no unexpected intersections | `via-in-pad-process.json` |
| Layout audit (Rev D, after the audit fixes) | Supply-pin decoupling distances, vias per exposed pad, LDO/converter support-part distances and feedback-trace lengths | `layout-audit-rev-d.json` (`cad/tools/audit_layout.py` with KiCad Python); see `../docs/rev-d-audit.md` |
| Manufacturing exports and visual review | Four copper layers, masks, paste, silk, outline, PTH/NPTH drills and six schematic pages | `visual-review.json` |
| Firmware and host | D-riso22 identity; feedback 22 Ω + RF‖100 pF; calibration schema 5; RAILS gross-fault check; firmware build, PIO and boxcar checks, hot loop 88/120 cycles; 29 Rust tests and Clippy pass | `../firmware/verification/`, `../host/verification/` |
| Coupled amplifier simulation (*Rev C*) | True DC, AC and transient data, exact models, negative false-OP regression and declaration-order identity checks | `solver-resolution-fixed-local/README.md` |
| Rev D stability, as built | Extracted Rev D parasitics + 0–1000 pF cable on each DUT terminal: minimum TIA margin 51.3°, |1+T| ≥ 0.573 over 64 cases (Rev C: 29.5°, 0.498) | `stability-full-chain/fixture-envelope.md`, `layout-parasitics/` (`rev_d_board`) |
| Return-ratio method | Bilateral matrix de-embedding, analytic stable/unstable controls, complete crossing enumeration, independent controlled-source cuts | `stability-full-chain/` |
| FDA model/corner cross-check (*Rev C*) | Current and original TI models,134 standalone cases; selected-network minimum59.19° | `fda-independent/README.md` |
| Bounded switched ADC load (*Rev C*) |640ns acquisition recovery below half-LSB comparison threshold;140ns negative control fails; actual input/CM windows checked | `adc-switched-load/README.md` |

The complete analog scope and acceptance results are in [the revision C report](../docs/analog-validation-rev-c.md). Raw data, logs and generators distinguish numerical convergence, loop margin, finite-time boundedness and acquisition recovery. None establishes physical-board accuracy, noise, process/temperature corners or arbitrary fixture stability. The original false operating point and the superseded FDA topology are retained as labelled historical evidence; they are not accepted manufacturing circuits.

The project has no custom ERC/DRC exclusions or suppressed error severities. KiCad's default inactive categories remain listed in its JSON reports. Geometry checks do not replace measured signal integrity.

The firmware verifier checks 120-cycle sampling frames,16 serial clock edges, dual-lane bit order, count bounds and late-READY handling. USB enumeration, ADC pattern acquisition and DUT measurements require hardware. Source settling remains 1 second. The host requires revision D-riso22 calibration identity and uses complex feedback impedance, including R94, on all ranges.

The board requires four-layer resin-filled, copper-capped, planarized via-in-pad processing. Vendor DFM acceptance and final placement preview remain ordering steps. Solder inspection, rail/startup checks, all-range scope tests, source-off noise measurements and independent calibration standards remain physical qualification. No manufacturer upload or purchase has occurred.

The package SHA256 manifest pins the delivered files. Revisions A and B are separately archived and superseded; Rev C is superseded by D (snapshot commit ff1ffb45b).
