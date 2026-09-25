# Harness lifecycle audit (read-only)

This audit compares the frozen runner45 lifecycle with the BYPASS-NEG launch
and postcapture wrappers. It does not signal processes, launch a solver, open a
FIFO, or read a raw archive. The stale-process evidence was supplied by the
existing `processes-before.json`, `path-inspection.json`, and cleanup receipt.

## What runner45 currently guarantees

* `ChildGuard` owns each child and kills/waits in `Drop`
  (`faults/native-runner-45/supervisor.rs:39-50`). The stage-2 group timeout
  and disk-floor failure call `kill_reap` for every adapter, validator,
  decoder, and decompressor child (`supervisor.rs:283-291`).
* Capture failure paths kill/reap the opposite side: native-host failure,
  missing/zero-point metadata, compressor failure, disk-floor failure, and the
  bounded capture timeout are handled in `supervisor.rs:227-280`. Positive
  point output is drained before semantic metadata rejection
  (`supervisor.rs:240-273`), preserving a diagnosable archive.
* The runner refuses pre-existing output names, including its two FIFOs, and
  creates only verified FIFOs (`supervisor.rs:132-143`). It removes the two
  FIFOs after the owned run (`supervisor.rs:328-329, 364-367`). Source/include
  closure and tool hashes are checked before and after the pipeline
  (`supervisor.rs:330, 356-360`).
* Capture timeout is bounded by `wall_seconds + export_timeout + 10` and stage 2
  by `export_timeout` (`supervisor.rs:348, 355`). The launch packet passes 3600
  s and 900 s respectively. The parent review confirms runner45 is a reviewed
  successor with kill/reap and endpoint/row-count guards; it has no full-case
  execution of its own (`faults/native-runner-45/parent-review.json:14-23`).

These guarantees apply when the supervisor remains alive and reaches its Rust
cleanup paths. An external SIGKILL, host crash, or terminal kill of the parent
shell can bypass Rust `Drop`; an interrupted run can therefore leave output
files or FIFOs for the fresh-output guard to reject on the next attempt.

## Launch and postcapture lifecycle

`settled-bypass-neg-66/launch.sh` checks disk space and solver inventory before
and after source copy, then starts runner45 and a monitor in the background
(lines 83-120). It waits for the runner, records `runner.exit`, waits for the
monitor, records `monitor.exit`, and returns the runner code (lines 122-129).
The monitor is explicitly observation-only: it samples descendants and exits
when the runner disappears or its observation deadline is reached; it does not
kill or reap campaign children (`host/resource-monitor-37.sh:38-44`). The launch
shell has no EXIT/INT/TERM trap around those background jobs. If the shell is
interrupted, the runner/monitor can outlive the shell; runner45 itself still
owns its children if it remains alive, but an abandoned runner is outside that
contract.

The reviewed `settled-bypass-postcapture-76/run.sh` has an EXIT trap that writes
`analysis.exit` (lines 27-32), checks the capture/source closure, and records
`PIPESTATUS` for each archive pipeline (lines 80-126). It has disk checks before
stages but no wall timeout around the five pipelines; a stalled decoder/reader
can therefore keep the shell and its pipeline descendants alive indefinitely.
The separate legacy wrapper also records a cleanup trap and removes `.running`
on failure (`legacy-strict.sh:95-101`), but its raw hash and archive pipeline
are likewise not wrapped by an external time limit (`legacy-strict.sh:50-56,
105-117`). These wrappers consume a completed gzip archive directly; they do
not create the runner45 FIFOs.

## What the stale evidence shows

The old ad-hoc native-export probe group 61540 spawned gzip readers on two
FIFOs and remained alive for over a day, with descendants 61554/61555/61556
(`host/harness-lifecycle-144/processes-before.json:2-46`). Separate wildcard
`sha256sum` jobs 92202 and 92344 included `trace.fifo` among ordinary paths and
also remained alive (`processes-before.json:47-100`). That is an old shell/hash
pattern, not runner45: runner45 hashes only regular source/include/tool paths,
and its `ensure_absent` list refuses stale FIFO/output names rather than
wildcarding them (`supervisor.rs:56-65, 82-97, 132-143`). The path inspection
found two unrelated stale FIFOs but no native-export probe FIFOs at inspection
time (`host/harness-lifecycle-144/path-inspection.json:2-25`). Parent cleanup
then removed only freshly identity/cwd-verified abandoned process groups; no
raw or source files were deleted (`cleanup-receipt.json:2-24`).

## Smallest future-run prevention

Keep runner45 unchanged. At the launch-wrapper boundary, add one reviewed
lifecycle guard for future runs: put runner and monitor in a known process group
and install an INT/TERM/EXIT trap that, on abnormal wrapper exit, signals that
verified group, waits for both PIDs, and records the interruption before
returning. Separately invoke each postcapture/legacy pipeline under a bounded
external timeout and retain its timeout status in the existing exit receipt.
For hash/index commands, enumerate an explicit regular-file manifest (or use a
regular-file predicate) and reject FIFOs before opening paths; never use a
wildcard that can open `trace.fifo`. These are wrapper/command hygiene changes,
not changes to runner45, checker criteria, source decks, or evidence claims.

No lifecycle audit can turn the cleaned stale jobs into campaign evidence. The
current BYPASS result and all future case statuses remain governed by their
source-bound receipts and parent review.
