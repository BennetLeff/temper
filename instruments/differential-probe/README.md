# Temper differential probe — Rev B PCB prototype

Three-sheet KiCad design and fully routed four-layer PCB for measuring the stage-53 coil and resonant capacitor bank. Rev B is an engineering prototype; voltage, stability and CMRR targets still require qualification of the assembled probe and fixed shield.

- [Schematic PDF](previews/differential-probe.pdf)
- [KiCad project](cad/differential-probe.kicad_pro) and [root schematic](cad/differential-probe.kicad_sch)
- [Routed PCB](cad/differential-probe.kicad_pcb), [3D preview](previews/pcb-3d.png), and [copper / assembly layers PDF](previews/pcb-layers.pdf)
- [Layout, shielding and mounting requirements](docs/layout.md)
- [BOM exported from the schematic](bom.csv), with exact manufacturer part numbers, footprints and datasheet links
- [Circuit decisions and assembly notes](docs/design.md)
- [Rev B circuit calculations and vendor-model checks](docs/circuit-revb.md)
- [Calibration and qualification plan](docs/qualification.md)
- [Electrical checks](validation/checks.txt), [ERC report](validation/erc.rpt), and [package/pad audit](validation/footprint-audit.tsv)
- [PCB connectivity and symmetry checks](validation/pcb-checks.txt), [native DRC](validation/pcb-drc.json), and [spacing-rule negative controls](validation/pcb-drc-oracle.txt)

The compact 240 × 84 mm board has two identical divider layouts separated by 35 mm, ten routed creepage slots, no planes under the HV ladders, and a ground plane confined to the amplifier region. Native KiCad DRC reports zero violations and zero unconnected items with the explicit HV rules enabled. These checks establish the recorded geometry and connectivity, not a qualified 3 kV or CAT rating.

## Specification carried into this design

| Item | Design target / implementation |
|---|---|
| Input divider | Two fixed 2000:1 dividers; five compensated sections per leg |
| Each upper section | Two 1 MΩ, 0.1% resistors in series, shunted by 33 pF C0G |
| Low leg | 4.99 kΩ, 0.01% plus 50 Ω trim; coarse C0G bank plus 12–60 pF top-adjust trimmer |
| Output gain | Fixed ×2 subtractor and fixed ×5 stage; output selection gives nominal 1000:1 / 200:1 ratios |
| Initial differential range target | ±1.5 kV at 1000:1; ±300 V at 200:1 |
| Extended range to qualify | ±3 kV at 1000:1; ±600 V at 200:1 |
| Initial tip-to-earth target | Each tip within ±1.5 kV; extend separately to ±3 kV |
| Bandwidth | DC–5 MHz small-signal target; calculated RC pole 6.00 MHz, estimated fine-range cascade 5.00 MHz |
| Initial-envelope warning | Nominal 1.406 kV per tip; 1.266 kV wide / 253 V fine differential, latched |
| Main measurement band | 35–60 kHz; proposed acceptance ±2% amplitude, ≤1° phase after calibration |
| Common-mode rejection | 60 dB goal; measure versus frequency and apply a measurement-specific error budget |
| Input loading | Ideal 10.005 MΩ and about 6.6 pF per tip; shield/lead/PCB capacitance adds to this |
| Scope | 1 MΩ input, short BNC cable; do not select 50 Ω termination |
| Power | Two 9 V batteries, regulated to approximately +4.80 / −4.81 V |

All voltage ratings and performance limits above are **qualification targets**. Full voltage at 5 MHz is not implied. Input-to-earth voltage, differential voltage, frequency, temperature, and duration must all remain inside the eventual measured envelope. The compact spacing design requires all three extended limits simultaneously: `|V+| ≤ 3 kV`, `|V−| ≤ 3 kV`, and `|V+ − V−| ≤ 3 kV`. It does not claim survival with opposing +3 kV / −3 kV tips. A differential input can exceed its range even when each individual tip is within its earth-voltage limit.

## Main selected parts

| Function | Selected MPN | Quantity |
|---|---|---:|
| Upper divider resistors | Stackpole HVCB2512BDE1M00 | 20 |
| Upper compensation | KEMET C1812C330JHGACTU, 33 pF C0G, 3 kV | 10 |
| Low-leg precision resistors | Stackpole RNCF0603TKY4K99 | 2 |
| Gain-setting precision resistors | Stackpole RNCF0603TKY499R | 11 |
| DC trim | Bourns 3296W-1-500LF | 2 |
| AC compensation trim | EW Electronics GKG60015, 12–60 pF | 2 |
| Input buffers | Analog Devices ADA4817-1ARDZ-R7 | 2 |
| Difference, ×5 and output amplifiers | TI OPA810IDR | 3 |
| Low-leakage clamps | Nexperia BAV199,215 | 3 |
| Overload comparators | TI TLV1704AIPWR / TLV1702AIDGKR | 1 each |
| Overload latch | TI CD4013BM96 | 1 |
| Regulators | ADP7142AUJZ-R7 / ADP7182AUJZ-R7 | 1 each |
| Clamp references | TI TL431BIDBZR | 2 |
| Range / power switches | C&K 7201SYZBE / 7201SYZQE | 1 each |
| Panel BNC | Amphenol RF 31-221-RFX | 1 |

The BOM contains every electronic component, including decoupling and both fine compensation trimmers. Exact-MPN sourcing checks found the active parts and main passive families; the catalog snapshots are dated evidence, not live availability or a purchasing quote. The twenty 0.1% HV resistors are the dominant cost item: a distributor listing was approximately $12 each at single-unit quantity when checked. Do not silently substitute 1% parts into this trim design.

The PCB includes captive-lead solder landings and explicit wire landings for the five offboard components. The enclosure, rated input leads, strain relief and battery retention still need an assembly design and orderable mechanical BOM. Shield offsets and mounting restrictions are recorded in the layout notes. Ordinary SMA or low-voltage terminal blocks are not selected for the HV inputs.

## Stage-53 identity

This work uses the user-selected stage 53, not the older stage15b baseline in the repository's general instructions.

Board: `worktrees/runs-native21/s53/c53int/section.kicad_pcb` relative to the repository root.

SHA-256: `82af7bd93e62d1f2e6c7c2c2b971a4830bf6e09078bae3f269d8bead9a31fd27`.

The coil spans `COIL_FEED`–`RES_A`; the capacitor bank spans `RES_A`–`SW_B`. The latter includes a bridge switch node, so probe-to-earth displacement current is a design constraint even when the wanted signal is the 35–60 kHz tank waveform. The bank is five 100 nF capacitors, 0.5 µF total. The inherited stage-53 studies include approximately 566 Vpk design operation, 775 Vpk no-pan, and 1.62–1.79 kV fault cases; these are simulation/design records, not measurements made with this probe.

The [CT correction](docs/stage53-ct-correction.md) verifies T1 as CST3015-200ED with a 3 Ω burden and recalculates its volt-second margin. Historical fixture documents and the stale model reference are addressed in a [scoped maintenance patch](maintenance/README.md).

Source records: `worktrees/ps-integrate/zapote/power-stage-120v/validation-results/11-candidates/c53-cert-provisions/stage53/README.md` and the `validation-results/08-manufacturing-package/native-21/review-packet-s53/` directory in that worktree. The fault envelope is why the 3 kV extension remains useful.

## Reproduce and edit

From this directory, run `make pcb` to regenerate the schematic and PCB, check them, and refresh previews. `make all` retains the schematic-only workflow. Optional `make simulate` verifies the archived model/testbench hashes and reruns the nominal OPA810 checks with ngspice. Requirements are KiCad 10, its native Python/pcbnew module, Rust, jq, and the standard KiCad libraries. The current tools use the macOS KiCad library location; adjust path constants and `KICAD_PYTHON` for another installation.

`tools/build.rs` is the deterministic authoring source for circuit selections, connections and sheet placement. It generates the native KiCad files and intended-pin records. `make export` exports PDF, SVG, XML netlist, BOM and ERC from those native files. `tools/check.rs` compares the exported connectivity against the intended pin groups, checks selected critical package pin mappings and footprint pad sets, and records ideal divider calculations. It does not simulate the ICs or establish high-voltage safety.

Edit the Rust authoring source for reproducible changes. Direct KiCad edits are possible, but a subsequent `make generate` replaces them; reconcile such edits into the authoring source first. Never hand-edit the generated BOM.

`tools/layout.rs` owns placement, hand-authored routing and HV rules; `tools/pcb_bridge.py` only adapts those records to native KiCad geometry and zone filling. `make pcb-generate` overwrites the canonical board, so reconcile manual PCB edits before regenerating. Existing project design settings are preserved. `make pcb-check` audits the current saved board without regenerating it. `make pcb-oracle` proves that a deliberately close grounded track and a removed capacitor slot fail the relevant native DRC rules. Opposite-tip fixtures pass at 20.5 mm and fail at 8 mm edge spacing under the revised 10 mm air / 20 mm surface rules. Fixtures stay in ignored `build/`.

Rev A is preserved in commit `14eda6c86` on `codex/differential-probe-revb`; Rev B is developed and saved on that branch without switching the shared main checkout.

The original scratchpad analysis is preserved verbatim in `evidence/2026-10-20-divider.py`, with its original output. It is historical ideal-RC analysis, not the authoring source or proof of this complete circuit's performance.
