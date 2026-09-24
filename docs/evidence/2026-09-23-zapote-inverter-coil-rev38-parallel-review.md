# Inverter, cookware, and Rev38 parallel milestone review

Date: 2026-09-23. Integrated branch: `codex/zapote-next-milestone-integrated-20260923`, based on `8b0a729600873c4e8e535bd614118d979cb38ec2`. This is a digital engineering review, with no purchased articles, inverter PCB, energized test, or appliance qualification.

## Combined decision

The three tracks agree on **a conditional VB_BANK/HOT0 half-bridge investigation**, a physical coil/pan measurement campaign, and a Rev38 source/limit freeze request. They do not justify selecting a switch, tank capacitor, local bus capacitor, PWM frequency window, discharge topology, or product PCB yet. The no-pan, synthetic weak-coupling, charged-bank restart, and F2-open states must remain in the candidate set even if a later usage model assigns them low probability.

| Track | Reviewable result | Decision it supports | Still open |
| --- | --- | --- | --- |
| Inverter | [U2 candidate screen](../../zapote/inverter/U2-CANDIDATE-SCREEN.md), Rust [matrix](../../zapote/inverter/evidence/candidate_matrix.rs), and [restart fixtures](../../zapote/inverter/evidence/candidate-restart-cases.csv) | Reject treating 44–50 kHz, historical IKW40N120H3, or 3 × CDE 942C as selected. A 144-row paired L/R screen has 16 overlaps with the provisional 45 A sine-peak marker; the charged VB bank still drives an improperly enabled bridge when F2 is open. | Measured load and source waveforms, gate/current-zero timing, bank-side failed-short containment, switch/cap/connector thermal limits. |
| Coil and cookware | [Reference-article intake packet](../../zapote/inverter/evidence/intake-2026-09-23/README.md) and [nine planned states](../../zapote/inverter/evidence/intake-2026-09-23/planned-cases.tsv) | Acquire the Infineon kit as a **reference coil assembly**, with an identified cast-iron pan and two stainless comparison pans; measure joint complex impedance on one frozen fixture. | Article receipt, actual gap/bracket, approved instrument limits, repeatability, hot and powered captures. The three pans are a coverage cohort, not a population distribution. |
| Rev38 / discharge | [Source and energy handoff](../../zapote/integration/evidence/rev38-interface-2026-09-23/README.md) | Keep VD, VB, HOT0, SELV and any detached inverter capacitor distinct. The active Rev38 source has evolved beyond the committed snapshot, including an off-board F2 candidate. F2 cannot interrupt a direct VB-bank-to-bridge short. | Frozen Rev38 source and native endpoints; separate allowable VD/VB and source envelopes; adopted voltage/time/access rule; AUX and dual-stage stop evidence. |

## Cross-track reconciliation

- The inverter matrix's 390 V point is a nominal-intent sensitivity, and 330 V is a sag probe. Rev38 has not supplied a permissible VB maximum, minimum loaded VB, ripple, or source impedance. A 450 V capacitor nameplate is only a rating-edge screen; the conditional 500 V F2-open VD case is not a VB operating case.
- A 120 V, 15 A input has an 1800 VA apparent-power ceiling before power factor and conversion loss. Neither the matrix's high-power stiff-bus point nor a 1.8 kW delivered cooking claim is a sustained, source-qualified condition. The installed inlet/fuse/cord/branch compatibility remains unresolved.
- The Rev38 bank's nominal 2240 µF holds about 170 J at 390 V. F2 is upstream of it; inverter PERMIT and PFC gate disable do not remove its energy. The local VB commutation capacitor, any detached island, and bank-side failed-short path must be returned to discharge and cooling before layout.
- The series tank capacitor's initial voltage is not established by steady-state VB/2 bias. In the illustrative 2 ms restart fixture, changing its initial voltage to −195 V raises modeled tank peak from about 67 A to 72 A. This is a screening result with ideal devices and source, not a validated trip or startup limit.
- The historical 34 V within 60 s discharge target is only a feasibility scenario. The applicable product/access rule and test method have not been adopted; no discharge board is released. The three-track work cannot freeze that requirement on behalf of a product safety authority.

## Verification and next gate

The coordinator cherry-picked the three disjoint agent commits (`23610cac2`, `b51cf3d7a`, `1542b43ea`) into this branch, inspected the documents and model, replayed the 144-row matrix and five restart fixtures against their saved CSVs, and ran four Rust matrix tests, `rustfmt --check`, `git diff --check`, and the cited source SHA-256 comparisons. The matrix yielded 16 provisional OCP overlaps and 26 historical capacitor-current proxy overlaps. These are repeated synthetic cases, **not likelihoods or part rejection rates**.

Next, obtain and identify the coil/pan articles and fixture; publish one frozen Rev38 source and measured or independently bounded VB/source/stop envelope; adopt the product-specific service voltage/time/access decision; then select and draw an exact inverter plus discharge interface. Construction acceptance requires native schematic/PCB checks and source locks on the selected circuit. Powered and assembled cooker qualification remains a separate later milestone.
