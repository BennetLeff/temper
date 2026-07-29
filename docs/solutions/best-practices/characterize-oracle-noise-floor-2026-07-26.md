---
title: "Characterise an oracle's noise floor before gating on it — kicad-cli's shorting_items varies 113-124 on a byte-identical file"
date: "2026-07-26"
category: best-practices
module: pcb-drc
problem_type: best_practice
component: testing_framework
severity: medium
applies_when:
  - "gating a CI check or acceptance test on a numeric field from an external tool you did not write"
  - "two measurements of the same artifact disagree and you are about to investigate it as a discrepancy"
  - "validating a fix by comparing a single before/after run"
  - "a metric's spread has never been measured on identical input across multiple runs"
tags:
  - oracle-noise-floor
  - kicad-cli
  - drc
  - non-determinism
  - median-and-range
  - before-after-comparison
  - external-tool-validation
---

# Characterise an oracle's noise floor before gating on it

## Context

`kicad-cli pcb drc` was treated as ground truth for the router's shorts count.
Two independent measurements of the exact same routed board — one from an
agent's diagnosis, one from re-measurement on the branch — reported `113` and
`123` `shorting_items`. That 10-count gap was investigated as a possible
router non-determinism bug before anyone ran the tool twice on the same file.

Five consecutive `kicad-cli pcb drc` runs on one byte-identical
`pcb/temper.kicad_pcb`:

| run | total | `shorting_items` | `clearance` | `unconnected` |
|---|---|---|---|---|
| 1 | 1456 | **124** | 499 | 276 |
| 2 | 1446 | **113** | 499 | 276 |
| 3 | 1451 | **119** | 499 | 276 |
| 4 | 1454 | **120** | 499 | 276 |
| 5 | 1456 | **123** | 500 | 276 |

`shorting_items` ranges 113–124 — a spread of 11, about 9%, on identical
input. The router itself is deterministic: two independent routing runs
produced byte-identical geometry once regenerated `tstamp`/`uuid` fields were
stripped, same 3,265 segments / 48 vias / 98 zones. `unconnected` was rock
stable at 276 across all five DRC runs and `clearance` moved by exactly one —
the instability is specific to the pairwise copper-overlap check, consistent
with a parallelised comparison racing on violation dedup. The 113-vs-123 "gap"
that looked like a discrepancy worth chasing was two ordinary samples of the
same noisy distribution. Full data: `docs/evidence/2026-07-25-shorting-items-diagnosis.md`;
the general rule: `docs/METHODOLOGY.md` §5, "The oracle is not exempt."

## Guidance

1. **An external tool used as ground truth is a validator like any other, and
   inherits the same falsification obligations** (`docs/METHODOLOGY.md` §5)
   — including the one most often skipped for third-party tools: proving it's
   reproducible.
2. **The cheapest axis to apply is invariance: run the tool N times on
   byte-identical input and compare.** No design change, no fault injection,
   no independent implementation needed — just repetition. This is also the
   cheapest possible experiment to run before escalating a discrepancy to a
   diagnosis effort.
3. **A gate threshold below the oracle's measured noise floor cannot
   distinguish signal from noise.** If `shorting_items` moves by up to 11
   between identical runs, a regression gate with a delta tolerance smaller
   than 11 is a random number generator wearing a verdict's clothing — it
   will fail or pass a genuinely unchanged board depending on which sample it
   happened to draw.
4. **A single before/after measurement is not evidence when the oracle is
   noisy.** Report median and range over N ≥ 5 runs. A delta smaller than the
   spread proves nothing about whether a fix worked — it could be entirely
   explained by which run happened to land where in the 113–124 band.
5. **Stability is field-specific, not tool-wide.** Do not generalize "kicad-cli
   is noisy" to every field it reports — `unconnected` was stable to zero and
   `clearance` to one. Characterise each field you gate on independently; a
   noisy field sitting next to a stable one in the same JSON blob is easy to
   miss if you only check the field you already trust.
6. **When two measurements disagree, run the cheap repeatability check before
   building a diagnosis on top of the disagreement.** The 113-vs-123 gap
   consumed investigation time as a suspected router bug before the five-run
   spread showed both numbers were unremarkable samples.

## Why This Matters

Every routing-quality claim in this project rested on an oracle whose
reproducibility had never been tested — the project had audited its own
router thoroughly (byte-identical output, deterministic) while treating the
measuring instrument as exempt from the same scrutiny. This is the reference
failure (`docs/METHODOLOGY.md` §7) one layer further out: instead of a check
being blind to a defect, the *number itself* has an error bar nobody had
measured, and every downstream consumer — `power_pcb_dataset/drc_ceiling.json`,
corpus regression baselines, the "381 honest violations" figure in
`docs/STRATEGY.md` — inherited a false precision of ±0 when the true precision
was ±11. A rejected fix (`router_v6/short_rejection.py`) could not have been
validated the way it was being measured, independent of its own design defect,
because no single before/after comparison against this oracle can mean
anything below the noise floor.

## When to Apply

- Before setting or trusting any CI threshold sourced from a third-party
  tool's numeric output (DRC/ERC violation counts, linter counts, coverage
  percentages from an external instrumenter).
- Before treating two measurements of the same artifact as a discrepancy
  worth investigating — run the oracle 5× on one of the two artifacts first.
- Before claiming a fix worked from a single before/after number — capture
  median and range on both sides.
- When a metric has multiple sub-fields (here: `shorting_items`, `clearance`,
  `unconnected` in one DRC report) — characterise each independently rather
  than assuming uniform stability.

## Examples

```bash
# Measure an oracle's noise floor before gating on it
for i in 1 2 3 4 5; do
  kicad-cli pcb drc --output "/tmp/drc_run_$i.json" --format json pcb/temper.kicad_pcb
  jq '.violations | group_by(.type) | map({type: .[0].type, count: length})' \
    "/tmp/drc_run_$i.json"
done
# Compare the five outputs per violation type; report median + range per
# field, not a single number, before setting any threshold against it.
```

```
# WRONG: treating a single before/after delta as proof
before: shorting_items = 123
after:  shorting_items = 113
claim:  "fix reduced shorts by 10"          <- within the measured 11-count
                                                noise floor; unsupported

# RIGHT
before: median 120, range 113-124 (N=5)
after:  median 121, range 114-125 (N=5)
claim:  "no measurable change" -- delta smaller than the noise floor
```

### Recurrence, 2026-07-29: caught by re-running the control

The same trap, on the same tool, three days later -- and this time it was
caught before it became a claim. While deciding whether two netclasses
(`Ground`, `HighSpeed`) could be safely defined in `pcb/temper.kicad_pro`,
the measurement was a DRC violation count before and after adding them:

```
baseline           2042
after adding       2043            <- looks like "+1 violation, the change costs something"
baseline, re-run   2044            <- the CONTROL moved by 2 on its own
```

The +1 was inside the tool's own noise. Re-running the *unmodified*
baseline is what exposed it; comparing only before-vs-after would have
produced a plausible, precise, wrong finding and probably blocked a
correct change.

The recovery that made it decisive: instead of comparing raw totals at
all, the report was filtered to violations naming the two rules in
question -- **0 before, 0 after**, an attributable delta rather than a
global one. Where a global count is noisy, an attributable subset can
still be exact.

Two rules worth carrying: re-run the control, not just the treatment; and
prefer a delta you can attribute to the thing you changed over a total
that anything on the board can move. See
`docs/evidence/2026-07-28-orphan-net-class-ground-highspeed.md`.

## Related

- `docs/METHODOLOGY.md` §5, "The oracle is not exempt" — the rule this doc
  instantiates, with the same five-run table
- `docs/evidence/2026-07-25-shorting-items-diagnosis.md` — full diagnosis,
  including why the accompanying fix was rejected independent of this finding
- `docs/solutions/best-practices/three-silent-failures-measurement-pipeline-2026-07-07.md`
  — a related but distinct oracle failure: `kicad-cli` failing to *load* the
  board at all (exit 3, no JSON) rather than reporting a noisy number on a
  board it loaded successfully
- `docs/solutions/best-practices/lie-proof-the-green-before-believing-it-2026-07-11.md`
  — same "don't believe a green/precise number" discipline applied to
  silently-dropped constraints
