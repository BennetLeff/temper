# PT100 safety: independent digital and hardware paths

The release design must use both mechanisms. They cover different common-cause
failures and neither is allowed to silently substitute for the other. The
current schematic implements the MAX31865 analogue interface and its
host-tested firmware device contract, including the board-owned boot/DRDY
service. The independent comparator now has a selected, executable interface
topology below; its components, resistor values, and fault-OR expansion remain
release-gated until the corresponding corner deck and schematic are reviewed.

1. **MAX31865 digital path.** Configure the low/high fault registers on every
   boot, run the MAX31865 fault-detection cycle at startup and periodically,
   and treat the latched fault-status bits as a safety fault. The MAX31865
   documents open-element, short-element, cable, and out-of-range input
   detection; its status is read over SPI and must feed the firmware fault
   handler. [Analog Devices MAX31865 datasheet](https://www.analog.com/media/en/technical-documentation/data-sheets/MAX31865.pdf)
   The device exposes `DRDY`, not a dedicated asynchronous `FAULT` output, so
   this path is necessarily MCU/SPI-mediated.
2. **Independent hardware path.** Add a high-impedance dual window comparator
   at the local `REFIN−`/`ISENSOR` RTD-current-drop node, not across the
   remote sense pair. Its low threshold asserts `RTD_HW_FAULT` for a short;
   its high threshold asserts the same fault for an open or out-of-range lead.
   `RTD_HW_FAULT` goes into the active-high fault latch through an added
   aggregate OR stage; it must not depend on SPI, the MCU clock, or a firmware
   GPIO. The comparator supply-loss state must be fail-safe (a defined fault
   level at the OR input).

The comparator thresholds must be derived from the **measured MAX31865 bias
current**, not guessed. For an excitation current `I_BIAS`, the nominal window
is `V_SHORT = I_BIAS * 10 Ω` and `V_OPEN = I_BIAS * 300 Ω`. Include the
MAX31865 bias-current tolerance, TLV3201 input offset, divider tolerance,
connector resistance, and temperature drift in the corner sweep. Do not place
the comparator until that sweep has a non-overlapping pass/fail window.

## Selected fail-safe topology (schematic input)

`RTD_HW_FAULT` is active high and has a pull-up to the upstream `SAFETY_3V3`
rail. It is not pulled up from the post-ferrite sensor rail. The only permitted
way to hold it low is an open-drain NAND powered from `RTD_AVDD`, the
post-ferrite rail that powers the MAX31865 and the window comparators:

```text
SAFETY_3V3 -- ferrite --> RTD_AVDD --> MAX31865 + two window comparators
    |                         |
    |                         +-- LOW_OK  = V(REFIN-) > V_LOW
    |                         +-- HIGH_OK = V(REFIN-) < V_HIGH
    |                                      |
    +-- upstream rail monitor ------------ RTD_RAIL_OK
    |                                      |
    +-- pull-up --> RTD_HW_FAULT <-- open-drain NAND(WINDOW_OK, RTD_RAIL_OK)
                         |
                         +--> added FAULT_ANY OR --> SR latch --> UCC21550 DIS
```

The captured circuit uses `REF2025AIDDCR` (1.25 V `VBIAS`) with 0.1% dividers:
61.9 kΩ (`ERA-3AEB6192V`) / 10 kΩ gives the 173.9 mV low threshold and
5.9 kΩ (`ERA-3AEB5901V`) / 10 kΩ gives the 786.2 mV high threshold. (2026-07-27:
corrected from the originally-specified 61.3 kΩ/`ERA-3AEB6132V` and
5.93 kΩ/`ERA-3AEB5931V` -- neither value is an E96/E192 series member and
neither MPN exists at any distributor; see
docs/evidence/2026-07-27-era-resistor-resolution.md for the distributor
fetches and worst-case-margin arithmetic, including 25 ppm/°C tempco, that
this substitution still clears.) Two TLV3201s produce `LOW_OK` and `HIGH_OK`;
an `SN74LVC1G08` forms `WINDOW_OK`; an Ioff-rated `SN74LVC1G38` sinks
`RTD_HW_FAULT` only while all permissions are true. The upstream `TPS3700DDCR`
monitors `RTD_AVDD` through a 619 kΩ (`ERA-6AEB6193V`, 0805) / 100 kΩ 0.1%
divider. (2026-07-27: corrected from 616 kΩ/`ERA-3AEB6163V` -- not an
E96/E192 value, the MPN does not exist, and 616 kΩ is above the top of
Panasonic's ERA-3A/0603 series; ERA-6A/0805 is the real family at this
value.) Its complete UV-fault/clear threshold corner is 2.777--2.882 V, above
the TLV3201 2.70 V minimum supply and below the 3.3 V -10% normal-rail
corner of 2.97 V. The selected single-channel UV monitor has no asserted
hysteresis claim.
[REF2025](https://www.ti.com/lit/ds/symlink/ref2025.pdf)
[TPS3700](https://www.ti.com/lit/ds/symlink/tps3700.pdf)
[TLV3201](https://www.ti.com/lit/ds/symlink/tlv3201.pdf)
[SN74LVC1G38](https://www.ti.com/lit/ds/symlink/sn74lvc1g38.pdf)

`WINDOW_OK` also has a 100 kΩ pull-down. It is not relied on for a lost
`RTD_AVDD` rail—the upstream monitor already withdraws permission—but ensures
an unpowered or floating AND output is a deterministic non-permission input.

Sampling `REFIN−`/`ISENSOR` follows the MAX31865's local RREF/RTD series
network and is exactly the voltage used by the VBIAS/RREF corner model. It
avoids incorrectly treating the remote `RTDIN−` sense lead as board ground;
the digital MAX31865 path remains responsible for cable-specific faults that
are not visible at this local voltage node.

| Condition | `RTD_HW_FAULT` result |
|---|---|
| Both window checks valid and `RTD_AVDD` above monitored UV | low (clear) |
| RTD short or open/out-of-range | high (fault) |
| `RTD_AVDD` brownout or absent | high (fault) |
| Upstream safety 3.3 V absent | UCC21550 `DIS` floats to its safe disable state |

The existing `SN74HC4075` is fully allocated. Add a second documented OR stage
to form `FAULT_ANY = OR(existing fault bus, RTD_HW_FAULT)` and route *both* the
NAND-latch set input and reset-qualification input from that new aggregate.
Do not connect `RTD_HW_FAULT` to GPIO15/runaway-cut or tie a comparator output
directly to the saturated existing OR.

## In-box validation

The executable resistance model is
`code = floor(32768 * R_RTD / R_REF)` with the existing 430 Ω reference. The
property tests in
`packages/temper-placer/tests/validation/test_rtd_safety_pbt.py` prove that
the code is monotonic and that the short/open boundaries stay separated for a
±1% reference-resistor corner. They are a digital acceptance test, not a
substitute for analogue evidence.

The same module now contains an in-box window-comparator synthesizer. It takes
the measured-or-datasheet bias-current range, comparator offset, divider
tolerance, and required no-false-trip margin as explicit parameters; it derives
both trip voltages only when every short, valid-PT100, and open corner is
separated. Otherwise it raises an error—there is no default bias current and
no guessed comparator threshold. Its property tests also require supply loss
to assert `RTD_HW_FAULT`. This is the decision gate before committing a
comparator circuit or SPICE deck.
`test_rtd_window_comparator_pbt.py` exhaustively samples the declared current,
offset, divider, short/open, valid-PT100, and supply-loss corners.

`test_rtd_fault_latch_pbt.py` then carries the abstract `RTD_HW_FAULT` through
the fault OR and fault-qualified NAND latch over generated reset, MCU, and SPI
states. It proves that a comparator fault or its supply loss asserts shutdown,
dominates a simultaneous reset request, and remains latched until an explicit
reset after the fault clears. This is intentionally a behavioural contract:
the source-level connection is added only with the measured comparator circuit.

`test_rtd_safety_pbt.py` also executes the board-owned MAX31865 service model
over generated DRDY delays, fault-status bytes, bootstrap outcomes, SPI-read
outcomes, and re-arm outcomes. It proves the 10-tick (100 ms) silent-DRDY bound
and fail-closed digital fault mapping. This simulation exercises protocol and
state timing only; it cannot prove physical SPI edges, GPIO voltage levels, or
the hardware latch response, which remain the low-voltage bench captures below.

The same property suite combines that service model with the independent
`RTD_HW_FAULT`, active-high MCU GPIO15 request, and the fault-qualified
set-dominant NAND latch. Generated event sequences prove that a digital RTD
fault, comparator/supply-loss fault, or another hardware fault reaches and
holds shutdown despite simultaneous reset requests. It is the virtual-board
integration gate; the bench only checks its declared electrical assumptions.

The ESP32 SPI HAL additionally programs two CS setup cycles and one hold cycle.
At the MAX31865's 5 MHz maximum, that is 400 ns setup and 200 ns hold, meeting
the device's 400 ns/100 ns limits; the implemented 500 kHz bus is slower still.
The property test checks the production source configuration and this worst-rate
timing arithmetic. Signal rise/fall and trace reflections remain model inputs
until routed geometry and ESP32 output-impedance data are captured.

The in-box RC envelope additionally sweeps the populated 33 ohm +/-5% SPI
series resistors, the MAX31865's 6 pF logic input, and its 50 pF timing-test
load. Even with an explicit 1 kohm driver-output bound, the lumped 10--90%
edge is below the 200 ns device limit. That proof deliberately excludes trace
reflections and conducted/radiated noise; those are assumptions to extract
from the routed board, then substitute into the model before bench correlation.

The MAX31865 analogue front end is also modeled as its actual VBIAS-driven
series network, not as a guessed constant-current source: VBIAS is swept from
1.95 V to 2.06 V and the populated 430 ohm reference is swept at +/-0.1% with
the PT100 valid range. This produces the RTD sense-voltage/current envelope
that a future comparator design must use. Comparator offset, supply-loss, and
threshold-network corners remain explicit inputs until a real comparator part
and circuit are selected.

Using the TLV3201's 4 mV full-temperature offset corner and 1% threshold
divider corners, the MAX31865 divider model retains the required 20% input
margin for 0--10 ohm short, 100--194.1 ohm valid PT100, and 300 ohm-and-up
open conditions. This is a threshold-feasibility result only: TLV3201 has a
push-pull output, so it is used only to produce local `LOW_OK`/`HIGH_OK`
permissions. The selected default-high/open-drain topology supplies the
separately proved supply-loss-to-fault mechanism; it still needs its physical
corner deck and schematic before it can satisfy the independent-path release
requirement.

Before PCB release, run an ngspice corner deck for the proposed comparator:

| Case | RTD resistance | Required result |
|---|---:|---|
| hard short | 0–10 Ω | `RTD_HW_FAULT=1` |
| valid cold/hot | 100–194.1 Ω (PT100, 0–250 °C) | `RTD_HW_FAULT=0` |
| guard band | 194.1–300 Ω | no false trip; firmware may derate |
| open / cable fault | ≥300 Ω, open, or lead-to-rail | `RTD_HW_FAULT=1` |

Sweep at minimum `I_BIAS`, `I_BIAS` nominal, and `I_BIAS` maximum over the
component temperature range. The result must show at least 20% voltage margin
between the worst valid case and the nearest fault threshold, and the OR/latch
must assert within the system's 100 ms fault-response budget. The selected
architecture is simulated before schematic capture: generated property tests
sweep window permissions, every declared UV-trip corner, complete post-rail
power loss, and upstream safety-rail loss. The CI-run abstract ngspice deck
`elec/validation/rtd_hw_fault_default_high.cir` additionally proves the
selected pull-up/open-drain connectivity at representative valid, short, open,
brownout, and complete-`RTD_AVDD`-loss points. It uses behavioural sources, not
vendor macro-models. `elec/validation/rtd_window_selected_values.cir` also
models the captured MAX31865 RREF, REF2025 divider values, and TPS3700 monitor
divider at nominal values. TI publishes models for the selected REF2025,
TLV3201, TPS3700, and SN74LVC1G38, but the released files are PSpice/TINA
syntax: the temporary ngspice compatibility smoke test rejects their PSpice
`IF()` syntax and warns on switch-model differences. The repository therefore
contains independently written, reviewable portable models in
`simulation/models/*_ngspice.lib`, with the original TI release identifier,
pin order, and modeled scope recorded in each header. The CI-run
`elec/validation/rtd_window_ported_models.cir` uses those ports for the full
selected RTD topology.

The portable ports deliberately cover the safety-relevant supply floor,
threshold decision, and open-drain/Ioff behaviour; they do not claim the
vendor models' temperature, noise, startup-statistical, or edge-timing
fidelity. The property suite retains the tolerance/PVT proof and low-voltage
bench captures remain required before PCB release. Do not vendor or
mechanically translate TI source files without recording TI's
license/provenance and reviewing every semantic conversion.

## Firmware alignment

The firmware now consumes generated `RTD_SHORT_FAULT_OHM` (10 Ω inclusive) and
`RTD_OPEN_FAULT_OHM` (300 Ω inclusive) for both fault detection and reset
clearance. `RTD_GROSS_OPEN_DIAGNOSTIC_OHM` (10 kΩ) remains as an explicit,
secondary diagnostic branch so existing 15 kΩ SIL traces retain their intended
coverage during migration; it does not weaken the 300 Ω safety boundary.

### MAX31865 threshold-register encoding

The MAX31865 RTD and fault-threshold registers carry the 15-bit resistance ADC
code in bits 15:1; bit 0 is not part of the code. With the populated 430 ohm
RREF, the 10 ohm short threshold is ADC code 763 and must be written as the
16-bit low-threshold word `0x05F6` (1526). The 300 ohm open threshold is ADC
code 22861 and must be written as `0xB29A` (45722). Firmware must not write
the unshifted ADC values directly to the fault registers: doing so silently
halves the physical resistance threshold.

### Firmware device contract

`firmware/components/sensors/max31865.c` writes those two words and starts
MAX31865 automatic fault detection with `VBIAS=1` and `D[3:2]=01`.
`firmware/components/sensors/rtd_service.c` is the board-owned integration:
it initializes SPI2 on GPIO8/11/12 with CS10, configures active-low DRDY on
GPIO9, and is bootstrapped after the production HAL. Its DRDY ISR only sets a
completion flag; `rtd_service_control_tick()` runs from the control-loop task,
performs the SPI read, and is the sole owner of the resulting state-machine
mutation. The service never claims synchronous conversion completion.

If bootstrap fails, it records the failure and the first control-loop tick
uses the same terminal probe-open/hardware-cut path before the power stage can
run. This keeps bootstrap, SPI, and state ownership explicit without doing
SPI or state work in interrupt context. A cycle that produces no DRDY handoff
within ten 10 ms control ticks (100 ms) is also terminal probe-open: a silent
MAX31865, cable, or DRDY path cannot leave the RTD interlock unmonitored.

That service reads the latched status at `07h`, delivers a decoded callback,
and then arms the next cycle. It can be wired directly to
`state_machine_report_rtd_device_fault`: high-threshold, cable/reference, and
supply faults become `FAULT_PROBE_OPEN`; the low threshold becomes
`FAULT_PROBE_SHORT`. Both enter the existing terminal hardware-cut path. A
SPI read failure, or a failure to arm a clean next cycle, is reported as
open/out-of-range, and the driver never writes the MAX31865 status-clear bit,
so a digital-path error cannot silently clear a latched safety fault.

### Transient RTD-to-DIS safety envelope

`elec/validation/rtd_fault_latch_transient.cir.in` and
`test_rtd_fault_latch_transient_spice.py` model the complete independent
hardware response as a transient path:

`RTD short/open or RTD_AVDD brownout → RTD_HW_FAULT → FAULT_ANY →
set-dominant latch → SHUTDOWN → UCC21550 DIS`.

The test renders and runs five ngspice stimuli: RTD short and open steps, fast
and 10 ms RTD_AVDD brownout ramps, and a short pulse with reset asserted while
the fault remains live. It requires the active-high DIS/shutdown node to cross
its 1.65 V logic threshold in under 100 ms and remain high after the input
fault clears. The reset-pulse case proves the behavioural latch is
set-dominant, not merely a combinational shutdown path.

The deck uses a deliberately conservative, reviewable timing envelope rather
than unavailable vendor transistor macro-models: 55 ns for the
[TLV3201](https://www.ti.com/lit/ds/symlink/tlv3201.pdf) propagation delay,
23 ns for the [SN74HC00](https://www.ti.com/lit/ds/symlink/sn74hc00.pdf), and
1 us for latch charging. The
[TPS3700](https://www.ti.com/lit/ds/symlink/tps3700.pdf) contributes a **450
µs conservative model parameter**. That value is not claimed as a TPS3700
datasheet maximum; it covers the cited slow-start behaviour until an
applicable brownout propagation-time corner is characterized. The deck's RC
threshold crossings are no earlier than those declared delays.

This is an in-box connectivity/timing bound only. It does not replace the
future measured comparator-current sweep, vendor macro-model/PVT analysis, or
scope capture at the physical `RTD_HW_FAULT`, `SHUTDOWN`, and UCC21550 `DIS`
nodes.

### Four-wire analogue connection

The implemented MAX31865 front end follows the 4-wire connection in the
datasheet: `BIAS` is tied to `REFIN+`; the 430 ohm RREF is between `REFIN+`
and `REFIN−`; `ISENSOR` is tied to `REFIN−`; and `FORCE2` is tied to ground.
`FORCE+`/`RTDIN+` and `FORCE−`/`RTDIN−` stay as separate conductors to the
RTD connector. Source and generated-netlist contract tests assert this exact
topology so that an unconnected reference or current-sense pin fails review.

When the comparator path is added, both paths must assert the same latched
`FAULT_PROBE_OPEN`/`FAULT_PROBE_SHORT` response. A cleared SPI value must not
clear the hardware latch; only the explicit safety reset sequence may release
`SHUTDOWN`.
