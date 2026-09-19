# Protection review corrections — 2026-09-19

Status: **experimental construction; protection incomplete**.

The four review findings are corrected in the authored source and decision.
This checkpoint also preserves the offered, unfinished Infineon bridge/AUX
integration. It does not replace or qualify the routed TEA candidate.

| Finding | Correction | Limit |
|---|---|---|
| Fault during POR could be forgotten | Permission latch with persistent asynchronous fault reset; separate startup VSENSE inhibit | Boolean behavior tested; rail ramps, comparator readiness, recovery timing and brownouts unqualified |
| TVR14561 does not support the claimed clamp | Removed from source and new compiled construction | No replacement energy-handling part selected; construction is incomplete |
| VSENSE-low timing confused with switch-off timing | Six-segment delay budget ends at actual U9 current cessation | Unknown segments stay unknown; no 5 us guarantee |
| Startup energy/cycle bound incorrect | 1.5 uF at 424.68 V = 135.2648268 mJ; cycle and 545 V bounds withdrawn | No startup trajectory or one-event guarantee |

The obsolete ECO patch is retired, with its original bytes saved in the
review evidence. It must not be applied: its comparator-input wiring was wrong.
The CD4013 second-half pin identities are also corrected. The schematic drawing
adapter no longer assigns obsolete TEA names to unrelated component pins.

## Verification

- Atopile 0.2.69: compiled/exported, `source-review-07`.
- Native construction: `native-review-03`, 119 components, **unrouted**.
- Native KiCad ERC: zero violations with the local project/library context.
- Exported native connected pin groups exactly match the compiled netlist.
- 13 Rust regressions pass in the normal zapote-harness suite, including the
  persistent-startup-fault and erroneous-comparator-wiring negative controls.
- Existing timed plant sweep reproduces byte-for-byte. That preserves a
  conditional calculation, not qualification of the newly selected circuit.
- Scoped claim ledger passes implemented checks, with no protection promotion.

Exact receipts, hashes and commands: [review evidence](../../evidence/protection-review-04/README.md).
No new routing, fabrication release, purchase or powered test is claimed.
The maintained `candidate/` PCB and its historical receipts remain unchanged.

## Next work, in order

1. Establish analog startup/reset and the complete detector-to-U9-off response
   for these exact devices and gate networks. Include partial AUX dropouts.
2. Select supported energy handling (or demonstrate an alternative), then
   model it with that response and the actual local capacitance over opening,
   startup and repeated bursts. A clamp may prevent the latch threshold from
   being reached; model both together.
3. Only after those decisions, integrate and route this construction, then
   rerun native and common validation and the installed thermal models.

Fault interruption and surge qualification remain separate open requirements;
see PROTECTION-SELECTION.md. General harness development remains frozen.

Tracked follow-up: [#1609](https://github.com/BennetLeff/temper/issues/1609).
