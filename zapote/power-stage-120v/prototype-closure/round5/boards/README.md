# Round5 routed supervisor and sensor candidates

**Nine real KiCad PCBs are routed and source-checked. They are not fabrication or powered-test releases.** This closes the earlier absence of placed/routed supervisor and remote sensor boards; it does not close supply thermals, signal integrity, product insulation, fast acquisition or complete enclosure integration. Round4 and native19 are unchanged.

| Board | Electrical parts | Outline | Copper |
|---|---:|---|---|
| Central supervisor | 436 | 275 × 240 × 1.6 mm | 4 layers |
| Catch / bus voltage | 21 each | 60 × 35 × 1.6 mm | 2 layers |
| Line / precharge / output voltage | 17 each | 60 × 35 × 1.6 mm | 2 layers |
| Tank voltage | 25 | 135 × 55 × 1.6 mm | 2 layers |
| Proof / line current CT | 5 each | 45 × 35 × 1.6 mm | 2 layers |

The central board is a **new guarded-pod allocation**, not a drop-in fit for either enclosure package. It carries the source hardware logic, comparators, timers, STM32, ADS131M08, isolated controller interface and contactor drivers. Voltage dividers and their AMC3330 isolation barriers move to local cards. CTs and permanent burdens remain together on separate cards. Contactor, fuse, thermal-cutoff, mains-supply and resistor assemblies remain external. `external-pins.tsv` preserves the historical round4 partition for conservation checks; **it is not the current external-assembly BOM**. Use round5 protection hardware's `PC125-CATCH-R5-2` contract for those revised parts.

## What was verified

Native KiCad 10.0.4 ran **three DRC samples on every board**: all 27 reports contain zero violations, zero opens and zero schematic-parity differences. Zones are filled and saved in the native files. Eight sensor schematics have zero ERC violations. The central schematic has zero ERC errors and nine `ground_pin_not_ground` warnings from the explicit AUX_0V/CTRL_GND isolated-domain names; these warnings are retained, not hidden.

`verify_native.py` compares each source-derived pin table against an independently exported KiCad XML netlist and the actual pcbnew pads, including exact footprint identities. Missing-pin and wrong-net negative controls fail as expected. It accounts for all **1761 original round4 pin rows (1698 connected plus 63 NC)** and checks the eight straight-through sensor harnesses across both boards. This validates translation and connection identity, not correctness of the original control architecture or real-world immunity.

The output directory contains `verification-summary.json`, `native-pin-oracle.json`, individual ERC/DRC reports, readable sensor schematics and board PDFs. Conventional component symbols show the sensor circuits. The central source capture is 43 sheets including its index, grouped by function but retaining typed pin blocks; it still needs a human circuit review, and a connectivity-only drawing must not substitute for that review. Catch, tank, current-card schematics and central/current board renders were inspected.

## Source authority and replay

- `partition.rs` derives central pins, connector additions, the preload ECO, and the D-30 controller-supply pin ECO from immutable round4 `supervisor/generated/pins.tsv`. `central/generated/pins.tsv` and `central/ref-map.tsv` retain source identities.
- `central/layout.json` records placements. `central/copper.json` contains the final reviewed copper geometry; `build_central.py` replays it using native KiCad. Freerouting 2.0.1 helped route it through the local-only `LocalRoute.java` adapter. Native KiCad found opens despite the router reporting completion; manual fixes and native checks closed them. The final replay, not discarded router sessions, is authoritative.
- Voltage `*-pins.tsv`, `*-ref-map.json`, `*-layout.json`, `build_boards.py` and `render_sensor.py` define their source-derived circuits and explicit geometry. `derive_sensor_variants.py` is an adapter over the round4 pin capture, not a new circuit authority.
- `build_current.py` derives the two burden circuits and emits their drawing-based CT footprint, conventional symbols and routed boards. CT pin 3 is mechanical support, not a secondary center tap.
- `board-bom.csv`, `component-census.json` and `connector-map.json` inventory actual candidates. The connector map gives **board pin numbers**, domains and directions; it is not a mating-face photograph or permission to mirror a cable.
- `power_direction.rs` audits all nine pin tables with explicit sensor harnesses and external supply/return boundaries. Connectors and `PWR_FLAG` symbols cannot count as onboard producers. Its negative tests include the original J9 defect, missing supplies and two joined `power_out` connector pins. `verify_native.py` also checks connector types against KiCad XML.
- J9.1 is `power_in`; J9.2 is a passive connector return. `render_central.py` declares the external controller supply and return with labeled ERC flags. These are interface assumptions, not validated controller hardware. See [D-30 evidence](../../../validation-results/01-switching-parasitics/round17/delegation/out-D30/README.md).
- Run `check.sh` from the repository root, with KiCad and standalone `rustc` available. The adapters use KiCad's bundled Python 3.9; Rust partition compilation is standalone and does not touch shared placer extensions. `ruff check` and Python 3.9 compilation pass.

## Implemented physical and electrical changes

The AMC3330 footprint uses TI's **DWE0016A HV option**: pad rows 9.75 mm apart with 1.65 × 0.6 mm pads, giving 8.1 mm opposite-row copper separation. The generic SOIC alternative gives only 7.3 mm. Pin identities are unchanged. All six voltage boards enforce a provisional 8 mm HV-to-SELV DRC screen. It is a geometric design screen, **not a selected product insulation requirement**; working voltage, transient category, pollution, coating, material group and actual housing environment remain to be qualified. Tank's twelve-resistor ladder is laid out straight over a larger board instead of folding high-voltage nodes next to each other.

JST XH board headers replace unspecified remote interfaces. Voltage-card J2 uses B6B-XH-A(LF)(SN), XHP-6 housing and SXH-001T-P0.6 contacts, for 22–28 AWG conductors. Pins 1–6 are POD_3V3, AUX_0V, channel_P, channel_N, channel_DIAG_N, AUX_0V. Pair supply/return, differential output pair, diagnostic/return. These connectors are on the low-voltage side only. Cable capacitance and analog settling remain held; AMC3330 limits direct load to 500 pF per output-to-ground or 250 pF differential without added isolation resistance.

The current cards retain two parallel resistors and SMCJ5.0CA TVS permanently across each CT secondary, ahead of the unplugged signal connector. Proof uses AC1005 with 200 Ω ∥ 200 Ω; line uses AC1020 with 100 Ω ∥ 100 Ω. Their JST two-pin signal connector carries RAW and REF_1V25 to central J23/J24. The primary is an independently restrained insulated conductor through the CT aperture, never a PCB terminal. These CTs are for 50/60 Hz, not tank-frequency capture. The footprint uses 15.24 mm end-pin spacing, a center support 7.62 mm behind, Ø1.2 mm finished-hole candidates for Ø0.813 mm leads, and the 23.8 × 11.12 mm body drawing. Actual fit, primary insulation and mechanical retention remain held.

Central R1 / R_MINLOAD changes 499 Ω → **470 Ω 0.1%, TNPW1206470RBEEA**, preserving the footprint. This supplies at least 10 mA over the stated 4.75 V lower boundary, including the documented resistance allowances. See [power-review.md](power-review.md) for the arithmetic and the unresolved 350 mA allocation, LD1117 heat, upstream 500 mA limit, sequencing and backfeed analysis.

The catch carrier interface remains 60 × 35 mm with Ø2.7 mm NPTH centers (17,32), (57,32), (57,3), and **nonconductive mounts**. HV input pads are local (3,3) and (3,28), independently restrained direct capacitor-strap leads. J2 pin1 is (53,10), pins advance local +Y at 2.5 mm; mating access is +world X. Local X follows world +Y, local Y follows world +Z; allocation is world X103–117, Y348–408, Z43–78 mm. The voltage-card input leads have no selected insulation/strain-relief assembly yet.

## Remaining digital design holds

1. Complete aggregate maximum/transient current and rail-tolerance accounting, then redesign or justify regulator thermal spreading. The central candidate has no accepted power-plane/return-path or coupled thermal model. A zero-open autoroute is not this qualification.
2. Review and improve central placement/return impedance, ADC filtering/clock routes, differential harness effects and contactor switching coupling. Total copper lengths are inventoried; they are not extracted RLC or validated signal-integrity results.
3. Implement the actual external ADC oscillator at J7 and its power-off behavior. Implement the fast common-timebase capture module's real FPGA/oscillator/header pin assignment and isolated analog acquisition. No FPGA, AD7380 or 80 MHz clock has been silently added to these boards.
4. Finish product-specific insulation rules, divider voltage/pulse/thermal limits, lead selection, probe access and carrier/guard mounting. Native pad checks do not establish dielectric or fault-energy capability.
5. Finish complete 3D review: U27's referenced TQFP-32 model is absent from the installed library; the CT body models and six HV wire/strain-relief paths are not modeled. All other component model references resolve on this host. No STEP, Gerber or fabrication release is claimed for this package.
6. Review the whole revision against the firmware, actual protection hardware and extracted coupled model before releasing one prototype. Measurements then qualify that prototype before siblings are built.

Primary mechanical/electrical sources: [TI AMC3330](https://www.ti.com/lit/ds/symlink/amc3330.pdf), [JST XH](https://www.jst-mfg.com/product/pdf/eng/eXH.pdf), [Talema AC1005 drawing / AC1005–AC1020 family](https://talema.com/wp-content/uploads/datasheets/AC-1005.pdf), and the sources in the power review. Standard symbols/footprints are vendored from installed official KiCad 10 libraries; see [KiCad library license](https://www.kicad.org/libraries/license/). The local CT and HV lead geometry is newly authored from manufacturer drawings; the AMC land pattern is a documented modification of the standard SOIC footprint.
