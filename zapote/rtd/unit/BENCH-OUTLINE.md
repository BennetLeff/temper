# Standalone RTD unit bench outline

Status: procedure prepared; all physical checks **NOT RUN**. This outline does
not authorize a purchase or claim assembly, electrical, thermal, or EMC results.
It applies to the standalone low-voltage RTD board described in `HANDOFF.md`.

## Bind the session before powering the board

Record the assembled board revision, final accepted source/board manifest and
full hashes, BOM revision, probe/harness identity, host firmware revision, and
the exact circuit/interface contract used for acceptance. Source04 is a reviewed
checkpoint, not a replacement for the final acceptance manifest. Record every
assembly substitution and test-fixture modification; reassess affected checks.

Use the final assembly drawing to identify connector pin 1. J2 is an unshrouded
header and does not prevent reversed mating. Verify cable continuity with power
off; colors and the apparent left/right order in a photograph are insufficient.

| Connection | Board pin roles |
|---|---|
| J1, four-wire probe | 1 FORCE+, 2 SENSE+, 3 SENSE−, 4 FORCE− |
| J2, host boundary | 1 +3V3 input; 2 and 3 common ground; 4 SCK; 5 SDI; 6 SDO; 7 CS_N; 8 DRDY; 9 active-high HW_FAULT; 10 shared 2.5 V reference output |

Connect the supply and host grounds to the intended common return. Do not drive
the reference output. Connect oscilloscope ground clips only to verified ground
points, with clips/probes attached while power is off. Observe the final power
sequencing and input-drive limits; do not apply host signals to an unpowered unit
unless that state is explicitly permitted by the accepted interface contract.

## Equipment and fixture capabilities

Use a regulated, current-limited low-voltage supply, DMM, oscilloscope or logic
analyzer with adequate timing resolution, and a host running the accepted RTD
driver. Set voltage and current limits from the final upstream supply contract;
the local filtered-rail allocation is not automatically the whole-unit current
limit. Record the instrument settings before the first powered run.

Use a characterized four-terminal resistance standard or simulator for initial
electrical checks. Add independently switchable FORCE+, SENSE+, SENSE−, FORCE−
conductors with a timing marker, and a defined sensor-short condition. Record
fixture resistance, leakage, parasitic capacitance and switch bounce. They must
fit the accepted harness/model envelope for a comparison with modeled timing.

For local rail-loss testing, the fixture must interrupt/control RTD_AVDD while
preserving upstream +3V3, the supervisor, fault NAND and pullup supply. The board
has no claimed built-in rail-disconnect switch. Document an approved fixture or
assembly rework and verify the resulting nets before using it. Shorting the
filtered rail to ground or lowering the common supply does not establish this
isolated fault condition.

## Staged operator sequence

| Stage | Stimulus and records | Acceptance authority |
|---|---|---|
| Inspection | Inspect polarity, connector orientation, exact parts, solder joints and shorts. Check supply-to-ground resistance and probe conductor continuity with power off. | Final schematic, BOM and assembly drawing; unexplained discrepancy stops the run. |
| Initial power | Apply nominal upstream supply with a valid resistance connected. Record input current, +3V3, RTD_AVDD, reference output, supervisor RESET and HW_FAULT through startup. | Final voltage/current/settling and startup contract. |
| Driver operation | Run the accepted BIAS-start, diagnostic-cycle and continuous-conversion sequence. Capture SPI, DRDY, raw RTD/fault registers, converted resistance and sample-readiness state. | Accepted driver/configuration and protocol tests; readiness requires a fresh valid sample. |
| Electrical accuracy | Exercise the declared resistance range, including the resistance corresponding to 100 °C. Record reference-standard uncertainty, raw codes, supply voltage and ambient temperature. | Circuit error allocation. This does not measure probe-to-pan temperature accuracy. |
| Individual lead opens | Establish a valid sample, then open exactly one conductor. Repeat separately for all four conductors; restore and re-establish valid operation between cases. Capture the switch marker, HW_FAULT, DRDY, raw readings and host readiness/fault logs. | Required detector and worst-case timing for each named case in the final fault contract. |
| Short and threshold boundaries | Apply the defined sensor-short condition and resistance points around the accepted inclusive fault thresholds. Record both raw-code and fault-output behavior. | Final ADC threshold encoding and analog-window contract; do not assume both paths have identical trip points. |
| Local rail loss/brownout | Keep upstream power valid while the qualified fixture removes or ramps RTD_AVDD. Record both rails, supervisor RESET and HW_FAULT, including recovery. | Final supervisor/NAND power-loss and restart contract. An unpowered comparator reading alone is not detection evidence. |
| Upstream loss/restart | Remove upstream power and restore it under the specified sequence. Record loss of valid samples and the host's inhibit/readiness response. | Unit interface obligations; a disappearing pullup cannot guarantee a powered-high fault output. Full cooker shutdown is a later integration test. |
| Physical temperature | With a characterized probe, mounting and thermal reference, measure the specified steady-state temperature accuracy and stability. Record settling, probe contact and ambient conditions. | Product thermal test requirements and uncertainty budget; resistor substitution cannot complete this stage. |

Repeat required cases at the supply, temperature and harness conditions named
in the final contract. Record the repetition count and every failure; do not
discard an inconvenient trial. EMC and noise qualification need the specified
disturbance setup and remain separate from this basic functional sequence.

## Results, stops and capability gaps

For every run retain stimulus identity, instrument settings, raw captures,
measured values, uncertainty, applicable limit, verdict and operator notes. A
timing comparison includes fixture-marker/bounce and instrument uncertainty.
Use PASS only when the measurement supports the applicable bound; otherwise
use FAIL or INDETERMINATE. An unavailable fixture, instrument or qualified
procedure leaves its test NOT RUN with the missing capability named.

Stop and remove power for unexpected current limiting, an out-of-contract rail,
unexpected heating, a wiring discrepancy, or a failed fault/readiness response.
Preserve the capture before changing the setup. Record the cause, correction
and affected retest scope; restoring a valid resistance does not itself clear
an unexplained failure. No completed test is asserted by this document.
