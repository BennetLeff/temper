<!-- provenance: commit=7e1194b776aad76db2f1fd2a323defa0bebd5367 dirty=true -->

# R42 gate-mutation testing: first sweep, safety-critical subset

This records the first run of `scripts/gate_mutate.py` +
`scripts/check_gate_mutations.py`
(`docs/plans/2026-08-02-035-feat-gate-mutation-testing-plan.md`) against a
curated subset of this repo's fail-closed gates: the ones the R42 plan
itself names as mattering most (creepage/clearance, the physical isolation
keepout, HV netclass coverage, the R27 DRC ceiling ratchet approval gate,
both provenance checkers, and the anti-vacuity guard itself).

**Scope, stated plainly**: this is 7 gates and 19 mutations, not the full
fail-closed gate inventory. R19/R30 (the incident-corpus and canary-contract
plan this suite was designed to sit on top of) had not landed at the time
of this sweep, so — per the R42 plan's own "Assumptions" section — the
runner bootstraps directly from hand-written canary fixtures under
`ci-corpus/canaries/`, one per targeted gate, rather than the not-yet-built
R19 corpus.

## Why these operators, not generic ones

The task that produced this plan named nine distinct, real mechanisms by
which a check reported success while being structurally incapable of
reporting failure (a value discarded before its consumer, a rule matching
names instead of geometry, a fatal check gated behind `verbose`, a
validator iterating an empty dict, an unguarded `all()`, a backwards
comparison, ...). Generic arithmetic mutants (off-by-one on a random
constant) would not have reproduced most of that list. `scripts/gate_mutate.py`
implements seven axes chosen to model those mechanisms directly:

| Axis | Models |
|---|---|
| `guard-strip` | a fatal check gated behind a flag that never fires ("StageDRCFailure gated behind verbose", "SIL prints [WARN] instead of failing") |
| `condition-invert` | a guard that runs backwards |
| `scope-remove` | a CI group / scanner silently losing a whole directory (gate-subset-blindness, mechanized) |
| `violation-discard` | a finding computed correctly but discarded before reaching the verdict ("a value discarded before reaching its consumer") |
| `comparison-flip` | a boundary written backwards (the schematic `rated >= actual*0.5` class), and literally "swap `>=` for `>`" |
| `threshold-set` | a threshold that quietly loosens |
| `return-stub` | "a test binary returning 0 instead of calling `UnityEnd()`" / "return a constant success" — the highest-severity mutant this suite can register |

This deliberately diverges from the R42 plan's original four-axis list
(`threshold-loosen`, `scope-remove`, `condition-invert`, `allowlist-widen`)
per this task's explicit instruction to model the observed failure corpus
rather than a generic set; `allowlist-widen` wasn't applicable to any of
the seven targeted gates (none of them carry a per-file allowlist as their
primary bite mechanism) and was dropped rather than forced.

Every mutation targets a real AST node in the real, committed gate script,
located by `(function, node-kind, occurrence-index)` and validated against
a `line_hint` substring before being applied — a mutation whose hint no
longer matches is reported `NOT_APPLICABLE`, never silently mis-applied to
the wrong node. See `ci-corpus/mutations.yaml` for the full, human-readable
manifest and `scripts/gate_mutate.py`'s module docstring for the engine
design.

## Mutation score per gate

Run: `uv run --no-sync python3 scripts/check_gate_mutations.py`

| Gate | Killed | Scored | Score |
|---|---|---|---|
| `check_creepage_clearance_drift.py` | 4 | 4 | 1.00 |
| `check_drc_ceiling_approval.py` | 3 | 3 | 1.00 |
| `check_evidence_provenance.py` | 1 | 1 | 1.00 |
| `check_hv_netclass_coverage.py` | 3 | 3 | 1.00 |
| `check_isolation_keepout.py` | 3 | 3 | 1.00 |
| `check_measurement_provenance.py` | 3 | 3 | 1.00 |
| `check_vacuous_gates.py` | 2 | 2 | 1.00 |
| **Overall** | **19** | **19** | **1.0000** |

Every registered mutant — including three separate `return-stub` mutants
that force a "constant success" verdict on `run()`/`evaluate()` — is killed
by the current canary suite. This is not a claim that these seven gates
have no blind spots; it is a claim about the 19 specific weakenings
registered here.

## Every surviving mutant found during the sweep, and how it was resolved

Three mutations survived on first run. Per KTD4, each was resolved by
**strengthening the canary's oracle** — never by weakening or deleting an
assertion, and never by declaring a real gap equivalent to make the number
look better. All three turned out to share the same root cause: the
canary's oracle collapsed a gate's rich internal state (which net was
flagged, which specific guard fired, what the raised message said) down to
a coarse `"clean"`/`"violation"`/`"error"` string, and a coarse oracle
cannot tell "the gate is right for the wrong reason" apart from "the gate
is genuinely right."

### 1. `hv-netclass-invert-membership-test` (comparison-flip)

**Gate:** `check_hv_netclass_coverage.py`, `check_hv_net_coverage()`.
**Mutation:** `n not in net_assignments` → `n in net_assignments`.

Flipping the membership test makes the function report *assigned* nets as
unclassified instead of *unassigned* ones. Against the seed (`dc_bus`
unassigned, `ac_l` assigned), the mutant reports `["ac_l"]` — a false
positive — instead of the correct `["dc_bus"]`. Both are non-empty, so
`run()`'s overall verdict is `"violation"` either way, and the original
canary (which only checked the overall state) could not tell them apart.

**Fix:** `seed_unassigned_hv_net` now returns
`f"violation:{sorted(report.unclassified_hv_nets)}"` instead of the bare
state, so the canary asserts *which* net was flagged, not just that
*some* violation was reported. The mutant is now killed (mutated verdict
`violation:['ac_l']` ≠ baseline `violation:['dc_bus']`).

**What this means for the real gate**: no evidence the real gate is
wrong today — this was purely a test-oracle gap. It is a legitimate
finding on its own terms, though: had this exact `n not in` → `n in` typo
ever been introduced by a real edit, the gate's own regression suite
(`scripts/tests/test_check_hv_netclass_coverage.py`) would need to already
assert on the *specific* net named in `unclassified_hv_nets`, not merely
on `state == "violation"`, to catch it — worth checking whether that
suite's own assertions are that specific.

### 2. `measurement-guard-strip-zero-artifacts` (guard-strip)

**Gate:** `check_measurement_provenance.py`, `evaluate()`.
**Mutation:** `if not artifacts: raise GateError(...)` → `pass`.

`evaluate()` carries two overlapping fail-closed guards for an empty
`artifacts` list: guard 1 fires immediately (`"zero measurement artifacts
registered"`); guard 2 fires a few lines later because an empty
`artifacts` list can never increment `total_records`, so `if
total_records == 0: raise ...` (`"zero provenance-bearing records
found"`) is *structurally guaranteed* to also fire for this exact input.
Stripping guard 1 alone still raises `GateError` via guard 2 — a coarse
"did it raise" oracle sees `"error"` either way.

**Fix:** `seed_zero_artifacts` now inspects the raised message and
returns `"error:zero-artifacts"` only when guard 1's specific text is
present, `"error:other:<message>"` otherwise. The mutant is now killed
(the stripped-guard-1 mutant surfaces guard 2's different message).

**What this means for the real gate**: this is a genuine (if minor)
structural finding, distinct from the first: guard 1 is *provably*
redundant with guard 2 for this exact input shape — no seed could ever
exist for which guard 1 fires and guard 2 does not, because guard 2's
condition is a strict consequence of guard 1's. That is not a defect (the
gate still fails closed either way), but it does mean guard 1's only
independent value is a clearer error message, not distinct fail-closed
coverage. Not fixed here (out of scope: this task does not touch gate
logic, only test/mutation infrastructure) — flagged for whoever next
touches `evaluate()`'s guard ordering.

### 3. `drc-ratchet-invert-trailer-check` (comparison-flip)

**Gate:** `check_drc_ceiling_approval.py`, `run_gate()`.
**Mutation:** `"Ceiling-Approval:" in commit_messages` → `not in`.

The original seed (`seed_unapproved_raise`) raised the ceiling with *no*
measurement evidence at all *and* no trailer. With the trailer check
inverted, the gate believes a trailer is present, skips straight to
`validate_raise_evidence(...)` — which *also* fails, because the seed's
raise had no provenance recorded either. Both paths land on
`EXIT_UNAPPROVED_RAISE`; the trailer inversion was invisible behind the
evidence check.

**Fix:** added `seed_unapproved_raise_with_valid_evidence` — a raise that
*would* satisfy the full measurement-evidence contract (real board hash,
fresh measured-live provenance, a non-empty `_march` entry) if the gate
ever reached that check, but still carries no `Ceiling-Approval:` trailer.
This isolates the trailer check as the only variable. The mutant is now
killed (mutated verdict `EXIT_OK` ≠ baseline `EXIT_UNAPPROVED_RAISE`).

**What this means for the real gate**: this is the sharpest of the three
— had this exact inversion ever landed in the real gate, a PR with a
technically-compliant-looking raise and *zero* human sign-off would have
been silently approved, and the *original* canary (mirroring
`seed_unapproved_raise` in
`scripts/tests/test_check_drc_ceiling_approval.py`'s own
`TestRaiseWithoutTrailerFails`) would not have caught it, because every
existing "no trailer" test fixture in that suite also happens to have no
valid evidence. Recommend `scripts/tests/test_check_drc_ceiling_approval.py`
gain a case that isolates the trailer check the same way this canary now
does (full evidence, no trailer) — flagged, not fixed here (out of R42's
scope: this task adds mutation infrastructure, not new assertions to that
gate's own suite).

## Mutation manifest and diff records

`ci-corpus/mutations.yaml` carries all 19 triples with human-readable
descriptions; `scripts/gate_mutate.py --describe` prints the same list.
Every diff record names the exact file:line and before/after text of the
node that was changed — see any `[PASS] KILLED` line's summary in a real
run for an example.

## Weakest self-verification, ranked

Ranking the seven targeted gates by how much this sweep had to do to
reach a clean bill of health (more work required = weaker prior
self-verification):

1. **`check_drc_ceiling_approval.py`** (R27 DRC ratchet) — the survivor
   here was the sharpest: an inverted trailer check would have silently
   defeated the entire human-approval requirement for a ceiling raise,
   and the gate's own existing test suite would not have caught it either
   (see finding 3). This is the highest-severity gate on this list by
   consequence (it directly gates whether a DRC regression can merge
   without a human looking at it), and its blind spot was the least
   contrived to find.
2. **`check_hv_netclass_coverage.py`** — the survivor here (finding 1)
   shows the gate's own regression suite likely also under-specifies
   *which* net triggers a violation, not just whether one did — worth an
   independent look at that suite's assertions.
3. **`check_measurement_provenance.py`** — the survivor here (finding 2)
   is a structural redundancy, not a live gap; still worth noting that
   `evaluate()` has a guard whose only marginal value is message clarity,
   which a future refactor could remove without anyone noticing for a
   long time.
4. **`check_creepage_clearance_drift.py`, `check_isolation_keepout.py`,
   `check_vacuous_gates.py`, `check_evidence_provenance.py`** — every
   registered mutation, including every `return-stub` "constant success"
   mutant, was killed on first run with no canary changes required. Of
   particular note: `check_vacuous_gates.py` — the anti-vacuity guard this
   whole plan takes inspiration from — killed both a `scope-remove` on its
   own `AGGREGATORS` set and a `return-stub` on `find_violations()` itself
   without any strengthening; the meta case ("does the gate that catches
   vacuous checks have a vacuity blind spot of its own") came back clean.

## CI wiring (described, not implemented in this change)

Per this task's constraint (several agents edited `.github/workflows/*`
today; this change avoids touching them), the wiring is described here
for whoever next edits the workflow files, rather than applied directly:

- Add a step to the same job that already runs the corpus/canary/vacuous
  gates (`.github/workflows/python-tests.yml`'s consistency-gates job) —
  they share `uv sync`/`PYTHONPATH` setup already.
- `uv run --no-sync python3 scripts/check_gate_mutations.py` — no
  `continue-on-error`. The step should fail the job on any `SURVIVED` or
  `UNVERIFIED` verdict, matching this script's own exit-code contract
  (0 only when every triple is `KILLED` or `EQUIVALENT`, and the manifest
  is non-empty).
- Add `scripts/gate_mutate.py`, `scripts/check_gate_mutations.py`,
  `scripts/tests/test_gate_mutate.py`,
  `scripts/tests/test_check_gate_mutations.py`, and `ci-corpus/**` to the
  job's trigger paths (all three copies: push, pull_request, and
  `.github/required-checks.json`'s `trigger_paths`, per this repo's
  established three-way-sync convention for that file).
- Wall time as of this sweep: the full 19-triple run completes in well
  under a second locally (no build step, no corpus I/O beyond tiny
  synthetic fixtures and one throwaway git repo per DRC-ratchet triple) —
  no smoke-subset/full-sweep split is needed at this scale; revisit if the
  manifest grows enough to matter.
- The manifest is small and reviewable by design (KTD1); a maintainer
  extending it to the rest of the fail-closed gate inventory (out of
  scope for this sweep — see "Scope, stated plainly" above) is the
  natural next step, not a blocker for wiring this subset into CI now.

## Reproducing this sweep

```
uv sync --all-packages
uv run --no-sync python3 -m pytest scripts/tests/test_gate_mutate.py scripts/tests/test_check_gate_mutations.py -v
uv run --no-sync python3 scripts/check_gate_mutations.py
```
