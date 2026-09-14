# Bridge redesign work allocation

The three plans below begin from `a4509b26bcc399a2df379d5263eb668c8552a0d4`.
Their outputs are candidates for review, not a fabrication release.

| Owner | Plan | Isolated branch | Owned output |
|---|---|---|---|
| Connections | [Connection redesign](../../docs/plans/2026-09-14-1215-fix-bridge-connections-plan.md) | `codex/bridge-connections-20260914` | `zapote/power-entry/bridge-redesign/` |
| Physical model | [Model and harness](../../docs/plans/2026-09-14-1215-feat-bridge-physical-model-plan.md) | `codex/bridge-physical-model-20260914` | Thermal Rust, thermal harness binding, new physical-model evidence |
| Cooling | [Cooling comparison](../../docs/plans/2026-09-14-1215-feat-bridge-cooling-assembly-plan.md) | `codex/bridge-cooling-options-20260914` | `zapote/thermal/cooling-options/` |

## Exchange points

1. Model owner publishes supported variant dimensions and input schema; connections owner supplies actual bridge/pad/trace geometry.
2. Cooling owner supplies sourced loss/contact/airflow ranges and candidate assembly dimensions.
3. Connections owner freezes candidate bundles with hashes, native checks and renders.
4. Model owner compares the baseline and frozen alternatives using consistent loads, uncertainty ranges and numerical criteria.
5. Coordinator integrates reviewed outputs, resolves conflicts, updates the maintained unit registry only with new source-bound evidence, and runs the full common suite.

## Coordinator acceptance

Review each handback against its plan's Definition of Done.
A report that says “partial” or names pending dependencies is a checkpoint, not completion.
Review actual changed files and test results before accepting claims.
The final integration must distinguish:

- numerical model validity;
- physical applicability and uncertainty;
- electrical/current-screen findings;
- temperature margin and fault protection;
- mechanical fit and assembly feasibility;
- hardware qualification, which remains NOT RUN.

Do not change the existing v1 contract or historical evidence to fit a new part.
Do not use a numerically converged model to waive unsupported physical assumptions.
Promote new lessons only after their cause and regression are reviewed; preserve frozen memory revisions.

## Bounded execution

Each initial worker attempt is limited to 90 minutes and at most three candidate designs including baseline.
This is a checkpoint boundary, not authorization to label unfinished work complete.
Workers send an early interface handoff, retain a failed-run record when applicable, and commit or salvage owned work before yielding.
Coordinator can assign a bounded continuation after reviewing the checkpoint.
No worker pushes or merges another owner's branch.

## Dispatch receipt

Plans were committed as `65406e8f1` and fast-forwarded into each isolated branch before dispatch.
The native collaboration tool launched `/root/bridge_connections`, `/root/bridge_physical_model` and `/root/bridge_cooling_options` with model override `gpt-5.6-luna`, reasoning `high`.
All three acknowledged the named plan and ownership.
This records launch and acknowledgement, not completed engineering work.
The [plan review](bridge-redesign-plan-review.json) records two corrected findings and verification of their resolution.
