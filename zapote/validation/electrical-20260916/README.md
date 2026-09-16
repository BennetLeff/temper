# PFC electrical harness checkpoint — 2026-09-16

Starting revision `7f506ba86`; final run inputs and executable/source digests are
recorded in each `suite-identity.json`. Board bytes were not changed.

- Rust workspace, release/offline/locked: **452 passed, 0 failed, 1 ignored**.
  The ignored live Gmsh integration test was not rerun: no thermal model or
  solver code changed. Retained thermal replay tests passed.
- Common [maintained run](../runs/electrical-20260916-maintained-final/summary.json):
  six INDETERMINATE units; power entry FAIL with exactly the four existing
  `DRC.PFC.BRANCH_COPPER` findings.
- Common [GBJ run](../runs/electrical-20260916-gbj-final/summary.json): all seven
  INDETERMINATE, no FAIL findings. Both report unchanged suite inputs during
  execution. Native KiCad 10.0.6 used ERC severity-all and DRC all-track-errors,
  schematic-parity and severity-all, plus fresh manufacturing extraction.
- Both PFC reports include the new mandatory interface rules, the modeled-net
  via census (35 GBU, 36 GBJ), and the source-bound shunt stress: 2.25 W mean /
  5.397 W peak under the
  ideal nominal waveform. These are not thermal acceptance results.
- Import boundaries: 5 kept, 0 broken; derived-artifact check passed.
- Clippy workspace/all-targets/all-features completed with **15 pre-existing
  warnings** outside this change. Strict `-D warnings` stopped at 14 library/
  unit-test warnings before the additional existing gate-drive integration-test
  warning. No new warnings were introduced.
- [Review](../../../docs/reviews/electrical-20260916/review.json) and
  [coordinator resolutions](../../../docs/reviews/electrical-20260916/resolution.md)
  retain the findings, rejected claims, applied fixes and scope limits.

Full final common-run evidence is committed alongside [command logs](logs/).
Earlier successful pre-review common runs remain local under
`validation/runs/electrical-20260916-{maintained,gbj}`; initial failed test
assertions and tool setup are explained in [validation notes](validation-notes.md).

The [electrical closeout contract](../../power-entry/electrical-closeout.md)
records the remaining model work. No PCB purchase, fabrication or powered
measurement occurred. No additional operational monitoring is required for
this local validator change; re-run the common suite on each future source or
board change and investigate unexpected new FAIL findings or missing rules.
