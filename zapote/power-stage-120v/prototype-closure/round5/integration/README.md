# Round5 joined implementation review

Status: **native board, target, conditional model and nominal mechanical
verification pass within the recorded scopes; no fabrication or powered-test
release.** The milestone remains a few engineering prototypes.
No assembled hardware is available. Digital checks and physical qualification
are tracked separately.

The FPGA experiment is optional bench research and has been removed from the
product build/model path. The cooker retains ESP32/STM32 control and discrete
hardware protection. On-chip register diagnostics are explicitly distinguished
from physical gate measurements. See [architecture-decisions.md](architecture-decisions.md).

## Implemented changes under review

- Shared target/model measurement, loaded bypass proof, precharge-isolation
  sequencing and GPIO signal projection replace diverging operational helpers.
  Cold POST requires two isolated branch measurements with uncertainty.
- ADC command CRC framing, startup synchronization, heartbeat direction/bias,
  PWM update/inhibit and contactor pickup/proof timing were corrected. The
  common reset, STOP_DONE, catch-history and ADMIT protocol now has regression
  coverage. A timer-driven mirror scan separates its deadlines from SPI work.
- Two independently controlled precharge isolation contactors open before RUN;
  five24V-wetted mirror receivers, signed discharge windows, one-token admission
  and a second loaded proof implement the corresponding candidate architecture.
- The supervisor supply uses a5V buck and precision3.3V postregulator. Its
  load/startup/thermal assumptions are explicit. VPRE's divider was increased
  to801:1 after shutdown exposed the old amplifier range limit.
- Independent review found the inherited SN74LVC1G74 physical pin error despite
  passing logical tests. All six mappings were corrected and rerouted. The
  final 596-part central board and eight sensor boards pass 27 native DRC runs
  with zero violations, opens or parity differences. Central ERC retains 14
  documented warnings and zero errors. Earlier receipts remain historical.
- Session retention now requires fully qualified RUN within446ms, then live
  runtime health. Zero demand no longer reapplies startup timing. Independent
  review and29 generated-pin state cases pass; proof without RUN still expires.
- HS400 mounting geometry now uses the specified45mm pitch and distinct8mm
  slots/5.4mm holes. A negative-control test rejects the old44.7mm pattern.
- Packaging adds actual native board placements, guided BUS/TANK sensing
  paths and candidate support/fastener/drilling details, matching the final
  central and PRE native board identities. The supervisor and part of the
  protection/sensing hardware occupy a separate engineering-prototype pod.
- The inherited reflected native19 placement was rejected and replaced with
  a proper top-up rigid placement. Cooling, clamp, support, catch and harness
  geometry were rebuilt around it. The exported-file orientation check passes
  and rejects the historical mirror as a negative control.
- A dedicated sink-to-cradle earth bond now has explicit terminals, locking
  stacks and a connected split-guide restraint. Independent review also found
  an unretained catch guide; its lower body and base are now one machined part.
  Its closed bores require threading before termination and do not establish
  axial strain relief. Fastener access requires the documented service stage.

## Evidence and current dispositions

[findings.json](findings.json) is the per-finding record, including source,
observed failure, correction and verification status. The independent review
scope and its limits are in [review-20261005.md](review-20261005.md).
The [verification snapshot](verification-snapshot.json) binds the board,
firmware, model, mechanical review, PDF and STEP artifacts by full hashes.

The independent ADC command oracle passes3 manufacturer-protocol vectors using
current `acquisition.c`; all3 failed with the earlier builder. The protection
geometry replay passes with four45mm transverse pitches and the old-pattern
negative control. The additive protection candidate's frozen source manifest
matches; its sanitized sequence,54 analytical/ngspice exposure cases and
131072 conditional discharge-window corners are recorded in
[protection-closure/RESULTS.md](../protection-closure/RESULTS.md).

The [board checkpoint](../boards/checkpoint.json) pins 358 artifacts; all hashes
were independently rechecked. The central native board is
`f307cdd9c75840c6b90c42dadd8eeb334c827fefedf520cd4b79076bdc8c9221`;
its pin table is `d8a30d9a8b82539ef012fb70c550a7e66d7c2e949fd455d59900a8323b64352e`.
Eleven interlock and five power tests pass. DRC and connectivity checks do not
close the dynamic, thermal, insulation and tolerance holds in the
[power review](../boards/power-review.md).

The accepted current model links the actual shared control and signal-projection code.
It requires actual joined RUN permission, nonzero electrical load and open
precharge isolation. Contact-reversal and invalid-audit negative controls were
added. The final frozen replay completes24 control/electrical cases,16 local
device references and64 energy cases, with all input hashes matching and a
maximum0.04837% control-case refinement difference. It does not qualify actual
gate/analog timing, installed catch inductance, DC fault clearing or thermal
survival. Historical receipts remain historical; source-changing or failed
runs are not accepted for this revision. See [model/RESULTS.md](../model/RESULTS.md).

The native19 power-board baseline remains SHA-256
`3557aa444873fa8b45eb7e0ae8ec3a4bc2b5cd526826b338b58d50e57747430b`.
Neither this review nor the new auxiliary boards change that identity.

The corrected cooker STEP is SHA-256
`a341bf9a4747c85074304d3ea40749837457d8f1ffd522cbf92c48e133fe9b69`.
It contains 927 valid solids. All 31 nominal placement, support/service and
harness check groups pass. Independent review verifies native-board placement,
modeled thermal and PE contact chains, the integral catch-guide attachment,
the four delegated cooling interfaces, and the final floor's 26 new cuts
with eight obsolete cooling holes removed from the new-blank design. These
results do not establish actual contact force, thermal performance, insulation,
fault withstand, supplier fit or assembly tolerance yield. See the
[installation package](../packaging-integration/README.md),
[cooling correction](../orientation-cooling/README.md) and independent review.

## Remaining work must keep its actual category

The [remaining-work checklist](remaining-work.md) gives the evidence required
for each release item. FPGA development is excluded from that checklist.

**Digital/supplier work:** complete the readable whole-circuit review,
target provisioning and operational input providers, installed
catch/return geometry and complete extracted coupling model, applicable DC
fuse/contact interruption data, proof-load500ms pulse qualification and final
product insulation requirements. None is closed by saying hardware is absent.

**Physical work:** measure the real coil/pan and capacitor operating envelope;
qualify sensors, rail startup/thermal behavior, contactor timing/feedback,
physical four-gate waveforms, shutdown, insulation and assembly tolerances.
Build and inspect the first prototype before repeating it. Existing simulations
are conditional studies and cannot establish fault survival or manufacturing
readiness on their own.
