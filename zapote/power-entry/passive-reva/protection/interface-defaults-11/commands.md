# Reproduction

Worktree: `/Users/bennet/Desktop/temper/worktrees/power-entry`.
Basis commit: `5dde29ab3e2f1223c2d33c129ced2cf647238307` (`assert-base.sh` passed).
Tools: ngspice 45.2, rustc 1.92.0, Atopile 0.2.69.
The untracked source inputs are identified in `input-identity.json`; the commit
alone is not their identity. No shared Rust extension was rebuilt.

The `before` controller is copied unchanged from revision 10. `after` adds the
new input resistors and OV/window path. Case files share stimuli except their
controller and output paths; the new model also writes detail traces. Circuit
files contain absolute paths to this experiment. Relocate those paths before
replaying elsewhere. Preserve this evidence directory when making a new revision.

From this directory, the simulator commands used for each variant and case are:

```sh
for variant in before after; do
  while IFS= read -r scenario; do
    ngspice -b "$variant/$scenario/case.cir" > "$variant/$scenario/run.log" 2>&1
  done < cases.txt
done
rustc --edition=2021 check.rs -o check
rustc --edition=2021 --test check.rs -o check-tests
./check-tests > check-tests.txt
```

Check retained traces and capture real exit codes (FAIL is exit 1):

```sh
for variant in before after; do
  : > "$variant/results.csv"
  : > "$variant/check-errors.log"
  : > "$variant/check-exits.csv"
  while IFS= read -r scenario; do
    ./check "$scenario" "$variant/$scenario/trace.tsv" \
      >> "$variant/results.csv" 2>> "$variant/check-errors.log"
    outcome=$?
    echo "$scenario,$outcome" >> "$variant/check-exits.csv"
  done < cases.txt
done
```

Use a shell without `set -e` for that loop: expected negatives must not abort
the collection. Before: one PASS, six FAIL. After: six PASS, one expected FAIL
(`arm_reconnect_high`). Simulator exit zero by itself is not a passing test.
The checker was strengthened after Luna review and rerun on all retained traces;
no circuit changed in that follow-up.

Deliberate defective variants:

```sh
ngspice -b missing_permit_pd/case.cir > missing_permit_pd/run.log 2>&1
./check permit_open missing_permit_pd/trace.tsv > missing_permit_pd/result.txt 2>&1
echo "$?" > missing_permit_pd/check-exit.txt
ngspice -b ov_bypassed/case.cir > ov_bypassed/run.log 2>&1
./check ov_running ov_bypassed/trace.tsv > ov_bypassed/result.txt 2>&1
echo "$?" > ov_bypassed/check-exit.txt
```

Each checker exits 1, demonstrating sensitivity to the missing protection.
The 15-case inherited regression uses revision 10's unchanged extractor:

```sh
sh regression/run_cases.sh > regression/run.log 2>&1
rustc --edition=2021 corners.rs -o corners
./corners > corners.json
rustc --edition=2021 audit-net.rs -o audit-net
./audit-net > net-connectivity.txt
```

The regression wrapper exits 0 only with 13 ordinary PASS results and both
designated negatives FAIL. The inherited unused-field compiler warning remains.
The standalone Rust tools avoid the shared Cargo/pyo3 target cache entirely.

From `source-candidate/`, build and then export sequentially:

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
  /Users/bennet/Desktop/temper/worktrees/power-entry/zapote/power-entry/passive-reva/protection/interface-defaults-11/source-candidate \
  resolved-components.json --entry-file elec/src/power_entry_pfc_control_candidate.ato \
  --entry PowerEntryPfcControlCandidate > export.log 2>&1
```

Both completed with exit 0. Missing passive MPN and existing declaration
warnings remain. Resolved per-instance attributes identify parts; footprint-
aliased `libsource` fields in the netlist do not. All exported build hashes
were checked against the files, and the Rust topology audit passed.

Metadata-only inventory and SHA-256 collection used Node's filesystem/crypto
APIs. Electrical calculations, connectivity assertions and trace verdicts are
in the standalone Rust sources retained here.
