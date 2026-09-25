# Rev38 native domain screen

**Status: FAIL and incomplete coverage, 2026-09-24. U7 remains OPEN.** This
is a bounded diagnostic on the unrouted `placement-review/02/` board. It
does not set an accepted insulation limit or qualify a board construction.

The saved KiCad 10.0.4 board SHA-256 is
`957ca67ada9338d91f9384695d3b3bf9d0f4a87263b471391700faf60760542d`.
The native pad/copper export SHA-256 is
`8a13ca76432e6f9d78c22153ccb138f9bb295b3efb55f10a893cd60dcb57e1a4`.
The strict Rust document binder verifies its component/MPN, pad number,
net-name, pad-UUID, trace and via census against the embedded exact board
bytes; the test separately compares those bytes with the saved board.
Every physical pad now has a deterministic UUID, and two independent
source/pose rebuilds produced byte-identical PCB and manifest outputs.

The focused `domain_clearance::validate` test compares only `selv3v3` and
`selv_gnd` against `hot0` and `hot_logic5` at a **provisional 16.0 mm**
board-surface spacing screen. It reports a **15.200000 mm** opposed-pad
clearance at `receiver.iso_protocol.1 / receiver.iso_protocol.16`, with
other DWW and arbitrary shelf-placement findings. Every other native net
is reported as unclassified, including PE and unassigned pads, so this
screen cannot pass as whole-board HOT/SELV coverage.

The mutation test adds a synthetic SELV trace from the selected isolator's
SELV pad across its HOT pad. The domain rule identifies the injected trace
as a failure; the strict binder separately rejects that changed export
because the saved PCB contains no such trace. This establishes the rule's
response to a copper bridge without misrepresenting the mutated export as
saved-board evidence. The test is
`zapote/packages/zapote-drc/tests/rev38_native_domains.rs`.

The remaining U7 work is a reviewed classification of every relevant
native net and exposed conductor, rule coverage for board surface and air
paths, package/slot/laminate construction, placement and routing, then a
fresh native extraction and fault-path review. The current DWW pad geometry
does not meet the provisional 16.0 mm board-surface screen by itself.
