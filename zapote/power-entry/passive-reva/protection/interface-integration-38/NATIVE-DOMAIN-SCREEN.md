# Rev38 native domain screen

**Status: FAIL and incomplete coverage, 2026-09-24. U7 remains OPEN.** This
is a bounded diagnostic on the unrouted `placement-review/02/` board, with
the same ownership and spacing checks repeated on the saved `/03` candidate. It
does not set an accepted insulation limit or qualify a board construction.

The saved KiCad 10.0.4 board SHA-256 is
`957ca67ada9338d91f9384695d3b3bf9d0f4a87263b471391700faf60760542d`.
The native pad/copper export SHA-256 is
`8a13ca76432e6f9d78c22153ccb138f9bb295b3efb55f10a893cd60dcb57e1a4`.
The later `/03` board SHA-256 is
`c277e9cae08213557f8bed43253253966229c695a9e754474d229babcf786ff5`,
and its export SHA-256 is
`3c539845b5e6e7b841d2450732d9ac6bc25b8b64d0abe9d24637ce9fd651b56e`.
The strict Rust document binder verifies its component/MPN, pad number,
net-name, pad-UUID, trace and via census against the embedded exact board
bytes; the test separately compares those bytes with the saved board.
Every physical pad now has a deterministic UUID, and two independent
source/pose rebuilds produced byte-identical PCB and manifest outputs.

The focused `domain_clearance::validate` anchor test compares only
`selv3v3` and `selv_gnd` against `hot0` and `hot_logic5` at a
**provisional 16.0 mm** projected copper-distance screen. It reports a
**15.200000 mm** opposed-pad gap at
`receiver.iso_protocol.1 / receiver.iso_protocol.16`, with other DWW and
arbitrary shelf-placement findings.

A second test assigns physical pad sides from source/connector ownership,
the exact 1–8 / 9–16 pins of both DWW isolators, the SELV-side local parts,
and the two PE terminals. The saved native export has **62 SELV, 183 live,
and one PE named nets**; no named net has pads on conflicting sides. A
mutation putting an isolator HOT pad on `selv3v3`, and another putting the
inlet PE terminal on `hot0`, both fail the ownership check. The broader
provisional copper-distance screen includes all 245 assigned SELV/live
nets and remains **FAIL**, including the same 15.2 mm DWW gap. It does not
assign a uniform insulation requirement to every AC, HOT, and SELV pair;
the 16 mm run is diagnostic only and does not measure creepage, air
clearance, package surfaces, solder, or slots.

The `/03` Rust test binds the saved exact PCB to the KiCad pad/copper export,
checks 295 source components and 1,052 numeric pad edges, and rejects a
wrong-net mutation. It confirms the same 62/183/one net-side census and the
same 15.2 mm DWW failure. Moving the small parts does not clear this gate.

The PE net is excluded from that two-side spacing projection. **Nineteen
KiCad pad objects have no assigned net**. Board inspection identifies
16 paste/mask-only objects (five each on `driver.driver`,
`hot_watchdog.watchdog`, and `source.watchdog`, one on
`hot15_converter.buck`) and three non-plated locating holes (one on
`pfc_power.l_boost`, two on `source_mcu.controller_port`). They are not
19 unexplained copper pads. The holes and any installed hardware still
need a constructed-path review. The board also remains unrouted; this
test cannot be transferred to future traces, vias, zones, or copper pours
without a fresh exact-board export and review.

The mutation test adds a synthetic SELV trace from the selected isolator's
SELV pad across its HOT pad. The domain rule identifies the injected trace
as a failure; the strict binder separately rejects that changed export
because the saved PCB contains no such trace. This establishes the rule's
response to a copper bridge without misrepresenting the mutated export as
saved-board evidence. The test is
`zapote/packages/zapote-drc/tests/rev38_native_domains.rs`.

The remaining U7 work is a reviewed voltage/insulation class for each
crossing, including PE and exposed metal, with rule coverage
for board surface and air paths, package/slot/laminate construction,
placement and routing, then a fresh native extraction and fault-path
review. The current DWW pad geometry does not meet the provisional
16.0 mm FR-4 surface-path screen by itself.
`INSULATION-COVERAGE.md` records the exact named-net pair census without
promoting this diagnostic distance check to a release rule.
