---
title: "A moved function silently relocates the monkeypatch surface — a re-export would have converted a loud failure into a vacuous pass"
date: "2026-07-29"
category: best-practices
module: router_v6
problem_type: best_practice
component: testing
severity: high
applies_when:
  - "splitting one module into several during a refactor, and at least one test patches a private/internal name with `mock.patch.object`"
  - "a test comment says 'patch where the name is looked up, not where it is defined'"
  - "reviewing whether a refactor should leave a re-export/alias behind on the old module for backward compatibility"
  - "a CI failure is `AttributeError` from `mock.patch.object` right after a file-split or move refactor"
tags:
  - mock-patch-relocation
  - vacuous-truth
  - module-split
  - re-export-hazard
  - fail-loud-not-silent
  - patch-where-looked-up
---

# A moved function silently relocates the monkeypatch surface

## Context

`packages/temper-placer/src/temper_placer/router_v6/_astar_reconstruct.py` had
grown to 1313 lines against a 1000-line cap. Commit `68cdd8e6` split it into
four modules: `_routing_reports.py` (172 lines), `_net_policy.py` (60 lines),
`_astar_search.py` (692 lines — gained `_dispatch_search`, `_segment_search`,
and `_astar_route_multilayer`), and a slimmed `_astar_reconstruct.py`
(486 lines, left with `run_astar_pathfinding` only). The split was done by an
AST-line-range extraction script asserting all 1313 lines land in exactly one
destination, so the moved code was byte-identical — not hand-retyped.

`_astar_route_multilayer` calls `_route_segment_3d` (defined in
`astar_core.py`, imported into whichever module calls it —
`packages/temper-placer/src/temper_placer/router_v6/_astar_search.py:24`).
Before the split, that import lived in `_astar_reconstruct.py`. Four tests in
`packages/temper-placer/tests/router_v6/test_astar_route_multilayer_via_fallback.py`
followed the correct discipline for patching a name looked up via module
attribute access —
`patch.object(astar_reconstruct_mod, "_route_segment_3d", wraps=_real_route_segment_3d)`
— with an in-line comment explaining exactly why: *"Patch where the name is
looked up, not where it is defined."* The split moved
`_astar_route_multilayer` (and with it, the lookup of `_route_segment_3d`)
into `_astar_search.py`. The tests still patched `_astar_reconstruct`, where
the name no longer existed. All four failed with `AttributeError` (fixed in
commit `7aee8e74`, which repoints the patches to `_astar_search` and updates
the comments to name the module that actually performs the lookup).

## The load-bearing point

The four tests failed **loudly**, and that was the good outcome, for one
specific reason: `mock.patch.object` refuses to patch an attribute that does
not exist on the target object. It raised `AttributeError` immediately,
before any test body ran.

Had the module split instead left a convenience re-export on
`_astar_reconstruct` — `from temper_placer.router_v6._astar_search import
_route_segment_3d` at the top of the slimmed file, the kind of thing a
refactor adds "for backward compatibility" — the patch would have applied
successfully. It would have replaced an attribute that existed, on a module
that still imported it, that nothing at runtime ever reads from anymore
(because the real call site moved to `_astar_search`). The spy/mock would
patch a dead alias; `_astar_route_multilayer`'s actual call to
`_route_segment_3d` would still resolve through `_astar_search`'s own
namespace, hit the real, unpatched function every time; and all four tests
would have passed, having verified nothing about the fallback tier, the
`net_id` threading, or the `max_iter` bound they exist to check.

**A re-export converts a loud failure into a vacuous pass.** The safety
property a module split must preserve is not "does the old import path still
work" — it is "does patching the old import path still patch something a
production code path actually reads." Those are the same question only until
someone moves the reader.

## Guidance

1. **When splitting a module, grep test files for `patch.object(<old_module>,`
   before merging, not after CI fails.** `git grep -n "patch\.object($OLD_MODULE"
   -- '*_test.py' 'test_*.py'` against the module being split finds every
   monkeypatch site whose target module attribute is about to move.
2. **Do not add a re-export/alias on the old module purely to keep old
   imports working**, unless every test patching that name is updated in the
   same commit to patch the new location instead. A re-export that outlives
   the tests patching it is a silent trap: the import still resolves, the
   patch still applies, and neither signals that the object being patched no
   longer intercepts anything real.
3. **An `AttributeError` from `mock.patch`/`patch.object` right after a
   file-split refactor is the check working, not a flake to route around.**
   The fix is to repoint the patch to the module that performs the lookup
   now (`7aee8e74`), never to make the old attribute resolve again via a
   re-export.
4. **Keep the "patch where it's looked up, not where it's defined" comment
   next to every such patch site**, and update it in the same commit that
   moves the lookup — the comment in
   `test_astar_route_multilayer_via_fallback.py` correctly named the specific
   module before the split; after the split it kept naming the old module
   for one commit, which is exactly the window in which a re-export would
   have caused silent damage instead of `AttributeError`.

## Why This Matters

This incident cost four loud failures and a one-file test fix. The
counterfactual — a re-export left behind "to be safe" — would have cost
nothing visible: CI green, four tests passing, and zero coverage of the
`_route_segment_3d` fallback tier, the `net_id` threading fix, or the
`max_iter` wall-time bound those tests exist to verify, discovered only by
someone reading the test body months later and asking why the spy never
recorded a call. This is the same shape as this repo's other vacuous-gate
findings (`docs/solutions/best-practices/gate-neutering-mechanisms-2026-07-26.md`,
`docs/solutions/best-practices/gate-subset-blindness-2026-07-27.md`): a check
that runs, produces a verdict, and is structurally incapable of catching the
defect it exists for — here, the mechanism is a refactor accidentally
building the exact silencer (a re-export) that would have turned a real gap
invisible, and the thing that saved it was `mock.patch.object`'s own refusal
to patch an absent attribute.

## When to Apply

- Splitting or moving a module that any test patches via
  `mock.patch`/`patch.object`/`monkeypatch.setattr` on a module-qualified
  name.
- Reviewing a refactor PR that adds a re-export or alias "for backward
  compatibility" on a module whose internals are covered by patch-based
  tests.
- Debugging a sudden `AttributeError` from `mock.patch.object` right after a
  file-split commit — repoint the patch, do not add a re-export to make the
  old path resolve.
- Writing a monkeypatch test against any private (`_`-prefixed) function:
  name in a comment exactly which module's namespace holds the lookup, so a
  future split's author knows what to move with the code.

## Examples

```python
# packages/temper-placer/tests/router_v6/test_astar_route_multilayer_via_fallback.py
# BEFORE the split (68cdd8e6): _astar_route_multilayer lived in
# _astar_reconstruct.py, so that module's namespace held the lookup.
import temper_placer.router_v6._astar_reconstruct as astar_reconstruct_mod
with patch.object(astar_reconstruct_mod, "_route_segment_3d",
                   wraps=_real_route_segment_3d) as spy:
    ...

# AFTER the split, before the fix (7aee8e74): _astar_route_multilayer moved
# to _astar_search.py -- the patch target above no longer has the attribute.
# mock.patch.object raises AttributeError here. Good: it is loud.

# AFTER the fix: patch follows the lookup to its new home.
import temper_placer.router_v6._astar_search as astar_search_mod
with patch.object(astar_search_mod, "_route_segment_3d",
                   wraps=_real_route_segment_3d) as spy:
    ...
```

```python
# The counterfactual that would have made this silent instead of loud --
# NOT what this codebase did, but the trap a "helpful" split could add:
# _astar_reconstruct.py, after the split
from temper_placer.router_v6._astar_search import _route_segment_3d  # noqa
# Now astar_reconstruct_mod._route_segment_3d exists again.
# patch.object(astar_reconstruct_mod, "_route_segment_3d", ...) SUCCEEDS.
# _astar_route_multilayer (in _astar_search.py) still calls the REAL,
# unpatched function through its own module's namespace. Four tests pass.
# Zero of them verified anything.
```

## Related

- `docs/solutions/best-practices/gate-neutering-mechanisms-2026-07-26.md` —
  the four sibling mechanisms that leave a check green while catching
  nothing; this is a fifth, refactor-specific instance of the same family,
  where the silencer is an accidental re-export rather than
  `continue-on-error` or a default-off flag.
- `docs/solutions/best-practices/gate-subset-blindness-2026-07-27.md` — a
  distinct fifth mechanism found the same week (a nonempty scan that is a
  silent minority of the true universe); this doc's failure mode is
  different again — the scan target itself becomes a dead object, not an
  undisclosed subset.
- `docs/solutions/test-failures/refactor-breakage-test-imports-stale-references-2026-06-29.md`
  — a related but distinct refactor-breakage class (stale import paths
  causing collection errors, which are also loud); this doc's case is
  specifically about monkeypatch targets, where the "loud failure" only
  happens because `mock.patch.object` checks attribute existence — a plain
  stale import would fail the same way for a different reason.
- Commit `68cdd8e6` — the module split (`_astar_reconstruct.py` →
  `_routing_reports.py` / `_net_policy.py` / `_astar_search.py` /
  slimmed `_astar_reconstruct.py`).
- Commit `7aee8e74` — the test fix, repointing all four `patch.object` calls
  to `_astar_search` and updating the "patch where it's looked up" comments.
- `packages/temper-placer/tests/router_v6/test_astar_route_multilayer_via_fallback.py`
  — the four affected tests.
