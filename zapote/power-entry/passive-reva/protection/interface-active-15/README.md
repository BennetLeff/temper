# Active AUX and hardware reset candidate 15

This round turns the two outstanding interface concepts into pin/value
proposals and a bench qualification worksheet. **The compiled circuit remains
revision11,136components.** Candidate15 is not a compiled or qualified replacement.

- [AUX circuit](clamp/design.md): LT4363-1 with the reference FDB33N25 pass
  device,0.22Ω sense resistor,59.0kΩ/4.99kΩ feedback,100nF timer and explicit
  gate/output-capacitance requirements. Conditional static clamp range is
  **15.941–16.761V**. Startup and fault-stress calculations are reproducible.
- [Reset circuit](reset/design.md): source-side captured permission across an
  ISO7741F, an independent HOT watchdog input, and reuse of the existing spare
  HCS74 half for hardware authorization. Faults clear authorization and RUN;
  recovery requires separate fresh session and START edges.
- [Bench worksheet](bench-plan.md): actual waveforms, fixtures and acceptance
  conditions needed to qualify voltage peaks, startup, transistor SOA and
  reset timing. **No physical measurements were performed.**

## Verification and review

Four Rust checks cover clamp corners, rejection of the original low threshold,
total-resistor-error sensitivity, and startup versus foldback. An independent
TI manufacturer-model fixture passes ten functional assertions. Keeping D1
fixed high deliberately fails the same checker. The transistor's official SOA
page was visually inspected and retained; it supports a room-temperature
screen, not a hot-assembly qualification.

Both blocks were delegated to Luna in isolated temporary directories. The
parent substantially corrected the handbacks before accepting these documents:
wrong sense-resistor topology, excessive gate pulldown current, a clamp that
could trip in normal operation, mixed OV/OC timing, unqualified FET gate-voltage
margin, an interlock signal placed on the wrong side of the isolation barrier,
and conflation of isolator enable timing with fault propagation. Raw final
worker handbacks remain under worker-handbacks/ and are **superseded** by the
parent designs. They must not be used as build instructions.

The new circuit proposals still require exact capacitors and load budgets,
supervisor/watchdog/decoder selection and level translation, schematic capture,
and physical qualification. Their added components have not been counted as a
new compiled revision. The input manifest binds the unchanged source baseline;
receipt.json records the verification scope and remaining work.

Next executable engineering step is to capture these corrected prototypes as
isolated schematics and resolve the stated producer/load/component contracts.
Bench execution then supplies the physical evidence that software cannot.
Do not add this candidate to the full power-entry PCB on the basis of static
thresholds or passing logical tests.
