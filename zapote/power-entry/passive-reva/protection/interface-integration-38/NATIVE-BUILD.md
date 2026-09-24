# Rev38 native export gate

`tools/build_source.py` freezes `elec/src` into a new directory, compiles the
`PowerEntryIntegrated38` entry with pinned Atopile 0.2.69, and writes the
resolved component export and source hashes. `tools/build_native.py` uses the
existing strict source-to-KiCad bridge. It requires the frozen build, an exact
pose for every source instance, and a reviewed rectangular outline; it refuses
to overwrite a native output directory.

The current frozen export, `source-build-04`, has a successful compiler receipt,
295 compiled references and a per-reference BOM. Its source files match the
current `elec/src` tree byte-for-byte. Its compiled `default.net` and
`default.csv` are retained with the snapshot because the strict bridge reads
those exact bytes. The duplicate ESP has been replaced by a 16-contact
Rev38-side controller port. A separate `cooker-mate` derivative joins the
existing cooker ESP, SELV rail and reset-good/interlock producers; these
are not part of this frozen `source-build-04` export. That derivative
now has its own frozen `cooker-source-02` export and a two-source 16-contact
connector audit, recorded in `COOKER-ASSEMBLY-SOURCE.md`. The native Rev38
section has candidate 3.3 V port limits in `SELV-PORT-CONTRACT.md`; its
load, startup, connector and physical fail-low acceptance remains open.
The cooker derivative's missing canonical
footprints, native cooker board and inverter power composition are follow-on
product work. The separate
[`POWER-ASSEMBLY-BOUNDARY.md`](POWER-ASSEMBLY-BOUNDARY.md) explains why the
two-source control-header audit cannot be promoted to a one-front-end cooker
product; it does not block export of the Rev38 source-to-PFC section. The
source remains an engineering candidate. It includes two unresolved
footprint references:
off-board `A70QS50-14F` F2 at `U226` and the distinct Phoenix `1017526`
board-terminal candidate at `U227`. The selected Mersen US141 holder is off
board; `F2-BOARD-INTERFACE.md` records the four board pins but does not close
their drill, fault-current, DC, thermal and geometry gates.
Phoenix-linked SamacSys CAD archives corroborate the four pin centers but
do not clear the 1017526 drill conflict; the similar 1017531 archive also
has a fabrication outline inconsistent with its current product dimensions.

The strict bridge now requires an exact assembly-only declaration for F2:
source path `pfc_power.f2`, MPN `A70QS50-14F`, and the off-board footprint
marker. Rust checks the declaration against the full converted candidate,
retains the excluded reference in the source manifest, and projects only PCB
references into the board and native schematic. Six focused Rust tests cover
the exact exclusion and stale, changed, duplicate, or overbroad declarations.
After the extension rebuild passed its freshness gate, the native probe on
`source-build-03` reached `vendor_candidate_libs` and stopped on the separate
board terminal placeholder `TBD_REVIEW_ONLY:PFC_F2_BOARD_TERMINAL_1017526`.
The generated partial directory was removed. No `section.kicad_sch` or
`section.kicad_pcb` was emitted. The terminal needs a released four-pin
footprint; neither placeholder may be promoted into a fabricated board.
There are also no
reviewed `poses.json` or `outline.json`; automatic arbitrary placement would
not satisfy the electrical or isolation layout review.

`source-build-04` freezes a 10 kΩ rather than 100 kΩ GPIO21 heartbeat
request pull-down. Its two-source assembly lock and audit pass. The native
probe result above is historical for `source-build-03`; it has not been
rerun on `source-build-04`. `INSULATION-BASIS.md` now identifies a second,
independent U7 blocker: the documented 409.307 V maximum static regulation
falls in the project's >400–500 V PD3 creepage row (16.0 mm reinforced
screen on Group IIIa FR-4; the separate Group I package screen is 12.6 mm,
while the selected ISO774x DW package provides only >8 mm external
creepage. The selected product standard, clearance, worst VD/VB
waveforms and complete barrier construction remain unresolved. No native
rule file or board DRC result is accepted.

Once those inputs are closed, use the current frozen source or generate a
new one if the selected components or pins change, then run
`uv run --no-sync python3 tools/build_native.py <source-build> native-01`
after `make extensions-check` confirms a fresh `temper-design-bundle` bridge.
The native output must then pass source/native parity, ERC, DRC, stackup and
unit checks before any U7 digital acceptance. Physical captures remain
NOT RUN.
