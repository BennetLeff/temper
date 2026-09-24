# Rev38 native export gate

`tools/build_source.py` freezes `elec/src` into a new directory, compiles the
`PowerEntryIntegrated38` entry with pinned Atopile 0.2.69, and writes the
resolved component export and source hashes. `tools/build_native.py` uses the
existing strict source-to-KiCad bridge. It requires the frozen build, an exact
pose for every source instance, and a reviewed rectangular outline; it refuses
to overwrite a native output directory.

The current frozen export, `source-build-03`, has a successful compiler receipt,
295 compiled references and a per-reference BOM. Its source files match the
current `elec/src` tree byte-for-byte. Its compiled `default.net` and
`default.csv` are retained with the snapshot because the strict bridge reads
those exact bytes. The duplicate ESP has been replaced by a 16-contact
Rev38-side controller port, but the cooker-board mate, SELV rail and
reset-good/interlock producers are not joined. The source remains an
engineering candidate. It includes two unresolved footprint references:
off-board `A70QS50-14F` F2 at `U226` and the distinct Phoenix `1017526`
board-terminal candidate at `U227`. The selected Mersen US141 holder is off
board; `F2-BOARD-INTERFACE.md` records the four board pins but does not close
their drill, fault-current, DC, thermal and geometry gates.

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

Once those inputs are closed, generate a **new** frozen source directory, then run
`uv run --no-sync python3 tools/build_native.py <source-build> native-01`
after `make extensions-check` confirms a fresh `temper-design-bundle` bridge.
The native output must then pass source/native parity, ERC, DRC, stackup and
unit checks before any U7 digital acceptance. Physical captures remain
NOT RUN.
