# R8 verification and limits

Prepared 2026-10-04. This is a documentation/evidence-readiness revision against R7 commit `fd618613c9db374560ba4aba0a6faf5413109f1f`. No physics implementation, CAD generator, firmware or R7 artifact was changed.

## Checks performed

- R7's existing `provenance.py verify` passes, including archived R5/current-index identities and R6 artifacts. R7 remains the current CAD revision.
- All 15 entries in `retention-induction-evidence/local-inputs.sha256` match their inherited repository files.
- Actual R7 exported STEP was imported read-only with CadQuery to inspect the upward toe/spider contact faces. The evidence JSON records three approximately 0.24 mm² bearing patches, their coordinates, root face and post lengths, plus source hashes. This checks geometry, not stress, strength or manufacturability.
- Arithmetic check: `6 × 0.45 / (0.8 × 0.15²) = 150 MPa/N` for the uniform-bearing toe illustration; the 0.60 mm edge lever gives 200 MPa/N. Neither value is an allowable or a physical failure finding. `10 − 3 − 3 − 4 = 0 mN` verifies the remaining seal elastic allocation at simultaneous maxima.
- Primary manufacturer publications were read for bond guidance, sensor construction/processing, seal ratings and material limits. URLs, page/section references and limits are preserved in the workstream documents. Generic ceramic cure/gap instructions are explicitly not a Resbond 908 lot-specific procedure. Vendor PDFs are not bundled here.
- Independent Astra document review is recorded in `review.md`. Its requested capture-state clarification was applied: cap +0.20 mm, island +0.10 mm, then combined sequential challenge. The root agent checked the correction; a second reviewer run is not claimed.
- Local Markdown/HTML link targets and the final artifact/source identities are checked during packaging; `source-provenance.json` records exact content hashes. `git diff --check` is part of the final packaging check.

## What was not verified

No hardware measurements, supplier replies, procurement, calibration fitting, fresh firmware tests, new thermal runs or production enablement occurred. The prior software test results cited in the contact document are inherited evidence only. No independent browser rendering/accessibility test was performed for the static report; the packaging check verifies its structure and local link targets.

No product acceptance load, permitted permanent set, service duty, cleaning chemistry, leakage allowance or maximum physical fault-to-cut latency was invented. Those requirements, actual metrology capability and complete wet-boundary/retention details remain inputs to a qualified build. The combined upward-capture pose remains a required geometry check, not an R8 CAD result.

Physical results: **NOT_RUN**. Supplier questions: **DRAFT / NOT_SENT**. Status: **READINESS_PACKET_NOT_FABRICATION_RELEASE**.
