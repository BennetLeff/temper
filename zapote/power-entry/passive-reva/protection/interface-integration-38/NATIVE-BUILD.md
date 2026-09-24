# Rev38 native export gate

`tools/build_source.py` freezes `elec/src` into a new directory, compiles the
`PowerEntryIntegrated38` entry with pinned Atopile 0.2.69, and writes the
resolved component export and source hashes. `tools/build_native.py` uses the
existing strict source-to-KiCad bridge. It requires the frozen build, an exact
pose for every source instance, and a reviewed rectangular outline; it refuses
to overwrite a native output directory.

The first frozen probe, `source-build-01`, has a successful compiler receipt,
299 compiled physical references and a per-reference BOM. Its source files
match the current `elec/src` tree byte-for-byte. The source is still an
engineering candidate: SELV 3.3 V, source reset-good and interlock producers
are not joined. The source includes one unresolved footprint reference,
`A70QS50-14F` F2 at `U226`. Its selected Mersen US141 holder is off board;
`F2-BOARD-INTERFACE.md` screens a board terminal but does not close its
fault-current, DC, thermal and geometry gates.

The strict native probe stopped at `vendor_candidate_libs` on that exact F2
placeholder. No `section.kicad_sch` or `section.kicad_pcb` was emitted. This
is the correct result until the off-board fuse is represented by a selected,
rated board connection with source/native pin parity. There are also no
reviewed `poses.json` or `outline.json`; automatic arbitrary placement would
not satisfy the electrical or isolation layout review.

Once those inputs are closed, generate a **new** frozen source directory with
`python3 tools/build_source.py source-build-02`, then run
`uv run --no-sync python3 tools/build_native.py source-build-02 native-01`
after `make extensions-check` confirms a fresh `temper-design-bundle` bridge.
The native output must then pass source/native parity, ERC, DRC, stackup and
unit checks before any U7 digital acceptance. Physical captures remain
NOT RUN.
