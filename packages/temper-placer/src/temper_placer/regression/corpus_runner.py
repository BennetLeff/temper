"""Corpus regression runner (optimizer path retired).

The JAX optimizer that drove per-board optimization was removed in the
JAX retirement. ``_run_board`` still validates corpus inputs (paths,
baseline well-formedness, zero-component guard) but the optimization and
metric-comparison step is retired: a fully-valid board gets a clear
"retired" error until the runner is rewired to the CP-SAT/deterministic
placer (tracked follow-up).
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]


@dataclass
class CorpusEntry:
    """A single corpus board entry from manifest.yaml."""

    id: str
    pcb: str
    constraints: str
    baseline: str
    seed: int
    epochs: int
    description: str = ""

    def pcb_path(self, corpus_root: Path) -> Path:
        return corpus_root / self.pcb

    def constraints_path(self, corpus_root: Path) -> Path:
        return corpus_root / self.constraints

    def baseline_path(self, corpus_root: Path) -> Path:
        return corpus_root / self.baseline


@dataclass
class BaselineSpec:
    """A single metric baseline with tolerance margins."""

    mean: float
    margin_rel: float = 0.05
    margin_abs: float = 0.0

    @classmethod
    def from_dict(cls, data: dict) -> BaselineSpec:
        return cls(
            mean=float(data["mean"]),
            margin_rel=float(data.get("margin_rel", 0.05)),
            margin_abs=float(data.get("margin_abs", 0.0)),
        )

    def allowed_delta(self) -> float:
        return max(self.mean * self.margin_rel, self.margin_abs)

    def limit(self) -> float:
        return self.mean + self.allowed_delta()


@dataclass
class BaselineFile:
    """Loaded baseline.json with validated structure."""

    board_id: str
    extracted_at: str
    git_hash: str
    config: dict[str, Any]
    metrics: dict[str, BaselineSpec]

    @classmethod
    def load(cls, path: Path) -> BaselineFile:
        with open(path) as f:
            data = json.load(f)

        metrics = {}
        for name, spec in data.get("metrics", {}).items():
            if isinstance(spec, dict):
                metrics[name] = BaselineSpec.from_dict(spec)

        return cls(
            board_id=data.get("board_id", ""),
            extracted_at=data.get("extracted_at", ""),
            git_hash=data.get("git_hash", ""),
            config=data.get("config", {}),
            metrics=metrics,
        )


@dataclass
class CorpusBoardResult:
    """Result of a single corpus board optimization and comparison."""

    board_id: str
    passed: bool
    skipped: bool = False
    skip_reason: str = ""
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metric_checks: list[dict[str, Any]] = field(default_factory=list)
    elapsed_seconds: float = 0.0
    metrics: dict[str, float] = field(default_factory=dict)

    @property
    def failed(self) -> bool:
        return not self.passed and not self.skipped


def check_metric(name: str, actual: float, baseline: BaselineSpec) -> dict[str, Any]:
    """Threshold-aware comparison against baseline spec.

    Returns dict with 'passed', 'name', 'actual', 'baseline', 'limit', 'delta'.
    Lower is better for all placement metrics. Regression means actual > limit.
    """
    limit = baseline.limit()
    passed = actual <= limit
    return {
        "name": name,
        "passed": passed,
        "actual": actual,
        "baseline": baseline.mean,
        "limit": limit,
        "delta": actual - baseline.mean,
        "allowed_delta": baseline.allowed_delta(),
    }


@dataclass
class CorpusManifest:
    """Loaded corpus manifest.yaml."""

    version: int = 1
    boards: list[CorpusEntry] = field(default_factory=list)

    @classmethod
    def load(cls, manifest_path: Path) -> CorpusManifest:
        if not manifest_path.exists():
            raise FileNotFoundError(f"Corpus manifest not found: {manifest_path}")

        with open(manifest_path) as f:
            data = yaml.safe_load(f)

        if data is None:
            return cls(version=1, boards=[])

        boards = [
            CorpusEntry(
                id=entry["id"],
                pcb=entry["pcb"],
                constraints=entry["constraints"],
                baseline=entry["baseline"],
                seed=entry.get("seed", 42),
                epochs=entry.get("epochs", 8000),
                description=entry.get("description", ""),
            )
            for entry in data.get("boards", [])
        ]

        return cls(version=data.get("version", 1), boards=boards)

    def get_board(self, board_id: str) -> CorpusEntry | None:
        for b in self.boards:
            if b.id == board_id:
                return b
        return None


class CorpusRegressionRunner:
    """Runs optimizer-based regression on corpus boards."""

    def __init__(
        self,
        corpus_root: Path,
        repo_root: Path | None = None,
        skip_unchanged: bool = False,
    ):
        self.corpus_root = corpus_root
        manifest_path = corpus_root / "manifest.yaml"
        self.manifest = CorpusManifest.load(manifest_path)
        self.skip_unchanged = skip_unchanged
        self._repo_root = repo_root or self._find_repo_root()
        self._source_fingerprint: str | None = None
        self._cache: dict | None = None

        if skip_unchanged:
            from temper_placer.regression.fingerprint import (
                compute_source_fingerprint,
                load_cache,
            )

            self._source_fingerprint = compute_source_fingerprint(self._repo_root)
            self._cache = load_cache(corpus_root)

    @staticmethod
    def _find_repo_root() -> Path:
        p = Path.cwd()
        while not (p / ".git").exists() and p != p.parent:
            p = p.parent
        return p

    def run(
        self,
        boards: list[str] | None = None,
        json_output: bool = False,
    ) -> int:
        """Run regression on all or selected boards.

        Returns exit code (0 = all pass, 1 = failures).
        """
        results: list[CorpusBoardResult] = []

        for entry in self.manifest.boards:
            if boards and entry.id not in boards:
                continue

            if self._should_skip_board(entry):
                results.append(
                    CorpusBoardResult(
                        board_id=entry.id,
                        passed=True,
                        skipped=True,
                        skip_reason="Inputs unchanged since last green run",
                    )
                )
                continue

            result = self._run_board(entry)
            results.append(result)

        if json_output:
            self._print_json_report(results)

        self._print_summary(results)

        return 1 if any(r.failed for r in results) else 0

    def _should_skip_board(self, entry: CorpusEntry) -> bool:
        if not self.skip_unchanged or self._cache is None:
            return False
        from temper_placer.regression.fingerprint import (
            compute_input_fingerprint,
            should_skip,
        )

        input_fp = compute_input_fingerprint(
            entry.pcb_path(self.corpus_root),
            entry.constraints_path(self.corpus_root),
            entry.baseline_path(self.corpus_root),
            manifest_seed=entry.seed,
            manifest_epochs=entry.epochs,
        )
        return should_skip(
            entry.id,
            input_fp,
            self._source_fingerprint or "",
            self._cache,
        )

    def _run_board(self, entry: CorpusEntry) -> CorpusBoardResult:
        board_id = entry.id
        pcb_path = entry.pcb_path(self.corpus_root)
        constraints_path = entry.constraints_path(self.corpus_root)
        baseline_path = entry.baseline_path(self.corpus_root)

        # Validate paths
        if not pcb_path.exists():
            return CorpusBoardResult(
                board_id=board_id,
                passed=False,
                skipped=True,
                skip_reason=f"PCB file not found: {pcb_path}",
            )
        if not constraints_path.exists():
            return CorpusBoardResult(
                board_id=board_id,
                passed=False,
                skipped=True,
                skip_reason=f"Constraints file not found: {constraints_path}",
            )
        if not baseline_path.exists():
            return CorpusBoardResult(
                board_id=board_id,
                passed=False,
                skipped=True,
                skip_reason=f"Baseline file not found: {baseline_path}",
            )

        # Load baseline: still validates corpus-input integrity even though
        # the metric comparison that consumed it was retired with the JAX
        # optimizer -- a corrupt baseline should skip, not crash.
        try:
            BaselineFile.load(baseline_path)
        except Exception as e:
            return CorpusBoardResult(
                board_id=board_id,
                passed=False,
                skipped=True,
                skip_reason=f"Failed to load baseline: {e}",
            )

        try:
            # Parse PCB
            from temper_placer.io.kicad_parser import parse_kicad_pcb

            parse_result = parse_kicad_pcb(pcb_path)
            netlist = parse_result.netlist
        except Exception as e:
            return CorpusBoardResult(
                board_id=board_id,
                passed=False,
                errors=[f"Failed to parse PCB: {e}"],
            )

        # Check for empty/minimal boards
        if netlist.n_components == 0:
            return CorpusBoardResult(
                board_id=board_id,
                passed=False,
                skipped=True,
                skip_reason="Board has zero components",
            )

        # The optimizer that drove corpus regression was retired with the JAX
        # migration: train_multiphase / create_default_phases and the JAX loss
        # classes (BoundaryLoss, OverlapLoss, SpreadLoss, WirelengthLoss) were
        # removed -- every board previously failed at setup with a
        # NotImplementedError from the removed optimizer. A fully-valid board
        # can no longer be optimized here; rewiring _run_board to the
        # CP-SAT/deterministic placer is a tracked follow-up (see the skipped
        # test_run_success_path reason in tests/regression/test_corpus_runner.py).
        return CorpusBoardResult(
            board_id=board_id,
            passed=False,
            errors=[
                "Corpus optimization retired with the JAX migration; "
                "_run_board needs rewiring to the CP-SAT/deterministic placer"
            ],
        )


    def _print_summary(self, results: list[CorpusBoardResult]) -> None:
        passed = sum(1 for r in results if r.passed)
        failed = sum(1 for r in results if r.failed)
        skipped = sum(1 for r in results if r.skipped)

        print("\n=== Corpus Regression Results ===")
        print(f"Total: {len(results)}, Passed: {passed}, Failed: {failed}, Skipped: {skipped}\n")

        for result in results:
            if result.skipped:
                print(f"  [SKIP] {result.board_id}: {result.skip_reason}")
            elif result.passed:
                print(f"  [PASS] {result.board_id} ({result.elapsed_seconds:.1f}s)")
            else:
                print(f"  [FAIL] {result.board_id} ({result.elapsed_seconds:.1f}s)")
                for check in result.metric_checks:
                    if not check["passed"]:
                        print(
                            f"         {check['name']}: {check['actual']:.2f} > "
                            f"limit {check['limit']:.2f} "
                            f"(baseline {check['baseline']:.2f} + {check['allowed_delta']:.2f})"
                        )
                for err in result.errors:
                    print(f"         ERROR: {err}")

    def _print_json_report(self, results: list[CorpusBoardResult]) -> None:
        report_path = Path("regression-report.json")
        report: dict = {
            "timestamp": datetime.now(UTC).isoformat(),
            "boards": [],
        }
        for result in results:
            report["boards"].append(
                {
                    "board_id": result.board_id,
                    "passed": result.passed,
                    "skipped": result.skipped,
                    "skip_reason": result.skip_reason if result.skipped else None,
                    "elapsed_seconds": result.elapsed_seconds,
                    "metrics": result.metrics,
                    "metric_checks": result.metric_checks,
                    "errors": result.errors,
                    "warnings": result.warnings,
                }
            )
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2)
        print(f"Regression report written to {report_path}", file=sys.stderr)
