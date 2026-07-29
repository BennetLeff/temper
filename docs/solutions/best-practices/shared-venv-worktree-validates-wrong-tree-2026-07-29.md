---
title: "The shared-venv worktree trap: a script can validate a different tree than it runs in"
date: "2026-07-29"
category: best-practices
module: net_classification
problem_type: best_practice
component: development_workflow
severity: critical
applies_when:
  - "a worktree points UV_PROJECT_ENVIRONMENT (or any venv path) at the main checkout's already-synced .venv to save disk or build time"
  - "a script imports a package (`temper_placer`, or any editable install) and trusts the import without checking which checkout's source it resolved from"
  - "a gate or audit script produces a plausible-looking result that contradicts what the current branch's own source says should be true"
  - "a KeyError or stale-value bug appears only in a worktree, never in the main checkout, for code that has not changed"
tags:
  - shared-venv
  - worktree-isolation
  - editable-install
  - wrong-tree-validation
  - sys-path-ordering
  - gate-audit
---

# The shared-venv worktree trap: a script can validate a different tree than it runs in

## Context

Two independent scripts, in the same worktree setup, hit the identical
failure a day apart. Both point `UV_PROJECT_ENVIRONMENT` at the main
checkout's already-synced `.venv` — the documented way to avoid a full
`uv sync`/cargo rebuild per worktree — and both discovered that
`import temper_placer` under that setup resolves to the **editable
install's baked-in absolute path**, which is the MAIN checkout, not the
worktree the script is actually running in.

**First instance:** `scripts/audit_dru_binding.py` (commit `d43a9f5f`,
`test(dru): absurd-threshold binding audit for every generate_kicad_dru.py
rule`). Its `import_generator()` docstring records the measurement directly:
invoking the script under a worktree via a shared main-checkout `.venv`
resolved `generate_kicad_dru`'s own `from temper_placer.core.design_rules
import ...` against the *main* checkout's `design_rules.py` — silently
auditing a different branch's net-classification table than the one on
disk in the worktree being tested.

**Second instance, found independently the next day:**
`scripts/gen_net_classification.py`'s `check_rule_referenced_classes`
(commit `cf3e6bd9`) hit the same trap and it surfaced concretely as
`KeyError: 'GateDriveHV'` — the other (main) checkout still had the
pre-split `GateDrive` class, not the `GateDriveHV`/`GateDriveSELV` split
this branch had already landed. The gate would have silently validated the
main checkout's net-classification table under the guise of checking this
branch's.

## The pattern

**A gate that silently validates the wrong tree is worse than one that
fails.** A crash at least stops the pipeline. A gate that runs to
completion, produces a real-looking pass or fail verdict, and did so
against a different git tree's source is indistinguishable from a correct
result until someone notices the verdict doesn't match what the current
branch's files actually say. The failure mode is not "the tool broke" —
it's "the tool answered a question about a repo that isn't the one being
worked on."

The root cause is ordinary and easy to miss: Python's editable-install
mechanism (`pip install -e` / `uv`'s equivalent) bakes an absolute
filesystem path into the installed package's metadata at sync time. A venv
synced from checkout A resolves `import temper_placer` to checkout A's
source tree forever, regardless of which directory the interpreter is later
invoked from. Sharing a `.venv` across worktrees to save disk (a real,
measured cost — see
[[shared-mutable-state-dominant-cost-multi-agent-repo-2026-07-28]]) makes
this the default behavior, not an edge case.

## What to do

**Put the running worktree's own package source on `sys.path` ahead of the
venv, and verify the import resolved there before trusting it.** Both fixes
took the same shape:

```python
# scripts/audit_dru_binding.py's import_generator()
placer_src = repo_root / "packages" / "temper-placer" / "src"
if str(placer_src) not in sys.path:
    sys.path.insert(0, str(placer_src))
scripts_dir = repo_root / "scripts"
if str(scripts_dir) not in sys.path:
    sys.path.insert(0, str(scripts_dir))
```

```python
# scripts/gen_net_classification.py's check_rule_referenced_classes,
# the package path FIRST, ahead of the scripts dir and the shared venv
sys.path.insert(0, str(repo_root / "scripts"))
sys.path.insert(0, str(repo_root / "packages" / "temper-placer" / "src"))
```

1. **`repo_root` must itself be derived from the running script's own
   location** (`scripts/_lib/repo.py`'s `find_repo_root()` in this repo),
   not assumed or hardcoded — otherwise the sys.path fix inherits the same
   wrong-tree risk one level up.
2. **Insert the worktree's own source path before any path a shared venv
   would already provide**, so it wins regardless of what the venv's
   editable-install metadata says.
3. **When a gate's output contradicts what the current branch's own source
   files say should be true — a class that should exist reports missing, a
   key that was renamed still fails as if unrenamed — check which tree the
   gate actually imported from before debugging the gate's logic.** Both
   instances here initially looked like ordinary bugs in the check itself.
4. **This is a property of the worktree setup, not of any one script.**
   Finding and fixing it in `audit_dru_binding.py` did not prevent the
   identical trap in `gen_net_classification.py` the next day — every
   script in the repo that imports `temper_placer` under a shared-venv
   worktree needs the same guard, or needs `make venv-isolate` run first
   (see `AGENTS.md`'s "Worktree `.venv`: shared vs. isolated" section).

## Why This Matters

Both scripts here are gates whose entire purpose is catching a
classification defect before it ships. A gate that answers the right
question about the wrong repository gives exactly the same false
confidence as a gate with a hand-maintained blind spot in its scope
([[gate-scope-hand-maintained-blind-spot-2026-07-29]]) — the output looks
identical to a correct verdict, and nothing about the JSON or exit code it
returns distinguishes "this branch is clean" from "the main checkout,
which I accidentally imported, is clean."

## When to Apply

- Writing or reviewing any script that imports an editable-installed
  package (`temper_placer` or equivalent) and runs inside a worktree that
  shares its `.venv` with another checkout.
- Debugging a gate result that contradicts the current branch's own
  source — check which tree it imported before assuming the check logic
  is wrong.
- Setting up a new gate/audit script in this repo: give it a `sys.path`
  guard equivalent to `import_generator()`'s, or require
  `make venv-isolate` as a precondition and document that requirement.

## Examples

```
# Symptom, exactly as it surfaced:
KeyError: 'GateDriveHV'
# Cause: the shared venv's editable install resolved `temper_placer` to
# the MAIN checkout, which still had the pre-split 'GateDrive' class —
# not this worktree's already-landed GateDriveHV/GateDriveSELV split.
```

## Related

- [[gate-scope-hand-maintained-blind-spot-2026-07-29]] — the other defect
  fixed in the same commit (`cf3e6bd9`) that this trap was found alongside.
- `docs/solutions/best-practices/shared-mutable-state-dominant-cost-multi-agent-repo-2026-07-28.md`
  — the broader shared-`.venv` hazard class (a concurrent `uv sync`
  evicting another worktree's built extension) that motivates
  `make venv-isolate`; this doc is the "wrong tree, not evicted tree"
  sibling of that hazard.
- `AGENTS.md`, "Worktree `.venv`: shared vs. isolated" — the two repo-level
  mitigations (content-hash staleness gate, `make venv-isolate`) and when
  each applies.
- `scripts/audit_dru_binding.py`'s `import_generator()` — the first fix and
  its full docstring measurement.
- `scripts/gen_net_classification.py`'s `check_rule_referenced_classes` —
  the second fix.
- Commit `d43a9f5f` — first instance, `audit_dru_binding.py`.
- Commit `cf3e6bd9` — second instance, `gen_net_classification.py`, surfaced
  as `KeyError: 'GateDriveHV'`.
