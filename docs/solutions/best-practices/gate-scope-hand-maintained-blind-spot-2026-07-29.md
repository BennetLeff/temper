---
title: "A gate's scope is data too — a hand-maintained class list drifted exactly the way the gate exists to catch"
date: "2026-07-29"
category: best-practices
module: net_classification
problem_type: best_practice
component: hardware_design
severity: critical
applies_when:
  - "a fail-closed check reads the universe it validates against from a hand-maintained list, tuple, or constant rather than from the artifact it is checking"
  - "a generator and a checker both need to agree on a set of names (netclasses, rule IDs, field names) and each keeps its own copy"
  - "hardening a check from warning to fail-closed without first asking whether the check's own inputs could be stale"
  - "two independent 'undefined class' defects are found and fixed an hour apart in the same file, and it looks like coincidence rather than one blind spot"
tags:
  - gate-scope
  - hand-maintained-list
  - fail-closed
  - net-classification
  - kicad-dru
  - artifact-derived-scope
---

> **Status update (2026-08-03 refresh):** `scripts/gen_net_classification.py`'s `check_rule_referenced_classes` landed on the unmerged `feat/ato-net-classification-ssot` branch, not main. The live generator on main is `scripts/generate_kicad_dru.py` — the artifact-derived-scope guidance applies to it directly.


# A gate's scope is data too — a hand-maintained class list drifted exactly the way the gate exists to catch

## Context

`scripts/gen_net_classification.py`'s `check_rule_referenced_classes` exists
to catch a specific defect: a generated KiCad DRC rule that conditions on a
netclass (`A.NetClass == 'Something'`) which `pcb/temper.kicad_pro` never
defines — a rule that parses, is wired into CI, and matches nothing, forever,
because the class it names does not exist. It had just been hardened from a
warning to a fail-closed `GateError` the same day.

It read the set of netclasses to check from
`generate_kicad_dru.rule_referenced_net_classes()` — a hand-maintained tuple
in `generate_kicad_dru.py`, not the rules the generator actually renders.
That tuple had drifted, and drifted in exactly the shape the check exists to
detect. Measured in commit `cf3e6bd9`:

```
tuple named:            5 classes
generator emitted:      9 classes
omitted from tuple:     FinePitch, HighCurrent, Power, Signal
omitted AND undefined:  HighCurrent, Signal
```

Two live classes — `Signal` and `HighCurrent` — were named in generated DRU
rule conditions, undefined in `pcb/temper.kicad_pro`'s `net_settings.classes`,
and invisible to the fail-closed gate whose entire job was to catch exactly
that. The commit measured 0 of the board's 164 live nets resolve to either
class anywhere, confirming both were dead weight; their trace-width rules
were deleted. This was not the first instance in the same file that day —
`Ground`/`HighSpeed` had been found and fixed by the identical mechanism
(hand-maintained list omits a live class) an hour earlier, in commit
`0c170a3c`.

## The pattern

**A gate whose scope is hand-maintained has a hand-maintained blind spot.**
The check logic itself — "flag any referenced-but-undefined netclass" — was
correct throughout. The defect was entirely in what the check considered
"referenced": a list a person typed once and never obligated to update when
the generator gained new conditions. Every property that makes hand-written
lists drift elsewhere in this codebase (a rename that doesn't propagate, a
new case nobody remembers to add) applies with equal force to a list that
exists specifically to bound a safety gate's coverage. The gate did not fail
to run; it ran successfully and reported agreement having checked a universe
smaller than the real one.

This is a sharper case than the general "hand-maintained table drifts"
shape documented elsewhere in this project
([[rename-orphans-derived-keys-2026-07-28]],
[[substring-net-classification-drifts-from-ssot-2026-07-27]]): those are
about a *classification* going stale. Here the thing that went stale was the
*gate's own scope* — the set of things it promises to check — which means
the drift is invisible even to someone auditing the gate's logic line by
line, because the logic is fine. Only comparing the list against the actual
artifact surfaces it.

## What to do

1. **Derive a gate's scope from the artifact it validates, not from a
   parallel list.** The fix here scrapes class names directly out of the
   rendered DRU rule text (`re.findall(r"NetClass\s*==\s*'([^']+)'", emitted)`
   against `generate_dru()`'s actual output) instead of calling
   `rule_referenced_net_classes()`. There is no longer a second copy of the
   class list that can drift from the first, because there is only one copy.
2. **Treat a hand-maintained tuple/list feeding a fail-closed check as a
   liability independent of any specific staleness found today.** Even after
   this fix, any other gate in the repo that reads "the set of X" from a
   maintained constant rather than computing it from a generator's real
   output carries the same latent blind spot until it is checked the same
   way.
3. **When two identical-shaped defects surface in the same file within an
   hour (`Ground`/`HighSpeed`, then `FinePitch`/`HighCurrent`/`Power`/
   `Signal`), treat it as a systemic property of the list, not two
   coincidental typos.** The second finding in `cf3e6bd9` is what motivated
   deriving the scope from the artifact instead of patching the list a third
   time.
4. **Hardening a check to fail-closed is the moment to re-derive its scope,
   not just its exit behavior.** A warning that silently under-covers is
   low-stakes; a `GateError` that silently under-covers gives false
   confidence that the class of defect is now impossible, when it is merely
   less likely for the specific instance already found.

## Why This Matters

The check existed, ran in CI, and had just been strengthened to hard-fail —
every visible signal said this class of defect was now closed. It was not:
two of the nine netclasses the generator actually conditions on were
undefined in KiCad, sitting inside the gate's own input, un-flaggable by a
gate whose scope stopped at five names. A reviewer reading the gate's logic
would find nothing wrong with it; the defect was one layer up, in what the
gate believed the universe to be.

## When to Apply

- Before trusting a fail-closed check's coverage claim, ask what supplies
  its scope: a computed artifact, or a list someone typed.
- When a generator and a checker both need the same set of names, make one
  of them derive it from the other's real output rather than maintaining
  two lists that must stay in sync by discipline alone.
- When the same shape of "undefined class" defect is found twice in one
  file in a short window, stop patching individual entries and re-derive
  the scope from source.

## Examples

```python
# WRONG — the check's universe is a hand-maintained tuple
from generate_kicad_dru import rule_referenced_net_classes
referenced = {str(name) for name in rule_referenced_net_classes()}
# rule_referenced_net_classes() named 5 classes; the generator emitted 9.

# RIGHT — the check's universe is scraped from what the generator renders
emitted = generate_dru()
referenced = set(re.findall(r"NetClass\s*==\s*'([^']+)'", emitted))
referenced |= set(re.findall(r'NetClass\s*==\s*"([^"]+)"', emitted))
```

## Related

- [[shared-venv-worktree-validates-wrong-tree-2026-07-29]] — the second,
  independent fix landed in the same commit (`cf3e6bd9`): the gate also
  silently validated a different checkout's copy of `temper_placer`.
- [[rename-orphans-derived-keys-2026-07-28]] — the general shape of a
  hand-maintained key/list drifting from the source of truth it is meant to
  track, applied to a classification table rather than a gate's scope.
- [[a-rule-that-matches-nothing-reads-as-coverage-2026-07-28]] — a sibling
  failure mode from the same DRC-rule surface: a condition that parses,
  looks correct, and matches nothing, discovered the same week.
- `scripts/gen_net_classification.py` — `check_rule_referenced_classes`,
  the fixed check.
- Commit `cf3e6bd9` — `fix(gen): scrape the emitted rules -- the check's
  own input had the defect`.
- Commit `0c170a3c` — the `Ground`/`HighSpeed` instance of the same defect,
  found an hour earlier in the same file.
