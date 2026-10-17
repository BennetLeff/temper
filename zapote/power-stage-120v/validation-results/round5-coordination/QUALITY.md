# Round 5 quality record

Base: `91888bb29e318eef09c0a292245de88b9016d250`. This packet records a blocked D1 extraction, a draft bench procedure, supplier identity candidates, native outer-land checks, and evidence transport. It changes no PCB, firmware, component values or production source.

- Round-4 archive: eight focused tests pass, including a concurrent-destination mismatch that fails on the original check/replace implementation. A fresh full restore after the atomic install fix verifies 12,027 files. [Transport QA](../round4-coordination/raw-evidence/QA.md) records hashes and content checks.
- D1 manifest verification passes: 18 raw, eight source and 12 report files. The coordinator sorted imports and made the verifier accept an explicit solver path while retaining its exact binary hash. Original source, manifests and README were preserved under ignored `extraction/source-before-lint/` and `extraction/source-before-review/` before refreshing hashes. Relocated identical binaries and environment selection pass; changed or missing binaries fail. D1 remains BLOCKED; fixture success does not qualify board geometry.
- Sourcing table regeneration is byte-identical. A wrong-manufacturer mutation is rejected before any output CSV is written. Catalog identity matches are candidates, not assembly or procurement approval.
- Related-board census uses KiCad FlashLayer, with native-15 failing and native-17 passing controls. It does not claim full board qualification.
- The eight retained bench source PDFs were hash-checked. No bench energization occurred.

Simplification review considered and declined three changes: inferring branch counts while the port contract is unsettled; removing an explicit external archive-size safety limit; and optimizing repeat restores at the cost of a second staging path. Reuse review found no worthwhile change. The overwrite race was fixed separately and tested.

The [independent review receipt](code-review.json) is complete (`20260928-104217-9c5bef11`), with zero open findings after the solver-path and restore revalidation fixes. Eight Sol-only review lenses covered the 52-path packet before this receipt and quality summary were added. Its Ready to merge verdict applies to the evidence packet, not board qualification. No additional operational monitoring is required: this packet has no deployed production/runtime change. Evidence restoration must pass its complete hash checks; failed checks stop use of that copy, and simulation acceptance remains governed by ROUND-5.md.

Final targeted checks: all new Python scripts pass Ruff; All relative Markdown links resolve; import-boundary gate has zero new violations; `make regen` and `make regen-check` pass without derived-file changes. The general Rust ownership finding was rejected for these one-off diagnostics under master §2.7; the D1 handback explicitly requires Rust implementation and independent verification before any permanent acceptance-gate promotion.

The review's `coverage.reviewer_outcome` contains a citation typo: the one-off Python exception is in **00-MASTER-PLAN.md §2.7**, not zapote/AGENTS.md §2.7. The receipt is retained verbatim. An independent narrow-neck synthetic fixture remains advisable before promoting the meshing diagnostic into a permanent acceptance gate; no qualified mesh or board verdict is claimed here.

Historical D1 replay was checked in an isolated temporary input tree: verification rejected missing raw data, then the documented no-overwrite copy of all 18 local files made the full manifest verification pass. New diagnostic runs are explicitly separate from verification of retained historical bytes.
