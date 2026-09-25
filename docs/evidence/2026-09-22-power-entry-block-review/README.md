# Power-entry functional decomposition and protection review

Review completed 2026-09-22. The current 131-instance candidate is a useful
comparison baseline. Its component count is neither a rejection criterion nor
an accepted final budget. This review identifies each block's responsibilities,
shared interfaces and the evidence needed to simplify it.

Five bounded research tasks were dispatched to gpt-5.6-luna through native
subagents. The parent checked the source, reconciled their boundaries,
corrected stale or overly broad findings and owns this recommendation.
The block reports are edited research summaries, not independent electrical
acceptance certificates.

## Result

| Block | Current compiled count | Review result | Next bounded deliverable |
|---|---:|---|---|
| [A — mains entry](block-a-mains.md) | 14 | Entry/inrush functions retained; F1 interruption coordination remains open | Source-fault envelope and F1 suitability table |
| [B — PFC stage/controller](block-b-pfc.md) | 21 | No justified deletion; clamp, current/loop and physical loss bounds unresolved | Source-bound frequency/current/feedback design table |
| [C — bus protection/storage](block-c-bus.md) | 37 | Keep VD/VB observation; mismatch removal requires a dynamic comparison | Current detector versus a defined alternative across F2-open/restart cases |
| [D — gate permission/restart](block-d-gate-restart.md) | 53 | Largest consolidation target; slow/fast monitoring and standby/gate blocking have distinct roles | One rail/enable consolidation candidate checked against the same temporal contract |
| [E — supplies/interfaces](block-e-interfaces.md) | 6 | Existing support only; producers and HOT/system crossings remain incomplete | Producer/consumer, rail-envelope and external-assembly contract |
| Total | 131 | No reduction or complete-converter acceptance claimed | Integrate block results before choosing a revised circuit |

The [machine-readable inventory](component-ownership.json) assigns all 131
exported addresses exactly once. The 79-component protection module contains
47 resistors, 18 capacitors and 14 semiconductor packages. In the primary
allocation, C owns 30 of those parts, D owns 47 and E owns 2. The remaining
52 instances are the original 54-part section after the two duplicate gate
parts were removed.

These are review ownership boundaries. They do not imply five separate PCBs.
For example, the health AND package is counted to D but aggregates C's
outputs; C's reference is also used by D. E's small count excludes the
external supply and control hardware that still needs selection.

## Why this decomposition is useful

Component count alone hides the work. The PFC/controller circuitry is a
21-instance block; the surrounding protection, restart and rail behavior
accounts for most of the current complexity. Those functions must be judged
against actual fault and startup requirements. Keeping the existing candidate
allows each proposed simplification to be compared with a concrete circuit.

The controller already supplies current limiting, overvoltage response and
standby behavior. Those do not establish observation of both VD and VB, a
retained fault after supply return, or interruption of a failed-short switch.
[TI UCC28180](https://www.ti.com/lit/ds/symlink/ucc28180.pdf).

No reviewed evidence supports saying “131 is necessary.” It also does not
support a smaller target count or declaring the protection module unnecessary.
The conclusion is to challenge the costly functions at their interfaces while
retaining a stable comparison baseline.

## Block interfaces

The power path is A rectified output → B boost stage → VD → external F2 →
VB/bulk bank → downstream inverter. C observes VD and VB separately; its
four comparator outputs feed D. B sends PWM into D, which drives the MOS gate
and controller standby release. E supplies HOT rails and sequencing commands.

| Boundary | Producer/owner | Consumer | Contract that must survive integration |
|---|---|---|---|
| Rectified input / return | A | B | Current and source-fault envelope; return through the actual shunt path |
| VD and VB | B / external F2 / C bank | B feedback, C sensing, downstream load | Distinct nets; equality alone does not prove F2 continuity |
| Four detector outputs | C | D shared health logic | Separate push-pull signals with defined valid-supply polarity; no wired-OR |
| PWM, gate and standby | B PWM; D driver/inhibit | D, B MOS/controller | Fast gate control and controller-state behavior both assessed |
| HOT logic5 and AUX15 | E producer selection | A/B/C/D | Load budget, valid ranges, power order, ramp/dropout and recovery |
| ARM, PERMIT, relay command | E sequencing authority | D/A | Defined default, isolation/domain boundary and fresh-arm protocol |
| Stored energy and interruption | C plus A source boundary | B/C assembly | F1, F2 and local VD paths evaluated separately |

A healthy MOS still conducting during detection delay can participate in a
bank fault if the boost diode reverse-conducts. A failed-short MOS cannot be
cleared by a gate command. Local VD reservoir energy is outside F2.
[Existing fault-path record](../../../zapote/power-entry/passive-reva/protection/reference-revision-09/fuse-coordination.md).

## Simplification decisions

1. **Prioritize rail/enable consolidation in D.** The target is to reduce
   supporting logic while preserving a stated rail-loss and fresh-arm contract.
   Slow qualification and fast interruption capture cannot be merged by name
   alone. The selected supply envelope determines whether both responses are
   needed.
2. **Test mismatch removal in C as a specific hypothesis.** VD feedback and
   independent absolute OV might support a simpler arrangement, but existing
   evidence does not prove retained shutdown before every controller retry.
   Compare one explicit alternative against startup, running and residual
   restart cases. Keep separate bank observation.
3. **Keep B's divider/filter and standby-related functions until their
   electrical purpose is checked.** Series resistor count can reflect voltage
   rating; gate blocking alone does not prove controller reset/restart behavior.
4. **Do not use A's relay removal as an easy count win.** It trades component
   count against NTC loss, heat and startup behavior. No such trade has been
   accepted.
5. **Reuse system functions through E where supported.** Precharge sequencing
   and command generation may belong to existing system control, but their
   HOT-domain integration is not present merely because another unit exists.

The historical 21-part TLV1704 detector is not a validated replacement for
today's sensing block: its timing limits were unresolved and later work
changed the comparator architecture.
[Timing audit](../../../zapote/power-entry/passive-reva/protection/f2-timing-02/README.md).

## Order of the next work units

E's producer/consumer contract is the first integration dependency, because D
cannot simplify against an unspecified rail disturbance or ARM source.
Record current known values and unknowns without inventing a final supply
selection. In parallel, A can assemble the source/fuse envelope, B can bind
the current/frequency/loop assumptions, and C can specify the mismatch A/B
comparison and stored-energy boundaries.

Once E supplies a bounded rail contract and B/C supply the relevant shutdown
conditions, choose one D consolidation candidate and one C sensing alternative.
Each gets a small isolated fixture before any broad converter run.
A successful comparison must retain the required behavior, cover deliberate
negative controls and declare remaining physical/model uncertainty. A reduced
compiled BOM is reported only after the selected source actually exports.

Full-converter startup/regulation/fault checks and PCB adoption follow the
integrated candidate choice. Missing vendor fuse or diode guarantees remain
separate dependencies; unrelated analysis can continue without pretending
those dependencies are closed.

## Concrete documentation drift found

- RevB's source comment describes a 1 kohm logic5 bleeder, but its actual value
  and resolved BOM are 220 ohm. Power budgeting must use the actual source.
- The older INTERFACE-DESIGN document describes UCC27624; current RevB uses
  UCC27511A. Its enable/default and supply claims must follow the actual part.
- Historical fault-extractor review findings were initially repeated by a
  worker. Current extractor and resolution records show those specific defects
  have been fixed. Only the remaining model/brownout limitations are retained.

These discrepancies are recorded here; historical source/receipts were not
rewritten in this review.

## Verification and limits

The parent asserted the exact base commit, checked the current source/BOM/netlist
hashes against revision 09 records, confirmed both RevB source copies match,
and verified the one-owner inventory covers all 131 unique exported addresses.
Important device distinctions were checked against TI primary documentation;
the worker reports link their manufacturer sources. The parent read current
fault-extractor coverage to distinguish resolved findings from open ones.

[Source identity](source-identity.json) and [review receipt](review-receipt.json)
record the boundaries. No new converter simulation, native ERC/DRC, PCB change,
part qualification, vendor communication, commit or publication occurred.
The candidate remains partly untracked local work. This directory is durable
local storage, not an off-machine backup.

The external assembly list still includes the replaceable F1 link, F2 and its
holder/interconnect, local VD reservoir/treatment, supply/control producers,
any necessary isolation and connectors, and unrepresented cooling/mechanical
items. Therefore 131 is not the finished product assembly count.
