"""Pinned Python oracle for the pre-port ``IEC60335_REQUIREMENTS`` matrix
(placer constraint/clearance Rust-port stage 1, 2026-08-17).

This file is a VERBATIM copy of the ``IEC60335_REQUIREMENTS`` dict body
(and the two enums it is keyed on) as it stood in
``temper_placer/requirements/validators/clearance.py`` immediately BEFORE
that dict was replaced with a call into
``temper_orchestration``'s Rust ``requirement_matrix()`` /
``req_safe_01_requirement_matrix()`` accessor (see
``docs/evidence/2026-08-17-domain-clearance-netclass-rust-port-stages-1-2.md``).

Per the port's own spike (``docs/evidence/2026-08-17-placer-constraint-
rust-port-spike.md``), no oracle existed for this matrix before the port
(``scripts/oracle_hashes.json`` had zero entries for ``domain_clearance``/
``netclass_constraints`` at spike time) -- this is oracle CREATION, not a
re-pin, per ``docs/migration-pipeline.md`` stage 3 (pin the pre-migration
Python first, then prove the Rust replacement matches it row-for-row).

DO NOT EDIT THE VALUES. This is the oracle
``tests/requirements/test_iec60335_requirements_rust_differential.py``
proves the Rust ``requirement_matrix()``/``req_safe_01_requirement_matrix()``
reproduces bit-identically. If the underlying safety values ever
legitimately change, that is a separate, deliberately-committed re-pin with
its own evidence -- never an edit to make a failing differential pass.
"""

from __future__ import annotations

from enum import Enum


class InsulationType(str, Enum):
    """Insulation type per IEC 60335-2-6 (verbatim pre-port copy)."""

    BASIC = "basic"
    REINFORCED = "reinforced"
    FUNCTIONAL = "functional"


class VoltageDomain(str, Enum):
    """Voltage domains in Temper PCB (verbatim pre-port copy)."""

    MAINS = "MAINS"
    DC_BUS = "DC_BUS"
    BOOTSTRAP = "BOOTSTRAP"
    LV_CONTROL = "LV_CONTROL"
    ISOLATED = "ISOLATED"


# Verbatim copy of `IEC60335_REQUIREMENTS` as committed at
# `packages/temper-placer/src/temper_placer/requirements/validators/clearance.py`
# immediately before the 2026-08-17 stage-1 port (commit range starting
# `caec25d61`). Dict insertion order is part of the pin -- the differential
# test compares row-for-row in this exact order.
IEC60335_REQUIREMENTS = {
    (VoltageDomain.MAINS, VoltageDomain.LV_CONTROL, InsulationType.BASIC): {
        "min_clearance_mm": 3.0,
        "min_creepage_mm": 6.3,
        "design_value_mm": 8.3,
    },
    (VoltageDomain.MAINS, VoltageDomain.LV_CONTROL, InsulationType.REINFORCED): {
        "min_clearance_mm": 6.0,
        "min_creepage_mm": 12.6,
        "design_value_mm": 14.6,
    },
    (VoltageDomain.DC_BUS, VoltageDomain.LV_CONTROL, InsulationType.BASIC): {
        "min_clearance_mm": 3.0,
        "min_creepage_mm": 6.3,
        "design_value_mm": 8.3,
    },
    (VoltageDomain.DC_BUS, VoltageDomain.LV_CONTROL, InsulationType.REINFORCED): {
        "min_clearance_mm": 6.0,
        "min_creepage_mm": 12.6,
        "design_value_mm": 14.6,
    },
    (VoltageDomain.MAINS, VoltageDomain.ISOLATED, InsulationType.REINFORCED): {
        "min_clearance_mm": 6.0,
        "min_creepage_mm": 12.6,
        "design_value_mm": 14.6,
    },
    (VoltageDomain.LV_CONTROL, VoltageDomain.LV_CONTROL, InsulationType.FUNCTIONAL): {
        "min_clearance_mm": 0.5,
        "min_creepage_mm": 1.8,
        "design_value_mm": 2.0,
    },
}
