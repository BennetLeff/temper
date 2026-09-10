# Integration review notes

The scoped simplification pass reviewed the native collector fixes, visible
label regression, and compact PCB authoring. Luna reuse and quality reviewers
found no actionable simplifications. The efficiency reviewer suggested changes
to two pre-existing lines outside the diff; neither was applied. In particular,
reloading before canonicalization preserves separation from the captured raw
native measurement and was not changed without targeted evidence.

Code review: skipped (ce-code-review unavailable).
The attempted nested ce-code-review run returned `status: degraded` because it
could not dispatch its required reviewers. Its artifact is
`/tmp/compound-engineering-501/ce-code-review/20260909-091500-buck-finished/review.json`.
This is not recorded as a completed independent code-review receipt. The host
performed a manual diff scan and checked its two proposed findings:

- The claim that a range-only requirement remains unresolved is false for
  this manifest: `unresolved_for_stage` checks
  `item.get("value").map(Value::is_null) == Some(true)`. Range-only entries
  omit `value`; `None` is not `Some(true)`. The complete-chain Rust test
  already includes a range-only output tolerance. No Rust change was made.
- Original run paths are host-local. The reports are explicitly historical
  excerpts, not portable trusted qualification receipts. Their provenance
  coverage and regeneration command are now documented in the adjoining
  engineering-evidence README. The full original run exists locally.

Native KiCad DRC, Atopile integrity, and the existing Rust judges were run by
the host. `make -C harness-lab check` passed 16 Rust and 48 Python tests,
including the regression with actual visible KiCad fields.

## Datasheet-derived model integration

A separate read-only Luna review inspected the model, decks, runner, and
plotter. It found missing EN/VIN hysteresis, incomplete native measurement
checks, and stale parameter documentation. All three were addressed. Luna
also implemented the runner failure handling and three focused mocked tests;
the host ran those tests independently. This review is useful evidence but
is not misrepresented as a completed CE review receipt.

The host's actual TI example run exposed excessive integrator leakage,
which was corrected from 10 Meg to 1 Tohm. The development revision remains
in measured-v2. The frozen corrected model has four 20 ns scenario runs,
two 10 ns convergence runs, and one EN hysteresis/restart run. Every native
measurement required by those runs was present and finite. The model report
separates plausible nominal regulation from uncalibrated transient behavior.
No approval registry entry was created.

The additional audit code is process/measurement I/O and plotting, not a new
Python authority for harness engineering decisions. The existing Rust
admission and layout judges remain authoritative. Manual final scan covered
the added model and audit code after the unavailable CE review outcome.
