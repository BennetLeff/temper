# Round 7: approved Palace retry and amended FEM qualification

- Authority: [D1-FEM amendments](../../validation-plan/D1-FEM.md), commit `dd3695326d416c6d818f4296ef2db6b0dffd2286`.
- Board: unchanged native-17, SHA-256 `16e8b70bb7f2bc9020ea574022c13661cd09640ca3a52db1ff43f9f6db976162`.
- Operator: one local Codex worker using `gpt-6-sol`; coordinator owns review and commits.
- Evidence class: source/build provenance and simulation diagnostics; no physical measurement.
- Status: **BLOCKED — plate fixture not qualified**. The third Palace build failed at final link and is closed. Elmer direct coax passes on two meshes; the finest completed plate run is 2.802628 nH, below the 2.85–3.14 nH criterion. Mutual, board extraction and dependent switching runs remain held.

## Scope and limits

Keep the default CPU dependencies, enable ARPACK, and disable GPU components. Bind the intended MFEM directory, library and headers; capture final caches, link commands, hashes and `otool -L` before any solve. For static MFEM, the archive will not appear in `otool`; the exact linker input and archive hash supplement that dynamic-library receipt. A Homebrew MFEM dependency is not acceptable.

The Palace working session runs from 2026-09-28 20:10 UTC to 22:10 UTC at the latest. One configured build campaign is authorized, with no fourth attempt after a substantive build failure. Retrying an unchanged download after sandbox network denial is an access correction and is recorded separately.

If Palace fails, Elmer direct UMFPACK/tree gauge is the accepted fallback method. The coax, plate and mutual fixtures must all pass before a board solve. Check memory feasibility before a large direct solve. Any iterative replacement must reproduce the direct coax and plate values within 1% and meet its own residual tolerance. The rejected round-6 AMS result cannot be used.

D2/C1/C2 remain held until accepted board matrices also satisfy crop, mesh/order, closure and heatsink checks. Round-6 evidence remains the historical record; this continuation writes new evidence under round 7.

## Current-source error budget

The [reproducible calculation](audit_round6_current_budget.py) reads the committed round-6 fixture summary and records its SHA-256 in [the output](round6-current-budget.json). For magnetic energy E and sampled currents between Imin and Imax, it reports `[2E/Imax², 2E/Imin²]`.

Round 6's fine coax gives a sampled normalization interval of 13.444589–13.754345 nH against 13.862944 nH analytic: −3.0178% to −0.7834%. Thus the nominal −0.849% result does not pass the amended 2% requirement over the entire reported interval. This is an interval derived from sampled cuts, not proof of a spatial bound. Refining the source or its discretization remains required before acceptance under the amended criterion.

Run from the repository root:

```sh
python3 zapote/power-stage-120v/validation-results/round7-coordination/audit_round6_current_budget.py
```

## Geometry and solver interpretation

Crossing closures become arches at 1, 2 and 3 mm; noncrossing adjacent closures stay flat. Audit exact two-pad contact at every height. Retain all height-dependent matrices, their linear intercepts and fit residuals. The zero-height intercept is the plan's de-embedding model; linearity alone is not proof that all closure-field interactions were removed. Keep its assumptions and sensitivity explicit before combining it with package/lead inductance.

Palace's pinned `IoData::CheckConfiguration` requires `Aperture` only for mixed current/flux-loop excitations and rejects it for current-only configurations. Its [problem guide](https://awslabs.github.io/palace/dev/guide/problem/) also describes inactive open ports and parallel-element current sharing. Use the pinned source and examples to resolve configuration details: do not treat the three faces of a raised arch as parallel current-port elements. A possible implementation is PEC vertical legs and one driven horizontal span, subject to the contact and source-current checks.

The arch interpretation is a model limitation, not a replacement of the authorized height study. As described in [Ansys's inductance-matrix training, pp. 3 and 7–9](https://innovationspace.ansys.com/courses/wp-content/uploads/sites/5/2021/07/Q3D_GS_2020R1_EN_LE05_Ind_Matrix.pdf), loop inductance includes the complete current path and mutual terms. The coordinator therefore infers that reducing arch height does not by itself prove extraction of a unique board-only partial inductance; the horizontal span and its interactions also need to be accounted for when interpreting the intercept.

## Local simulation prerequisite repaired

The worker's initial three task-01 smoke runs stopped before simulation because the ignored `IFX_CFD7_650V.lib` was absent from its checkout. The coordinator copied the existing local library from its own checkout, verified SHA-256 `02ac6634f47c25be04e8de3c6eec4ec8cf403b659001b7f176c8f98bb6e9ce3b` against `sim-kit/models/fetch_models.sh`, and confirmed Git ignores it. This was an input-availability failure, not a circuit-result failure.

All three replays then completed (exit 0, `aborted=false`); task 02/04/05/07 smoke checks had already passed. The worker retains both sets of logs. Copies of the licensed library created by the runner were removed from the new raw result directories; the licensed source remains only in the ignored local vendor directory. These smoke results establish readiness of that starter setup, not acceptance of any FEM or board-switching result.

## Palace attempt 3 outcome

The campaign reached Palace's final executable link and failed with unresolved arm64 symbols, including `_gslib_tensor_mxm` referenced by the local static MFEM archive. The final inner Palace cache and link command selected `/opt/homebrew/lib/libgs.dylib`, while MFEM’s cache selected the superbuild’s `/tmp/ps-r6-fem-build1/lib/libgs.a`. This is another dependency-selection/configuration failure, not evidence that Palace cannot run on this host. No fourth build or link repair was attempted; the worker moved to Elmer direct as authorized.

The coordinator independently checked the saved final inner CMake cache and linker command: both select `/tmp/ps-r6-fem-build1/lib/libmfem.a`, and the link command contains no Homebrew MFEM library. Palace compiler commands include `/tmp/ps-r6-fem-build1/include`. The installed and build-tree MFEM hashes each match their recorded files. Their whole-file hashes differ, but a read-only ar-member comparison found the same ordered 270 members with identical payloads, including all 269 object files; the difference is archive metadata, not compiled object code. The [comparison receipt](mfem-archive-comparison.json) records both archive hashes. The comparison parses each 60-byte ar header, removes BSD extended-name prefixes from member data, and compares SHA-256 payload hashes in member order. `otool -L` cannot validate a linked Palace executable because the final link failed and no installed binary exists. These are verified build-input identities, not a successful binary-linkage receipt.

## Direct-solver resource diagnosis

The 0.18 mm coax source audit reduces the sampled current spread to about 0.046%, but its first direct solve terminated before an energy result. The worker traced this to a macOS SIGSEGV report identifying excessive recursion in Elmer's `GaugeTree` / `depthfirstsearch`, with roughly 29,000 recursive frames. This is a process-stack failure, not measured RAM exhaustion. The retry changed only the stack resource limit while preserving mesh, physics, solver and numerical tolerances. Neither source-current improvement alone nor a terminated solve is a fixture pass.

The larger stack allowed the 471,372-tetrahedron coax mesh to pass tree-gauge construction, but UMFPACK then returned `-1` (`UMFPACK_ERROR_out_of_memory`) during direct factorization. That failure is distinct from the first stack crash.

A targeted mesh, 0.10 mm at the port and 0.30 mm in the volume (130,430 tetrahedra), completed. The coordinator independently read its log and source audit: energy `6.897231e-9 J`, sampled currents `0.9984955317284225–1.0000111513633454 A`, and normalization interval `13.794154351030233–13.836062517234721 nH`. This is `−0.49621%` to `−0.19391%` relative to analytic and passes the amended interval criterion for that run. Exit 0 and `ALL DONE` are present. The second mesh, 0.08 mm at the port and 0.25 mm in the volume (229,668 tetrahedra), also completed with exit 0 and `ALL DONE`. Independently reading its log and source audit gives energy `6.906864e-9 J`, currents `0.9999670670863967–1.0007100585386928 A`, and interval `13.794131763146943–13.814637897569646 nH` (−0.49637% to −0.34845%). Its nominal value changes by +0.13966% from the coarser mesh. Both runs pass the amended sampled-current interval criterion; the plate outcome is reported below; mutual remains held.

Source PDF identities for the independent interpretation checks are pinned in [sources/references.json](sources/references.json).

## Independent plate reference check

[Wheeler (1965), IEEE MTT, printed p. 179, equation 31](https://davemcglone.com/wp-content/uploads/2023/02/IEEE-Wheeler-Transmission-Line-Properties-of-Parallel-Strips-01125962-1.pdf) describes thin parallel strips including finite-width fringing. For air (`k=1`) and width/gap `r=20`, its denominator is `D = r + ln(4)/pi + ln[(pi*e/2)*(r+0.94)]/pi = 21.871515158126368`. The corresponding inductance for 50 mm is `mu0*0.05/D = 2.8727709359655713 nH`. This is an infinite-length cross-section approximation multiplied by the fixture length; it does not include finite end/port effects and is not an independent 3-D oracle. It supports the existing 2.85–3.14 nH band rather than replacing it. The first localized plate solve (118,127 tetrahedra, 2.714820 nH) is below that band and is retained as a failed coarse result.

The coordinator's [actual-element audit](audit_plate_mesh.py), saved in [plate-mesh-audit.json](plate-mesh-audit.json), found median plate triangle maximum edges of 0.417 and 0.388 mm for the nominal 0.15 and 0.13 mm meshes; their 99th percentiles are both about 1.025 mm. Both meshes cover the expected 1000 mm² of plate surface. The small parameter change is therefore insufficient evidence of full plate refinement. The worker replaced the sampled distance field with continuous sizing over the plate/gap; the later runs still did not qualify. Reproduce with `python3 audit_plate_mesh.py <ASCII-MSH-2.2-file> ...`; inputs must use mm and the documented fixture coordinates.

## Plate refinement outcome

Continuous Box sizing exposed the direct-solver memory limit: the 0.4 mm plate / 4 mm exterior / 20 mm margin mesh (165,394 tetrahedra) failed numeric factorization with UMFPACK `-1`; no energy is accepted from it. Host RAM read via `sysctl -n hw.memsize` is 34,359,738,368 bytes (32 GiB). Tetrahedron count alone is not a memory predictor: sparsity/fill differ between the coax and plate problems.

The controlled full-domain pair at 20 mm margin, 12 mm exterior size and 0.5 mm transition completed: 0.4 mm plate sizing gives 2.759946 nH (80,041 tetrahedra); 0.3 mm gives 2.793182 nH (155,974 tetrahedra), +1.204%. Both remain below 2.85 nH. Changing exterior density and box margin also moves results, so these cases do not yet establish convergence.

A half-domain refinement was evaluated and rejected as configured. Reflection about z=0.25 mm exchanges equal/opposite plate currents: Bx and By are even and Bz odd. Thus the midplane has zero normal magnetic flux. An upper-half model uses the same PEC vector-potential boundary there, keeps the 10 mm-wide 100 A/m source (1 A), and should have half the full-domain energy; full inductance would be `4Ehalf/I²`. This parity argument did not qualify the implemented reduction: matched full/half comparisons differ by −5.84% at 0.4 mm and −5.47% at 0.3 mm. The natural-midplane negative control gives 325.638 nH equivalent and is also rejected. These are configuration/discretization diagnostics, not proof that symmetry reduction is intrinsically invalid; no half-model result is accepted.

The final full-domain run used 0.25 mm plate sizing, 12 mm exterior sizing and a 20 mm air margin: 226,819 tetrahedra, exit 0 and `ALL DONE`, energy `1.401314e-9 J`, inductance **2.802628 nH**. It is 0.047372 nH (1.66%) below the prescribed lower limit. The last matched refinement changes the value by 0.338%; outer-grid and domain sensitivity remain unresolved. This is an unqualified fixture result, not a demonstrated PCB defect and not evidence that Elmer is unsupported. Computation stopped after this run. No mutual, board, arch-height, heatsink, D2, C1 or C2 solve followed.

## Review and repository validation

The frozen [worker packet](../01-switching-parasitics/round7/d1-fem/README.md) is integrated. The independent Sol [code-review receipt](review/review.json) is complete with no remaining actionable findings (run `20260928-152038-748b39ca`). Review lenses ran sequentially in one local context; no external peer or expensive solve/build was repeated. The coordinator then added source-PDF hash metadata and these final review records. This accepts the evidence handback for commit, not the board or fixture qualification. The coordinator verified all 358 local raw files (417,368,869 bytes) against the manifest, checked source currents and energies against plate summaries, regenerated both summaries byte-for-byte, checked local links and script syntax, and confirmed the native-17 hash is unchanged; see [validation.json](validation.json). Scoped Ruff passes. The repository import-boundary gate passed with 5 contracts kept and 0 broken. `make regen` and `make regen-check` passed without changes to generated artifacts.

The `ce-simplify-code` reuse, quality and efficiency passes ran sequentially in the coordinator under the repository agent mapping. One quality change removed an unused shell variable; five import-order lint fixes followed. Historical geometry variants and independent audit implementations were retained: merging them could change generated meshes or remove the independent check. No reuse or efficiency changes were needed. No new production behavior is introduced, so targeted numerical/output checks replace unrelated application tests. No additional operational monitoring is required: this change records local validation evidence and reproducibility scripts, with no production PCB, source or firmware changes.

Review fixes bind each solved plate result to its paired source audit and actual SIF, require 1 A, use only finite positive final energy/coenergy, and reject explicit error markers. [Twenty-two scratch mutation checks](summary-mutations.json) pass. All original numerical values and classifications remain unchanged; the plate summary now also records its verified sampled-current range. Reproduction instructions separate frozen raw verification from new scratch runs.
