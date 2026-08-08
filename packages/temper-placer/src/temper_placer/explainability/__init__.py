"""Explainability module for temper-placer.

This module provides auditable decision tracking for placement and routing.
Every decision the placer makes can be traced back to its reason. The
substantive types (Decision, DecisionTrace, Trace, ...) live in this
package's submodules (decision.py, trace.py, serialization.py,
markdown_report.py) and are unaffected by this change.

The `from temper_placer.explainability import X` re-export surface that
used to live here was removed 2026-08-07
(docs/plans/2026-08-06-001-docs-python-removal-retriage-plan.md DELETE
pass): no consumer in src/tests/scripts/benchmarks imports through this
package root -- every real caller already imports the submodule directly
(e.g. `temper_placer.explainability.decision`). One orphaned, non-CI script
(`tools/demo_explainability_file.py`) does `from temper_placer.explainability
import Trace`; it already guards the import in a try/except ImportError and
is not exercised by any test or workflow.

The file itself is kept (not deleted) because `.importlinter`'s
core-public-interface-only and router-v6-public-interface-only contracts
name `temper_placer.explainability` as a source_module; grimp cannot
resolve a namespace package (no __init__.py) as a module, so removing the
file outright breaks the import-boundary CI gate.
"""
