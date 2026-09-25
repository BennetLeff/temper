# Capture review: interface-active-15

Reviewed the parent-corrected `clamp/design.md`, `reset/design.md`, and
`bench-plan.md` against the current manufacturer datasheets for LT4363 Rev C,
ISO774x Rev K, SN74HCS74 Rev D, and SN74LVC1G08 Rev AA. The pin tables below
are otherwise consistent with those sources.

## Actionable findings before capture

### P1 — LT4363 input bulk and ceramic-ratio requirement is missing from the clamp netlist

The LT4363 datasheet requires at least 22 uF low-ESR bulk close to the source
pin of the pass MOSFET and says this bulk should be at least 10 times the total
ceramic bypass capacitance on the downstream converter input (Rev C, p. 15,
lines 1634–1637). `clamp/design.md` only specifies the 35–100 uF *downstream*
protected capacitance and 100 nF VCC bypass. The existing upstream LDO output
capacitor must not be assumed to satisfy the placement, ESR, or 10:1 ratio.

**Exact correction:** add an explicit `AUX_RAW` bulk capacitor, minimum 22 uF
effective at bias/temperature/aging, located at Q1 drain-to-HOT_GND, and a
capture/acceptance check that its effective value is at least 10× the sum of
all downstream ceramic converter-input bypass capacitors. Record its actual
part and derated value before the transient test.

### P1 — fault capture has no defined hardware connection to LT4363 /SHDN

The reset design's source/HOT latches clear `PERMIT_TX`, `arm_authorized`, and
`RUN`, while the clamp design leaves `/SHDN` as a local service contact only.
That is internally coherent if the LT4363's own timer is the sole AUX cutoff,
but the worksheet calls R3 a “hardware trip” and R5 measures a complete stop
path without stating whether AUX `/SHDN` is intentionally excluded. A source
health fault therefore does not force the surge-stopper into its low-current
shutdown state; only the downstream driver path is guaranteed to be disabled.

**Exact correction:** label `/SHDN` in the capture as either (a) deliberately
service-only, with R3/R5 acceptance explicitly limited to driver/PFC shutdown,
or (b) driven by a separately qualified hardware fault/reset net. Do not leave
the net visually unconnected while claiming a complete hardware trip.

### P2 — SOURCE_REARM_PULSE producer and its power-on default are still an open pin

The source HCS74 D input is tied to 3.3 V and `SOURCE_REARM_PULSE` clocks the
latch. The fault-clear path is firmware-independent, but a floating or
firmware-owned rearm input could create an unintended rising edge during SELV
brownout. The document mentions a 10 k pulldown but does not assign a physical
connector/test point or state the required source-reset behavior.

**Exact correction:** capture the 10 k pulldown at the HCS74 CLK1 pin and
expose the producer as a named interface/test point with an explicit
power-on-low requirement. Require the producer to issue no edge until
`SOURCE_HEALTH` is high and the LT4363 reset/clear acknowledgement (or the
chosen measured substitute) is present.

### P2 — HCS74 timing numbers are used only for logic, but the mixed-voltage path needs a stated setup margin

The SN74HCS74 pin assignments are correct (PW package: VCC 14, GND 7,
1CLR/1D/1CLK/1PRE/1Q at 1/2/3/4/5, and 2CLR/2D/2CLK/2PRE/2Q at
13/12/11/10/9). At 4.5 V the specified CLK-to-Q and CLR-to-Q maxima are
19 ns; at 2 V they are 42 ns. The reset design correctly avoids summing these
as a complete stop bound, but its “separate pulses at least 1 us apart” is only
a stimulus choice. The future 3.3 V source producer and 5 V HOT producer need
actual HCS74 setup/hold and clear-recovery measurements before that spacing is
used as an electrical requirement.

**Exact correction:** keep 1 us as a bench stimulus, and add the measured
setup/recovery values to the R4/R6 acceptance record; do not encode 1 us as a
datasheet timing guarantee.

## Confirmed correct details

* LT4363 MSOP-12 `-1` pin mapping is correct: 1 FB, 2 OUT, 3 SNS, 4 GATE,
  5 VCC, 6 SHDN, 7 GND, 8 UV, 9 GND, 10 FLT, 11 ENOUT, 12 TMR. The -1
  variant has no OV comparator; the proposal does not connect an OV pin.
* The Figure 5 gate network orientation is correct: the diode cathode is on
  the capacitor node (anode at the gate), so charge bypasses the 100 ohm
  resistor while pull-down uses the resistor. The 470 nF value remains a
  prototype choice requiring turn-off/SOA measurement.
* ISO7741 DW-16 mapping is correct: VCC1=1, GND1=2/8, INA/B/C=3/4/5,
  OUTD=6, EN1=7, GND2=9/15, EN2=10, IND=11, OUTC/B/A=12/13/14,
  VCC2=16. The 3-forward/1-reverse allocation matches the device.
* SN74LVC1G08 DBV mapping (A=1, B=2, GND=3, Y=4, VCC=5) is correct.

## Remaining producer interfaces

The source reset-good supervisor, source watchdog-good producer, interlock
permit producer, `SOURCE_REARM_PULSE`, HOT watchdog-good producer, validated
SESSION_ARM/START pulse source, HOT/SELV level translation, and any measured
LT4363 reset acknowledgement remain integration contracts. They must be
named in the schematic and bench fixture; they cannot be inferred from the
existing decoder firmware.
