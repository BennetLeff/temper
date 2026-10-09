# Round 5 model results — 2026-10-05

## Current revision versus historical evidence

The accepted current revision joins the actual shared target measurement, loaded
bypass predicate and precharge-isolation controller. FPGA capture has been
removed from the product simulation path. The historical receipts below do
**not** validate these new source bytes. The current accepted replay is
`output/temper-prototype-closure/round5/model/joined-product-20261005e/`.
Its final status is `DIAGNOSTIC_REPLAY_COMPLETE_NO_POWER_RELEASE` and every
pinned input passed the post-run hash check. See [current-evidence.json](current-evidence.json)
and the compact `evidence-current/` receipts; `evidence.json` remains historical.

| Current evidence | Result | Limit |
|---|---|---|
| Shared controller, measurement and GPIO projection |24/24 cases complete at0.625/0.3125µs; maximum refinement0.0483692% | Ideal analog/peripheral/native-gate boundaries remain |
| Actual joined RUN | Nominal first RUN0.785s,0.485s permission,327.013J load, zero RUN with precharge isolation conducting | Averaged load omits tank switching/return energy |
| Demand pause/resume |100ms zero demand after RUN, subsequent RUN and normal STOP pass | Not a measured timing test |
| Proof without subsequent RUN | Second proof0.784s; source admitted0.379s; fault0.825s, exactly446ms later, both steps | First RUN still required before deadline |
| Failure controls | Catch/bus shorts, stale ADC, invalid readback, open proof/bypass, invalid POST and inhibited path match expected faults; readback loss trips at1.001s | These are specific shared-software fault paths, not fuse/comparator qualification |
| Audit negative controls |7/7 pass, including false enum-only RUN, nonfinite results and mis-timed events | Protects this evidence pipeline, not the physical cooker |
| Local vendor device references |16/16 complete | Separate native19 A/B matrices,198V/37A assumptions |
| Finite-energy oracle |64/64 complete;4.748ppm maximum energy residual,0.09116% refinement | Unmeasured initial-state and loop-inductance sensitivities |
| Complete installed geometry | Correctly rejected as incomplete | No installed catch/shared-return extraction claim |

Current prospective catch demand reaches4295.13A²s with an assumed conducting
fuse. The isolated precharge branch peaks at1056.67W in this particular model;
that does not qualify its full hot/repetitive fault envelope. The separate
finite-energy study still reaches254.112V against the250V guard allocation.
DC clearing, hot pulse/SOA limits, the real operating envelope and complete
installed geometry remain unresolved. Corrected mechanical routing does not
make the assumed1/3µH catch values extracted measurements.

## Preserved intermediate failures

Interim runs are deliberately not accepted as current-revision evidence:
`shared-target-20261005a` detected source changes during execution, and
`shared-target-20261005b` failed the2% refinement criterion (6.3449% on a fault
peak). Investigation replaced an ill-conditioned linear-resistance contact
ramp with a declared linear-conductance ramp; the arc/contact law remains an
unqualified sensitivity. Independent review added contact-reversal tests and
an audit that requires actual joined RUN permission and electrical load.

`joined-product-20261005a` used stale expected fault outcomes and changed
source identities. `joined-product-20261005b` completed its individual
processes, but the joined audit exposed incorrect bad-POST expectations and
then a10.02% catch-I²t refinement difference. The latter was caused by
comparing floating-point solver time to the STOP deadline: one step size
stopped at1.270s and the other at1.271s. Integer-microsecond event scheduling
corrects the deadline; a negative audit test rejects that one-tick drift.
Neither old run has been relabeled as passing.

`joined-product-20261005c` repeats the cases with the corrected event clock
and adds a100ms zero-demand interval after successful RUN, followed by resumed
heat demand. Its22 cases and numerical audit passed (maximum0.04837%
refinement), but its final input check correctly rejected five changed files:
the stronger retained-RUN contract and added no-demand case were implemented
while it ran. Its STATUS remains INCOMPLETE and it is not current evidence.
`joined-product-20261005d` repeats the complete set against the new freeze,
adding startup proof without subsequent RUN as an expected timeout.
All24 individual simulations completed. Its original audit expected the
adapter's readback fault code7, but the newly retained-session PWM-health check
correctly withdraws hardware health first, producing code1 at1.001s after the
injected loss at1s. The revised audit requires that exact fault time, rejects
an unrelated earlier fault, and passes all24 receipts without changing the2%
convergence threshold. The original run remains INCOMPLETE because its pinned
auditor changed; its post-review `audit.json` is explicitly a reanalysis.
`joined-product-20261005e` is the fresh full replay of the final frozen sources
and corrected auditor.

The joined nominal probes reached RUN after the two mechanical self-tests and
second loaded proof. Shutdown then exposed VPRE clipping at249.793V, beyond
the old native divider's approximately248.76V amplifier linear range. This
was corrected by the separate801:1 VPRE board ECO and the current replay.
Probe directories are not accepted completed-revision receipts.

## Preserved earlier replay

The earlier accepted replay is
`output/temper-prototype-closure/round5/model/replay-20261005c/`.
Its `STATUS` is `DIAGNOSTIC_REPLAY_COMPLETE_NO_POWER_RELEASE`; every pinned input
passed the end-of-run SHA256 recheck. Compact receipts are in `evidence/` and
indexed by `evidence.json`. Earlier probe, failed SPICE energy and intermediate
refinement directories are exploratory and must not be cited as accepted runs.

| Evidence | Result | Meaning |
|---|---|---|
| Actual portable C controller with dynamic averaged plant | 20/20 cases completed; maximum final refinement difference 0.665% across recorded peak/energy/I²t metrics | Executable sampled feedback and sequence evidence under the stated idealized interfaces |
| Inhibited build, missing POST, bypass-open, proof-open, lost ADC, corrupted capture | All expected inhibit/fault outcomes matched | Negative controls exercise actual control and parser code |
| Installed shared-library analytic RC oracle | 0.1203µV maximum error; seven exact 256µs deadlines | Checks the integration instrument independently of the Temper plant |
| Sample estimator analytic sine/harmonic tests | Passed true RMS, crest admission, missing-proof and duplicate-time checks | Diagnostic estimator arithmetic; no target analog qualification |
| Separate A/B Infineon references | 16/16 complete; maximum reported die VDS 246.1931V | Conditional 198V/37A local references with finite-closure matrices, not an operating limit |
| Independent finite-energy recovery/short oracle | 64/64 complete; maximum energy residual 4.749ppm; maximum refinement difference 0.0912% | Numerically consistent reduced energy model; not semiconductor SOA |
| Complete installed catch geometry | Rejected as incomplete | No extracted installed catch inductance or cross-leg matrix claim |

Nominal startup reaches RUN at268ms. The separate extended replay in
`output/temper-prototype-closure/round5/model/extended-cases/` completes1.5s at
1.25/0.625µs. The final RUN sample in the finer run has conductance0.104157S,
line RMS119.999V and inlet RMS12.3429A; maximum logged RUN inlet RMS is12.3436A.
This demonstrates the actual conductance ramp approaching the1500W request in
the averaged plant. It is not a measured1500W thermal, EMI or load-tolerance test.

## Historical findings from the earlier topology

The following numbers describe the preserved earlier replay, before monitored
precharge isolation and shared target integration. Use the current table above
for the latest conditional study; do not mix the two topology identities.

1. **DC fault clearing is still unsupported.** With the fuse intentionally
   represented by an assumed2mΩ conductor, the source-fed catch short accumulates
   approximately5362A²s. This is prospective demand, not fuse let-through.
   The20/24ms assumed bypass/source opening sequence diverts energy through the
   precharge path. Across the source fault cases, individual resistor peak power
   reaches36.612kW with the explicit400V/0.5Ω contact arc sensitivity. Final
   numerical refinement is below0.665%, but the physical arc law remains
   unverified. Available4000W overload evidence cannot justify this demand.
   A real DC fuse/contactor interruption model and component pulse coordination
   must replace the conductor/arc assumptions before accepting this design.

2. **The assumed stored-energy range can exceed the catch guard.** The reduced
   finite-energy oracle reaches254.112V on the catch capacitor and271.011V on
   the bus, using the explicitly unmeasured tank state and assumed catch loop.
   Do not dismiss this because the averaged plant reports zero tank stress:
   that plant omits tank energy by construction. Establish actual coil/pan,
   capacitor and shutdown state bounds and then qualify the guard/catch margin.

3. **The whole target is not yet the co-simulated executable.** The controller
   cores and packet parsers are real source; measurement qualification,
   calibration, contact/POST/cold-condition inputs, FPGA capture and peripheral
   schedules have ideal harness boundaries. Integrate the target's eventual
   shared measurement helper and real HAL timing, then repeat against its exact
   identity. The target remains inhibited. No calibrated sensor, physical Vgs,
   ZVS, shoot-through, MCU independent shutdown or supervisor-chain pass follows
   from these cases.

4. **Parasitic coverage is local.** Both accepted native19 4×4 matrices are used
   separately. Complete catch internal paths and native return closure are
   absent. Cross-leg/shared-return/CM/chassis modes cannot be fabricated from
   the two local matrices. The1/3µH cases remain sensitivities. Obtain defensible
   physical geometry or correlated measurement bounds before a combined claim.

5. **Device and hot-fault models remain bounded in scope.** The local MOSFET
   references use the vendor L1 model, but the full plant does not use an exact
   rectifier/catch/driver/TVS electrothermal chain. The catch diode's manufacturer
   simplified forward model is limited below80A and its surge ratings are
   waveform/temperature-specific; see `primary-source-check.json` and the
   [official datasheet](https://www.infineon.com/assets/row/public/documents/24/49/infineon-idw40g65c5-ds-en.pdf).
   Neither the supplier's10ms I²t nor the fuse's AC total-clearing number is an
   arbitrary-waveform DC coordination proof.

## Files and ownership

The replay reads shared target and power-control sources whose integration
corrections are recorded in `../firmware/` and `../integration/`. Native19 and
historical evidence are preserved. No hardware was energized and no power
release follows from the receipts. Full assumptions and replay commands are
in `README.md`; the compact current CSVs permit inspection without replaying
all runs.
