<!-- provenance: commit=3dd0f80440500113c736be0d67a9d75cdf80db82 dirty=false -->

# DRC-ceiling provenance identity: the orphaned `measured_at_commit` (2026-08-07)

**Date:** 2026-08-07
**Status:** resolved — `scripts/check_measurement_provenance.py` makes the content hash the primary identity and verifies commit resolvability

## The incident

`power_pcb_dataset/drc_ceiling.json`'s `provenance.measured_at_commit` was
`3410ee4e1fe8c3a5cce13b9262585016a06fce8d` — a commit absent from this
repository's object store entirely (`git cat-file -t` fails on it).

Root cause, confirmed against `git log -p` and the GitHub API: the PR that
recorded it (#602, branch `feat/k3-swap-and-board-write`) named a
mid-development branch commit as the measurement anchor; that branch was
rebased more than once before merging (its own commit trailers say
"re-point wave-2 provenance to post-rebase HEAD"), and the squash/rebase
orphaned the original commit object before the PR landed.

## Why the existing checks missed it

Neither existing check would have caught it:

- `validate_provenance_shape` only checks that `measured_at_commit` is 40
  lowercase hex characters or `"UNKNOWN"` — shape, not existence.
- `DrcRatchet.validate_raise_evidence`'s commit check
  (`_SHA256_HEX_RE.fullmatch`) is the same regex-only check despite its
  error message claiming otherwise, and it only runs when a ceiling
  *raise* is being approved, not on every re-measurement.

## The fix: content hash is the identity, commit SHA is advisory

The fix (`scripts/check_measurement_provenance.py`, 2026-08-07): a
measurement's **primary, authoritative identity is the content hash**
already recorded at `provenance.inputs[].sha256` — this was already true
in design (the module docstring's "informational, never the thing
compared" language predates this incident) but was not fully true in
enforcement. `measured_at_commit` is **advisory** — useful for a human
tracing which run produced a number — but is now also **verified for
resolvability whenever it is not `"UNKNOWN"`**, via
`check_evidence_provenance.verify_commits_exist` (the same
`git cat-file --batch-check` mechanism that already closed this exact hole
for `docs/evidence/*`, reused rather than reimplemented).

A commit SHA was rejected as the *primary* identity outright, not merely
deprioritized: it is not stable under history rewriting by construction
(squash merge, rebase, `git gc` pruning an unreachable object), while a raw
content hash of the file bytes is independent of git object model, mtimes,
or commit topology entirely — the only signal that directly answers "is
this the same content" regardless of how the repository's history around
it changed.

## What now fails closed

A **dangling** `measured_at_commit` (well-formed but unresolvable) is now
treated as a hard failure — worse than an honest `"UNKNOWN"`, because it
claims traceability it does not have while looking exactly like a record
that does. A `dirty: true` record is now also a hard failure on every
provenanced record, not only on a ceiling raise: an unnamed uncommitted
change at measurement time could have influenced the result without ever
appearing in `inputs`, which the content-hash check cannot see.

All three of these are checked unconditionally by
`check_measurement_provenance.py` on every PR that touches a registered
measurement artifact — not only on a ceiling raise — so a bad record now
fails closed on the PR that writes it, the same "same-PR" discipline the
DRC-ceiling re-measurement convention requires of the re-measurement
itself (see
`docs/solutions/best-practices/drc-ceiling-same-pr-discipline-2026-08-19.md`).

## Alternatives considered and rejected

See `scripts/check_measurement_provenance.py`'s module docstring for the
full incident writeup and design rationale, including the alternatives
considered and rejected:

- re-anchoring freshness on the commit SHA instead of content;
- silently downgrading a dangling commit to `"UNKNOWN"` instead of failing
  on it.
