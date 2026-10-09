# Prototype control and measurement boundary

## FPGA is optional bench research

The user's design decision on 2026-10-05 is authoritative: the FPGA capture
experiment is not a required part of the induction cooker's control,
protection, start-up, enclosure, or production BOM. Its absence must not
prevent a correctly qualified cooker from operating. No mirror-feedback
decoder or safety permission may acquire a dependency on that experiment.

The experiment remains preserved in `../fast-capture/` as optional bench
research. Its RTL and protocol tests do not prove physical gate waveforms.
Its last routed timing result failed the 80 MHz target. Do not present it as
a completed instrument or continue optimizing it without a demonstrated
measurement need that an oscilloscope or suitable timer capture cannot meet.

The product retains its ESP32/STM32 controllers and independent hardware
protection. On-chip PWM configuration/readback is evidence of what the
peripheral is configured to generate; it is not an independent measurement
of MOSFET gate voltage, switching overlap, or zero-voltage switching.
Never substitute command-derived numbers for physical measurements while
labeling them as captured feedback.

## First-prototype timing evidence

Use oscilloscope measurements for commissioning the first assembled unit.
The record must identify the exact power board, controller hardware,
firmware, gate resistors/drivers, supply/load condition, probe setup and
instrument uncertainty. A nonzero record identifier alone does not prove
qualification; it must refer to reviewed measurements of that configuration.

Measure gate-to-source voltage at each device with appropriately rated
differential or isolated probes. Include the two devices of each bridge leg
simultaneously, with matched channels or measured channel/probe skew. Do not
connect earth-referenced probe grounds to a switching source. Evaluate
cross-leg phase with a common timing reference rather than unrelated captures.

Record four-channel inhibit behavior, deadtime and phase at relevant operating
corners, startup/stop, rejected commands, communication loss and hardware
fault shutdown. Measure physical voltage/current transitions where claims
about overlap, switching stress or ZVS depend on them. Derive instrument
bandwidth, sample rate and uncertainty requirements from the smallest margin
being accepted; a nominal PWM setting is not the measured margin.

Suitable microcontroller timer capture may supplement these tests after its
resolution, clock domains, input conditioning and event-loss behavior are
established. Neither a timer-capture experiment nor an FPGA is selected as a
mandatory product dependency here.

No assembled unit is available yet. These are acceptance requirements, not
completed measurements or permission to energize the present design.

## Mirror contacts and precharge isolation

Receiver challenges run with the source isolated. After a successful
challenge, excitation is held continuously active during mechanical contactor
self-tests and the source-present interval. This permits direct hardware
use of the two precharge-isolation NC mirror signals without a scanned-state
decoder or an FPGA. Coil commands, excitation state, rail qualification and
the existing hardware permission chain also constrain the run gate.

An open NC mirror does not prove that its NO power contact conducts. The
loaded bypass proof remains a distinct test. Held RESET, stale feedback,
unqualified timer rearming and restarting the overall source-present timer
are not acceptable shortcuts around this sequence.
