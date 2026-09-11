# Memory integration closeout — 2026-09-11

The durable model-qualification lesson now has a versioned Zapote memory package,
Rust validation/selection through the normal `zapote-rtd` binary, and a thin
construction-input transport. Agent startup guidance points to the workflow.
No PCB, model qualification rule, engineering acceptance threshold or legacy
memory package was changed.

The Rust port retains the donor's entry, selection and promotion policy. The
new context adapter checks raw bytes, preserves exact-fact source dependencies,
rejects duplicate catalog keys and includes rendered headings in the 64 KiB
bound. During review we corrected the old adapter's loss of source dependencies
and the donor's unchecked byte-count arithmetic. Python owns contained file
reads, process calls and immutable evidence; Rust owns selection policy.

Evidence in this directory:

- `cargo-test.log`: 76 workspace tests passed, including the memory controls.
- `python-test.log`: 8 transport tests passed, including CLI, changed/rehashed
  prompt, binary drift, timeout, path escape and failed preparation evidence.
- `verified-run/integration-receipt.json`: nine controls against the compiled
  binary and actual catalog. Procedure transfers; exact RTD fact requires its
  identities. Changed bytes/evidence, required stale facts, duplicate entries,
  candidates and rendered-note overflow are rejected.
- `verified-run/process-control/`: exact Rust-produced prompt equals the local
  echo process's input and output. This is explicitly not an LLM experiment;
  its receipt leaves model consumption unverified and helper execution empty.
- `luna-delivery-receipt.json` and `luna-decision-record.json`: the coordinator
  submitted that same selected prompt to a live Luna agent through
  `collaboration.followup_task`. Its response cited `rtd-mem-001`, proposed
  unit-specific checks and rejected transfer of RTD timing to current sensing.
  This is actual tool-level delivery plus attributed reported use, separate
  from the generic subprocess adapter. Provider wire capture is unavailable.
- `engineering-replay/root-review/mutation-replay.json`: all 34 existing
  engineering-validator scenarios still produce their expected outcomes.
- `cargo-fmt.log`: formatting passes. Clippy completes with only the previously
  existing `zapote-drc` range-comparison warning; new memory code is clean.
- `closeout-receipt.json`: source, catalog, test and evidence identities.

The live control made no CAD edits and ran no engineering experiment or helper.
It does not establish improved routing quality, time savings, or future automatic
use by every agent. The next construction attempt must use the documented input
workflow and retain its own receipt. Notes remain advisory. The RTD device and
brownout qualification gaps remain INDETERMINATE; hardware is NOT RUN.

To replay policy and process controls into a new directory:

```sh
python3 zapote/artifacts/memory-integration/verify_integration.py \
  --binary /absolute/path/to/zapote-rtd \
  --output /private/tmp/new-memory-control
```

The earlier 62-file model qualification receipt remains replayable against the
separate [frozen snapshot](../model-qualification-before-memory/README.md).
The raw provider output is buffered by the current host; keep responses bounded.
Source identities are supplied by the engineering caller and must describe its
current inputs. Catalog hashes establish byte identity, not permission to invent
or self-promote new engineering facts.
