---
title: "The atopile-to-KiCad pipeline has no schematic-sync step, and when its source disagrees with hardware documentation on a safety-critical decision, resolve with an independent third source before picking a side"
date: "2026-07-14"
category: workflow-issues
module: pcb-schematic-capture
problem_type: workflow_issue
component: development_workflow
severity: critical
applies_when:
  - "elec/src/*.ato (atopile) and pcb/*.kicad_sch (KiCad) disagree on circuit topology, pin mapping, or component orientation"
  - "A design/reference doc and the atopile source give conflicting instructions for the same connection"
  - "Deciding whether to trust a generative source of truth (atopile) blindly for a safety-critical or mains-voltage decision"
tags:
  - atopile
  - kicad
  - pipeline-gap
  - source-of-truth
  - safety-critical
  - conflict-resolution
---

# The atopile-to-KiCad pipeline has no schematic-sync step, and when its source disagrees with hardware documentation on a safety-critical decision, resolve with an independent third source before picking a side

## Context

This project's `Makefile` build pipeline (`make netlist` -> `ato build`) only generates
`elec/build/default.net` and a BOM from the Atopile source. There is no step anywhere in the
pipeline that generates or syncs `pcb/*.kicad_sch` from `elec/src/*.ato` — `make footprints` is a
literal placeholder ("This would call `ato export footprints`... once FaC is fully integrated"),
and `make route` operates directly on the hand-maintained `pcb/temper.kicad_pcb`. Atopile does have
schematic-capable tooling (`ato view`, a KiCad plugin it offers to install on first run), but this
project's pipeline never wires it in.

This is the root cause of essentially every KiCad-vs-Atopile discrepancy found in an extended
schematic-repair session on this repo: a short circuit, a reset-pin miswire, a backwards IGBT, a
backwards bootstrap diode, an entirely unwired gate driver, a swapped comparator input, a
feedback-pin coordinate typo, and two backwards mains-rectifier diodes. None of these were caught
because nothing mechanically keeps the hand-maintained schematic in sync with the source of truth.

Mid-repair, the Atopile source itself was also found to contain two independent bugs (a wrong
physical pin map for `SN74HC4075` in `elec/src/components.ato`, and a reversed diode-orientation
statement for the voltage-doubler's `D2`). So "atopile disagrees with the schematic" does not
automatically mean "atopile is right" — the source of truth itself needs independent verification
for genuinely safety-critical decisions, especially ones a generative pipeline gap has left
unreviewed for a while.

## Guidance

When Atopile and the KiCad schematic (or a hardware design doc) disagree on something
safety-critical — mains-voltage rectifier polarity, in the case that prompted this — do not treat
either source as automatically authoritative. Instead:

1. **State the conflict precisely.** Identify exactly which claim disagrees: e.g. "design doc
   diagram says diode anode faces node X; atopile statement `ac_n ~ d2.A` says anode faces node Y."
   Vague "these don't match" isn't enough to reason about; write down the literal, specific claim
   from each source.
2. **Find or derive a third, independent check** rather than picking whichever source seems more
   convenient or was more useful earlier in the session:
   - Search for an external, well-established reference for the general circuit topology (a
     standard textbook/reference description of how the circuit class is supposed to behave — for
     a "Delon voltage doubler," a general search for how the topology operates, independent of this
     project's own possibly-buggy artifacts).
   - Independently re-derive the required behavior from first principles (in this case: which diode
     must conduct on which AC half-cycle for each output capacitor to charge correctly, worked
     through with KCL rather than by re-reading either source's notation a second time — re-reading
     the same ambiguous ASCII diagram again is not independent verification).
   - Only proceed once the external reference and the independent derivation **converge on the same
     answer**. If they don't, that's a signal to stop and ask, not to pick a tiebreaker arbitrarily.
3. **Apply the same rigor already used for other multi-source conflicts in this repo** (see the
   companion firmware-vs-schematic pin-map doc): working/tested artifacts and independently
   verifiable physics outrank a single generated source's variable names, especially when that
   source has already shown at least one unrelated bug.
4. **Verify the fix with the same connectivity tracer used elsewhere**, and watch specifically for
   this failure mode: naively swapping which wire endpoint reaches which pin (to "flip" a
   component's effective polarity without touching its symbol placement) can create a new
   short if the two wires' new paths overlap along the same coordinate line between the swapped
   pins. A polarity fix needs its own small reroute (a jog around the component, not a straight
   endpoint swap) plus its own tracer re-verification — don't assume a polarity fix is automatically
   safe just because the general wiring technique has been reliable elsewhere in the session.

## Why This Matters

A generative source of truth with a pipeline gap accumulates silent drift indefinitely — there is
no CI, DRC, or build step here that would ever catch a hand-maintained schematic diverging further
from `elec/src/*.ato`, so the divergence found this session (backwards diodes at 340V, a shorted
GPIO, an unwired gate driver) is not a one-time event; it will recur for any future hand-edit that
isn't independently verified. Treating the generative source as infallible is also wrong, though:
this session found two real bugs in `elec/src/components.ato`/`modules.ato` themselves. The correct
posture is neither "trust the schematic" nor "trust atopile" by default — it's "verify against
something independent of both" for anything where getting it wrong has real consequences (fire,
shock, a destroyed board).

## When to Apply

- Any disagreement between `elec/src/*.ato` and `pcb/*.kicad_sch` on connectivity, polarity, or
  pin assignment, especially at mains voltage, high current, or anywhere a wrong connection could
  damage hardware or create a safety hazard.
- Before wiring in `ato view` or the atopile KiCad plugin as an automated schematic-generation
  step for this project — the component-model bugs found this session mean generation should not
  be trusted blindly until the underlying `.ato` component definitions have their own independent
  verification pass.
- Any time a "quick tiebreak" between two sources is tempting under time pressure — that pressure is
  exactly when a wrong guess on a safety-critical circuit is most likely to go unnoticed until bench
  test or, worse, until deployed.

## Examples

The exact resolution sequence used for the Power_Input voltage-doubler diodes:

1. Design doc (`docs/hardware/VOLTAGE_DOUBLER_DESIGN.md`) ASCII diagram, read carefully, implied
   `D2`: anode toward `DC_BUS-`, cathode toward the AC node.
2. `elec/src/modules.ato`'s `ac_n ~ d2.A` implied the opposite: anode toward the AC node.
3. External reference (general web search on Delon voltage doubler operation): "During the positive
   cycle, the input forward biases D1... In the negative half cycle... the polarity forward biases
   D2" — a description of conduction timing, not wiring, but enough to check against.
4. Independent KCL derivation: for `D2` to pull `DC_BUS-` more negative on each cycle (required for
   charging), forward conduction must flow from `DC_BUS-` into the AC node, meaning anode must be at
   `DC_BUS-` — a hardware fact, not a token from either document.
5. Steps 1, 3, and 4 converged; step 2 (Atopile) was the outlier. Fixed the schematic to match the
   converged answer, documented the Atopile bug separately rather than silently patching it.

## Related
- `docs/solutions/tooling-decisions/kicad-schematic-connectivity-tracer-2026-07-14.md`
- `docs/solutions/workflow-issues/firmware-hardware-pin-map-divergence-2026-07-14.md`
- `docs/solutions/tooling-decisions/kicad-embedded-symbols-lose-pin-semantics-2026-07-14.md`
