# Rev38 native export gate

`tools/build_source.py` freezes `elec/src` into a new directory, compiles the
`PowerEntryIntegrated38` entry with pinned Atopile 0.2.69, and writes the
resolved component export and source hashes. `tools/build_native.py` uses the
existing strict source-to-KiCad bridge. It requires the frozen build, an exact
pose for every source instance, and a reviewed rectangular outline; it refuses
to overwrite a native output directory.

The current frozen export, `source-build-02`, has a successful compiler receipt,
300 compiled references and a per-reference BOM. Its source files match the
current `elec/src` tree byte-for-byte. Its compiled `default.net` and
`default.csv` are retained with the snapshot because the strict bridge reads
those exact bytes. The source is still an
engineering candidate: SELV 3.3 V, source reset-good and interlock producers
are not joined. The source includes two unresolved footprint references:
off-board `A70QS50-14F` F2 at `U226` and the distinct Phoenix `1017526`
board-terminal candidate at `U227`. The selected Mersen US141 holder is off
board; `F2-BOARD-INTERFACE.md` records the four board pins but does not close
their drill, fault-current, DC, thermal and geometry gates.

The strict native probe on `source-build-02` again stopped at
`vendor_candidate_libs`, this time on the explicit assembly-only F2
placeholder `TBD_REVIEW_ONLY:PFC_F2_OFFBOARD_ASSEMBLY`. The generated partial
directory was removed. No `section.kicad_sch` or `section.kicad_pcb` was
emitted. The bridge needs an explicit, auditable off-board component rule and
a released four-pin terminal footprint; neither placeholder may be promoted
into a fabricated board. There are also no
reviewed `poses.json` or `outline.json`; automatic arbitrary placement would
not satisfy the electrical or isolation layout review.

Once those inputs are closed, generate a **new** frozen source directory, then run
`uv run --no-sync python3 tools/build_native.py <source-build> native-01`
after `make extensions-check` confirms a fresh `temper-design-bundle` bridge.
The native output must then pass source/native parity, ERC, DRC, stackup and
unit checks before any U7 digital acceptance. Physical captures remain
NOT RUN.
