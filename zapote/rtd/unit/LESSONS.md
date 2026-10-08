# RTD unit lessons for the next unit owner

These lessons describe verified circuit, source and harness findings. They do
not certify physical hardware or imply that every current Rust check passes.
Use the final acceptance receipt for that status. Read this file before the
next unit's circuit model and layout work, and record which lessons were
applicable in that unit's handoff.

## Test each external conductor independently

An RTD-element open and an individual sense-wire open are different circuits.
The earlier REFIN−/ISENSOR window could miss a sense break while force current
continued. The revised window observes local RTDIN_P, and its LOW divider
returns to local RTDIN_N. The final circuit model exercises FORCE+, FORCE−,
SENSE+ and SENSE− separately, as well as healthy and short transitions.

For the next sensing unit, enumerate external conductors and power states
before choosing the model cases. A generic “sensor disconnected” case does not
prove coverage of every wire. Use the actual source topology and keep expected
fault behavior separate from observed model output.

Evidence: [circuit audit](../circuit/RTD_CIRCUIT_AUDIT.md),
[observed-model producer](../circuit/rtd_observed_faults.py), and
[independent replay and negative controls](evidence/root-circuit-final-review/receipt.json).

## Model capacitance at the actual electrical node

The RTD differential capacitor is connected at the ADC sense pins. An earlier
transient model placed it at the remote probe nodes instead. After a sense
wire opened, that model disconnected the capacitor from the node being
observed and reported an instantaneous crossing. Reconnecting it to the
source-defined local nodes produced a finite response.

Model net identity deserves the same scrutiny as PCB net identity. Check
which passive elements remain connected after each fault. Do not accept a
fast response just because a transient solver completed successfully.

Evidence: [frozen correct and deliberately wrong model comparison](evidence/root-transient-node-review/receipt.json).
This retained comparison predates final component-corner qualification; its
purpose is to prove the topology distinction, not supply the final timing bound.

## Require complete source-to-board identity

Checking a few supplied bindings left the rest of the unit unexamined. The
revised check rejects a one-binding input when the source and board contain
119 pads. Native ERC/DRC and schematic parity are useful independent checks,
but they do not establish exact purchased-part identity or complete Atopile
instance correspondence by themselves.

Carry the full component and pad census through source generation, editing,
and validation. Reject missing or duplicate identities. Do not derive an
expected net from the same observed net being checked.

Evidence: [complete source04 identity](evidence/root-source04-identity/receipt.json)
and [partial-binding rejection](evidence/root-source-binding-recheck-01/receipt.json).

## Check the return underneath the actual route

A ground zone and a nearby ground via do not establish a continuous return
for a signal. The RTD board passed native DRC while B-layer clocks crossed a
cut in their In2 ground reference created by a CS trace. Moving CS to F.Cu
removed that cut. Further endpoint ground stitches addressed distant return
entries.

Choose the reference layer from the actual signal layer. Inspect the filled
copper along the route, including holes and isolated islands. Legitimate
signal-via antipads require a local transition rule tied to real geometry;
a blanket distance allowance can conceal a genuine plane slot. Likewise,
proximity to a ground via is not proof that the via has a short connected
path to the relevant ground pad and plane.

Evidence: [explicit return correction](evidence/return-correction-01/routes-receipt.json),
[added return stitches](evidence/return-stitch-02/routes-receipt.json), and the
[coordinator audit](../../../docs/reviews/2026-09-10-1641-rtd-milestone-acceptance-audit.md).
The final Rust report must establish whether all required corridors pass;
these correction receipts alone do not do so.

## Prove the feedback loop with an actual board defect

Deleting an RTDIN− copper segment from a saved native copy produced a specific
Rust connectivity finding. An explicit agent-authored repair removed that
finding after native re-extraction. The frozen binary reproduced both reports.
This proves an editing-and-validation loop more directly than a suite of
synthetic JSON fixtures alone.

For each new unit, retain at least one representative native defect, its
specific finding, and the repaired artifact. Keep binary, input and source
identities so the proof can be replayed.

Evidence: [native defect and correction](evidence/native-open-correction/receipt.json)
and [independent frozen replay](evidence/root-open-correction-replay/receipt.json).

## Separate nominal response from a maximum guarantee

The TPS3890 timing table places its 18 us assertion delay in the nominal
column under specified conditions. It supplies no maximum in that row. A
model can use the nominal value with those conditions; it cannot turn it into
a guaranteed worst-case result by adding an unexplained margin.

Keep three distinct statements: the unit's observed or modeled behavior,
the response budget allocated at its interface, and any characterization
needed before the integrated system can claim that budget. Local rail-loss
logic ownership is separate from its dynamic delay. Upstream power loss is
also a different state: an unpowered pullup cannot assert a powered-high fault.

Evidence: [reviewed datasheet timing and limitations](evidence/root-tps3890-timing/README.md).
Physical timing is NOT RUN.

## Clear native fill caches before editing copper

Use the existing adapter's tested invalidation in both scratch replacement and
append destinations. Stale filled polygons caused KiCad to change authored
ground-via net identities during refill/save. Checking the net before refill
was insufficient.

Read the durable [KiCad stale-fill learning](../../../docs/solutions/architecture-patterns/kicad-stale-zone-fill-via-net-corruption-2026-09-10.md)
and run the maintained native adapter regressions when changing those paths.
