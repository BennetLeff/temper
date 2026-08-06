"""Load netclass_rules.yaml into a DesignRules instance.

The loader is implemented in Rust as pyo3 functions in the
``temper-design-bundle`` crate (the ``temper_design_bundle_python``
extension, ``src/loaders.rs``) — the Wave 4 Phase 3 formats/IO migration,
candidate 2
(``docs/plans/2026-08-02-001-feat-wave4-phase3-formats-io-plan.md``, R5).
This module keeps the pre-migration public API unchanged and re-exports the
Rust symbols directly (the pure-delegation pattern established by
``core/priority.py`` / ``core/loop.py``).

Two boundaries stay on the Python side of the pyo3 call, both deliberately
(see ``loaders.rs`` and ``packages/temper-design-bundle/VERIFICATION.md``):
``yaml.safe_load`` remains the tokenizer, because PyYAML implements YAML 1.1
and ``serde_yaml`` implements YAML 1.2 and the two genuinely disagree
(``on`` → ``True`` vs ``"on"``, ``012`` → ``10`` vs ``12``); and the
``DesignRules``/``NetClassRules`` objects are built by calling the very
constructors this module used to call, so construction parity is by
identity. Everything else — the field mapping, the per-key defaults, the
``class_pairs`` split/sort/dedup, the skipped-key warning — is Rust.

Verification: bit-identical parity against the pinned pre-migration
implementation is asserted by ``tests/io/test_loaders_rust_differential.py``
(oracle: ``tests/io/_netclass_loader_py_oracle.py``); the properties and
metamorphic relations live in ``tests/io/test_loaders_pbt.py`` and the
structural proof in ``packages/temper-design-bundle/VERIFICATION.md``.

API note (deliberate, documented deviation): ``NetClassRulesDict`` is now a
pyo3 pyclass rather than a ``@dataclass``. Its attribute surface,
mutability, field-wise ``__eq__`` and dataclass-shaped ``__repr__`` are
preserved, but ``dataclasses.fields()`` / ``dataclasses.asdict()`` no longer
apply to it. No consumer uses either (verified 2026-08-04).
"""

from __future__ import annotations

import logging

import temper_design_bundle_python as _tdb

# The migrated loader logs through this exact logger name, so handler and
# `caplog` configuration keyed on the module keeps working unchanged.
logger = logging.getLogger(__name__)

# Map classify_net_type() return values to DesignRules net class names
_NET_TYPE_TO_CLASS = {
    "ground": "GND",
    "power": "Power",
    "hv": "HighVoltage",
    "signal": "Signal",
}

NetClassRulesDict = _tdb.NetClassRulesDict
load_netclass_rules = _tdb.load_netclass_rules

__all__ = ["NetClassRulesDict", "load_netclass_rules"]
