<!-- provenance: commit=96fb58871c6d3951c70342784f9bcc07119bd7e1 dirty=false (re-pointed 2026-08-05: the cited 197314aa658b9cded556bfd480683cbf5c1705c7 was a pre-squash #699 branch commit, orphaned by force-push; the zombie-aware timeout probe fix landed at 96fb58871c6d3951c70342784f9bcc07119bd7e1 (#699), which is the cited commit) -->

# Flaky grandchild-reap test — observation-semantics bug, not a helper leak or a tight deadline

## Summary

`tests/placer/cp_sat/test_parallel_drc_helper.py::test_timeout_reaps_the_process_group`
was the last red on main's Regression Suite: it failed with
`Failed: grandchild survived the timeout` on **every** Regression Suite run
since the test landed (6/6 runs, all dated 2026-08-04 — run ids
30933256144, 30933052476, 30932485241, 30927563400, 30926908018,
30885909766 — each exactly one FAILED line for this test), while passing
4/4 locally at 1.1–1.6s. The prior triage
(`docs/evidence/2026-08-04-designrules-parse-fix.md`) classified it
"flaky-timing, not a real bug" on the strength of the local-only
observation. The CI logs show it was not flaky at all: it was a
deterministic failure on the CI container, masked by the fact that no
green CI run of this test has ever existed.

## Triage: deadline vs. logic vs. observation semantics

The helper under test (`packages/temper-placer/tests/placer/cp_sat/_parallel_drc.py`,
`run_drc_loud`) starts each subprocess with `start_new_session=True` and on
`TimeoutExpired` runs `os.killpg(proc.pid, SIGKILL)` then reaps the direct
child with `proc.communicate()`. Its reap logic is correct and complete:

- The fake kicad-cli (`_FAKE_KICAD_CLI_ORPHAN`) spawns its grandchild with a
  plain `subprocess.Popen` (no `start_new_session`), so the grandchild is in
  the fake's process group; `killpg` reaches it. SIGKILL is uncatchable, so
  the grandchild cannot keep running after the group kill.
- There is no poll-loop or reap deadline in the helper — the group kill is a
  single synchronous signal.

The failure therefore is **not** (b) a leak and **not** (a) a deadline too
tight to reap a live-but-slow group. It is an **observation-semantics bug in
the test's own poll loop**: `os.kill(pid, 0)` succeeds on **zombies** as well
as on live processes. After the helper's killpg lands, the grandchild is dead
— but its corpse sits unreaped under the container's PID 1, and the test's
"is it alive" probe cannot tell an unreaped corpse from a leaked live
process.

### Why the zombie persists on CI but not locally (empirical)

- Local (macOS): PID 1 is launchd, which reaps orphaned children promptly.
  Measured: a SIGKILLed group's grandchild is fully reaped in **0.004s**
  (probe, see below), far shorter than the poll interval — so the first
  `os.kill` raises `ProcessLookupError` and the test passes in ~1s.
- CI (`.github/workflows/regression.yml`, `ghcr.io/bennetleff/temper-ci:latest`
  = ubuntu:24.04 container): PID 1 is the GitHub Actions runner's internal
  Node.js helper, which does not reap orphaned children — a well-documented
  GitHub Actions container behavior (orphaned zombies accumulate for the
  container's lifetime). `os.kill(pid, 0)` therefore keeps succeeding on the
  grandchild zombie for the entire 5s observation window, and the test
  `pytest.fail`s. CI log timestamps confirm the shape: the FAILED line is
  ~6.1s after the previous test (1s helper timeout + full 5s window).

A pure deadline raise (5s → anything) could not fix this: on the CI
container the zombie is never reaped, so the probe never observes it gone.
The fix must make the observation distinguish *dead-but-unreaped* from
*alive*.

### Probe evidence (local, macOS, 2026-08-05)

`os.kill(pid, 0)` on a deliberately-created zombie: succeeds (`os.kill
succeeds=True`), while `ps -o stat=` reports `Z`. After `killpg` of a group
containing a grandchild, the grandchild is observed as a zombie for a few ms
before launchd reaps it (`reaped at t=0.004s`). A *detached* grandchild
(`start_new_session=True`, its own pgid) survives both `kill(parent)` and
`killpg(parent-group)` and keeps running in state `S` — the leak scenario the
assertion exists to catch.

## The fix

`packages/temper-placer/tests/placer/cp_sat/test_parallel_drc_helper.py`:

1. **Zombie-aware observation** (the substantive fix): the poll loop now
   treats "process observable but a zombie" as reaped. `ps -o stat=` reports
   `Z` only for zombies and no live state contains `Z`, so it is a precise
   cross-platform signal; on `ps` failure the check reports "not a zombie"
   (fail-closed — a genuinely leaked process still fails the assertion). A
   zombie proves the SIGKILL landed, so it is *not* a leak.
   - `_is_zombie(pid)` helper added at `test_parallel_drc_helper.py:125`.
   - Observation loop at `test_parallel_drc_helper.py:259-276` (window 5s →
     30s, deliberately generous: the assertion is about eventual reaping,
     not latency).
2. **Setup slack** (`test_parallel_drc_helper.py:245-256`): the test's helper
   timeout was 1s, which also raced the fake's own setup under load — a cold
   python3 startup exceeding 1s got the fake SIGKILLed before it wrote the
   grandchild pidfile (`AssertionError: grandchild never started`, observed
   locally under 60+ concurrent agent worktrees). Raised to `timeout=5`; the
   fake sleeps 60s, so the timeout path is still exercised and the reap
   assertion is unchanged, but setup now has a 5x margin.

The assertion is **not** weakened: a leaked grandchild runs `time.sleep(60)`
in live state `S`, never matches the zombie check, and still fails the test.
Verified with a detached-grandchild negative test (fake spawns the
grandchild with `start_new_session=True` and `stdout/stderr=DEVNULL`, sleeps
120s): the fixed test fails with `grandchild survived the timeout` after
35.0s (5s helper timeout + 30s window).

## Verification (commit e162c37b4, clean tree)

| Check | Result |
|-------|--------|
| `test_timeout_reaps_the_process_group` | 15/15 PASS (5.09–5.36s each: 10 runs pre-amend on identical content + 5 runs on the committed tree) |
| Full `test_parallel_drc_helper.py` | 8 passed |
| Negative test (detached, leaked grandchild) | FAILS assertion as required (35.0s) |
| `tests/placer/cp_sat/test_regression_drc.py` (main `run_drc_samples` consumer) | 4 passed, 1 skipped (documented pre-existing KNOWN GAP, unrelated) |
| `ruff check` on touched file | clean |
| `uv run python scripts/import_linter_gate.py` | PASSED — 0 new violations |
| `scripts/check_evidence_provenance.py` | PASSED (this file) |

## Why CI failed and why this fixes it

The CI container's PID 1 does not reap orphaned zombies, so the old test's
`os.kill(pid, 0)` probe observed the SIGKILLed grandchild as "alive" for the
entire 5s window on every run (6/6, deterministic). The new observation
correctly reads the process state: on CI the grandchild is a zombie
(`ps` → `Z`) the moment the helper's killpg lands, so the loop breaks
immediately and the test passes. Locally the grandchild is reaped in ~4ms
and the loop breaks on `ProcessLookupError` as before. In the only case the
assertion exists for — a helper that leaks a live grandchild — the process
is in state `S` and the test still fails after the 30s window.

## Follow-ups

- None required. The helper's post-kill `proc.communicate()` can block for a
  leaked grandchild's lifetime if the leaked process inherits the helper's
  stdout/stderr pipes (observed while building the negative test; the second
  `communicate()` has no timeout). This only matters in the leak case (a
  helper bug this test is designed to catch, not the flake being fixed) and
  is out of scope for this surgical test fix; noted here for completeness.
