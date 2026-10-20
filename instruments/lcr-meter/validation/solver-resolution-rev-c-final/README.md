> Historical intermediate Rev C circuit: per-range remote 100/10/5 pF compensation. The released circuit uses one local100 pF capacitor. See `../solver-resolution-fixed-local/README.md` for final full-chain traces. These retained results are not transferred to the changed TIA network.

# Final Rev C full-chain solver and transient evidence

This directory tests the final FDA network: 22 Ω from each physical THS4551 output to its feedback takeoff, 1 kΩ in parallel with 100 pF from that takeoff to the opposite input, then 4.32 Ω from the takeoff to the ADC filter. The filter remains 330 pF from each input to ground and 3.3 nF differential, with 16 pF static ADC loading per input. The RGT feedback pins are unused. TIA feedback capacitors are 100 pF / 10 pF / 5 pF on the 100 Ω / 5 kΩ / 100 kΩ ranges.

The models in `models/` are the unmodified official TI OPA810, OPA2810 and 2021 Green–Williams–Lis THS4551 model. Real FDA common-mode bias and its approximately 1 mA input-resistor loading remain connected to the OPA2810 followers and TIA throughout every accepted full-chain result.

## Numerical cause and resolution

The final coupled network is numerically sensitive to KLU's matrix ordering. `partition.cir` fails while `order0.cir` converges at the same strict tolerances and with the same seed. `verify_order.rs` compares component-name maps and asserts that every pin, value and component line is identical. Only top-level declaration order changes. Neither vendor models nor physical connections are changed to obtain convergence.

A single ordering is not reliable for every load and range. `strict_order.rs` tries a finite, deterministic set of declaration permutations: original, reverse, then sorting by an explicitly defined FNV key. Every attempt is retained as its own deck and log. An accepted order must produce one finite operating point, both FDA internal MID references within 1 µV of their exact DC divider values, and a near-zero DC voltage on the AC-coupled source input. The helper removes any stale raw file before running. There is a three-second watchdog per initialization attempt.

The helper issues `optran 1 0 0 0 0 0`: ordinary Newton iteration is enabled; gmin stepping, source stepping and transient-OP fallback are disabled. `newton-only.cir` and `newton-bad.cir` demonstrate immediate success and immediate rejection respectively. The ngspice command's arguments are documented in the [ngspice manual, operating-point analysis](https://ngspice.sourceforge.io/docs/ngspice-43-manual.pdf), pages 305–306. Original failed/fallback runs are retained for comparison.

Do not accept ngspice's exit status or “Transient op finished successfully” as proof of DC convergence. The THS4551 macro-model contains a 1 F internal capacitor and a 1 MΩ divider. A short transient fallback can leave its internal supply midpoint near zero. The correct value at a 5 V supply is 2.499998750 V. `op_guard.rs` and `strict_order::true_op` reject that false state.

## Seed provenance

`old-strict-good.raw` and `old-offset-nodeset.inc` are imported, verified strict operating-point evidence from the preceding FDA topology. `standalone_seed.rs` obtains the final FDA's real operating point under fixed near-zero inputs. `partition.rs` solves the AFE with the corresponding physical resistor loads, then combines these initial guesses. `order0.cir` solves the complete final circuit with that seed. `filter_seed order0.raw final-cap.cir final-seed.inc` exports the accepted final coupled seed.

Only voltage guesses on resistor endpoints are emitted. KLU cannot necessarily create missing diagonal entries for arbitrary internal ideal-source nodes. These `.nodeset` values are released after initialization; they do not impose voltages or replace any bias network. The accepted operating point is independently checked after iteration.

## Results and scope

- `verified-results.md`: six final DC/AC/120 µs sine-transient cases, three common-mode step cases, and AFE output-current KCL residuals.
- `dc-summary.txt`: actual FDA output/takeoff voltages and AFE bias currents. Physical output common-mode is near 2.048 V; the feedback/ADC takeoff is near 2.025 V because of the 22 Ω resistor's DC drop.
- `before-after-results.csv`: final-hardware 5 kΩ fast-pulse comparison. Uncompensated overshoot is approximately 94.25%; 10 pF compensation reduces it below 0.0001% in the nominal test. Last excursion outside 1% moves from approximately 323 ns to 226 ns.
- `corner-results.csv`: fast-pulse supply/fixture corners; the complete-set checker requires all 54 rows and rejects incomplete or failed runs.
- `extended-pulse.md`: additional stage-component, open/short and deliberately mismatched high-range coil tests. A bounded transient is not a blanket stability proof.

The main nominal sweep uses the official 2021 GWL FDA model. Independent FDA model cross-checks, loop-return analysis, tolerances and switched-ADC loading are maintained separately by the lead reviewer. These simulations do not establish board accuracy, noise floor, calibration quality, layout parasitics or performance outside the tested fixture envelope. Hardware qualification remains necessary.

## Reproduce the accepted matrix

Run `./rerun.sh --check` to rebuild the Rust validators and inspect all saved evidence. Run `./rerun.sh --full` to execute the 75 accepted decks again and then inspect the new results. The full run can take many minutes. It deletes declared output files before each run so stale data cannot create a false pass. Ngspice defaults to `/opt/homebrew/bin/ngspice`; set `NGSPICE` to another compatible executable as needed. Rust compilation uses edition 2021. Model includes and seed paths are local and relative.

The other generators preserve the investigation and initial failed orderings; they are not substitutes for the accepted-case manifest. In particular, `final_cases.rs` records the first nominal attempts, including their ordering failures. No compiled helper binaries are required in the deliverable; `rerun.sh` builds them from source.

This package qualifies the explicitly stated circuit. The lead's subsequent review of long compensation-header paths may select additional damping. If that circuit changes, these results remain historical evidence until the affected cases are rerun.
