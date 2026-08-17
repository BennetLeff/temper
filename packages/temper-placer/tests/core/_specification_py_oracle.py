"""
Pinned Python oracle for ``temper_placer/core/specification.py`` (Wave 4, fan-out).

This file is a VERBATIM copy of the pre-migration dataclass implementations of
``temper_placer/core/specification.py`` as of commit on ``origin/main``
(before migration). The module imports only the Python stdlib, so no relative
imports needed rewriting.

DO NOT EDIT THE SEMANTICS. This is the oracle the Rust pyo3 pyclasses
(``temper_design_bundle_python``) must reproduce bit-identically; any
edit here silently weakens the differential proof. If the module's
contract changes, the oracle must be re-pinned from the new base first.

The YAML ``load`` classmethod is explicitly NOT included — it is a library
boundary (``yaml.safe_load``), and per the migration spec the yaml marshalling
is JUSTIFIED-KEEP, staying in the Python shim.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class _OracleThermalSpec:
    """Thermal management targets."""

    # RE-PINNED 2026-08-15: defaults now mirror the corrected Rust
    # ThermalSpec — max_junction_temp_c = 125 (the datasheet-recovery
    # "design for ≤125 °C" junction limit; the 110 had no documented
    # basis) and ambient_temp_c = 60 (the design-limit ambient,
    # ENVIRONMENTAL_SPEC.md derating zero-power point). Decision doc
    # 2026-08-15 §6.4; see
    # docs/evidence/2026-08-15-thermal-corrections-implemented.md.
    max_junction_temp_c: float = 125.0
    ambient_temp_c: float = 60.0
    power_dissipation: dict[str, float] = field(default_factory=dict)
    target_edge: str = "TOP"
    max_heatspread_mm: float = 10.0


@dataclass
class _OracleEMISpec:
    """EMI performance targets (loop areas)."""

    max_loop_area_mm2: dict[str, float] = field(default_factory=dict)
    loop_components: dict[str, list[str]] = field(default_factory=dict)
    frequency_hz: float = 100000.0


@dataclass
class _OracleSignalIntegritySpec:
    """Signal integrity targets."""

    max_length_mm: dict[str, float] = field(default_factory=dict)
    length_match_mm: dict[str, float] = field(default_factory=dict)


@dataclass
class _OracleSafetySpec:
    """Safety-critical specifications for mains-connected designs.

    Follows IEC 60335-1 for clearance and creepage requirements.
    """

    # RE-PINNED 2026-08-17: defaults now mirror the corrected Rust
    # SafetySpec -- mains_voltage_v = 120.0 (this design is a US 120V RMS
    # +-10% appliance; docs/specs/REQUIREMENTS.md REQ-SYS-01,
    # elec/src/main.ato's own v_ac_nominal = 120V assert) and
    # pollution_degree = 3 (PD3 is the enforced degree; the as-built board
    # is forced-air vented with no sealed compartment; 2026-08-15
    # data-driven decision, docs/evidence/2026-08-15-pd2-pd3-data-driven-
    # decision.md). See docs/evidence/2026-08-17-safetyspec-default-repin.md.
    mains_voltage_v: float = 120.0
    pollution_degree: int = 3


@dataclass
class _OraclePcbSpecification:
    """Complete physical specification for a design."""

    name: str = "Unnamed Design"
    thermal: _OracleThermalSpec = field(default_factory=_OracleThermalSpec)
    emi: _OracleEMISpec = field(default_factory=_OracleEMISpec)
    signal_integrity: _OracleSignalIntegritySpec = field(
        default_factory=_OracleSignalIntegritySpec
    )
    safety: _OracleSafetySpec | None = None
