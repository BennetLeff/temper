"""Type stubs for `temper_design_bundle_python.validation`.

Compiled from `packages/temper-design-bundle/src/validation.rs` — the
Wave 4 Phase 4 migration of the validation-remainder decision kernels
(`temper_placer/validation/{preflight,netlist_reconciliation,
placement_roundtrip}.py`, `prereg/schema.py`'s temporal gate). Keep in
sync with that file.

The kernels are plain pyfunctions (no pyclasses). Non-trivial return
shapes:

- `preflight_unassigned` / `preflight_impossible` return
  `(passed, issues)` where each issue is
  `{severity, code, message, suggestion, components, details}`.
- `parse_design_netlist` returns `(components, nets, duplicate_refs)`:
  components as `(ref, instance_path)` pairs, nets as `(name, [(ref,
  pin), ...])` lists, duplicate refs as `(ref, first_path, second_path)`
  triples anchored at the first-seen path.
- `reconcile` returns `(findings, design_components, board_components,
  matched_paths, design_nets_nonempty, board_nets)` where each finding is
  `{kind, severity, detail, refs, paths}`.
- `check_footprint_geometry` returns `(mismatches, checked_pads)` where
  each mismatch is `{kind, pad, expected, actual, detail}`.
- `prereg_temporal_gate` takes the already-parsed aware datetimes plus
  the raw strings interpolated into the (byte-identical) ValueError, and
  raises rather than returning on rejection.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

Bounds = tuple[float, float, float, float]
Issue = dict[str, Any]
Finding = dict[str, Any]
Mismatch = dict[str, Any]

def zones_overlap(a: Bounds, b: Bounds) -> bool: ...

def preflight_zones_fit(
    zones: list[tuple[str, Bounds]], board_w: float, board_h: float
) -> tuple[bool, list[tuple[str, list[str]]], list[tuple[str, str]]]: ...

def preflight_unassigned(
    netlist_refs: list[str],
    assigned_refs: list[str],
    fixed_refs: list[str],
    require_all: bool = False,
) -> tuple[bool, list[Issue]]: ...

def preflight_impossible(
    components: list[tuple[str, float, float]],
    zones: list[tuple[str, Bounds]],
    assignments: list[tuple[str, str]],
    groups: list[tuple[str, str, list[str]]],
    thermals: list[list[str]],
) -> tuple[bool, list[Issue]]: ...

def parse_design_netlist(
    netlist_path: str, text: str
) -> tuple[
    list[tuple[str, str]],
    list[tuple[str, list[tuple[str, str]]]],
    list[tuple[str, str, str]],
]: ...

def reconcile(
    board_components: list[tuple[str, str]],
    board_nets: list[tuple[str, list[str]]],
    design_components: list[tuple[str, str]],
    design_nets: list[tuple[str, list[tuple[str, str]]]],
    duplicate_refs: list[tuple[str, str, str]],
) -> tuple[list[Finding], int, int, int, int, int]: ...

def canonical_angle(angle: float) -> float: ...

def angle_diff(a: float, b: float) -> float: ...

def pad_key(number: str | None, index: int) -> str: ...

def check_footprint_geometry(
    ref: str,
    pos: tuple[float, float],
    rot_center: tuple[float, float],
    written_anchor: tuple[float, float],
    theta: float,
    written_angle: float,
    epsilon: float,
    template_pads: list[tuple[str, float, float, float]],
    written_pads: list[tuple[str, float | None, float | None, float | None]],
) -> tuple[list[Mismatch], int]: ...

def prereg_temporal_gate(
    created_dt: datetime,
    created_raw: str,
    battery_dt: datetime,
    battery_iso: str,
) -> None: ...
