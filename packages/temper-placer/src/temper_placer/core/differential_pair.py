"""
Differential pair routing constraints.

This module defines constraints for routing differential pairs (e.g., USB D+/D-)
to maintain coupling and controlled impedance.

Migrated to Rust pyclass (Wave C, temper-design-bundle).
This module is now a pure-delegation shim re-exporting the pyclass.
"""

import temper_design_bundle_python as _tdb

DifferentialPairConstraint = _tdb.differential_pair_contracts.DifferentialPairConstraint

__all__ = ["DifferentialPairConstraint"]
