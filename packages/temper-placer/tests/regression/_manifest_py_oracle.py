"""Pinned Python oracle for ``temper_placer/regression/manifest.py``.

VERBATIM copy of the pre-migration implementation of
``temper_placer/regression/manifest.py`` (as of ``origin/main`` commit
``2426f5cf5``, the Wave-4 tail-tooling migration base). Do NOT edit the
semantics: the differential suite
(``tests/regression/test_manifest_rust_differential.py``) compares the Rust
kernels (``temper-io-types`` ``manifest`` module) against this file
byte-for-byte, and its content hash is registered in
``scripts/oracle_hashes.json``. The migrated compute — the path-set rules
(``resolve_path`` / ``baseline_yaml_path`` / ``baseline_pcb_path``) and the
PCB-missing validation — stays here VERBATIM as evidence; the production
``manifest.py`` is now a delegation shim whose YAML ingestion
(``GoldenManifest.load``), the ``mkdir`` side effect and the
``get_board`` lookup remain Python.

Original module docstring (kept verbatim):
-----------------------------------------

Golden manifest loader and validator.

Loads golden_manifest.yaml which declares each golden board for
the regression suite. The manifest is manually reviewed (B4) and
never auto-updated by automation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

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
        return repo_root / self.path

    def baseline_yaml_path(self, repo_root: Path) -> Path:
        return repo_root / "power_pcb_dataset" / "baselines" / f"{self.id}_baseline.yaml"

    def baseline_pcb_path(self, repo_root: Path) -> Path:
        return repo_root / "power_pcb_dataset" / "baselines" / f"{self.id}.kicad_pcb"


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
        errors: list[str] = []
        baselines_dir = repo_root / "power_pcb_dataset" / "baselines"
        baselines_dir.mkdir(parents=True, exist_ok=True)

        for board in self.boards:
            pcb_path = board.resolve_path(repo_root)
            if not pcb_path.exists():
                errors.append(f"Board '{board.id}': PCB file not found at {pcb_path}")

        return errors

    def get_board(self, board_id: str) -> GoldenBoard | None:
        for b in self.boards:
            if b.id == board_id:
                return b
        return None
