"""Round-trip oracle: written board vs the solver's placement model.

Every placement write is re-parsed from disk and its pad geometry is
compared EXACTLY (modulo canonicalization and float epsilon) against the
geometry the solver's placement record implies under the sanctioned
``kicad_transform`` convention.  This is the instrument that makes the
rotation-convention class -- a sign error across call sites, an un-applied
solved rotation, pad bodies left un-rotated -- a direct, immediate
assertion instead of a latent DRC regression that only surfaces when some
future PR happens to choose a non-90-degree-multiple rotation.

Design (see docs/plans/2026-08-02-009-feat-transform-round-trip-oracle-plan.md
and the origin evidence docs it cites):

* KTD1 -- The reference model is the solver's placement record transformed
  by ``kicad_transform``'s sanctioned convention.  Expected footprint
  anchors and pad world positions are computed from ``(positions,
  rotations, parsed template pad offsets)`` via
  :func:`~temper_placer.geometry.kicad_transform.place_local_to_world`.
  The convention's own correctness is pinned separately by the
  pcbnew-oracle tests; this oracle only checks writers against it.
* KTD2 -- Comparison is exact modulo canonicalization, not
  tolerance-banded.  Angles are normalized mod 360 (which also maps the
  omitted-angle-token form to 0), and float comparisons use a single
  epsilon.  A dropped rotation or sign flip is an exact, structural
  difference; a tolerance band would let the class this oracle exists for
  hide inside the band.
* KTD3 -- Every production write path gets oracle coverage (the per-writer
  tests in ``tests/io/test_kicad_writer.py`` and
  ``tests/router_v6/test_adapter.py``); one covered path does not vouch
  for another (the two writers have different geometry contracts --
  center-offset subtraction -- and different incident histories).
* KTD4 -- The oracle consumes the written FILE, not an in-memory
  representation: the board is re-parsed from disk with
  :func:`~temper_placer.io.kicad_parser.parse_kicad_pcb_v6` (raw per-pad
  geometry is then read from the kiutils tree -- the parser's
  ``initial_position`` mirrors center offsets for back-side footprints,
  so raw file geometry is the side-agnostic source of truth for written
  anchors and pad offsets).

Pad local ``(x, y)`` offsets are NOT rewritten by the writers (KiCad
rotates them at load time); the oracle therefore compares pad world
positions and pad body angles, not pad local offsets -- but the world
comparison is computed from the raw local offsets on each side, so a
hypothetical future writer that *did* rewrite local offsets would still be
caught.

Float format note: ``_apply_placements_to_pcb`` (the adapter writer)
quantizes coordinates and angles to 4 decimal places, so the default
``epsilon`` (1e-3) is comfortably above the worst-case 5e-5 rounding
error while being orders of magnitude below every failure mode this
oracle exists to catch (a dropped rotation shifts a pad body by 90
degrees; a sign flip shifts an asymmetric footprint's anchor by
``2 * center_offset``).

Wave 4 Phase 4: the decision compute — ``canonical_angle`` (mod-360),
``_angle_diff`` (shortest signed-magnitude angle difference), ``_pad_key``
(stable per-footprint pad key), and ``_check_footprint``'s comparison
logic (anchor / footprint-angle / pad-presence / pad-position / pad-angle
checks and mismatch-record construction) — is implemented in Rust as the
``validation`` submodule of ``temper_design_bundle_python``
(``temper-design-bundle/src/validation.rs``) and delegated to here. This
module keeps the file I/O (KTD4: ``parse_kicad_pcb_v6`` +
``KiBoard.from_file`` re-parse), the kiutils-tree extraction (written
anchors/angles/pad local offsets), the template ``Component`` attribute
reads, the kicad_transform primitives (``place_local_to_world`` /
``rotate_local_to_world`` stay single-source in
``geometry/kicad_transform.py`` — both arms call the same Python, so the
shared geometry is identical by construction), and the
``_get_footprint_reference`` consumer relationship (the #723 note's
kiutils-free attribute reader stays imported verbatim from
``io/_parse_modules``).

Verification: bit-identical parity against the pinned pre-migration
implementation is asserted by
``tests/validation/test_placement_roundtrip_rust_differential.py``
(oracle: ``tests/validation/_placement_roundtrip_py_oracle.py``); the
structural proof lives in ``packages/temper-design-bundle/VERIFICATION.md``.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import temper_design_bundle_python as _tdb
from kiutils.board import Board as KiBoard

from temper_placer.core.netlist import Component
from temper_placer.geometry.kicad_transform import place_local_to_world, rotate_local_to_world
from temper_placer.io._parse_modules import _get_footprint_reference
from temper_placer.io.kicad_parser import parse_kicad_pcb_v6

if TYPE_CHECKING:
    from kiutils.footprint import Footprint

__all__ = [
    "RoundTripMismatch",
    "RoundTripResult",
    "canonical_angle",
    "check_placement_roundtrip",
]


def canonical_angle(angle: float) -> float:
    """Normalize an angle into ``[0, 360)`` degrees.

    Canonicalization rule (KTD2): KiCad/kiutils omit the ``(at ... angle)``
    angle token when it is zero, so a written angle of 360, 0, or an absent
    token must all compare equal.  Mod-360 normalization gives that.

    Implemented in Rust (``temper_design_bundle_python.validation.
    canonical_angle``) with CPython float-``%`` semantics — the oracle's
    ``-720.0 % 360.0`` is ``+0.0``, not ``-0.0`` (CPython's float_rem
    ``copysign`` branch).
    """
    return _tdb.validation.canonical_angle(angle)


def _angle_diff(a: float, b: float) -> float:
    """Shortest signed-magnitude difference between two angles, in degrees
    (the Rust ``angle_diff`` kernel)."""
    return _tdb.validation.angle_diff(a, b)


def _template_fp_angle(comp: Component) -> float:
    """The template footprint's exact board rotation in degrees."""
    return float(comp.attributes.get("_rotation_deg", "0"))


def _center_offset(comp: Component) -> tuple[float, float]:
    return (
        float(comp.attributes.get("_center_offset_x", "0")),
        float(comp.attributes.get("_center_offset_y", "0")),
    )


def _pad_key(pad: object, index: int) -> str:
    """A stable per-footprint key for a pad: its number when it has one,
    else its positional index (a pad with an empty number is legal in
    KiCad, e.g. an unconnected pad numbered ``""``).  The Rust
    ``pad_key`` kernel."""
    return _tdb.validation.pad_key(getattr(pad, "number", None) or None, index)


@dataclass(frozen=True)
class RoundTripMismatch:
    """One geometric disagreement between the written board and the model.

    ``kind`` is one of: ``parse_error`` (the written file cannot be
    re-parsed), ``footprint_missing`` (a model ref absent from the written
    board), ``pad_missing`` (a template pad absent from the written
    footprint), ``footprint_anchor``, ``footprint_angle``,
    ``pad_position``, ``pad_angle``.
    """

    ref: str
    kind: str
    pad: str | None = None
    expected: object = None
    actual: object = None
    detail: str = ""

    def __str__(self) -> str:
        where = f"{self.ref}" + (f" pad {self.pad}" if self.pad else "")
        core = f"{where}: {self.kind}"
        if self.expected is not None or self.actual is not None:
            core += f" expected={self.expected} actual={self.actual}"
        if self.detail:
            core += f" ({self.detail})"
        return core


@dataclass
class RoundTripResult:
    """Outcome of one round-trip check.

    ``passed`` is False iff at least one mismatch was found.  ``summary``
    renders the result for console/CLI use.
    """

    mismatches: list[RoundTripMismatch] = field(default_factory=list)
    checked_components: int = 0
    checked_pads: int = 0
    skipped_refs: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.mismatches

    @property
    def summary(self) -> str:
        if self.passed:
            return (
                f"round-trip PASS: {self.checked_components} components, "
                f"{self.checked_pads} pads verified"
            )
        head = "; ".join(str(m) for m in self.mismatches[:5])
        more = f" (+{len(self.mismatches) - 5} more)" if len(self.mismatches) > 5 else ""
        return (
            f"round-trip FAIL: {len(self.mismatches)} mismatch(es) across "
            f"{self.checked_components} components / {self.checked_pads} pads: {head}{more}"
        )


def _check_footprint(
    result: RoundTripResult,
    ref: str,
    pos: tuple[float, float],
    rotations: dict[str, float],
    template: Component,
    fp: Footprint,
    epsilon: float,
) -> None:
    """Compare one written footprint (and every one of its pads) against
    the model geometry implied by ``(pos, rotations, template)``.

    All geometry is reduced to world coordinates by
    ``kicad_transform``'s R(-theta) convention -- the single sanctioned
    formula (KTD1); this module never re-derives it. The world reduction
    (kicad_transform primitives, template attribute reads, kiutils-tree
    extraction) stays here; the comparison logic -- the anchor/angle/pad
    checks and mismatch-record construction -- is the Rust
    ``check_footprint_geometry`` kernel.
    """
    # A ref absent from `rotations` means "no rotation change": the solved
    # rotation record (CpSatPlacementResult.to_rotations_dict) omits
    # zero-index refs, and the adapter writer keeps those footprints'
    # existing angles byte-for-byte -- so the expected angle is the
    # template's own board rotation, not 0.
    theta = rotations.get(ref, _template_fp_angle(template))
    theta_rad = math.radians(theta)

    co_x, co_y = _center_offset(template)

    # --- footprint anchor (world) ------------------------------------------
    # The solver's position is the box CENTRE (the parser's
    # initial_position convention).  KiCad's ``(at X Y)`` is the raw
    # footprint anchor; the writers subtract the rotated center offset to
    # convert between the two frames.  Expected anchor = centre minus the
    # R(-theta)-rotated offset, exactly the writers' own correction.
    rot_cx, rot_cy = rotate_local_to_world(co_x, co_y, theta_rad)
    wx = float(fp.position.X) if fp.position and fp.position.X is not None else 0.0
    wy = float(fp.position.Y) if fp.position and fp.position.Y is not None else 0.0
    wa = (fp.position.angle or 0.0) if fp.position else 0.0
    wa_rad = math.radians(wa)

    # --- pads (world) -------------------------------------------------------
    # Dedup by key, LAST pin wins — mirroring the oracle's
    # `{_pad_key(p, i): p for i, p in enumerate(template.pins)}` dict
    # comprehension exactly: two pins sharing a pad number collapse to the
    # last one and are checked once (a dict reassignment keeps the first
    # insertion position but replaces the value).
    template_pads_by_key: dict[str, tuple[float, float, float]] = {}
    for i, tpin in enumerate(template.pins):
        key = _pad_key(tpin, i)
        exp_px, exp_py = place_local_to_world(
            tpin.position[0], tpin.position[1], pos[0], pos[1], theta_rad
        )
        template_pads_by_key[key] = (exp_px, exp_py, tpin.pad_rotation_deg)
    template_pads = [
        (key, exp_px, exp_py, intrinsic)
        for key, (exp_px, exp_py, intrinsic) in template_pads_by_key.items()
    ]

    written_pads: list[tuple[str, float | None, float | None, float | None]] = []
    for i, wpad in enumerate(fp.pads or []):
        key = _pad_key(wpad, i)
        if wpad.position is None:
            written_pads.append((key, None, None, None))
        else:
            act_px, act_py = place_local_to_world(
                float(wpad.position.X), float(wpad.position.Y), wx, wy, wa_rad
            )
            written_pads.append((key, act_px, act_py, wpad.position.angle or 0.0))

    mismatches, checked_pads = _tdb.validation.check_footprint_geometry(
        ref,
        pos,
        (rot_cx, rot_cy),
        (wx, wy),
        theta,
        wa,
        epsilon,
        template_pads,
        written_pads,
    )
    for m in mismatches:
        result.mismatches.append(
            RoundTripMismatch(
                ref=ref,
                kind=m["kind"],
                pad=m["pad"],
                expected=m["expected"],
                actual=m["actual"],
                detail=m["detail"],
            )
        )
    result.checked_pads += checked_pads
    result.checked_components += 1


def check_placement_roundtrip(
    written_board_path: Path | str,
    positions: dict[str, tuple[float, float]],
    rotations: dict[str, float] | None = None,
    template_components: Sequence[Component] | None = None,
    *,
    epsilon: float = 1e-3,
) -> RoundTripResult:
    """Round-trip a written board through the oracle.

    Args:
        written_board_path: The ``.kicad_pcb`` file the writer just
            produced (KTD4 -- re-parsed from disk, not compared in
            memory).
        positions: Model box-centre positions ``{ref: (x, y)}`` in the
            same coordinate frame the writer wrote (file coordinates).
        rotations: Model rotations ``{ref: degrees}``.  A ref absent from
            this dict is treated as "no rotation change" (the adapter
            writer keeps such footprints' angles byte-for-byte); callers
            of ``write_placements_to_pcb`` that emit an explicit angle for
            every ref (e.g. the CLI's ``optimize``) pass a complete dict.
        template_components: The ``Component`` list parsed from the
            template board before writing (netlist components).  Required:
            the oracle computes expected pad geometry from the template's
            pad offsets and intrinsic angles, not from the written file.
        epsilon: Float tolerance (mm and degrees) for the exact comparison
            (KTD2).  Default 1e-3 covers the adapter writer's 4-decimal
            quantization; every failure class this oracle exists for is
            orders of magnitude larger.

    Returns:
        A :class:`RoundTripResult`; ``passed`` is True only when every
        model ref present in the written board matches its expected
        geometry exactly (modulo canonicalization and ``epsilon``).
    """
    written_path = Path(written_board_path)
    if not written_path.exists():
        raise ValueError(f"Written board does not exist: {written_path}")
    if template_components is None:
        raise ValueError(
            "template_components is required: the oracle computes expected pad "
            "geometry from the template's pad offsets and intrinsic angles"
        )

    rotations = dict(rotations) if rotations else {}

    result = RoundTripResult()

    # KTD4: re-parse the written board with the production parser.  A file
    # the production parser cannot read is itself a round-trip failure.
    # (The result is not otherwise used -- the raw per-footprint/per-pad
    # geometry below comes from the kiutils tree, because the parser's
    # ``initial_position`` mirrors center offsets for back-side (B.Cu)
    # footprints; the parse still must succeed for the round-trip to pass.)
    try:
        _parsed = parse_kicad_pcb_v6(written_path)
    except Exception as exc:  # pragma: no cover - defensive; any exception
        result.mismatches.append(
            RoundTripMismatch(
                ref="<board>", kind="parse_error",
                detail=f"written board failed parse_kicad_pcb_v6: {exc}",
            )
        )
        return result

    try:
        board = KiBoard.from_file(str(written_path))
    except Exception as exc:  # pragma: no cover - defensive
        result.mismatches.append(
            RoundTripMismatch(
                ref="<board>", kind="parse_error",
                detail=f"written board failed KiBoard.from_file: {exc}",
            )
        )
        return result

    written_fps: dict[str, Footprint] = {}
    for fp in board.footprints:
        ref = _get_footprint_reference(fp)
        if not ref or ref.startswith("REF**"):
            continue
        written_fps[ref] = fp

    template_by_ref = {c.ref: c for c in template_components}

    for ref, pos in positions.items():
        template = template_by_ref.get(ref)
        if template is None:
            result.skipped_refs.append(f"{ref} (no template component)")
            continue
        fp = written_fps.get(ref)
        if fp is None:
            result.mismatches.append(
                RoundTripMismatch(
                    ref=ref, kind="footprint_missing",
                    detail="model ref not found in the written board",
                )
            )
            continue
        _check_footprint(result, ref, pos, rotations, template, fp, epsilon)

    return result
