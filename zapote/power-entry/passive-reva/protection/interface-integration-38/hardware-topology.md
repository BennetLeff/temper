# Rev38 hardware join contract

Status: **pin-level design input**, not a compiled circuit or analog approval.
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
| ISO7741FDWR C | 5 INC, source relay request | 12 OUTC, HOT relay driver | Low requests relay off; no gate authority. |
| ISO7741FDWR D | 6 OUTD, source UART RX | 11 IND, AVR PA0/30 TX | Protocol response only. |
| ISO7742FDWR A | 3 INA, source hardware-health Q | 14 OUTA, HOT source-health clear | Low clears both HOT memories independently of receiver UART. |
| ISO7742FDWR B | 4 INB, source STOP_N | 13 OUTB, HOT STOP clear | Low clears both HOT memories; source GPIO default low. |
| ISO7742FDWR C | 5 OUTC, source physical-PERMIT readback | 12 INC, physical HOT PERMIT after isolator | A distinct reverse conductor, captured by source seen memory. |
| ISO7742FDWR D | 6 OUTD, source HOT validity readback | 11 IND, retained HOT_SESSION_OK Q | A distinct reverse conductor; low also inhibits source PERMIT. |

For each device pin 1/2/8 are SELV supply/returns, pin 16/9/15 are HOT
supply/returns, pin 7 EN1 is tied to the SELV supply, and pin 10 EN2 to the
HOT supply. The audit must check these physical pins rather than only net
names. The selected footprint is
`Package_SO:SOIC-16W_7.5x10.3mm_P1.27mm`; verify its pad dimensions against
the DW package drawing in the data sheet before a board claim.

## Retained hardware equations

These are required Boolean behavior, not a substitute for parts, pulse-width
or partial-supply analysis:

```text
BASE_OK = F2_DETECTORS_OK & HOT_RAILS_OK & HOT_WATCHDOG_OK
          & SOURCE_HEALTH_HOT & SOURCE_STOP_N & RECEIVER_ABORT_N
PERMIT_HISTORY_OK = !HOT_PERMIT_SEEN_Q | HOT_PERMIT_PHYSICAL
SESSION_CLEAR_N = BASE_OK & PERMIT_HISTORY_OK
RUN_CLEAR_N = SESSION_CLEAR_N & HOT_PERMIT_PHYSICAL & HOT_SESSION_OK_Q
DRIVER_ENABLE = HOT_RUN_Q & BASE_OK & HOT_PERMIT_PHYSICAL
```

`HOT_SESSION_OK_Q` and `HOT_RUN_Q` require separate retained elements with
asynchronous, active-low clear pins. `HOT_PERMIT_SEEN_Q` sets from the **HOT
physical** high transition and clears only in controlled physical disarm.
This permits initial preparation with PERMIT low, then makes a later low
PERMIT a sticky invalidation. STOP and receiver reset assert
`RECEIVER_ABORT_N` low even in READY before PERMIT first rises.

Revalidation must clock SESSION on the raw rising request edge with D equal
to current eligibility. **Never gate the clock with a recovering fault**:
if the request stays high while a fault clears, the clock must not acquire
a new edge. A separate preparation-abort memory captures any qualified new
trip after challenge publication, even while SESSION Q is already low. The
RUN-set clock likewise uses a raw request edge; D and asynchronous clear
require current SESSION, PERMIT, and fault validity. Neither START nor
revalidation may release an asynchronous clear.

The AVR PC3/9 disarm-history reset request must produce a bounded pulse that
ends **before** challenge publication. The pulse clears HOT permit-seen and
preparation-abort history only after both physical PERMIT nodes are low.
The AVR verifies PC4/22 seen Q low and PC1/7 preparation-abort Q low after
the pulse, then reserves the new durable ID and rechecks them after the
EEPROM write before publishing the challenge. A held PC3 level must not keep
either memory reset during preparation. The one-shot part, its timing
components, set/reset dominance during a coincident trip, and the target
adapter sequence still need selection and test; this is a U4/U5 completion
condition.

## Gate-driver boundary

The selected [UCC27624](https://www.ti.com/lit/ds/symlink/ucc27624.pdf)
has **typical internal pull-ups on ENA/ENB**, so an unpowered HOT logic rail
cannot be allowed to leave EN floating while AUX powers the driver. Use
channel A only: pin 1 ENA from a locally pulled-low `DRIVER_ENABLE` node,
pin 2 INA from the UCC28180 PWM, pin 7 OUTA through the gate resistor to
STW, pin 6 VDD on AUX and pin 3 GND on HOT0. Hold unused pin 8 ENB and pin 4
INB low locally; leave pin 5 OUTB unconnected. Check worst-case output-high
drive against the external ENA pull-down and EN threshold, and output-low
voltage against the internal pull-up. Confirm loaded STW gate discharge and
controller VSENSE inhibit independently.
The old Rev35 UCC27511A IN- behavior cannot be copied as a UCC27624 EN
guarantee.

## Evidence needed to promote this to U4 PASS

1. Select and compile the new latch, one-shot, AVR64DA32, ISO7742F,
   UCC27624, F2, watchdog, source memory, reservoir, and PFC parts in **one**
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
