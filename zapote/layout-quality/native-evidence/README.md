# Native integration validation evidence

See [usage and findings](../NATIVE.md) and [integration audit](../INTEGRATION-AUDIT.md).
The runs identify the precommit revision and honestly record a dirty source tree.
`source-sha256.json` pins the reviewed source files. Binary hashes identify the
actual executed evaluators; formatting-only source changes followed the capture.
No production PCB was edited.

- `native17-report.json`: live release-mode native measurement.
- `native-edit-proof.tar.gz`: full native before/after snapshots, reports, command
  receipts, stderr and the scratch board with a narrower gate track.
- `unit-run.tar.gz`: full five-unit common run, including native ERC/DRC and P2
  inputs/reports; overall indeterminate, not acceptance.
- `unit-audit-summary.json`: compact projection of that run. Manufacturing counts
  are lengths of evaluated/skipped witness lists; full lists are in the archive.
- `workspace-tests.log`: 387 passed, 0 failed; one live test ignored by default.
  `PROPTEST_CASES=2048` applied to this invocation.
- `native-tests.log`: focused 11-test native Rust run, including two PBT properties.
- `native-edit-test.log`: both native CLI tests passed, including live KiCad.
- `source-audit.log`, `source-tests.log`, `native-parity.log`: existing 120 V checks
  rerun during the integration audit; 53 source tests passed.
- `regen.log`, `regen-check.log`, `import-boundary.log`: repository gates.

Clippy completed for `zapote-drc` and `zapote-harness` with all targets. Its 17
warning emissions were existing `needless_borrow`, `manual_range_contains`, and
`iter_overeager_cloned` diagnostics; none were in the new native-layout files.
Targeted rustfmt, `ruff check zapote/tools/layout_snapshot.py`, and `git diff
--check` passed. No claim of a warning-free legacy workspace is made.

The native fact fixture is
`../../packages/zapote-drc/tests/fixtures/native17-layout.json.gz`, captured with
KiCad 10.0.4. It is not a synthetic external-schema example. The native report's
`snapshot_sha256` is the SHA-256 of its decompressed bytes.
