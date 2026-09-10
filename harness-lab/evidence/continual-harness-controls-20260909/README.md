# Continual harness software controls — 2026-09-09

The complete local software path passed. These are scripted-provider controls,
not live model scores or electrical qualification. The intentionally unrouted
construction remains a valid native `fail`; the control passes by detecting it,
refining only at the specified boundary, and preserving state and provenance.

- 123 Python tests and 28 Rust tests passed; formatting, Clippy, and import
  boundaries passed (5 kept, 0 broken).
- A real sandboxed cell performed 20 native full-buck edits, applied one revised
  executable skill, and continued with its existing variables and old alias.
- A new reserved attempt imported the frozen artifact into a fresh interpreter;
  a fixed-base attempt received the base artifact. Software-control artifacts
  are explicitly rejected as sources for live inheritance.
- Driver recovery reused the owned worker, nonce, OpenCode session ID, variables,
  native ledger, and unchanged absolute deadline. Incomplete transport did not
  retry; worker death retained the completed native edit as indeterminate.
- Admission drift materializes the remaining blocked slots. Missing engineering
  evidence blocks preflight before provider launch. Exporter exceptions cannot
  change finalized local results.

Compact identities are in [controls.json](controls.json); final commands and
results are in [validation.log](validation.log). Raw snapshots, native outputs,
wire-shaped scripted evidence, revisions, receipts and liveness challenges are
retained locally under `harness-lab/runs/continual-controls-20260909-final/`.
That run directory is deliberately not committed. The compact record hashes its
complete control summary.

## Reproduce

From the repository root:

```sh
make -C harness-lab build check
PYTHONPATH=packages/temper-placer/src uv run --no-sync python scripts/import_linter_gate.py
```

To retain another complete native refinement/inheritance control, use a fresh
output directory and run from `harness-lab`:

```python
from pathlib import Path
from test_buck_runner import RunnerIntegrationTests
output = Path("runs/new-continual-control")
output.mkdir(parents=True, exist_ok=False)
RunnerIntegrationTests().refinement_control(output.resolve())
```

Native tests need KiCad and the real macOS sandbox/loopback capabilities. An
outer agent sandbox that denies those capabilities is not a negative result
about the nested workspace boundary.

## Review and operational validation

`ce-code-review` was invoked against the implementation base and returned a
**degraded** receipt: the four-agent service rejected independent reviewer
creation and exposes no release operation. Its sanctioned sequential review
found five defect groups in history replay, state classification, optional
status validation, inheritance identities, and admission drift. All were fixed
and their negative controls rechecked. No confirmed findings remain.

Code review: skipped (ce-code-review unavailable) — the top-level invocation
could not produce its required complete independent receipt after recovery.
The reviewing agent's sequential pass and the caller's manual diff scan were
completed; they do not replace independent coverage. Review run:
`20260910-035654-04274819` (temporary artifacts under `/tmp/compound-engineering-501/ce-code-review/`).

For the first future qualified run, the operator should inspect every slot's
claim, final classification, native measurement reference, and applied revision
receipt before accepting the aggregate. A missing receipt, indeterminate
transport, stale identity, or unqualified sandbox stops scoring and calls for
apparatus diagnosis; do not replace the consumed slot. Telemetry failures alone
must leave result hashes and process exit status unchanged. Live scoring still
requires current qualification, resolved engineering requirements, approved
component/model evidence, and a fresh exact-runtime preflight. SaaS trace
transport and physical hardware remain unverified.
