# Rev38 response-contract gate

Status: **OPEN — U1 has not passed.** This is a producer and response inventory for
the approved HOT-receiver architecture, not a released circuit or a safe-to-run
power stage. `fault-response.tsv` is the row-level companion. Rev35 and Rev37
are review fixtures; no Rev38 netlist, selected receiver, loaded-gate capture,
or assembled prototype exists.

## Decision this gate must make

An ESP32-S3 CPU-only reset can leave external GPIO levels unchanged. A HOT
receiver cannot distinguish that reset from continued source operation until
an independent indication or a qualified liveness timeout reaches it. The
contract must cover **both** (a) a PFC already RUNNING and (b) the first START
frame already in flight before reset detection. Two possible closures are:

1. **Independent indication:** demonstrate a source-reset signal that reaches
   HOT hardware before an in-flight START can set RUN, with a bounded path to
   source PERMIT clear, HOT RUN clear, and driver disable. A boot-time GPIO
   assignment, `SOURCE_RESET_GOOD` driven by firmware, or ESP `CHIP_PU` does
   not establish that behavior for a CPU-only reset. No such indication is
   identified in the present fixtures.
2. **Accepted bounded interval:** establish a product-approved maximum
   interval during which an already-running PFC may continue **and** a first
   queued START may be accepted after a CPU-only reset. The measured or
   guaranteed worst case must include any post-reset WDI edge, capacitor and
   TPS3431 tolerance, watchdog output assertion, source-latch capture,
   isolation and HOT clear propagation, local driver disable, loaded STW gate
   discharge, and actual current cessation. Approval of continued RUN alone
   does not approve the first START.

Neither option is accepted in the current evidence. If the product requires
that no first START can be accepted after the instant of CPU-only reset, the
bounded-watchdog option is insufficient. **Stop U2–U7 until this decision and
the applicable response limits are recorded.** A reset test of source policy
alone cannot pass this gate.

## Fault-to-current-cessation limit ownership

The power-stage/safety owner must define a maximum permissible interval for
each fault class from its hazard, current, stored energy, and installed voltage
limits. The interval starts at the declared physical fault or threshold and
ends at sustained switch-current cessation, not at a latch bit, EN edge, or
unloaded gate transition. The response budget must cover the producer/filter,
guaranteed capture, latch/logic, isolation where used, UCC27624 EN and output,
loaded STW gate, and commutation. Rows with no hazard-derived limit remain
**UNRESOLVED**; part choice cannot assign the limit retroactively.

The existing F2 timing audit leaves incremental inductance, current at trip,
installed voltage acceptance, filter delay, and loaded turn-off unbounded. Its
2.527 µs conditional remaining interval and 2 µs provisional design target
are **not** product limits. Its TLV3202/HCS21/HCS74/UCC27624 maxima use
different test fixtures and do not sum to a system guarantee. The source
TPS3431's 119.82–144.98 ms interval is for an ideal 1 nF CWD and excludes
capacitor tolerance and every downstream stage. Neither number passes this
gate. See `zapote/power-entry/passive-reva/protection/f2-timing-02/README.md`,
`interface-source-reset-32/README.md`, and `interface-integration-35/README.md`.

## Existing producers and Rev38 work

The Rev35 copy of `power_entry_f2_shutdown_revb.ato` has four TLV3202
comparator outputs for VD and VB absolute OV and both directions of VD/VB
mismatch, a fast AUX UV and AUX OV window, two TPS3890 rail outputs aggregated
as `rails_ok`, physical `permit_safe`, a retained link-good bit, and a HOT
TPS3431 output. `clear_ok` clears its RUN latch and qualifies enable. The
Rev35 join supplies only one reverse isolated receiver response, does not
instantiate complete F2/reservoir wiring, and uses UCC27511A; it is **not** the
proposed UCC27624 path. The separate Rev37 fixture returns physical HOT
PERMIT but lacks the retained HOT fault memory needed for a brief trip. These
are source/connectivity observations, not guaranteed electrical capture.

The Rev35 source maps VD OV `cmp_vd.OUT1` pin 1 to `health.A1` pin 1, VD/VB
mismatch `cmp_vd.OUT2` pin 7 to `health.B1` pin 2, VB OV `cmp_vb.OUT1` pin 1
to `health.C1` pin 4, and reverse mismatch `cmp_vb.OUT2` pin 7 to
`health.D1` pin 5. `health.Y1` pin 6 becomes `health_ok`; its second HCS21
gate also receives `rails_ok`, buffered PERMIT, and the AUX window, then the
separate link AND drives the Rev35 RUN latch's asynchronous clear. Both rail
supervisors expose active-low RESET on pin 6. This is a read of
`interface-integration-35/elec/src/power_entry_f2_shutdown_revb.ato`; U4
must re-audit the **new** compiled netlist, rather than inheriting these joins.

Rev38 must provide real producers and exact pins for: retained
`HOT_SESSION_OK`; independently retained HOT RUN; a default-asserted
`RECEIVER_ABORT_N` while MCU reset, unpowered, or high impedance; preparation
abort even while session Q is already low; physical HOT PERMIT high-then-low
memory; source physical-PERMIT-readback high-then-low memory and source latch
clear; separate reverse isolation for receiver response, physical PERMIT, and
retained HOT validity; and UCC27624 EN locally off in all invalid or partial
power states. The GPIO, supervisor, pullup, and isolator names in earlier
fixtures are not credit for these missing joins.

## State transition and physical action contract

All transition attempts are conditional on required rails and external faults
being healthy. A newly qualified external trip wins over a revalidation or
RUN-set edge; the selected silicon's clear/clock timing must prove this.

| From | Event | Next | Required physical action |
| --- | --- | --- | --- |
| Boot or Lockout | Physical source Q and HOT PERMIT observed low after invalidation; new durable receiver ID | Preparing | RUN low; source PERMIT low; receiver abort held until qualified preparation; no old identifier reused. |
| Preparing | Matching DISARM_ACK and one consumed revalidation with no new fault | Ready | HOT session Q may rise once; RUN stays low. |
| Preparing | New trip, STOP, receiver reset, or deadline | Lockout | Preparation-abort memory asserts even if session Q was already low; pending ID invalidated; both HOT latches clear. |
| Ready | STOP or receiver reset before PERMIT has ever risen | Lockout | `RECEIVER_ABORT_N` clears HOT session and RUN physically; low PERMIT alone is not credited. |
| Ready | Fresh button release and later press; physical PERMIT rises; REQUEST accepted | StartPending | Source and HOT physical readbacks must agree; fixed receiver START deadline begins. |
| StartPending | Matching START before deadline, with all hardware conditions still valid | Running | One RUN-set operation; START is consumed. |
| StartPending | START late, duplicated, cancelled, or from old ID; missing liveness | Lockout | No RUN-set; source PERMIT drops; new ID and fresh press required. |
| Running | Qualified trip, STOP, PERMIT loss after seen high, or receiver reset | Lockout | HOT session and RUN clear; driver EN falls; source latch clears on returned invalidity or established readback loss. |
| Any state | ESP CPU-only reset | Undecided until reset choice closes | Existing RUN and first in-flight START must meet the selected physical/bounded contract above. Boot code alone is not detection. |

Normal physical PERMIT low before its first high in a session allows
preparation; low after high is session-invalidating. A new trip during
preparation must be captured separately from the already-low session Q. A
held revalidation request cannot create a later clock edge when fault
eligibility returns. These are independent of message CRC or software state.

## Gate evidence and remaining inputs

| Input | Current finding | Closure evidence |
| --- | --- | --- |
| CPU-only reset choice | No independent indication demonstrated; bounded option unapproved | Product decision covering RUN and first START, then pin-level implementation and worst-case capture. |
| Fault-to-current limits | No accepted per-class maxima; F2 audit is conditional | Hazard-derived limits from power-stage/safety owner, including current/energy and voltage assumptions. |
| Actual fault producers | Rev35/Rev37 have partial circuit joins only | Rev38 exact-pin Atopile source, domain and channel census, negative mutations. |
| Capture minima and reset dominance | TPS3890 MR requires at least 1 µs low; new latch and pulse conditioning unselected | Datasheet corner checks and adverse pulse/clear-release tests for selected parts. |
| Loaded shutdown | No Rev38 hardware or capture | Assembled low-voltage fault injection with synchronized detector, latches, PERMIT, EN, VGS, and switch current. |

The first four rows determine whether digital implementation may proceed.
Physical capture remains a later, separately labeled NOT RUN campaign; digital
PASS cannot be reported as physical protection acceptance.

## Source basis

- Approved behavior: `docs/superpowers/specs/2026-09-23-power-entry-hot-receiver-design.md`.
- Rev35 joined fixture: `zapote/power-entry/passive-reva/protection/interface-integration-35/README.md` and its `elec/src/` files.
- Rev37 counterexamples: `zapote/power-entry/passive-reva/protection/interface-hardware-only-37/README.md`.
- Reset producer gap: `zapote/power-entry/passive-reva/protection/interface-source-reset-32/README.md`.
- Hazard arithmetic and evidence limits: `zapote/power-entry/passive-reva/protection/f2-timing-02/README.md`.
- Retained baseline: `zapote/power-entry/passive-reva/protection/ARCHITECTURE-REDUCTION.md`.
- Manufacturer behavior to recheck for selected parts: Espressif [ESP32-S3 restart behavior](https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-reference/system/misc_system_api.html), TI [TPS3431 watchdog timing](https://www.ti.com/lit/ds/symlink/tps3431.pdf), and TI [UCC27624 enable default](https://www.ti.com/lit/ds/symlink/ucc27624.pdf).
