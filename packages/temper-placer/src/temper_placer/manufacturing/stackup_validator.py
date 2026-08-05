"""Professional PCB stackup validation checks.

Validates the 4-layer Temper board against industry-standard
stackup quality criteria: effective copper symmetry, return-path
adjacency for differential nets, controlled-impedance specification,
and copper density balance.

All checks return advisory warnings -- they do not block the pipeline.

The implementation migrated to Rust (``temper_io_types``,
``stackup_validator.rs``) under the Wave 4 Phase 4 leftovers slice — the
home crate is ``temper-io-types`` because the validator consumes the
``LayerStackup`` pyclass (the stackup primitives landed by the Wave 4
Phase 3 parse-engine work, PR #723) as an opaque Python object across the
pyo3 boundary. This module keeps the pre-migration public API unchanged
and re-exports the Rust pyclasses/functions directly (the pure-delegation
pattern established by ``io/footprint_library.py``).

The ``routing_results`` fill arm calls back into
``temper_placer.router_v6.copper_balance.analyze_copper_balance`` — the
router stays Python (another Wave-4 slice's surface); the call-back, its
kwargs and the dict comprehension are transcribed in Rust and exercised by
the differential.

Verification: bit-identical parity against the pinned pre-migration
implementation — including the byte-exact warning message strings, the
``details`` dicts' float bits, the fail-closed ``all_passed``, and the
``summary()`` rendering — is asserted by
``tests/manufacturing/test_stackup_validator_rust_differential.py``
(oracle: ``tests/manufacturing/_stackup_validator_py_oracle.py``) and the
closed-form properties in
``tests/manufacturing/test_stackup_validator_pbt.py``; the structural
proof lives in ``packages/temper-io-types/VERIFICATION.md``.
"""

from __future__ import annotations

from temper_io_types import (
    StackupValidationResult,
    StackupValidationReport,
    validate_stackup,
)

# IPC-2221 / IPC-6012 guidance: 25-75% copper fill per layer to avoid
# warping during reflow.  Power-electronics boards may push to 20-80%
# on outer layers carrying high current.
COPPER_BALANCE_MIN_PCT: float = 25.0
COPPER_BALANCE_MAX_PCT: float = 75.0

# USB 2.0 Full-Speed (12 Mbps) differential impedance target.
# ESP32-S3 uses USB OTG 1.1 -- standard 90Ω differential.
USB_DIFFERENTIAL_IMPEDANCE_OHMS: float = 90.0

# Effective copper-weight imbalance threshold above which a warping
# risk warning fires.  Expressed as (max_eff - min_eff) / total_eff.
COPPER_SYMMETRY_IMBALANCE_THRESHOLD: float = 0.25

__all__ = [
    "StackupValidationResult",
    "StackupValidationReport",
    "validate_stackup",
    "COPPER_BALANCE_MIN_PCT",
    "COPPER_BALANCE_MAX_PCT",
    "USB_DIFFERENTIAL_IMPEDANCE_OHMS",
    "COPPER_SYMMETRY_IMBALANCE_THRESHOLD",
]
