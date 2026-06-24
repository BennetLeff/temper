"""Hash-keyed DRC regression cache.

The fence is cheap on repeated runs: cache the ``drcc.v1.json`` schema
artifact on disk keyed on a stable hash of the inputs.  Cache hits
return the stored result with ``cache_hit=True``; misses run
kicad-cli and write the artifact.  ``UNVERIFIED`` results are never
cached — caching a missing measurement is a memory leak, and the
next run with the same inputs must re-attempt the measurement.

The cache key is the SHA256 of
``f"{router_commit}|{board_hash}|{kicad_cli_version}|{design_rule_set_hash}|{posture.value}"``
— a content-addressed tuple that any change to inputs (a new commit,
a new board, a new kicad-cli version, a new rule set, a different
posture) invalidates deterministically.

The cache lives at ``~/.cache/temper/drc/`` per-user, never in the
repo.  A missing or unreadable cache directory is non-fatal — the
fence still runs kicad-cli, the cache is best-effort.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from temper_placer.validation.drc_runner import (
    DrcResult,
    DrcStatus,
    FencePosture,
    run_drc,
)
from temper_placer.validation.drc_schema import (
    compute_provenance,
    from_drcc_v1,
    to_drcc_v1,
)
from temper_placer.validation.drc_state import FenceState

_LOGGER = logging.getLogger(__name__)

#: Default cache directory.  Per-user, never in the repo.  Tests
#: override this with a tmp_path.
DEFAULT_CACHE_DIR = Path.home() / ".cache" / "temper" / "drc"


def make_cache_key(
    *,
    router_commit: str,
    board_hash: str,
    kicad_cli_version: str,
    design_rule_set_hash: str,
    posture: FencePosture,
) -> str:
    """Build the SHA256 cache key from the input tuple.

    The key is a hex SHA256 of the pipe-joined tuple.  Any change to
    any input changes the key deterministically; there is no second
    chance to be ambiguous.  The posture is in the key so
    REPORT / FENCE / GATE invocations on the same board do not share
    a cache entry — they are semantically different measurements.
    """
    payload = (
        f"{router_commit}|{board_hash}|{kicad_cli_version}|"
        f"{design_rule_set_hash}|{posture.value}"
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class DrcCache:
    """Hash-keyed DRC regression cache.

    Wraps :func:`temper_placer.validation.drc_runner.run_drc` with a
    content-addressed cache.  The first run with a given input tuple
    is a miss; subsequent runs are hits.  ``UNVERIFIED`` results are
    never cached.

    Args:
        cache_dir: Directory for cached ``drcc.v1.json`` artifacts.
            Defaults to ``~/.cache/temper/drc``.  Created on first
            write if it does not exist; a missing directory on read
            is treated as a cache miss.
    """

    def __init__(self, cache_dir: Path | None = None) -> None:
        self.cache_dir = cache_dir if cache_dir is not None else DEFAULT_CACHE_DIR

    def _cache_file(self, key: str) -> Path:
        return self.cache_dir / f"{key}.json"

    def get_or_run(
        self,
        pcb_path: Path,
        *,
        posture: FencePosture,
        router_commit: str = "",
        board_hash: str | None = None,
        kicad_cli_version: str | None = None,
        design_rule_set_hash: str | None = None,
        repo_root: Path | None = None,
    ) -> DrcResult:
        """Cache-aware wrapper around ``run_drc``.

        Computes the cache key from the input tuple (defaulting any
        missing provenance via :func:`compute_provenance`), checks
        the cache, and falls through to ``run_drc`` on a miss.  On
        a hit, parses the stored ``drcc.v1.json`` artifact and
        returns the ``DrcResult`` with ``cache_hit=True``.

        ``UNVERIFIED`` results (kicad-cli missing or errored) are
        never cached: the function returns the result with
        ``cache_hit=False`` regardless of the cache state.  This
        keeps the cache deterministic — the next run with the same
        inputs is a miss, not a hit on "we don't know".

        Args:
            pcb_path: Path to the .kicad_pcb file.
            posture: FencePosture (GATE / FENCE / REPORT).  The
                posture is part of the cache key.
            router_commit: ``git rev-parse HEAD`` of the router.
                Empty string when not a git repo.
            board_hash: SHA256 of pcb_path content.  Computed from
                pcb_path when not provided.
            kicad_cli_version: ``kicad-cli version`` first line.
                Computed when not provided.
            design_rule_set_hash: SHA256 of the .kicad_dru file, or
                the empty-string hash when no companion file exists.
                Computed when not provided.
            repo_root: Repo root for ``git rev-parse HEAD`` and
                design rule set lookup.  Defaults to ``Path.cwd()``.

        Returns:
            ``DrcResult`` with ``cache_hit`` reflecting whether the
            result was served from the cache.
        """
        # Compute any missing provenance values from the PCB file.
        if (
            board_hash is None
            or kicad_cli_version is None
            or design_rule_set_hash is None
        ):
            prov = compute_provenance(pcb_path, repo_root=repo_root)
            board_hash = board_hash if board_hash is not None else prov["board_hash"]
            kicad_cli_version = (
                kicad_cli_version
                if kicad_cli_version is not None
                else prov["kicad_cli_version"]
            )
            design_rule_set_hash = (
                design_rule_set_hash
                if design_rule_set_hash is not None
                else prov["design_rule_set_hash"]
            )

        key = make_cache_key(
            router_commit=router_commit,
            board_hash=board_hash or "",
            kicad_cli_version=kicad_cli_version or "",
            design_rule_set_hash=design_rule_set_hash or "",
            posture=posture,
        )
        cache_file = self._cache_file(key)

        # Cache hit: parse the stored artifact and return.
        if cache_file.exists():
            try:
                data: dict[str, Any] = json.loads(cache_file.read_text())
                result, _, _ = from_drcc_v1(data)
                # Mark the result as served from cache.  This is the
                # signal downstream consumers use to distinguish a
                # fresh measurement from a cached one.
                return DrcResult(
                    error_count=result.error_count,
                    warning_count=result.warning_count,
                    errors=result.errors,
                    warnings=result.warnings,
                    drc_status=result.drc_status,
                    cache_hit=True,
                )
            except (json.JSONDecodeError, ValueError, OSError) as e:
                # Corrupt or unreadable cache entry: delete it and
                # fall through to a fresh run.  Cache is best-effort.
                _LOGGER.warning(
                    "DRC cache: corrupt entry at %s (%s); deleting and re-running",
                    cache_file,
                    e,
                )
                try:
                    cache_file.unlink()
                except OSError:
                    pass

        # Cache miss: run kicad-cli.
        result = run_drc(pcb_path, posture=posture)
        # UNVERIFIED is never cached.  Caching a missing measurement
        # is a memory leak; the next run must re-attempt the
        # measurement, not see a stale "we don't know".
        if result.drc_status is DrcStatus.UNVERIFIED:
            return result

        # Build the schema artifact and write to cache.  Cache write
        # is best-effort: a write failure is logged at INFO and the
        # function returns the result regardless.
        artifact = to_drcc_v1(
            result=result,
            fence_state=FenceState.FENCED,
            posture=posture,
            provenance={
                "board_hash": board_hash or "",
                "router_commit": router_commit,
                "kicad_cli_version": kicad_cli_version or "",
                "design_rule_set_hash": design_rule_set_hash or "",
            },
            cache_hit=False,
        )
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(json.dumps(artifact, indent=2))
        except OSError as e:
            _LOGGER.info(
                "DRC cache: failed to write %s (%s); cache is best-effort",
                cache_file,
                e,
            )
        return result

    def invalidate(self, key: str) -> None:
        """Delete a single cache entry by key.  Used by tests and by
        future rule-set-change detection.  A missing entry is
        silently ignored.
        """
        cache_file = self._cache_file(key)
        if cache_file.exists():
            try:
                cache_file.unlink()
            except OSError:
                pass

    def clear(self) -> int:
        """Delete all cache entries.  Returns the number of files
        removed.  A missing directory is treated as zero files.
        """
        if not self.cache_dir.exists():
            return 0
        n = 0
        for f in self.cache_dir.glob("*.json"):
            try:
                f.unlink()
                n += 1
            except OSError:
                pass
        return n
