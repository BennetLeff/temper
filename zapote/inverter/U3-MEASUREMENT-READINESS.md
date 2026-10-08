# Inverter U3 measurement readiness

**Verdict on 2026-09-23: INDETERMINATE.** The [saved gate output](evidence/measurement-output.tsv) has zero physical capture records across the closed 20-row [scenario registry](evidence/measurement-scenarios.tsv). The [manifest](evidence/measurement-manifest.tsv) deliberately uses `NONE` and `UNKNOWN` for every absent observation. This is a ready-to-fill capture inventory, not a selected half bridge, switch, capacitor, coil, frequency, native inverter source, or hardware stop qualification.

The Rev38 PFC source and accepted standalone gate-drive source are fixed to the bytes in [measurement-sources.sha256](evidence/measurement-sources.sha256). The prior [coupled transient screen](U2-TRANSIENT.md) and its case file are also locked. `source_check` requires all four named roles and matching SHA-256; a missing row cannot silently disappear. This is a read-byte boundary. The active Rev38 checkout can change, so the inventory must be replayed against a reviewed frozen revision before selecting hardware. The U1 snapshot references `docs/hardware/TANK_COIL_SPECIFICATION.md`, a path absent in this checkout; its old chart-derived coil claims are not upgraded to a source-locked acceptance claim here.

## Run and interpret

From the repository root:

```sh
rustc --edition=2021 -O zapote/inverter/evidence/measurement_gate.rs -o /tmp/zapote-inverter-measurement-gate
/tmp/zapote-inverter-measurement-gate > /tmp/zapote-inverter-measurement-output.tsv
# Exit 2 is the expected incomplete/review-pending state; exit 1 means rejected input or source drift.
cmp /tmp/zapote-inverter-measurement-output.tsv zapote/inverter/evidence/measurement-output.tsv
rustc --edition=2021 --test zapote/inverter/evidence/measurement_gate.rs -o /tmp/zapote-inverter-measurement-tests
/tmp/zapote-inverter-measurement-tests
rustfmt --check zapote/inverter/evidence/measurement_gate.rs
```

The output is deterministic by registry order. `INDETERMINATE` means absent or synthetic evidence. `REJECTED` means malformed or invalid input, source drift, wrong topology, or an unsafe shortcut. `CAPTURE_RECORDED` means a typed record, bounded raw file path and matching digest are present. Even if all 20 become `CAPTURE_RECORDED`, the overall verdict is only `REVIEW_PENDING` and the program exits 2: this checker cannot establish whether an instrument, calibration, fixture, load envelope or reviewer is genuine or adequate. It never emits a hardware PASS. A digest establishes byte identity only.

## Manifest contract

Each scenario row has exactly one manifest row. `kind` is a closed Rust enum. `origin` is `NONE`, `SYNTHETIC` or `MEASURED`; `SYNTHETIC` exists only for checker controls. Every measured row names the physical article/fixture, raw capture under `zapote/inverter/evidence/raw/`, its full SHA-256 and independent reviewer identity. `return_net` is `HOT0`; historical `PWR_RTN` is invalid for Rev38. The semicolon-separated `values` field uses named units in keys and disallows unrecognized keys. Current file rows remain `UNKNOWN` until there is actual evidence.

| Kind | Typed summary required before a record can be counted | Raw evidence and applicability to review |
| --- | --- | --- |
| `coil` | Frequency, current and temperature ranges; loaded complex impedance `Z_re + j Z_im` bounds and uncertainty; gap, offset and sample count; coil/pan identities. Frequency and current must span more than one point. | Complex impedance samples with instrument frequency, phase, current, winding/ferrite/pan temperatures, geometry and uncertainty. A free-air inductance or one 47 kHz reading cannot fill it. The reference cold/hot pan identity must agree; a weak pan must be distinct. |
| `bus` | VD/VB minima and maxima, ripple, voltage uncertainty, source current/power limits and slew. Zero-voltage startup is allowed. The F2-open row also requires independent contact-open and F2-current evidence. | Simultaneous VD/VB and source-current waveforms across startup, loaded ripple/step, surge and F2-open states. The 390 V nominal intent and 450 V can rating are not maximum observed bounds. Equal charged VD/VB alone does not prove F2 continuity. |
| `stop` | Loaded starting current, command, gate-off and separately observed current-zero times, current-zero threshold and time uncertainty. | Synchronized PWM, PERMIT, both gate-to-Kelvin voltages, switch/tank current, bus and both rail voltages. Gate-off cannot substitute for current-zero. |
| `fault` | F2-open VD/VB current/voltage/energy and clearing path; direct-bank loop current, energy, R/L and bank-side clearing identity. | Independently bounded loop model and staged protected capture. F2, PFC RUN and PERMIT cannot clear a short between VB cans and bridge. A declared energy number alone does not prove containment. |
| `part` | Exact manufacturer part number; voltage/current/temperature ratings at their applicable conditions; observed waveforms; local capacitance for `part_local_cap`. | Datasheet revision and measured waveform range, including derating, pulse/RMS distinction, sharing and thermal mounting. A rating comparison without frequency, duty, temperature and overshoot applicability remains under review. |

The current checker validates summary shape and raw byte identity; it does not parse the raw waveform or independently certify the measurement. Review must compare summaries to raw traces and manufacturer limits before any operating range, thermal budget or fault claim is accepted.

## Capture protocol and stop boundaries

1. **Freeze the article and sources.** Record coil build/revision, ferrite, bracket, gap, terminals, pan material/base/ID, bus and gate source hashes, fixture topology, instrument model/serial, calibration date, probe factor, bandwidth, sampling rate, channel deskew and uncertainty. Use a new immutable raw file per run, including failed and aborted runs; retain the correction and retest link. Do not copy an old midpoint capture into a HOT0 row.
2. **Measure impedance before power conversion.** Capture no-pan, reference cold/hot, weak pan, offset and lift. Sample frequency, current and temperature coverage, not a single favorable operating point. Record complex impedance and uncertainty for each point. Pan removal is a separate transient under protected, limited energy; the static pre/post points cannot establish removal trip time.
3. **Bound the source before enabling the inverter.** Record simultaneous VD/VB startup, ripple, load-step, surge and F2-open behavior with source current and power limits. Separate observed extrema from applied uncertainty and define the time span/line/load conditions. Rev38 must publish a reviewed bus-ready meaning and source impedance. The 390 V target is not a voltage ceiling.
4. **Stage loaded stop captures under separately approved limited-energy conditions.** Record PERMIT loss, PWM loss, isolated 15 V loss and 3V3 loss with synchronized command, gate, current and rails. Stop the session on unexpected gate overlap, overvoltage/current, missing instrument channel, protection failure or re-arm without a new safe state. Carry both gate-off and measured current-zero delays into the cross-unit fault contract.
5. **Treat fault loops separately.** F2 opening isolates VD from VB; it does not interrupt VB-can discharge into a failed bridge. Use bounded analysis and a protected staged fixture for the direct-bank loop before any higher-energy fault attempt. Record loop R/L, energy, current, peak voltage, physical clearing element and post-fault state. Gate inhibit alone is not failed-short containment. Do not perform a live full-bank short as a checker test.
6. **Only after bounded waveforms, compare exact parts.** Select a candidate switch, VB-local commutation capacitor and series tank capacitor against manufacturer limits at actual frequency, duty, temperature, waveform shape, sharing, mounting and fault condition. Publish inverter-side capacitance and heat locations to discharge and cooling. Refit the ideal screen to independent loaded captures, then perform native schematic/PCB construction and cross-unit verification on the accepted revision.

The prior P3 model remains useful for rejecting declared example stresses. Its hypothetical 0.47 µF VB-local capacitor, 47 kHz point and 20 µs stop delay are not measurements. No physical capture, part selection, downstream interruption or assembled cooker safety result is asserted by this milestone.
