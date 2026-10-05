## Institutional Learnings Search Results

### Search Context
- **Feature/Task**: Review R7 experimental RTD coupon CAD, CAD-coupled thermal comparisons, independent fixtures, calibration preparation, and artifact identity. Physical results remain `NOT_RUN`.
- **Keywords Used**: measurement identity, provenance, CAD geometry, thermal boundary, convergence, gate scope, negative checks, calibration, fixture, sensor.
- **Files Scanned**: 209 Markdown learning files in `docs/solutions/` by metadata pre-filter; relevant candidates were read in full.
- **Relevant Matches**: 5 prioritized files. These are historical risks and review prompts, **not observed R7 defects**.

### Relevant Learnings

#### 1. A measurement carries its commit, or it is not a measurement
- **File**: `docs/solutions/best-practices/a-measurement-carries-its-commit-2026-07-26.md`
- **Module**: `development_workflow`
- **Problem Type**: `best_practice`
- **Relevance**: R7 compares a frozen R5 control with new CAD, publishes generated result files, and records `baseline_commit` plus per-artifact SHA256 identities in `revision7/provenance.py`. The historical lesson is to bind each measured claim to the exact inputs that produced it, particularly when comparing runs across revisions. R7's current source shows content hashes and a baseline commit; the review should verify those receipts actually cover each result's inputs. No mismatch is established here.
- **Key Insight**: A numerically correct result from an older checkout or a different input revision can support a false present-tense comparison. The earlier router investigation could not conclusively explain a 37.5%–53.1% spread because the source states were not both pinned.
- **Severity**: high

#### 2. Measurement conventions must be stated, because mixing them is invisible
- **File**: `docs/solutions/best-practices/measurement-convention-must-be-stated-2026-07-28.md`
- **Module**: `temper_placer`
- **Problem Type**: `best_practice`
- **Relevance**: `revision7/mechanical/thermal_geometry.csv` exports multiple lengths, areas, volumes, package envelopes, and film-path quantities consumed by `revision7/thermal/adapter.rs`. The lesson is applicable to the CAD-to-model boundary: verify that each quantity's physical basis and units match the receiving equation and the claimed threshold. The CSV uses descriptive fields, but that alone does not prove their conventions are correct.
- **Key Insight**: The earlier creepage analysis compared a real 7.62 mm center pitch to an edge-gap threshold; the correct edge gap was 6.02 mm, reversing the verdict. Numbers sharing units can represent different quantities.
- **Severity**: high

#### 3. Gate subset blindness — a check that passes over a fraction of its input
- **File**: `docs/solutions/best-practices/gate-subset-blindness-2026-07-27.md`
- **Module**: `ci_infrastructure`
- **Problem Type**: `best_practice`
- **Relevance**: R7 verification reports 12 nominal assemblies, 15 cartridge STEP exports, 4 fixture STEP artifacts, 77 Rust tests, and targeted negative checks. Check that mechanical pose, exported-solid, fixture intersection, thermal variant, and calibration run denominators come from the generated artifact universe rather than a narrow hand-maintained subset. This is a coverage question, not evidence that R7 omitted one.
- **Key Insight**: A green check over a nonempty subset can conceal most of the intended universe. Prior traceability and net-partition gates reported clean results while scanning only a minority of eligible items.
- **Severity**: critical

#### 4. Falsify the fix before believing it
- **File**: `docs/solutions/best-practices/falsify-the-fix-before-believing-it-2026-07-29.md`
- **Module**: `development_workflow`
- **Problem Type**: `best_practice`
- **Relevance**: R7 `VERIFICATION.md` says the mechanical audit rejected deliberately bad collision records and a disconnected weld, while thermal, fixture, and calibration runners rejected specific bad inputs. Review the negative checks at the actual runner entry points and verify they fail for the intended reason with stale success receipts cleared. This recommendation does not imply the documented checks failed.
- **Key Insight**: Earlier gates passed their own motivating violations through parsing, wiring, or capability-check errors. A clean run becomes meaningful when the check also turns red on the precise defect it claims to catch.
- **Severity**: high

#### 5. Thermal FDM was first-order accurate from a misplaced boundary condition
- **File**: `docs/solutions/logic-errors/thermal-fdm-cell-centre-dirichlet-first-order-2026-07-09.md`
- **Module**: `temper_placer`
- **Problem Type**: `logic_error`
- **Relevance**: R7 provides `revision7/thermal/results/convergence.csv` for its lumped thermal network. The old defect was in a different FDM solver, so its specific half-cell fix is **not** a prescribed R7 change. The transferable review check is whether R7's convergence comparison actually varies the resolution and time step that control its reported response, and whether geometry/contact boundaries in CAD and the network refer to the same physical surfaces.
- **Key Insight**: A single-grid check passed while a refinement ladder exposed first-order error; boundary placement, rather than the interior stencil, controlled the global accuracy. A convergence table should be read against the method it claims to validate.
- **Severity**: medium

### Recommendations
- Trace each headline comparison from source CAD and assumptions through the geometry CSV, thermal inputs, result CSV, and SHA256 receipt; keep R5, R6, and R7 identities distinct.
- Check dimensional and physical conventions at every CAD-to-thermal handoff, especially package versus installed geometry, nominal versus maximum envelope, bond footprint versus actual contact area, and wire hot/cold path length.
- Read gate coverage as `checked / eligible` for assemblies, poses, exports, variants, and calibration cases. Preserve the documented negative cases as proof that the corresponding runners fail closed.
- Treat the FDM incident as a general convergence and boundary-alignment warning only. Do not report a solver defect in R7 without direct evidence from its own network code and outputs.
