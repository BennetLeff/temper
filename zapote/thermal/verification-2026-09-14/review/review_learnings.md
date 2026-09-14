## Institutional Learnings Search Results

### Search Context
- **Feature/Task**: Review the new Zapote bridge-neck thermal FEM experiment, retained Elmer/Gmsh evidence, replay binding, and its harness integration.
- **Keywords Used**: thermal model, semantic binding, model/solver independence, Elmer, Gmsh, FEM, replay, generated artifacts, stale evidence, geometry rotation, harness validation, fail-closed, INDETERMINATE.
- **Files Scanned**: 12 targeted learning records after grep-first filtering.
- **Relevant Matches**: 6.

### Relevant Learnings

#### 1. Model certificates need semantic binding as well as artifact hashes
- **File**: `docs/solutions/best-practices/model-certificates-need-semantic-binding.md`
- **Module**: zapote
- **Problem Type**: best_practice
- **Severity**: high
- **Relevance**: Fresh hashes alone cannot prove that a board-derived model, its numerical output, and the engineering claim still describe the same physical object. The new replay rule is aligned: it requires saved-board/native binding, regenerated geometry and SIF, raw-log/scalar agreement, convergence, and scenario population (`zapote/thermal/bridge-necks.md:99-103`); the harness makes unreplayable evidence fail closed (`zapote/packages/zapote-harness/src/bridge_thermal.rs:19-21,45-53`).
- **Key Insight**: Preserve an executable semantic validator and mutation controls, rather than treating an evidence directory hash as proof. A future mutation should change a scenario, a current, or a source identity while refreshing dependent hashes and still be rejected by replay/binding. The present changed tests already cover scalar mutation failure and mesh physical-tag mutation (`zapote/packages/zapote-thermal/tests/neck_physics.rs:36`, `zapote/packages/zapote-thermal/tests/neck_transfer.rs:24-74`), so no historical-rule contradiction was observed.

#### 2. Solver-independence is not model-independence for validation oracles
- **File**: `docs/solutions/best-practices/solver-independence-is-not-model-independence-2026-07-09.md`
- **Module**: temper_placer
- **Problem Type**: best_practice
- **Severity**: high
- **Relevance**: A closed-form bar test and Elmer execution establish implementation and numerical behavior for their declared model; neither alone validates the neck model against assembled-cooker physics. The change avoids the prohibited interpretation: it calls the bar a separate constant-conductivity check (`zapote/thermal/bridge-necks.md:97`), records omitted package/solder/opposite-side/enclosure effects (`:39-43`), and retains an INDETERMINATE verdict (`:99-103`; `bridge_thermal.rs:77-83`).
- **Key Insight**: Do not call two solves independent physical corroboration unless their discretization or physics differ on a material axis and a deliberately discriminating case proves that difference. The changed prose makes no such claim, so this is a review note rather than a finding.

#### 3. External-FEM corroboration is a validity-proxy, not a soundness proof
- **File**: `docs/solutions/best-practices/external-fem-corroboration-validity-proxy-2026-07-09.md`
- **Module**: temper_placer
- **Problem Type**: best_practice
- **Severity**: high
- **Relevance**: This is a direct Elmer/FEM learning. Its rule says external FEM can add a model-different validity proxy, while hardware remains the closing instrument and unavailable tools must not silently pass. The new implementation uses Gmsh solids and an Elmer electrical/Joule/thermal solve (`zapote/thermal/bridge-necks.md:21-35`), but expressly says no hardware was powered or measured (`:117`) and exposes missing evidence as INDETERMINATE (`bridge_thermal.rs:27-39`).
- **Key Insight**: If this evidence is later used to corroborate another thermal solver, register the comparison metric and tolerance, document shared assumptions, and retain a missing-tool/evidence UNMEASURED or INDETERMINATE result. The current work does not overstate FEM as a soundness or hardware proof.

#### 4. Qualification exports require clean-build replay
- **File**: `docs/solutions/best-practices/qualification-exports-require-clean-build-replay-2026-09-01.md`
- **Module**: electrical_qualification
- **Problem Type**: best_practice
- **Severity**: high
- **Relevance**: Meshes, SIFs, solver logs, scalars, and evidence manifests are generated qualification artifacts. The learning requires clean source-to-export replay, narrow normalization, semantic mutation controls, and protected-artifact checks. The changed command always receives a new output directory and retains geometry, mesh, SIF, scalar output, logs, backend hashes, and command records (`zapote/thermal/bridge-necks.md:108-117`), which is compatible with that rule.
- **Key Insight**: Before treating the committed evidence bundle as a qualification export, add or retain a clean-toolchain regeneration comparison against its canonical outputs and verify protected product artifacts do not change. The visible replay description validates regenerated inputs and artifact identities, but does not itself claim a clean-build byte-for-byte export receipt; this is a forward recommendation, not a demonstrated contradiction.

#### 5. A runnable behavioral model is evidence only inside its declared boundary
- **File**: `docs/solutions/best-practices/behavioral-model-evidence-boundary.md`
- **Module**: simulation
- **Problem Type**: best_practice
- **Severity**: high
- **Relevance**: The record correctly distinguishes source-backed geometry from chosen cooling/terminal assumptions: values are explicitly “not measured assembly properties” (`zapote/thermal/bridge-necks.md:47-65`), and the abstraction says which bodies and paths are omitted (`:39-43`). The normal unit integration keeps the numerical replay from supplying a rating contract (`bridge_thermal.rs:77-83`).
- **Key Insight**: Keep source facts, sensitivity assumptions, numerical checks, and product limits as separately named authorities. The changed documentation follows that boundary; its conclusion must remain limited until thermal limits and assembly cooling are established.

#### 6. Thermal models need complete connectivity and scoped sensor ratings
- **File**: `docs/solutions/logic-errors/thermal-model-rating-and-connectivity-boundaries.md`
- **Module**: zapote-thermal-sense
- **Problem Type**: logic_error (inferred; legacy frontmatter omits `problem_type`)
- **Relevance**: The direct Zapote predecessor warns against lossy connectivity checks and applying a rating beyond the assembly that earned it. The new record binds individual bridge trace UUIDs and native pad/drill data (`zapote/thermal/bridge-necks.md:12-20`) and deliberately refuses to infer a bridge/package rating from its local neck result (`:99-103`).
- **Key Insight**: Any added connectivity or component-rating claim should test split clusters while preserving endpoint coverage, reject duplicate/malformed native rows, and identify the exact assembly/part owning the rating. No changed line was found that contradicts that rule.

### Recommendations
- Preserve the current fail-closed replay path and make its semantic mutation tests exercise each claimed binding axis: board/native identity, selected four traces, scenario parameters, current-to-PFC binding, and raw solver-output interpretation.
- Keep the experiment outcome explicitly numerical and INDETERMINATE for product thermal acceptance until it has an assembly cooling model or instrumented hardware evidence.
- If the FEM result becomes an oracle for another solver, demonstrate model independence with a predeclared discriminating case and report the shared assumptions; solver/tool diversity by itself is insufficient.
- Treat regenerated mesh/SIF/log bundles as qualification exports: run a clean, isolated replay or source-to-export comparison before any promotion, with only proved non-semantic normalization.

No learning-derived review finding is warranted: the directly applicable historical rules are acknowledged by the changed code and documentation rather than contradicted by a changed line.
