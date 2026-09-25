# Reset hardware candidate — parent corrected

This pin-level proposal is for an isolated prototype. It has not been compiled
into revision 11. The source and HOT processor/supervisor/watchdog devices are
not selected; the named health inputs below are explicit integration contracts.

## SELV fault capture

All of this section is SELV3V3/SELV_GND. Do not take interlock PERMIT across the
barrier as an unisolated additional input. Two SN74LVC1G08DBVR gates form:

`SOURCE_HEALTH = SOURCE_RESET_GOOD AND SOURCE_WATCHDOG_GOOD AND INTERLOCK_PERMIT`

For each DBV gate, A=1, B=2, GND=3, Y=4, VCC=5. Gate A combines reset and
watchdog good; gate B combines its output and interlock permission. Use 10 kΩ
pulldowns on the three external healthy-high inputs and 100 nF bypass per IC.
These inputs require driven, rail-compatible levels. An open-drain supervisor
needs its own qualified pullup/interface; a pullup must not disguise a missing
producer. A firmware GPIO is not independent reset/watchdog evidence.

U_SRC is SN74HCS74PWR, powered at pin14, grounded pin7, bypassed 100 nF:

| Pin | Connection |
| --- | --- |
| 1 /CLR1 | SOURCE_HEALTH |
| 2 D1 | SELV3V3 |
| 3 CLK1 | SOURCE_REARM_PULSE, 10 kΩ pulldown |
| 4 /PRE1 | SELV3V3 |
| 5 Q1 | PERMIT_TX, 10 kΩ pulldown, to isolator pin4 |
| 6 /Q1 | No connect |
| 10 /PRE2 | SELV3V3 |
| 11 CLK2, 12 D2, 13 /CLR2 | SELV_GND (unused half held reset) |
| 8 /Q2, 9 Q2 | No connect |

Any recognized low health pulse clears PERMIT_TX and it stays low after health
returns. The source supervisor must hold clear low during startup until the
latch operates at a valid supply; a pulldown alone is not a power-on-reset
guarantee. The physical minimum captured pulse includes both AND gates and the
latch. It is not an arbitrary zero-width glitch guarantee.

Rearm sequence: keep both command pulse outputs low; establish all source
health inputs high; establish that the previous low interval reached and
cleared HOT hardware; then issue one deliberate SOURCE_REARM_PULSE. Only
after PERMIT_TX rises may the normal newer-session challenge/request/ACK/START
exchange proceed. This avoids waiting for a permission-dependent challenge
before raising permission. The low-interval requirement needs a measured and
bounded Tclear or an implemented reset acknowledgement; neither exists yet.
The interlock's fresh RESET_N pulse is not a substitute for SOURCE_RESET_GOOD.

## Isolation allocation

Reference package: ISO7741FDWR, non-Q1, DW16. Pin mapping is checked against
[TI ISO774x Rev K, Figure 4-2](https://www.ti.com/lit/ds/symlink/iso7740.pdf).
SELV3V3 goes to pin1; SELV_GND to2/8. HOT_LOGIC5 goes to16; HOT_GND to9/15.
Each supply has its own 100 nF bypass. EN1 pin7 and EN2 pin10 tie directly to
their respective local supply; they are not fault-control inputs.

| Function | SELV pin | HOT pin |
| --- | --- | --- |
| COMMAND_TX → HOT_COMMAND_RX | INA3 | OUTA14 |
| PERMIT_TX → HOT_PERMIT_RX | INB4 | OUTB13 |
| RELAY_CMD → HOT_RELAY_CMD | INC5 | OUTC12 |
| HOT_RESPONSE_TX → SELV_RESPONSE_RX | OUTD6 | IND11 |

Use 10 kΩ local pulldowns on command/relay inputs and received relay output;
retain the existing 10 kΩ HOT permit input pulldown and SN74LVC1G17 buffer.
The reverse response output receives a SELV pulldown. Communication must treat
loss/default-low as link loss, not a valid frame. Receiver supply absent means
an undefined output, not a driven zero; local rail supervision remains required.
This is a channel/pin proposal, not assembly creepage/insulation qualification.

## HOT authorization and direct shutdown

The existing health gate has all four inputs occupied: detector health,
rails_ok, permit_safe, and AUX-window health. Retain them. Add U_HOT_ABORT,
SN74LVC1G08DBVR powered HOT_LOGIC5: pin1=clear_ok,
pin2=HOT_WATCHDOG_GOOD, pin3=HOT_GND, pin4=clear_ok_hw, pin5=HOT_LOGIC5.
Add 10 kΩ pulldown at its external watchdog input and 100 nF bypass. This
watchdog must clear on HOT reset as well as missed heartbeat; its producer
and timeout are not selected. It is not the decoder's own health GPIO.

Repurpose the existing HOT SN74HCS74 second half:

| Pin | Connection |
| --- | --- |
| 12 D2, 10 /PRE2 | HOT_LOGIC5 |
| 11 CLK2 | Validated SESSION_ARM_PULSE, 10 kΩ pulldown |
| 13 /CLR2 | clear_ok_hw |
| 9 Q2 | arm_authorized; connect to pin2 D1, removing fixed-high tie |
| 8 /Q2 | No connect |
| 1 /CLR1 | clear_ok_hw, replacing clear_ok |
| 3 CLK1 | Validated START edge through existing ARM input buffer |
| 4 /PRE1 | HOT_LOGIC5 |
| 5 Q1 | Existing RUN net |

Both pulse inputs require HOT5-compatible levels, a low idle state, and a
fresh edge. An eventual 3.3 V MCU cannot be assumed to meet 5 V HCS thresholds;
its level translation and reset pin defaults remain design work. SESSION_ARM
must precede START by Q2 clock propagation plus D1 setup, with margin. Use
separate pulses at least 1 µs apart in the prototype; this is a stimulus choice,
not a proved full-corner bound. Clear must be inactive for its recovery time.

Change the existing enable AND input B to clear_ok_hw; input A stays RUN.
Its output drives the existing 1 kΩ/BSS138/100 kΩ gate network. UCC27511A
IN− pin5 remains pulled up to protected AUX through 1 kΩ; the BSS138 releases
it on disable. OUTL pin3 discharges the power gate through its existing 10 Ω.
The existing separate driver input path gives immediate disable while the
latches retain OFF. A frozen decoder cannot prevent an asserted hardware clear.
A decoder that later emits invalid new pulses remains a protocol/firmware fault
outside the frozen-output claim. Two latches do not validate frame contents.

## Timing evidence and remaining measurements

Rev K gives ISO signal propagation maxima 17 ns with both sides 5 V ±10% and
18.5 ns with both sides 3.3 V ±10%, at its 15 pF test fixture. Neither number
alone is a demonstrated limit for this mixed 3.3→5 V assembly. Its 0.3 µs
input-power-loss datum starts at VCCI=1.7 V with 10 mV/ns supply ramp, while
the output side remains powered. The 30 ns F entry is **enable into low**, not
an asserted fault's propagation time. No such term is summed as a full bound.

[SN74HCS74 Rev D](https://www.ti.com/lit/ds/symlink/sn74hcs74.pdf) specifies
19 ns maximum /CLR→Q at 4.5 V/50 pF, 42 ns at 2 V, and 11 ns minimum clear
pulse at its listed supplies. Source3.3V and HOT5V actual loading/ramp limits
need an applicable bound. The manufacturer's macro-model checks below verify
logical sequence only. The external BSS138 release, IN− pullup and actual
power MOSFET discharge must be included in Tstop; driver logic delay alone
does not establish current cessation.

See ../bench-plan.md and ../vendor-check/README.md. The proposed circuit still
cannot tolerate the shared PERMIT path stuck high by itself. That limitation
is retained rather than hidden in a passing reset test.
