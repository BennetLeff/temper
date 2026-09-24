# Parallel Zapote board and characterization review

Date: 2026-09-23. Scope: the next parallel milestone after U1–U3 digital readiness. The home-kitchen Control Freak Home comparison is a functional target; it supplies no electrical rating or physical qualification. The user has no coil/pan or fan article and has not adopted a post-power-off discharge voltage/time criterion.

## Outcomes

| Workstream | Current artifact | Reviewed disposition |
| --- | --- | --- |
| Auxiliary | `zapote/auxiliary/rail-order-fixture-01/candidate/rail-order-fixture.kicad_sch` and routed `.kicad_pcb` | **Lab-only rail-order fixture PCB candidate.** It does not generate HOT or SELV power and must not mate directly to Rev38. Product auxiliary source remains unselected. |
| Programming | `zapote/programming-ui/source-build-01/` and `zapote/programming-ui/evidence/service-board-01/native/service_coupon.kicad_pcb` | **SELV UART0 lab coupon candidate.** Product service access, backfeed prevention, MCU pin ownership, and reset-to-both-stage-stop remain open. ERC/DRC warnings preclude standalone digital acceptance. |
| Rev38 voltage telemetry | `zapote/voltage-sense/rev390-interface-01/README.md` | Isolated architecture selection only; no PCB. Adopt VB/VD voltage envelope, insulation row, HOT/SELV supplies, divider and receiver before capture. Legacy common-return half-bus board cannot attach to Rev38. |
| Discharge | `zapote/discharge/evidence/board-candidate-01/DECISION.md` | Design hold; no product PCB. Adopt discharge criterion and source/energy/part/thermal evidence first. A 24 V coupon would not verify high-voltage DC switching or installed heat. |
| Coil/pan and fan | `zapote/inverter/characterization/` and `zapote/thermal/cooker-envelope/characterization/` | Capture-ready registers and schemas; every physical run remains unmeasured. No generic coupon has a defined termination or approved envelope yet. |

## Independent replay and review finding

- Auxiliary KiCad 10.0.4 ERC: 0 violations. DRC with `--all-track-errors`: 0 violations and 0 unconnected. Fresh KiCad schematic export matched the normalized Atopile netlist at 10 nets, 24 `(reference,pin)` nodes and 13 components. The fixture's own receipt records the source-normalization reason and exact build procedure.
- Programming KiCad 10.0.4 ERC replay: 0 errors and 13 warnings in the coordinator configuration (the saved agent report has 18 warnings, including library-resolution differences). DRC with `--all-track-errors`: 2 `lib_footprint_mismatch` warnings at J1/J2, 0 unconnected. Fresh KiCad schematic export matched the compiled Atopile netlist at 7 nets, 22 pad claims and 7 components. These results are a routed **candidate**, not a warning-free construction release.
- Existing digital gates replayed on the combined branch: discharge 27/27 Rust tests, inverter measurement 17/17 and cooling readiness 6/6. `python3 scripts/regen_derived.py --check` passed after regenerating the plan index. These checks do not measure hardware.
- Independent adversarial review found that the inverter U3 gate requires all measured rows to name one physical article. The early coil-only fixture and a later protected inverter cannot honestly share an article ID. The characterization plan and README now require repeating coil measurements on the integrated article or explicitly revising the cohort contract before transferring early data.

Neither native PCB has been fabricated or powered. No integrated cooker PCB, inverter PCB, accepted auxiliary supply, Rev38 voltage board, or discharge board exists from this milestone. The next physical step is to identify actual coil/pan and fan articles and independently adopt the electrical and service requirements listed in the individual plans.
