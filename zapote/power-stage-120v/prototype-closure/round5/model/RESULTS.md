# Round 5 model results — 2026-10-05

The accepted replay is
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

## Findings requiring design/model closure

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

Only `round5/model/` and its matching model output were authored. Native19,
prior evidence, production firmware, peer boards and component selections were
not edited. No Git index, commit, push, supplier message, purchase or hardware
energization was performed. Full model assumptions and replay commands are in
`README.md`; the compact CSVs permit independent checking without replaying all
runs.
