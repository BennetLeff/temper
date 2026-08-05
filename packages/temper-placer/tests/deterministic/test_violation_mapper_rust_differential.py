"""Differential test: deterministic feedback violation mapping, Rust vs oracle.

Wave 4, **Phase 5** (deterministic hubs slice). The regex-based compute of
``temper_placer/deterministic/feedback/violation_mapper.py``
(``ViolationComponentMapper.map_violation``) moves to
``temper_design_bundle_python.deterministic_hubs.map_violation_kernel``. The
Python module keeps its public API (``DRCViolation``/``MappedViolation`` stay
Python dataclasses) and delegates.

Bit-exactness pins:
- ``re.IGNORECASE`` patterns ``of ([A-Za-z0-9_]+)`` / ``pad ([A-Za-z0-9_]+)-`` /
  ``pad ([A-Za-z0-9_]+\\.)`` map to ``(?i)`` regex-crate patterns; captures and
  ``sorted(components)`` (byte-order == code-point order for ASCII refs) must
  match.
- Clearance extraction patterns (``([\\d\\.]+)mm < ([\\d\\.]+)mm required``
  first, then ``clearance ([\\d\\.]+) mm; actual ([\\d\\.]+) mm``) and the
  group-to-field mapping (pattern 1: g1=actual, g2=required; pattern 2:
  g1=required, g2=actual) must match; floats via ``float()`` == Rust
  ``parse::<f64>()``.
- Zone containment iterates ``zone_config`` in insertion order and uses
  Python ``min``/``max`` semantics (NaN-propagating), replicated manually in
  the kernel.
- The mapper's ``component_refs`` is captured from the Python netlist at
  init (orchestration stays Python); the kernel receives the ref set.
"""

from __future__ import annotations

import temper_design_bundle_python as _tdb
import tests.deterministic._violation_mapper_py_oracle as _oracle
from tests.core._contract_canon import canon

# Rust symbols under test — must exist or this file fails to collect (RED).
_DH = _tdb.deterministic_hubs
RS_MAP = _DH.map_violation_kernel


def _kernel(violation, zone_config, component_refs):
    pos = violation.pos
    return RS_MAP(
        list(violation.items),
        set(component_refs),
        pos[0] if pos is not None else None,
        pos[1] if pos is not None else None,
        violation.required,
        violation.actual,
        violation.description,
        zone_config,
    )


def _assert_mapped_parity(violation, zone_config=None, component_refs=("Q2", "U_GATE", "D1")):
    """Run both sides and compare the full MappedViolation field surface."""
    o = _oracle.ViolationComponentMapper(
        _NetlistStub(component_refs), zone_config
    ).map_violation(violation)
    components, zone, required, actual, involves_via, involves_pth = _kernel(
        violation, zone_config or {}, set(component_refs)
    )
    shim_fields = (
        violation.type,
        tuple(components),  # kernel's raw order — the oracle's list is
        # already sorted(components), so a sort-order regression is visible
        # here, not normalised away
        zone,
        required,
        actual,
        involves_via,
        involves_pth,
        violation.description,
    )
    oracle_fields = (
        o.type,
        tuple(o.components),
        o.zone,
        o.required_clearance,
        o.actual_clearance,
        o.involves_via,
        o.involves_pth,
        o.description,
    )
    assert canon(shim_fields) == canon(oracle_fields), f"parity divergence: {shim_fields} vs {oracle_fields}"


class _NetlistStub:
    def __init__(self, refs):
        self.components = [_RefStub(r) for r in refs]


class _RefStub:
    def __init__(self, ref):
        self.ref = ref


# ---------------------------------------------------------------------------
# Component-reference extraction
# ---------------------------------------------------------------------------


def test_short_violation_both_components():
    v = _oracle.DRCViolation(
        type="shorting_items",
        items=["Track on F.Cu at (67.5, 6.0)", "Pad Q2-D on F.Cu"],
        severity="error",
    )
    _assert_mapped_parity(v)


def test_solder_mask_bridge_pad_dash_and_dot_formats():
    v = _oracle.DRCViolation(
        type="solder_mask_bridge", items=["Pad Q2-D", "Pad U_GATE.8"], pos=(68.0, 5.5)
    )
    _assert_mapped_parity(v)


def test_of_ref_case_insensitive():
    # "OF q2" must match via IGNORECASE, ref "q2" is NOT in the component set
    # (refs are case-sensitive members) — only refs in the set are kept.
    v = _oracle.DRCViolation(type="clearance", items=["of Q2", "OF Q2"])
    _assert_mapped_parity(v)


def test_via_and_pth_detection_case_insensitive():
    v = _oracle.DRCViolation(
        type="hole_clearance", items=["Via at (68.0, 7.0)", "PTH pad Q2-S"], required=0.25
    )
    _assert_mapped_parity(v)
    v2 = _oracle.DRCViolation(type="hole_clearance", items=["vIa here", "pTh there"])
    _assert_mapped_parity(v2)


def test_unknown_refs_are_dropped():
    v = _oracle.DRCViolation(
        type="clearance", items=["of R99", "Pad R77-1", "Pad R55."], pos=(10.0, 10.0)
    )
    _assert_mapped_parity(v)


# ---------------------------------------------------------------------------
# Zone containment
# ---------------------------------------------------------------------------


def test_violation_maps_to_zone():
    v = _oracle.DRCViolation(type="clearance", pos=(67.5, 6.0))
    _assert_mapped_parity(v, zone_config={"HV_POWER": {"bounds": [(60, 0), (80, 15)]}})


def test_zone_supports_p2_p1_order():
    # (max, min) order must be normalised by min/max on both sides.
    v = _oracle.DRCViolation(type="clearance", pos=(70.0, 10.0))
    _assert_mapped_parity(v, zone_config={"Z": {"bounds": [(80, 15), (60, 0)]}})


def test_zone_no_match_falls_through():
    v = _oracle.DRCViolation(type="clearance", pos=(100.0, 100.0))
    _assert_mapped_parity(v, zone_config={"HV_POWER": {"bounds": [(60, 0), (80, 15)]}})


def test_zone_boundary_inclusive():
    v = _oracle.DRCViolation(type="clearance", pos=(60.0, 0.0))
    _assert_mapped_parity(v, zone_config={"HV_POWER": {"bounds": [(60, 0), (80, 15)]}})


def test_zone_skipped_without_pos():
    v = _oracle.DRCViolation(type="clearance", items=["of Q2"])
    _assert_mapped_parity(v, zone_config={"HV_POWER": {"bounds": [(60, 0), (80, 15)]}})


def test_multiple_zones_insertion_order_first_wins():
    v = _oracle.DRCViolation(type="clearance", pos=(65.0, 5.0))
    # Both zones contain (65,5); the FIRST in insertion order wins.
    _assert_mapped_parity(
        v,
        zone_config={
            "ZONE_A": {"bounds": [(0, 0), (100, 100)]},
            "ZONE_B": {"bounds": [(0, 0), (100, 100)]},
        },
    )


# ---------------------------------------------------------------------------
# Clearance extraction from description
# ---------------------------------------------------------------------------


def test_clearance_extraction_pattern1():
    v = _oracle.DRCViolation(
        type="clearance", description="Clearance violation (0.15mm < 0.20mm required)"
    )
    _assert_mapped_parity(v)


def test_clearance_extraction_pattern2():
    v = _oracle.DRCViolation(
        type="clearance", description="clearance 0.2000 mm; actual 0.1958 mm"
    )
    _assert_mapped_parity(v)


def test_clearance_uses_explicit_values_first():
    # required/actual already set -> description regex must NOT override.
    v = _oracle.DRCViolation(
        type="clearance",
        description="Clearance violation (0.15mm < 0.20mm required)",
        required=0.5,
        actual=0.25,
    )
    _assert_mapped_parity(v)


def test_clearance_partial_values_filled_from_description():
    # only one of required/actual set -> description fills the missing one.
    v = _oracle.DRCViolation(
        type="clearance",
        description="clearance 0.3000 mm; actual 0.2900 mm",
        required=0.3,
    )
    _assert_mapped_parity(v)


def test_clearance_no_pattern_no_description():
    v = _oracle.DRCViolation(type="clearance", description="something else entirely")
    _assert_mapped_parity(v)
    v2 = _oracle.DRCViolation(type="clearance")
    _assert_mapped_parity(v2)


def test_clearance_int_positions():
    # int-typed pos elements pass through (no float coercion on either side).
    v = _oracle.DRCViolation(type="clearance", pos=(67, 6))
    _assert_mapped_parity(v, zone_config={"HV_POWER": {"bounds": [(60, 0), (80, 15)]}})


def test_empty_items_no_components():
    v = _oracle.DRCViolation(type="clearance", items=[])
    _assert_mapped_parity(v)
