# Native conductor/contact integration evidence

This continues the initial native integration. Production PCB bytes are unchanged:
`16e8b70bb7f2bc9020ea574022c13661cd09640ca3a52db1ff43f9f6db976162`.
Reports record the precommit revision, dirty source state, runtime, KiCad 10.0.4,
extractor/evaluator hashes, input hashes and the authoritative incomplete status.
`source-sha256.json` identifies the final reviewed implementation and tests.

## Results

- Native-17: 23/35 reconstructed paths, 12 explicit geometry gaps; 1,723 metrics.
  C16 return is newly reconstructed, 18.266090510544025 mm.
- 395 track/pad contacts evaluated: 351 full-width witnesses, 39 partial,
  5 without a straight-section witness. These are geometric observations, not
  minimum-cut width, ampacity or board acceptance.
- Scratch mutation: U1.15 trace width 0.8 → 0.4 mm; section resistance doubles,
  route resistance increases by the original section resistance, and the contact
  chord changes from 0.6 mm (partial) to 0.4 mm (full trace-width witness).
- KiCad's independent connectivity queries confirm all nine object transitions
  on C16's reconstructed return. The source board remains byte-identical.
- Rust workspace: 396 passed, 0 failed, 1 live test ignored by default, with
  `PROPTEST_CASES=2048`. Explicit live suite: 2 passed, including that test.
- Final native fixture replay/order tests: 17 passed, with `PROPTEST_CASES=2048`.
  Contact order is reversed as well as object order. KiCad can enumerate multiple
  contacts differently between runs; raw snapshot hashes can differ without
  differing facts. The fixture was recaptured from the retained final live run.
- Common five-unit runner: all five indeterminate, none failed. Missing operating,
  thermal, timing and current-distribution inputs remain visible. This does not
  register the 120 V board as a sixth accepted unit.
- Release benchmark: 321.10 ms/report over 25 repetitions of captured native-17
  facts, excluding native extraction/JSON parsing. Full live run: 2.100 s. Timing
  is a host observation, not a performance guarantee.
- Clippy completed for the whole workspace/all targets: 25 pre-existing warning
  emissions, none in changed code. Targeted rustfmt, Python Ruff, import-boundary
  and generated-artifact checks passed.

## Contents

- `native17-report.json` and `native-run.tar.gz`: full live report plus raw native
  capture, commands and stderr. The report's snapshot hash matches the decompressed
  v2 fixture in `packages/zapote-drc/tests/fixtures/native17-layout.json.gz`.
- `native-edit-proof.tar.gz`: complete before/after reports, captures, scratch PCB,
  mutation stderr and native connectivity oracle stdout/stderr.
- `unit-run.tar.gz`, `unit-summary.json`: full current common run and its summary.
- `workspace-tests.txt`, `native-replay.txt`, `native-edit-test.txt`: test results.
- `integration-red.txt`: two failures before implementing junction/contact wiring.
- `numerics-red.txt`: reproduced transformed-coordinate overflow before the fix.
- `benchmark.txt`, `clippy.jsonl`, `clippy.txt`, `regen.txt`, `regen-check.txt`,
  `import-boundary.txt`: performance and quality evidence.

## Remaining software scope

Zones and non-centreline copper contacts still need a complete conductor model.
Plated pad/via connectivity is included, but their resistance and current density
are not modelled. Branch current, field, decoupling parasitics, thermal and 3D
assembly integration remain open in [the audit](../INTEGRATION-AUDIT.md) and
issue #1628. No absent physical quantity is silently assigned zero.
