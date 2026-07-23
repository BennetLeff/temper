---
title: "Regression baseline's net_count used a different definition than the checker — false-positive regression on a healthy board, masking a real disconnected buck converter"
date: "2026-07-17"
category: logic-errors
module: temper_placer
problem_type: logic_error
component: service_object
symptoms:
  - "temper-placer regression exits 1 with 'REGRESSION: net_count: 92.0 vs baseline 150.0 (-58.0)' against a board that had not actually lost any real connectivity"
  - "gen_pcb_skeleton.py prints 'Wrote pcb/temper.kicad_pcb: 144 footprints, 150 nets' at write time, but re-parsing the same file immediately after (oracle step, and independently the placer's own parser) reports 92 nets"
  - "CI's golden-check workflow appeared to pass after being repointed from a dead CLI subcommand to 'temper-placer regression', because piping its output through 'tail' masked the nonzero exit code"
root_cause: logic_error
resolution_type: code_fix
severity: medium
tags:
  - temper-placer
  - regression
  - net-count
  - metric-definition
  - ci-honesty
  - baseline
---

# Regression baseline's net_count used a different definition than the checker

## Problem

`power_pcb_dataset/baselines/temper_production_baseline.yaml` recorded
`net_count: 150`, but `temper-placer regression` (the tool that actually
enforces the baseline) computed 92 on an unchanged, healthy board and
failed with a large apparent regression (-58 nets). Investigating surfaced
two independent things: a metric-definition mismatch (this doc) and a
genuine disconnected rail (see Related Issues) that the same investigation
uncovered.

The 150 figure was written by counting all distinct net *names* in the
design (`gen_pcb_skeleton.py`'s own print statement, sourced from the raw
atopile-compiled netlist, `elec/build/default.net`). The 92 figure comes
from `parse_kicad_pcb`'s `_extract_nets_from_pcb`, which has always
filtered to `len(pins) >= 2` — nets with only one attached pin (unused
MCU GPIOs, literal no-connect pins, relay throws that are deliberately
unused, signals waiting on a connector that doesn't exist yet) are dropped
before the count, because they carry no placement/routing-relevant
information. Both numbers are individually correct for what they measure;
nobody had reconciled which one the regression baseline should record.

## Symptoms

- `temper-placer regression` fails with `net_count: 92.0 vs baseline
  150.0 (-58.0)` against a board with no actual connectivity loss.
- The failure looks identical in shape to a genuine dropped-connection bug
  (large net-count delta), so the natural first reaction is to suspect
  data loss in the KiCad export/parse round-trip.
- The CLI's exit code is correct (1) on failure, but piping its output
  through `tail` or similar in an ad-hoc verification command silently
  discards that exit code, making a failing check look like it passed —
  this is how the CI workflow swap in this arc was initially reported as
  "all green" when one of the six checks was still red.

## What Didn't Work

- Assuming the mismatch was a KiCad round-trip bug and looking for pads
  dropped during the `.kicad_pcb` write. The written file was correct —
  a direct regex count of `(net N "name")` entries inside pad definitions
  found all 150 names present, 125 of them with real pad references.
- Assuming it was a parser bug in `parse_kicad_pcb`. Instrumenting the
  exact grouping it performs (`comp.pins[].net` → dict → filter
  `len(pins) >= 2`) reproduced 92 directly from the written file with no
  discrepancy — the filter is deliberate, documented behavior, not a bug.
- The turning point was cross-referencing all 33 "dropped" net names
  against `elec/build/default.net` directly (the atopile compiler's own
  output, upstream of any KiCad export): every one of them was *already*
  single-node there. The loss, if it can be called that, happens at
  compile time in the `.ato` source, not in any later tool.

## Solution

Correct the baseline's `net_count` to match what the checking tool
actually measures (92, now 95 after the related buck-converter fix added
real connectivity), rather than the raw atopile net-name count:

```yaml
# power_pcb_dataset/baselines/temper_production_baseline.yaml
# Before:
component_count: 144
net_count: 150

# After:
component_count: 149  # +5 from the BuckConverter3V3 fix (see related doc)
net_count: 95         # >=2-pin connectivity, matching temper-placer
                       # regression's own definition
```

`power_pcb_dataset/golden_manifest.yaml`'s description field now states
the definition explicitly ("net_count is >=2-pin connectivity...the design
declares 151 named nets total, ~56 of which are single-pin/no-connect by
design") so a future reader doesn't have to re-derive it from scratch.

## Why This Works

There are two legitimate, different questions a "net count" can answer —
"how many nets does the design declare" and "how many nets have real
routing-relevant connectivity" — and this codebase has tooling that
answers each one at a different point in the pipeline
(`gen_pcb_skeleton.py`'s write-time print vs. `parse_kicad_pcb`'s
`_extract_nets_from_pcb`). A regression baseline is only meaningful if it
was populated by the same code path that checks it. Recording the
write-time print's number and checking it with the parse-time filter's
number compares two different metrics under one field name.

## Prevention

- **When writing a baseline value, use the exact function that will check
  it**, not an adjacent tool that happens to report a similarly-named
  number. If two codepaths in the same pipeline can produce different
  counts for the same-sounding quantity, that's a sign the metric itself
  needs a single canonical source (a shared helper both the writer and the
  checker call), not just careful discipline about which one to use.
- **Never trust a piped command's apparent success without checking the
  real exit code.** `cmd | tail -N` reports `tail`'s exit status, not
  `cmd`'s. When verifying a CI check locally, redirect to a file (or use
  `${PIPESTATUS[0]}` / `set -o pipefail`) and check `$?` on the actual
  command, not the last stage of a pipe.
- **A regression check firing is a report to investigate, not a number to
  suppress.** The instinct to "just bump the baseline to match reality" is
  correct only after confirming what the new number actually represents.
  In this case doing that investigation first — rather than reflexively
  setting `net_count: 92` — is what surfaced the real bug in the sibling
  finding below.

## Related Issues

- [`docs/solutions/logic-errors/config-key-whitelisted-but-never-parsed-slot-generation.md`](config-key-whitelisted-but-never-parsed-slot-generation.md)
  — the sixth silent-config-drop bug in this same arc; this is closer to a
  seventh, though it's a metric-definition mismatch rather than a dropped
  assignment. Same underlying lesson: two parts of a pipeline each compute
  "the same" value independently, and nothing reconciles them.
- **The genuine bug this investigation surfaced**: `BuckConverter3V3`
  (`elec/src/modules.ato`) was a stub — it declared an inductor and output
  caps but never instantiated the switching IC or wired VIN→SW→L→VOUT, so
  `power_out.vcc` had zero connection back to `power_in.vcc`. This is what
  made `l_out`'s two pins show up as the one genuinely informative entry
  among the 33 "dropped" nets (the other 32 were legitimate no-connects).
  Fixed in the same change: real `LMR51430` topology per TI datasheet
  SLUSF4A Table 9-1 (Vfb=0.6V typ — an existing but unverified comment on
  the module had claimed 1.0V "per SLUSF42", both the value and the
  document number were wrong). Worth its own compound doc if this class of
  "declared-but-unwired placeholder module passing ato build" recurs.
- `docs/plans/2026-07-15-001-feat-artifact-identity-provenance-plan.md`,
  unit U6/U7 — the placement re-baseline whose regression check this
  affects, and the planned CI-enforcement unit that should make this kind
  of drift visible automatically rather than requiring manual discovery.
