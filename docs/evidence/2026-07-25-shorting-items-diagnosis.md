# `shorting_items` diagnosis — zone-pour path exonerated

**Provenance: commit=UNKNOWN dirty=UNKNOWN** -- backfilled prior to the provenance gate's introduction (2026-07-26); no self-declared commit exists in this file's own content and none was fabricated. See .evidence-provenance-allowlist.

**Date:** 2026-07-25
**Board:** `pcb/temper.kicad_pcb` at outline (20,20)–(172,254)
**Status:** diagnosis **agent-reported, not independently reproduced**; the
accompanying fix was **rejected on review** (see below).

Answers the primary open question in
`docs/brainstorms/2026-07-25-router-drc-legal-completion-requirements.md`:
*are the shorts in the zone-pour path or in A\* traces?*

## Finding

Of the `shorting_items` measured on the routed production board with
`enable_zone_pours=True`:

| Class | Count | Nature |
|---|---|---|
| Involving a `(zone ...)` | **0** | **Zone-pour path is not implicated** |
| Pad-vs-pad, overlapping *before* routing | 62 | Placement / footprint-library defect |
| Involving routed `(segment ...)` / `(via ...)` | 51 | Router-emitted copper |
| — of which via-vs-existing-track | 26 | Via dropped without clearance check |

Reported total 113 vs. 123 measured on this branch. **Reconciled 2026-07-25 —
see below. Both are correct: `shorting_items` is not a reproducible metric.**

## Reconciliation: `shorting_items` is non-deterministic

The 113-vs-123 gap is not a difference in board, router, or method.

**The router is deterministic.** Two independent routing runs produced
byte-identical geometry after stripping regenerated `tstamp`/`uuid` fields —
same completion (0.7857), same 3,265 segments / 48 vias / 98 zones.

**`kicad-cli pcb drc` is not.** Five consecutive runs *on the same file*:

| run | total | `shorting_items` | `clearance` | unconnected |
|---|---|---|---|---|
| 1 | 1456 | **124** | 499 | 276 |
| 2 | 1446 | **113** | 499 | 276 |
| 3 | 1451 | **119** | 499 | 276 |
| 4 | 1454 | **120** | 499 | 276 |
| 5 | 1456 | **123** | 500 | 276 |

`shorting_items` ranges **113–124** on identical input — a spread of 11, about
9%. The agent's 113 is the observed minimum; the branch's 123 is near the
maximum. Both are samples of the same distribution.

Note the contrast: `unconnected` is rock-stable at 276 and `clearance` varies
by one. The instability is specific to `shorting_items`, consistent with
parallelised pairwise copper-overlap checks racing on violation dedup.

### Consequences — these matter more than the reconciliation

1. **Every figure gated on `shorting_items` is unreliable at ±11.** That
   includes `power_pcb_dataset/drc_ceiling.json`, the corpus regression
   baselines, and the "381 honest violations" figure carried in
   `docs/STRATEGY.md`.
2. **A single before/after comparison cannot validate a shorts fix.** A change
   of fewer than ~11 is indistinguishable from noise. The rejected
   `short_rejection.py` could not have been validated the way it was being
   measured, independent of its design defect.
3. **Acceptance condition 2 is strengthened:** any shorts fix must report
   median and range over **N ≥ 5 runs**, not a single measurement.
4. **`METHODOLOGY.md` §5's determinism relation was never applied to the
   measurement tool itself** — only to our own code. An external tool is as
   capable of being a blind metric as an internal one.

## Consequences

**The 62 pad-vs-pad shorts are not a router problem.** Pads overlap in the
pre-route board geometry — reported causes include a pad-height-exceeds-pitch
defect on the ESP32 module footprint and components placed closer together
than their pad sizes permit. No routing change can fix these; they need a
placement or footprint-library fix. They should be excluded from any
router-quality metric and tracked separately.

**Only ~51 are attributable to the router**, and over half of those are vias
placed without checking clearance against another net's existing track. That
is a specific, contained defect, not an architectural one.

**Zone pours are exonerated.** The `enable_zone_pours` default should not be
touched on account of shorts.

## Why the accompanying fix was rejected

The agent added `router_v6/short_rejection.py` (217 lines) — a post-emission
pass that deletes `(segment ...)`/`(via ...)` lines proven to overlap another
net's copper, on the fail-closed principle that an honest gap beats a silent
short. That principle is right, and it mirrors the existing
`_allow_forced_segments` precedent.

But the module states explicitly (`strip_shorting_copper` docstring, line 203):

> it is not otherwise reclassified (``completion_rate`` is unaffected …)

**A net that has copper deleted is no longer routed, and the metric would
still call it routed.** The result:

- `shorting_items` falls — the number looks better
- affected nets become electrically incomplete
- `completion_rate` continues to count them as complete

That manufactures a *worse* blind metric than the one being fixed, which is
the exact failure this branch exists to remediate
(`docs/METHODOLOGY.md` §7). It also directly violates R2 of the governing
brainstorm:

> **R2.** A net counts as **routed** only if its path is DRC-legal. Nets whose
> emitted copper shorts … are reported in a distinct category — not silently
> included in the completion numerator.

The fix was also never verified: the agent exhausted its budget before
producing before/after `shorting_items`.

## What would make it acceptable

1. Deleting copper from a net **decrements** that net from the completion
   numerator, into a distinct `routed_then_stripped` category.
2. Before/after `shorting_items` **and** `unconnected_items` measured
   together — stripping copper must be shown to move unconnected up as
   shorts come down, or the accounting is wrong.
3. The 113-vs-123 discrepancy reconciled.
4. The 62 pad-vs-pad shorts excluded from router-attributed counts, with the
   footprint/placement defect filed separately.

## Disposition

Diagnosis retained. Code not merged; it remains on
`worktree-agent-aeeab152bf155cdb8`.
