# Plan 3 — prepare the buck prototype bring-up procedure

Created: 2026-09-10

## Assignment and completion

Write a short, board-specific procedure an operator can use to power the standalone buck safely, establish 0.5 A operation, and measure startup, 1 A pulses, ripple and temperature. Supply detailed measurement definitions and empty records behind the short procedure so results can be interpreted without another research session.

The immediate deliverable is bench-ready documentation. Physical assembly and measurements occur later with an operator and actual equipment. Do not invent measurements or mark a test passed because its procedure is complete.

Read the [handoff index](2026-09-10-1105-buck-prototype-handoff-plan.md). Work in `/Users/bennet/Desktop/temper/.worktrees/codex/buck-harness-experiment-plan`, branch `codex/buck-harness-experiment-plan`, preserving WIP. You own `docs/hardware/buck-reva/` only. Other agents own the standalone CAD, procurement and release package.

## Inputs and precedence

- Adopted limits: `harness-lab/engineering/requirements.json`.
- Measurement definitions: `harness-lab/audits/buck-20260910-followup/requirements-proposal.md`.
- Updated startup stimulus: `harness-lab/engineering/scenarios/lmr51430-datasheet/` and `harness-lab/audits/buck-final-20260910/full-scenario-readiness/README.md`. The current requirements/scenario definitions override older prose on startup load compliance.
- Known limitations: `harness-lab/audits/buck-final-20260910/components/qualification-ledger.md`, `margin-resolution/README.md`, and `transient-resolution/README.md`.
- Board-specific authority, when available: `pcb/prototypes/buck-reva/source-manifest.json`, `verification/board-freeze.md`, and final assembly drawing.

General Temper safety/assembly checklists cover a larger system. Do not import their 24 V input, 5 V checks, MCU boot, UART/SPI/I²C, mains or inverter steps into this standalone board. This prototype contains only the 15 V-to-3.3 V buck and bench interfaces.

## Deliverables and preparation order

Create:

- `docs/hardware/buck-reva/BRINGUP.md`: concise operator sequence, preferably two or three printable pages plus figures.
- `measurement-definitions.md`: exact stimulus, capture and calculation definitions below.
- `equipment.md`: required capabilities, wiring/probing setup, and which checks become unavailable when capability is missing.
- `results-template.csv`: empty per-operating-point table with explicit status and evidence fields.
- `run-record-template.md`: revision, assembly inspection, instrument settings, event log, failures and conclusion.
- `images/`: annotated final connector/probe map and bench wiring diagram.
- `README.md`: index, documentation readiness, actual test status and deferred qualification items.

Draft procedures and templates immediately. Finalize pinout illustrations only after the board owner freezes the board. Label draft figures as provisional; do not ship a placeholder as the final connection guide. Refer to the matching release manifest/hash, not just “Rev A” if several revisions exist.

## Step 1 — specify equipment and connection boundaries

Use an isolated, adjustable, current-limited DC supply covering 13.5–16.5 V; a DMM; an electronic load capable of 3.3 V operation and controlled pulses; an oscilloscope with suitable probes; and a thermocouple or adequately characterized temperature measurement setup. Resistors can cover staged DC loads but cannot reproduce the specified constant-current startup/pulse protocol.

The operating connection is J1.1 VIN/J1.2 GND and J2.1 3V3/J2.2 GND. Measure board VIN at TP1/TP2 and VOUT at TP3/TP4; record any optional SW access from the final board. Verify the actual silk and pin numbering against the drawing before energizing.

Use short ground springs or equivalent low-inductance connections for ripple. Ground-referenced scope clips connect only to verified circuit GND; assess supply/load/scope earth connections before probing. A differential probe or otherwise appropriate setup is required where a ground-referenced connection would short a node. SW probing is optional diagnostic work, not a mandatory first-power connection.

For formal ripple comparison, specify a 20 MHz bandwidth limit, at least 100 MS/s and enough memory to retain a 100 ms steady capture. For transient tests, verify **measured load current** achieves the commanded slew and plateau; a load front-panel setting alone is not evidence. Avoid adding a permanent shunt or long wiring in the buck switching path just to measure current.

## Step 2 — write the staged first-power sequence

1. With supply disconnected, inspect populated MPNs, U3 orientation, solder bridges, inductor seating, connector polarity and testpoints against the assembly drawing. Check ground continuity and input/output-to-ground resistance. Capacitors can make resistance change with time; a continuity beep alone is not a definitive short test. Discharge rails before reconnecting.
2. Place the board on a stable insulating support. Attach the load disabled and scope probes with power off. Set the supply to 15 V and an initial 0.10 A input current limit, then energize with no output load. This is a conservative diagnostic setting, not an IC current specification or a formal startup-ramp test.
3. Confirm VOUT settles within 3.135–3.465 V, the supply is in voltage regulation and no abnormal heating occurs. If the supply current-limits, disconnect and investigate wiring, shorts and startup charging before changing limits. Do not keep increasing the limit until a suspect board appears to work.
4. After the no-load check passes, use a recorded input limit initially 0.30 A for staged 0.05, 0.10, 0.25 and 0.50 A output loads at 15 V. Record actual VIN at the board, VOUT, IIN and IOUT at each step. Repeat stable checks at 13.5 and 16.5 V. A supply running in current limit makes a converter-performance result invalid until the cause is resolved.
5. Measure ripple and observe temperature during stable 0.5 A operation. Only after that stage passes, prepare the 1 A/10 ms pulse test; an initial 0.50 A input current limit is a practical test setup allowance, not a guaranteed current consumption or output rating. Record actual settings and supply behavior.
6. After testing, disable the supply, discharge and verify rails, and photograph/record any assembly changes. A component rework creates a new assembly identity and requires affected tests to be repeated.

The operator must set a documented conservative temperature stop threshold before power. Proposed first-board screen: stop at 80°C measured U3 case or L2 surface, or sooner for rapid unexplained heating. This is a protective bench threshold, not a manufacturer rating or evidence that junction temperature is safe. Confirm measurement placement and uncertainty; room-temperature observations cannot close the 70°C-ambient thermal requirement.

Immediately remove power for reversed polarity, a persistent short, smoke/odor, unexpected current limiting, output above 3.465 V, rail collapse, sustained instability or abnormal heating. Preserve the capture/settings and diagnose before retrying. A failed test does not justify changing the acceptance limit.

## Step 3 — define the measurement matrix

All numerical limits below are adopted project targets unless their source explicitly says otherwise. They are not claims about measured hardware or manufacturer guarantees.

| Check | Initial operating points | Target / result |
|---|---|---|
| DC regulation | VIN 13.5/15/16.5 V; loads 0, 0.05, 0.10, 0.25, 0.50 A | 3.135–3.465 V; record actual current and board VIN |
| Startup | Begin at 15 V; then 13.5/16.5 V, at 0 and 0.5 A specified load | Rise ≤8 ms; overshoot ≤100 mV above final and never >3.465 V; settled by 10 ms |
| Load step | 0.05↔0.50 A, initially 15 V then input corners | Each edge departure ≤100 mV from pre-edge level, absolute voltage limits, recovery ≤1 ms |
| Pulse | 0.05↔1.00 A, 10 ms plateau, initially 15 V then corners | Same voltage/recovery targets; three pulses per point |
| Output ripple | 0, 0.05, 0.50 A at each VIN; 1 A plateau separately | ≤50 mVpp at 20 MHz, with PFM envelope retained |
| Room-temperature thermal screen | 0.50 A at each VIN | Record ambient, U3 case and L2 surface over time; apply protective stop criteria |
| Efficiency observation | 0.10 and 0.50 A at each VIN | Record VIN×IIN and VOUT×IOUT; compare ≥80% / ≥85% only under the specified 25°C conditions |

Startup and ripple belong in this initial bring-up plan; do not silently defer them out of scope. If the available instrument cannot reproduce a required stimulus or capture, run a clearly labeled exploratory check where useful and mark the exact target **NOT RUN** or **INDETERMINATE**. Documentation can still be complete; physical verification cannot be called complete with mandatory points missing.

## Step 4 — preserve the exact protocol behind the short runbook

**Startup:** begin with VIN and VOUT below 50 mV and EN tied to VIN. For the formal comparison, apply a measured monotonic 0-to-selected-VIN ramp of 1 ms. Set t0 at the actual 13.5 V crossing, capture a pretrigger interval and through t0+20 ms, and define final VOUT as the mean from t0+15 to t0+20 ms. Rise is t90−t10 relative to that final level. Require settling within ±1% of final by t0+10 ms and remaining there through t0+20 ms. The lower steady voltage limit applies after settling, not while starting from zero.

At the 0.5 A startup point, the corrected harness law is `Iload = 0.5 A × clamp(VOUT / 0.1 V, 0, 1)`, with the defined 2% rated-current tolerance. This is a fixture stimulus, not an IC property. Ordinary loads often cannot draw 0.5 A at 0.1 V; check actual compliance and measured current before asserting protocol equivalence. Normal bench-supply turn-on and a resistor load are useful smoke tests but do not automatically satisfy the formal ramp/compliance protocol. Do not build a new load instrument just to complete the documentation.

**Steps and pulses:** slew is 0.1 A/µs ±10%; expected edge durations are 4.5 µs for 0.05→0.50 A and 9.5 µs for 0.05→1.00 A. Confirm current plateaus within ±2%. Use three 10 ms high pulses with starts at least 100 ms apart and at least 100 ms initial/final low-load holds. Evaluate rising and falling edges. Define Vpre from the last 1 ms before each edge and Vfinal from the stable late plateau. Require departure ≤100 mV from Vpre as well as absolute 3.135–3.465 V, and recovery to within ±1% of Vfinal within 1 ms after the edge ends, remaining there for the applicable plateau. Record the actual averaging windows.

**Ripple:** measure directly across C11 or C12 output-capacitor terminals with a short return, 20 MHz bandwidth and at least 100 MS/s. Identify the selected capacitor in the record. TP3/TP4 may be used for this result only if their placement provides the same local pickup without a significant extra loop; otherwise use the capacitor pads. Preserve a 100 ms steady record at light/DC load so burst-mode envelopes are included; do not crop to a quiet switching cycle. Separate 1 A plateau ripple from load-edge excursion, using the available 10 ms plateau. Report probe method, bandwidth, sample rate, window and raw extrema; distinguish input-supply ripple from output ripple. There is no adopted 125 mV input-ripple closure threshold.

**Temperature and efficiency:** at 0.5 A, observe until temperature drift is less than 1°C over 10 minutes, then record a further 10-second measurement window. If the session ends earlier, report a timed observation rather than thermal equilibrium. Measure U3 case and L2 surface with placement/emissivity documented. Do not convert case temperature directly into junction temperature without a defensible method. Full qualification targets U3 junction ≤125°C and L2 hotspot ≤105°C at 0.5 A through 70°C ambient; a room-temperature screen cannot demonstrate this. Measure input/output power at the board terminals with synchronized or steady readings and document meter burden and uncertainty sufficient to interpret margins. Record measured ambient for every efficiency comparison: the ≥80%/≥85% thresholds apply at the adopted 25°C condition. If that condition cannot be established, retain the observed efficiency but mark the target comparison NOT RUN or INDETERMINATE.

## Step 5 — create honest records and a useful next-subsystem handoff

Each result row needs board/release hash, assembly identifier, date/operator, test ID, VIN set/measured, load target/measured, input limit, IIN, VOUT mean/min/max, bandwidth/sample rate, stimulus timing, temperature locations/ambient, measurement units, waveform filenames, and status. Put detailed instrument models, probe attenuation, calibration/uncertainty notes, wiring photo and raw-file hashes in the run record.

Use `PASS`, `FAIL`, `NOT RUN`, or `INDETERMINATE`; leave measured cells empty in the template. Instrument limitations and results close to measurement uncertainty must remain visible. Do not fill templates with model outputs as though they were bench data.

After real testing, the operator's summary should state demonstrated operating points, failures, rework and remaining tests. A proposed next-subsystem power interface can cite the 3.3 V/0.5 A design budget immediately as provisional; it becomes demonstrated only for the measured conditions. Keep the 1 A pulse headroom provisional until it passes. Do not release a sensitive downstream load onto a rail that failed the relevant test.

Deferred work is explicit and bounded: combined capacitor derating, hot-inductor/fault characterization, environmental qualification, validated junction estimation and behavioral-model correlation. The 8.35 A hot-inductor fault screen is not a commanded output load for this board. No mains, inverter, hi-pot or intentional short-circuit tests belong in this initial runbook.

## Documentation acceptance

- [ ] An operator can connect J1/J2 and every required probe using the final drawing without guessing.
- [ ] First power, load progression, current limits, shutdown and retry conditions are explicit.
- [ ] Startup, 0.5 A, 1 A pulses, ripple and temperature all have defined procedures and result fields.
- [ ] Instrument capability gaps result in honest statuses rather than invented passes.
- [ ] Case temperature, junction temperature and later hot-inductor qualification remain distinct.
- [ ] The short runbook and detailed definitions agree with the frozen board and current requirements.
- [ ] No physical test is marked complete merely because documentation is ready.

Have another agent perform a tabletop walkthrough against the schematic and assembly drawing. Resolve conflicting pin labels, missing scope-return details or unstated timing definitions. Do not turn this into another simulator implementation or a full product certification checklist.

## Ready-to-send agent prompt

> Use Luna to execute this documentation plan in `/Users/bennet/Desktop/temper/.worktrees/codex/buck-harness-experiment-plan`. Own `docs/hardware/buck-reva/`; draft in parallel and bind final pinout/probe figures to the board owner's freeze. Deliver a concise operator runbook, detailed measurement definitions, equipment capabilities and empty result templates. Preserve the distinction between prototype preparation and actual bench evidence. Do not energize hardware, edit the model, import full-system 24 V/MCU tests, or claim a runbook is a hardware pass.
