"""
Channel sidecar loader for placement-time routability scoring.

Consumes ``placement.channels.json`` (written by Router V6 Stage 2) and exposes
a typed, frozen ``ChannelMap`` plus a single ``routability_penalty`` function
that the placer's ``score_slot`` closure consults. The loader degrades
gracefully: any read or schema failure returns ``ChannelMap.empty()`` and the
caller can fall back to wirelength-only scoring.

The grid is stored as a flat tuple of floats (occupancy in [0.0, 1.0]) keyed
by ``(y * width + x)`` for O(1) integer index lookups on the placement hot
path. Bottlenecks are stored as ``(x, y, layer, severity_index, score)``
tuples inside a frozenset so membership tests stay hash-based.
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


ALLOWED_SEVERITIES: frozenset[str] = frozenset({"LOW", "MEDIUM", "HIGH", "CRITICAL"})

#: Severity -> weight multiplier used by :func:`routability_penalty`.
SEVERITY_WEIGHTS: dict[str, float] = {
    "LOW": 0.05,
    "MEDIUM": 0.15,
    "HIGH": 0.4,
    "CRITICAL": 1.0,
}

#: Schema hash allowlist. The Router V6 Stage 2 sidecar writer must include
#: one of these values in ``temper_schema_hash``; otherwise the loader raises.
ALLOWED_SCHEMA_HASHES: frozenset[str] = frozenset(
    {
        "temper.channels.v1",
        "temper.channels.v1.0",
    }
)


class ChannelSidecarError(Exception):
    """Raised when a sidecar cannot be loaded or fails schema validation."""


@dataclass(frozen=True)
class Bottleneck:
    """A single routing bottleneck cell."""

    x: int
    y: int
    layer: str
    severity: str
    score: float

    def to_dict(self) -> dict:
        return {
            "x": self.x,
            "y": self.y,
            "layer": self.layer,
            "severity": self.severity,
            "score": self.score,
        }


@dataclass(frozen=True)
class ChannelMap:
    """In-memory snapshot of the channel sidecar.

    Attributes:
        grid: Tuple of ``height`` rows, each a tuple of ``width`` floats in
            ``[0.0, 1.0]`` representing per-cell occupancy. Stored as nested
            tuples so the dataclass remains hashable/frozen.
        cell_size_um: Cell edge length in micrometres.
        bottlenecks: Frozenset of :class:`Bottleneck` records.
        schema_hash: Schema identifier from the sidecar; ``""`` for empty map.
    """

    grid: tuple[tuple[float, ...], ...]
    cell_size_um: float
    bottlenecks: frozenset[Bottleneck] = field(default_factory=frozenset)
    schema_hash: str = ""

    @property
    def width(self) -> int:
        return len(self.grid[0]) if self.grid else 0

    @property
    def height(self) -> int:
        return len(self.grid)

    @classmethod
    def empty(cls) -> "ChannelMap":
        """Return a sentinel zero-bottleneck map (no routability penalty)."""
        return cls(grid=(), cell_size_um=0, bottlenecks=frozenset(), schema_hash="")

    @classmethod
    def load_from_sidecar(cls, path: Path | str) -> "ChannelMap":
        """Load a sidecar from ``path``.

        On any error (missing file, malformed JSON, schema mismatch, unknown
        severity, unknown schema hash) this raises
        :class:`ChannelSidecarError`. The pipeline wrapper at
        :mod:`temper_placer.deterministic` catches that error and falls back to
        ``ChannelMap.empty()``.
        """
        path = Path(path)
        try:
            raw = path.read_text()
        except FileNotFoundError as exc:
            raise ChannelSidecarError(f"sidecar not found: {path}") from exc
        except OSError as exc:
            raise ChannelSidecarError(f"sidecar unreadable: {path}: {exc}") from exc

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ChannelSidecarError(
                f"malformed sidecar JSON at {path}: {exc}"
            ) from exc

        return cls._from_payload(payload, source=str(path))

    @classmethod
    def _from_payload(cls, payload: dict, source: str = "<payload>") -> "ChannelMap":
        if not isinstance(payload, dict):
            raise ChannelSidecarError(
                f"sidecar {source}: top-level must be an object"
            )

        schema_hash = payload.get("temper_schema_hash", "")
        if schema_hash not in ALLOWED_SCHEMA_HASHES:
            raise ChannelSidecarError(
                f"sidecar {source}: unknown temper_schema_hash {schema_hash!r}; "
                f"allowed: {sorted(ALLOWED_SCHEMA_HASHES)}"
            )

        cell_size_um_raw = payload.get("cell_size_um")
        if not isinstance(cell_size_um_raw, (int, float)) or cell_size_um_raw <= 0:
            raise ChannelSidecarError(
                f"sidecar {source}: cell_size_um must be a positive number, "
                f"got {cell_size_um_raw!r}"
            )
        cell_size_um = float(cell_size_um_raw)

        grid_raw = payload.get("grid")
        if not isinstance(grid_raw, list) or not grid_raw:
            raise ChannelSidecarError(
                f"sidecar {source}: grid must be a non-empty 2D list"
            )
        grid: list[tuple[float, ...]] = []
        width = None
        for row in grid_raw:
            if not isinstance(row, list):
                raise ChannelSidecarError(
                    f"sidecar {source}: grid row must be a list, got {type(row).__name__}"
                )
            if width is None:
                width = len(row)
            elif len(row) != width:
                raise ChannelSidecarError(
                    f"sidecar {source}: grid rows must have uniform width "
                    f"(expected {width}, got {len(row)})"
                )
            cells: list[float] = []
            for v in row:
                if not isinstance(v, (int, float)):
                    raise ChannelSidecarError(
                        f"sidecar {source}: grid cell must be numeric, got {v!r}"
                    )
                fv = float(v)
                if fv < 0.0 or fv > 1.0:
                    raise ChannelSidecarError(
                        f"sidecar {source}: grid cell occupancy {fv} out of [0.0, 1.0]"
                    )
                cells.append(fv)
            grid.append(tuple(cells))
        grid_tuple = tuple(grid)

        bottlenecks: set[Bottleneck] = set()
        for entry in payload.get("bottlenecks", []):
            if not isinstance(entry, dict):
                raise ChannelSidecarError(
                    f"sidecar {source}: bottleneck must be an object, got {entry!r}"
                )
            severity = entry.get("severity")
            if severity not in ALLOWED_SEVERITIES:
                raise ChannelSidecarError(
                    f"sidecar {source}: unknown bottleneck severity {severity!r}; "
                    f"allowed: {sorted(ALLOWED_SEVERITIES)}"
                )
            try:
                x = int(entry["x"])
                y = int(entry["y"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ChannelSidecarError(
                    f"sidecar {source}: bottleneck x/y must be ints: {entry!r}"
                ) from exc
            layer = str(entry.get("layer", "F.Cu"))
            score_raw = entry.get("score", 1.0)
            if not isinstance(score_raw, (int, float)):
                raise ChannelSidecarError(
                    f"sidecar {source}: bottleneck score must be numeric, got {score_raw!r}"
                )
            bottlenecks.add(
                Bottleneck(
                    x=x, y=y, layer=layer, severity=severity, score=float(score_raw)
                )
            )

        return cls(
            grid=grid_tuple,
            cell_size_um=cell_size_um,
            bottlenecks=frozenset(bottlenecks),
            schema_hash=schema_hash,
        )

    def has_grid(self) -> bool:
        return bool(self.grid) and self.cell_size_um > 0 and self.width > 0


def routability_penalty(
    slot: tuple[float, float], channel_map: ChannelMap
) -> float:
    """Return a routability penalty in ``[0.0, 1.0]`` for ``slot``.

    The slot position is in millimetres (mm); it is converted to grid
    coordinates using ``floor`` semantics so a 1 µm offset straddling a
    cell boundary lands in the lower-indexed cell. The penalty is

        ``severity_weight * (0.5 + 0.5 * occupancy)``

    where ``severity_weight`` is looked up from the worst-severity bottleneck
    covering the cell, or ``0.0`` if the cell is not in the bottleneck set.
    Out-of-grid slots return ``0.0`` so placement at the board edge is never
    penalised purely for being outside the sidecar's coverage.

    An empty :class:`ChannelMap` always returns ``0.0``.
    """
    if not channel_map.has_grid():
        return 0.0

    cell_size_um = channel_map.cell_size_um
    width = channel_map.width
    height = channel_map.height

    x_mm, y_mm = slot
    gx = int(math.floor((x_mm * 1000.0) / cell_size_um))
    gy = int(math.floor((y_mm * 1000.0) / cell_size_um))

    if gx < 0 or gx >= width or gy < 0 or gy >= height:
        return 0.0

    row = channel_map.grid[gy]
    occupancy = row[gx]
    if occupancy < 0.0:
        occupancy = 0.0
    elif occupancy > 1.0:
        occupancy = 1.0

    # Look up the worst-severity bottleneck for this cell. Bottlenecks are
    # stored per-layer; we conservatively pick the worst across all layers
    # because the penalty function has no layer context.
    severity = ""
    worst_score = 0.0
    for bn in channel_map.bottlenecks:
        if bn.x == gx and bn.y == gy:
            sev_weight = SEVERITY_WEIGHTS.get(bn.severity, 0.0)
            if sev_weight > worst_score:
                worst_score = sev_weight
                severity = bn.severity
            elif sev_weight == worst_score and sev_weight > 0.0 and not severity:
                severity = bn.severity

    if not severity:
        return 0.0

    severity_weight = SEVERITY_WEIGHTS[severity]
    penalty = severity_weight * (0.5 + 0.5 * occupancy)
    if penalty < 0.0:
        return 0.0
    if penalty > 1.0:
        return 1.0
    return penalty
