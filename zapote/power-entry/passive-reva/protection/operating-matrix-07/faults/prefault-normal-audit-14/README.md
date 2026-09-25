# Prefault normal-prefix audit 14

This candidate reads a decoded native `fault42` TSV and selects an exact
normal-operation prefix for the settled fault cases. It validates all 42
columns on every row, rejects backwards time, retains equal timestamps, and
does not interpolate or rewrite selected values. The output contains the
original `normal15` columns in canonical order. A temporary output is renamed
only after the complete input reaches the cutoff and the last selected sample
is within the declared cutoff gap. Each row is bounded at 16 KiB; the input is
expected to be the trusted streaming decoder's whitespace TSV contract.

The same pass records every `fault_inject` rising edge (`<2.5 V -> >=2.5 V`,
bounded at 16) with its original timestamp and `v(acsrc,acn)` value. This is
the observed fault phase/electrical value from the trace, not a nominal AC
formula. `--scan-only` performs the full validation and writes only the JSON
report, so a caller can scan first and rerun selection after choosing the
settled cutoff.

```text
prefault_normal_audit RAW42 NORMAL15_OUT REPORT_JSON CUTOFF_S MAX_CUTOFF_GAP_S [--scan-only]
```

Campaign use can keep the decoded trace and selected prefix as pipes:

```text
fault_native_adapter --schema fault42 --byte-order little < raw.bin \
  | prefault_normal_audit - - prefault-report.json 0.65 1e-6
```

`RAW42=-` reads stdin and `NORMAL15_OUT=-` streams the selected normal15 rows
to stdout; no decoded TSV or selected-prefix file is accumulated. Since a pipe
can receive selected rows before a late input error is discovered, the caller
must require exit status zero and a published `status=OK` report before passing
the stream to any auditor or acceptance check. Regular file output remains
available and is renamed atomically after EOF.

For the settled fault campaign, use the exact last accepted sample as the
normal prefix endpoint and then run the existing normal auditor/normalizer on
the selected `normal15` output. F2-START is exempt from settled regulation;
it still requires its separately measured healthy-prefix contract. This tool
does not run a simulator, fault checker, or acceptance decision.

## Bounded checks

```text
rustc --edition=2021 -D warnings --test fault_normal_audit.rs \
  -o /tmp/prefault-normal-audit14-tests
/tmp/prefault-normal-audit14-tests
rustc --edition=2021 -D warnings -O fault_normal_audit.rs \
  -o /tmp/prefault-normal-audit14
```

The six tests cover reordered 42-column input, exact cutoff selection,
equal-time retention, scan-only operation, truncated/backward/nonfinite and
bad-schema rejection, and output flush failure. The candidate remains
transport/audit evidence only.
