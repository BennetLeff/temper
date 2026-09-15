# Zapote project instructions

Zapote is a project boundary inside Temper, not an isolated checkout.

- Keep Temper's product sources in place: `pcb/`, `elec/`, `firmware/`,
  `simulation/`, `components/`, and `datasheets/` remain shared inputs.
  Existing packages and harness code are donors: copy needed Rust code and
  tests into `zapote/packages/` with the policy in `ARCHITECTURE.md`.
  Do not retain runtime dependencies on donor packages.
- Do not move, delete, or duplicate `harness-lab/` during the setup phase.
- Add new harness behavior under `zapote/` only after its contract and
  evidence path are defined.
- Prioritize the board passing the Rust validation suite in `VALIDATION.md`.
  Keep the working Python/KiCad adapter and host for now; thin glue to Rust is
  allowed. New engineering rules/tests are Rust. Defer Python replacement,
  Rust IPC work and any editor rewrite; they are not milestone dependencies.
- The agent chooses placements and routing paths. Do not rebuild or invoke
  placer/router algorithms. Expose explicit edits and reusable validators.
- Preserve full local evidence for every run. External telemetry may carry
  authorized raw conversations and PCB artifacts, but transport credentials
  must never enter payload data.
- A Zapote run must identify its source revision, fixture/input hashes,
  runtime, model/provider, and final authoritative result.
- Never use `git stash` in this repository.

The repository-level `AGENTS.md` remains authoritative for code generation,
DRC measurement, extension rebuilding, and validation gates.

## Distilled Temper learnings

These are the operating conclusions Zapote should apply by default. The linked
documents contain the incident details and the evidence behind each rule.

### Truth, source, and validation

- Rust owns engineering rule implementation and verdicts. Python may transport
  inputs/results and call native KiCad, but must not duplicate rule logic.
  When implementations disagree, verify the Rust with production-shaped inputs
  and an independent oracle. Legacy retirement requires a separate consumer
  audit; Rust/Python agreement alone does not prove correctness.
- The validator's truth function is the acceptance authority. Audits must
  re-run that truth function rather than rely on a cheaper proxy. Preserve
  findings at their real granularity (especially net pair and layer), and fail
  closed on malformed or missing evidence instead of treating it as an empty
  success.
- Test external schemas with captured or real outputs. Invented fixtures that
  resemble a CLI/API response can validate the wrong field names, nesting, or
  semantics.
- Treat generated files and installed extensions as evidence-bearing outputs:
  regenerate or rebuild them, then verify freshness immediately before any
  measurement or claim.

### Measurement discipline

- A measurement is only as trustworthy as its apparatus. For DRC, regenerate
  the rules, use the complete KiCad sidecar/library environment, pass the
  repository's required flags, and repeat nondeterministic measurements using
  the repository's sampling requirement. Record the tool version, input hash,
  revision, dirty state, sample count, and observed range.
- Prefer independent external oracles for correctness: `pcbnew`/`kicad-cli`
  for board behavior, and brute-force completeness oracles for optimized
  geometry and clearance. Use asymmetric, non-90-degree probes for rotation;
  KiCad places footprint children with clockwise `R(-theta)`.
- When a measurement contradicts a recent change, inspect the instrument,
  stale build, fixture, and environment before concluding that the change is
  wrong. Report unexplained regressions; never widen a ceiling or baseline just
  to make a check green.

### Harness and agent contracts

- Keep the harness thin and observable: expose the exact current context,
  provide native tools that return actionable findings, and do not hide repair,
  search, or acceptance logic inside the harness.
- Bound every attempt with an absolute deadline and edit budget. Consume a
  slot for every attempted action, preserve failed and indeterminate outcomes,
  and never retry until success. Recovery is allowed only after a verified
  complete provider response and a live provider; do not reconstruct state from
  partial output.
- Treat learned artifacts as immutable, versioned, and hashed. Make frozen
  versus updating conditions explicit, and require evidence before claiming an
  improvement over a baseline.
- Before accepting any new or changed unit PCB, run the Rust physical stackup gate
  documented in `VALIDATION.md` on the actual saved PCB bytes. A clean native
  DRC does not establish a consistent physical stackup.
- Before a new unit construction attempt, use the [memory workflow](skills/README.md)
  to select applicable reviewed notes and retain the actual outbound input and
  dispatch receipt. Preparation alone is not delivery. Record reported use and
  executed helpers separately; do not infer either from selection. Transfer
  procedures across units, but bind exact facts to current source identities.
  Memory is advisory and cannot relax Rust validation or current requirements.
- Delegate bounded deliverables, use one isolated worktree per agent, commit
  or salvage work before restarting a dead agent, and independently verify
  every delegated claim. Never parallel-edit the same file.

### Evidence and telemetry

- Preserve a causal run record: operation sequence, provider request/response,
  source and fixture hashes, before/after board or revision identity, native
  findings, budgets, and the final authoritative result. Write local evidence
  before exporting telemetry.
- Zapote may export the user's authorized full-fidelity raw conversations and
  complete PCB/project/footprint artifacts. Keep credentials transport-only;
  they must never appear in trace payloads. Support an explicit offline path
  (`--no-telemetry`) and retain the local run as the source record.
- Make trace fields structured and bounded enough for reliable querying, while
  retaining the raw artifacts needed to reproduce a decision. A trace with
  only a run name and IDs is not actionable.

### Workflow guardrails

- A subagent handback is not batch completion. Accept validator work only after
  reviewing and integrating its files, proving relevant failure cases, and
  running the common `check-units` command on current maintained candidates.
  Missing adapters, geometric models and evaluated-object counts are software
  gaps; never relabel them as only hardware qualification. Track exact remaining
  requirements in the [integration checkpoint](validation/integration-2026-09-12.md).
- Use public module interfaces and keep import-boundary checks ratcheting
  monotonically: new violations fail, and fixed exceptions are removed rather
  than replaced with broader coupling.
- Never use `git stash`. Check `git status`, the actual diff, branch, and commit
  before trusting a result; preserve unrelated user work and generated-file
  requirements.

## Evidence map

Read the relevant detailed record before changing behavior in that area:

- [Truth-validator audit pattern](../docs/solutions/design-patterns/proxy-audit-must-rerun-truth-validator-aligned-audit-2026-08-02.md)
- [Per-net-pair clearance oracle](../docs/solutions/logic-errors/clearance-false-negatives-per-net-pair-2026-06-28.md)
- [Real DRC API schema](../docs/solutions/logic-errors/drc-api-wrapper-components-and-location-always-empty.md)
- [Measurement instruments and failure modes](../docs/evidence/2026-08-19-measurement-instruments-that-lie.md)
- [KiCad rotation oracle](../docs/evidence/2026-08-18-pad-core-polygon-rotation-convention.md)
- [Bounded delegated-agent tasks](../docs/solutions/workflow-issues/delegated-agent-task-shape-2026-07-26.md)
- [Dead-agent salvage and restart](../docs/solutions/workflow-issues/dead-agent-signature-and-cleanroom-restart-playbook-2026-08-02.md)
- [Parallel-edit collision failure](../docs/solutions/workflow-issues/parallel-batch-agents-same-file-edit-clobber-2026-07-31.md)
- [Import-boundary ratchet](../docs/solutions/tooling-decisions/import-linter-boundary-enforcement-ratchet-2026-06-22.md)
- [Current harness contract](../harness-lab/CONTINUAL-HARNESS.md)
- [PFC current and copper model lessons](validation/p1-current/README.md) —
  preserve switching-state moments, physical pad UUIDs, signed sharing
  sensitivity and explicit area-current gaps; a graph tree or pad-size proxy
  cannot certify native current distribution.
- [Independent PFC validator references](validation/p1-current/oracle-2026-09-12/README.md) —
  a passing self-consistency test is insufficient. Keep closed-form and external
  solver references independent; enforce CCM validity over the continuous phase
  domain, and require unchanged-copper subdivision to preserve verdicts. SPICE
  probes need correct initial conditions, integer-cycle windows and timestep
  refinement before their measurements become reference evidence.
- [Model certificate semantic binding](../docs/solutions/best-practices/model-certificates-need-semantic-binding.md)
- [Real bridge-neck thermal assessment](thermal/bridge-necks.md) — preserve
  independent geometry-transfer checks, electrical/thermal energy balance and
  mesh refinement. Elmer nodal reaction fluxes at shared boundary nodes are not
  per-face heat flows; use integrated boundary laws for heat partition. A valid
  numerical result cannot certify unbounded assembly cooling or waive current
  findings. Replay validates historical evidence, not the installed solver.
- [Bridge cooling contract](thermal/bridge-cooling.md) — source-bind selected
  cooling targets separately from verified assembly properties. A Robin
  reservoir temperature is not the boundary-surface temperature; a junction
  limit is not a PCB limit. Compare mesh refinements of the same physics.
  The 20-case run has only 2.14 K nominal PCB margin and fails its weaker-contact
  sensitivity: finer meshes cannot resolve unknown lead/barrel heat paths.
- [Buck harness refinement plan](../docs/plans/2026-09-09-1945-feat-buck-harness-refinement-plan.md)

- [GBJ package and assembly study](thermal/gbj-study/README.md) — transfer the
  procedure, not the numerical result: preserve actual copper side, distinguish
  per-element package ratings from total loss, test asymmetric conduction, and
  retain assembly/airflow applicability separately from numerical convergence.
  The historical GBU front-side normalization is not a validated model of an
  asymmetric back-copper joint.
