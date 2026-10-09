---
title: Legacy-era documents removed from main
date: 2026-10-09
---

# Legacy-era documents removed from main

On 2026-10-09, 1,021 files under `docs/` were removed from main: plans,
evidence, brainstorms, solutions and reports. They described only the legacy
tree (the placer and router, `packages/`, `pcb/`, `elec/`, `crates/` and the
datasets), which was itself removed on 2026-10-08. The full list is in
[`legacy-docs-removed-2026-10-09.txt`](legacy-docs-removed-2026-10-09.txt).

A document was removed only if both held:
- it named legacy paths and no live ones (`zapote/`, `power-stage-120v`, `firmware/`);
- nothing outside `docs/` links to it (code, CI, zapote evidence, the top-level guides).

The 72 legacy documents that zapote evidence cites as provenance stay.

Some kept documents still link to removed ones. Every removed file is
unchanged at tag `archive/temper-legacy-2026-10-08`:

```sh
git show archive/temper-legacy-2026-10-08:docs/<path>
```
