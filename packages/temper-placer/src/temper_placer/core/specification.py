"""
Physical design specifications for PCB validation.

This module delegates the data structures to Rust pyo3 pyclasses in
``temper_design_bundle_python.specification_contracts`` (Wave 4 fan-out
migration). The YAML ``load`` classmethod is a JUSTIFIED-KEEP library
boundary — ``yaml.safe_load`` stays in Python.
"""

from __future__ import annotations

from pathlib import Path

import yaml  # type: ignore[import-untyped]

import temper_design_bundle_python as _tdb

# Re-export the Rust pyclasses (attribute access because pyo3 submodules
# are not directly importable as ``parent.child``).
EMISpec = _tdb.specification_contracts.EMISpec
_RustPcbSpecification = _tdb.specification_contracts.PcbSpecification
SafetySpec = _tdb.specification_contracts.SafetySpec
SignalIntegritySpec = _tdb.specification_contracts.SignalIntegritySpec
ThermalSpec = _tdb.specification_contracts.ThermalSpec


# ---------------------------------------------------------------------------
# YAML boundary — JUSTIFIED-KEEP: yaml.safe_load is a library boundary
# (no mature Rust YAML parser with bit-identical float semantics).
# The record layer migrates; the marshalling stays Python.
# ---------------------------------------------------------------------------


def _load_pcb_specification(cls: type, path: Path) -> _RustPcbSpecification:
    """Load specification from YAML file.

    This is a classmethod monkey-patched onto the Rust pyclass so that
    ``PcbSpecification.load(path)`` continues to work after migration.
    """
    with open(path) as f:
        data = yaml.safe_load(f)

    thermal = ThermalSpec(**data.get("thermal", {}))
    emi = EMISpec(**data.get("emi", {}))
    si = SignalIntegritySpec(**data.get("signal_integrity", {}))

    safety = None
    safety_data = data.get("safety")
    if safety_data is not None:
        safety = SafetySpec(**safety_data)

    return cls(
        name=data.get("name", path.stem),
        thermal=thermal,
        emi=emi,
        signal_integrity=si,
        safety=safety,
    )


# Monkey-patch the load classmethod onto the Rust pyclass.
_RustPcbSpecification.load = classmethod(_load_pcb_specification)

# Re-export with the correct name.
PcbSpecification = _RustPcbSpecification

__all__ = [
    "EMISpec",
    "PcbSpecification",
    "SafetySpec",
    "SignalIntegritySpec",
    "ThermalSpec",
]
