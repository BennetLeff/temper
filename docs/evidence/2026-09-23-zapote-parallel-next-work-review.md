# Zapote next digital milestone: implementation review

Date: 2026-09-23. Scope: the four independent P1–P4 gates in [the reviewed plan](../plans/2026-09-23-zapote-parallel-next-digital-milestone-plan.md). The active Rev38 checkout was read only. These are digital fixtures and screens; no energized or assembled appliance test was run.

| Unit | Reproducible milestone | Result and next boundary |
| --- | --- | --- |
| Auxiliary | Atopile 0.2.69 built the lab-only, mains-disconnected HOT rail-order coupon from byte-matched source; generated node-map audit checked 10 nets and 13 passive components. Eleven Rust tests include early-gate and weakened-observation mutations. | Connectivity and capture matrix pass; rail behavior remains **indeterminate** until safe coupon mating and waveform capture. HOT0 can become mains-referenced on an energized Rev38 board, so that hookup is outside this milestone. |
| Discharge | Source-locked Rust scenario gate, two replay cases and bench protocol. Twenty-one tests cover independent VD/VB islands, contact/coil faults, thermal stress and restart claims. | Both supplied cases are **indeterminate**. An adopted 450→80 V, 35 s adverse case **rejects** at the VB deadline. Product criteria, actual parts, contact DC life, coil rail and installed fan-off thermal path are still needed. |
| Inverter | Coupled VD/VB and ideal half-bridge/tank model with 17 saved scenario outputs. Nine Rust tests cover conservation, two RC oracles, timestep convergence and stop-horizon failure. | Nine conditional mathematical screens, seven rejected screens and one indeterminate F2-opening case. No component, frequency, physical stop or thermal selection follows from the ideal model. |
| Cooling | Typed Rust package/airflow/fault gate, nine integration tests and one source-lock mutation test. Pins the discharge executable and selection receipt in addition to the earlier topology and interlock interface. | Catalog screens and logical interlock outputs replay. Installed flow, simultaneous losses, chassis support, trip timing and a joined stop capture remain **indeterminate**. |

## Independent implementation review

Correctness and adversarial reviewers independently reproduced a rail-audit hole: the event trace could stay `RESET>AUX_ON>CHECK_OFF` while a mutated row claimed fresh arm and gate eligibility. The audit now pins every named row's state and observation contract, with both early-gate and weakened-observation regression tests.

The correctness review reproduced a requested inverter stop whose declared gate-off occurred after the simulated horizon but received a conditional verdict. The gate now returns **indeterminate** for that schedule, with a regression test.

The adversarial review found that discharge timing used an illustrative `initial_v=390` while stress used `max_v=450`. That could mark a 35 s criterion conditional even though a 450 V bank needs more than 35 s. Deadline timing now starts from the declared maximum for every island; the adverse case rejects. Cooling had pinned only the earlier discharge topology document while independently encoding the candidate resistor values. It now verifies hashes of the executable discharge gate and selection receipt, and a mutation test rejects a changed gate file.

The reviewers also checked the apparent Rev38/inverter permit asymmetry. It matches the present separate PFC and inverter contracts: the shared interlock removes both permissions, while Rev38 authorization applies to PFC. Deciding which Rev38 trips also inhibit the inverter remains a product integration requirement.

## Verification and limits

Focused Rust tests: auxiliary **11/11**, discharge **21/21**, inverter **9/9**, cooling module **1/1** and cooling integration **9/9**. The inverter's saved CSV replays byte for byte. The auxiliary audit passed against an independently generated scratch netlist; Atopile embeds the scratch path in sheet metadata, so the portable check is source SHA-256 plus the exact node map. Rust formatting and `git diff --check` pass.

The full `cargo test -p zapote-thermal --test cooker_envelope` could not resolve uncached dependencies in the restricted network (`zlib-rs 0.6.7` online; `adler2 2.0.1` offline). The cooling module and integration test instead compiled through a focused `rustc` route against the cached `sha2` release artifact. This verifies the new code paths, not the full Cargo dependency graph.

The next advance needs measured Rev38 and inverter interfaces, isolated lab instrumentation, mounted thermal evidence, and an adopted discharge/service rule. Full-board integration and physical qualification remain separate roadmap work.
