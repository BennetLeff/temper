# Power-entry decision and qualification handoff

Date: 2026-09-18. Based on repository revision `59aedee4f` and the retained
campaign evidence linked below. This document supersedes the priorities in
`loss-budget/DECISION.md` and is the current entry point for this work.

**Decision milestone complete: choose the next design direction and define its
qualification work. Protection coordination remains UNESTABLISHED; hardware
qualification remains NOT PERFORMED.** This is a design handoff, not a fabrication
release. The passive baseline is unchanged. The separate [active-rectifier
construction checkpoint](active-rectifier/README.md) now contains the active
bridge and F2 proposal in authored source and routed CAD. Its [active Rust
integration](active-rectifier/RUST-INTEGRATION.md) now runs; three package-spacing
findings, fuse mechanical fit and Q1–Q5 qualification remain open.

## 1. Decisions made

| Area | Decision for the next revision | Basis and limit |
| --- | --- | --- |
| Rectifier | Advance TEA2209T/1 with four IPW60R017C7 as the preferred experimental replacement for GBJ2510-F. Retain the passive board as the comparison baseline. | AR-VERIFY supports an approximately 20 W nominal typical conduction opportunity, not a guaranteed net saving or completed qualification. Do not apply passive-bridge surge survival figures to these MOSFETs. |
| Gate bias | Use 220 nF as the bootstrap design target carried from AR-VERIFY. Select the exact capacitor and verify effective capacitance, tolerance, leakage and gate-charge corners during schematic implementation. | The retained low gate-voltage corner uses typical gate charge; it is conditional, not a guaranteed minimum. |
| Boost stage | Retain STW65N65DM2AG, UCC28180D and the 10 Ω external gate resistor as the baseline. | The independent switching-model discrepancy remains a measurement question. No additional device/frequency campaign before evidence changes the choice. |
| Internal bus fault | Carry Mersen A70QS50-14F as the preferred F2 application-review candidate, in series between the boost diode cathode and the capacitor bank. | Relevant manufacturer capacitor-discharge guidance exists. Exact application limits, clearing and withstand coordination are unestablished. Holder selection and its DC/thermal ratings remain part of the ECO. |
| Line fault | Retain F1 only as an unqualified baseline component; review its interruption rating and total clearing against the actual prospective line fault. | F2 does not replace F1. No existing record demonstrates F1 coordination with either bridge. |
| Differential surge | Retain V150LA10AP as the candidate L–N clamp under the adopted 1 kV differential target. | The loaded calculation supports further evaluation. Its scaled curve is a sensitivity, not a maximum characteristic; its generator is not a verified combination-wave equivalent. |
| Common-mode surge | Pursue insulation/return-path withstand under the adopted 2 kV common-mode target. Do not add a PE clamp merely because the L–N MOV does not clamp common mode. | Evaluate the actual PFC board and the connected assembly. No withstand or compliance pass is claimed. |
| Cooling | Keep assembly cooling explicit in qualification. Do not transfer the GBJ heatsink result to four MOSFETs or credit unmeasured interface resistance/airflow. | The active-bridge thermal result is conditional on its assumed assembly. |

These decisions end the architecture search for this milestone. Reopen a choice
only when the qualification evidence below rules it out or identifies a material
benefit. The nominal saving is sufficient to justify the next experiment; it is
not a reason to waive its fault or surge tests.

## 2. Exact baseline and circuit boundaries

The assessed unit is [the shunt-repair PCB](shunt-repair/candidate/section.kicad_pcb),
not `pcb/temper.kicad_pcb`:

| Input | SHA-256 |
| --- | --- |
| `shunt-repair/candidate/section.kicad_pcb` | `34e6fba9e6d323d795bba5bfe7ddfbcb5d158630cd2eb8cf95253b8e0263b2b9` |
| `shunt-repair/candidate/section.kicad_sch` | `49db3ee4e2d79f08d524b92457764098f9dc051b17746729cfb1460bbde4d3a9` |

The [retained fault netlist](loss-budget/campaign/runs/2026-09-17-pfc-campaign/AR-FAULT/attempt-001/raw/netlist_fault_loop.json)
and saved PCB agree on these boundaries:

- U9 source, capacitor negatives and U12.1 share `PFC_BUS_MINUS`.
- U12.2 is on `minus`, the rectifier-side return. U12 is outside the internal
  capacitor–U10–U9 discharge loop.
- U10 cathode is on `PFC_BUS_PLUS_390V`; its anodes and U9 drain are on `a1`.
- U41 is `VY1102M31Y5UQ63V0`, authored as 1 nF Y1, between `PFC_BUS_MINUS`
  and `PE_CHASSIS`. The prior 2.2 nF Y2 / 5.6 nF doubler-midpoint description
  belongs to another design and cannot justify this board's common-mode result.
- All HOT bias/permit/control interfaces must be included when assessing the
  installed common-mode path. This board alone does not define a complete SELV
  isolation barrier or prove a completed hipot test.

The bank's approximately 179.24 J at 400 V uses nominal 2240.47 µF. Qualification
must include capacitance tolerance, maximum credible bus voltage and operating
temperature; this nominal energy is not the maximum exposure.

## 3. Proposed F2 topology and fault cases

During the ECO, split the present positive-bus net at U10's cathode. Assign a new
diode-side net and place F2 between it and the bank-positive net. Keep the bank,
output, discharge network and intended bank-voltage sensing on the bank side.
Audit every branch on the old net; a drawing of F2 is insufficient if copper or a
parallel connection bypasses it. Reassess diode-side overvoltage and controller
behavior after F2 opens, including loss of feedback and continued mains drive.

For the proposed topology, the stored-energy fault path is:

```text
bank+ -> F2 -> U10 failed-short -> a1 -> U9 -> PFC_BUS_MINUS -> bank−
```

Neither U12 nor F1 is in that loop. F2 is a proposed interruption location, not
demonstrated interruption. The capacitor bank remains charged after F2 opens and
still requires its own discharge and access provisions.

| Fault scenario | What conducts / blocks | Credited protection today |
| --- | --- | --- |
| U9 failed-short; U10 healthy | Line-fed current passes through the rectifier, inductor, U9 and U12; U10 blocks the bank's reverse discharge. | F1 is in the line path; clearing and bridge survival unestablished. F2 does not interrupt this path. |
| U10 failed-short; U9 healthy/on | Bank current flows in the internal loop until interrupted or U9 turns off. | No shutdown credit: a usable detection signal, latency and U9 turn-off survival have not been demonstrated. U12 is blind to this loop. |
| U10 failed-short; U9 failed-short | The internal loop remains conductive regardless of gate commands. | Proposed F2 is in the loop; its coordination is unestablished. |
| Rectifier gates disabled | The active rectifier may still conduct through body diodes. | Disabling TEA2209T is not a mains disconnect or fault interrupter. |

## 4. Finite qualification work packages

Each row ends with a retained answer or an explicit unresolved dependency. Do not
launch another model sweep merely because a source is missing. A negative result
changes the named design choice; a missing result keeps the affected release gate
open. Work on other cooker units can continue.

| ID / owner role | Work and exact output | Completion evidence / consequence |
| --- | --- | --- |
| Q1 — component applications engineer | Submit the corrected Mersen packet and obtain the time-constant definition, capacitor-discharge current limit, minimum breaking current and applicable total clearing/let-through data for A70QS50-14F. Include actual voltage/energy corners and normal/startup RMS duty in the application review. | Retained manufacturer response tied to exact part and application conditions, or an explicit refusal/unsupported use. If unsuitable, request their supported alternative before opening a new parts sweep. |
| Q2 — power/protection engineer and test lab | Coordinate both line and internal faults. Establish prospective line fault conditions; characterize defensible R/L and failed-device scenarios; use applicable clearing data and bank/copper/device withstand. Include high-impedance faults, interrupted-arc behavior, enclosure containment and maximum bus energy. | Reviewed coordination report plus required physical tests. Select or replace F1/F2 and holders accordingly. No AC I²t-to-capacitor-discharge substitution; no reliance on normal Rds(on) for a destructive short. A specimen measurement alone does not bound production variation. |
| Q3 — EMC engineer and lab | Test the differential arrangement with a calibrated combination-wave source and the adopted coupling network. Include mains phase/polarity, component variation, wiring overshoot and all relevant controller/MOSFET terminal voltages. | Record applied and loaded waveforms, MOV stress, pin stresses, post-test function and damage inspection against the adopted criterion and each applicable rating. The present 1.2/50 source plus fixed resistor cannot supply this release evidence. |
| Q4 — isolation/EMC engineer | Resolve the common-mode path using U41 and the actual connected supplies, controls, PE and enclosure. Confirm exact capacitor approvals/impulse requirements and the installed barrier; determine current distribution and test both polarities/modes. | Review and test record for the real assembly. A catalog Y classification or an AC hipot requirement alone does not demonstrate system surge withstand. Change the clamp/isolation architecture only if this evaluation requires it. |
| Q5 — power electronics engineer | Qualify active-bridge commutation, startup/precharge, brownout, gate bias and bootstrap corners; confirm RMS fuse loading including startup and hot derating. Measure thermal behavior and loss using the real interfaces and airflow. Use the retained switching-test proposal for the boost-switch uncertainty. | Waveforms, loss/temperature results and fault behavior on the exact assembly, with a calibrated setup. If the active bridge offers no useful net saving or cannot be protected, retain the passive baseline and its required cooling. |
| Q6 — CAD owner | Implement the selected revision through Atopile → native schematic → agent placement/routing → existing Rust and native validators. Include exact MPNs, fuse holders, pin mappings, HOT interfaces, F2 opening behavior and enclosure/clearance constraints. | Source/native parity, fresh native ERC/DRC and Rust reports on saved bytes, reviewed renders and updated BOM/manifest. CAD completion does not close Q1–Q5. Prototype test release requires the responsible engineer's approved test arrangement. |

Sequence: Q1 and assembly definition for Q4 can proceed now. Q2 uses Q1's actual
application limits; Q6 may develop an isolated candidate while those answers are
pending, but must not freeze a qualified protection design. Q3/Q5 physical tests
follow an approved prototype/test setup. Confirm the applicable market/product
standard and precise test details with the lab before using results for compliance.

The [manufacturer handoff](qualification/MANUFACTURER-HANDOFF.md) is prepared and
unsent. No outreach, purchase, fabrication or powered operation is implied by this
document.

## 5. What is closed and what remains open

Closed here: architecture priority, candidate protection location/part, provisional
common-mode approach, current board identity, external questions and qualification
deliverables. No further bridge V–F measurement, frequency sweep, generic evidence
schema work or checker expansion is scheduled.

Still open: protection coordination, exact next-revision schematic/layout/BOM,
prototype testing, installed cooling, full assembly integration and compliance.
Existing modeled loss/surge figures remain conditional. The
[harness freeze](loss-budget/campaign/ARC-SUMMARY.md#10-harness-development-is-frozen-2026-09-18)
stands. Do not reopen it for the documentation corrections made in this closeout.

## 6. Evidence and verification boundary

- [Campaign arc and freeze](loss-budget/campaign/ARC-SUMMARY.md).
- [AR-VERIFY result](loss-budget/campaign/runs/2026-09-17-pfc-campaign/AR-VERIFY/attempt-001/result.json): candidate gate/thermal/loss calculations, not hardware qualification.
- [Mersen application inquiry](loss-budget/campaign/runs/2026-09-17-pfc-campaign/AR-MERSEN/manufacturer-packet/A70QS50-14F-application-review.md): estimates, screening and unanswered application conditions.
- [Surge calculation and limitations](surge/README.md) and [adopted contract](../../docs/specs/SURGE_CONTRACT.md).
- [Shunt-repair checkpoint](shunt-repair/README.md): historical native/Rust evidence. No fresh CAD pass is claimed in this documentation closeout; the saved board was not changed.
- [Boost switching measurement proposal](loss-budget/campaign/PHYSICAL-TEST-PLAN.md).

This handoff consolidates existing evidence; it neither promotes an electrical
claim nor counts as a validated campaign attempt. The historical numerical
attempts, ledgers, manifests and receipts remain historical records.

Closeout verification: the saved PCB/schematic hashes above matched; local
Markdown file targets resolved; both edited Python files parsed. The manufacturer
packet was regenerated from its corrected prose template and its six numerical
oracle checks passed (largest relative error 8.31e-4). Its representative-case
JSON stayed byte-identical. The surge script reproduced the retained values with
the new screening labels. No Rust/harness code, CAD or BOM was changed, and no
fresh native/ERC/DRC or physical qualification result is asserted.
