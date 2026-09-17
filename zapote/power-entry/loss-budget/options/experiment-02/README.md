# Buffered gate-drive experiment 02

Compare C7 and the incumbent ST MOSFET with a proposed UCC27624DR buffer and
separate regulated supply. [PLAN.md](PLAN.md) defines the bounded experiment;
[SOURCE-AUDIT.md](SOURCE-AUDIT.md) records the retained primary-source facts.
The [measurement contract](MEASUREMENT-CONTRACT.md) separates design requirements
from measurements that have not been performed.

From the repository root, using the configured shared release target:

```sh
cargo build --manifest-path zapote/Cargo.toml --release --offline --locked \
  -p zapote-harness --bin zapote-pfc-drive-experiment
"$CARGO_TARGET_DIR/release/zapote-pfc-drive-experiment" \
  zapote/power-entry/shunt-repair/candidate/source-manifest.json > report.json
```

An overall INDETERMINATE report exits 2 even when numerical checks pass. Retain
stdout, stderr and the exit code; an execution failure is not successful empty
evidence. The experiment does not modify the circuit, PCB or procurement BOM.

`independent-audit.rs` independently reconstructs continuous-phase current
moments and asymmetric triangle energies. It is a mathematical implementation
check, not a second semiconductor simulator. It takes TSV fields in the order
documented in its header, with separate external turn-on and turn-off path
resistances and 5 A peak-current assumptions. Results, exact reproduction
commands, hashes and review are retained under `evidence/`.

Replay is required before consuming retained evidence. It parses the saved JSON
and compares every field against a new source-bound run; formatting/key order
may differ, but numbers, identities, cases and qualification status must match.
The matching retained report still exits **2** (INDETERMINATE); a mismatch exits 1.

```sh
"$CARGO_TARGET_DIR/release/zapote-pfc-drive-experiment" --replay \
  zapote/power-entry/shunt-repair/candidate/source-manifest.json \
  zapote/power-entry/loss-budget/options/experiment-02/evidence/report.json
```

Then independently check the complete canonical grid and its arithmetic:

```sh
rustc --edition=2021 -O \
  zapote/power-entry/loss-budget/options/experiment-02/independent-audit.rs \
  -o /private/tmp/pfc-drive02-audit
jq -r -f zapote/power-entry/loss-budget/options/experiment-02/audit-extract.jq \
  zapote/power-entry/loss-budget/options/experiment-02/evidence/report.json \
  > /private/tmp/pfc-drive02-audit-input.tsv
/private/tmp/pfc-drive02-audit < /private/tmp/pfc-drive02-audit-input.tsv
rustc --edition=2021 --test \
  zapote/power-entry/loss-budget/options/experiment-02/independent-audit.rs \
  -o /private/tmp/pfc-drive02-audit-tests
/private/tmp/pfc-drive02-audit-tests
```

Use the two checks together. Replay binds the whole report to current model and
pinned source bytes; the standalone audit supplies independent mathematics and
requires exact scenario coverage. Neither check establishes physical validity.
