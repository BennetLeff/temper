---
title: "Buck Continual Harness - Engineering Validation Plan"
date: 2026-09-09
type: feat
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
product_contract_source: conversation-approved-scope
execution: code
supersedes: docs/plans/2026-09-09-1528-feat-buck-continual-harness-plan.md
---

# Buck Continual Harness - Engineering Validation Plan

## Goal Capsule

This revision governs future work after collection of the currently pinned U1 builder attempt. The original plan remains immutable for that attempt; its outputs are preliminary fixture evidence and must be reconciled to this revision before further dispatch or model trials. Existing U1–U5 IDs retain their meanings; U6–U10 add engineering validation.

Determine whether an agent can place and route Temper's complete nine-component 3.3 V buck, and whether reusable procedures refined during construction improve its performance on reserved layout variants.
The September 9 conversation approves this scope and its comparison of fixed, inherited-frozen, and inherited-updating harnesses.
The user's subsequent correction excludes a new DSL: executable procedures use ordinary code in an isolated standard interpreter.
The existing two-footprint experiments remain independent historical results.
Validate requirements, the existing atopile circuit, supported simulated behavior, and layout quality before admitting the reference to model trials. Define the physical measurement format while keeping hardware explicitly unverified.
Stop model execution on an unqualified engineering reference or fixture, compromised isolation, unmeasurable board, or incomplete transport evidence; retain the unsuccessful attempt.

---

## Product Contract

### Summary

Extend the lab to the complete buck, add a persistent programming workspace and versioned reusable procedures, and run a bounded pilot against an engineering-qualified reference with separate requirements, circuit, simulation, layout, and physical evidence.

### Problem Frame

The current five-operation interface passed three joint C9 placement and two-net routing trials.
It does not yet test complete circuit construction, programmable working state, automatic harness refinement, or transfer to unseen layouts.

### Requirements

**Circuit construction**

- R1. Admit U3, L2, C9–C13, R16, and R17 from the source board, with an explicit reconciliation to `BuckConverter3V3` and its external net obligations.
- R2. Begin construction with all nine functional footprints in a neutral staging arrangement and no functional copper; frozen terminals represent the external connections.
- R3. Permit explicit placement, track/via editing, inspection, and independent checking while preserving footprint/pad/net identity, external terminals, outline, and rules.
- R4. Acceptance requires complete physical connectivity, legal placement, all mandatory native DRC checks, and a frozen buck layout contract with feasible witnesses; R13–R18 govern engineering qualification beyond routing completion.

**Programmable working state and refinement**

- R5. Supply a persistent standard scripting interpreter with ordinary code, structured observations, and callable admitted PCB operations; do not create a DSL or hide a placement/router algorithm inside a primitive.
- R6. A bounded sequential refiner reads the ongoing attempt's trace and updates versioned notes or executable skills while construction retains its board, action history, and remaining budget.
- R7. Every harness revision records its source trajectory, parent version, contents, and application boundary; inherited versions can be restored without erasing intervening evidence.
- R8. Generated code and refinements cannot read witnesses, other trials, credentials, the shelved repository, or evaluator internals, and cannot change acceptance rules or budgets.

**Experiment and evidence**

- R9. Compare a fixed base harness, inherited procedures with refinement disabled, and the same inherited procedures with refinement enabled, holding the model, native operations, task inputs, and total attempt ceilings constant.
- R10. Freeze development/evaluation splits and inherited state before evaluation; each evaluation trial starts with fresh working state and contributes no learning to another trial.
- R11. Preserve every scheduled attempt, actual supplied context, code execution, revision, board action, native report, transport outcome, and resource receipt.
- R12. Report circuit completion, observed refinement effects, and transfer effects separately, including regressions and inconclusive small-sample outcomes.

**Engineering validation**

- R13. Freeze source-backed operating conditions and measurable acceptance limits before declaring the reference qualified or starting model trials.
- R14. Reuse the existing atopile buck as the circuit authority and verify generated circuit/BOM/ratings and exact candidate PCB agreement.
- R15. Qualify the simulation model independently, retain supported scenario evidence, and invalidate reuse whenever a relevant circuit/model/scenario identity changes.
- R16. Evaluate electrical layout quality and presentation quality separately from DRC, with explicit measurements, limits, and uncovered physical behavior.
- R17. Define a provenance-bound bench measurement format; hardware remains unverified throughout this software milestone.
- R18. Expose five separate stage outcomes and reject missing, stale, unsupported, or incomplete mandatory evidence at the shared admission gate.

### Key Decisions

- **Use the complete buck** (session-settled: user-approved — chosen over further two-footprint refinement because the existing task leaves little completion headroom). Governs R1–R4.
- **Refine during an ongoing attempt** (session-settled: user-approved — chosen over between-attempt-only refinement to exercise the papers' continual mechanism). Governs R6, R7, R9.
- **Use ordinary code** (session-settled: user-directed — a custom DSL adds unnecessary language and maintenance burden). Governs R5.

- **Add all five validation stages** (session-settled: user-approved — implement stages 1–4 and the stage-5 measurement format, preserving the original continual-harness comparison). Governs R13–R18.

### Scope Boundaries

This milestone implements an engineering validation workflow for a local PCB experiment. Stages 1–4 and the stage-5 record format are in scope; fabrication, powered measurements, parasitic extraction, and full thermal/EMI qualification are deferred. A qualified benchmark reference is not hardware qualification.
Use the existing Muse Spark Contributor Free route through OpenCode Zen under the previously accepted terms; no paid or alternate-provider fallback is part of this experiment.
Recursive teams, model-weight training, whole-board integration, production board edits, and public publication remain outside this milestone.

---

## Planning Contract

### Key Technical Decisions

- KTD1. Retain `harness-lab/` and its isolated standalone Rust judge; implement new domain judgment in Rust and native KiCad/process glue in Python. Reuse raw native serialization and census-before-connectivity from `routing_native.py`.
- KTD2. Add a full-buck profile alongside the existing profiles, preserving their frozen fixtures and results. Start with two copper layers and an approximately 50 × 40 mm region; exact feasible geometry and numeric rules are frozen during local qualification before model work.
- KTD3. Use an isolated ordinary Python interpreter for model-authored programs, with persistent variables and a small RPC bridge to the same validated PCB actions. Enforce file/process/network access outside Python and qualify denied-access behavior; interpreter import filtering is not a sandbox.
- KTD4. Keep trusted board/evaluator operations in the host process. Generated programs see observations and their own workspace; every nested PCB action passes the same budget, validation, logging, and independent acceptance path as a direct tool call.
- KTD5. Apply refinement at recorded action boundaries with no board reset. A separate sequential invocation of the same model edits only the admitted notes/skill store, and its time counts against the original attempt deadline. Load each applied version into subsequent interpreter use and observations; persisted files alone do not establish reuse. The MCP operation timeout must cover the bounded refinement and native measurement while remaining inside the attempt deadline.
- KTD6. Freeze a small pilot: two development variants and two reserved evaluation variants. Run fixed and updating conditions on development, then three conditions once on each reserved variant. Ten construction attempts is the maximum scheduled pilot; it is not a statistical generalization study.
- KTD7. Each construction attempt has a 20-minute elapsed ceiling and 200 mutating PCB operations, including nested program actions; allow at most three refinement calls, each bounded by 90 seconds and the remaining attempt deadline. Track reported tokens and cost, without claiming an independently verified dollar bill or a hard token ceiling.
- KTD8. All conditions expose the same computation and native operation capabilities. Fixed conditions prohibit changes to reusable inherited artifacts but retain ordinary working computation. Updating conditions may revise the reusable store; each trial begins from its designated immutable initial version.
- KTD9. Choose an inherited development revision only from fully recorded, locally qualified artifacts, preferring a revision associated with complete construction, then lower total elapsed time, then lexical revision identity. If no usable revision is produced, report that failure and do not label the unchanged baseline as learned.

- KTD10. Reuse the existing `BuckConverter3V3` module through an isolated build entry and provenance-bound circuit manifest; keep new domain validation in the standalone Rust judge under KTD1. Governs R13–R14.
- KTD11. Use one trusted evaluator for requirements and stage receipts, recording per-stage and per-requirement outcomes rather than one overall engineering pass. Governs R13, R18.
- KTD12. Qualify exact-device simulation coverage before trusting results; cache schematic evidence by circuit/model/scenario/tool identity and never present it as layout-sensitive. Missing adequate models block scientific qualification. Governs R15.
- KTD13. Strengthen the U1 reference with connected-copper electrical checks and separate presentation metrics grounded in TI guidance. Freeze acceptance before solver results are observed. Governs R16.
- KTD14. Implement the bench schema and synthetic example only; real physical qualification requires later measurements and review. Keep the original three conditions, ten-attempt ceiling, isolation, and trace accounting. Governs R17–R18.

### Paper Alignment

[Prime Agent, §§2.2–2.6](https://arxiv.org/html/2608.23552v1#S2) grounds KTD3–KTD5: retained computation, revisable external state, and explicit accounting.
Its §3.5 specification-exploit example motivates R8 and independently checked board identity.
This milestone implements a single-agent subset of that architecture and does not claim recursive orchestration.

[Continual Harness, §§3.1–3.2 and 4.1](https://arxiv.org/html/2605.09998v1#S3) grounds the live refinement and inherited-frozen/updating comparison.
Board state continues across revisions within an attempt; independent benchmark trials reset intentionally.
The experiment therefore tests online adaptation and cross-variant transfer separately.
The reported capability floor and regressions in §4.4 make a negative result admissible.

### High-Level Technical Design

```mermaid
flowchart TB
    M[Solver model] --> O[Admitted operations]
    M --> P[Isolated persistent Python]
    P --> O
    O --> H[Trusted host and shared budget]
    H --> K[Native KiCad board operations]
    K --> J[Native measurements and Rust judge]
    J --> M
    H --> T[Append-only trajectory]
    T --> R[Sequential refiner]
    R --> V[Versioned notes and skills]
    V --> M
    V --> P
```

```mermaid
sequenceDiagram
    participant S as Solver
    participant H as Host
    participant R as Refiner
    S->>H: Inspect, compute, and edit
    H-->>S: Measured state and findings
    H->>R: Recent trace at eligible boundary
    R->>H: Proposed reusable-state revision
    H->>H: Validate, version, and apply
    H-->>S: Updated artifacts; same board and deadline
    S->>H: Continue and submit
    H->>H: Independent final validation
```

```mermaid
flowchart LR
    A[Requirements frozen] --> B[Atopile circuit reconciled]
    B --> C[Qualified circuit simulation]
    B --> D[Native layout checks and review]
    C --> E[Engineering reference admission]
    D --> E
    E --> F[Bounded model comparison]
    E --> G[Future bench measurements]
```

### Qualification Decisions

Reconcile actual reference/pin/net mappings before fixture admission, including whether enable is tied to the input supply in the admitted design.
Do not invent a separate electrical net to accommodate a fixture terminal.
Freeze input/boot/feedback locality, feedback-to-switching separation, power copper widths, and return connectivity as explicit benchmark constraints supported by native measurements and TI layout guidance.
Numeric geometry proxies are not manufacturer guarantees or evidence of electrical performance.
Every variant needs a passing witness and negative controls; witnesses remain outside solver/refiner access.

### Risks and Dependencies

The local standard interpreter's sandbox and native KiCad 10.0.4 are qualification dependencies.
If an isolation primitive fails on this host, qualify an available standard process/container boundary before continuing; do not substitute an ad hoc safe-eval language.
Transport failures invalidate the affected attempt even if its final board happens to pass.
More components or refinement may exceed the model's useful capacity; preserve the measured outcome without tuning the reserved batch.

---

## Engineering Validation Contract

The user approved these five stages on September 9 after inspecting the full-buck fixture. Implement stages 1–4 and the stage-5 measurement format in this milestone. Powered testing itself remains future work. Keep every stage visible; do not collapse engineering evidence into the existing routing pass flag.

| Stage | Required evidence | Completion meaning |
|---|---|---|
| 1. Requirements | Versioned operating envelope and acceptance limits, each with units, source, and approval state | The intended operating conditions and pass criteria are frozen |
| 2. Circuit | Atopile build evidence, exact parts/values, pin/net mapping, tolerance/rating checks, and agreement with the candidate PCB | The admitted physical circuit matches the checked design |
| 3. Simulation | Qualified model identity, scenario definitions, retained waveforms, numeric measurements, and coverage limits | Supported circuit behaviors meet the frozen requirements |
| 4. Layout | Native connectivity/DRC, electrical geometry checks, manufacturability review, and separate presentation metrics | The saved layout satisfies the admitted layout contract |
| 5. Physical | Bench record format for the same requirements, board revision, instruments, conditions, and raw measurements | Hardware remains unverified until a future physical-validation workflow supplies and reviews measurements |

### Requirements and source ownership

`elec/src/modules.ato::BuckConverter3V3` remains the circuit authority; `PowerManagement` establishes enable and external supply wiring. Build an isolated entry that instantiates that existing module, rather than cloning its component declarations. Use the repository's supported atopile build/export path, pin its version and dependencies, and preserve identity through module paths and pad numbers rather than relying only on reference designators. Do not rewrite the production board.

The requirements manifest must cover nominal/minimum/maximum input voltage, continuous and peak output current with peak duration, output-voltage tolerance, ripple amplitude and measurement bandwidth, startup ramp/overshoot/settling, load-step endpoints/slew/undershoot/overshoot/recovery, ambient temperature, thermal limits, and efficiency at stated operating points. Include capacitor effective capacitance under DC bias/tolerance and inductor current/saturation assumptions. Distinguish product limits from device maximum ratings.

Assign each requirement its verification method and owning stage before qualification. A bench-only requirement keeps its acceptance limit in stage 1 and remains visibly unverified in stage 5; it is not silently counted as a stage-3 success or made an impossible prerequisite for a schematic model. Mandatory simulation coverage must be explicit and cannot be reduced to bypass a missing model. The stages-1–4 admission status always identifies the physical requirements it does not establish.

Known source values include nominal 15 V input, nominal 3.3 V output, and the existing ±5% output assertion. The regulator's 3 A device rating is not automatically the product load requirement. Resolve other values from cited Temper requirements and load budgets; unresolved values remain explicit and block the affected stage. Implementation of the harness can proceed with incomplete requirements, but no qualified reference or model trial can bypass them. Synthetic limits used in software tests must be marked synthetic and cannot become engineering evidence.

An atopile assertion that declares the desired output voltage is a requirement, not a measured regulator response. Reconcile generated netlist/BOM, component source definitions, and the exact saved candidate's pad-net census. A missing value or `?` in the fixture must resolve through an unambiguous provenance-bound source manifest; ambiguous or conflicting identity fails circuit admission.

### Simulation qualification and reuse

Choose a simulator only after verifying a usable model for the exact LMR51430XDDCR variant and the capabilities needed by the requirements. Use a verified vendor-supported route if available; ngspice compatibility, WEBENCH access, and a downloadable transient model are dependencies to establish, not assumed installed capabilities. Retain model source/license, exact bytes, simulator/version/options, and qualification evidence. If no adequate model is available, record a concrete stage-3 blocker and retain completed circuit/layout work; do not substitute another regulator or silently weaken coverage.

`simulation/models/LMR51430_avg.lib` is currently inadmissible: it uses a 0.8 V reference whereas the datasheet specifies 0.6 V nominal. It also lacks switching, enable, startup/protection behavior, and a credible input-power path. Correcting the reference alone cannot qualify transient response or efficiency. Preserve this defect as a negative control. Any approximate model must identify its supported behaviors and be checked against independent datasheet, vendor-reference, or bench evidence within a stated validity envelope; a model's own output is not its qualification oracle.

Run startup, input variation, and load variation scenarios with the pinned BOM, source/load impedances, component tolerances, capacitor effective values/ESR, and inductor DCR. Measure only behaviors supported by the qualified model. Switching ripple requires a switching model; efficiency requires a validated loss/input-power model; EMI, thermal performance, and protection behavior need their own justified evidence. A successful simulator exit, flat waveform, or converged operating point is insufficient. Missing samples, non-finite results, insufficient settling/resolution, unsupported mandatory behavior, and nonconvergence must prevent a pass.

Reuse schematic simulation only when the electrical design, component models, requirement/scenario definitions, simulator settings, and relevant source identities are unchanged. Moving a component does not make a schematic-only simulation layout-sensitive. Each candidate still requires circuit-to-PCB reconciliation. A parasitic simulation additionally binds the exact board hash, stackup, extraction method, and extraction settings; layout edits invalidate it. Parasitic extraction implementation is deferred, and the report must say when it has not been performed.

### Layout quality and reference qualification

Promote the original U1 witness only after it passes this expanded contract. Its existing DRC report establishes a fixture observation, not a validated buck design. A benchmark reference is distinct from fabricated hardware and from a model-generated trial result.

Derive input high-current loop and ground-return checks from actual connected copper, along with input/boot locality, SW-to-inductor routing, output-capacitor return paths, feedback divider locality and sensing isolation, power-path bottleneck width, supported copper/stackup assumptions, and provision for heat spreading. Anchor choices in TI's layout example and datasheet; record which measurements are engineering proxies and which requirements they support. Do not claim loop area, temperature, or EMI compliance from Euclidean component distance alone. Missing measurement capability is indeterminate. Ground-zone support requires actual fill/connectivity and retained copper evidence, not merely a polygon declaration.

Record presentation quality separately: component alignment/orientation, unnecessary routing detours, functional grouping, readable non-overlapping references, and connector/test-point access. Use deterministic metrics where justified and a visible review rubric for subjective judgments; no opaque aesthetic score may override an electrical failure. Missing 3D models are a presentation limitation rather than proof of a missing electrical component. Existing fixture terminal proxies must be labeled as such; actual connector and test-point selection belongs to later fabrication preparation.

Freeze all mandatory layout checks and secondary ranking rules before the pilot. Qualify positives and defect-specific negatives on each variant, including DRC-clean long input return paths, poorly isolated feedback routing, power-trace neck-downs, and unreadable labeling. Choose threshold values from source guidance and feasibility evidence before observing solver performance. Requalification after a contract change invalidates earlier scored comparisons; preserve them as historical results.

### Evidence states and admission

Each stage has `not_run`, `blocked`, `fail`, `pass`, or `indeterminate`, with per-requirement outcomes and a reason. `blocked` means a known missing prerequisite; `indeterminate` means attempted measurement did not produce usable evidence. Unsupported mandatory coverage cannot become `pass` or silently become optional. A stage passes only when all its mandatory checks have current, complete evidence. Substantive review conclusions include reviewer attribution and the cited board/source revision.

The stage receipt records schema version, requirements revision, dependency receipts, source/model/board hashes as applicable, tool identities, command/exit status, timestamp, supported coverage, raw artifact hashes, measurements/units, limits, and findings. Resolve artifacts only under the trusted evidence store, reject path traversal and missing/altered files, and verify dependency identities before reuse. Failed reruns remain in history and supersede a prior success for that exact requested evaluation; changing software, source, or requirements makes affected evidence stale until revalidated.

Keep `routing_complete`, `circuit_validated`, `simulation_validated`, `layout_validated`, and `hardware_validated` distinct. A reference is eligible for the pilot only after stages 1–4 pass and the original fixture/isolation/transport controls pass. Reports must name uncovered physical behavior even for an eligible reference. Stage 5 initially remains `not_run`, displayed as **hardware unverified**. Neither imported sample records nor stages 1–4 may set `hardware_validated`.

All three experiment conditions receive the same approved requirements, circuit manifest, model coverage/limitations, and readable findings. Only the trusted host owns evaluators, simulator invocation, artifact validation, and acceptance limits. Preserve witness secrecy and development/reserved isolation. Reuse qualified circuit-only evidence consistently across conditions; report shared preflight cost separately from per-attempt cost and charge any candidate-specific evaluation against the existing attempt deadline.

### Bench measurement format

Define a versioned schema and an explicitly synthetic example for later bench use. A real record must identify the assembled board revision/BOM and rework, specimen, operator/reviewer, test procedure, supply/load and ambient conditions, instrument/probe identifiers and calibration information, bandwidth/sample settings, raw waveform/measurement artifacts with full hashes, uncertainty where relevant, and per-requirement outcomes. Reserve tests for regulation/ripple, startup, load steps, efficiency, temperature, and switching noise; do not invent measurements. The current milestone validates record structure and provenance completeness only. A future separately authorized bench workflow must evaluate and review real measurements before marking physical validation complete.

### Grounding and limits

- Existing circuit: `elec/src/modules.ato::BuckConverter3V3`, `elec/src/components.ato::LMR51430`.
- Known model defect: `simulation/models/LMR51430_avg.lib`.
- [TI LMR51430 datasheet, revision A](https://www.ti.com/lit/ds/symlink/lmr51430.pdf), §§7.5, 9.2, 9.4: reference voltage, component design, and layout guidance. Pin the document bytes during implementation rather than relying on a changing URL.
- [TI evaluation-module guide](https://www.ti.com/lit/ug/sluuch0/sluuch0.pdf): external layout/measurement reference; its conditions are not automatically the Temper product requirements.
- [Atopile toolchain](https://github.com/atopile/atopile): circuit source/build/constraint role. No integrated simulator capability is assumed.

---

## Implementation Units

Serial builder order: collect/review the existing U1 attempt, then U6 → U7 → U8 → U9 → U2 → U3 → U4 → U10 → U5. If a scientific prerequisite blocks U8, independent software/layout units may continue, but U5 stays blocked. Do not treat the original U1 qualification as engineering acceptance.


### U1. Qualify the full buck environment

- **Requirements:** R1–R4, R8.
- **Files:** `harness-lab/buck_native.py`, `harness-lab/build_buck.py`, `harness-lab/src/buck.rs`, `harness-lab/src/main.rs`, `harness-lab/fixtures/buck-contract.json`, `harness-lab/qualify_buck.py`, `harness-lab/test_buck_boundary.py`.
- **Approach:** Extend the native/Rust boundary under KTD1–KTD2; freeze source mapping, terminals, starts, rules, and protected hashes.
- **Patterns:** `combined_native.py`, `routing_native.py`, `qualify_combined.py`.
- **Test scenarios:** Each witness passes repeated native validation; missing terminal connectivity, wrong raw copper net, moved protected terminal, altered rules, short, clearance error, outside footprint, and DRC-clean locality violation are rejected.
- **Verification:** All admitted variants have independent positive and negative evidence; production board hash remains unchanged.

### U2. Add complete-circuit operations

- **Requirements:** R3, R4, R11. **Dependencies:** U1.
- **Files:** `harness-lab/buck_host.py`, `harness-lab/harness.py`, `harness-lab/test_buck_boundary.py`.
- **Approach:** Provide explicit per-component placement and branched multi-pad copper editing through KTD4, with atomic validation and shared accounting.
- **Test scenarios:** Invalid arguments leave state unchanged; placement leaves existing copper stationary; replacing one net preserves other copper; exhausted/stale requests cannot mutate; a submitted board is independently reloaded and verified.
- **Verification:** A recorded complete construction replays through the public operations and passes the same checker used for model trials.

### U3. Add isolated programmable working state

- **Requirements:** R5, R8, R11. **Dependencies:** U2.
- **Files:** `harness-lab/workspace.py`, `harness-lab/workspace_worker.py`, `harness-lab/test_workspace.py`, `harness-lab/buck_host.py`.
- **Approach:** Apply KTD3–KTD4 using ordinary Python, persistent variables, bounded output/runtime, and audited nested calls.
- **Test scenarios:** Variables persist between calls; an ordinary function composes PCB operations; attempted secret/witness reads, subprocess creation, network access, and writes to protected state fail; infinite execution/output ends within limits; nested edits exhaust the real shared budget.
- **Verification:** Real isolated subprocess controls pass, not just mocked path checks.

### U4. Add versioned live refinement

- **Requirements:** R6–R8, R10, R11. **Dependencies:** U3.
- **Files:** `harness-lab/refinement.py`, `harness-lab/test_refinement.py`, `harness-lab/buck_host.py`, `harness-lab/run_buck_trials.py`.
- **Approach:** Apply KTD5 and KTD8; version complete artifact contents, expose revisions on the next solver boundary, and retain their source windows.
- **Test scenarios:** A revision changes a subsequent skill invocation without resetting board or deadline; frozen artifacts reject edits; malformed/path-escaping revisions are rejected; rollback retains prior history; refiner timeout is recorded and cannot extend the construction budget.
- **Verification:** Scripted end-to-end controls prove revision, reuse, continuation, and rejection semantics before live calls.

### U5. Run and report the bounded comparison

- **Requirements:** R9–R18. **Dependencies:** U1–U4, U6–U10; stages 1–4 must actually pass.
- **Files:** `harness-lab/run_buck_trials.py`, `harness-lab/test_buck_runner.py`, `harness-lab/TRIAL-INPUTS.md`, `harness-lab/BUCK-EXPERIMENT.md`, `harness-lab/BUCK-RESULTS.md`, `harness-lab/README.md`, `harness-lab/evidence/`.
- **Approach:** Enforce the engineering admission gate under KTD10–KTD14, then reuse the serial Zen relay and complete wire audit under KTD6–KTD9; preflight the exact new catalog and payload before development, then freeze inherited state before reserved trials.
- **Test scenarios:** Qualification/source drift blocks launch; no reserved trace enters development or another trial; all requested/served models and tool schemas match; upstream failure ends admission; missing evidence cannot pass; all scheduled trials appear in the report.
- **Verification:** Retained pilot receipts support each stated result, including an honest blocked or negative outcome where a gate prevents further experiments.

### U6. Add requirements and stage evidence

- **Requirements:** R13, R18. **Dependencies:** U1 host collection/review for the serial builder route; this unit does not assume U1 is electrically qualified.
- **Files:** `harness-lab/engineering/requirements.json`, `harness-lab/engineering_host.py`, `harness-lab/src/engineering.rs`, `harness-lab/src/main.rs`, `harness-lab/test_engineering.py`, `harness-lab/BUCK-ENGINEERING.md`.
- **Approach:** Apply KTD10–KTD11 and the Engineering Validation Contract. Implement Rust-owned requirement/state/provenance validation and thin host JSON/process glue. Populate only source-supported limits; keep unresolved requirements visible.
- **Test scenarios:** Missing required limits block admission; synthetic values cannot qualify a reference; incompatible units and non-finite limits fail; stale dependency hashes invalidate prior passes; missing/corrupt artifacts and path traversal are rejected; no evidence yields five non-passing states.
- **Verification:** A complete synthetic receipt chain passes schema/state controls while a clearly labeled real requirements report exposes all outstanding product inputs.

### U7. Validate the existing atopile circuit

- **Requirements:** R14, R18. **Dependencies:** U6.
- **Files:** `harness-lab/engineering/buck.ato`, `harness-lab/engineering/ato.yaml`, `harness-lab/circuit_native.py`, `harness-lab/src/engineering.rs`, `harness-lab/test_circuit_validation.py`, `harness-lab/BUCK-ENGINEERING.md`.
- **Approach:** Apply KTD10 and source ownership above. Resolve the supported standalone build entry and exported BOM/netlist, retain build/version/source receipts, and reconcile all nine functional components plus external-net obligations to native PCB data. Do not duplicate the atopile circuit or add a second Python domain authority.
- **Test scenarios:** The real module exports expected connectivity and component values; wrong regulator pin mapping, changed divider value, unresolvable placeholder, ambiguous renamed reference, insufficient component rating, and mismatched candidate net all fail their intended check; unavailable build tools or unresolved requirements block qualification rather than producing an empty pass.
- **Verification:** The saved reference has a reproducible circuit manifest and candidate agreement report; source or BOM changes invalidate that report and downstream simulation evidence.

### U8. Qualify and run circuit simulation

- **Requirements:** R15, R18. **Dependencies:** U7.
- **Files:** `harness-lab/engineering/models/`, `harness-lab/engineering/scenarios/`, `harness-lab/simulation_host.py`, `harness-lab/src/engineering.rs`, `harness-lab/test_simulation.py`, `harness-lab/BUCK-ENGINEERING.md`.
- **Approach:** Apply KTD12. First establish exact-device model availability, permitted use, supported behaviors, and independent qualification evidence. Then implement bounded simulator execution, waveform retention, Rust measurement/admission checks, and circuit-identity-based reuse. Leave the known legacy model untouched as negative evidence unless a separately evidenced correction is needed; never use it for acceptance as-is.
- **Test scenarios:** The legacy 0.8 V model is rejected against the independent 0.6 V reference; omitted mandatory model behavior blocks admission; timeout/nonconvergence/truncated/non-finite or under-resolved waveforms cannot pass; a passing supported scenario and a deliberately failing requirement produce distinct outcomes; unchanged circuit evidence is reusable across placements but stale BOM/model/settings are rejected; parasitic evidence is invalidated by a changed board hash.
- **Verification:** Retain real qualified-model scenario receipts and waveform plots, or an explicit model/requirements blocker. Simulator plumbing passing software tests does not mark stage 3 passed and cannot unblock U5.

### U9. Qualify an engineering layout reference

- **Requirements:** R4, R16, R18. **Dependencies:** U1, U6, U7; circuit simulation may be independently blocked, but the combined reference cannot qualify until U8 succeeds.
- **Files:** `harness-lab/src/buck.rs`, `harness-lab/buck_native.py`, `harness-lab/qualify_buck.py`, `harness-lab/fixtures/buck-contract.json`, `harness-lab/test_buck_boundary.py`, `harness-lab/BUCK-QUALIFICATION.md`, `harness-lab/evidence/`.
- **Approach:** Apply KTD13. Upgrade the preliminary U1 geometry contract using actual connected-copper measurements and TI grounding. Add explicit presentation review/metrics, improve local reference layouts as needed, and requalify all variants before freezing. Preserve original fixture evidence and do not claim thermal/EMI prediction from layout proxies.
- **Test scenarios:** Each reference passes repeated native checks; DRC-clean bad return paths, feedback interference, and power neck-downs fail their electrical checks; clean geometry with unreadable labels fails mandatory presentation checks where specified; a missing 3D model is reported without changing electrical truth; changed thresholds require a new qualification identity.
- **Verification:** Every variant has an engineering review with current circuit evidence, declared physical limitations, and independently failing controls. Reference PCB screenshots and native boards are reviewable outside the solver context.

### U10. Integrate stage reporting and the bench format

- **Requirements:** R12–R18. **Dependencies:** U2, U6–U9. Blocked upstream scientific qualification permits software controls and report implementation, but not a passing engineering reference or live pilot.
- **Files:** `harness-lab/engineering/bench-record.schema.json`, `harness-lab/engineering/examples/bench-record.synthetic.json`, `harness-lab/buck_host.py`, `harness-lab/run_buck_trials.py`, `harness-lab/test_engineering.py`, `harness-lab/test_buck_runner.py`, `harness-lab/README.md`, `harness-lab/BUCK-RESULTS.md`.
- **Approach:** Apply KTD11 and KTD14. Expose five stage results and per-requirement findings through both agent observations and human reports. Define the future bench format and provenance checks without asserting physical completion. Enforce preflight admission using the same trusted stage evaluator as final reports.
- **Test scenarios:** A DRC-only pass cannot launch the pilot; missing/stale/unsupported circuit simulation blocks launch; schematic-only results cannot be labeled layout simulations; all three conditions receive identical engineering context; malformed or synthetic bench records never mark hardware verified; a full stages-1–4 chain admits the pilot while reporting hardware unverified and all uncovered physical behavior.
- **Verification:** End-to-end scripted controls prove stage separation, provenance invalidation, common evaluation across conditions, and the original context/budget restrictions. User-facing reports distinguish implemented software, measured reference results, scored model results, and future bench work.


---

## Verification Contract

Exercise the stage evaluator end-to-end with good evidence and deliberate wrong-reference, source-drift, missing-waveform, unsupported-model, bad-return-path, and synthetic-bench controls. Require real native/circuit/simulation receipts for stages 1–4; synthetic software tests cannot qualify the reference. No benchmark receipt or DRC-only result can assert electrical or hardware performance.

Run the lab's existing `make check` plus the new focused native qualification and real-process isolation controls.
Preserve all earlier fixture results by rerunning their relevant qualification after changes to shared hosts or measurement paths.
Use KiCad-generated geometry and physical connectivity as external evidence; Rust/Python self-agreement is insufficient.
Record the exact interpreter, KiCad, OpenCode, source, contract, and judge identities before live inference.
Review the completed diff for correctness, isolation, and evidence integrity before local commits are finalized.

## Definition of Done

All five stages have implemented reporting and provenance semantics. Stages 1–4 have independently reviewed reference evidence, or the delivery explicitly remains scientifically blocked with the missing requirement/model/measurement capability identified. The bench schema is validated with synthetic controls and every report continues to show hardware unverified. A blocked delivery is retained progress, not completion of the engineering reference or permission to run U5.

The environment, public operations, programmable workspace, and live refinement pass their named controls.
Every scheduled pilot attempt is retained and classified, or a concrete qualification/operational blocker explains which attempts could not run.
The report distinguishes implemented capability from model behavior actually observed and compares total effort without hiding refinement overhead.
Deliver reviewable local commits and evidence; the existing unpublished branch is not implicitly authorized for publication.

## Execution Appendix: Muse Spark Builder Handoff

### Workspace, route, and authority

Future dispatches must use this revision. The active U1 worker finishes against its original immutable packet; collect its complete diff and receipts before checkpointing this revision. Do not edit that packet, launch a duplicate worker, or advance directly from preliminary U1 to U2. After host review, the next new unit is U6. Preserve prior U1 evidence and require U9 to requalify the engineering contract. Progress and controller identities belong in the external host handoff record.

The canonical checkout is the host-selected Temper worktree, branch `codex/buck-harness-experiment-plan`. The code baseline before this plan's checkpoint is `772f183e2aa7e6457c0c243cbc8165aff1abbe10`. Preserve its earlier unpublished commits and all earlier experiment artifacts. The host records the plan checkpoint and supplies the resulting exact base SHA for each implementation unit; the worker must verify its HEAD against that supplied SHA.

The user selected **OpenCode Zen → Meta Muse Spark 1.3 Contributor Free** as the implementation author as well as the experiment model. Pin the builder to `opencode/muse-spark-1.3-contributor-free`; record the requested model and any actual served-model receipt separately. No paid model, alternate provider, recursive delegation, push, PR, or production-board change is authorized by this handoff.

Use the CE Work cross-model controller and its fixed OpenCode adapter for serial builder units. The controller creates a detached sibling worktree, checkpoints this plan, captures the worker's complete diff, and lets the host verify and integrate it. A builder receives a bounded unit packet and can read tracked repository content in its worktree. It may use source editing and shell/build tools. Workspace and command restrictions in the OpenCode builder adapter are cooperative; a linked worktree is not an OS sandbox. The host owns canonical Git operations, scope review, and authoritative verification. The worker leaves its changes uncommitted and never touches another checkout or another agent's work.

The existing `run_zen_trials.py` configuration is a **solver** configuration: its tool allowlist cannot implement source changes. Do not loosen that configuration to create the builder. Give the builder a separate configuration with the selected model, sharing and unrelated plugins disabled, and no automatic paid/provider fallback. Any configuration or permission limitation must be recorded before dispatch rather than silently dropped.

Builder time is separate from scored construction time. Each builder unit has a two-hour hard ceiling; retain progress if it expires. That ceiling does not replace the 20-minute per-trial limit in KTD7.

### Required context and installed tools

Read the root `AGENTS.md` and any applicable nested instructions, then the active unit and its cited requirements/decisions. Read these existing patterns as needed:

- `harness-lab/README.md`, `TRIAL-INPUTS.md`, `COMBINED-EXPERIMENT.md`, `COMBINED-RESULTS.md`, and `VALIDATOR-CONTROLS.md` for actual scope and historical controls.
- `harness.py`, `native.py`, `routing_native.py`, `combined_native.py`, `routing_host.py`, `combined_host.py`, `qualify_combined.py`, `src/main.rs`, and `src/routing.rs` for the native boundary and judge.
- `run_zen_trials.py` and `test_zen_runner.py` for the fixed provider, full-stream accounting, and restricted solver runtime. Discover additional tests by imports rather than assuming this list is exhaustive.
- `elec/src/modules.ato` (`BuckConverter3V3` and `PowerManagement`) and `pcb/temper.kicad_pcb` as read-only circuit sources.
- `docs/solutions/best-practices/three-silent-failures-measurement-pipeline-2026-07-07.md` and root guidance on raw KiCad serialization, rotation oracles, shared Cargo output, and measurement failures.
- The two papers linked under Paper Alignment and TI's [LMR51430 datasheet, layout section](https://www.ti.com/lit/ds/symlink/lmr51430.pdf). Record source versions in fixture provenance; unavailable references are reported rather than reconstructed from memory.

Host paths observed during planning: OpenCode `/Users/bennet/.opencode/bin/opencode`; KiCad CLI `/opt/homebrew/bin/kicad-cli`; pcbnew Python `/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3.9`; Ruff `/Users/bennet/Miniforge3/bin/ruff`. Verify availability/version at execution. The lab Makefile supplies the shared Cargo target directory; this independent Rust binary is not a pyo3 extension. Do not rebuild production packages or mutate global environments.

Baseline checks, run from the worker's own `harness-lab/` directory:

```sh
make build
make check
```

Use fresh output directories for native qualification. A native DRC permission failure or crash is indeterminate; return its command and log for host execution under the existing permission boundary. Never substitute an empty DRC report. The host must distinguish a sandbox denial from a missing KiCad capability.

### Fixture decisions and qualification authority

Preserve the actual source mapping below and verify it again before extraction. U3 enable is tied to +15V in both the schematic and board; there is no separate enable net. Use three protected external terminals: VIN on +15V, GND on gnd, and VOUT on +3V3.

| Net | Functional pads |
|---|---|
| +15V | C9.1, U3.3, U3.5 |
| gnd | C9.2, C11.2, C12.2, C13.2, R17.2, U3.1 |
| sw | U3.2, C10.2, L2.1 |
| boot | U3.6, C10.1 |
| fb | U3.4, R16.2, R17.1 |
| +3V3 | L2.2, C11.1, C12.1, C13.1, R16.1 |

Freeze a versioned contract containing full source/fixture/context hashes, native version, pad census, protected terminal poses, outline, supported layers, allowed copper kinds, connectivity obligations, and named numerical layout checks. Do not inherit the old judge's two-footprint census, intentional U3.5 disconnection, one-open-connection allowance, or fixed ten-edit budget. Complete construction permits zero open required connections.

The builder may determine exact terminal poses, neutral staging poses, four variant geometries, and numerical engineering proxies during U1 qualification. Start with two copper layers and a 50 × 40 mm region. Use two development and two reserved variants with meaningful terminal-access or region differences; label their split before model trials. Every choice requires a passing native witness and independently failing controls. Record why each locality/separation/width threshold was chosen; distinguish benchmark proxies from TI requirements. This is explicit design authority before the contract is frozen, not permission to tune constraints after observing model performance.

Measure input-capacitor and bootstrap locality, output-capacitor/inductor locality, feedback-resistor locality and separation from switching copper, minimum power-copper widths, and connected local ground returns. Use native geometry; arbitrary-angle checks must include an asymmetric non-orthogonal oracle case. A declaration that a pad belongs to gnd does not prove a local return path. Explicit ground pours are allowed, with the model supplying layer and polygon and KiCad supplying normal zone filling; no hidden routing or placement search is allowed. Inventory saved copper nets before connectivity rebuilding can propagate assignments.

Every witness must pass three fresh native evaluations; keep the full reports. Each named negative control must fail for its intended defect, not merely fail for some unrelated reason. A malformed/missing report must be indeterminate, never pass. If a complete witness cannot satisfy the proposed contract, investigate before freezing it and document the outcome; do not run or score a model against an unqualified fixture.

### Stable public operation contract

U1 establishes the measured JSON/contract schema; U2 implements these ordinary tool calls. Publish their exact JSON schemas and examples before U3. All arguments are finite values with unknown keys rejected; invalid arguments leave the board unchanged. Units are millimetres and KiCad degrees.

| Operation | Arguments and behavior |
|---|---|
| `inspect` / `check` | No arguments. Return saved geometry, constraints, connectivity, DRC findings, revision identity, and remaining budgets; `check` performs independent native validation. |
| `place` | `reference`, `x_mm`, `y_mm`, `angle_deg`; move one of the nine functional footprints only. Copper stays stationary. Admit 0/90/180/270 initially. |
| `replace_copper` | `net`, `segments`, `vias`, `zones`; atomically replace all mutable copper for that one admitted net, preserving other nets. An empty set removes that net's copper. |
| `execute` | `code`; execute ordinary Python with persistent working variables, bounded output, and a `pcb.call(operation, arguments)` bridge to the same host operations. It cannot recursively call `execute`. |

Each segment has `start_mm`, `end_mm`, `layer`, and `width_mm`; each via has `position_mm`, `diameter_mm`, and `drill_mm` spanning the two admitted copper layers. Each zone has `layer` and `outline_mm` vertices, with native filling and frozen clearance/connection settings. Only gnd zones are admitted initially. Freeze per-call object and output limits in the public schema before live trials. One successful `place` or `replace_copper` consumes one mutation; every nested call consumes the same budget. Checks and computation still consume the shared elapsed deadline. Tool responses and final scoring use the same judge.

### Runtime and live refinement decisions

Use a persistent standard Python subprocess. On this macOS host, first qualify `/usr/bin/sandbox-exec` with an explicit deny-by-default profile that admits the Python runtime and dedicated working directory, passes no credentials, and denies other files, network, and new subprocesses. A real denial test is required for each restriction. If unavailable, use an available container boundary and rerun the same tests; do not replace it with import filtering, an AST whitelist, or a DSL. An unavailable OS/container boundary blocks U3 and all model trials, while retaining completed U1/U2 work.

The host communicates over a bounded RPC channel; Python code cannot supply a raw board path or evaluator command. Cap each `execute` at 120 elapsed seconds and 64 KiB returned output, inside the unchanged attempt deadline. Exceeding a limit terminates the worker, records loss of working state, and ends the attempt as indeterminate. Host actions already completed remain in the trace. Test infinite computation, output flooding, malformed RPC, and nested budget exhaustion using real processes.

Reusable artifacts are `notes.md` and `skills.py`, initially an explicitly versioned minimal base. Working variables/scratch code are separate. In updating conditions, trigger refinement after the 20th, 60th, and 100th successful mutation, after its native measurement, unless construction has passed or the deadline has expired. Apply a proposal only at that boundary. Freeze this schedule for all live trials.

Each refiner call receives task/tool instructions, current notes/skills, current observation, and the last 20 operation request/response pairs from its own trial. Bound the serialized input to 128 KiB by removing oldest complete pairs, recording exactly what was supplied; an oversized indispensable input skips refinement with a receipt. It returns complete replacement contents for those two artifacts through a structured update tool, at most 64 KiB combined. It receives no board editing, shell, repository, witness, other-trial, or provider-switching tools.

Record parent and child hashes, contents, source window, model/transport evidence, elapsed time, and application boundary. Validate syntax/path/size, then load the new skill module in the isolated worker under a new revision namespace while preserving ordinary working variables. Calls through the current `skills` binding must use the applied revision; retained aliases remain attributed to their old revision. Syntax validation is not security validation. Artifact parse failures/timeouts retain the old revision and consume time. Transport-integrity failures follow the plan's indeterminate-attempt rule. The solver's next observation exposes the revision and its notes. MCP calls must allow the 120-second execution plus a bounded 90-second refinement and native checks, but never exceed the shared remaining deadline.

### Checkpoints and command interfaces to implement

The commands below are required deliverable interfaces; they do not all exist yet. Run serially from the checkout root and capture argv, working directory, source/contract/binary hashes, exit status, logs, and machine-readable receipts. Qualification and preflight commands must exit nonzero on incomplete evidence. A successfully recorded scored failure is a valid experimental result and must not be silently retried.

| Stage | Command / required evidence before advancing |
|---|---|
| U1: fixture and judge | `python3 harness-lab/qualify_buck.py <fresh-output>` produces `qualification.json` for all four variants, three passing witness checks each, intended negative-control results, protected-state checks, and unchanged production-board digest. Run `make -C harness-lab build check` as well. Stop the first builder unit here. Collect it as preliminary fixture work; U6–U10 must precede any U5 trial. |
| U2: operations | `python3 -m unittest discover -s harness-lab -p 'test_buck_boundary.py'` plus qualification proves atomic operations, stationary copper on placement, shared budgets, and a complete witness replay through public operations. |
| U3: ordinary Python | `python3 -m unittest discover -s harness-lab -p 'test_workspace.py'` proves persistence, composed PCB edits, real denied access, and process/output limits. |
| U4: refinement | `python3 -m unittest discover -s harness-lab -p 'test_refinement.py'` proves changed skill behavior, continuing board/deadline, frozen conditions, failure handling, and retained history. No live refinement is needed to establish these controls. |
| U6–U10: engineering admission | Implement `python3 harness-lab/engineering_host.py <fresh-output>` to produce `engineering.json` and hashed raw artifacts, returning nonzero if stages 1–4 are incomplete. This command reports stage 5 as hardware unverified. A script-only success cannot replace the unit-specific evidence above. |
| U5: preflight | `python3 harness-lab/run_buck_trials.py <fresh-output> --phase preflight --qualification <qualification.json> --engineering <engineering.json>` uses the exact trial configuration in inspection-only mode and records model/tool/context identities. |
| U5: development | `python3 harness-lab/run_buck_trials.py <fresh-output> --phase development --qualification <qualification.json> --engineering <engineering.json> --preflight-receipt <results.json>` runs exactly four declared attempts and produces a frozen inherited revision manifest or an explicit no-usable-revision outcome. |
| U5: evaluation | `python3 harness-lab/run_buck_trials.py <fresh-output> --phase evaluation --qualification <qualification.json> --engineering <engineering.json> --preflight-receipt <results.json> --inheritance <inheritance.json>` runs exactly six declared attempts, one per reserved variant/condition. Refuse launch if no usable inherited revision exists. |

The host independently reviews and verifies each unit before dispatching its successor. U1 delivery includes native evidence and exact rerun instructions; a worker's claim of success alone cannot advance the experiment. Regression qualification for earlier profiles is required whenever their shared paths change. U1's expected file scope also includes generated `harness-lab/fixtures/buck/**`, new `harness-lab/evidence/buck-qualification*` receipts/archives, a focused `harness-lab/BUCK-QUALIFICATION.md`, and minimal `harness-lab/Makefile` changes needed for its checks. Existing frozen fixture/evidence files are not editable. Keep temporary native output under ignored `harness-lab/runs/` and retain a compact, reproducible committed evidence artifact.

### Context separation, receipts, and recovery

Never reuse the builder's conversation, working directory, OpenCode session, or notes as solver/refiner context. Builders may know witnesses; solvers/refiners may not. Each scored attempt uses fresh isolated OpenCode state and interpreter state. Only the explicit frozen inherited artifact manifest crosses trial boundaries; neither development transcripts nor reserved-trial outputs do. The developer model and the solver may have the same model identity without sharing a session.

Keep a durable host run receipt outside this plan: canonical/base SHA, plan digest, controller run/attempt/job identifiers, builder model receipts, changed paths, verification results, and next eligible stage. Keep builder transcripts separate from experiment trace archives. Redact credential-bearing transport headers while retaining model requests/responses. Trial receipts also include conditions, variant/revision hashes, all actions/revisions, native reports, elapsed time, supplied token/cost reports, and pass/fail/indeterminate classification.

On interruption, inspect the existing controller run and worker job before launching anything. Resume or collect that job; do not create a duplicate builder. A terminal failed builder retains its diff/logs for recovery. An interrupted scored attempt remains recorded as indeterminate and consumes its declared slot; do not restart it with a fresh deadline or quietly add a replacement. Future exploratory retries require a separately labelled batch outside this pilot.

An evidence-backed blocker names the failed command/control, retained artifacts, affected stage, and the exact capability or decision needed to continue. Never bypass a qualification failure, loosen rules after scoring begins, fabricate a pass, or label the unchanged baseline as learned. Final delivery distinguishes completed implementation units from live trials actually executed.
