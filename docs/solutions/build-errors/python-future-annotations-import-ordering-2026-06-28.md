---
title: "Misplaced `from __future__ import annotations` silently breaks closure test"
date: "2026-06-28"
category: build-errors/
module: temper-placer
problem_type: build_error
component: tooling
symptoms:
  - "CI closure test fails with router_completion_pct <= 0"
  - "Router V6 strategy fails to load with no explicit error in test output"
  - "SyntaxError at import time — `from __future__ imports must occur at the beginning of the file`"
root_cause: import_order
resolution_type: code_fix
severity: high
tags:
  - python
  - future-annotations
  - import-order
  - ci
  - closure-test
  - syntax-error
---

# Misplaced `from __future__ import annotations` silently breaks closure test

## Problem
The CI closure test was failing with `router_completion_pct <= 0` because the Router V6 strategy could not be imported. `from __future__ import annotations` was placed after other imports and TYPE_CHECKING blocks in 4 files, causing a `SyntaxError` at import time that silently propagated up as a strategy-load failure.

## Symptoms
- Closure test: `Status: FAIL`, `router_completion_pct: 0.0%`, `"Router V6 not available: All strategies exhausted"`
- No explicit `SyntaxError` in the test summary — the error was caught by the strategy resolver and reported as a generic strategy failure
- Running the test locally with `--require-all-stages` surfaced: `from __future__ imports must occur at the beginning of the file (pipeline.py, line 21)`

## What Didn't Work
- Grepping for `__future__` alone was insufficient — all 4 files had the import, just at the wrong line
- Grepping for `from __future__` in the first 3 lines of each file would have caught the issue: 307 files had it correct, only 4 were broken
- Ruff/isort don't flag `__future__` placement within TYPE_CHECKING blocks by default

## Solution
Move `from __future__ import annotations` to immediately after the module docstring, before any other imports.

```
# Before (broken):                   # After (fixed):
"""module docstring"""               """module docstring"""
import foo
from typing import TYPE_CHECKING     from __future__ import annotations
                                     import foo
if TYPE_CHECKING:                    from typing import TYPE_CHECKING
    from x import Y                  if TYPE_CHECKING:
                                         from x import Y
from __future__ import annotations
```

Files fixed (same pattern — move `__future__` to line after docstring):
- `router_v6/pipeline.py`: from line 21 to after docstring
- `io/kicad_exporter.py`: from line 9 to after docstring
- `pipeline/dag_expr.py`: from line 22 to after docstring
- `pcl/parser.py`: from line 28 to after docstring

## Why This Works
Python requires `from __future__ import ...` to be the first executable statement in a file — only a module docstring may precede it. When placed after other imports or TYPE_CHECKING blocks, Python raises `SyntaxError: from __future__ imports must occur at the beginning of the file`, preventing the entire module from loading. Since the error occurred in a dependency module of the router strategy, the strategy couldn't be imported, and the closure test fell through to "nothing routed."

## Prevention
- A pre-commit or CI check that verifies `from __future__ import` appears at line 1 or 2 (after docstring) in every Python file:
  ```bash
  rg -l 'from __future__ import' --glob '*.py' packages/ \
    | while read f; do
        head -5 "$f" | grep -q 'from __future__' || echo "MISPLACED: $f"
      done
  ```
- 90 BMC tests now run in CI (`tests/router_v6/ -m "not slow"`) which would catch a broken import chain that prevents router tests from collecting
