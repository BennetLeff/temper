# Switch-short protection strategy: parent-reviewed scope

The model contains a gate-independent failed-switch branch from `sw` to
`channel_source`. The bridge and boost inductor feed that branch without
passing through F2. F2 connects the diode-side node VD to the bulk-bank node
VB. Opening that modeled branch can disconnect the bank, but cannot interrupt
the source-fed failed-switch route. Clocal remains on the VD side. This is a
connectivity result, not a measured interruption result; F2 stayed closed in
the attempted SW-SHORT experiment.

The complete archive of the shortened run contains an original last row with
`i(Lboost)=181.994403905508960 A`, `i(Vchannel)=181.994403511165075 A`,
`v(sw)=0.181994403511164887 V`, and `v(gate)=7.69773308048825069e-7 V`.
The worker initially confused switch-node and gate columns; the named frozen
Rust decoder header resolves them. q/en remain near5V and fault is0V, while
the PWM chain begins rising. The low gate is therefore not a retained external
shutdown witness. These are diagnostic samples from an incomplete nominal
model; they are neither whole-fault maxima nor physical current predictions.
The fixed inductor model does not bound saturation or temperature behavior.

The functional requirement is an independent means of interrupting the
source-fed failed branch, with its actuation/clearing behavior and unintended
restart behavior defined. An active detector/latch or a passive one-shot
protective device may implement that function; this report does not select
between them or claim qualification. The selected implementation must address
its actual interrupting voltage/current/energy and any required fault clearing
coordination. Remaining energy in VD/VB must be accounted for separately,
including a defined safe discharge/restart policy. F2 bank isolation alone is
insufficient for the failed-switch source path.

A future validation must observe source/failed-branch current separately from
gate/q/en, and distinguish bank current and VD/VB voltage. The device's actual
interrupting/withstand ratings and any arc/restrike behavior are manufacturer
or hardware questions. No new protection circuit is implemented or qualified.

The attempted case is INDETERMINATE because the solver stopped before662ms;
both validators rejected its endpoint. The declared bounded-execution policy
allows retaining this outcome. A repaired full run would be a separately
identified attempt with unchanged acceptance limits, not a prerequisite for
reporting this topology limitation. Root cause remains unknown; proposed
fixture84 is not ready for a causal experiment.

Authority: [partial-run disposition](../faults/settled-sw-short-59/full-SW-SHORT/parent-disposition-80.json),
[parent tail review and literal fields](../faults/sw-short-tail-parent-review-85.json),
[bounded fault contract](../faults/fault-matrix.md), and
[selected inductor model boundary](inductor-manufacturer-audit-72/vendor-model-parent-review-73.json).
