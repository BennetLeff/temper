#!/usr/bin/env bash
# assert-base.sh -- fail loudly if this checkout is not on the commit/branch
# a subagent was told to work from.
#
# Why: four confirmed cases today of an agent measuring from a stale
# worktree and reporting the result as current state (temper-drc-rs
# "broken", a UVL-02 fault-tree survey, a bus-capacitor agent on ee9ba6ba,
# a BOM agent on b259419f) -- see docs/METHODOLOGY.md Sec 5. This is the
# single command a dispatch should always run first.
#
# Usage:
#   scripts/assert-base.sh <expected-ref>
#
# <expected-ref> is anything `git rev-parse` accepts: a branch name
# (docs/methodology-loop-discipline), a full or short SHA, origin/main, etc.
#
# Exit codes:
#   0  HEAD matches <expected-ref> exactly (after resolving both to a SHA).
#   1  HEAD does NOT match -- this is the failure this script exists to
#      catch. Prints both SHAs and how far HEAD is behind the expected ref.
#   2  <expected-ref> does not resolve to a real commit (typo, unfetched
#      branch, etc.) -- a broken assertion is not a silent pass.
#
# On a mismatch, the fix is almost always:
#   git rebase <expected-ref>
# not force-checkout -- see docs/METHODOLOGY.md Sec 5 and AGENTS.md.

set -euo pipefail

if [ $# -ne 1 ]; then
  echo "usage: scripts/assert-base.sh <expected-ref>" >&2
  exit 2
fi

expected_ref="$1"

expected_sha="$(git rev-parse --verify --quiet "${expected_ref}^{commit}" || true)"
if [ -z "${expected_sha}" ]; then
  echo "ASSERT-BASE FAIL: '${expected_ref}' does not resolve to a commit in this repo." >&2
  echo "  (typo? unfetched branch? run 'git fetch' first?)" >&2
  exit 2
fi

actual_sha="$(git rev-parse HEAD)"

if [ "${actual_sha}" = "${expected_sha}" ]; then
  echo "ASSERT-BASE OK: HEAD == ${expected_ref} (${actual_sha})"
  exit 0
fi

echo "ASSERT-BASE FAIL: this checkout is NOT on ${expected_ref}." >&2
echo "  expected (${expected_ref}): ${expected_sha}" >&2
echo "  actual   (HEAD):            ${actual_sha}" >&2
behind="$(git rev-list --count "${actual_sha}..${expected_sha}" 2>/dev/null || echo UNKNOWN)"
ahead="$(git rev-list --count "${expected_sha}..${actual_sha}" 2>/dev/null || echo UNKNOWN)"
echo "  HEAD is ${behind} commit(s) behind and ${ahead} commit(s) ahead of ${expected_ref}." >&2
echo "  Fix: git rebase ${expected_ref}   (then re-run this assertion)" >&2
exit 1
