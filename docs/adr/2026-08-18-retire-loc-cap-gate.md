---
date: 2026-08-18
status: accepted
plan-id: 2026-06-22-006-feat-cli-zoning-loc-cap-plan
supersedes: []
---

# ADR-002: Retire the LOC Cap Gate (N6)

## Context

The LOC cap gate (`tools/loc_cap_check.py` + `.loc-allowlist.txt`) enforced a
1000-line ceiling on source `.py`/`.c` files. It landed under
`docs/plans/2026-06-22-006-feat-cli-zoning-loc-cap-plan.md` as gate **N6** and
ran in two places:

| Invocation | File |
|---|---|
| `LOC cap gate` step of the merged `fast-gates` job | `.github/workflows/python-tests.yml` |
| `run_gate "LOC cap gate"` in the trunk-health canary | `.github/workflows/trunk-health.yml` |

The gate had a genuinely good design. It was a real ratchet: a committed
baseline, per-entry ticket justification, a strict-shrink policy, distinct exit
codes per violation class, and — unusually, and correctly —
`STALE_ENTRY` detection so that paid-down debt could not sit unrecorded. That
last property was added on 2026-07-27 after it emerged that 13 of 17 allowlist
entries were for files already decomposed. It is a design worth copying, and it
was copied: `scripts/vulture_gate.py`, `scripts/check_hash_order_determinism.py`
and `scripts/known_failure_pins.py` all cite it as the exemplar.

What it did **not** have was anyone acting on it.
`docs/plans/2026-07-25-002-refactor-baseline-burndown-plan.md` measured this
directly: across 14 sampled commits, **every** allowlist movement was an upward
cap bump (e.g. `1110→1187`); **zero** downward events were observed. The ledger
recorded growth and called it compliance.

## Decision

**Retire the LOC cap gate.** Remove both CI invocations, the script, and its
allowlist/baseline data.

The cap's real value was never the number 1000. It was as a **prioritizer**:
it pointed at the god-objects that most needed decomposition, in an era when
"which file do we break up next?" was an open question. That role is now served
by a measured port list driving the Python→Rust migration, which orders the same
work by measured cost rather than by line count — a better instrument for the
same purpose.

A gate the team has decided not to act on is worse than no gate. It trains
everyone to merge past red, and that habit generalizes to gates that *are*
load-bearing — several of which, on this board, are safety gates. Removing a
gate we have collectively opted out of is a smaller loss than keeping a
standing demonstration that red is negotiable.

## Consequences

- No ceiling on source-file length is enforced in CI. Reviewers may still ask
  for decomposition; nothing blocks a 2000-line file mechanically.
- `fast-gates` merges three gate steps rather than four. No other gate's
  coverage changes, and no threshold anywhere moved.
- `.loc-allowlist.txt` is removed from the `paths:` filters in
  `python-tests.yml` and from `trigger_paths` in `.github/required-checks.json`.
  Those two lists are cross-validated by
  `check_required_checks.validate_trigger_manifest`, so they were edited in
  lockstep.
- Three source files cited the script as a ratchet exemplar
  (`scripts/known_failure_pins.py`, `scripts/check_hash_order_determinism.py`,
  `router_v6/_astar_theta_star.py`), and two more cited the allowlist as the
  reason for a module split (`router_v6/net_batching.py`,
  `net_batching_subprocess.py`). All five were rephrased to keep the
  explanation and point at this ADR instead of a deleted path. The ratchet
  *pattern* is still the repo's convention and is still live in
  `vulture_gate.py`, `check_hash_order_determinism.py` and
  `known_failure_pins.py`; only this instance of it is gone.

## Scope

This retirement is specific and reasoned. **It does not generalize.** It is
not a precedent for weakening any other check, and in particular not for any
clearance, creepage, copper-weight or DRU threshold, none of which may be moved
to make something pass. The distinction that makes this decision legitimate —
an explicit, recorded owner decision to stop enforcing something, versus
quietly relaxing it until it stops complaining — is exactly the distinction
this ADR exists to preserve.
