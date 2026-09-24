# Rev38 joined-candidate capture plan

Status: **procedure only; all physical captures NOT RUN**. This is the
Rev38-specific companion to the [fault ledger](fault-response.tsv),
[timing equations and channel matrix](timing-analysis.md), and the earlier
[protected-AUX fixture procedure](../interface-integration-24/bench-capture.md).
It cannot qualify the current partial Atopile netlist. Record the final
selected source, native board, firmware, and installed part identities before
using any row below as evidence.

## Evidence and article identity

Give every run one ID. Record the assembled article serial and ECOs; hashes
of the joined Atopile inputs, generated netlist, native schematic and PCB;
exact F1/block, AUX module, buck, cutoff, FET, shunt, divider, rail capacitors,
receiver, isolators and watchdogs; both firmware images and programmed fuse
readback; board stackup; and the instrument/probe IDs, bandwidth, sample rate,
calibration status, deskew, and raw-data hash. Record the installed load,
source impedance, local part temperatures, line or emulated-source conditions,
and all relay/PFC inhibition states. A changed source, board, firmware,
component value, or probe chain starts a new evidence identity. An unloaded
or current-limited fault stimulus that fails to reach its declared waveform is
an invalid stimulus, not a pass.

For the first electrical campaign, use a physically isolated, current-limited
low-voltage fixture with the power stage inhibited and independently observed.
Characterize its fault source and load before connecting the article. Use
rated isolated/differential measurements across HOT and SELV; a grounded
scope lead must not bridge those domains. Select source current limit,
fixture fuse, wiring, discharge, and injected energy from the actual article
and selected devices. Review FET SOA and capacitor energy before each forced
OV/short. These low-voltage observations cannot establish mains interruption,
thermal compliance, or final fault-to-current cessation in the power stage.

## Common timing record

Use one synchronized timebase or measured inter-instrument skew. Save raw
waveforms with pre-trigger history, analog bandwidth, sample rate, probe
loading, and trigger definition. Capture all causal nodes simultaneously;
sequential screenshots cannot establish an end-to-end delay. Use fast and long
records so both sub-microsecond clear/gate edges and watchdog/startup intervals
are visible without gaps. For each applicable fault, identify:

| Marker | Physical meaning |
| --- | --- |
| `t0` | First physical fault crossing or externally marked execution-loss stimulus. Report the actual threshold, hysteresis and uncertainty. |
| `t1` | Qualified detector, rail-supervisor, isolator, or watchdog output at its receiving pin. |
| `t2` | Both retained HOT session and RUN clear at their actual Q pins; also source permit Q where relevant. |
| `t3` | UCC27624 EN inhibit at the driver pin. |
| `t4` | Loaded STW gate crosses the independently accepted OFF level at its gate/source pins. |
| `t5` | Sustained switch-current cessation at the measured conductor; identify other stored-energy paths separately. |

Keep the complete `t5−t0` distribution and instrument uncertainty, not only
the fastest trace. Before a numerical PASS, derive each `T_allowable`
independently from the accepted voltage/current/energy envelope and compare
it with the worst supported implementation bound plus margin, as required by
[timing-analysis.md](timing-analysis.md). Where no assembled power stage or
accepted limit exists, label `t5`, `T_allowable`, and the verdict **NOT RUN**
or **OPEN**, never zero or PASS.

## Capture matrix

Every row also captures retained session/RUN Q, EN at the UCC27624 pin,
loaded STW gate-to-source, and switch current when an assembled safe fixture
permits them. Observe the relay drive and contact state for any state that
could energize it. Repeat at declared low/high line or DC-source conditions,
temperature corners, and relevant pre-fault states; record which corners were
actually reached.

| Stimulus and starting state | Additional simultaneous probes | Question answered |
| --- | --- | --- |
| Cold, warm and partial-charge AUX startup; relay and PWM separately and together | Raw AUX (`AUX15_SOURCE` or `RAW_AUX24`), 15 V buck output if fitted, LTC4368 VIN/GATE/OUT and sense current, `AUX_PROTECTED`, driver VDD, HOT logic5, SELV3V3, relay coil current, both rail resets | Does the selected source start every intended load without cutoff chatter or an unintended RUN/relay request? What peak and local temperatures occur? |
| Slow and fast source OV, feedback-loss/high-output fault, UV, overload, short, repeated mains-dip emulation | Same supply probes plus AUX fast-dip/OV comparator outputs, both TPS3890 RESET pins, HOT trip fan-in, receiver abort, cutoff FET VGS/VDS/current and case temperature | Bound protected driver-pin peak, source/cutoff energy and recovery; show inhibition before control rails leave guaranteed regions. |
| Physical PERMIT break before first high, and after captured high; STOP in READY and RUNNING | Both sides of the isolator, source local permit and seen Q, HOT physical PERMIT and seen Q, receiver abort, HOT session/RUN Q | Distinguish normal pre-permit low from a session-invalidating high-to-low loss; verify physical clear without UART cooperation. |
| Qualified VD/VB OV, mismatch, F2 opening, and overcurrent under separately reviewed low-energy emulation | Physical VD/VB, comparator pins and outputs, F2 terminals, shunt/PCL/PWM, inductor and switch current, HOT trip fan-in | Show detector capture, memory clear, loaded disable and any energy path that gate disable cannot interrupt. Equal-voltage F2 opening requires its own observability test. |
| Receiver reset, stalled decoder, malformed link, preparation timeout, late START | AVR RESET, abort_N, WDI/WDO, complete isolated UART frames, receiver challenge/seen-reset/RUN-set, physical PERMIT | Verify default abort, fresh identifier, bounded deadlines, no post-fault START rearm and no watchdog credit from a stalled parser. |
| ESP execution loss while RUNNING or with one first START committed | External loss marker, GPIO21 rising WDI request, one-shot output, TPS3431 WDI/WDO, STOP_N, physical PERMIT, source/HOT latch Q, UART TX FIFO-empty event and final stop bit at isolator/AVR RX | Find the last qualifying watchdog edge after loss; prove no new interval, rebooted START, or duplicate START. A FIFO-empty indication is not final wire-bit completion. |
| Cooker power/EN reset, GPIO14 controlled reset, and narrow fault before/during/after reset release | Cooker SELV3V3, ESP EN, TPS389001 SENSE/CT/RESET, GPIO14, GPIO15, latch Y2/SHUTDOWN, mate header 14/15, Rev38 SOURCE_HEALTH_Q and STOP_N | Prove that startup reset initializes the latch, GPIO14 is high-Z/open-drain without supervisor contention, a live fault wins during reset, a cleared transient remains latched afterward, and both candidate producer outputs stay low across partial-power and unplugged-cable states. |
| Preparation seen-reset pulse at the deadline edge | Expander P0/P1 pins, I²C SDA/SCL/acknowledgements, source clock marker, STOP_N, HOT feedback and receiver abort | Bound the **pre-edge** transaction and I²C delay; a check after P1 rises cannot retract a late pulse. |
| Partial-power and rail-order permutations | SELV3V3, HOT logic5, driver VDD, both sides of each relied-on isolator channel, reset supervisors, local EN bias, AVR reset/abort | Show default-off with driver supply present and HOT logic absent, and no false liveness or stale high across either domain. |
| Failed-short STW/diode or noninterruptible bank discharge | F1/F2 terminal voltage/current, bank energy and current paths, interconnect temperatures | Use a separate interruption/containment verdict; gate disable has no valid `t5` for the failed path. This row is **not** authorized by low-voltage gate captures. |

### Source-reset feed-tail discriminator

For the ESP execution-loss row, start once with RUN retained and once with a
first START already committed but not yet received. Repeat CPU-only reset,
`esp_restart`, panic, task/RTC watchdog reset and brownout. Inject each reset
immediately after a qualifying WDI edge, during an expander P1 write, and
during a UART START frame. Record the actual reset cause. Probe the GPIO21
pad and one-shot B2 input separately, Q2_N/WDI, WDO, GPIO13 STOP_N, GPIO48
permit-set clock, both permit Q pins, TCA6408A P0–P2, SDA/SCL and the
SELV3V3 rail on a shared timebase. Include the UART final stop bit at the
receiver and the HOT session/RUN clear pins.

Force a continuous boot loop as a falsification test. If each reboot creates
another qualifying WDI edge before WDO times out, the feed tail is
**unbounded** and the reset candidate fails, even if a finite single-reboot
trace appears safe. For every reset class and starting state, identify the
last WDI falling edge after `t0`, attribute each GPIO21/B2 transition to a
firmware write, pad pull, boot path or rail disturbance, and bound the
maximum last-edge time with instrument uncertainty. A pad transition seen
without a named owner or a high retained expander output that can clock a
new permission edge is a failure to establish that bound. Check whether
GPIO13 falls before or after the last WDI edge and whether physical PERMIT,
RUN and EN clear without firmware service. The 10 kΩ GPIO21 pull-down is a
typical-pull-up screen only; it is not a substitute for these captures.

Only compare a finite, supported feed-tail maximum plus the installed WDO
and downstream clear/current-cessation maxima against an independently
derived allowable time. Do not count a reset-to-low STOP trace as proof of
the first-START path unless the already-issued START and final UART bit are
also accounted for.

Include narrow minimum-width fault pulses, pulses during preparation while
`HOT_SESSION_OK` is already low, a held revalidation request coincident with
clear, and near-threshold rail ramps. Record what waveform actually reaches
the device pin and whether a pulse meets its qualified capture minimum.

## Review and stop condition

For each row, retain the raw data, annotated `t0`–`t5` markers where they
exist, uncertainty, corner coverage, and observed failure/recovery state.
Map it to the event ID in `fault-response.tsv` and AE1–AE5 in the final
`ACCEPTANCE.md`. A digital netlist or host test can establish connectivity or
logic only. A low-voltage article can establish its own observed behavior
only. Leave the response-time, fault-to-current-cessation, F1/F2 interruption,
thermal, and mains decisions OPEN until each has the required installed
article and independent limit. Stop a run on unintended RUN, relay closure,
overstress trajectory, unqualified overvoltage, or fixture failure and retain
that trace as a failure rather than resetting it into a pass.
