"""
Router V6 Stage 2.4: Compute Channel Widths

Measures channel width (clearance) at each point along the skeleton.
Part of temper-7qu7 (Stage 2 - Channel Analysis)

Phase E batch E4 (Rust Orchestration Engine plan 2026-08-09-001): the EDT
production path's ORCHESTRATION — the per-edge interior sampling, the
all-points assembly, the batched ``temper-geometry.edt_width_lookup_batch``
dispatch, the node/edge-width assembly and the min/max/avg statistics —
moved to ``temper-orchestration``'s ``channel_mapping.rs``
(``run_channel_widths_edt``).  The rasterised EDT grid preparation is now
owned by ``temper-geometry`` as one Rust call; this module only extracts
Shapely rings and adapts the returned mask byte buffer for its disk cache,
then wraps the Rust orchestration results back into ``ChannelWidths``
(unchanged).

**The shapely-blocked portions stay Python (evidence).** The pieces this
module still owns have no Rust equivalent, measured in the E4 scoping:

- ``_compute_width_at_point`` — shapely prepared-geometry ``Point.distance``
  to the exterior/interior rings (GEOS distance, the per-point reference
  path).
- ``_compute_board_fingerprint`` — the routing polygon's ``wkb``
  serialization (shapely) hashed for the EDT disk cache.
- ``_build_edt`` / ``_atomic_write_npz`` / ``_evict_if_over_budget`` — the
  Rust rasterise/EDT dispatch plus npz disk-cache lifecycle (Shapely ring
  extraction and NumPy file I/O).
- The ``available_area.is_empty`` guard and the ``MultiPolygon``
  decomposition / prepared-geometry caches (shapely objects).
- The per-point reference path (``use_edt=False``) — entirely
  ``_compute_width_at_point``.

The ``ChannelWidthsStage`` pipeline stage and ``validate_channel_widths``
validator stay Python unchanged (BoardState orchestration + the
``StageDRCFailure`` DRC-fence convention).  The oracle is pinned verbatim as
``tests/router_v6/_channel_ops_py_oracle.py`` (content-hash registered in
``scripts/oracle_hashes.json``).
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import tempfile
import zipfile
from dataclasses import dataclass, replace
from pathlib import Path
from typing import cast

import numpy as np
import temper_geometry as _tg
import temper_orchestration as _to

from temper_placer.deterministic.stages.base import Stage
from temper_placer.deterministic.state import BoardState
from temper_placer.router_v6.channel_skeleton import ChannelSkeleton
from temper_placer.router_v6.occupancy_grid import _area_rings
from temper_placer.router_v6.routing_space import RoutingSpace
from temper_placer.router_v6.stage_validators import (
    StageDRCFailure,
    register_validator,
)

# --- EDT disk cache: path scoping, atomicity, key sufficiency, eviction ---
#
# This cache was previously a single machine-global path
# (``Path("/tmp/temper-edt-cache")``), shared by every checkout/worktree on
# the box with no writer coordination and a cache key that hashed only
# ``(bounds, area)`` of the routing polygon. All three properties were
# wrong:
#
# 1. Global path: this repo routinely runs 20-60+ concurrent agent
#    worktrees against a shared machine (see AGENTS.md's cargo/venv
#    sections for the same failure class). A single shared cache directory
#    meant worktree A could read a `.npz` written by worktree B for an
#    *unrelated* board/branch state, and concurrent writers to the same
#    path produced the read-during-write ERRORs that motivated this fix
#    (spurious failures in test_stage2_monolith_parity.py).
# 2. Non-atomic writes: ``np.savez_compressed`` wrote directly to the
#    final path. A reader could ``np.load`` a truncated/half-written file.
# 3. Insufficient key: ``_compute_board_fingerprint`` hashed only
#    ``f"{bounds}{area}"`` -- the polygon's bounding box and total area.
#    This is NOT injective: two ``available_area`` geometries with
#    different shapes (different obstacle layout, different concavity,
#    holes moved around) can share the same bounding box and the same
#    total area while differing in actual boundary shape. Such a
#    collision would silently serve one board's distance field for
#    another's channel-width computation -- a correctness bug on the
#    clearance/routability path, not merely a performance one. Also
#    missing from the old key: ``cell_size`` (a coarser/finer grid changes
#    every distance value; only an unenforced code comment kept every
#    call site pinned to 0.1mm) and a cache-format version (so a future
#    change to the EDT algorithm or ``.npz`` schema would silently reuse
#    stale entries instead of invalidating them).
#
# Fixes below: scope the directory per checkout/worktree (and honor
# ``TMPDIR``), make writes atomic (temp file + ``os.replace``), and key on
# the routing polygon's exact geometry (WKB) plus cell_size plus a format
# version. See docs/solutions/ for the incident writeup.

_CACHE_FORMAT_VERSION = "v2"  # bump when the EDT algorithm or .npz schema changes
_EDT_CACHE_MAX_ENTRIES = int(os.environ.get("TEMPER_EDT_CACHE_MAX_ENTRIES", "500"))


def _checkout_discriminator() -> str:
    """A short hash that differs per git checkout/worktree.

    Walks up from this file to the nearest ``.git`` (a directory in a
    normal checkout, a file in a git *worktree* -- ``.exists()`` covers
    both) and hashes that directory's resolved path. Every worktree in
    this repo's multi-agent workflow lives at its own path
    (``.claude/worktrees/agent-<id>/...``), so this reliably gives each
    worktree its own cache subdirectory even though they all share the
    same ``$TMPDIR``. Falls back to this file's own parent directory if no
    ``.git`` is found (e.g. installed as a package outside a checkout).
    """
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / ".git").exists():
            root = parent
            break
    else:
        root = here.parent
    return hashlib.sha256(str(root).encode()).hexdigest()[:16]


def _cache_root() -> Path:
    """``$TMPDIR`` (or the platform default) scoped to this checkout."""
    return Path(tempfile.gettempdir()) / "temper-edt-cache" / _checkout_discriminator()


_EDT_CACHE_DIR = _cache_root()


@dataclass
class ChannelWidths:
    """Width measurements for routing channels."""

    layer_name: str
    node_widths: dict[tuple[float, float], float]  # Node position -> width in mm
    edge_widths: dict[tuple[tuple[float, float], tuple[float, float]], float]  # Edge -> min width
    min_width: float  # Minimum width across all channels
    max_width: float  # Maximum width across all channels
    avg_width: float  # Average width

    @property
    def bottleneck_width(self) -> float:
        """Return the minimum channel width (bottleneck)."""
        return self.min_width

    def get_node_width(self, node: tuple[float, float]) -> float:
        """Get width at a specific node."""
        return self.node_widths.get(node, 0.0)


def _edt_width_lookup_batch(
    xs: np.ndarray,
    ys: np.ndarray,
    edt: np.ndarray,
    mask: np.ndarray,
    bounds: tuple[float, float, float, float],
    cell_size: float,
) -> np.ndarray:
    """Batch EDT width lookup: one FFI crossing for all samples.

    Bit-identical per point to the pre-batch per-point reference
    implementation (same f64 arithmetic order, computed in
    ``temper-geometry``); the batch form exists because the sampling
    hot loop (~12k calls per layer) is per-call Python overhead.
    """
    h, w = edt.shape
    out = _tg.edt_width_lookup_batch(
        np.ascontiguousarray(xs, dtype=np.float64).tolist(),
        np.ascontiguousarray(ys, dtype=np.float64).tolist(),
        np.ascontiguousarray(edt, dtype=np.float64).tobytes(),
        np.ascontiguousarray(mask).tobytes(),
        h,
        w,
        bounds,
        cell_size,
    )
    return np.asarray(out, dtype=np.float64)


def _compute_board_fingerprint(routing_space: RoutingSpace, cell_size: float) -> str:
    """Content hash of everything that determines the EDT output.

    Must include, and previously did not:

    - The routing polygon's *exact* geometry (WKB), not just
      ``bounds``/``area``. Two ``available_area`` geometries can share a
      bounding box and total area while differing in actual boundary shape
      (different obstacle layout, concavity, hole placement) -- bounds+area
      is not an injective function of the geometry, so it was possible for
      two different boards/layers to collide on one cache key and silently
      serve each other's distance field.
    - ``cell_size``: a coarser/finer raster grid changes every distance
      value. Previously every call site just happened to pass 0.1mm by
      convention (see ``capacity_check.py``'s ``_EDT_CELL_SIZE`` comment
      "matches channel_widths.py") -- an unenforced invariant, not a
      guarantee.
    - ``_CACHE_FORMAT_VERSION``: bumping it invalidates every existing
      entry, so a future change to the EDT algorithm or the ``.npz``
      schema can't be silently misread as an old-format cache hit.

    ``layer_name`` is intentionally hashed in too (in addition to being a
    separate filename component below) so the key alone is already unique
    per layer, independent of how the filename happens to be built.
    """
    geom = routing_space.available_area
    h = hashlib.sha256()
    h.update(_CACHE_FORMAT_VERSION.encode())
    h.update(b"\0")
    h.update(routing_space.layer_name.encode())
    h.update(b"\0")
    h.update(repr(cell_size).encode())
    h.update(b"\0")
    h.update(geom.wkb)
    return h.hexdigest()[:32]


def _edt_cache_path(fp: str, layer: str) -> Path:
    safe_layer = "".join(c if c.isalnum() or c in "._-" else "_" for c in layer)
    return _EDT_CACHE_DIR / f"edt_{fp}_{safe_layer}.npz"


def _atomic_write_npz(path: Path, *, edt: np.ndarray, mask: np.ndarray) -> None:
    """Write an ``.npz`` cache entry atomically.

    ``np.savez_compressed`` writes directly to its destination with no
    atomicity guarantee: a concurrent reader (``np.load``) can observe a
    truncated/partial file mid-write, and a crash mid-write leaves a
    permanently corrupt file behind. Fixed by writing to a temp file in the
    *same directory* (so the final rename is same-filesystem, hence atomic
    on POSIX) and calling ``os.replace`` into the real path. A concurrent
    reader either sees the fully-old file or the fully-new file, never a
    partial one -- ``os.replace`` never exposes an intermediate state, and
    an already-open reader fd keeps working against the old inode even
    after this replace unlinks its name.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            np.savez_compressed(f, edt=edt, mask=mask)
        os.replace(tmp_name, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp_name)
        raise


def _evict_if_over_budget(max_entries: int = _EDT_CACHE_MAX_ENTRIES) -> None:
    """Bound the per-checkout cache to ``max_entries`` files (LRU by mtime).

    116,000+ files accumulated in the old global cache because nothing
    ever removed an entry -- it was a leak, not a working cache. Scoping
    the directory per checkout/worktree (above) already bounds the *blast
    radius* of that leak to one checkout's lifetime, but a single
    long-lived checkout run across many boards/layers/cell-sizes would
    still grow unboundedly, so this adds an explicit cap.

    Count-based LRU (evict oldest-by-mtime first) rather than a TTL or a
    byte-size budget: entries are small and roughly uniform in size for a
    given board, so entry count is a reasonable proxy for disk footprint,
    and mtime ordering needs no extra bookkeeping file (which would itself
    need cross-process locking). This runs after every write, is O(n) in
    directory size, and is a leak-prevention backstop rather than a
    hot-path optimization -- acceptable because the directory is now
    scoped per checkout rather than shared globally by every checkout on
    the machine, which was the actual cause of the 116K-file accumulation.
    Default cap is overridable via ``TEMPER_EDT_CACHE_MAX_ENTRIES`` for
    tests that want to exercise eviction without creating 500 files.
    """
    try:
        entries = sorted(
            (p for p in _EDT_CACHE_DIR.glob("edt_*.npz") if p.is_file()),
            # Deterministic tie-break: files written inside one filesystem
            # mtime tick share st_mtime, and Path.glob order is not stable
            # across platforms -- sorting on (mtime, name) makes eviction
            # deterministic instead of keeping an arbitrary subset of a
            # tie group (measured 2026-08-08: the bounds test flaked on a
            # burst of writes landing in one tick, evicting a newer entry
            # while keeping an older one).
            key=lambda p: (p.stat().st_mtime, p.name),
        )
    except OSError:
        return
    excess = len(entries) - max_entries
    for p in entries[: max(excess, 0)]:
        with contextlib.suppress(OSError):
            p.unlink()


def _exact_edt(mask: np.ndarray) -> np.ndarray:
    """Exact Euclidean distance transform, delegating to
    ``temper_geometry.exact_edt_transform`` (Rust Felzenszwalb-Huttenlocher
    sweep).  Bit-exact vs ``scipy.ndimage.distance_transform_edt(mask)`` (no
    ``sampling`` argument) on every input reachable by this module -- see
    ``docs/evidence/2026-08-07-exact-edt-rust-spike.md``.  ``mask`` must
    already be the desired ``uint8``/bool array at the call site; this
    function does not renormalize dtype or semantics.
    """
    h, w = mask.shape
    mask_u8 = np.ascontiguousarray(mask, dtype=np.uint8)
    out_bytes = _tg.exact_edt_transform(mask_u8.tobytes(), h, w)
    return np.frombuffer(out_bytes, dtype="<f8").reshape(h, w)


def _build_edt(
    routing_space: RoutingSpace,
    cell_size: float,
    use_cache: bool = True,
) -> tuple[np.ndarray, np.ndarray, tuple[float, float, float, float]]:
    """Build an EDT grid for the given routing space, with optional disk cache.

    Returns:
        (edt_distances, interior_mask, bounds)
    """
    bounds = routing_space.available_area.bounds
    fp = _compute_board_fingerprint(routing_space, cell_size)

    if use_cache:
        cache_path = _edt_cache_path(fp, routing_space.layer_name)
        try:
            # No pre-check ``cache_path.exists()``: that would be a
            # separate syscall racing a concurrent evictor/writer
            # (TOCTOU). Attempting the load directly and handling
            # "not there" is the race-free version of the same check.
            with np.load(cache_path) as data:
                return np.array(data["edt"]), np.array(data["mask"]), bounds
        except FileNotFoundError:
            pass
        except (OSError, ValueError, EOFError, zipfile.BadZipFile):
            # A cache entry that exists but fails to parse cleanly is
            # treated as a miss, never as an error: the atomic write below
            # means this should only happen for a pre-fix legacy file, not
            # a genuine race, but a cache must never be allowed to turn a
            # read failure into a computation failure.
            pass

    outer_rings, holes = _area_rings(routing_space.available_area)
    edt, mask_bytes, height, width = _tg.prepare_channel_widths_edt(
        outer_rings,
        holes,
        bounds,
        cell_size,
    )
    # The numerical preparation is Rust-owned. Rust transfers ownership of
    # the EDT Vec directly to a C-contiguous float64 ndarray; only the mask
    # remains a byte-buffer adaptation at this boundary. This preserves the
    # historical ndarray return contract and npz cache format without a
    # second EDT-sized serialization buffer.
    mask = np.frombuffer(mask_bytes, dtype=np.uint8).reshape(height, width).astype(bool)

    if use_cache:
        _atomic_write_npz(cache_path, edt=edt, mask=mask)
        _evict_if_over_budget()

    return edt, mask, bounds


def compute_channel_widths(
    routing_space: RoutingSpace,
    skeleton: ChannelSkeleton,
    sample_distance: float = 1.0,
    use_edt: bool = True,
) -> ChannelWidths:
    """
    Compute channel widths along the skeleton.

    Width is measured as the distance to the nearest obstacle (2x clearance).

    Args:
        routing_space: Routing space from Stage 2.2
        skeleton: Channel skeleton from Stage 2.3
        sample_distance: Distance between width samples along edges (mm)

    Returns:
        ChannelWidths with width measurements

    Example:
        >>> widths = compute_channel_widths(routing_space, skeleton)
        >>> widths.min_width > 0.0  # Some routing space available
        True
    """
    node_widths = {}
    edge_widths: dict[tuple[tuple[float, float], tuple[float, float]], float] = {}

    # Get the available routing area
    available_area = routing_space.available_area

    if available_area.is_empty or skeleton.node_count == 0:
        # No routing space or skeleton
        return ChannelWidths(
            layer_name=routing_space.layer_name,
            node_widths={},
            edge_widths={},
            min_width=0.0,
            max_width=0.0,
            avg_width=0.0,
        )

    # Pre-build the per-call caches for ``_compute_width_at_point``.
    # This is the hot path: the function is called once per
    # node (~2000) plus once per sample along each edge
    # (~10000 total) per layer.  Without these caches, each
    # call re-builds the prepared geometry and re-extracts the
    # exterior / interior rings via ``_get_ring`` (the dominant
    # per-call Shapely cost).  Demonstrated 2.2x speedup in the
    # sampling profile.
    import shapely.prepared
    from shapely.geometry import MultiPolygon

    prepared_area = shapely.prepared.prep(available_area)
    if isinstance(available_area, MultiPolygon):
        cached_polygons = list(available_area.geoms)
    else:
        cached_polygons = [available_area]
    cached_exteriors = [p.exterior for p in cached_polygons]
    cached_interiors = [list(p.interiors) for p in cached_polygons]

    # EDT path: rasterize + distance transform replaces per-point Shapely
    _edt_grid, _edt_mask, _edt_bounds, _edt_cell = None, None, None, 0.1
    if use_edt:
        _edt_grid, _edt_mask, _edt_bounds = _build_edt(routing_space, _edt_cell)

    def _width_at(p: tuple[float, float]) -> float:
        return _compute_width_at_point(
            p,
            available_area,
            _prepared=prepared_area,
            _polygons=cached_polygons,
            _exteriors=cached_exteriors,
            _interiors=cached_interiors,
        )

    if _edt_grid is not None and _edt_mask is not None and _edt_bounds is not None:
        # Batched EDT path: the edge sampling, the all-points assembly, the
        # batch width lookup and the node/edge-width + statistics assembly
        # run in temper-orchestration (channel_mapping.rs), bit-identical
        # per point to the reference pinned in the differential suites.
        _node_points = list(skeleton.graph.nodes)
        _edge_list = list(skeleton.graph.edges)

        node_widths_out, edge_widths_out, min_width, max_width, avg_width = (
            _to.run_channel_widths_edt(
                _node_points,
                _edge_list,
                np.ascontiguousarray(_edt_grid, dtype=np.float64).tobytes(),
                np.ascontiguousarray(_edt_mask).tobytes(),
                _edt_grid.shape[0],
                _edt_grid.shape[1],
                _edt_bounds,
                _edt_cell,
                sample_distance,
            )
        )

        node_widths = dict(((x, y), w) for (x, y, w) in node_widths_out)
        edge_widths = dict(((u, v), w) for u, v, w in edge_widths_out)
    else:
        # Reference path: per-point width sampling (EDT disabled or
        # unavailable).  Keep the original loop untouched for parity.
        for node in skeleton.graph.nodes:
            width = _width_at(node)
            node_widths[node] = width

        for u, v in skeleton.graph.edges:
            widths_along_edge = []

            widths_along_edge.append(node_widths[u])
            widths_along_edge.append(node_widths[v])

            dx = v[0] - u[0]
            dy = v[1] - u[1]
            edge_length = (dx**2 + dy**2) ** 0.5

            if edge_length > sample_distance:
                num_samples = int(edge_length / sample_distance)
                for i in range(1, num_samples):
                    t = i / num_samples
                    sample_x = u[0] + t * dx
                    sample_y = u[1] + t * dy
                    width = _width_at((sample_x, sample_y))
                    widths_along_edge.append(width)

            edge_widths[(cast(tuple[float, float], u), cast(tuple[float, float], v))] = min(widths_along_edge) if widths_along_edge else 0.0

        # Compute statistics (the reference path's own assembly).
        all_widths = list(node_widths.values()) + list(edge_widths.values())
        if all_widths:
            min_width = min(all_widths)
            max_width = max(all_widths)
            avg_width = sum(all_widths) / len(all_widths)
        else:
            min_width = max_width = avg_width = 0.0

    return ChannelWidths(
        layer_name=routing_space.layer_name,
        node_widths=node_widths,
        # skeleton.graph.nodes()/edges() are untyped in mypy, but the nodes
        # are genuinely (x, y) coordinate tuples at runtime; the edge key is
        # ((u_x, u_y), (v_x, v_y)).
        edge_widths=cast(
            dict[tuple[tuple[float, float], tuple[float, float]], float],
            edge_widths,
        ),
        min_width=float(min_width),
        max_width=float(max_width),
        avg_width=float(avg_width),
    )


def _compute_width_at_point(
    point: tuple[float, float],
    available_area,
    _prepared=None,
    _polygons=None,
    _exteriors=None,
    _interiors=None,
) -> float:
    """
    Compute channel width at a point.

    Width is 2x the distance to the nearest boundary (clearance on both sides).

    Args:
        point: (x, y) coordinate
        available_area: Available routing area (Polygon or MultiPolygon)
        _prepared: Optional pre-built ``shapely.prepared.prep`` of
            ``available_area``.  Pass this in for hot loops to skip
            the per-call prepared-geometry build.
        _polygons: Optional pre-extracted polygon list
            (``list(available_area.geoms)`` for MultiPolygon,
            ``[available_area]`` for Polygon).  Pass for hot loops.
        _exteriors: Optional pre-cached list of ``polygon.exterior``
            rings (one per polygon).  Avoids the per-call
            ``_get_ring`` access on each ``polygon.distance``.
        _interiors: Optional pre-cached list of
            ``list(polygon.interiors)`` per polygon.  Same
            rationale as ``_exteriors``.

    Returns:
        Width in mm
    """
    from shapely.geometry import MultiPolygon, Polygon
    from shapely.geometry import Point as ShapelyPoint

    pt = ShapelyPoint(point)

    # Lazy-init the per-call caches (back-compat for callers
    # that don't pre-compute).  In a hot loop the caller should
    # pass these in for the 2x speedup demonstrated in the
    # sampling profile.
    if _prepared is None:
        import shapely.prepared

        _prepared = shapely.prepared.prep(available_area)
    if _polygons is None:
        if isinstance(available_area, Polygon):
            _polygons = [available_area]
        elif isinstance(available_area, MultiPolygon):
            _polygons = list(available_area.geoms)
        else:
            return 0.0

    # Check if point is inside available area (prepared geometry
    # is 5-10x faster than the bare .contains() call).
    if not _prepared.contains(pt):
        return 0.0

    # Distance to boundary.  We pre-cache the exterior / interior
    # rings once per call (or once per run if the caller pre-cached)
    # because each ``polygon.exterior`` / ``polygon.interiors``
    # access goes through Shapely's ``_get_ring`` and is the
    # dominant per-call cost in the original implementation
    # (~700k ``_get_ring`` calls in the sampling profile).
    min_distance = float("inf")
    if _exteriors is None:
        _exteriors = [p.exterior for p in _polygons]
    if _interiors is None:
        _interiors = [list(p.interiors) for p in _polygons]

    for exterior, interiors in zip(_exteriors, _interiors):
        d = pt.distance(exterior)
        if d < min_distance:
            min_distance = d
        for interior in interiors:
            d = pt.distance(interior)
            if d < min_distance:
                min_distance = d

    if min_distance == float("inf"):
        return 0.0
    return 2.0 * min_distance


class ChannelWidthsStage(Stage):
    """Stage 2.4: Compute channel widths along skeletons."""

    @property
    def name(self) -> str:
        return "ChannelWidths"

    def run(self, state: BoardState) -> BoardState:
        channel_widths: dict[str, ChannelWidths] = {}
        for layer_name, skeleton in state.channel_skeletons.items():  # type: ignore[union-attr]
            widths = compute_channel_widths(
                state.routing_spaces[layer_name],  # type: ignore[index]
                skeleton,
            )
            channel_widths[layer_name] = widths
        return replace(state, channel_widths=channel_widths)


@register_validator("ChannelWidths")
def validate_channel_widths(state: BoardState) -> list[StageDRCFailure]:
    """Validate channel width invariants."""
    failures: list[StageDRCFailure] = []
    if state.channel_widths is None:
        failures.append(
            StageDRCFailure(
                field="channel_widths",
                value=None,
                reason="Channel widths not computed",
                stage="ChannelWidths",
            )
        )
        return failures

    for layer_name, cw in state.channel_widths.items():
        if cw.min_width < 0:
            failures.append(
                StageDRCFailure(
                    field="channel_widths",
                    value=layer_name,
                    reason="Negative minimum width: " + repr(cw.min_width),
                    stage="ChannelWidths",
                )
            )
        if cw.max_width < 0:
            failures.append(
                StageDRCFailure(
                    field="channel_widths",
                    value=layer_name,
                    reason="Negative maximum width: " + repr(cw.max_width),
                    stage="ChannelWidths",
                )
            )

    return failures
