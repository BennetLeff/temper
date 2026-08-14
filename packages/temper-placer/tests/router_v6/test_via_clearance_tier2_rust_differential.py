"""R1a differential: the Wave-4 tier-2 via/clearance/grid cluster vs its pinned oracles.

Verification unit: ``router_v6/{via_placement, clearance_engine, grid_converter,
path_simplify}.py`` (home crate ``temper-geometry``, kernel module
``temper_geometry.via_clearance``).

Migrated kernels
----------------
* ``via_placement`` — ``_get_adjacent_layer`` (the shipped ``dict.get`` layer
  map) and ``_place_vias_for_path``'s segment-layer derivation (the
  ``abs(...) < 1e-4`` both-axes segment match, then ``segs[vi][2]`` /
  ``segs[vi+1][2]`` with the ``"F.Cu"``/``"B.Cu"`` fallback).  Pinned via
  ``_oracle_get_adjacent_layer`` / ``_oracle_place_vias_for_path`` — verbatim
  copies of the committed module.
* ``clearance_engine`` — ``calculate_safety_distances`` (the IEC 60950-1
  clearance/creepage tables + overvoltage/pollution multipliers),
  ``_kw_boundary_match`` (the ``(?:^|_)kw(?:$|[\\d_])`` word-boundary regex),
  and ``_net_class_to_voltage_class`` (the IEC 60335-1 voltage-class
  branching).  Pinned via ``_oracle_calculate_safety_distances``,
  ``_oracle_kw_boundary_match``, ``_oracle_net_class_to_voltage_class`` and
  the composite ``_oracle_get_clearance`` — all verbatim copies.
* ``grid_converter`` — ``grid_to_world``, ``extract_vias``,
  ``compute_path_length``, ``count_vias_in_path``.  Pinned via the four
  ``_oracle_*`` copies below.
* ``path_simplify`` — ``is_collinear``, ``simplify_path``,
  ``estimate_segment_count``.  These were migrated to ``temper-rust-router``
  in an earlier slice (#856); this tier **re-homes** them into
  ``temper-geometry`` (the Wave-4 home crate for router_v6 geometry) and the
  existing pinned oracle ``tests/router_v6/_path_simplify_py_oracle.py`` is
  reused verbatim as the reference.

Comparison discipline: ``tests/router_v6/_signature.sig`` — type-carrying,
bit-exact (``float.hex()``), no tolerance anywhere.  Floats are the IEC
tables' exact literals (bit-identical doubles in Python and Rust) and the
grid arithmetic (int * f64 with the same left-to-right expression shape);
there is no libm transcendental in the unit, so the Wave-4 B1/B2/B4/B6/B7
catalog classes do not apply here.

``test_oracle_is_verbatim_copy`` re-extracts each oracle definition from the
pinned commit and compares it character-for-character (after normalising the
``_oracle_`` name prefix).
"""

from __future__ import annotations

import ast
import random
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

import tests.router_v6._path_simplify_py_oracle as PS_ORACLE
from temper_placer.core.net_types import VoltageClass
from temper_placer.router_v6.clearance_engine import (
    calculate_safety_distances as _shim_safety_distances,
)
from temper_placer.router_v6.clearance_engine import (
    get_clearance,
)
from temper_placer.router_v6.creepage_check import _calculate_required_creepage
from temper_placer.router_v6.grid_converter import (
    GridCell as ShimGridCell,
)
from temper_placer.router_v6.grid_converter import (
    compute_path_length,
    count_vias_in_path,
    grid_to_world,
)
from temper_placer.router_v6.grid_converter import (
    extract_vias as _shim_extract_vias,
)
from temper_placer.router_v6.via_placement import (
    _get_adjacent_layer as _shim_adjacent_layer,
)
from temper_placer.router_v6.via_placement import (
    _place_vias_for_path,
)
from tests.router_v6._pending_rust import missing_symbols, rust
from tests.router_v6._signature import sig

# ===========================================================================
# ADAPTER BLOCK -- the ONLY part of this file that knows the Rust arm exists.
# Phase B binds these; no assertion and no corpus row below changes.
# ===========================================================================

_RUST_MODULE = "temper_geometry"

REQUIRED_RUST_SYMBOLS: tuple[str, ...] = (
    "adjacent_layer_py",
    "via_layer_pair_py",
    "safety_distances_py",
    "kw_boundary_match_py",
    "net_class_to_voltage_class_py",
    "grid_to_world_py",
    "extract_vias_py",
    "compute_path_length_py",
    "count_vias_in_path_py",
    "is_collinear_py",
    "simplify_path_py",
    "estimate_segment_count_py",
)


def _rust(symbol: str):
    return rust(_RUST_MODULE, symbol)


# ===========================================================================
# END ADAPTER BLOCK
# ===========================================================================

# ---------------------------------------------------------------------------
# Verbatim pre-migration oracles -- copied from the modules AS COMMITTED at
# the dispatch base (origin/main f1ffc013).  Do NOT edit: they are the
# reference.  Only the `_oracle_` name prefix is an edit (so the originals
# stay importable under their own names in this module, which the verbatim
# `_oracle_place_vias_for_path` / `_oracle_get_clearance` bodies rely on via
# the aliases at the end of this block).
# ---------------------------------------------------------------------------

# -- via_placement.py -------------------------------------------------------


@dataclass
class _OracleVia:
    position: tuple[float, float]
    from_layer: str
    to_layer: str
    diameter: float
    drill: float
    net_name: str


Via = _OracleVia


def _oracle_get_adjacent_layer(layer_name: str) -> str | None:
    """
    Get adjacent layer for via transition.

    Args:
        layer_name: Current layer (e.g., "F.Cu")

    Returns:
        Adjacent layer name or None
    """
    # Simplified layer mapping
    layer_map = {
        "F.Cu": "In1.Cu",
        "In1.Cu": "In2.Cu",
        "In2.Cu": "B.Cu",
        "B.Cu": "In2.Cu",
    }

    return layer_map.get(layer_name)


def _oracle_place_vias_for_path(
    net_name: str,
    route_path,
    via_diameter: float,
    via_drill: float,
) -> list[Via]:
    """
    Place vias for a single routed path.

    Args:
        net_name: Net name
        route_path: RoutePath from pathfinding
        via_diameter: Via diameter
        via_drill: Drill diameter

    Returns:
        List of vias for this path
    """
    vias = []

    # If RoutePath3D, use explicit via_positions from pathfinder.
    # U3: derive from_layer/to_layer from the actual segment layers on
    # either side of each transition, not the hardcoded F.Cu/B.Cu pair.
    if hasattr(route_path, "via_positions") and hasattr(route_path, "segments"):
        segs = route_path.segments
        for vx, vy in route_path.via_positions:
            vi = None
            for i, (sx, sy, _) in enumerate(segs):
                if abs(sx - vx) < 1e-4 and abs(sy - vy) < 1e-4:
                    vi = i
                    break
            if vi is not None and vi + 1 < len(segs):
                from_layer = segs[vi][2]
                to_layer = segs[vi + 1][2]
            else:
                from_layer = "F.Cu"
                to_layer = "B.Cu"
            vias.append(
                Via(
                    position=(vx, vy),
                    from_layer=from_layer,
                    to_layer=to_layer,
                    diameter=via_diameter,
                    drill=via_drill,
                    net_name=net_name,
                )
            )
        return vias

    # Legacy fallback for RoutePath
    if hasattr(route_path, "coordinates") and len(route_path.coordinates) >= 3:
        # Add a via at the midpoint for demonstration
        mid_idx = len(route_path.coordinates) // 2
        via_pos = route_path.coordinates[mid_idx]

        # Determine layers (simplified)
        from_layer = route_path.layer_name
        to_layer = _get_adjacent_layer(from_layer)

        if to_layer:
            via = Via(
                position=via_pos,
                from_layer=from_layer,
                to_layer=to_layer,
                diameter=via_diameter,
                drill=via_drill,
                net_name=net_name,
            )
            vias.append(via)

    return vias


# -- clearance_engine.py -----------------------------------------------------

INTERNAL_LAYER_CREEPAGE_FACTOR: float = 0.30


def _oracle_calculate_safety_distances(
    voltage_v: float,
    pollution_degree: int = 2,
    _material_group: str = "IIIa",
    overvoltage_category: int = 2,
):
    """Calculate required creepage and clearance per IEC 60950-1.

    Based on Table 2K (clearance) and Table 2N (creepage) from IEC 60950-1.
    Conservative values for PCB routing.

    Returns:
        SafetyDistances dataclass with clearance_mm, creepage_mm, voltage_v.
    """
    from dataclasses import dataclass

    @dataclass
    class SafetyDistances:
        clearance_mm: float
        creepage_mm: float
        voltage_v: float

    clearance_table = [
        (50, 0.2),
        (150, 1.0),
        (300, 2.0),
        (600, 2.5),
        (1000, 4.0),
        (float("inf"), 5.0),
    ]
    creepage_table = [
        (50, 0.4),
        (150, 2.0),
        (300, 2.5),
        (600, 3.0),
        (1000, 5.0),
        (float("inf"), 8.0),
    ]
    clearance_mm = 0.2
    for vl, d in clearance_table:
        if voltage_v <= vl:
            clearance_mm = d
            break
    creepage_mm = 0.4
    for vl, d in creepage_table:
        if voltage_v <= vl:
            creepage_mm = d
            break
    if overvoltage_category >= 3:
        clearance_mm *= 1.25
        creepage_mm *= 1.25
    if pollution_degree >= 3:
        creepage_mm *= 2.0
    return SafetyDistances(
        clearance_mm=clearance_mm,
        creepage_mm=creepage_mm,
        voltage_v=voltage_v,
    )


def _oracle_kw_boundary_match(upper: str, keywords: tuple[str, ...]) -> bool:
    """Word-boundary keyword match, delimited by ``_`` or start/end of string.

    Bug history (2026-07-27, ``clearance_engine.py:125``, the third
    confirmed instance of this defect class -- see
    ``docs/evidence/2026-07-27-net-classification-gate.md``): this
    function's predecessor used plain substring matching
    (``kw in upper for kw in ("HIGH_VOLTAGE", "HV", "MAINS_240V", "MAINS",
    "AC")``). Bare ``"HV"``/``"AC"`` as substrings match any label that
    merely *contains* those two letters in sequence -- the exact same
    class of bug already fixed twice elsewhere in this module family:
    ``creepage_check._is_high_voltage_net`` (merge ``5076e715`` -- ``"L1"``/
    ``"L2"``/``"LINE"`` substrings matched ``COIL1``/``COIL2``/``...-line``,
    producing 24/24 false-positive creepage violations) and
    ``clearance_check._get_required_clearance`` (merge ``466c7724`` -- a
    narrow 4-keyword substring list under-matched 11 real HV-domain nets).
    This function was not proven to have live false positives against the
    project's actual net names (its only caller passes canonical labels
    like ``"HV"``/``"GND"``/``"POWER"``/``"SIGNAL"``, none of which happen
    to collide) but its own docstring documents it as accepting arbitrary
    caller-supplied strings, so it carries the same latent risk and is
    fixed with the same technique for consistency and defense-in-depth,
    rather than left as the one unfixed instance of a defect class already
    confirmed three times in this repo.

    Mirrors ``creepage_check._is_high_voltage_net``'s regex exactly:
    a keyword must be preceded by ``_``/start-of-string and followed by
    ``_``/digit/end-of-string to count as a match.
    """
    return any(
        re.search(rf"(?:^|_){re.escape(kw)}(?:$|[\d_])", upper) for kw in keywords
    )


def _oracle_net_class_to_voltage_class(net_class: str) -> VoltageClass:
    """Map a free-form net-class string to an IEC 60335-1 ``VoltageClass``.

    The mapping is intentionally broad so callers can pass short labels
    (``"HV"``, ``"LV"``) or full names (``"HIGH_VOLTAGE"``) and still
    get the right table-entry. All keyword matching is word-boundary
    (delimited by ``_`` or start/end of string) -- see
    :func:`_kw_boundary_match`'s docstring for why plain substring
    matching here would repeat a defect class already confirmed three
    times in this repo.
    """
    upper = net_class.upper()

    if _kw_boundary_match(upper, ("HIGH_VOLTAGE", "HV", "MAINS_240V", "MAINS", "AC")):
        # Distinguish 120 V vs 240 V when possible. "120"/"240" are
        # typically followed by a "V" unit suffix (e.g. "MAINS_120V"),
        # which the standard trailing boundary (`$`/digit/`_`) does not
        # cover -- so the trailing-boundary set is widened to also accept
        # a literal "V" immediately after the digits, rather than falling
        # back to an unanchored substring test (found by
        # scripts/check_net_classification.py auditing this function a
        # second time; see
        # docs/evidence/2026-07-27-net-classification-gate.md).
        if re.search(r"(?:^|_)120(?:V|$|[\d_])", upper):
            return VoltageClass.MAINS_120V
        if re.search(r"(?:^|_)240(?:V|$|[\d_])", upper) or _kw_boundary_match(upper, ("MAINS",)):
            return VoltageClass.MAINS_240V
        return VoltageClass.HIGH_VOLTAGE

    if re.search(r"(?:^|_)120(?:V|$|[\d_])", upper) or _kw_boundary_match(upper, ("MAINS_120V",)):
        return VoltageClass.MAINS_120V

    if _kw_boundary_match(upper, ("LOW_VOLTAGE", "LV", "POWER")):
        return VoltageClass.LOW_VOLTAGE

    # Everything else (Signal, GND, SELV, …) → SELV (lowest requirements)
    return VoltageClass.SELV


def _oracle_get_clearance(
    net_class_a: str,
    net_class_b: str,
    voltage: float,
    layer_type: str = "external",
    pollution_degree: int = 2,
    material_group: str = "IIIa",
    overvoltage_category: int = 2,
    *,
    design_rule_creepage: float | None = None,
) -> float:
    """Return the most-conservative clearance (mm) across all applicable standards.

    Composite oracle (the committed `get_clearance` body) so the shim's
    `get_clearance` can be A/B'd against the pre-migration orchestration
    composing the pure-Python kernels. NOT in `_ORACLE_SOURCES` /
    `test_oracle_is_verbatim_copy`'s character-for-character pin (that check
    covers `_oracle_calculate_safety_distances`, `_oracle_kw_boundary_match`
    and `_oracle_net_class_to_voltage_class` only), so unlike those three
    this function is not a byte-frozen historical snapshot -- it is the hand
    composed orchestration around them, which is why it is fixable here.

    RE-PIN (2026-08-14, its own commit, separate from the behavioral fix it
    tracks): the `vc.get_creepage_mm()` no-arg call (material_group discard)
    and the un-floored `> 0.5` internal-layer reduction below were both
    confirmed defects, not intended reference behavior -- see
    `temper-orchestration/src/clearance.rs::get_clearance_impl`'s fix
    (234ce918d, then the non-monotonicity floor fix) and
    `_clearance_family_py_oracle.py`'s matching re-pin for the full
    citation and the exhaustive-sweep evidence this correction was gated on.
    """
    candidates: list[float] = []

    # ---- IEC 60950-1 ---------------------------------------------------
    try:
        iec60950 = calculate_safety_distances(
            voltage_v=voltage,
            pollution_degree=pollution_degree,
            _material_group=material_group,
            overvoltage_category=overvoltage_category,
        )
        candidates.append(iec60950.clearance_mm)
        candidates.append(iec60950.creepage_mm)
    except Exception:
        pass  # Degrade gracefully if the table somehow fails

    # ---- IEC 60335-1 (VoltageClass tables) ----------------------------
    try:
        vc_a = _net_class_to_voltage_class(net_class_a)
        vc_b = _net_class_to_voltage_class(net_class_b)
        # Re-pin (2026-08-14): was `vc.get_creepage_mm()` (no-arg,
        # material_group discard) -- see the docstring above. Bucket mapping
        # mirrors `MaterialGroup::parse`/`creepage_bucket` in clearance.rs;
        # this block is inside the `try/except Exception: pass` above (a
        # pre-existing structural choice, not introduced by this re-pin), so
        # a hard raise here would just be silently swallowed rather than
        # propagate like the live code's `PyValueError` does -- no test
        # exercises an unrecognized label (every call site keeps the
        # "IIIa" default), so this is documented rather than worked around.
        bucket = {"I": 1, "II": 2, "IIIa": 3, "IIIb": 3}.get(material_group.strip(), 3)
        # Use the more demanding of the two net classes
        for vc in (vc_a, vc_b):
            candidates.append(vc.get_clearance_mm(pollution_degree))
            candidates.append(vc.get_creepage_mm(bucket))
    except Exception:
        pass

    # ---- IPC-2221 (generic PCB creepage table) ------------------------
    try:
        ipc = _calculate_required_creepage(voltage)
        candidates.append(ipc)
    except Exception:
        pass

    # ---- IEC 62368-1 (design-rule creepage from NetClassRules) --------
    if design_rule_creepage is not None and design_rule_creepage > 0.0:
        candidates.append(design_rule_creepage)

    # ---- Compute base conservative value -------------------------------
    if not candidates:
        # All standards failed — return a safe default
        return 0.5

    result = max(candidates)

    # ---- IEC 60664-1 internal-layer reduction -------------------------
    # Re-pin (2026-08-14): floored at `.max(0.5)` -- same non-monotonicity
    # fix as `_clearance_family_py_oracle.py`'s `get_clearance` and
    # `temper-orchestration/src/clearance.rs::get_clearance_impl`. `0.30`
    # and `0.5` both keep their pre-existing values; only the floor is new.
    if layer_type == "internal" and result > 0.5:
        result = max(result * INTERNAL_LAYER_CREEPAGE_FACTOR, 0.5)

    return result


# -- grid_converter.py -------------------------------------------------------


@dataclass
class _OracleGridCell:
    """Grid cell coordinates (x, y, layer)."""

    x: int
    y: int
    layer: int = 0


GridCell = _OracleGridCell


def _oracle_grid_to_world(
    cell: GridCell,
    origin: tuple[float, float],
    cell_size: float,
) -> tuple[float, float]:
    """Convert grid cell to world coordinates (mm).

    Returns center of cell in PCB coordinate system.

    Args:
        cell: Grid cell coordinates
        origin: PCB origin (x0, y0) in mm
        cell_size: Grid cell size in mm

    Returns:
        (x, y) position in mm, at cell center

    Example:
        >>> cell = GridCell(x=10, y=20, layer=0)
        >>> grid_to_world(cell, origin=(0, 0), cell_size=0.5)
        (5.25, 10.25)  # Cell center at (10*0.5 + 0.5/2, 20*0.5 + 0.5/2)
    """
    x = origin[0] + cell.x * cell_size + cell_size / 2
    y = origin[1] + cell.y * cell_size + cell_size / 2
    return (x, y)


def _oracle_extract_vias(cells: list[GridCell]) -> list[int]:
    """Find indices where layer transitions occur.

    A via is required when consecutive cells are on different layers.

    Args:
        cells: Ordered list of grid cells forming a path

    Returns:
        List of cell indices where vias are needed

    Example:
        >>> cells = [
        ...     GridCell(0, 0, 0),
        ...     GridCell(1, 0, 0),
        ...     GridCell(1, 0, 1),  # Via here
        ...     GridCell(2, 0, 1),
        ... ]
        >>> extract_vias(cells)
        [2]  # Via at index 2 (transition from layer 0 to 1)
    """
    via_indices = []
    for i in range(1, len(cells)):
        if cells[i].layer != cells[i - 1].layer:
            via_indices.append(i)
    return via_indices


def _oracle_compute_path_length(cells: list[GridCell], cell_size: float) -> float:
    """Calculate total path length in mm (Manhattan distance).

    Args:
        cells: Ordered list of grid cells forming a path
        cell_size: Grid cell size in mm

    Returns:
        Total path length in mm

    Example:
        >>> cells = [GridCell(0, 0, 0), GridCell(1, 0, 0), GridCell(2, 0, 0)]
        >>> compute_path_length(cells, cell_size=0.5)
        1.0  # 2 steps * 0.5mm
    """
    if len(cells) < 2:
        return 0.0

    total_length = 0.0
    for i in range(1, len(cells)):
        # Manhattan distance between consecutive cells
        dx = abs(cells[i].x - cells[i - 1].x)
        dy = abs(cells[i].y - cells[i - 1].y)
        # Layer change doesn't add physical length (via is at same x,y)
        total_length += (dx + dy) * cell_size

    return total_length


def _oracle_count_vias_in_path(cells: list[GridCell]) -> int:
    """Count the number of layer transitions (vias) in a path.

    Args:
        cells: Ordered list of grid cells forming a path

    Returns:
        Number of vias needed

    Example:
        >>> cells = [
        ...     GridCell(0, 0, 0),  # L0
        ...     GridCell(1, 0, 1),  # L1 - via 1
        ...     GridCell(2, 0, 1),
        ...     GridCell(3, 0, 0),  # L0 - via 2
        ... ]
        >>> count_vias_in_path(cells)
        2
    """
    return len(extract_vias(cells))


# -- path_simplify.py --------------------------------------------------------
# Reused verbatim oracle: tests/router_v6/_path_simplify_py_oracle.py (the
# pinned 550cab2a extraction).  `PS_ORACLE.is_collinear` / `.simplify_path` /
# `.estimate_segment_count` are the reference for the re-homed kernels.

# Aliases the verbatim composite bodies above rely on (oracle arm only).  The
# shim's versions are imported at the top under `_shim_*` names, so these
# plain names belong to the oracle and the shim-arm assertions reference the
# `_shim_*` aliases explicitly (never the oracle).
_get_adjacent_layer = _oracle_get_adjacent_layer
calculate_safety_distances = _oracle_calculate_safety_distances
_kw_boundary_match = _oracle_kw_boundary_match
_net_class_to_voltage_class = _oracle_net_class_to_voltage_class
extract_vias = _oracle_extract_vias

# ===========================================================================
# G1 evidence: the oracles are verbatim pins
# ===========================================================================

_ORACLE_PIN_SHA = "f1ffc013"

_ORACLE_SOURCES = (
    (
        "packages/temper-placer/src/temper_placer/router_v6/via_placement.py",
        (
            ("_oracle_get_adjacent_layer", "_get_adjacent_layer"),
            ("_oracle_place_vias_for_path", "_place_vias_for_path"),
        ),
    ),
    (
        "packages/temper-placer/src/temper_placer/router_v6/clearance_engine.py",
        (
            ("_oracle_calculate_safety_distances", "calculate_safety_distances"),
            ("_oracle_kw_boundary_match", "_kw_boundary_match"),
            ("_oracle_net_class_to_voltage_class", "_net_class_to_voltage_class"),
        ),
    ),
    (
        "packages/temper-placer/src/temper_placer/router_v6/grid_converter.py",
        (
            ("_oracle_grid_to_world", "grid_to_world"),
            ("_oracle_extract_vias", "extract_vias"),
            ("_oracle_compute_path_length", "compute_path_length"),
            ("_oracle_count_vias_in_path", "count_vias_in_path"),
        ),
    ),
)


def _segments_from_source(src: str, names: tuple[str, ...]) -> dict[str, str]:
    tree = ast.parse(src)
    lines = src.splitlines()
    out: dict[str, str] = {}
    for node in tree.body:
        nm = getattr(node, "name", None)
        if nm in names:
            decos = getattr(node, "decorator_list", [])
            start = (min(d.lineno for d in decos) if decos else node.lineno) - 1
            out[nm] = "\n".join(lines[start : node.end_lineno])
    return out


def test_oracle_is_verbatim_copy():
    """Every oracle definition is character-identical to the pin (modulo the
    ``_oracle_`` name prefix, which is exactly one edit)."""
    src_text = Path(__file__).read_text(encoding="utf-8")
    this = ast.parse(src_text)
    src_lines = src_text.splitlines()
    have: dict[str, str] = {}
    for node in this.body:
        nm = getattr(node, "name", None)
        if nm and nm.startswith("_oracle_"):
            decos = getattr(node, "decorator_list", [])
            start = (min(d.lineno for d in decos) if decos else node.lineno) - 1
            have[nm] = "\n".join(src_lines[start : node.end_lineno])

    for rel, names in _ORACLE_SOURCES:
        try:
            committed = subprocess.run(
                ["git", "show", f"{_ORACLE_PIN_SHA}:{rel}"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout
        except (subprocess.CalledProcessError, FileNotFoundError):  # pragma: no cover
            pytest.skip(f"pinned commit {_ORACLE_PIN_SHA} not present in this clone")
        original = _segments_from_source(committed, tuple(n for _, n in names))
        for ora_name, orig_name in names:
            assert ora_name in have, f"{ora_name} missing from the differential file"
            assert orig_name in original, f"{orig_name} missing from {rel} at the pin"
            normalised = have[ora_name].replace(f"def {ora_name}", f"def {orig_name}", 1)
            assert normalised == original[orig_name], (
                f"{rel}::{orig_name} in the oracle is NOT verbatim -- "
                f"the pin is broken and the differential proves nothing"
            )


def test_path_simplify_oracle_present():
    """The re-homed kernels share the existing pinned path-simplify oracle."""
    for name in ("is_collinear", "simplify_path", "estimate_segment_count"):
        assert hasattr(PS_ORACLE, name), f"{name} missing from the pinned oracle"


def test_rust_symbols_exist():
    """The migration checklist. RED until every kernel is ported."""
    missing = missing_symbols(_RUST_MODULE, REQUIRED_RUST_SYMBOLS)
    assert not missing, (
        f"temper_geometry is missing {len(missing)} of {len(REQUIRED_RUST_SYMBOLS)} "
        f"tier-2 kernels: {missing}"
    )


# ===========================================================================
# via_placement.py — adjacent layer + segment-layer derivation
# ===========================================================================


def _make_path3d(segments, via_positions):
    from types import SimpleNamespace

    return SimpleNamespace(segments=segments, via_positions=via_positions)


def _via_tuples(vias) -> list[tuple[object, ...]]:
    return [
        (v.position, v.from_layer, v.to_layer, v.diameter, v.drill, v.net_name)
        for v in vias
    ]


def test_adjacent_layer_oracle_parity():
    fn = _rust("adjacent_layer_py")
    for layer in ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu", "In3.Cu", "", "F.CuX", "top"]:
        assert sig(_oracle_get_adjacent_layer(layer)) == sig(fn(layer)), layer
        assert sig(_shim_adjacent_layer(layer)) == sig(_oracle_get_adjacent_layer(layer)), layer


def test_via_layer_pair_matches_oracle_path3d():
    fn = _rust("via_layer_pair_py")
    cases = [
        (
            [(0.0, 0.0, "F.Cu"), (5.0, 0.0, "F.Cu"), (5.0, 0.0, "B.Cu"), (10.0, 0.0, "B.Cu")],
            [(5.0, 0.0)],
        ),
        (
            [
                (0.0, 0.0, "F.Cu"),
                (5.0, 0.0, "F.Cu"),
                (5.0, 0.0, "B.Cu"),
                (10.0, 0.0, "B.Cu"),
                (10.0, 0.0, "F.Cu"),
                (15.0, 0.0, "F.Cu"),
            ],
            [(5.0, 0.0), (10.0, 0.0)],
        ),
        ([(0.0, 0.0, "F.Cu")], [(0.0, 0.0)]),  # single segment, no successor -> fallback
        ([], [(1.0, 1.0)]),  # no segments at all -> fallback
        ([(0.0, 0.0, "F.Cu"), (1.0, 0.0, "B.Cu")], [(99.0, 99.0)]),  # no match -> fallback
        ([(0.0, 0.0, "F.Cu"), (0.0, 0.0, "In1.Cu")], [(0.0, 0.0)]),  # coincident segs, first wins
        ([(5.0, 0.0, "F.Cu"), (5.0, 0.0, "B.Cu")], [(5.00005, 0.0)]),  # within 1e-4
        ([(5.0, 0.0, "F.Cu"), (5.0, 0.0, "B.Cu")], [(5.00015, 0.0)]),  # outside 1e-4 -> fallback
    ]
    for segs, vias in cases:
        oracle = _via_tuples(_oracle_place_vias_for_path("N", _make_path3d(segs, vias), 0.6, 0.3))
        shim = _via_tuples(_place_vias_for_path("N", _make_path3d(segs, vias), 0.6, 0.3))
        assert sig(oracle) == sig(shim), f"shim diverged: {oracle} vs {shim}"
        seg_xs = [s[0] for s in segs]
        seg_ys = [s[1] for s in segs]
        seg_layers = [s[2] for s in segs]
        for (vx, vy), via in zip(vias, shim):
            assert sig(fn(vx, vy, seg_xs, seg_ys, seg_layers)) == sig(
                (via[1], via[2])
            ), (vx, vy)


def test_via_layer_pair_epsilon_and_nan():
    """The segment scan's epsilon semantics, pinned through the wired
    via_layer_pair kernel (the pure scan is internal to it)."""
    fn = _rust("via_layer_pair_py")
    segs = [
        (0.0, 0.0, "F.Cu"),
        (5.0, 0.0, "F.Cu"),
        (5.0, 0.0, "B.Cu"),
        (10.0, 0.0, "B.Cu"),
    ]
    seg_xs = [s[0] for s in segs]
    seg_ys = [s[1] for s in segs]
    seg_layers = [s[2] for s in segs]
    # Exact hit on an interior segment endpoint -> derived pair.
    assert fn(5.0, 0.0, seg_xs, seg_ys, seg_layers) == ("F.Cu", "B.Cu")
    # Just inside epsilon on both axes -> still a match.
    assert fn(5.000099, 0.000099, seg_xs, seg_ys, seg_layers) == ("F.Cu", "B.Cu")
    # NaN via position never matches (`abs(nan) < 1e-4` is False) -> fallback.
    assert fn(float("nan"), 0.0, seg_xs, seg_ys, seg_layers) == ("F.Cu", "B.Cu")


def test_via_layer_pair_outside_epsilon_falls_back():
    fn = _rust("via_layer_pair_py")
    segs = [(0.0, 0.0, "F.Cu"), (5.0, 0.0, "B.Cu")]
    seg_xs = [s[0] for s in segs]
    seg_ys = [s[1] for s in segs]
    seg_layers = [s[2] for s in segs]
    # Clearly outside epsilon -> no match -> hardcoded fallback.
    assert fn(5.00015, 0.0, seg_xs, seg_ys, seg_layers) == ("F.Cu", "B.Cu")


def test_via_placement_legacy_fallback_unchanged():
    from types import SimpleNamespace

    path = SimpleNamespace(
        coordinates=[(0, 0), (5, 0), (10, 0)], layer_name="F.Cu", path_length=10.0
    )
    oracle = _via_tuples(_oracle_place_vias_for_path("N", path, 0.6, 0.3))
    shim = _via_tuples(_place_vias_for_path("N", path, 0.6, 0.3))
    assert sig(oracle) == sig(shim)
    assert shim and shim[0][1] == "F.Cu" and shim[0][2] == "In1.Cu"


# ===========================================================================
# clearance_engine.py — safety-distances tables + voltage-class branching
# ===========================================================================


@pytest.mark.parametrize(
    "voltage,pollution,ovcat",
    [
        (0.0, 2, 2),
        (50.0, 2, 2),
        (50.0001, 2, 2),
        (150.0, 1, 1),
        (300.0, 2, 3),
        (600.0, 3, 2),
        (1000.0, 1, 4),
        (1000.0001, 3, 4),
        (1200.0, 2, 2),
        (340.0, 3, 2),
        (float("nan"), 2, 2),
        (float("inf"), 2, 2),
        (-5.0, 2, 2),
        (49.9, 3, 3),
    ],
)
def test_safety_distances_oracle_parity(voltage, pollution, ovcat):
    fn = _rust("safety_distances_py")
    o = _oracle_calculate_safety_distances(voltage, pollution, overvoltage_category=ovcat)
    got = fn(voltage, pollution, ovcat)
    assert sig(o.clearance_mm) == sig(got[0])
    assert sig(o.creepage_mm) == sig(got[1])
    assert sig(o.voltage_v) == sig(got[2])
    # And the shim path (dataclass) matches too.
    s = _shim_safety_distances(voltage, pollution, overvoltage_category=ovcat)
    assert sig(s.clearance_mm) == sig(o.clearance_mm)
    assert sig(s.creepage_mm) == sig(o.creepage_mm)
    assert sig(s.voltage_v) == sig(o.voltage_v)


def test_kw_boundary_match_oracle_parity():
    fn = _rust("kw_boundary_match_py")
    words = ["HV", "AC", "MAINS", "MAINS_240V", "MAINS_120V", "LOW_VOLTAGE", "LV", "POWER"]
    labels = [
        "HV", "AC_L", "AC1", "_AC", "AC_", "HV_BUS", "HV1", "X_HV_2", "MAINS_240V",
        "MAINS_120V", "MAINS", "mains_l", "LOW_VOLTAGE", "LV_BUS", "POWER", "GND",
        "Signal", "SELV", "COIL1", "coil2", "TRACE", "ACH", "HIVE", "BEHAVE", "PE",
        "120", "240V", "V240", "B+", "BUS_340V", "SW_NODE", "GATE", "+15V", "",
        "MAINS_240V_EXTRA", "H_120_V", "pre_120V_post", "120V", "x120", "120X",
        "A240", "240", "HV_LV", "LOW_VOLTAGE_HV",
    ]
    for upper in labels:
        for kw in words:
            assert sig(fn(upper, [kw])) == sig(
                _oracle_kw_boundary_match(upper, (kw,))
            ), (upper, kw)
    # Multi-keyword call: any() semantics.
    for upper in labels:
        assert sig(fn(upper, words)) == sig(
            _oracle_kw_boundary_match(upper, tuple(words))
        ), upper


def test_net_class_to_voltage_class_oracle_parity():
    fn = _rust("net_class_to_voltage_class_py")
    labels = [
        "HV", "HV_BUS", "HV1", "AC_L", "AC", "AC1", "MAINS", "MAINS_240V", "MAINS_120V",
        "MAINS_240", "MAINS_120", "MAINS_110V", "MAINS_240V_EXTRA", "LOW_VOLTAGE", "LV",
        "LV_BUS", "POWER", "POWER_5V", "GND", "Signal", "SELV", "safety_lv", "COIL1",
        "coil2", "TRACE", "ACH", "HIVE", "BEHAVE", "", "PE", "B+", "BUS_340V", "SW_NODE",
        "GATE", "+15V", "120V", "240V", "x120", "120X", "V240", "240", "mains_120V",
        "HIGH_VOLTAGE", "HIGH_VOLTAGE_3", "high_voltage", "LOW_VOLTAGE_2", "AC_DC",
        "ac-dc", "AC-DC",
    ]
    for label in labels:
        assert sig(fn(label)) == sig(
            _oracle_net_class_to_voltage_class(label).value
        ), label


_NET_CLASS_LABELS = [
    "HV", "AC_L", "MAINS_240V", "MAINS_120V", "MAINS", "LOW_VOLTAGE", "LV", "POWER",
    "GND", "Signal", "SELV", "COIL1", "TRACE", "HV_BUS", "3V3", "5V", "ANALOG",
]


@given(
    st.sampled_from(_NET_CLASS_LABELS),
    st.sampled_from(_NET_CLASS_LABELS),
    st.one_of(st.floats(min_value=0.0, max_value=1200.0), st.just(float("nan"))),
    st.sampled_from(["external", "internal"]),
    st.integers(min_value=1, max_value=4),
    st.integers(min_value=1, max_value=4),
    st.one_of(st.none(), st.floats(min_value=-1.0, max_value=30.0)),
)
@settings(max_examples=200, deadline=2000)
def test_get_clearance_oracle_parity_hypothesis(nca, ncb, voltage, layer_type, pd, ovcat, drc):
    o = _oracle_get_clearance(
        nca,
        ncb,
        voltage,
        layer_type=layer_type,
        pollution_degree=pd,
        overvoltage_category=ovcat,
        design_rule_creepage=drc,
    )
    s = get_clearance(
        nca,
        ncb,
        voltage,
        layer_type=layer_type,
        pollution_degree=pd,
        overvoltage_category=ovcat,
        design_rule_creepage=drc,
    )
    assert sig(o) == sig(s), (nca, ncb, voltage, layer_type, pd, ovcat, drc)


# ===========================================================================
# grid_converter.py
# ===========================================================================


def test_grid_to_world_oracle_parity():
    fn = _rust("grid_to_world_py")
    cases = [
        (ShimGridCell(10, 20, 0), (0.0, 0.0), 0.5),
        (ShimGridCell(0, 0, 0), (0.0, 0.0), 0.5),
        (ShimGridCell(-3, 7, 1), (-10.0, 2.5), 0.25),
        (ShimGridCell(1, 1, 0), (1.0, 1.0), 0.1),
        (ShimGridCell(0, 0, 0), (0.0, 0.0), 0.0),
        (ShimGridCell(5, -5, 0), (3.3, -2.2), 1.0),
    ]
    for cell, origin, size in cases:
        o = _oracle_grid_to_world(cell, origin, size)
        got = fn(cell.x, cell.y, origin[0], origin[1], size)
        assert sig(o) == sig(got), (cell, origin, size)
        assert sig(grid_to_world(cell, origin, size)) == sig(o), (cell, origin, size)


def test_extract_vias_and_count_oracle_parity():
    fn = _rust("extract_vias_py")
    cnt = _rust("count_vias_in_path_py")
    cases = [
        [ShimGridCell(0, 0, 0), ShimGridCell(1, 0, 0), ShimGridCell(1, 0, 1), ShimGridCell(2, 0, 1)],
        [],
        [ShimGridCell(5, 5, 0)],
        [ShimGridCell(0, 0, 0), ShimGridCell(1, 0, 0)],
        [ShimGridCell(0, 0, i) for i in range(6)],
        [ShimGridCell(0, 0, 0), ShimGridCell(1, 0, 1), ShimGridCell(2, 0, 0), ShimGridCell(3, 0, 2)],
    ]
    for cells in cases:
        o = _oracle_extract_vias(cells)
        got = fn([c.layer for c in cells])
        assert sig(o) == sig(list(got)), cells
        assert sig(_shim_extract_vias(cells)) == sig(o), cells
        assert sig(_oracle_count_vias_in_path(cells)) == sig(cnt([c.layer for c in cells])), cells
        assert sig(count_vias_in_path(cells)) == sig(len(o)), cells


def test_compute_path_length_oracle_parity():
    fn = _rust("compute_path_length_py")
    cases = [
        ([ShimGridCell(0, 0, 0), ShimGridCell(1, 0, 0), ShimGridCell(2, 0, 0)], 0.5),
        ([ShimGridCell(0, 0, 0), ShimGridCell(0, 0, 1)], 0.5),  # layer change adds no length
        ([], 1.0),
        ([ShimGridCell(5, 5, 0)], 0.5),
        ([ShimGridCell(0, 0, 0), ShimGridCell(-3, 4, 0)], 0.1),
        (
            [
                ShimGridCell(0, 0, 0),
                ShimGridCell(1, 1, 0),
                ShimGridCell(1, 2, 0),
                ShimGridCell(4, 2, 0),
            ],
            0.25,
        ),
    ]
    for cells, size in cases:
        o = _oracle_compute_path_length(cells, size)
        got = fn([c.x for c in cells], [c.y for c in cells], size)
        assert sig(o) == sig(got), (cells, size)
        assert sig(compute_path_length(cells, size)) == sig(o), (cells, size)


# ===========================================================================
# path_simplify.py (re-homed kernels vs the pinned oracle)
# ===========================================================================


def _cell_wire(c: ShimGridCell) -> tuple[int, int, int]:
    return (c.x, c.y, c.layer)


def test_is_collinear_oracle_parity():
    fn = _rust("is_collinear_py")
    triples = [
        (ShimGridCell(0, 0, 0), ShimGridCell(1, 0, 0), ShimGridCell(2, 0, 0)),  # horizontal
        (ShimGridCell(0, 0, 0), ShimGridCell(0, 1, 0), ShimGridCell(0, 2, 0)),  # vertical
        (ShimGridCell(0, 0, 0), ShimGridCell(1, 0, 0), ShimGridCell(1, 1, 0)),  # corner
        (ShimGridCell(0, 0, 1), ShimGridCell(1, 0, 0), ShimGridCell(2, 0, 0)),  # layer mismatch
        (ShimGridCell(0, 0, 0), ShimGridCell(1, 0, 0), ShimGridCell(2, 0, 1)),
        (ShimGridCell(3, 3, 0), ShimGridCell(3, 3, 0), ShimGridCell(3, 3, 0)),  # coincident
        (ShimGridCell(0, 0, 0), ShimGridCell(0, 0, 0), ShimGridCell(1, 0, 0)),  # dup then along
        (ShimGridCell(0, 0, 0), ShimGridCell(1, 1, 0), ShimGridCell(2, 2, 0)),  # diagonal
    ]
    for p1, p2, p3 in triples:
        o = PS_ORACLE.is_collinear(p1, p2, p3)
        got = fn(_cell_wire(p1), _cell_wire(p2), _cell_wire(p3))
        assert sig(o) == sig(got), (p1, p2, p3)


def test_simplify_path_oracle_parity():
    fn = _rust("simplify_path_py")
    cases = [
        [ShimGridCell(0, 0, 0), ShimGridCell(1, 0, 0), ShimGridCell(2, 0, 0)],
        [ShimGridCell(0, 0, 0), ShimGridCell(1, 0, 0), ShimGridCell(1, 1, 0)],
        [ShimGridCell(0, 0, 0), ShimGridCell(1, 0, 0), ShimGridCell(1, 0, 1)],
        [],
        [ShimGridCell(5, 5, 0)],
        [ShimGridCell(0, 0, 0), ShimGridCell(9, 9, 3)],
        [
            ShimGridCell(0, 0, 0),
            ShimGridCell(1, 0, 0),
            ShimGridCell(1, 1, 0),
            ShimGridCell(2, 1, 0),
            ShimGridCell(2, 2, 0),
        ],
        [ShimGridCell(0, 0, 0), ShimGridCell(0, 0, 0), ShimGridCell(0, 0, 0)],
        [
            ShimGridCell(0, 0, 0),
            ShimGridCell(1, 0, 1),
            ShimGridCell(1, 0, 0),
            ShimGridCell(2, 0, 0),
        ],
        [ShimGridCell(i, 0, 0) for i in range(10)] + [ShimGridCell(9, 1, 0), ShimGridCell(9, 2, 0)],
        [ShimGridCell(-5, -5, 0), ShimGridCell(-3, -5, 0), ShimGridCell(-1, -5, 0)],
        [ShimGridCell(0, 0, 0), ShimGridCell(0, 0, 1), ShimGridCell(0, 0, 2), ShimGridCell(0, 0, 3)],
    ]
    for cells in cases:
        o = PS_ORACLE.simplify_path(cells)
        wire = [_cell_wire(c) for c in cells]
        got = [ShimGridCell(*t) for t in fn(wire)]
        assert sig(o) == sig(got), cells


def test_estimate_segment_count_oracle_parity():
    fn = _rust("estimate_segment_count_py")
    cases = [
        [ShimGridCell(0, 0, 0), ShimGridCell(1, 0, 0), ShimGridCell(2, 0, 0)],
        [],
        [ShimGridCell(5, 5, 0)],
        [ShimGridCell(0, 0, 0), ShimGridCell(1, 0, 0), ShimGridCell(1, 0, 1), ShimGridCell(2, 0, 1)],
        [ShimGridCell(0, 0, 0), ShimGridCell(0, 0, 1), ShimGridCell(0, 0, 2)],
    ]
    for cells in cases:
        o = PS_ORACLE.estimate_segment_count(cells)
        got = fn([_cell_wire(c) for c in cells])
        assert sig(o) == sig(got), cells


# ===========================================================================
# Randomized end-to-end A/B (seeded, deterministic)
# ===========================================================================

_LAYERS = ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"]


def _random_path3d(rng: random.Random):
    n = rng.randint(1, 8)
    segs = []
    for i in range(n):
        x = round(rng.uniform(-50, 50), 3)
        y = round(rng.uniform(-50, 50), 3)
        layer = _LAYERS[rng.randrange(len(_LAYERS))]
        if i == 0 or rng.random() < 0.7:
            segs.append((x, y, layer))
        else:
            segs.append((segs[i - 1][0], segs[i - 1][1], layer))
    via_positions = []
    for _ in range(rng.randint(0, 3)):
        if segs and rng.random() < 0.8:
            sx, sy, _ = segs[rng.randrange(len(segs))]
            via_positions.append((sx, sy))
        else:
            via_positions.append(
                (round(rng.uniform(-50, 50), 3), round(rng.uniform(-50, 50), 3))
            )
    return segs, via_positions


def test_randomized_via_layer_pair_parity():
    fn = _rust("via_layer_pair_py")
    rng = random.Random(0x51AC1E4A)
    for _ in range(300):
        segs, vias = _random_path3d(rng)
        oracle = _via_tuples(_oracle_place_vias_for_path("N", _make_path3d(segs, vias), 0.6, 0.3))
        shim = _via_tuples(_place_vias_for_path("N", _make_path3d(segs, vias), 0.6, 0.3))
        assert sig(oracle) == sig(shim)
        seg_xs = [s[0] for s in segs]
        seg_ys = [s[1] for s in segs]
        seg_layers = [s[2] for s in segs]
        for (vx, vy), via in zip(vias, shim):
            assert sig(fn(vx, vy, seg_xs, seg_ys, seg_layers)) == sig((via[1], via[2]))


def test_randomized_clearance_engine_parity():
    fn_sd = _rust("safety_distances_py")
    fn_vc = _rust("net_class_to_voltage_class_py")
    rng = random.Random(0xC1E4A2CE)
    for _ in range(300):
        voltage = rng.uniform(0.0, 1200.0)
        pd = rng.randint(1, 4)
        ovcat = rng.randint(1, 4)
        o = _oracle_calculate_safety_distances(voltage, pd, overvoltage_category=ovcat)
        got = fn_sd(voltage, pd, ovcat)
        assert sig(o.clearance_mm) == sig(got[0])
        assert sig(o.creepage_mm) == sig(got[1])
        label = rng.choice(_NET_CLASS_LABELS)
        assert sig(fn_vc(label)) == sig(
            _oracle_net_class_to_voltage_class(label).value
        ), label
        layer_type = rng.choice(["external", "internal"])
        drc = rng.choice([None, 0.0, -1.0, rng.uniform(0.0, 30.0)])
        ncb = rng.choice(_NET_CLASS_LABELS)
        assert sig(
            get_clearance(
                label,
                ncb,
                voltage,
                layer_type=layer_type,
                pollution_degree=pd,
                overvoltage_category=ovcat,
                design_rule_creepage=drc,
            )
        ) == sig(
            _oracle_get_clearance(
                label,
                ncb,
                voltage,
                layer_type=layer_type,
                pollution_degree=pd,
                overvoltage_category=ovcat,
                design_rule_creepage=drc,
            )
        )


def test_randomized_grid_and_path_parity():
    fn_gtw = _rust("grid_to_world_py")
    fn_ev = _rust("extract_vias_py")
    fn_pl = _rust("compute_path_length_py")
    fn_cnt = _rust("count_vias_in_path_py")
    fn_simp = _rust("simplify_path_py")
    fn_est = _rust("estimate_segment_count_py")
    rng = random.Random(0x6E1D)
    for _ in range(300):
        n = rng.randint(0, 12)
        cells = [
            ShimGridCell(rng.randint(-20, 20), rng.randint(-20, 20), rng.randint(0, 3))
            for _ in range(n)
        ]
        size = rng.choice([0.1, 0.25, 0.5, 1.0, 0.125, 0.2])
        origin = (round(rng.uniform(-10, 10), 2), round(rng.uniform(-10, 10), 2))
        for cell in cells:
            assert sig(_oracle_grid_to_world(cell, origin, size)) == sig(
                fn_gtw(cell.x, cell.y, origin[0], origin[1], size)
            )
        assert sig(_oracle_extract_vias(cells)) == sig(
            list(fn_ev([c.layer for c in cells]))
        )
        assert sig(_oracle_compute_path_length(cells, size)) == sig(
            fn_pl([c.x for c in cells], [c.y for c in cells], size)
        )
        assert sig(_oracle_count_vias_in_path(cells)) == sig(
            fn_cnt([c.layer for c in cells])
        )
        wire = [_cell_wire(c) for c in cells]
        assert sig(PS_ORACLE.simplify_path(cells)) == sig(
            [ShimGridCell(*t) for t in fn_simp(wire)]
        )
        assert sig(PS_ORACLE.estimate_segment_count(cells)) == sig(fn_est(wire))
