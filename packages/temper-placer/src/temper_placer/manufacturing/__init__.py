"""Manufacturing variability models for PCB design validation.

This package provides tolerance analysis for manufacturing variability:
- Level 1: Simple inflation (in core/manufacturing.py)
- Level 2: Per-parameter tolerance model (tolerances.py)
- Level 3: Monte Carlo analysis (future)

The re-export of tolerances.py's public names that used to live here was
removed 2026-08-07 (docs/plans/2026-08-06-001-docs-python-removal-retriage-plan.md
DELETE pass): zero consumers did `from temper_placer.manufacturing import X`
anywhere in src/tests/scripts/benchmarks/tools -- every real caller already
imports `temper_placer.manufacturing.tolerances` directly. The file itself is
kept (not deleted) because `.importlinter`'s core-public-interface-only and
router-v6-public-interface-only contracts name `temper_placer.manufacturing`
as a source_module; grimp cannot resolve a namespace package (no __init__.py)
as a module, so removing the file outright breaks the import-boundary CI gate.
"""
