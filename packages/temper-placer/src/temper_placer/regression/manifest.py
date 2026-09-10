"""Golden manifest loader and validator.

Loads golden_manifest.yaml which declares each golden board for
the regression suite. The manifest is manually reviewed (B4) and
never auto-updated by automation.

This module is a delegation shim. The path-set compute moved to
``temper-io-types``'s ``manifest`` module (Wave-4 tail-tooling migration):
``resolve_path`` (``repo_root / board.path``), ``baseline_yaml_path`` and
``baseline_pcb_path`` (the ``power_pcb_dataset/baselines`` rules), and the
per-board missing-PCB check + error-message construction of ``validate``.
The YAML ingestion stays here — ``GoldenManifest.load`` (``yaml.safe_load``,
the same Python-YAML boundary ``reference_aliases`` keeps), the
``validate`` ``mkdir`` side effect, and the ``get_board`` linear lookup
(trivial membership orchestration). The public API is unchanged. The
pre-migration module is pinned VERBATIM as
``tests/regression/_manifest_py_oracle.py`` (content-hash registered in
``scripts/oracle_hashes.json``); bit-identical parity is pinned by
``tests/regression/test_manifest_rust_differential.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import temper_io_types as _tio
import yaml  # type: ignore[import-untyped]


@dataclass
class GoldenBoard:
    """A single golden board entry in the regression manifest."""

    id: str
    path: str
    component_count: int
    net_count: int
    baseline_git_hash: str
    description: str = ""

    def resolve_path(self, repo_root: Path) -> Path:
        return Path(_tio.resolve_board_path_py(str(repo_root), self.path))

    def baseline_yaml_path(self, repo_root: Path) -> Path:
        return Path(_tio.baseline_yaml_path_py(str(repo_root), self.id))

    def baseline_pcb_path(self, repo_root: Path) -> Path:
        return Path(_tio.baseline_pcb_path_py(str(repo_root), self.id))


@dataclass
class GoldenManifest:
    """Full golden manifest loaded from golden_manifest.yaml."""

    version: int = 1
    boards: list[GoldenBoard] = field(default_factory=list)

    @classmethod
    def load(cls, manifest_path: Path) -> GoldenManifest:
        with open(manifest_path) as f:
            data = yaml.safe_load(f)

        if data is None:
            return cls(version=1, boards=[])

        boards = []
        for entry in data.get("boards", []):
            boards.append(
                GoldenBoard(
                    id=entry["id"],
                    path=entry["path"],
                    component_count=entry.get("component_count", 0),
                    net_count=entry.get("net_count", 0),
                    baseline_git_hash=entry.get("baseline_git_hash", "unknown"),
                    description=entry.get("description", ""),
                )
            )

        return cls(version=data.get("version", 1), boards=boards)

    def validate(self, repo_root: Path) -> list[str]:
        baselines_dir = repo_root / "power_pcb_dataset" / "baselines"
        baselines_dir.mkdir(parents=True, exist_ok=True)

        return _tio.validate_board_paths(
            str(repo_root), [(b.id, b.path) for b in self.boards]
        )

    def get_board(self, board_id: str) -> GoldenBoard | None:
        for b in self.boards:
            if b.id == board_id:
                return b
        return None
