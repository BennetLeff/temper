# Interface physical boundary 14

This round defines a reset-path architecture, tests its event ordering, and
rules out a low-current passive AUX barrier under the stated supply envelope.
It also corrects the rail-current corner calculation. **The compiled circuit
remains revision 11 with 136 components.** These are isolated design experiments;
no electrically qualified replacement interface is claimed.

## Result and next design choice

Use a hardware-captured, default-low reset/permission path independent of the
HOT command decoder. Recovery must require reset observation, a newer session
and fresh source intent. A short reset must be captured and held; repeatedly
observing low must never extend the first shutdown deadline. The final model
also clears hardware permission while leaving a frozen decoder frozen.

To fit bidirectional commands without adding a separate isolated reset channel,
the proposed channel allocation is:

| Direction | Signal | Required implementation |
| --- | --- | --- |
| SELV → HOT | COMMAND_TX | Framed command transport; receiver validates session/intent |
| SELV → HOT | PERMIT_TX | Hardware AND of interlock permission, source reset-good and external watchdog-good; captured faults force low |
| SELV → HOT | RELAY_CMD | Existing relay command, with its own default/sequence qualification |
| HOT → SELV | RESPONSE_TX | Challenge and acknowledgement transport |

This fits the **direction count** of the previously screened ISO7741F family;
it is not a selected package/pin map or an isolation qualification. A separate
SOURCE_OK conductor would need a fourth forward channel in addition to the
return. Combining source health into PERMIT_TX sacrifices fault localization
and does not tolerate a shared PERMIT_TX path stuck high. Existing HOT rail
health remains a separate local trip. Source reset-good is a hardware
processor/supply status function; it is not the interlock's fresh-reset pulse.

The hardware role of the model's `arm_authorized` flag must be implemented:
a fault clears it independently of decoder execution, and a valid new session
is required before a new START can enable output. It must not be implemented
as an ordinary software variable while claiming frozen-processor coverage.

The complete physical stop bound must include:

`Tstop = source-fault detection + capture + isolation/filter + latch/logic + driver/MOSFET turnoff`

All terms need actual worst-case limits at the specified rails, temperature,
loads and pulse width. The two-tick examples are abstract event-order tests.
No allowable pulse energy or full PFC fault-response deadline has been proven.
An asynchronous path also has finite delay. The model demonstrates an enabled
interval when a valid START arrives before the inhibit arrives; it does not
make that interval acceptable by calling it small.

## Executable evidence

The reset worker's first model let repeated low observations postpone reset,
and lost a short low pulse. The parent reproduced both failures and retained
the witnesses. Its second model still mishandled an open conductor and allowed
an invalid command to defer a trip at the same timestamp. Independent tests
caught these defects; the final parent-corrected source passes **21 tests**.
One test deliberately preserves the failed-high conductor counterexample, and
two exercise finite START/inhibit ordering. Passing these tests establishes
the specified abstract behavior, not physical fault tolerance.

See [reset/design.md](reset/design.md), `reset/reset_timing.rs`,
`reset/parent-tests.rs`, and `reset/parent-final-tests.log`. Historical v1/v2
sources and failing logs are retained. The reduced decoder is not a second
production protocol implementation and is not an integration test of the
full v13 handshake; validated frames and persistent session storage remain
external requirements.

The AUX calculator passes **3 focused arithmetic checks**. Independent
ngspice RC threshold measurements match the parent's closed-form calculation
at the recorded precision. No actual limiter or fault-source model is present
in that RC oracle.

## AUX conclusions

- Corrected conditional load: **114.473684 mA**, using protected AUX=14.25 V,
  logic5=5.25 V and assumed 70% conversion efficiency. New transport loads
  and a complete bound on the existing 75 mA allocations are still absent.
- Available total series resistance: at most **3.275862 Ω**, before switch
  and wiring losses. A resistor limiting a stiff 35 V fault to 120 mA from
  14.25 V would need **172.916667 Ω**. Those requirements do not overlap.
- With an ideal stiff 35 V fault source, 3.275862 Ω and 10 µF effective
  downstream capacitance, the rail rises from 15.75 to 18 V in **4.071822 µs**.
  This sensitivity result is not measured behavior of the Mean Well module.
- Visual inspection of TPS2660 Rev G page 9 resolves the old timing ambiguity:
  **6 µs is nominal, MAX is blank**, and the endpoint is FLT falling. It cannot
  supply the required maximum turnoff/charge guarantee.

See [aux/report.md](aux/report.md) and [load-audit.md](load-audit.md).
A series resistor plus finite capacitor cannot protect indefinitely against a
persistent overvoltage. The next AUX design should therefore develop the
already-screened active clamp or a cutoff with a guaranteed delivered-charge
bound, with exact pass device, output capacitor, timer and compensation.
The source envelope and full load budget must be established before treating
any such parts as selected. Another nominal simulation cannot replace that
information. The minimum isolated low-voltage measurement protocol is included
in the AUX report; no hardware experiment was performed.

## Provenance and reproduction

All nine frozen electrical/source-contract inputs remain unchanged. The new
models and input identity are recorded in `receipt.json`, `input-identity.json`
and `artifact-hashes.json`. Workers used separate temporary directories; the
parent inspected, corrected and integrated their evidence here. Luna was the
requested model; served-model identity is not independently attested.

Compile `reset/reset_timing.rs` concatenated with `reset/parent-tests.rs` using
`rustc --edition=2021 --test`; run the resulting binary. Compile/test
`aux/aux_envelope.rs` separately. Compile `load_audit.rs` and
`transient_window.rs` as ordinary Rust binaries. Run
`ngspice -b rc-oracle.cir -o rc-oracle.log` for the independent RC check.

No production source, PCB, firmware or part count changed. No commit, push,
vendor contact or hardware qualification occurred.
