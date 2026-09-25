# ARM/PERMIT defaults and AUX overvoltage — isolated revision 11

The isolated candidate adds receiver-side ARM/PERMIT bias and an AUX
overvoltage path that clears retained RUN. The compiled assembly has **136
component instances**: revision 10's 128 plus six resistors, one single AND
gate and its bypass capacitor. This addresses gaps in the 128-part candidate;
it is not another component reduction. The original 131-part revision remains
unchanged, as do the canonical RevB source and the existing interface documents.

Status: nominal circuit experiment complete; not approved for hardware adoption.
The producer contract is now explicit in [INTERFACE-CONTRACT.md](INTERFACE-CONTRACT.md).
It still requires an implemented command producer and a supply/limiter that
bounds AUX voltage. Gate shutdown does not clamp the supply.

## Circuit changes

| Addition | Count | Purpose |
|---|---:|---|
| Raw ARM and PERMIT 10 kΩ pulldowns | 2 | Bias the receiver inputs when the producer is high impedance or a signal conductor opens |
| AUX OV divider, 560 kΩ / 100 kΩ | 2 | Set a nominal 16.5 V threshold against the existing 2.5 V reference |
| 22 kΩ comparator input series resistors | 2 | Limit input injection; actual partial-power behavior still needs qualification |
| SN74LVC1G08DBVR and 100 nF bypass | 2 | Combine existing AUX undervoltage and new overvoltage healthy signals |

The spare channel of the existing TLV3202 supplies OV detection. Its OUT2 is
high below the OV threshold and low above it. OUT1 and OUT2 drive separate
inputs of the new AND; its output drives health.D2. No push-pull outputs are
connected together, and neither is connected to the shared open-drain RESET net.
Both TPS3890 supervisors, their timers, the retained latch, and the final driver
enable gate remain. Routing OV through a supervisor MR pin was rejected for
this experiment: MR pulse recognition and propagation would introduce another
condition into the fast fault path.

[component-delta.json](component-delta.json) records exactly eight additions,
zero removals and zero attribute changes to existing instances. The protection
block is now 84 instances; the rest of the assembly remains 52. Counts include
the source's interface components and are not an orderable, fully selected BOM.
The new generic passives still need exact MPNs and ratings.

## What the measurements establish

The same Rust checker was applied to traces from the old and new models.
The old-model failures were observed before changing the candidate. Each
disconnect opens a modeled cable switch; it does not force the receiver input
low. Input/cable capacitance is an explicit, unmeasured 1 nF assumption.

| Scenario | Before | After | Meaning |
|---|---|---|---|
| OV while running: 15 → 17 → 15 V | FAIL | PASS | Stops, retains the stopped state after recovery, then accepts a fresh ARM edge |
| Startup at 17 V | FAIL | PASS | Cannot start while OV is present; needs a later ARM edge |
| PERMIT conductor opens and reconnects | FAIL | PASS | Raw PERMIT discharges, clears RUN and cannot restart on PERMIT return alone |
| Producer reset; both outputs disconnect, ARM returns low | FAIL | PASS | Stops and waits for a deliberate new ARM edge |
| ARM conductor opens while running | FAIL | PASS | Raw ARM discharges; RUN remains set, as defined for an edge request |
| Normal AUX upper limit, 15.75 V | PASS | PASS | Remains running in this nominal fixture |
| ARM reconnects with producer already high after a fault | FAIL | **FAIL, expected** | Reconnection creates a rising edge and can restart; hardware cannot infer intent |

The last row is a demonstrated limitation, not a passed safety case. A 10 kΩ
pulldown cannot distinguish a deliberate command edge from reconnecting a high
source. The producer must hold ARM low through reset and reconnection. An ARM
wire break alone is not a stop command; PERMIT is the maintained permission.

Retained evidence:

- [before/results.csv](before/results.csv), [after/results.csv](after/results.csv),
  per-case circuit files, full traces, simulator logs and checker exit statuses.
- [regression/traces/summary.csv](regression/traces/summary.csv): all 13 inherited
  ordinary cases pass; the two inherited negative controls fail as expected.
  The inherited Rust extractor is byte-identical to revision 10's extractor.
- Removing the new PERMIT pulldown causes `permit_open` to fail
  ([negative result](missing_permit_pd/result.txt)); bypassing OV at the health
  gate causes `ov_running` to fail ([negative result](ov_bypassed/result.txt)).
- Four checker self-tests pass. Following review, the checker was strengthened
  to require measured 15.75 V in `normal_upper` and raw ARM low before rearm in
  `producer_reset`; rechecking every retained trace preserved these outcomes.
- [net-connectivity.txt](net-connectivity.txt): a Rust audit checks 136 instances,
  13 pin-connectivity groups, separate comparator/window/RESET outputs, and raw
  rather than buffered input bias. This is a focused topology check, not full ERC.

## Threshold and input budgets

[corners.rs](corners.rs) gives a **conditional static** OV range of
**16.049833–16.961738 V**, with a 16.5 V nominal threshold. It assumes at most
1% total resistor deviation including temperature, a 20 mV reference allowance,
6 mV comparator offset, and 5 nA bias per input. It is not a complete guarantee
across supply, common mode, temperature, noise, parasitics and transients.
The exact conditions and unclosed items are in the contract.

This explicitly refines the earlier proposed interface wording: 14.25–15.75 V
is the **normal AUX range**; a separate guard band allows OV detection above
that range. This circuit does **not** guarantee permission removal the instant
AUX exceeds 15.75 V. Nonzero threshold tolerance prevents simultaneously
accepting 15.75 V and guaranteeing a trip at or below that same voltage.

With a required aggregate input leakage no greater than 25 µA and maximum
pulldown resistance 10.1 kΩ, the calculated disconnected input is at most
0.2525 V. With at most 1 nF capacitance, decay from 5.5 V to 1.51 V takes about
14.43 µs. This is an RC budget, not a guaranteed complete shutdown latency.

## Evidence boundaries and review

The behavioral model uses nominal supply thresholds, authored delays, an
idealized latch, and a 12 nF gate load. The new window AND uses a 3 ns RC
surrogate; comparator input capacitance is assumed 2 pF. These are not vendor
maximum-delay models. The suite does not establish minimum detectable OV pulse
width, chatter immunity, full brownout behavior, isolation, appliance energy
decay, or the physical PFC standby network. The inherited sub-microsecond UV
comment describes intent and a nominal experiment, not a hardware guarantee.

Luna reviewed the producer defaults and then the final wiring and checker.
The final review's two checker qualifications were addressed as described above.
Its apparent stale-netlist concern was investigated: export hashes match every
compiled output. Atopile 0.2.69 aliases netlist `libsource` part metadata by
footprint, a known limitation already documented in
`harness-lab/BUCK-ENGINEERING.md`. Thus the AND instances appear under a buffer
library alias in the netlist, while resolved per-instance attributes correctly
identify SN74LVC1G08DBVR. Use resolved attributes for part identity and the
audited nodes for connectivity. This netlist is not a manufacturing BOM.

[input-verification.json](input-verification.json) confirms all eight frozen
inputs and prior edited documents are unchanged, and that compiled output
hashes match the export. [commands.md](commands.md) records reproduction.
[receipt.json](receipt.json) summarizes outcomes; [artifact-hashes.json](artifact-hashes.json)
identifies the retained artifacts. No PCB was edited, no hardware was tested,
and this experiment was not promoted into the canonical circuit.

The next engineering step is to select and qualify the HOT-domain command
receiver/producer and the AUX source or independent limiter against this
contract, including reset/reconnection and overshoot. A further part-count
reduction is not evidence that either boundary has been closed.
