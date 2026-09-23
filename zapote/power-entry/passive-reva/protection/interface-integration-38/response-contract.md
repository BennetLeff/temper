# Rev38 response-contract gate

Status: **bounded-reset candidate selected; numerical timing acceptance OPEN.**
This is a producer and response inventory for the approved HOT-receiver
architecture, not a released circuit or a safe-to-run power stage.
`fault-response.tsv` and `timing-analysis.md` are the row-level and timing
companions. Rev35 and Rev37 are review fixtures. A selected AVR64DA32
receiver and a partial Rev38 isolation netlist now exist; the joined
protection netlist, loaded-gate capture, and assembled prototype do not.

## Selected candidate reset contract

An ESP32-S3 CPU-only reset can leave external GPIO levels unchanged. A HOT
receiver cannot distinguish that reset from continued source operation until
an independent indication or a qualified liveness timeout reaches it. The
contract covers **both** (a) a PFC already RUNNING and (b) one START committed
to transmission before unexpected reset, after fresh user intent in the
current session. That already-issued START may produce at most one RUN
transition before watchdog detection while the fixed command deadline,
physical PERMIT, and independent HOT fault memory remain valid. Rebooted
source code cannot generate or retransmit it. START acceptance or reboot
activity cannot restart or extend the source-execution watchdog deadline.
The same reset-to-off limit applies if the PFC was already running or begins
running in the detection interval. After reset, source initialization must
invalidate external authorization and establish physical disarm before any
watchdog service capable of preserving permission resumes. Deliberate
software restart requires disarm and physical acknowledgement **before** the
restart request.

This selects the bounded-reset **candidate**, not a numerical interval or
protected-operation approval. The candidate needs a finite bound including
post-reset WDI edges, capacitor and TPS3431 tolerances, watchdog output,
source-latch capture, isolation and HOT clear, local driver disable, loaded
STW gate discharge, and sustained switch-current cessation. If the bound
cannot satisfy independently derived first-start and already-running
allowable times, revise the watchdog, protection, or reset architecture.
Parameterized protocol tests, reset-driver work, and circuit design may
proceed while timing inputs remain OPEN; they cannot turn this inventory into
a safety acceptance result.

### Bounded-option timing worksheet

Use worst-case maxima at the selected supply, temperature, loading, and
component corners. None of the symbols below has an accepted system value.

| Term | Meaning | Present evidence |
| --- | --- | --- |
| `T_postreset_WDI` | Time from CPU reset to the **last** possible qualifying source WDI edge, including bootloader, other core, timer, DMA, queued write, and restart-loop behavior | Unbounded until the actual ESP pin owner and reset paths are proved to withhold edges. |
| `T_TPS3431_max` | Maximum interval from that last edge to asserted physical WDO, with CWD tolerance, leakage, temperature, selected SET1/EN state, and watchdog configuration | Rev35's 144.98 ms is device-only at ideal 1 nF, not this term. |
| `T_source_clear` | WDO-to-source-PERMIT-latch-Q-low maximum, including WDO low width and asynchronous-clear capture | A partial Rev38 source/receiver netlist now joins WDO, source health, latch CLR_N and isolated PERMIT. Electrical timing and capture corners are unproved. |
| `T_permit_crossing` | Source-Q-low through isolation and HOT physical PERMIT-low qualification | No selected isolator or line/capture bound. |
| `T_hot_clear` | Physical PERMIT loss through retained HOT session and RUN clear, including seen-high capture | No joined Rev38 latch. |
| `T_driver_to_current_zero` | Local EN-low assertion through UCC27624, loaded STW gate discharge, and sustained switch-current cessation | A partial UCC27624/STW pin path now joins the receiver. ENA clamp corners, loaded gate/current waveform, and physical capture remain unproved. |
| `T_first_START_min_to_RUN` | Minimum reset-to-RUN time for a START already at the last receiver acceptance boundary when the CPU resets | Could approach zero; no positive minimum demonstrated. |
| `T_first_START_max_to_RUN` | Maximum time for a pre-reset START already in a transport, task queue, or GPIO-write path to reach the physical RUN-set operation | No receiver decoder, queue, or device implementation. |

The bounded continuation candidate must prove
`T_postreset_WDI + T_TPS3431_max + T_source_clear + T_permit_crossing + T_hot_clear + T_driver_to_current_zero`
plus a justified margin is at or below **both** independently derived
allowable times: first START after reset and continued RUN. If
`T_postreset_WDI` is unbounded because ordinary boot or another execution
path can keep feeding WDI, **there is no watchdog-based bound at all**. The
first-START behavior is selected only for a genuinely pre-reset committed,
unexpired command; a queued START may reach RUN before WDO asserts, but it
does not get another watchdog interval.
`T_first_START_min_to_RUN` cannot be assumed positive; an
already queued command may have arbitrarily little delay unless the real
transport and receiver enforce a lower bound. A source firmware reset handler
does not retract bytes or edges that have already crossed the isolation barrier.

An event-order counterexample explains why an instantaneous-detection claim
was not selected: place
the CPU-only reset immediately after the last START bit has crossed the
isolator but immediately before the HOT receiver's RUN-set operation. If every
external source pin retains its level, the receiver sees the same input trace
as a no-reset execution until an independent indication arrives. It cannot
reject the START solely because source software has reset. A later change to
an independent-reset architecture would need demonstration at the physical
RUN-set boundary, with fault/reset clear dominant for simultaneous set and
clear. Merely adding a message saying “reset” after reboot would not suffice.

## Fault-to-current-cessation limit ownership

The Rev38 timing work package must derive a proposed maximum permissible
interval for each fault class from its hazard, current, stored energy, and
installed voltage limits; a power-stage/safety owner must review it before
numerical acceptance. The interval starts at the declared physical fault or threshold and
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
| Running or StartPending | Unexpected ESP CPU-only reset | Lockout after one bounded hardware-supervised interval | Existing RUN may continue; one already-issued, unexpired START may set RUN once if all independent permission remains valid. Reboot cannot retransmit it or extend WDI. Source PERMIT and HOT RUN must clear by the same derived reset-to-off bound; later restart requires physical disarm and a new session. |
| Any authorized state | Deliberate software restart request | Lockout before restart | Source requests PERMIT low and observes local Q and physical HOT PERMIT low before asking the ESP to restart. |

Normal physical PERMIT low before its first high in a session allows
preparation; low after high is session-invalidating. A new trip during
preparation must be captured separately from the already-low session Q. A
held revalidation request cannot create a later clock edge when fault
eligibility returns. These are independent of message CRC or software state.

## Gate evidence and remaining inputs

| Input | Current finding | Closure evidence |
| --- | --- | --- |
| CPU-only reset behavior | Bounded-reset candidate selected for both RUN and one already-issued first START; no numerical duration accepted | Actual ESP WDI ownership and queued-command tests, independent allowable first-start/RUN times, and worst-case physical path. |
| Fault-to-current limits | No accepted per-class maxima; F2 audit is conditional | Derive per-fault allowable and implementation times independently from current/energy, voltage, derating, and joined-circuit evidence; record missing parameters in `timing-analysis.md`. |
| Actual fault producers | Rev35/Rev37 have partial circuit joins only | Rev38 exact-pin Atopile source, domain and channel census, negative mutations. |
| Capture minima and reset dominance | TPS3890 MR requires at least 1 µs low; new latch and pulse conditioning unselected | Datasheet corner checks and adverse pulse/clear-release tests for selected parts. |
| Loaded shutdown | No Rev38 hardware or capture | Assembled low-voltage fault injection with synchronized detector, latches, PERMIT, EN, VGS, and switch current. |

The chosen candidate behavior permits digital implementation to proceed with
missing numerical terms explicit. These rows remain closure gates for
numerical timing acceptance and any protected-operation claim. Physical
capture remains a later, separately labeled NOT RUN campaign; digital PASS
cannot be reported as physical protection acceptance.

## Source basis

`source-inputs.sha256` pins the exact local Rev35/Rev37/F2 files read for this
inventory. Recheck those hashes before treating a later edit to an untracked
historical fixture as the same evidence. The hashes bind source bytes, not an
approved design or a live measurement.

- Approved behavior: `docs/superpowers/specs/2026-09-23-power-entry-hot-receiver-design.md`.
- Rev35 joined fixture: `zapote/power-entry/passive-reva/protection/interface-integration-35/README.md` and its `elec/src/` files.
- Rev37 counterexamples: `zapote/power-entry/passive-reva/protection/interface-hardware-only-37/README.md`.
- Reset producer gap: `zapote/power-entry/passive-reva/protection/interface-source-reset-32/README.md`.
- Hazard arithmetic and evidence limits: `zapote/power-entry/passive-reva/protection/f2-timing-02/README.md`.
- Retained baseline: `zapote/power-entry/passive-reva/protection/ARCHITECTURE-REDUCTION.md`.
- Manufacturer behavior to recheck for selected parts: Espressif [ESP32-S3 restart behavior](https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-reference/system/misc_system_api.html), TI [TPS3431 watchdog timing](https://www.ti.com/lit/ds/symlink/tps3431.pdf), and TI [UCC27624 enable default](https://www.ti.com/lit/ds/symlink/ucc27624.pdf).
