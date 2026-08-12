<!-- provenance: branch fix/scipy-migration-regression, worktree
.claude/worktrees/fix-scipy-migration-regression, from origin/main 66a277d94.
Companion to docs/evidence/2026-08-12-migration-reversal-sweep.md (the count
this brainstorm's scope is calibrated against) and
docs/evidence/2026-08-12-corridor-backbone-scipy-to-rust-board-neutrality.md
(Part 1's fix). No pcb/** modified. -->

# Preventing migration reversals: options, ranked, with cost

## Recap of the finding this brainstorm is scoped against

`docs/evidence/2026-08-12-migration-reversal-sweep.md` swept every
production (`packages/`, `scripts/`, `tools/`, excluding tests/oracles/
spikes) import of scipy, networkx, shapely, and ortools. Result: **exactly
one** reversed-migration import exists repository-wide — the
`scipy.ndimage.label` reintroduction in `_corridor_backbone.py` (#1052,
`d8e6efd48`), fixed on this branch. Both libraries with an actually-closed
migration (scipy, networkx) are now at zero production usage. shapely (26
files) and ortools (4 files) are *not* closed migrations — both are
extensively, independently documented as deliberate, currently-necessary
dependencies with no committed removal plan.

This changes the calculus stated in the task brief: the count is 1, not 20.
A narrow, cheap, already-armed gate is proportionate; a large new subsystem
is not justified by the evidence.

## Option A: Import-denylist gate driven by a machine-readable "closed migrations" record

**Shape:** a registry (YAML/JSON) mapping third-party symbol -> Rust
replacement -> the PR/commit that closed the migration, populated whenever
migration-pipeline.md's stage 7 ("wire") completes. A CI gate scans
production imports against the registry and fails on any match.

**Cost:** real infrastructure to build: the registry schema, a gate script,
a manifest entry, CI wiring, and — critically — a mechanism that actually
*populates* the registry when a migration closes, or it is exactly the kind
of check-a-frozen-list gate `docs/evidence/2026-08-12-gate-vacuity-structural-prevention.md`
found four instances of already in this repo this week (a gate that exists
but never learns about new closures is not better than no gate; it is a
gate with a silent blind spot that looks covered). Making population
*automatic* — "completing a migration automatically arms its guard," per
the task brief — is the hard part: nothing in this repo's stage 7 process
today writes machine-readable state that a script could consume without a
human/agent remembering to also touch the registry, which is the exact
kind of manual, forgettable step this whole task exists to stop relying on.

**Verdict: not chosen.** Given the measured count (1 reversal, not many),
building a new registry-driven subsystem is solving a problem at a scale
that doesn't exist yet, and its central design problem (auto-population) is
unsolved by anything in this repo today. Revisit if the sweep count grows.

## Option B: Extend the existing import-boundary check (chosen)

**Shape:** `scripts/import_linter_gate.py` + `.importlinter` already run in
CI as a required, blocking check (`AGENTS.md` § "Import Boundary Check";
confirmed: `"Repo Hygiene & Import Gates"` is in
`.github/required-checks.json`'s `required_contexts`, and the "Import
boundary enforcement" step carries no `continue-on-error`).  import-linter
supports `type = forbidden` contracts against *external* (non-root-package)
modules once `include_external_packages = True` is set. Add:

```ini
[importlinter:contract:no-scipy-in-temper-placer]
name = no-scipy-in-temper-placer
type = forbidden
source_modules = temper_placer
forbidden_modules = scipy

[importlinter:contract:no-networkx-in-temper-placer]
name = no-networkx-in-temper-placer
type = forbidden
source_modules = temper_placer
forbidden_modules = networkx
```

**Why "ratchet at zero" sidesteps Option A's registry problem entirely:**
since the sweep proves scipy and networkx are *already* at zero production
imports, there is no per-symbol registry to build or keep in sync — the
denylist is maximally strict from the moment it lands, for exactly the two
libraries with a real reversal history (scipy) or reversal risk (networkx,
zero-cost to include). A *future* closed migration for a *different*
library (say, a hypothetical future migration off some other dependency)
would need its own contract added by hand at that time — this is a real,
named limitation (see "What this does not solve" below), not swept under
the rug.

**Cost: near-zero.** No new script, no new CI job, no new manifest entry
beyond what already exists for `import_linter_gate.py`. Measured: adding
the two contracts plus `include_external_packages = True` and re-running
`lint-imports` took under 0.2s wall time on this repo's 507-file graph — no
detectable performance cost to the existing gate. The allowlist mechanism
(`import-linter-allowlist.yaml`, frozen since 2026-07-06, ticket-required)
already provides the reviewed escape hatch for a hypothetical legitimate
future need, with no changes needed.

**Verified non-vacuous, directly (not by inspection alone) — the exact
failure mode the task warned about:**

```
$ # with the exact reintroduced line: from scipy.ndimage import label
$ uv run python scripts/import_linter_gate.py
...
temper_placer imports scipy
Boundary rule: no-scipy-in-temper-placer
$ echo $?
3

$ # with the fix applied
$ uv run python scripts/import_linter_gate.py
Import boundary gate PASSED — 0 new violations
$ echo $?
0
```

This is the real historical regression, reproduced and shown to be caught —
not a synthetic example. See §2 of the companion plan document for the
full transcript and the CI-wiring confirmation.

**What this does not solve (named honestly):** it only guards scipy and
networkx, the two libraries with a demonstrated-closed migration today. It
does not guard a hypothetical future closed migration off a *different*
library without a human/agent adding that library's own contract at the
time. It also only covers the `temper_placer` package (import-linter's
`root_packages`) — a regression in `scripts/`, `tools/`, or a sibling
package (`temper-workflow`, etc.) would not be caught by this specific
mechanism. The sweep found zero such regressions today, so this is a scope
boundary, not a currently-open hole.

## Option C: Per-package dependency declarations (fail at build, not review)

**Shape:** remove scipy/networkx from `pyproject.toml`'s dependency list
entirely (or a per-package equivalent) so a re-introduced import fails at
`import` time in any environment built from a clean lockfile, not just in
CI's lint step.

**Cost / risk, evaluated and rejected for now:** scipy and networkx are
still real, installed dependencies of *other* transitive requirements in
this monorepo's shared `uv.lock` (numpy's own ecosystem neighbors,
pytest plugins, etc. — not independently re-verified line-by-line here,
flagged as the reason this option needs its own spike before being
attempted, not assumed safe). More importantly: this repo's test suite
*deliberately* imports scipy in ~20 `test_*_rust_differential.py` /
`_py_oracle.py` files as the R19 pinned pre-migration oracle
(`docs/migration-pipeline.md` stage 3) — removing the dependency outright
would break the differential-test discipline this repo's whole migration
program depends on, which is a materially worse outcome than the problem
being solved. A per-package split (production package depends on
`scipy`-free extras, test package retains it) is possible in principle but
is a real packaging change with its own blast radius, not evaluated in
depth here given Option B already closes the measured gap at near-zero
cost and risk.

**Verdict: not chosen**, but recorded because it is the strongest
"structural, can't-forget-to-run-it" option in the abstract — it fails at
import time in *any* context, not just a specific CI step someone could
misconfigure or route around. Worth revisiting only if Option B's
`temper_placer`-only scope proves to be an actual gap (a regression in
`scripts/`/`tools/`/a sibling package) rather than the theoretical one it
is today.

## Option D: Do nothing (sweep says one-off)

**Considered directly, per the task's own escape hatch.** Rejected because
the marginal cost of Option B is close to zero and it closes a real,
already-occurred failure mode (#1052 happened once; nothing but review
attention stopped it, and review attention already failed once). "The
sweep found only one instance" argues against a *large* investment
(Options A/C), not against a *free* one (Option B).

## Recommendation

**Option B**, landed on this branch (`.importlinter`,
`docs/evidence/2026-08-12-migration-reversal-sweep.md`,
`docs/evidence/2026-08-12-corridor-backbone-scipy-to-rust-board-neutrality.md`).
Full design, wiring confirmation, and the R42/mutation-coverage
follow-up decision are in
`docs/plans/2026-08-12-005-feat-migration-regression-prevention-plan.md`.
