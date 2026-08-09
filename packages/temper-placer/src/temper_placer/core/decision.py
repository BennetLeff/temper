"""
Decision audit-trail data structures for placement/routing explainability.

This module defines data structures for recording, querying, and serializing
auditable decisions made during the placement and routing process. Each
decision carries its subject, chosen value, justification, and the set of
alternatives that were considered and rejected.

Migrated to Rust pyclasses (Wave C, temper-design-bundle).
This module is now a pure-delegation shim re-exporting the pyclasses.
"""

import temper_design_bundle_python as _tdb

Alternative = _tdb.decision_contracts.Alternative
Decision = _tdb.decision_contracts.Decision
DecisionTrace = _tdb.decision_contracts.DecisionTrace

__all__ = ["Alternative", "Decision", "DecisionTrace"]
