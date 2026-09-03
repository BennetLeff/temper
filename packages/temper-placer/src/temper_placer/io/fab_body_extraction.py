"""Extract ``F.Fab``/``B.Fab`` body geometry from a KiCad PCB file.

Companion to ``io/kicad_metadata.py``'s ``F.CrtYd`` courtyard extraction --
same raw-shape schema, same merge algorithm (reused verbatim, not
reimplemented: ``kicad_metadata._courtyard_points_from_raw``), different
source layer and different footprint reader.

**kiutils-free (Wave 4 Phase 3, formats/IO).** Board reading goes through
the Rust parse engine: ``parse_engine.extract_metadata_raw`` emits the
identical raw-shape schema for ``F.Fab``/``B.Fab`` (``fab_body_inputs``
key) that it has always emitted for ``F.CrtYd``/``B.CrtYd``
(``courtyard_inputs``) -- one shape-serialization switch, two layer
filters. The geometry ARITHMETIC (rotation transform, merge/hull,
polygon boolean) is unchanged from the canonical kernels either way;
only the parsing library differs.

**Validation.** This module's output was originally cross-checked against
PR #1158's independently-implemented (from-scratch S-expression parser, not
this codebase's kernels) body-overlap measurements for the then-current
``courtyards_overlap`` pairs. The committed board has since landed the
documented component relocations; the current test pins C2/C3 as the one
remaining body collision and explicitly checks the seven cleared historical
pairs against the board's current geometry and live ``kicad-cli`` output.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

import temper_design_bundle_python as _tdb
import temper_geometry as _rust_geometry

from temper_placer.core.fab_body import FabBody
from temper_placer.io.kicad_metadata import _courtyard_points_from_raw


@dataclass(frozen=True)
class FabBodyCoverage:
    """Explicit F.Fab extraction coverage for an expected reference set.

    ``present`` contains only references with a validated, usable polygon;
    ``missing`` means the board supplied no parseable F.Fab body for that
    reference; ``invalid`` records malformed geometry/parser failures.  A
    caller must inspect this coverage before treating an audit as complete.
    """

    present: dict[str, FabBody]
    missing: tuple[str, ...]
    invalid: dict[str, str]
    supplement_digests: dict[str, str] = field(default_factory=dict)

    @property
    def complete(self) -> bool:
        return not self.missing and not self.invalid


def _fab_shape_inputs(footprint_shapes: list[dict]) -> list[dict]:
    """Normalize one footprint's Rust-extracted fab shapes (already in the
    ``{"kind": ..., ...}`` schema ``kicad_metadata._courtyard_points_from_raw``
    consumes). Kept as a named seam for the merge-algorithm tests; the
    schema is produced by ``parse_engine.extract_metadata_raw``'s
    shape switch, mirrored byte-for-byte from the courtyard extraction.
    """
    return list(footprint_shapes)


def _flat_points(points: list[tuple[float, float]]) -> list[float]:
    return [coordinate for point in points for coordinate in point]


def extract_fab_bodies(pcb_path: Path) -> dict[str, FabBody]:
    """Return ``{ref: FabBody}`` for every footprint on *pcb_path* that
    carries real ``F.Fab``/``B.Fab`` graphics.

    A footprint with no parseable fab-layer geometry is EXCLUDED from the
    returned dict (not given a fabricated fallback shape) -- the caller
    (``body_collision.audit_body_collisions``) treats an absent ref as "no
    body-collision opinion" for any pair involving it, which is the correct,
    honest handling: inventing a box here could manufacture false positives
    or mask real ones, either of which is worse than a documented skip.

    Raises:
        FileNotFoundError: pcb_path does not exist.
    """
    if not pcb_path.exists():
        raise FileNotFoundError(f"PCB file not found: {pcb_path}")

    fab_inputs = _tdb.parse_engine.extract_metadata_raw(
        pcb_path.read_text(encoding="utf-8")
    )["fab_body_inputs"]

    bodies: dict[str, FabBody] = {}
    for ref, shapes in fab_inputs.items():
        if not ref:
            continue
        points = _courtyard_points_from_raw(_fab_shape_inputs(shapes))
        if not points:
            continue
        _rust_geometry.fab_body_validate_py(ref, _flat_points(points))
        bodies[ref] = FabBody(component_ref=ref, points=points)
    return bodies


def extract_fab_body_coverage(
    pcb_path: Path, expected_refs: Iterable[str]
) -> FabBodyCoverage:
    """Extract bodies and classify every expected reference explicitly.

    This is an additive coverage API; the historical ``extract_fab_bodies``
    map remains unchanged for compatibility.  No pad, courtyard, or
    rectangular fallback is invented for a missing body.
    """
    if not pcb_path.exists():
        raise FileNotFoundError(f"PCB file not found: {pcb_path}")

    expected = tuple(sorted(set(expected_refs)))
    fab_inputs = _tdb.parse_engine.extract_metadata_raw(
        pcb_path.read_text(encoding="utf-8")
    )["fab_body_inputs"]
    present: dict[str, FabBody] = {}
    missing: list[str] = []
    invalid: dict[str, str] = {}
    for ref in expected:
        shapes = fab_inputs.get(ref)
        if not shapes:
            missing.append(ref)
            continue
        try:
            points = _courtyard_points_from_raw(_fab_shape_inputs(shapes))
            if len(points) < 3:
                invalid[ref] = "F.Fab geometry is degenerate or empty"
                continue
            _rust_geometry.fab_body_validate_py(ref, _flat_points(points))
            present[ref] = FabBody(component_ref=ref, points=points)
        except Exception as exc:  # noqa: BLE001 - classify every parser/GEOS failure as invalid coverage
            invalid[ref] = str(exc)

    return FabBodyCoverage(
        present=present,
        missing=tuple(missing),
        invalid=invalid,
    )


def extract_fab_body_coverage_with_j1_supplement(
    pcb_path: Path,
    expected_refs: Iterable[str],
    supplement_path: Path,
    expected_sha256: str,
) -> FabBodyCoverage:
    """Augment board body coverage with the approved, content-bound J1 body.

    The supplement is an explicit model input, not a fallback.  Rust parses
    exactly one standalone footprint root and emits only its real ``F.Fab``
    graphics; this shim verifies the complete source digest, enforces the
    ``REF** -> J1`` mapping, and merges the resulting body only for J1.
    Missing pads, courtyard/silkscreen graphics, and synthetic rectangles
    therefore cannot become body geometry at this boundary.
    """
    refs = tuple(sorted(set(expected_refs)))
    if "J1" not in refs:
        raise ValueError("J1 supplement requires J1 in expected_refs")
    if not supplement_path.exists():
        raise FileNotFoundError(f"J1 supplement not found: {supplement_path}")
    if (
        len(expected_sha256) != 64
        or any(char not in "0123456789abcdef" for char in expected_sha256)
    ):
        raise ValueError("J1 supplement digest must be a full 64-character lowercase SHA256")

    supplement_content = supplement_path.read_bytes()
    actual_sha256 = hashlib.sha256(supplement_content).hexdigest()
    if actual_sha256 != expected_sha256:
        raise ValueError(
            "J1 supplement digest mismatch: "
            f"expected {expected_sha256}, got {actual_sha256}"
        )

    coverage = extract_fab_body_coverage(pcb_path, refs)
    if "J1" not in coverage.missing:
        if "J1" in coverage.present:
            raise ValueError(
                "J1 supplement is only valid when board extraction reports J1 missing; "
                "board coverage already contains valid J1 geometry"
            )
        if "J1" in coverage.invalid:
            raise ValueError(
                "J1 supplement is only valid when board extraction reports J1 missing; "
                f"board coverage marked J1 invalid: {coverage.invalid['J1']}"
            )
        raise ValueError(
            "J1 supplement requires board extraction to report J1 missing"
        )
    raw = _tdb.parse_engine.extract_standalone_footprint_raw(
        supplement_content.decode("utf-8"), "J1"
    )
    if raw.get("source_reference") != "REF**" or raw.get("expected_reference") != "J1":
        raise ValueError("J1 supplement did not preserve the explicit REF** -> J1 mapping")
    shapes = raw.get("fab_body_inputs")
    if not isinstance(shapes, list) or not shapes:
        raise ValueError("J1 supplement has no F.Fab body geometry")
    try:
        points = _courtyard_points_from_raw(_fab_shape_inputs(shapes))
        if len(points) < 3:
            raise ValueError("J1 supplement F.Fab geometry is degenerate or empty")
        _rust_geometry.fab_body_validate_py("J1", _flat_points(points))
    except Exception as exc:  # noqa: BLE001 - preserve an exact invalid-input reason
        raise ValueError(f"invalid J1 supplement F.Fab geometry: {exc}") from exc

    present = dict(coverage.present)
    present["J1"] = FabBody(component_ref="J1", points=points)
    missing = tuple(ref for ref in coverage.missing if ref != "J1")
    invalid = {ref: reason for ref, reason in coverage.invalid.items() if ref != "J1"}
    return FabBodyCoverage(
        present=present,
        missing=missing,
        invalid=invalid,
        supplement_digests={"J1": expected_sha256},
    )
