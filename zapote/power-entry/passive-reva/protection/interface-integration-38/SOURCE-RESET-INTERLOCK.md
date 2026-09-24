# Cooker-side reset and interlock producer candidate

Status: **compiled connectivity PASS; firmware and electrical qualification
OPEN**. The source is `cooker-mate/elec/src/cooker_mate.ato`, imported with
the unchanged cooker `Top`. It uses the selected existing ESP and SELV rail.
The Rev38-side header pull-downs remain the low state for missing cable,
unpowered cooker, or undriven output. There is no native cooker board or
physical capture yet.

## Why the original cooker latch needs a reset contract

`SafetyInterlock` drives an active-high `SHUTDOWN` from NAND-latch Y2. Its
reset qualification is `R_N = FAULT_ANY OR GPIO14`, and fault set dominates
simultaneous reset. GPIO14 is named `PIN_RESET_INPUT` in the firmware pin
header but has no production driver in the inspected firmware. GPIO15's
active-high runaway cut is configured by safety startup, but has no external
default in the canonical cooker circuit. For `FAULT_ANY = 0`, holding GPIO14
low clears the latch continuously, so a transient fault is forgotten as soon
as it ends. Holding GPIO14 high retains faults but gives no deterministic
power-on reset. Direct inversion of `SHUTDOWN` would therefore be an
unqualified high-to-allow interlock.

The candidate adds a cooker-side TPS389001 supervisor with a 16 kΩ/10 kΩ
SELV3V3 sense divider, EN connected to its active-low MR input, 100 nF CT,
and 10 kΩ open-drain RESET pull-up. RESET joins ESP GPIO14 and the latch
reset request. A 10 kΩ GPIO15 pull-down defines the inactive runaway-cut
input before firmware owns it. The supervisor holds the latch reset request
low while its rail/EN condition is false and through its release delay; it
then releases the node high to retain future faults. GPIO14 must be **input
or open-drain only**. A push-pull high can contend with the supervisor, and a
push-pull low held during operation defeats fault retention. No production
GPIO14 ownership implementation or target pin-mode receipt exists yet.

The nominal divider falling threshold is about 2.99 V. Using the
[TPS3890's](https://www.ti.com/lit/ds/symlink/tps3890.pdf) 1.15 V nominal
threshold and ±1% threshold accuracy with ±1% independent resistor corners
gives approximately 2.924–3.057 V at the monitored rail, before input
leakage, hysteresis, temperature and installed-part effects. This is a
component screen, not a qualified undervoltage limit or release delay. The
separate Rev38 source rail supervisor remains in the authorization path.

`SOURCE_RESET_GOOD` is the push-pull Schmitt-buffered supervisor RESET node;
it reports **physical EN and rail release after CT delay**, not internal ESP
CPU execution. The `SOURCE_INTERLOCK_N` push-pull path is:

    RESET_GOOD AND GPIO14_RESET_REQUEST_HIGH AND NOT SHUTDOWN

This uses a [SN74LVC1G17](https://www.ti.com/lit/ds/symlink/sn74lvc1g17.pdf),
[SN74LVC1G04](https://www.ti.com/lit/ds/symlink/sn74lvc1g04.pdf), and two
[SN74LVC1G08](https://www.ti.com/lit/ds/symlink/sn74lvc1g08.pdf) gates. A
stuck-low GPIO14, physical EN reset, rail loss, or asserted cooker fault
must hold the Rev38 interlock low. CPU-only reset can leave EN high; the
separate TPS3431 watchdog, fail-low STOP ownership and bounded-reset
contract cover that case. No supervisor or CMOS gate is credited with
detecting internal CPU reset.

| Condition | Reset request | SHUTDOWN | RESET_GOOD | INTERLOCK_N candidate |
| --- | --- | --- | --- | --- |
| Power absent or EN held low | Low by supervisor | Unknown | Low | Low via local Rev38 bias; verify during ramps |
| Released healthy source | High | Low | High | High |
| Latched cooker fault | High | High | High | Low |
| Deliberate GPIO14 reset pulse | Low | Low if fault absent | Low at reset-request buffer | Low |
| GPIO14 stuck low after a transient fault | Low | May clear | Low at reset-request buffer | Low |
| CPU-only reset with EN retained high | May retain high | May retain | May retain high | May retain high until watchdog/STOP clear |

The RESET_GOOD row for a GPIO14 low pulse is a consequence of the shared
open-drain node: its buffer reads low even when the supervisor itself is
released. Digital connectivity alone cannot establish analog logic levels
during rail ramps or fault pulses. The SN74LVC output state below its minimum
operating VCC, supervisor minimum-output behavior, EN bounce, CT tolerance,
GPIO14 reset mode, and fault-latch power-on behavior require measurements.

## Gates before crediting these producers

1. Implement one firmware owner for GPIO14, configure it only as open drain,
   and issue a deliberate low reset pulse only after the source and HOT sides
   acknowledge physical disarm. Verify no other cooker or diagnostic task
   changes its mode or level. A fault during the pulse must keep SHUTDOWN
   high, and a subsequent transient fault must remain latched until another
   controlled reset.
2. Confirm the existing GPIO15 runaway-cut task drives high for fault and
   does not pulse low before a latched fault is captured. Capture its startup
   state at the physical pin.
3. Measure SELV3V3, ESP EN, supervisor SENSE/CT/RESET, GPIO14, SHUTDOWN,
   header pins 14/15, Rev38 local health, HOT clear, EN and loaded gate on
   cold/warm/partial power ramps, EN-button reset, watchdog trip, CPU-only
   reset and cable open/short cases. Include narrow fault pulses and a fault
   coincident with reset release.
4. Verify supervisor and gate package footprints, pin 1 orientation,
   decoupling, output high/low thresholds against the 10 kΩ Rev38 biases,
   rail loading and harness faults on the native cooker and Rev38 boards.
   The compiled pin audit only proves named connectivity and part MPNs.

Until those gates and the joined native design pass, pins 14/15 remain
**candidate producers**, not accepted safety evidence. No START/WDI task
may be enabled by this source-only build.
