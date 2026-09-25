# Rev38 native export gate

`tools/build_source.py` freezes `elec/src` into a new directory, compiles the
`PowerEntryIntegrated38` entry with pinned Atopile 0.2.69, and writes the
resolved component export and source hashes. `tools/build_native.py` uses the
existing strict source-to-KiCad bridge. It requires the frozen build, an exact
pose for every source instance, and a reviewed rectangular outline; it refuses
to overwrite a native output directory.

The current frozen export, `source-build-05`, has a successful pinned
Atopile **0.2.69** compile/export receipt, **296 compiled references** and a
per-reference BOM. Its copied `default.net` and `default.csv` are retained
because the strict bridge reads those exact bytes. The Rev38 source has a
16-contact controller port and no ESP32-S3; the separate frozen
`cooker-source-02` derivative has the existing cooker ESP, SELV rail and
reset-good/interlock producers. The receipt-bound two-source 16-contact
connector audit passes. `COOKER-ASSEMBLY-SOURCE.md` records that narrow
digital join; the 3.3 V supply/load/startup/fail-low and physical harness
gates remain open. Cooker native placement and inverter power composition
are follow-on product work; the
[`POWER-ASSEMBLY-BOUNDARY.md`](POWER-ASSEMBLY-BOUNDARY.md) records that
boundary without blocking this section-board deliverable.

The current source retains off-board `A70QS50-14F` F2 at `U226` and joins
**two separate** on-board Würth `74651173R` studs at `U227` and `U228`,
one per `VD_LOCAL`/`VB_BANK` potential. Each stud is assigned a
`ReviewOnly` footprint. The Mersen US141 holder remains off board.
`F2-BOARD-INTERFACE.md` and `WURTH-STUD-FOOTPRINT-SCREEN.md` preserve the
candidate geometry and the open drill, fault-current, DC, thermal,
insulation, lug and restraint gates. The older Phoenix 1017526/1017531
terminal studies remain historical; their drilling conflict no longer
blocks footprint vendoring for this frozen candidate.

The strict bridge now requires an exact assembly-only declaration for F2:
source path `pfc_power.f2`, MPN `A70QS50-14F`, and the off-board footprint
marker. Rust checks the declaration against the full converted candidate,
retains the excluded reference in the source manifest, and projects only PCB
references into the board and native schematic. Six focused Rust tests cover
the exact exclusion and stale, changed, duplicate, or overbroad declarations.
Historical native probes on `source-build-03` and `source-build-04` reached footprint
vendoring and stopped on the Phoenix terminal placeholder. These probes do
not describe the current stud source. No `section.kicad_sch` or
`section.kicad_pcb` was emitted from them.

`source-build-04` remains the historical 295-reference heartbeat-pull-down
snapshot. Its receipt SHA-256 is
`ecd434f9e896cae47cadd73f955235d1c254030c46d6887461b6986b423a68cf`;
its netlist and resolved-export hashes are
`b1a7a8119055b59d7786addd0be70d0cccfb1337dc851a626aa0ca6534f10bfe`
and `6b41cb7304a93a5eefdcd71c91831fedbaa6a8aa2c5e50955c65a0a7f0997b7c`.
The 2026-09-24 pyo3 rebuild/freshness gate passed **10/10**. A current
`tools/build_native.py source-build-05` probe passed source validation,
footprint vendoring and strict pin-map conversion, then stopped at the
missing reviewed `poses.json`. The user-approved 360 × 250 mm planning
`outline.json` now exists; it is not a released mechanical or insulation
drawing.
The command emitted no section schematic or PCB, and this is a preflight
receipt only. Exact current SHA-256 inputs: build receipt
`4f07f1177fbe39eef940e665892c40285e77925ce4f4622ddbf21cd38672a7f5`,
netlist `c221b3048527eccbb3c9574ff35124f071c96d2b5031c19d81752c4159db13ea`,
resolved export `ef3f899e279843928e63464066378055bca704123ef9081e406c639c5a4c15a2`.
Automatic arbitrary placement would not satisfy electrical or isolation
layout review. A temporary flat KiCad schematic from the current source
exports **296 references, 246 nets and 1,054 numeric pin edges**, matching
the compiled source projection. It is a connectivity diagnostic, not the
native section schematic or a full functional pin-name audit.

A separate [temporary native generation diagnostic](NATIVE-DIAGNOSTIC-05.md)
used unreviewed courtyard shelf poses with that planning outline. After
preserving fabrication-only mask/paste apertures and aligning selected board
Values and legacy footprint text, the bridge emitted **295 board references,
246 nets and 1,052 mapped numeric edges** (the off-board F2 is excluded).
Its raw-pad oracle and KiCad schematic-parity comparison pass on those
temporary bytes. After the library-footprint serialization repair, board
DRC reports 22 violations and capped 499 unconnected items, with zero
library-footprint mismatches (`NATIVE-DIAGNOSTIC-07.md`); the grid-corrected
schematic ERC reports 63 single-node-label warnings after local symbol
and footprint library registration (`NATIVE-DIAGNOSTIC-08.md`). The diagnostic is not
the reviewed `native/section.kicad_pcb` deliverable, a DRC/ERC pass, or a
functional pin-name audit.

`INSULATION-BASIS.md` identifies another independent U7 blocker: the documented 409.307 V maximum static regulation
falls in the project's >400–500 V PD3 creepage row (16.0 mm reinforced
screen on Group IIIa FR-4; the separate Group I package screen is 12.6 mm).
The now-joined DWW package pair has >14.5 mm external paths but an
unqualified **PD3** application and board land-to-land construction. The
selected product standard, clearance, worst VD/VB
waveforms and complete barrier construction remain unresolved. No native
rule file or board DRC result is accepted.

The netlist's `(libsource (part ...))` may be a footprint-shared alias rather
than the selected per-reference MPN. A static comparison on historical
`source-build-04` found 122 such differences among 295 references. For example, the
selected `TCA6408AQPWRQ1` expander carries `SN74LV221AQPWRQ1` as its
compiled libsource identity. The native bridge now requires each selected
MPN in the resolved export to match the per-reference BOM and rekeys the
schematic symbol ID and visible Value to that MPN. It preserves only the
compiled **numeric pin** set; functional pin names are explicitly
unverified. Focused missing/mismatched-MPN tests pass 8/8. A temporary
flat Rev38 schematic exported by KiCad 10.0.4 from `source-build-05` had
296 references, 246 nets and the same 1,054 `(net, reference, pin number)`
edges as the frozen source, with zero missing or extra edges; U289's exported
libpart and Value are both `TCA6408AQPWRQ1`. This verifies identity and numeric connectivity at that
projection, not pin function or a complete native section board.
An independent selected-part check compared six critical refs (U1/U44
isolators, U2 AVR, U289 expander, U130 gate driver and U225 boost diode)
with their manufacturer numeric pinouts and found no source pad/function
miswire in those six. It is not a full-board audit. The
[Wolfspeed diode data sheet](https://assets.wolfspeed.com/uploads/2023/12/Wolfspeed_C3D20065D_data_sheet.pdf)
marks its metal tab cathode pin 4; the source fixture represents
the three leads, so tab isolation, mounting and thermal connection need
native mechanical review. The selected-part data sheets are linked in the
Atopile fixtures and `INSULATION-BASIS.md`.

Once those inputs are closed, use the current frozen source or generate a
new one if the selected components or pins change, then run
`uv run --no-sync python3 tools/build_native.py <source-build> native-01`
after `make extensions-check` confirms a fresh `temper-design-bundle` bridge.
The native output must then pass source/native parity, ERC, DRC, stackup and
unit checks before any U7 digital acceptance. Physical captures remain
NOT RUN.
