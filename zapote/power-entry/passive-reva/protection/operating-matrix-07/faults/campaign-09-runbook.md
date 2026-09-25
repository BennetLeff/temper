# Matrix 07 fault campaign runbook (prepared, dependency-gated)

## Current parent checkpoint (2026-09-21 UTC)

The accepted source is now `../accepted-baseline-11/`, with the explicit
`event-aware-normal-v1` receipt in `acceptance.json`. Its six input files
are frozen by content hash. The baseline retains the legacy strict-time
checker rejection; that rejection must not be relabelled or hidden.
The older source and acceptance commands below are historical and must not
be copied as current launch instructions.

LL01 through LL04 are accepted modeled normal points under their
source-bound receipts. LL05 completed solvercallbacks but its export was
incomplete and missing the native header; no fullsolver is live. Preserve
its failed archive and resolve transport before repeating a fullrun.
The first real F2-START attempt in `startup-candidate-13/` aborted numerically
at 4.416873 ms, before its 75 ms injection. Its complete retained partial
trace is rejected. The later compact-source fullstartup20 is accepted only
under `startup-compact-analysis-23/acceptance.json` for exactstartup screens.

Current native fault transport is parent-reviewed in `native-runner-14/`,
`native-capture-13/`, `event-aware-adapter-13/`, and
`event-aware-validation-13/`. Each folder's `parent-review.json` binds the
reviewed implementation. Current supervisor19 and validator22 supersede those transport/resource
versions as described below. Do not use historical ASCII
runner09 commands below. The native supervisor's exit zero means review
pending, never fault acceptance. Retain raw42 evidence and every pipeline
status. `prefault-normal-audit-14/parent-review.json` covers the streaming
prefix selector; each settled fault needs normal checks on its OWN prefix
and actual injection phase. F2-START instead requires the declared healthy
10 ms startup prefix.

`branch-model-review-13-parent.json` accepts the modeled terminal connections
for the short cases, with explicit limits: F2 isolates bank energy only;
local capacitance and source current remain. Gate-off cannot interrupt a
failed-short channel.

The bounded KLU versus SPARSE experiment in `linear-solver-probe-15/` reached
10 ms with KLU and stopped at 4.416873 ms with SPARSE. The native42 path was
then verified in `klu-native-16/`. Full startup17 hit its600wall cap at76.36ms.
A compact3point repeating PWL replaced the960002point timing source after the
isolated89ms benchmark passed all960002expectedcorners and25ns sampling gaps.
The source-bound `startup-compact-candidate-20/` reached89ms in276.326wallseconds,
with6,025,180finite/nondecreasing raw42rows. This resolves numerical capture,
not fault acceptance: validator13 rejected its4million-row memory cap.

Current native supervisor19 has parent-reviewed partialcapture draining and
9passedtests. Validator22 raises only that resource cap to8million, with
22passedtests and unchanged frozen electrical/event rules. Same-raw reanalysis
completed in `startup-compact-analysis-23/`: allfourstages0, all6025180rows,
frozencheckerPass and scopedparentacceptance. The bankpeaked127V; channelcurrent
wasalreadybelow0.1A about596nsbeforedetector. No settled390V or fuseclearing
claim follows. Preserve all originalcase20failure outputs.
No resimulation is needed for a checker memory limit. No source models or
protection thresholds are relaxed.

Keep at most two full solvers and a 10 GiB disk floor. Check live process
state and available space before launching. Current evidence is retained;
no separate storage volume is available.

Every real ngspice launch must supply
`SPICE_SCRIPTS=/opt/homebrew/Cellar/ngspice/45.2/share/ngspice/scripts`.
Without it, the authored UADC model cannot load and the command can exit zero
with no simulation points. Require the capture mask, nonzero point count,
endpoint, and complete trace checks as well as child exit codes.

## Historical preparation and retained timing contract

Parent update: bounded child supervision is now implemented and tested in
`runner-09/parent-review.json`. Use that reviewed supervisor for execution;
the older shell sequence below remains historical preparation, not an
independently supervised launch command. An accepted source baseline and
capacity check are still required. No full fault cases have launched.

Status: **RUNBOOK ONLY / NO FAULT CAMPAIGN STARTED**.

Parent review: the electrical timing and classification corrections below
are recorded, but the FIFO shell orchestration is still a draft. Before
executing it, add and test bounded child supervision and cleanup on every
failure (including a missing executable, an adapter rejecting before opening
its outputs, and compression failure). Removing FIFO names alone does not
terminate blocked children. The current normal source failed and cannot
supply the required accepted baseline. This runbook is not launch approval.

This runbook describes the first executable campaign against the
`normal-hysteretic-settling-extension` source, whose only electrical-source
change is `TSTOP=500m` to `TSTOP=650m`. That source is still marked
`accepted: false` in `normal-hysteretic-settling-extension/execution.json`;
the current extension attempt halted at a repeated time near 501.554914 ms.
Do not launch a fault case until a corrected 650 ms normal trace completes and
passes the unchanged normal checker with its endpoint and input-hash receipt.

## 1. Acceptance gate before any fault case

Set the matrix root once; all subsequent paths are absolute through this
variable:

```sh
set -eu
MATRIX07=/private/tmp/temper-pkgs-1-4/zapote/power-entry/passive-reva/protection/operating-matrix-07
NORMAL="$MATRIX07/normal-hysteretic-settling-extension"
```

First confirm the source identity. A gzip-valid partial trace is not complete;
the corrected producer must report a clean solver stop at 0.65 s. The receipt
must retain `accepted: false` until the checks below actually pass:

```sh
grep -E '^\.param RLOAD=190 TSTOP=650m STEP=500n$' "$NORMAL/cold.cir"
shasum -a 256 "$NORMAL/cold.cir" "$NORMAL/protection.inc" \
  "$NORMAL/standby.inc" "$NORMAL/clamp.inc" \
  "$NORMAL/ucc28180-pwm-latch.inc" "$NORMAL/authored_logic_hysteretic.inc"
gzip -t "$NORMAL/trace.tsv.gz"
```

Build the unchanged normal adapter and checker, including their tests. Run
the acceptance pipeline only after `trace.tsv.gz` is complete:

```sh
rustc --edition=2021 -D warnings --test "$MATRIX07/checker/normalize.rs" \
  -o /tmp/matrix07-normalize-tests
/tmp/matrix07-normalize-tests
rustc --edition=2021 -D warnings --test "$MATRIX07/checker/operating_point_checker.rs" \
  -o /tmp/matrix07-operating-point-checker-tests
/tmp/matrix07-operating-point-checker-tests
rustc --edition=2021 -D warnings -O "$MATRIX07/checker/normalize.rs" \
  -o /tmp/matrix07-normalize
rustc --edition=2021 -D warnings -O "$MATRIX07/checker/operating_point_checker.rs" \
  -o /tmp/matrix07-operating-point-checker
set -o pipefail
gzip -cd "$NORMAL/trace.tsv.gz" \
  | /tmp/matrix07-normalize 190 \
  | /tmp/matrix07-operating-point-checker --end-s 0.65 \
  > "$NORMAL/checker-650ms.txt"
```

The normal report must show a complete finite trace ending at exactly 0.65 s,
the frozen switching-gap and node screens, the settled-cycle screen, and no
`REJECTED` or `engineering_screen=STOP`. A report that only parses or reaches
the endpoint is insufficient. Retain the report, the raw trace hash, the
source/include hashes, simulator options, and the command output together;
until then every row below remains **UNEXECUTED**.

The accepted normal trace ends at 650 ms, so it cannot contain rows after the
endpoint at which the settled fault will be injected. Select those events
analytically from the unchanged `SIN(... FLINE=60 ...)` source, then verify the
actual `v(acsrc,acn)` samples in each fault trace before invoking the checker.
At 650 ms the source is at a zero crossing; the next absolute crest is
`650 ms + 1/(4*60 Hz) = 654.1666666667 ms`, and the following zero is
`650 ms + 1/(2*60 Hz) = 658.3333333333 ms`. This source-phase calculation is
predeclared evidence, not a claim that the normal baseline contains those
rows. If the fault trace does not show the selected voltage within 1% of the
target, classify the case as unexecuted and investigate source/event identity.

## 2. Build the fixed campaign tools

Build and test the preparation materializer, tracked export host, streaming
fault adapter, and unchanged fault checker. These commands do not simulate:

```sh
rustc --edition=2021 -D warnings --test \
  "$MATRIX07/faults/materializer-09/materializer.rs" \
  -o /tmp/matrix07-materializer-tests
/tmp/matrix07-materializer-tests
rustc --edition=2021 -D warnings -O \
  "$MATRIX07/faults/materializer-09/materializer.rs" \
  -o /tmp/matrix07-materializer-09

rustc --edition=2021 -D warnings --test "$MATRIX07/faults/tracked-host-09/progress.rs" \
  -o /tmp/matrix07-fault-tracked-tests
/tmp/matrix07-fault-tracked-tests
rustc --edition=2021 -D warnings -O "$MATRIX07/faults/tracked-host-09/progress.rs" \
  -L /opt/homebrew/opt/libngspice/lib -l ngspice \
  -o /private/tmp/matrix07-fault-tracked-host-09

rustc --edition=2021 -D warnings --test "$MATRIX07/faults/adapter-09/fault_normalize.rs" \
  -o /tmp/matrix07-fault-adapter-tests
/tmp/matrix07-fault-adapter-tests
rustc --edition=2021 -D warnings -O "$MATRIX07/faults/adapter-09/fault_normalize.rs" \
  -o /tmp/matrix07-fault-normalize

rustc --edition=2021 -D warnings --test "$MATRIX07/faults/fault_checks.rs" \
  -o /tmp/matrix07-fault-checks-tests
/tmp/matrix07-fault-checks-tests
rustc --edition=2021 -D warnings -O "$MATRIX07/faults/fault_checks.rs" \
  -o /tmp/matrix07-fault-checks
```

Record each binary/source hash in the campaign receipt. The tracked host must
run with the ngspice script directory set; omitting `SPICE_SCRIPTS` can produce
the earlier UADC setup failure before the deck is evaluated:

```sh
export SPICE_SCRIPTS=/opt/homebrew/Cellar/ngspice/45.2/share/ngspice/scripts
```

## 3. Predeclared case matrix

The materializer source is the accepted 650 ms source directory only after the
gate above passes:

```sh
SOURCE="$MATRIX07/normal-hysteretic-settling-extension"
RUNROOT="$MATRIX07/faults/campaign-09-run"
mkdir -p "$RUNROOT"
```

Each output directory must be new. These are proposed settled event times and
finite horizons; confirm phase against the accepted normal trace before
materializing. `TSTOP` includes the search horizon, post-detector observation,
and a small endpoint margin.

| case | proposed `T_FAULT` | `PREFAULT_WINDOW` | proposed `TSTOP` | checker window / observation | status |
|---|---:|---:|---:|---:|---|
| F2-CREST | 0.6541666666667 s | 0.002 s | 0.662 s | 0.002 s / 0.002 s | first settled positive path |
| F2-ZERO | 0.6583333333333 s | 0.010 s | 0.682 s | 0.010 s / 0.010 s | second settled positive path |
| SW-SHORT | crest time above | 0.002 s | 0.662 s | 0.002 s / 0.002 s | expected `PROTECTION_GAP` |
| DIODE-SHORT | crest time above | 0.002 s | 0.662 s | 0.002 s / 0.002 s | gated on branch-model review |
| BOTH-SHORT | crest time above | 0.002 s | 0.662 s | 0.002 s / 0.002 s | expected `PROTECTION_GAP` |
| BYPASS-NEG | crest time above | 0.002 s | 0.662 s | 0.002 s / 0.002 s | expected bypass negative control |
| F2-START | measured only | 0.010 s | measured `t_F` + 0.014 s | 0.010 s / 0.002 s | separate startup gate |

For `F2-START`, do not use the settled crest time. Select `t_F` only after a
fault-deck prefix demonstrates at least 10 ms of contiguous healthy
ARM/PERMIT/q/en/fault state. The 71 ms example is only a candidate if the
measured prefix proves it; the case remains held until that startup contract
is reviewed.

Materialize a settled case after its phase and normal-prefix receipts pass:

```sh
CASE=F2-CREST
TF=0.6541666666667
TSTOP=0.662
PREF=0.002
OUT="$RUNROOT/$CASE"
/tmp/matrix07-materializer-09 "$SOURCE" "$CASE" "$TF" "$TSTOP" "$PREF" "$OUT"
```

The complete settled-case preparation commands are:

```sh
/tmp/matrix07-materializer-09 "$SOURCE" F2-ZERO     0.6583333333333 0.682 0.010 "$RUNROOT/F2-ZERO"
/tmp/matrix07-materializer-09 "$SOURCE" SW-SHORT    0.6541666666667 0.662 0.002 "$RUNROOT/SW-SHORT"
/tmp/matrix07-materializer-09 "$SOURCE" DIODE-SHORT 0.6541666666667 0.662 0.002 "$RUNROOT/DIODE-SHORT"
/tmp/matrix07-materializer-09 "$SOURCE" BOTH-SHORT  0.6541666666667 0.662 0.002 "$RUNROOT/BOTH-SHORT"
/tmp/matrix07-materializer-09 "$SOURCE" BYPASS-NEG  0.6541666666667 0.662 0.002 "$RUNROOT/BYPASS-NEG"
```

Hold DIODE-SHORT and BOTH-SHORT at the branch-model review gate even though
their mechanical commands are shown. Preserve each generated `manifest.json`,
`case.cir`, closure hashes, and the materializer command. The manifest remains
`PREPARED_UNEXECUTED` until the host run below succeeds; it is not a fault
verdict.

## 4. Execute one case and normalize without retaining duplicate giant files

Run the tracked host in the case directory. A long wall limit is intentional;
the 650 ms normal extension previously required a multi-minute-to-tens-of-
minutes run. The host writes its `wrdata` export to a FIFO so raw and
normalized traces are compressed concurrently; no giant uncompressed raw file
is retained. Keep stdout/stderr and the first-invalid snapshot:

```sh
cd "$OUT"
WINDOW=0.002
OBSERVATION=0.002
ADAPTER_KIND=f2-crest
CHECK_KIND=f2-open
# For F2-ZERO use WINDOW=0.010, OBSERVATION=0.010, ADAPTER_KIND=f2-zero.
# For F2-START use WINDOW=0.010, OBSERVATION=0.002, ADAPTER_KIND=f2-start.
# For BYPASS-NEG use ADAPTER_KIND=bypass-neg and CHECK_KIND=bypass.
# For short cases use the corresponding adapter label and checker kind.
rm -f host.raw.fifo adapter.raw.fifo checked.fifo supplement.fifo
mkfifo host.raw.fifo adapter.raw.fifo checked.fifo supplement.fifo
trap 'rm -f host.raw.fifo adapter.raw.fifo checked.fifo supplement.fifo' EXIT
pigz -c <checked.fifo >TRACE.tsv.gz & CHECKED_GZIP_PID=$!
pigz -c <supplement.fifo >supplemental.tsv.gz & SUPP_GZIP_PID=$!
/tmp/matrix07-fault-normalize \
  adapter.raw.fifo checked.fifo supplement.fifo adapter-report.txt \
  "$TSTOP" "$ADAPTER_KIND" "$TF" "$WINDOW" 25e-9 \
  >adapter.stdout 2>adapter.stderr & ADAPTER_PID=$!
(set -o pipefail; tee adapter.raw.fifo <host.raw.fifo | pigz -c >raw.tsv.gz) & TEE_PID=$!
set +e
SPICE_SCRIPTS="$SPICE_SCRIPTS" /private/tmp/matrix07-fault-tracked-host-09 \
  case.cir 3600 "$TSTOP" host.raw.fifo first-invalid.tsv \
  >host.stdout 2>host.stderr
HOST_RC=$?
wait "$TEE_PID"; TEE_RC=$?
wait "$ADAPTER_PID"; ADAPTER_RC=$?
wait "$CHECKED_GZIP_PID"; CHECKED_GZIP_RC=$?
wait "$SUPP_GZIP_PID"; SUPP_GZIP_RC=$?
set -e
printf 'host_rc=%s tee_rc=%s adapter_rc=%s checked_gzip_rc=%s supplemental_gzip_rc=%s\n' \
  "$HOST_RC" "$TEE_RC" "$ADAPTER_RC" "$CHECKED_GZIP_RC" "$SUPP_GZIP_RC" | tee host.exit
test "$HOST_RC" -eq 0
test "$TEE_RC" -eq 0
test "$ADAPTER_RC" -eq 0
test "$CHECKED_GZIP_RC" -eq 0
test "$SUPP_GZIP_RC" -eq 0
gzip -t raw.tsv.gz TRACE.tsv.gz supplemental.tsv.gz
```

The host exit, source/deck hashes, and simulator stderr are mandatory even if
the trace is incomplete. Do not treat a callback-free run, a low gate, or a
solver exit alone as protection evidence.

For the settled crest/zero cases, verify the actual source voltage in the
fault trace at the predeclared event before accepting the checker result. The
normalized trace has time in field 1 and `v(acsrc,acn)` in field 2; use a
1%-of-peak tolerance (the 120 Vrms source peak is about 169.7056 V):

```sh
if [ "$CASE" = F2-ZERO ]; then
  AC_TARGET=0
else
  AC_TARGET=169.7056
fi
gzip -cd TRACE.tsv.gz | awk -v tf="$TF" -v target="$AC_TARGET" \
  'NR>1 { d=$1-tf; if (d<0) d=-d; if (d<best) {best=d; t=$1; ac=$2} }
   END { printf "nearest_source_sample_s=%.17e ac_v=%.9e dt_s=%.3e\n", t, ac, best;
         a=ac; if (a<0) a=-a; err=a-target; if (err<0) err=-err;
         if (best>2e-9 || err>1.6971) exit 1 }'
```

For `F2-START`, skip this settled-phase target and instead retain the measured
source sample and the 10 ms healthy ARM/PERMIT/q/en prefix evidence in the
adapter report. A source-phase mismatch or missing startup prefix is an
unexecuted case, not a widened event window.

The adapter retains the exact 17-column checker schema plus branch-current and
mutation-marker evidence. The FIFO chain uses the same strict 25 ns maximum
gap as the checker; a larger gap is a failed capture, not a reason to widen
the bound. Use `sw-short`, `diode-short`, `both-short`, `bypass-neg`, or
`f2-start` for the corresponding materialized labels. The checker CLI uses
`switch-short` and `bypass` for its own kind names; preserve both names in the
case receipt.

Run the unchanged checker from a FIFO so its `read_to_string` path consumes
the compressed normalized trace without retaining a second giant file:

```sh
mkfifo checker.fifo
gzip -cd TRACE.tsv.gz >checker.fifo & TRACE_GZIP_PID=$!
set +e
/tmp/matrix07-fault-checks checker.fifo "$TSTOP" "$CHECK_KIND" "$TF" \
  "$WINDOW" 2e-6 "$OBSERVATION" 25e-9 \
  >checker.stdout 2>checker.stderr
CHECK_RC=$?
wait "$TRACE_GZIP_PID"; TRACE_GZIP_RC=$?
set -e
rm -f checker.fifo
printf 'checker_rc=%s trace_gzip_rc=%s\n' "$CHECK_RC" "$TRACE_GZIP_RC" | tee checker.exit
test "$TRACE_GZIP_RC" -eq 0
```

For F2-CREST and F2-ZERO, only `PASS` is a positive model-screen result;
retain the reported detector time, turn-off delay, channel peak, and passive
peak. For SW-SHORT and BOTH-SHORT, `PROTECTION_GAP` is the expected
categorical negative classification regardless of whether the measured
channel current is above or below the threshold; gate-off cannot earn
interruption credit for a failed-short kind. Preserve the adapter report's
actual channel/body/inductor and branch-current maxima independently of that
classification. For BYPASS-NEG, invoke the checker with `bypass` and expect
`FAIL protection detector is bypassed`; this is a checker negative control,
never a circuit pass. DIODE-SHORT remains a normal checker classification but
is gated on the reviewed diode branch model.

## 5. Retention and unresolved decisions

Each case directory retains only the source/deck receipt, `raw.tsv.gz`,
`TRACE.tsv.gz`, `supplemental.tsv.gz`, adapter report, checker stdout/stderr
and exit files, host stdout/stderr and exit, first-invalid snapshot, and a
small `COMMANDS.txt` containing exact commands and binary/source hashes. The
raw and normalized streams are compressed directly from FIFOs; no giant
uncompressed raw or normalized copy is retained.

Before the parent authorizes the first campaign launch, resolve:

1. the 650 ms extension's final normal checker result and exact trace hash;
2. the measured crest/zero row selection against the proposed phase times;
3. the source/include and host-binary hashes for each materialized case;
4. the F2-START 10 ms healthy ARM/PERMIT/q/en prefix and its measured event;
5. the diode branch model review before DIODE-SHORT or BOTH-SHORT; and
6. any adapter/checker failure as a data or provenance failure, rather than
   widening event windows, timing gaps, node thresholds, or observation
   horizons after the fact.

No result from this runbook qualifies hardware, fuse interruption, thermal
behavior, component ratings, or mains safety. It produces model-trace evidence
only after the stated source and normal-prefix gates pass.
