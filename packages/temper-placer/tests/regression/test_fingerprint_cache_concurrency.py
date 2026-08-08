"""Concurrent-*process* tests for ``.regression-cache.json``'s atomic write.

Context: ``fingerprint.py::save_cache`` used to write the regression cache
with a plain ``json.dump(cache, f, indent=2)`` directly to the destination
path -- no atomicity. The cache's *key* is sufficient (each board entry is
keyed on the input content hash and the full source-tree hash together, per
``should_skip``), so a stale/foreign entry being served was never the
hazard here -- unlike the EDT disk cache this fix mirrors (commit
``c57101ac``, ``router_v6/channel_widths.py::_atomic_write_npz``), whose key
WAS insufficient. What a non-atomic write DOES risk is a crash (or a
concurrent reader) mid-write observing a truncated/malformed JSON document,
corrupting the WHOLE cache -- every board's entry, not just the one being
updated -- because the file holds one JSON object for the entire corpus.
Fixed the same way as the EDT cache: write to a temp file in the same
directory, then ``os.replace`` into place (atomic on POSIX).

Mirrors ``test_edt_cache_concurrency.py``'s
``test_atomic_write_no_torn_reads_under_concurrent_processes`` almost
exactly (same rationale for real OS processes over threads: distinct PIDs,
independent file descriptor tables, a genuine race on one filesystem path --
not a GIL/threading concern).
"""

from __future__ import annotations

import json
import multiprocessing as mp
from pathlib import Path

import pytest

from temper_placer.regression import fingerprint as fp


def _fork_ctx() -> mp.context.BaseContext:
    # Explicit, not the platform default -- see test_edt_cache_concurrency.py
    # for why "fork" (children inherit the parent's already-patched module
    # state via copy-on-write) is required, not merely convenient, and why
    # "spawn" (re-imports the module fresh) would not work here.
    return mp.get_context("fork")


# ---------------------------------------------------------------------------
# Concurrent-process worker. Must be module-level (picklable) --
# multiprocessing sends task args through a queue even under "fork".
# ---------------------------------------------------------------------------


def _worker_hammer_save_cache(args: tuple[Path, int, int]) -> list[str]:
    """Writer+reader in one process, tight loop, on a single shared path.

    Every write fills the cache with ONE constant tag value unique to
    (worker_id, iteration), spread across every board entry so a torn read
    that mixes bytes from two different writes is detectable even if it
    lands mid-object rather than at a board boundary. A reader that ever
    observes a non-constant tag, or a JSON parse failure, proves it read a
    partial/mixed file -- exactly what atomic replace must prevent.
    """
    corpus_root, worker_id, n_iters = args
    corpus_root = Path(corpus_root)
    errors: list[str] = []
    n_boards = 12

    for i in range(n_iters):
        tag = f"w{worker_id}-i{i}"
        cache = {
            "version": fp.CACHE_VERSION,
            "boards": {
                f"board_{b}": {
                    "input_fingerprint": tag,
                    "source_fingerprint": tag,
                    "last_pass_commit": tag,
                    "last_pass_at": tag,
                }
                for b in range(n_boards)
            },
        }
        fp.save_cache(corpus_root, cache)

        cache_path = corpus_root / fp.CACHE_FILENAME
        try:
            text = cache_path.read_text()
            data = json.loads(text)
        except FileNotFoundError:
            # Another worker's replace raced us between our write and our
            # read -- acceptable; the property under test is "no PARTIAL
            # read", not "always hit". os.replace never leaves the path
            # missing (the old or new file is always there), but a
            # concurrent test run against a shared tmp_path could still
            # see this on a first-ever write; kept defensive.
            continue
        except json.JSONDecodeError as exc:
            errors.append(f"worker {worker_id} iter {i}: torn read, JSONDecodeError: {exc}")
            continue
        except Exception as exc:  # noqa: BLE001 - any read failure is itself a bug
            errors.append(f"worker {worker_id} iter {i}: read raised {type(exc).__name__}: {exc}")
            continue

        if not isinstance(data, dict) or "boards" not in data:
            errors.append(f"worker {worker_id} iter {i}: torn read, malformed top-level shape")
            continue

        tags = {
            v
            for board in data["boards"].values()
            for v in (
                board.get("input_fingerprint"),
                board.get("source_fingerprint"),
                board.get("last_pass_commit"),
                board.get("last_pass_at"),
            )
        }
        if len(tags) != 1:
            errors.append(
                f"worker {worker_id} iter {i}: torn read, mixed tags from multiple "
                f"writes in one file: {sorted(tags)[:6]}"
            )
    return errors


@pytest.mark.slow
def test_atomic_write_no_torn_reads_under_concurrent_processes(tmp_path):
    """Many real OS processes hammering ONE shared ``.regression-cache.json``
    path (write, then immediately read) must never observe a partial/torn
    file, proving the fix stated in the module docstring: a crash (or a
    racing reader) mid-write cannot corrupt every board's entry.
    """
    n_workers = 12
    n_iters = 40
    tasks = [(tmp_path, i, n_iters) for i in range(n_workers)]

    ctx = _fork_ctx()
    with ctx.Pool(processes=n_workers) as pool:
        results = pool.map(_worker_hammer_save_cache, tasks)

    all_errors = [e for errs in results for e in errs]
    assert not all_errors, "\n".join(all_errors[:20])


def test_save_cache_leaves_no_temp_file_behind(tmp_path):
    """A successful write cleans up after itself: only the final cache file
    remains in the directory, not a stray ``.tmp`` sibling."""
    cache = {"version": fp.CACHE_VERSION, "boards": {}}
    fp.save_cache(tmp_path, cache)

    entries = sorted(p.name for p in tmp_path.iterdir())
    assert entries == [fp.CACHE_FILENAME], entries


def test_save_cache_round_trips_through_load_cache(tmp_path):
    """Sanity check: the atomic-write refactor doesn't change the file's
    observable content or shape from the reader's point of view."""
    cache = {
        "version": fp.CACHE_VERSION,
        "boards": {"demo": {"input_fingerprint": "abc", "source_fingerprint": "def"}},
    }
    fp.save_cache(tmp_path, cache)

    loaded = fp.load_cache(tmp_path)
    assert loaded["boards"] == cache["boards"]
    assert "generated_at" in loaded
