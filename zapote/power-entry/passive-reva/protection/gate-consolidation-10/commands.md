# Commands and reproduction

Worktree: `/Users/bennet/Desktop/temper/worktrees/power-entry`.
Base assertion: `scripts/assert-base.sh 5dde29ab3e2f1223c2d33c129ced2cf647238307` passed.
Tools: ngspice 45.2, rustc 1.92.0, Atopile 0.2.69.

Baseline fixture files were copied from `../f2-shutdown-04/fault-tests/`.
Both copies of `extract.rs` are byte-identical to the donor. Runner changes
only move its executable from `/tmp` into the local experiment directory;
the candidate controller delta is confined to RESET aggregation.

From this directory:

```sh
sh baseline/run_cases.sh
sh candidate/run_cases.sh
rustc --edition=2021 --test baseline/extract.rs -o extractor-tests
./extractor-tests > extractor-tests.txt
```

The wrappers regenerate traces in their own variant directories. Their exit
status is zero only when all ordinary cases pass and both designated negative
controls fail the unchanged Rust checks. Simulator output is retained per case.
The compiler emits the donor's unused-field warning; all four tests pass.

For the added PERMIT observations, run from each `permit-loss/` directory:

```sh
ngspice -b permit-loss.cir > run.log 2>&1
```

These copied circuit stimuli and their `.meas` observations are separate from
the authoritative fifteen-case Rust scenario set. They are not fixture code
for the missing physical command receiver or VSENSE standby path.

From `reset-bench/`:

```sh
ngspice -b shared-reset.cir > shared-reset.log 2>&1
ngspice -b open-aux-negative.cir > open-aux-negative.log 2>&1
```

The negative bench differs only by removing `Saux` and changing its output
filename. ngspice exits zero for a simulated bad circuit: the observed bad
voltage, not process exit status, demonstrates the connection fault.

The source candidate copies Rev09's two-file `elec/` subtree and ato.yaml.
Only its RevB aggregation wiring and corresponding description changed.
From `source-candidate/`:

```sh
UV_CACHE_DIR=/private/tmp/temper09-uv-cache UV_TOOL_DIR=/private/tmp/temper09-uv-tools \
  /Users/bennet/.local/bin/uv tool run --offline \
  --python /opt/homebrew/opt/python@3.12/bin/python3.12 --from atopile==0.2.69 \
  ato --non-interactive build \
  elec/src/power_entry_pfc_control_candidate.ato:PowerEntryPfcControlCandidate \
  > build.log 2>&1

UV_CACHE_DIR=/private/tmp/temper09-uv-cache UV_TOOL_DIR=/private/tmp/temper09-uv-tools \
  /Users/bennet/.local/bin/uv tool run --offline \
  --python /opt/homebrew/opt/python@3.12/bin/python3.12 --from atopile==0.2.69 \
  python /Users/bennet/Desktop/temper/worktrees/power-entry/harness-lab/circuit_export.py \
  /Users/bennet/Desktop/temper/worktrees/power-entry/zapote/power-entry/passive-reva/protection/gate-consolidation-10/source-candidate \
  resolved-components.json --entry-file elec/src/power_entry_pfc_control_candidate.ato \
  --entry PowerEntryPfcControlCandidate > export.log 2>&1
```

Both commands returned zero. The first build launch used the worktree root
by mistake, returned 1 because the entry file was absent there, and produced
no successful candidate build. The corrected working-directory build above
is authoritative. Existing missing-MPN/declaration warnings were retained.

Tool caches above are incidental dependencies, not evidence storage. A fresh
machine needs the same pinned compiler available. Use a new output directory
when extending this experiment so these source hashes and results remain
reproducible. No installed extensions or shared Cargo build artifacts changed.
