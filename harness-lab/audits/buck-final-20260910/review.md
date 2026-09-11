# Local closeout review

Date: 2026-09-10. Scope: component/source reconciliation, waveform admission,
v2 fixture generation, native controls and explicit v2 runtime selection.
Three Luna subagents performed read-only reviews; the host integrated and
validated the corrections. This is a local review record, not a fresh formal
CE shipping receipt or electrical qualification.

- **Components:** all nine exact MPNs agree with source and contract. The host
  corrected the main BOM's L2 body envelope and removed unsupported precision
  from the approximate Samsung curve reading. Two unresolved requirements
  and typical-data limitations remain explicit.
- **Waveforms:** host review corrected case-ID transport, requirements-bound
  Cartesian coverage, clipped reference windows, missing pre/post holds,
  asymmetric relative endpoint tolerance, startup excitation/load checks,
  hidden transient excursions and acceptance-failure classification. Luna's
  final review found no remaining startup/load protocol defect. Its input-
  variation observation was retained as a documented coverage limit: there is
  no adopted line-step sequence in the requirements manifest.
- **Native fixtures:** the host rejected an earlier generated fixture set
  with stale metadata and suppressed footprint checks, rebuilt from the
  reviewed v5 reference and checked every terminal variant. Luna confirmed
  exact BOM maps, original staging/terminals, unchanged rule configuration
  and all original negative-control assertions. The relocated-capacitor and
  operation-recovery routes were adjusted to the new geometry, preserving
  their expected verdicts and budgets.
- **Runtime:** the circuit collector's hardcoded old adapter was exposed by
  an actual engineering run and replaced with the selected adapter. The v2
  launcher and native entry point live in the root source inventory, so the
  qualification receipt pins them alongside the shared implementation. The
  native dispatch retains the original 10.0.4 default for v1.

Simplification retained one shared native implementation and a small explicit
profile launcher; the copied audit-only adapter was removed. Rust remains the
policy owner. No approval check or electrical requirement was removed.

Validation is in [tests](tests/README.md), the [native receipt](native-tool/qualification/qualification.json)
and the [engineering report](engineering/report.md). The full umbrella
`make check` still stops on formatting in three pre-existing dirty files; its
failure is not reported as a passing check. No current review of that unrelated
telemetry/runner diff, live model trial, exact model approval, hot-component
qualification or powered measurement is claimed.
