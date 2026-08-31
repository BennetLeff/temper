<!-- provenance: commit=28c7e4c5cdbe0f1b4f6b86abefa4b9178c0557a6 dirty=false board_sha256=a65bb65c5247493637f9acb510769e604d0e407b256e87e1845160609052b13f kicad_cli=10.0.5 -->

# Duplicate relay contacts are physical pad occurrences, not repeated coordinates

**Date:** 2026-08-30  
**Board:** `pcb/temper.kicad_pcb`, SHA-256
`a65bb65c5247493637f9acb510769e604d0e407b256e87e1845160609052b13f`  
**Base:** PR #1544 at `28c7e4c5cdbe0f1b4f6b86abefa4b9178c0557a6`  
**Ground truth:** `kicad-cli` 10.0.5 project-context DRC  
**Board edits / threshold changes:** none

## Verdict

K2 and K3 intentionally fabricate two through-hole pads with the same logical
number for each high-current relay contact. A `(component_ref, pad_number)`
pair therefore identifies a logical contact, not a unique copper terminal.
Consumers that call first-match `Component.get_pin()` once for every repeated
`Net.pins` entry collapse two holes onto one coordinate and can neither route
nor audit the physical connection correctly.

The production closure experiment proves the missing physical operation. With
the terminal-admission occupancy correction in PR #1544 and `WDT_RESET_N` plus
`io0` routed first, both control nets connect and KiCad reports 15
`shorting_items` / 343 `unconnected_items`. Adding one 0.5 mm F.Cu segment
between K2's two physical pad-3 centres, `(137.32, 72.21)` and
`(144.82, 72.21)`, changes only `unconnected_items`, from 343 to 342. Every
violation category, including `shorting_items=15`, is unchanged.

The implemented production path generalizes that witness without hard-coding
K2 or a coordinate. Rust discovers occurrence-distinct same-number contacts and
selects local minimum-spanning edges; the board writer emits an edge only when
its full netclass-width footprint clears foreign copper. On the preserved
production output, that fail-closed gate emits K2's pad-4 edge and skips
intersecting candidates, including the manually-probed K2 pad-3 edge. The final
five-run KiCad sample is stable at **15/15/15/15/15 `shorting_items`** and
**341 `unconnected_items`**, one item below the required ceiling. Independent
pad connectivity reports all three `WDT_RESET_N` pads and all three `io0` pads
connected by copper.

This is causal closure rather than a threshold purchase: occurrence-aware
identity makes each physical terminal visible, a local collision gate adds only
proved-clear copper, and the production result improves connectivity without a
short, threshold increase, or board edit.

## The collapsed identity

K2 is `temper:Relay_SPDT_Schrack-RT314012`. Its physical pin list contains two
pad-3 entries, 7.5 mm apart, both assigned to `discharge.k_dis1-no`. The net's
logical pin list correspondingly contains two `("K2", "3")` entries. The
same shape exists on K3 and on the relay's other duplicated high-current
contacts.

The repository already has the correct identity type:
`temper-design-bundle/src/pad_occurrence.rs::PadOccurrence`, whose key is
`(pin_number, occurrence_index)`. The occurrence index is the zero-based
encounter order among a component's pins with the same name or number. The
Python owner in `temper_placer.core.pad_identity` and
`_pipeline_grid._net_pad_positions` already use that rule.

Two later Rust-live consumers still used first-match lookup:

- `temper-rust-router::terminal_planning::extract_net_terminals`
- `temper-orchestration::pipeline_route::run_collect_pad_positions`

Both must resolve the nth repeated net reference to the nth physical matching
pin. An unmatched extra reference is omitted; it must not synthesize a second
copy of occurrence zero.

## Measured alternatives

All rows used the same stripped production input and project-context KiCad DRC.

| experiment | target nets connected | `shorting_items` | `unconnected_items` | result |
|---|---:|---:|---:|---|
| corrected occupancy, geometric order | 0/2 | 15 | 345 | target regression |
| `WDT_RESET_N`, `io0` first | 2/2 | 15 | 343 | one physical gap remains |
| targets first + K2 occurrence-0↔1 pad-3 segment | 2/2 | 15 | **342** | acceptance witness |
| targets plus relay net globally promoted | 3/3 | 19 | 345 | rejected; order is non-monotonic |
| implemented declarative targets + collision-checked occurrence closure | 2/2 | **15** | **341** | accepted production path |

The rejected relay-priority row is why the repair is not “route every relay
net early.” Critical control-net order is board intent and belongs in a
declarative routing constraint. Duplicate-contact closure is local geometry
and must be emitted only after a foreign-copper clearance/creepage collision
check. Combining those two scoped decisions reproduces the measured witness
without perturbing unrelated routing priority.

## Oracle re-pin decision

The pinned terminal-extraction Python oracle encoded the historical
first-match behavior and therefore emitted occurrence zero twice for a
repeated `(ref, pad)` pair. Keeping that behavior would require changing the
corrected Rust back to a known-wrong physical model.

The oracle is deliberately re-pinned with this evidence to the occurrence
rule above:

1. enumerate matching physical pins in component pin-list order;
2. resolve repeated net references by `(pin_number, occurrence_index)`;
3. omit a reference whose requested physical occurrence does not exist;
4. retain first-match fallback only for legacy duck fixtures that expose no
   physical `pins` collection.

Differential and metamorphic tests retain the oracle, but now pin the correct
physical contract rather than the deleted ambiguity.
