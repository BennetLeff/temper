# Temper differential probe — Rev C PCB prototype

Three-sheet KiCad design and fully routed four-layer PCB for measuring the stage-53 coil and resonant capacitor bank. Rev C is a compacted, simplified Rev B with every function kept. It is an engineering prototype; voltage, stability and CMRR targets still require qualification of the assembled probe in its enclosure.

**Start here:** [Rev C design record](docs/revc.md) — reasoning, calculations, rejected options and the before/after table against Rev B.

- [Schematic PDF](previews/differential-probe.pdf)
- [KiCad project](cad/differential-probe.kicad_pro) and [root schematic](cad/differential-probe.kicad_sch)
- [Routed PCB](cad/differential-probe.kicad_pcb), [3D preview](previews/pcb-3d.png), and [copper / assembly layers PDF](previews/pcb-layers.pdf)
- [Layout, enclosure and mounting requirements](docs/layout.md)
- [BOM exported from the schematic](bom.csv), with exact manufacturer part numbers, footprints and datasheet links
- [Circuit decisions and assembly notes](docs/design.md)
- [Calibration and qualification plan](docs/qualification.md)
- [Electrical checks](validation/checks.txt), [ERC report](validation/erc.rpt), and [package/pad audit](validation/footprint-audit.tsv)
- [PCB connectivity and symmetry checks](validation/pcb-checks.txt), [native DRC](validation/pcb-drc.json), and [spacing-rule negative controls](validation/pcb-drc-oracle.txt)
- [OPA2810/OPA810 vendor-model checks](validation/spice/results.txt)
- [Procurement package](procurement/README.md) (draft; nothing ordered)

The board is 150 × 70 mm, four layers, and carries every component.

- **HV dividers.** The two dividers are mirror images about an open-ended inter-leg notch, at a 23 mm leg pitch. Each leg has five 2 MΩ / 33 pF sections.
- **Spacing.** There are ten routed capacitor slots and no planes under the HV ladders.
- **Panel parts.** The BNC, range switch and power switch are PCB-mounted at the output edge. The two 9 V holders sit on the underside of the low-voltage section.

Native KiCad DRC reports zero violations and zero unconnected items with the explicit HV rules and `--all-track-errors`. These checks establish geometry and connectivity, not a qualified 3 kV or CAT rating.

## Specification carried into this design

| Item | Design target / implementation |
|---|---|
| Input divider | Two fixed 2000:1 dividers; five compensated sections per leg |
| Each upper section | One 2 MΩ, 1%, 3 kV HV12 2512 resistor, shunted by 33 pF NP0 / 3 kV ([cost-down](docs/cost-down.md)) |
| Low leg | 4.87 kΩ, 0.1% plus 500 Ω trim; 10 nF fixed + two select-on-test C0G + 12–60 pF top-adjust trimmer |
| Amplifiers | OPA2810 dual buffer; OPA2810 ×2 subtractor + coax driver; OPA810 ×5 stage |
| Output gain | Fixed ×2 subtractor and fixed ×5 stage; output selection gives nominal 1000:1 / 200:1 ratios |
| Initial differential range target | ±1.5 kV at 1000:1; ±300 V at 200:1 |
| Extended range to qualify | ±3 kV at 1000:1; ±600 V at 200:1 |
| Initial tip-to-earth target | Each tip within ±1.5 kV; extend separately to ±3 kV |
| Bandwidth | DC–5 MHz small-signal target; vendor-model −3 dB 5.79 MHz wide / 5.25 MHz fine |
| Initial-envelope warning | Nominal 1.363 kV per tip; 1.239 kV wide / 248 V fine differential, latched |
| Main measurement band | 35–60 kHz; proposed acceptance ±2% amplitude, ≤1° phase after calibration |
| Common-mode rejection | 60 dB goal; measure versus frequency and apply a measurement-specific error budget |
| Input loading | Ideal 10.005 MΩ and about 6.6 pF per tip; with leads and enclosure about 11.6 pF per tip (estimate, target ≤ 12 pF; [HV leads](docs/hv-leads.md#capacitance-budget)) |
| Scope | 1 MΩ input, short BNC cable; do not select 50 Ω termination |
| Power | Two 9 V batteries, regulated to approximately +4.80 / −4.81 V |
| Enclosure | Hammond 1455N2201 extruded aluminium; 20 mm HV-to-metal setback in 3-D (see [Rev C record](docs/revc.md#9-size-layers-enclosure)) |

All voltage ratings and performance limits above are **qualification targets**. Full voltage at 5 MHz is not implied. Input-to-earth voltage, differential voltage, frequency, temperature and duration must all stay inside the eventual measured envelope.

The compact spacing design requires all three extended limits at once: `|V+| ≤ 3 kV`, `|V−| ≤ 3 kV` and `|V+ − V−| ≤ 3 kV`. It does not claim survival with opposing +3 kV / −3 kV tips. A differential input can exceed its range even when each tip is within its earth-voltage limit.

## Main selected parts

| Function | Selected MPN | Quantity |
|---|---|---:|
| Upper divider resistors | Uni-Royal HV121WF2004T4E (2 MΩ, 1%, 1 W, 3 kV) | 10 |
| Upper compensation | Yageo CC1812JKNPOEBN330, 33 pF NP0, 3 kV | 10 |
| Low-leg fixed resistors | Yageo RT0603BRD074K87L (4.87 kΩ, 0.1%) | 2 |
| Gain-setting precision resistors | Stackpole RNCF0603TKY499R / 1K00 / 2K00 | 3 / 2 / 1 |
| Low-leg capacitors | Yageo CC1206FKNPO9BN103 + select-on-test C0805C302F5GACTU / C0805C161F5GACTU | 2 + 2 + 2 |
| DC trim | Bourns 3296W-1-501LF (500 Ω) | 2 |
| AC compensation trim | EW Electronics GKG60015, 12–60 pF | 2 |
| Buffers, subtractor, driver | TI OPA2810IDR | 2 |
| ×5 stage | TI OPA810IDR | 1 |
| Low-leakage clamps | Nexperia BAV199,215 | 3 |
| Overload comparators | TI TLV1704AIPWR / TLV1702AIDGKR | 1 each |
| Overload latch | TI CD4013BM96 | 1 |
| Regulators | ADP7142AUJZ-R7 / ADP7182AUJZ-R7 | 1 each |
| Range / power switches (PCB) | E-Switch 100SP1T1B5M7RE / 100DP1T1B1M7QEH | 1 each |
| BNC (PCB, bulkhead) | Amphenol RF 031-5431-10RFX | 1 |
| 9 V holders (PCB, underside) | MPD BH9VPC | 2 |

The BOM contains every component.

- **Cost-down (2026-10-20).** The divider uses 1% HV12 bodies stocked at JLC instead of the 0.1% HVCB2512 (9 at DigiKey, 0 at LCSC). The 4.87 kΩ + 500 Ω trim covers both a 1% and a 0.1% string, so Stackpole HVCB2512BDE2M00 remains a drop-in upgrade. The margin costs (DC CMRR drift with temperature, one fault case at the ±3 kV extension) are quantified in [cost-down](docs/cost-down.md).
- **HV leads.** Captive Rowe R800-1020 leads (UL 3239, 10 kV DC), 200 mm outside the box, leave through nylon glands in a copper-free FR4 tip-end plate and are tied to an FR4 lead bridge inside. Tips, strain relief and the loading budget are in [HV leads](docs/hv-leads.md). Ordinary SMA, 1 kV test leads or low-voltage terminal blocks are not acceptable for the HV inputs.

## Stage-53 identity

This work uses the user-selected stage 53, not the older stage15b baseline in the repository's general instructions.

Board: `worktrees/runs-native21/s53/c53int/section.kicad_pcb` relative to the repository root.

SHA-256: `82af7bd93e62d1f2e6c7c2c2b971a4830bf6e09078bae3f269d8bead9a31fd27`.

The coil spans `COIL_FEED`–`RES_A`; the capacitor bank spans `RES_A`–`SW_B`. The latter includes a bridge switch node, so probe-to-earth displacement current is a design constraint even when the wanted signal is the 35–60 kHz tank waveform. The bank is five 100 nF capacitors, 0.5 µF total. The inherited stage-53 studies include approximately 566 Vpk design operation, 775 Vpk no-pan, and 1.62–1.79 kV fault cases; these are simulation/design records, not measurements made with this probe.

The [CT correction](docs/stage53-ct-correction.md) verifies T1 as CST3015-200ED with a 3 Ω burden and recalculates its volt-second margin. Historical fixture documents and the stale model reference are addressed in a [scoped maintenance patch](maintenance/README.md).

Source records: `worktrees/ps-integrate/zapote/power-stage-120v/validation-results/11-candidates/c53-cert-provisions/stage53/README.md` and the `validation-results/08-manufacturing-package/native-21/review-packet-s53/` directory in that worktree. The fault envelope is why the 3 kV extension remains useful.

## Reproduce and edit

From this directory, run `make pcb` to regenerate the schematic and PCB, check them, and refresh previews. `make all` retains the schematic-only workflow. Optional `make simulate` verifies the archived model/testbench hashes and reruns the nominal OPA2810/OPA810 checks with ngspice. Requirements are KiCad 10, its native Python/pcbnew module, Rust, jq, and the standard KiCad libraries. The current tools use the macOS KiCad library location; adjust path constants and `KICAD_PYTHON` for another installation.

`tools/build.rs` is the deterministic authoring source for circuit selections, connections and sheet placement. It generates the native KiCad files and intended-pin records. `make export` exports PDF, SVG, XML netlist, BOM and ERC from those native files. `tools/check.rs` compares the exported connectivity against the intended pin groups, checks selected critical package pin mappings and footprint pad sets, and records ideal divider calculations. It does not simulate the ICs or establish high-voltage safety.

Edit the Rust authoring source for reproducible changes. Direct KiCad edits are possible, but a subsequent `make generate` replaces them; reconcile such edits into the authoring source first. Never hand-edit the generated BOM.

`tools/layout.rs` owns placement, hand-authored routing and HV rules; `tools/pcb_bridge.py` only adapts those records to native KiCad geometry and zone filling. `make pcb-generate` overwrites the canonical board, so reconcile manual PCB edits before regenerating. Existing project design settings are preserved. `make pcb-check` audits the current saved board without regenerating it. `make pcb-oracle` proves that a deliberately close grounded track, a removed capacitor slot, a closed inter-leg notch and a shortened notch each fail the relevant native DRC rules. Opposite-tip fixtures pass at 20.5 mm and fail at 8 mm edge spacing under the 10 mm air / 20 mm surface rules. Fixtures stay in ignored `build/`. `sh procurement/export.sh` regenerates the draft fabrication/assembly package.

Rev A is preserved in commit `14eda6c86`. Rev B is preserved unchanged at commit `ca79d882f` on `codex/differential-probe-revb`; its circuit record, build decision and layout handoff remain in `docs/`. Rev C is developed on `claude/differential-probe-revc`.

The original scratchpad analysis is preserved verbatim in `evidence/2026-10-20-divider.py`, with its original output. It is historical ideal-RC analysis, not the authoring source or proof of this complete circuit's performance.
