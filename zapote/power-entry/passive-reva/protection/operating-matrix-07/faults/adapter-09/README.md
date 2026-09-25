# Fault trace adapter 09

Prepared and host-reviewed; no campaign fault trace has been accepted.
This is a minimal compatibility copy of `../readiness-08/fault_normalize.rs`;
the original is unchanged. The host independently compiled it with warnings
denied and ran all 14 tests successfully.

Changes are limited to the `F2-START` label, `SW-SHORT` alias for
`SWITCH-SHORT`, and requiring an actual F2 transition for `BYPASS-NEG`.
F2-START uses the same transition and healthy ARM/PERMIT/q/en prefix checks
as F2-CREST/ZERO. Numerical limits, transport checks and verdict separation
are unchanged. The adapter never grants a circuit protection PASS.

For this campaign the caller supplies the predeclared injection time and
window in `../timing-preflight-09/README.md`: 2 ms for F2 crest and 10 ms for
F2 zero/startup. Startup requires at least 10 ms of contiguous healthy armed
prefix. These bounds are caller inputs, not inferred from the case label or
moved to the observed detector edge. A pre-armed startup experiment needs
a different contract.

The raw trace must retain all normal diagnostics plus the fault currents and
control markers supplied by `../materializer-09/` and exported by
`../tracked-host-09/`. That source must derive from an accepted normal model;
the old `normal-tracked` source failed and is not an accepted baseline.
All five model includes, the deck and the executable belong in its source
identity. Ideal current-sense sources and pacing need prefault revalidation.

The streaming adapter reads one row at a time, checks all fields for finite
numbers, rejects duplicate headers and nonincreasing time, and produces the
17-column fault-checker input plus supplemental branch-current evidence.
Its CLI is:

```text
fault-normalize RAW.tsv CHECKED.tsv SUPPLEMENT.tsv REPORT.txt TSTOP KIND MUTATION_S EVENT_WINDOW MAX_GAP
```

The separate unchanged checker consumes CHECKED.tsv by path:

```text
fault-checks CHECKED.tsv TSTOP KIND EXPECTED_FAULT DETECTOR_WINDOW TURNOFF_BUDGET OBSERVATION MAX_GAP
```

Use checker kind `f2-open` for the three F2 cases. Source-bound case receipts
must record actual numerical arguments and graph mutations. Preserve
injection-to-detector latency, gate/channel cessation and remaining currents
separately. A failed-short MOSFET cannot earn interruption credit from a low
gate. Full traces are large: use checked FIFO/compression transport where
appropriate rather than creating unnecessary full uncompressed copies.
