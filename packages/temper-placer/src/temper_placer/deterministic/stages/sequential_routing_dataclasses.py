"""Configuration dataclasses for sequential routing.

The ``DiffPairConfig`` dataclass is implemented as a pyo3 pyclass in the
``temper-design-bundle`` crate (Wave 4 **Phase 5, batch 2** — deterministic
leaf stages); this module re-exports it under the pre-migration name so
every ``from ...sequential_routing_dataclasses import DiffPairConfig``
import path is unchanged.

Bit-exactness: the pyclass preserves the dataclass's no-coercion field
storage (an ``int`` passed for ``spacing_mm`` stays an ``int``), its
defaults (``0.15`` / ``0.5`` / ``0.5``), all-five-field equality, and the
CPython repr. Verified by
``tests/deterministic/stages/test_sequential_routing_dataclasses_rust_differential.py``
(oracle: ``tests/deterministic/stages/_sequential_routing_dataclasses_py_oracle.py``);
the structural proof lives in ``packages/temper-design-bundle/VERIFICATION.md``.
"""

from temper_design_bundle_python import DiffPairConfig

__all__ = ["DiffPairConfig"]
