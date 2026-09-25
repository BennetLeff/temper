# Mains entry: block A

Luna research handback, reviewed and condensed by the parent on 2026-09-22.
Read-only review of revision 09; no electrical or hardware acceptance.

## Ownership and contract

Fourteen compiled instances: bridge, holder, cmc, ntc, bypass, x2, mov,
r_relay_gate, r_relay_pd, r_relay_drop, relay_driver, relay_flyback, y1, mains.
The replaceable F1 link is represented by the holder and is not a second compiled
instance. Exact inventory: [component ownership](component-ownership.json).

Inputs: AC line/neutral/PE, HOT AUX15 and HOT relay command. Outputs: rectified
positive to block B and rectifier negative to B's shunt. Relay command defaults
low through the retained pulldown. The NO relay contact shorts the NTC; it does
not disconnect the mains when open. Y1 connects HOT bus return to PE through a
capacitor; it is not a direct DC bond.

Source: [candidate](../../../zapote/power-entry/passive-reva/protection/reference-revision-09/source-candidate/elec/src/power_entry_pfc_control_candidate.ato),
connections at lines 357–399 and 470–482.

## Findings and disposition

Retain the current rectifier, inrush and EMI/surge functions during the next
comparison. The choice of exact EMI components is conditional on emissions,
leakage and surge evidence. No deletion is justified by this review.

The bypass relay and its drive could be reconsidered only with a replacement
inrush/hot-loss/thermal case. Its 12 V coil and the source's 15 V/91 ohm drive
require toleranced pull-in, hold and dropout evaluation.
[TE RT33K012](https://www.te.com/en/product-2-1393240-3.html).

For the positive mains half-cycle, the failed-short MOS path is AC_L → F1 →
CMC → NTC or bypass → conducting bridge diode → Lboost → MOS drain/source →
control_gnd → shunt → bridge.MINUS → conducting bridge diode → AC return.
Trace the opposite half-cycle separately when building the next witness.
F2 is absent from this loop. Gate disable cannot clear a failed-short MOS.

F1 0034.3129 is the selected baseline link, not a demonstrated coordinated
interrupter. Its typical melting I²t is not total-clearing I²t.
[Schurter FST datasheet](https://www.schurter.com/en/datasheet/typ_FST_5x20.pdf);
[existing coordination record](../../../zapote/power-entry/passive-reva/protection/reference-revision-09/fuse-coordination.md).

## Next bounded deliverable

Create a source-fault envelope and F1 suitability table using published
application limits and explicitly bounded installation assumptions. Include
both mains half-cycles, bypass open/closed, and healthy/failed MOS states.
Separate topology coverage from clearing/withstand acceptance. Unavailable
prospective current or clearing data remains an external dependency; an
assumed SPICE source resistance cannot close it.

A reduced topology witness can proceed without a fuse clearing law if its
result is limited to identifying current paths. Coordination requires
applicable breaking/clearing limits and downstream withstand for the bounded
source. Hardware verification remains later.

## Parent corrections

The initial handback reversed part of the shunt/return ordering and described
the bank fault too narrowly. The final path above follows current source.
Bank discharge requires diode reverse conduction and a conducting MOS;
the MOS may still be healthy during turn-off delay. Simultaneous failed shorts
are one case, not the only case. EMI retention is a baseline choice, not a
claim that every component has been proved indispensable.
