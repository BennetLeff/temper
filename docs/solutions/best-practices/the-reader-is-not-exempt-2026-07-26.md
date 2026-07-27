---
title: "The reader is not exempt — six ways a shell pipeline lied about a real measurement in two days"
date: "2026-07-26"
category: best-practices
module: development_workflow
problem_type: best_practice
component: development_workflow
severity: high
applies_when:
  - "piping a command's output through tail, head, or grep before checking its exit code or full text"
  - "a result surprises you — a working thing looks broken, or a broken thing looks fine"
  - "grepping for a string that a formatter or terminal may have line-wrapped"
  - "inferring a code path ran because you saw no warnings, rather than confirming it executed"
  - "reading an evidence file, log, or report without checking its own timestamp against 'now'"
tags:
  - measurement-pipeline
  - shell-pipeline
  - exit-code
  - head-truncation
  - grep-line-wrap
  - stale-evidence
  - validate-the-validator
  - false-negative
---

# The reader is not exempt — six ways a shell pipeline lied about a real measurement in two days

## Context

`docs/solutions/best-practices/assert-input-preconditions-not-just-output-metrics.md`
establishes that a check can exist, run, and still be structurally blind to
the defect it exists to catch. This is the same failure one layer closer to
the terminal: **the shell pipeline between a real measurement and the person
reading it is itself a validator, and it fails silently, just as often.** Over
two days on this project it did, six separate times, and every one was the
reading, not the underlying measurement:

| What happened | Consequence |
|---|---|
| `cmd \| tail` then `echo $?` | read `tail`'s exit status, not the command's — reported a working gate as broken |
| `grep ... \| head -10` | truncated before the real hit count — nearly produced "zero production callers" |
| `\| head` on a long run's output | destroyed a ten-minute route's entire result |
| `grep` for a string that was line-wrapped by the terminal/formatter | missed a match that was present in the file |
| inferred "the checks ran" from the absence of warnings | the stage had never executed; the claim was published, then corrected |
| read a date-stamped evidence file from the previous day | reported a stale value as current |

Full incident detail and the measurement context: `docs/METHODOLOGY.md` §5,
"The reader is not exempt either."

## Guidance

1. **Capture raw to a file, then query the file.** Do not filter in the same
   pipeline that produces the value:
   ```bash
   # WRONG — the pipe's exit status is head's, not the command's
   long_running_command | tail -20; echo $?

   # RIGHT — capture unfiltered, inspect separately
   long_running_command > /tmp/out.log 2>&1; echo $? > /tmp/out.exit
   cat /tmp/out.exit
   tail -20 /tmp/out.log
   ```
2. **Exit codes never through a pipe.** `$?` after a pipeline reports the
   last command in the pipe (`tail`, `head`), not the producer. Redirect to a
   file and check the code before filtering.
3. **`head`/`tail` only when the value's position in the output is already
   known.** A truncated `grep | head -10` reads like "there are few matches"
   when it means "there were at least 10, and I stopped looking." Count first
   (`grep -c`), then decide whether to page.
4. **Prefer structured output** (JSON, a count on its own line) over scraping
   free text — it removes the line-wrap and truncation failure modes at the
   source.
5. **Do not infer execution from silence.** "No warnings printed" is
   consistent with both "it ran clean" and "it never ran." Assert execution
   happened (a log line, a count, a file write) before treating absence of
   error as a pass — this is the vacuity axis in `docs/METHODOLOGY.md` §5.
6. **Check the date on anything you didn't just generate.** An evidence file,
   a log, a cached report — read its own timestamp, not just its content,
   before treating it as current.
7. **When a result surprises you, suspect the reading before the result.**
   This single heuristic is what caught most of the six instances above; the
   failures were the occasions it was not applied. Before writing "X is
   broken" or "X is zero," re-derive the number a second, different way
   (a different tool, a raw file, a manual count) and see if it still surprises
   you.

## Why This Matters

Every one of these six failures had a real, correct measurement sitting one
layer beneath the misread — the gate was working, the callers existed, the
route had finished, the string was present, the checks had not yet run, the
evidence was from yesterday. None of them were bugs in the thing being
measured. All six cost real time: a route re-run from scratch after a `head`
truncation, a correction issued after a "the checks ran" claim was published,
and a diagnosis nearly built on "zero production callers" that a full (not
head-truncated) grep would have shown were plentiful. The failure mode is
cheap to prevent and expensive to discover after the fact, because a misread
result looks exactly like a real one until someone re-derives it differently.

This generalizes past shell pipelines: any layer that summarizes, truncates,
or filters a measurement before a human or an agent sees it — a log tailer, a
dashboard's "top 10," a chat summary of a long tool output — is a validator
over the real result, and inherits the same obligation to prove it isn't
lying.

## When to Apply

- Before trusting any command's exit code that was read after a `|`.
- Before concluding "zero," "none," or "no matches" from a piped `grep` or
  `find` — re-run without the trailing filter and compare counts.
- Before treating "no errors were printed" as "the stage executed" — find the
  positive evidence that it ran (a line count, a log entry, a written file).
- Before using any file as "current" evidence — check its mtime or embedded
  date against the actual current date.
- Whenever a measurement contradicts your prior belief. That is precisely the
  moment the reading is most likely to be the thing that's wrong, and the
  moment it's most tempting to accept the number because it fits.

## Examples

```bash
# WRONG — head -10 on a grep looking for "zero production callers"
grep -rn "old_api_call(" src/ | head -10
# 10 lines shown, conclusion drafted: "only 10 callers, all in tests"
# but grep -c shows:
grep -rc "old_api_call(" src/ | awk -F: '{s+=$2} END {print s}'
# 47 — the head silently dropped 37 real callers

# WRONG — exit status of the pipe, not the command
some_long_gate_check.sh | tail -5
echo $?     # this is tail's exit code (almost always 0), not the gate's

# RIGHT
some_long_gate_check.sh > /tmp/gate.log 2>&1
gate_status=$?
tail -5 /tmp/gate.log
echo "gate exit: $gate_status"
```

## Related

- `docs/solutions/best-practices/a-measurement-carries-its-commit-2026-07-26.md`
  — the sibling failure one layer further out: a clean pipeline run against a
  *stale checkout*, rather than a clean pipeline misread. Four instances in
  one day, now outnumbering the six catalogued here.
- `docs/METHODOLOGY.md` §5, "The reader is not exempt either" — the rule this
  doc instantiates, with the same six-instance table
- `docs/solutions/best-practices/assert-input-preconditions-not-just-output-metrics.md`
  — the sibling failure one layer in: a check that runs and is structurally
  blind, rather than a reading that is structurally misleading
- `docs/solutions/best-practices/three-silent-failures-measurement-pipeline-2026-07-07.md`
  — a related but distinct failure class: the *tool* silently failing
  (`kicad-cli` exit 3, no JSON) rather than the *reader* misreading a tool
  that succeeded
- `docs/solutions/best-practices/lie-proof-the-green-before-believing-it-2026-07-11.md`
  — same discipline applied to silently-dropped constraints rather than a
  misread pipeline
