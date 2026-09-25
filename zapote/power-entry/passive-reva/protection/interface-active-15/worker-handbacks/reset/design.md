# Hardware reset and permission boundary — candidate 15

This is a concrete interface candidate for review. It is not a released
schematic or a safety qualification. The important change from the reduced
timing model is that a source-side latch captures loss of reset/watchdog
health before the isolation delay and holds the permission low until a
deliberate re-arm pulse.

## Source-side capture

Use one SN74HCS74PWR half at the SELV coordinator, powered from its monitored
3.3 V rail. Name the two external health inputs `SOURCE_RESET_GOOD` (high
means the source supervisor is out of reset) and `SOURCE_WATCHDOG_GOOD`
(high means the independent watchdog window is healthy). A
SN74LVC1G08DBVR, powered from the same 3.3 V rail, forms
`SOURCE_HEALTH = SOURCE_RESET_GOOD AND SOURCE_WATCHDOG_GOOD`.

The HCS74 wiring is:

| U_SRC (SN74HCS74PWR) pin | net | purpose |
|---|---|---|
| 14 VCC | `SELV_3V3` | source logic rail |
| 7 GND | `SELV_GND` | source ground |
| 2 D1 | `SELV_3V3` | only a deliberate clock can set permission |
| 3 CLK1 | `SOURCE_REARM_PULSE` | operator/service re-arm, normally low |
| 1 CLR1 | `SOURCE_HEALTH` | asynchronous low clears the captured permission |
| 4 PRE1 | `SELV_3V3` | asynchronous set is never firmware-controlled |
| 5 Q1 | `PERMIT_LATCH` | captured permission into isolator |
| 6 QN1 | `PERMIT_LATCH_N` | optional diagnostic only |

Place 100 kΩ from `PERMIT_LATCH` to `SELV_GND`; the ISO7741F's F-side
default-low behavior is the safety fallback during source power loss. Add a
100 kΩ pull-down on `SOURCE_HEALTH`; it makes a powered-off or disconnected
health producer clear the latch. The health producer must itself be a
supervisor/watchdog output with a guaranteed low or an open-drain pull-down
when its rail is absent. A firmware GPIO asserted by the same processor does
not satisfy this contract.

`SOURCE_REARM_PULSE` is generated only after the source supervisor reports
healthy, the HOT receiver reports reset observed, and a newer session/fresh
intent is available. It is not the interlock's `RESET_N` pulse. A healthy
transition alone cannot re-arm the latch. If either health input drops, CLR1
clears Q1 asynchronously; a later high transition leaves Q1 low until the
deliberate clock edge.

## Isolation channel and HOT-side connection

For ISO7741F DWW/DW/DBQ pin naming, TI's ISO7741-Q1 pin map is used (the
non-Q1 F ordering must be checked against the exact orderable before capture):
VCC1=1, GND1=2/8, INA=3, INB=4, INC=5, OUTD=6, EN1=7, GND2=9/15,
EN2=10, IND=11, OUTC=12, OUTB=13, OUTA=14, VCC2=16.

| Channel | side-1 pin/net | side-2 pin/net | direction |
|---|---|---|---|
| A | 3 `COMMAND_TX` | 14 `HOT_COMMAND_RX` | SELV→HOT |
| B | 4 `PERMIT_LATCH` | 13 `HOT_PERMIT_RX` | SELV→HOT |
| C | 5 `RELAY_CMD` | 12 `HOT_RELAY_CMD` | SELV→HOT |
| D | 11 `HOT_RESPONSE_TX` | 6 `SELV_RESPONSE_RX` | HOT→SELV |

Tie EN1 (7) to `SELV_3V3` through 10 kΩ and EN2 (10) to `HOT_LOGIC5`
through 10 kΩ; add 100 kΩ pulldowns on both enables. This makes each side
disabled while its own supply is absent. The F variant's output defaults low
when input power or signal is lost. Keep 100 nF at each VCC pin group.

On the HOT side, route OUTB (13) through the existing `permit` receiver
boundary. Preserve its 10 kΩ pulldown and the existing Ioff-rated
SN74LVC1G17 `permit_buf`. Add one SN74LVC1G08 (`U_PERMIT_MERGE`) with
A=`HOT_PERMIT_RX` and B=`INTERLOCK_PERMIT`; its Y is the existing
`permit_safe`. This explicitly requires both the captured source permission
and the maintained interlock permission. Do not connect the isolator output
directly to the HCS74 asynchronous clear. `permit_safe` is one input of the
existing four-input health AND. Thus a captured source fault makes `clear_ok` low,
which drives a new, single-gate abort stage low. Use one
SN74LVC1G08DBVR (`U_HOT_ABORT`) with A=`clear_ok`, B=`HOT_WATCHDOG_GOOD`, and
Y=`clear_ok_hw`; route `clear_ok_hw` to the HOT HCS74 CLR1 and to the
`enable_good` AND. `HOT_WATCHDOG_GOOD` must be a hardware supervisor/watchdog
output, not a bit emitted by the frozen command decoder. This gives a
processor-independent HOT hang trip without consuming another ISO7741 channel.
The resulting low drives HCS74 CLR1 low and makes `enable_good` low at the
driver even if the HOT decoder is frozen.

The existing UCC27511A boundary remains: INP pin 6 receives PWM through 1 kΩ
and 10 kΩ pulldown; INN pin 5 is pulled to AUX15 by 1 kΩ and is pulled low by
the BSS138 only while `enable_good` is high. This path is a second local
disable condition, not a replacement for the captured permission latch.

## HOT arm authorization latch

Use the second half of the existing HOT `SN74HCS74PWR` as the hardware arm
authorization instead of tying it inactive:

| U_HOT HCS74 pin | net |
|---|---|
| 12 D2 | `HOT_LOGIC5` |
| 11 CLK2 | `SESSION_ARM_PULSE` |
| 13 CLR2 | `clear_ok_hw` (active-low asynchronous clear) |
| 10 PRE2 | `HOT_LOGIC5` |
| 9 Q2 | `arm_authorized` and U_HOT D1 (pin 2) |
| 8 QN2 | diagnostic only |

Change Q1 D1 (pin 2) from a fixed logic-high tie to `arm_authorized`; leave
Q1 CLK1 (pin 3) as the validated HOT `START` edge and Q1 Q1 (pin 5) as the
retained `RUN` state. Both halves now clear asynchronously through
`clear_ok_hw`; a frozen decoder cannot leave authorization or RUN set.
`SESSION_ARM_PULSE` follows HOT reset observation and valid source/interlock
conditions. It is a qualification edge, not a stale START replay.

## Timing claim and limits

The current TI ISO7741-family datasheet gives, at 3.3 V, a maximum signal propagation delay
of 18.5 ns and a maximum F-suffix disable low-transition delay of 30 ns under
its stated 15 pF test load. It also gives 0.3 µs maximum default-output delay
after a supply falls below 1.7 V. These are component limits, not the complete
stop time. The candidate budget is:

`Tstop = T_source_health_detection + T_HCS74_CLR + 18.5 ns + HOT_input_filter + T_LVC1G17 + T_HCS74_CLR + T_UCC27511_disable + T_gate_charge`

Only the isolator terms are bounded here. HCS74, LVC1G08/LVC1G17, source
supervisor, input RC values, the UCC27511A external 10 Ω gate path, and the
power MOSFET's Miller plateau/temperature trajectory still require worst-case
data or bench measurement. A captured pulse must be wider than the source
health supervisor's guaranteed response and HCS74 asynchronous-clear timing;
the present design does not claim an arbitrary analog glitch width.

## Required bench acceptance

Drive each source health input low separately and together while the HOT
decoder is held in a valid RUN/START state. Record source low-to-HOT_PERMIT_RX,
HOT_PERMIT_RX-to-`clear_ok`, `clear_ok`-to-INN high, and gate VGS fall at
minimum/nominal/maximum SELV and HOT rails, -40/25/125 °C fixture points, and
with the selected gate MOSFET. Repeat for source power removal, open health
input, stuck-high health input, isolator VCC removal, and a re-arm pulse before
and after the receiver reset acknowledgement. Acceptance requires that no
fault case reasserts `PERMIT_LATCH` without the deliberate re-arm sequence.

Known single-fault gap: a source health conductor failed high, or a
PERMIT_TX output stuck high, is not detected by this one channel. Closing that
gap needs a second independent trip path or a different channel allocation.
