# Rev38 hardware join contract

Status: **pin-level design input and partial source/receiver/driver/watchdog/rail/VD-VB compiled join**,
not a complete U4 circuit or analog approval.
This records the joins that must replace Rev35's connectivity-only fixture.
The existing F2 detector and power-stage values remain candidate inputs;
none of their typical delays establish a fault allowance.

## Two isolated devices, eight assigned channels

Both devices use the 16-pin wide SOIC package. `F` means the isolator output
defaults low when its input power or signal is lost, **not** that an unpowered
output can sink current. Fit a local pull-down at every safety-significant
output and check partial-power and leakage corners. Side 1 is SELV3V3/GND;
side 2 is HOT logic5/HOT0. No connector, resistor, or probe may join those
grounds directly. TI's [ISO774x data sheet](https://www.ti.com/lit/ds/symlink/iso7742.pdf)
gives the direction and physical pin map, and lists both selected ordering
codes as active production.

| Device/channel | SELV pin and producer/consumer | HOT pin and producer/consumer | Failure meaning |
| --- | --- | --- | --- |
| ISO7741FDWR A | 3 INA, source UART TX | 14 OUTA, AVR PA1/31 RX | Corrupt or absent traffic cannot count as liveness. |
| ISO7741FDWR B | 4 INB, source retained PERMIT Q | 13 OUTB, physical HOT PERMIT | Low clears RUN; loss after observed high also clears SESSION. |
| ISO7741FDWR C | 5 INC, source relay request | 12 OUTC, AVR PA5/3 input | The AVR PA2/32 alone drives the relay stage; low request cannot grant gate authority. |
| ISO7741FDWR D | 6 OUTD, source UART RX | 11 IND, AVR PA0/30 TX | Protocol response only. |
| ISO7742FDWR A | 3 INA, source hardware-health Q | 14 OUTA, HOT source-health clear | Low clears both HOT memories independently of receiver UART. |
| ISO7742FDWR B | 4 INB, source STOP_N | 13 OUTB, HOT STOP clear | Low clears both HOT memories; source GPIO default low. |
| ISO7742FDWR C | 5 OUTC, source physical-PERMIT readback | 12 INC, physical HOT PERMIT after isolator | A distinct reverse conductor, captured by source seen memory. |
| ISO7742FDWR D | 6 OUTD, source HOT validity readback | 11 IND, retained HOT_SESSION_OK Q | A distinct reverse conductor; low also inhibits source PERMIT. |

For each device pin 1/2/8 are SELV supply/returns, pin 16/9/15 are HOT
supply/returns, pin 7 EN1 is tied to the SELV supply, and pin 10 EN2 to the
HOT supply. The audit must check these physical pins rather than only net
names. The ISO7741F uses
`Package_SO:SOIC-16W_7.5x10.3mm_P1.27mm`. The ISO7742F currently uses a
distinct provisional footprint key: Atopile 0.2.69 otherwise exports both
same-footprint parts with ISO7741F metadata. Bind that key to reviewed DW
package pads and verify dimensions against the TI drawing before a board
claim.

Rev35's fixture tied an isolator relay output to an MCU output. Rev38 must
place the isolator channel on AVR PA5/3 **input** and use PA2/32 as the sole
HOT relay-driver output, with its own pull-down. The audit must reject a
short between those two producer pins.

## Retained hardware equations

These are required Boolean behavior, not a substitute for parts, pulse-width
or partial-supply analysis:

```text
HOT_PREP_TRIP_OK = HOT_ATTEMPT_VALID & SOURCE_HEALTH_HOT & SOURCE_STOP_N
                   & HOT_RAILS_OK & HOT_FAULT_N & HOT_WATCHDOG_OK
PERMIT_HISTORY_OK = !(HOT_PERMIT_SEEN_Q & !HOT_PERMIT_PHYSICAL)
SESSION_CLEAR_N = HOT_PREP_TRIP_OK & HOT_PREP_ABORT_OK
                  & RECEIVER_ABORT_N & PERMIT_HISTORY_OK
SESSION_REVALIDATE_D = SESSION_CLEAR_N & DISARM_Q
                       & !HOT_PERMIT_PHYSICAL & !HOT_RUN_Q
RUN_CLEAR_N = SESSION_CLEAR_N & HOT_PERMIT_PHYSICAL & HOT_SESSION_OK_Q
RUN_D = RUN_CLEAR_N
DRIVER_ENABLE = HOT_RUN_Q & HOT_PREP_TRIP_OK
                & HOT_PERMIT_PHYSICAL & RECEIVER_ABORT_N
```

`HOT_SESSION_OK_Q` and `HOT_RUN_Q` use separate retained elements with
asynchronous, active-low clear pins. `HOT_PERMIT_SEEN_Q` sets from the **HOT
physical** high transition and clears only in controlled physical disarm.
This permits initial preparation with PERMIT low, then makes a later low
PERMIT a sticky invalidation. STOP and receiver reset assert
`RECEIVER_ABORT_N` low even in READY before PERMIT first rises.
`DISARM_SEEN_AFTER_TRIP` is another SN74HCS74 retained element. Its D is the
physical HOT PERMIT inversion; its raw clock is AVR PF1/21, and its
asynchronous CLR_N is `HOT_PREP_TRIP_OK`. While PA6 attempt-valid is low,
the latter holds Q low. The AVR raises PA6, waits for the logic to settle,
then requests one PF1 edge while physical PERMIT and RUN read low; PC0/6
must read Q high on a later fresh sample. A new trip forces CLR_N low and
Q low, including at the clock edge. A held PF1 request cannot clock on
fault recovery. This prevents a pre-trip low level from masquerading as a
new disarm observation. A broken PERMIT wire may still set Q, but
DISARM_ACK, a new durable ID, and fresh intent remain separate requirements.
The external trip producer and rail/output-level timing still need proof.

The AVR PF0/20 samples the physical `HOT_SESSION_CLEAR_N` node. After the
matching DISARM_ACK and permit-history reset, the receiver releases
`RECEIVER_ABORT_N`, waits for a new physical sample showing
`HOT_SESSION_CLEAR_N` high, and only then issues the raw revalidation edge.
This is a distinct step because the clear cannot be high while abort is
asserted. A low readback aborts the attempt. The hardware clear remains
asynchronous and fault dominant; the readback only prevents a knowingly
ineffective or premature revalidation pulse.

Revalidation must clock SESSION on the raw rising request edge with D equal
to current eligibility. **Never gate the clock with a recovering fault**:
if the request stays high while a fault clears, the clock must not acquire
a new edge. A separate preparation-abort memory captures any qualified new
trip after challenge publication, even while SESSION Q is already low. The
RUN-set clock likewise uses a raw request edge; D and asynchronous clear
require current SESSION, PERMIT, and fault validity. Neither START nor
revalidation may release an asynchronous clear.

The two history resets are separate. PA4/2 requests a bounded reset of
preparation-abort memory **before** challenge publication, after physical
disarm. The AVR verifies PC1/7 Q low, reserves the durable ID, then rechecks
PC1/7 before publishing the challenge. Any new trip thereafter retains
preparation-abort Q high. After a matching DISARM_ACK, PC3/9 requests a
different bounded reset of historical HOT permit-seen memory while physical
PERMIT and RUN remain low. The AVR verifies PA3/1 seen Q low and PC1/7
preparation-abort Q still low before releasing abort and revalidation. This
follows the approved spec's order; resetting preparation-abort memory at
DISARM_ACK would erase evidence of a trip during preparation.

Held PA4 or PC3 levels must not keep either memory reset. In particular,
the PC3 pulse must have **no path** to preparation-abort clear. The one-shot
fixture selects two channels of [SN74LV221A-Q1](https://www.ti.com/lit/ds/symlink/sn74lv221a-q1.pdf)
with separate RC networks and raw active-low outputs. The part is
non-retriggerable and rated to 125 °C; this meets the held-request
requirement at the pulse generator. The first channel's positive Q clocks
an [SN74HCS74](https://www.ti.com/lit/ds/symlink/sn74hcs74.pdf)
preparation-abort memory with D low. Its asynchronous PRE1_N takes
`HOT_PREP_TRIP_OK` (locally pulled low) and forces Q high on a qualified
trip, including while the finite reset pulse is active. One
[SN74HCS21](https://www.ti.com/lit/ds/symlink/sn74hcs21.pdf) now drives
that input with both 4-input AND gates cascaded:

```text
HOT_PREP_TRIP_OK = HOT_ATTEMPT_VALID & HOT_SOURCE_HEALTH
                   & HOT_SOURCE_STOP_N & HOT_RAILS_OK
                   & HOT_FAULT_N & HOT_WATCHDOG_OK
```

The HCS21's output and every unproduced safety input have local low
defaults. The partial fixture now has a HOT TPS3431 WDO producer and two
TPS3890 undervoltage supervisors with open-drain RESET outputs wire-ANDed
on `HOT_RAILS_OK`. Four VD/VB TLV3202 channels and two AUX window channels
now feed `HOT_FAULT_N` through HCS21 fan-in. VD and VB now join the candidate
boost/F2/reservoir/bank path, but the AC input, AUX source, and source-side
health/STOP GPIO logic remain external. The compiled fan-in does not prove
fault capture. The provisional logic5 and AUX falling
thresholds are 4.531 V and 12.88 V nominal; see [HOT-RAILS.md](HOT-RAILS.md)
for the unclosed corners, [F2-DETECTOR.md](F2-DETECTOR.md) for the VD/VB
window topology, [AUX-WINDOW.md](AUX-WINDOW.md) for the fast-dip/OV
candidate, and [PFC-POWER.md](PFC-POWER.md) for the power path. PA6/4 drives
attempt-valid high before
the prep-reset edge and low on lockout, STOP, or reset, with a local
pull-down. `RECEIVER_ABORT_N` cannot serve this role while it is already low
through preparation. The second one-shot Q clocks a separate SN74HCS74
permit-seen memory. Its D is low only when a separate HCS21 gate verifies
disarm Q high, RUN and physical PERMIT low, preparation-abort Q low,
external/receiver trip fan-in healthy, and `RECEIVER_ABORT_N` still low.
Otherwise D is locally pulled high so a stray clock retains seen history.
A physical HOT PERMIT high goes through an
[SN74HCS04 inverter](https://www.ti.com/lit/ds/symlink/sn74hcs04.pdf)
to its asynchronous PRE_N, setting the seen bit even while a reset pulse
is active. Physical PERMIT low alone cannot clear a prior high. This is
still a pin-level priority candidate: DISARM_ACK is checked by receiver
firmware before issuing the edge, and the D qualification has not passed
propagation, setup/hold, and coincident-fault timing review. The minimum
preset pulse also needs electrical proof. Do not gate either
one-shot CLR_N with live faults: its low-to-high transition can
trigger a fresh pulse when A is low and B is high. Their installed width,
set/reset dominance during coincident trips, and target-adapter sequence
still need selection and test;
this is a U4/U5 completion condition. The 32-pin AVR package has PA3/1 and PA4/2, but **no
PC4 pin**; the physical package table is the authority for this allocation.

## Gate-driver boundary

The selected [UCC27624](https://www.ti.com/lit/ds/symlink/ucc27624.pdf)
has **typical internal pull-ups on ENA/ENB**, so an unpowered HOT logic rail
cannot be allowed to leave EN floating while AUX powers the driver. The
compiled `driver_stage.ato` candidate uses channel A only: pin 1 ENA has an
AUX-biased PMBT3904 shunt to HOT0, released by a HOT_LOGIC5-powered open-drain
inverter only when retained hardware permission is high. Pin 2 INA is the
UCC28180 PWM port; pin 7 OUTA reaches STW through 10 Ω, pin 6 VDD is
on `AUX_PROTECTED`, and pin 3 GND and the DDA PowerPAD are on HOT0. Pin 8 ENB
and pin 4 INB are grounded locally; pin 5 OUTB remains unconnected. The
controller PWM producer and a separate retained-permission VSENSE inhibit
are joined. The boost/diode/F2/reservoir/bank candidate is also joined, but
the AC input and AUX source remain external. Confirm loaded
STW gate discharge and controller VSENSE inhibit
independently.
The old Rev35 UCC27511A IN- behavior cannot be copied as a UCC27624 EN
guarantee.
The [ENA corner review](gate-enable-corners.md) records why a passive
pull-down alone has no data-sheet worst-case proof: TI specifies the
internal EN pull-up resistance only as a typical value. The active shunt is
now defined by pins, but its temperature, current, partial-rail and failure
corners are still open.

## Evidence needed to promote this to U4 PASS

1. Select and compile the remaining actual F1/EMI/NTC/relay AC input and
   AUX source in **one**
   Atopile 0.2.69 entry. Rev35's `clear_core_ok` includes PERMIT and cannot
   be reused as `SESSION_CLEAR_N`.
2. Audit every producer and consumer by physical pin; mutate each critical
   clear, reverse channel, power domain, and EN pull-down to prove a red gate.
3. Calculate guaranteed logic levels at cold/hot, partial-supply current,
   minimum captured fault-pulse width, latch clear and clock priority,
   isolator default/output-disable behavior, and worst-case driver EN path.
4. Carry the joined bill of materials and timing paths into U1, then create
   the native board and source/native parity receipt. Neither an Atopile
   graph nor a host state machine establishes fault-to-current cessation.
