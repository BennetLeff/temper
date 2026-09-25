# F2 shutdown circuit review

Review date: 2026-09-19  
Scope: read-only review of the isolated F2 experiment. I read the plan, the
canonical Atopile source, `f2_shutdown.rs`, `compiled-bridge.json`, the
`source-01` export, and `device-audit.md`. No schematic or PCB was created and
no repository files were changed.

The pin declarations and the present detector graph are otherwise consistent
with the retained TI pin tables: TLV3202 pins 1/2/3/4/5/6/7/8, HCS21 NC pins
3/11 and gate pins 1/2/4/5/6 and 9/10/12/13/8, HCS74 pins 1/2/3/4/5/6 and
13/12/11/10/9/8, and UCC27624 pins 1/2/3/4/5/6/7/8. All four comparator
outputs are separate nets and the two VD/VB dividers are separate in the
compiled bridge. The findings below are the material issues and evidence gaps.

## Findings

### F1 — Gate resistor is the wrong package and MPN (high confidence, P1)

`elec/src/power_entry_f2_shutdown.ato:253-256` selects
`RC0603FR-0710RL` with `R_0603_1608Metric` for the 10-ohm gate resistor. The
retained passive drive baseline calls for `RC1206FR-0710RL` / `R_1206_3216Metric`.
The 0603/0.1-W part is not a like-for-like replacement for the retained gate
interface and has no pulse/average-power derating evidence for this driver and
MOSFET. The source comment says the 10-ohm baseline is retained, but the
package and MPN were changed.

The current Rust test has already been changed to require the 1206 MPN and
footprint (`zapote/packages/zapote-erc/tests/f2_shutdown.rs:179-181`), so a
fresh source build should keep this guard. The retained `source-01` export still
contains the 0603 part, however, and cannot be used as evidence for the fixed
source.

### F2 — Q is wired directly to UCC27624 ENA across the 5-V/15-V domains (high
confidence, P1 for any default-off or physical claim; explicitly unqualified
for this isolated experiment)

`elec/src/power_entry_f2_shutdown.ato:236-249` connects HCS74 `Q1`/`run`
(`latch` pin 5) directly to UCC27624 `ENA` (driver pin 1), with only the 2.2-kΩ
pulldown on that same node. UCC27624 has an internal EN pullup, about 200 kΩ
typical with no minimum/maximum specified; its EN pins float enabled. Thus the
5-V HCS74 output is directly exposed to an aux15-powered input pullup. In the
Q-high state the unknown pullup current is forced into the HCS74 output, and in
logic5-off/aux15-on states the node's behavior depends on unpowered output and
clamp behavior. This is the exact topology that `device-audit.md:40-58` says
not to use; that audit recommends an isolating clamp/level interface and says
the 2.2-kΩ calculation is typical-only. The current source has no isolator.

This does not require adding the rejected 133-part supervisor, and the plan
explicitly leaves unpowered/back-power behavior unqualified. It does mean the
compiled connectivity test (`f2_shutdown.rs:135-138`) proves only that ENA is
connected to `run`; it cannot support a rail-off default-off or hardware
qualification claim. The unpowered/aux15-on case must remain an explicit
indeterminate interface condition until an isolation stage or a bounded
electrical analysis is supplied.

### F3 — The retained compiled receipt is stale relative to the current source
(high confidence, P1 evidence-integrity issue)

`source-01/resolved-components.json` records source hash
`a1db21a831ce17342da72bae46ee39a6ea4116cd302aa71a56d3376050a218a7`, while the
canonical `elec/src/power_entry_f2_shutdown.ato` currently hashes to
`dcd9d65f77fad557b46a8bee92915782abec24cd5478c1a0583ade9927a40c69`. The
`source-01` export also still records the 0603 gate resistor. Nevertheless,
`compiled-tests.txt` reports five passing shutdown tests. That receipt predates
the current source/test state; it is not evidence that the present source and
the new 1206 expectation compile and pass together. Rebuild the bridge/export
after the source correction and replace the receipt before accepting the
result.

### F4 — Latch PRE1 is not asserted by the graph test (medium confidence, P1
false-pass in the test)

The source correctly ties `latch.PRE1` (HCS74 pin 4) to `logic5` at
`elec/src/power_entry_f2_shutdown.ato:223-227`, leaving asynchronous preset
inactive. `ready_and_latch_enforce_external_rails_permit_and_fresh_arm_edge`
checks CLR1 (pin 1), D1 (pin 2), CLK1 (pin 3), Q1 (pin 5), VCC (pin 14) and GND
(pin 7), but never checks pin 4 (`f2_shutdown.rs:121-138`). A source mutation
that tied PRE1 low would therefore pass all five current tests while forcing Q
high asynchronously, defeating default-off/fresh-arm behavior. Add an exact
assertion that `p["latch.4"] == p["latch.14"]` and retain the active-low PRE
polarity in the test.

### F5 — Reference anode and divider returns are not covered by the compiled
graph tests (medium confidence, P1 false-pass in the test)

The source currently connects `reference.A` (LM4040 pin 2) and both divider
grounds to `gnd` (`elec/src/power_entry_f2_shutdown.ato:165-181`). The tests
only assert the LM4040 cathode/ref25 net through comparator pin 3 (`f2_shutdown.rs:93-103`);
they never assert `reference.2 == gnd`, `vd_div.bottom.2 == gnd`, or
`vb_div.bottom.2 == gnd`. A source mutation to an aux/logic return would pass
the existing five tests while removing the reference return or changing both
sense ratios. Add exact return-net assertions, plus bypass-cap rail/ground
checks if those capacitors are part of the retained connectivity contract.

### F6 — Several topology assertions use substring matching (medium confidence,
P2 test robustness)

`f2_shutdown.rs:128-129`, `:133`, `:144`, and `:147` use `.contains("rails")`,
`.contains("permit")`, `.contains("arm")`, `.contains("pwm")`, and
`.contains("aux")`. A wrongly renamed or aliased net such as
`rails_ok_fault`, `arm_return`, or `pwm_test` would satisfy these checks. The
source-hash binding does not make the assertion itself exact: a newly compiled
wrong source would update the hash and still pass. Use exact net names for the
external interfaces, while retaining the existing physical-pin checks.

## Scope and non-findings

The review did not treat the externally supplied `rails_ok` contract as a
missing power supervisor: the plan explicitly defines it as an aggregate valid
5-V/aux/reference indication held low through startup. The second HCS21 gate
count is sufficient for health AND rails/permit qualification, and the HCS74
CLR/D/raw-ARM arrangement is logically the intended retained, fresh-edge
behavior. HCS21 NC pins 3/11 and the unused HCS74 half inputs are defined/open
according to their device functions; UCC INB/ENB are tied low and OUTB is
unused. These are graph-level observations only. They do not qualify the
unpowered back-power path, comparator input clamps, analog thresholds, or an
end-to-end 2-us shutdown result.
