"""Concurrent-*process* tests for the EDT disk cache in ``channel_widths.py``.

Context: the cache used to be a single machine-global path
(``/tmp/temper-edt-cache``, no per-checkout scoping), written with a plain
``np.savez_compressed(final_path, ...)`` (no atomicity), keyed by only
``sha256(f"{bounds}{area}")`` of the routing polygon (not the actual
geometry). That combination was discovered via spurious ERRORs in
``test_stage2_monolith_parity.py`` when concurrent processes hammered the
shared path, and is fixed in ``channel_widths.py`` by: scoping the cache
directory per checkout/worktree under ``tempfile.gettempdir()``, writing via
temp-file-plus-``os.replace`` (atomic on POSIX), and hashing the polygon's
exact WKB geometry + cell_size + a format version.

These tests use ``multiprocessing`` with the (default-on-Linux) **fork**
start method to get genuinely separate OS processes -- distinct PIDs,
independent file descriptor tables, real races on the shared cache file --
which is the failure mode an in-process thread test cannot exercise (the
original bug was never a GIL/threading problem; it was concurrent
*processes* racing on a filesystem path). Forking (rather than "spawn") also
lets the parent monkeypatch ``_EDT_CACHE_DIR`` to an isolated ``tmp_path``
*before* forking, so these tests never touch the real
``/tmp/temper-edt-cache/<checkout-hash>`` directory a live session might be
using concurrently.
"""

from __future__ import annotations

import multiprocessing as mp
from pathlib import Path

import numpy as np
import pytest
from shapely import affinity
from shapely.geometry import Polygon, box

from temper_placer.router_v6 import channel_widths as cw
from temper_placer.router_v6.channel_widths import (
    _atomic_write_npz,
    _build_edt,
    _compute_board_fingerprint,
    _evict_if_over_budget,
)


class _FakeRoutingSpace:
    def __init__(self, polygon, layer_name: str = "F.Cu") -> None:
        self.available_area = polygon
        self.layer_name = layer_name


def _fork_ctx() -> mp.context.BaseContext:
    # Explicit, not the platform default: the atomicity/no-collision proofs
    # below depend on children inheriting the parent's *already patched*
    # ``cw._EDT_CACHE_DIR`` via copy-on-write, which only "spawn" cannot do
    # (spawn re-imports the module fresh, losing the monkeypatch). "fork" is
    # available on the Linux CI/dev environment this repo targets.
    return mp.get_context("fork")


# ---------------------------------------------------------------------------
# Key sufficiency: two different shapes must not collide, even when they
# share the OLD cache key's inputs (bounds + area) exactly.
# ---------------------------------------------------------------------------


def _make_adversarial_pair() -> tuple[Polygon, Polygon]:
    """Two L-shaped polygons, related by a 180-degree rotation about the
    center of their shared bounding box.

    Rotation by 180 degrees preserves both area and bounding box exactly
    (the box maps onto itself), but this particular L-shape has no
    180-degree rotational symmetry, so the rotated copy is a genuinely
    different point set / different WKB. This is exactly the adversarial
    case the OLD fingerprint (``sha256(f"{bounds}{area}")``) could not
    distinguish -- two different boards that would have silently collided
    on one cache entry.
    """
    p = Polygon([(0, 0), (10, 0), (10, 4), (6, 4), (6, 10), (0, 10)])
    q = affinity.rotate(p, 180, origin=(5, 5))
    assert p.bounds == q.bounds, "test setup: bounds must match to be adversarial"
    assert abs(p.area - q.area) < 1e-9, "test setup: area must match to be adversarial"
    assert not p.equals(q), "test setup: shapes must actually differ"
    return p, q


def test_fingerprint_differs_for_shapes_sharing_bounds_and_area():
    """Headline key-sufficiency proof: same bounds, same area, different
    shape -> different cache key.

    This is a single-process, deterministic regression test for the exact
    defect described in the task: the old key was `sha256(bounds + area)`,
    which is not injective over polygon shape.
    """
    p, q = _make_adversarial_pair()
    fp_p = _compute_board_fingerprint(_FakeRoutingSpace(p), 1.0)
    fp_q = _compute_board_fingerprint(_FakeRoutingSpace(q), 1.0)
    assert fp_p != fp_q, (
        "two distinct polygons with identical bounds and area collided on one "
        "cache key -- this is the silent-wrong-answer hazard the task called out"
    )


def test_fingerprint_includes_cell_size():
    """Same geometry, different cell_size, must not collide either.

    The pre-fix key ignored ``cell_size`` entirely; every call site just
    happened to agree on 0.1mm by an unenforced comment
    (``capacity_check.py``'s ``_EDT_CELL_SIZE`` "matches channel_widths.py").
    """
    board = box(0, 0, 20, 20)
    fp_a = _compute_board_fingerprint(_FakeRoutingSpace(board), 0.1)
    fp_b = _compute_board_fingerprint(_FakeRoutingSpace(board), 0.2)
    assert fp_a != fp_b


def test_cache_directory_is_not_the_old_global_path():
    """The directory must be scoped, not the literal machine-global path."""
    assert Path("/tmp/temper-edt-cache") != cw._EDT_CACHE_DIR
    assert cw._EDT_CACHE_DIR.parent.name == "temper-edt-cache"
    # Scoped under the resolved tempdir (honors $TMPDIR), not hardcoded /tmp.
    import tempfile

    assert str(cw._EDT_CACHE_DIR).startswith(str(Path(tempfile.gettempdir())))


# ---------------------------------------------------------------------------
# Concurrent-process worker functions.  Must be module-level (picklable) --
# multiprocessing sends task args through a queue even under "fork".
# ---------------------------------------------------------------------------


def _worker_build_edt_for_shape(args: tuple[int, bytes, str, float, int]) -> tuple[bool, str]:
    """Repeatedly build+cache the EDT for one of two adversarial shapes and
    verify the result always matches a freshly (uncached) computed
    reference for THAT SAME shape -- i.e. this process never observes the
    other shape's cached entry."""
    worker_id, wkb, layer_name, cell_size, n_iters = args
    from shapely import wkb as wkb_mod

    polygon = wkb_mod.loads(wkb)
    rs = _FakeRoutingSpace(polygon, layer_name)

    # Ground truth, computed once, uncached, before any cache pollution.
    ref_edt, ref_mask, _ = _build_edt(rs, cell_size, use_cache=False)

    for _ in range(n_iters):
        edt, mask, _bounds = _build_edt(rs, cell_size, use_cache=True)
        if edt.shape != ref_edt.shape or mask.shape != ref_mask.shape:
            return False, f"worker {worker_id}: shape mismatch vs reference"
        if not np.array_equal(mask, ref_mask):
            return False, f"worker {worker_id}: mask does not match own reference (foreign entry?)"
        if not np.allclose(edt, ref_edt):
            return False, f"worker {worker_id}: edt does not match own reference (foreign entry?)"
    return True, ""


@pytest.mark.slow
def test_no_cross_contamination_concurrent_processes(tmp_path, monkeypatch):
    """Many real OS processes, racing on ONE shared cache directory, split
    between two adversarial (equal-bounds, equal-area) shapes: no process
    may ever read back the other shape's cached EDT/mask.

    This is the direct test for "a cache keyed on something insufficiently
    specific ... can serve a stale or foreign result" -- run under actual
    process concurrency, not in-process.
    """
    monkeypatch.setattr(cw, "_EDT_CACHE_DIR", tmp_path)

    p, q = _make_adversarial_pair()
    layer = "F.Cu"
    cell_size = 1.0
    n_workers = 8
    n_iters = 15

    tasks = []
    for i in range(n_workers):
        shape = p if i % 2 == 0 else q
        tasks.append((i, shape.wkb, layer, cell_size, n_iters))

    ctx = _fork_ctx()
    with ctx.Pool(processes=n_workers) as pool:
        results = pool.map(_worker_build_edt_for_shape, tasks)

    failures = [msg for ok, msg in results if not ok]
    assert not failures, "\n".join(failures)


def _worker_hammer_atomic_write(args: tuple[int, int]) -> list[str]:
    """Writer+reader in one process, tight loop, on a single shared path.

    Every write fills the whole ``edt`` array with ONE constant tag value
    unique to (worker_id, iteration). A reader that ever observes a
    non-constant array proves it read bytes from two different writes at
    once -- a torn/partial read, which atomic replace must prevent.
    """
    worker_id, n_iters = args
    path = cw._EDT_CACHE_DIR / "hammer_shared.npz"
    errors: list[str] = []
    shape = (24, 24)
    for i in range(n_iters):
        tag = float(worker_id * 1_000_000 + i)
        edt = np.full(shape, tag, dtype=np.float64)
        mask = np.ones(shape, dtype=bool)
        _atomic_write_npz(path, edt=edt, mask=mask)

        try:
            with np.load(path) as data:
                read_edt = np.array(data["edt"])
                read_mask = np.array(data["mask"])
        except FileNotFoundError:
            # Another worker's eviction/replace raced us; acceptable --
            # the property under test is "no PARTIAL read", not "always hit".
            continue
        except Exception as exc:  # noqa: BLE001 - any parse failure is itself a bug
            errors.append(f"worker {worker_id} iter {i}: read raised {type(exc).__name__}: {exc}")
            continue

        if read_edt.shape != shape or read_mask.shape != shape:
            errors.append(f"worker {worker_id} iter {i}: torn read, bad shape {read_edt.shape}")
        elif not np.all(read_edt == read_edt.flat[0]):
            sample = read_edt.flat[:6].tolist()
            errors.append(f"worker {worker_id} iter {i}: torn read, non-constant array {sample}")
        elif not read_mask.all():
            errors.append(f"worker {worker_id} iter {i}: torn read, corrupt mask")
    return errors


@pytest.mark.slow
def test_atomic_write_no_torn_reads_under_concurrent_processes(tmp_path, monkeypatch):
    """Many real OS processes hammering ONE shared cache path (write, then
    immediately read) must never observe a partial/torn file.

    Directly exercises ``_atomic_write_npz`` (bypassing ``_build_edt``'s own
    graceful degrade-to-recompute-on-parse-error path), so a failure here
    means atomicity is actually broken, not just that the safety net caught
    something.
    """
    monkeypatch.setattr(cw, "_EDT_CACHE_DIR", tmp_path)

    n_workers = 12
    n_iters = 60
    tasks = [(i, n_iters) for i in range(n_workers)]

    ctx = _fork_ctx()
    with ctx.Pool(processes=n_workers) as pool:
        results = pool.map(_worker_hammer_atomic_write, tasks)

    all_errors = [e for errs in results for e in errs]
    assert not all_errors, "\n".join(all_errors[:20])


# ---------------------------------------------------------------------------
# Eviction / bounded size
# ---------------------------------------------------------------------------


def test_eviction_bounds_entry_count(tmp_path, monkeypatch):
    """Writing past the cap evicts the oldest entries, keeping the
    directory bounded rather than growing without limit (the 116K-file
    leak this replaces)."""
    monkeypatch.setattr(cw, "_EDT_CACHE_DIR", tmp_path)
    cap = 5

    for i in range(cap * 3):
        path = tmp_path / f"edt_fake{i:03d}_F.Cu.npz"
        _atomic_write_npz(path, edt=np.zeros((2, 2)), mask=np.ones((2, 2), dtype=bool))
        _evict_if_over_budget(max_entries=cap)

    remaining = sorted(tmp_path.glob("edt_*.npz"))
    assert len(remaining) <= cap
    # The most-recently-written entries must be the ones kept (LRU evicts
    # oldest first), not an arbitrary subset.
    kept_indices = sorted(int(p.stem.split("fake")[1].split("_")[0]) for p in remaining)
    assert kept_indices == list(range(cap * 3 - cap, cap * 3))
