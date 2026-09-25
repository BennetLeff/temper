# Parent disposition: controller threshold coverage

This supersedes the two retained worker audit snapshots. No new simulation or
accepted circuit source was changed. The older controller-integration-06 unit
receipts cannot by themselves establish coverage of the current accepted
controller: the ICOMP law, reset behavior, PWM hold, blanking and output edges
have changed. The separate parent-reviewed `accepted-controller-test-binding-54.md` now
binds controller-finite-edge-safe receipts to the exact accepted controller
bytes. Those receipts cover nominal controller behavior only.

The actual accepted cold.cir connects the controller VCC pin to the ideal
aux15 source, prescribed as PWL(0 0 5m 15 200m 15). It is an external supply
stand-in, not a modeled auxiliary converter. Its 0-to-15 V ramp crosses the
published 10.8-to-12.1 V turn-on voltage range at 3.6-to-4.033333333 ms.
At its held 15 V level, the source is 2.9 V above the largest turn-on threshold
and 4.7 V above the largest turn-off threshold. These are source-defined
voltage-condition margins only. They do not bound actual gate-enable time,
converter startup, real supply droop, dynamic silicon response or regulation.
Other permit, arm and standby inputs inhibit operation later in this netlist.
The nine grid transformations retain the same prescribed auxiliary supply.

The accepted UVLO switch uses Vt=10.5 V and Vh=1 V, corresponding to nominal
11.5/9.5 V thresholds. A hypothetical threshold sensitivity must satisfy all
three published ranges together: on 10.8..12.1 V, off 9.1..10.3 V, and on-minus-
off 1.6..2.0 V. The resulting feasible polygon has vertices (10.8,9.1),
(10.8,9.2), (11.9,10.3), (12.1,10.3), (12.1,10.1), (11.1,9.1) V. Separate
printed typical values do not establish a jointly correlated device corner.

The old pin-forced functional fixture's 12.0 V plateau does not guarantee
turn-on for a 12.1 V threshold. Its 10.0 V plateau was intended to test HOLD,
not turn-off; hold is not guaranteed at the largest 10.3 V turn-off threshold.
That older fixture is not the accepted cold-start supply waveform. Changing
its plateaus and repeatedly simulating the same authored switch would not
qualify the real auxiliary supply or silicon.

Disposition: no UVLO sweep is needed to establish the limited ideal-rail
voltage margin above. Exact-source nominal functional-test provenance is now verified in the companion audit.
The TI vendor-model, timing/corner and physical auxiliary-supply gaps remain.
Authority: retained TI UCC28180 RevD electrical table 7.5 (printed page 6),
https://www.ti.com/lit/ds/symlink/ucc28180.pdf. Parent independently extracted
and checked the three UVLO rows. Input hashes are in the adjacent parent
review JSON. This is analysis of declared source conditions, not acceptance.
