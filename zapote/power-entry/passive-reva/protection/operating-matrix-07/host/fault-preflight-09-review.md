# Fault preflight host review

This records preparation, not executed fault acceptance. The full hysteretic
startup reached 0.5 s with 22,686,813 finite, strictly increasing rows. The
unchanged electrical checker rejected only unsettled bus-cycle drift. A
650 ms cold extension is running; no baseline has been accepted.

## Materializer

The host reviewed the seven branch mutations and independently compiled the
materializer with warnings denied. All eight tests passed, including byte-exact
inverse reconstruction for all seven cases and reversal of the BYPASS change.
The failed-switch branch returns through `Vchannel`; the failed-diode branch
is parallel to Dboost1 and passes through its added sense source. F2 and both
diode legs have 0 V current-sense sources. Normal diagnostic vectors remain.

Review corrected an unclosed F2 PWL expression, discontinuous event markers,
a duplicated final pacing time, missing output hashes, and tests whose names
claimed more than their original assertions proved. The final preparation
uses continuous control-derived markers and a strictly ordered PWL schedule.
The generator's known six-file source closure is narrow; it is not a general
SPICE dependency parser. Source identity and actual ngspice smoke results are
required in addition to its tests. The source endpoint parser accepts the
500m and 650m cold sources while preserving their other bytes. A parent-run
materialization from the actual 650m source produced the same tiny F2-CREST
deck byte-for-byte as the earlier 500m source preparation.

## Timing

The campaign uses predeclared injection time as `EXPECTED_FAULT`, with a 2 ms
search window for F2 crest and 10 ms for zero/startup. The existing 2 us
post-detector turn-off budget is unchanged. Pacing begins at injection minus
that window minus 25 ns and continues to the endpoint. Startup requires a
verified healthy armed prefix at least 10 ms long; an unarmed test is a
different contract. The timing note is analytical planning, not a measured
latency or guaranteed bound. Review corrected two factors of 1000: the local
bleed estimate is about 0.317 s, and 2 us is about 0.258 switching periods.

## Schematic and model boundary

The reviewed topology belongs to `power_entry_passive_reva.ato`. That source
does not yet contain the proposed F2/VD/VB split. The simulation includes it
as an ideal controlled switch, not a melting/arc/current-clearing fuse model.
The current 07 plant includes AC bridge, source, NTC/bypass and winding
resistances; descriptions of the old 04 ideal DC source do not describe 07.
An early delegated draft cited the different active-unit schematic; review
rebound it to the passive source and made the distinction explicit.

The proposed F2 can isolate the bank's discharge path, but it cannot remove
local diode-side stored energy or interrupt the separate mains-to-failed-MOS
path. Gate-off cannot open a failed-short device. Fuse assembly, source
impedance, DC clearing and parasitic limits remain physical-validation needs.

## Tracker and adapter verification

All seven tiny 20 us decks ran in fresh processes with the required
`SPICE_SCRIPTS` initialization. The parent independently compiled the final
trace verifier and checked each exported trace: 42 unique columns, all finite,
strictly increasing time, complete 20 us endpoint, all normal and fault
vectors, and actual solver gaps at most 13.297 ns across the required local
window. Larger gaps before the 25 ns instrumentation lead are outside that
window; no resampling or timestep relaxation was used. These unpowered
startup smokes establish parsing/export and sampling only, not protection.

The parent also independently compiled adapter-09 and passed all 14 tests.
Its narrow additions support F2-START with the existing healthy-prefix/F2-edge
contract, accept the SW-SHORT alias, and require an F2 edge for BYPASS-NEG.
No old adapter or electrical acceptance threshold was changed.

## Pending before fault execution

Accept the complete settled normal startup, bind the materializer to that
source's endpoint, select source-bound injection phases, and verify the
instrumented prefault operating window. F2-START must use the declared
10 ms healthy-prefix contract. No prepared deck, unit test, short export
smoke or ideal-switch result alone supplies those receipts.
