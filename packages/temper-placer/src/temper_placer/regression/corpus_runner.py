"""Corpus regression runner.

Runs the full optimizer on each corpus board and compares placement
quality metrics against version-controlled baselines.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


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

    def __init__(self, corpus_root: Path):
        self.corpus_root = corpus_root
        manifest_path = corpus_root / "manifest.yaml"
        self.manifest = CorpusManifest.load(manifest_path)

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
            result = self._run_board(entry)
            results.append(result)

        if json_output:
            self._print_json_report(results)

        self._print_summary(results)

        return 1 if any(r.failed for r in results) else 0

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

        # Load baseline
        try:
            baseline = BaselineFile.load(baseline_path)
        except Exception as e:
            return CorpusBoardResult(
                board_id=board_id,
                passed=False,
                skipped=True,
                skip_reason=f"Failed to load baseline: {e}",
            )

        import time

        start_time = time.time()

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

        try:
            # Load constraints and board
            from temper_placer.io.config_loader import load_constraints, create_board_from_constraints
            constraints = load_constraints(constraints_path)
            board = create_board_from_constraints(constraints)
        except Exception as e:
            return CorpusBoardResult(
                board_id=board_id,
                passed=False,
                errors=[f"Failed to load constraints: {e}"],
            )

        try:
            # Build loss function
            from temper_placer.losses.base import LossContext, CompositeLoss, WeightedLoss
            from temper_placer.losses.overlap import OverlapLoss
            from temper_placer.losses.wirelength import WirelengthLoss
            from temper_placer.losses.boundary import BoundaryLoss
            from temper_placer.losses.regularization import SpreadLoss

            weights = {
                "overlap": 200.0,
                "boundary": 100.0,
                "wirelength": 20.0,
                "spread": 5.0,
            }
            if constraints.losses is not None:
                config_weights = constraints.losses.get_weights()
                for k in weights:
                    if k in config_weights:
                        weights[k] = config_weights[k]

            def make_loss(w):
                return CompositeLoss([
                    WeightedLoss(OverlapLoss(margin=1.0, rotation_invariant=True), w["overlap"]),
                    WeightedLoss(BoundaryLoss(), w["boundary"]),
                    WeightedLoss(WirelengthLoss(), w["wirelength"]),
                    WeightedLoss(SpreadLoss(), w.get("spread", 5.0)),
                ])

            context = LossContext.from_netlist_and_board(netlist, board)

            # Build optimizer config
            from temper_placer.optimizer.config import OptimizerConfig
            from temper_placer.optimizer.curriculum import create_default_phases
            from temper_placer.optimizer.train import train_multiphase
            from temper_placer.heuristics import create_default_pipeline

            pipeline = create_default_pipeline()
            rng_key = __import__("jax").random.PRNGKey(entry.seed)
            preset = pipeline.run(board, netlist, constraints, rng_key)
            initial_state = preset.state

            # Guard against degenerate initial placements (NaN positions,
            # extreme rotations) that cause NaN gradients at epoch 0.
            # Small boards with few components are especially prone.
            pos = initial_state.positions
            if not __import__("jax").numpy.all(__import__("jax").numpy.isfinite(pos)):
                import jax.numpy as jnp
                # Fall back to uniform random within board bounds
                ox, oy = board.origin
                k1, k2 = __import__("jax").random.split(rng_key)
                margin = min(2.0, board.width * 0.1, board.height * 0.1)
                px = __import__("jax").random.uniform(
                    k1, (netlist.n_components,),
                    minval=ox + margin,
                    maxval=ox + board.width - margin,
                )
                py = __import__("jax").random.uniform(
                    k2, (netlist.n_components,),
                    minval=oy + margin,
                    maxval=oy + board.height - margin,
                )
                from dataclasses import replace as dc_replace
                initial_state = dc_replace(
                    initial_state,
                    positions=jnp.stack([px, py], axis=-1),
                    rotation_logits=jnp.zeros_like(initial_state.rotation_logits),
                )

            phases = create_default_phases(entry.epochs)
            cfg = OptimizerConfig(
                epochs=entry.epochs,
                seed=entry.seed,
                log_interval=max(1, entry.epochs // 100),
                curriculum_phases=phases,
                use_centrality_weighting=False,
            )
        except Exception as e:
            return CorpusBoardResult(
                board_id=board_id,
                passed=False,
                errors=[f"Setup failed: {e}"],
            )

        # Run optimizer
        try:
            import jax
            jax.config.update("jax_platform_name", "cpu")

            result = train_multiphase(
                netlist, board, make_loss, context, cfg,
                initial_state=initial_state,
            )

            elapsed = time.time() - start_time

            # Compute final individual loss values from breakdown
            composite = make_loss(weights)
            # Softmax the rotation logits to get rotation probabilities.
            # Passing raw logits to loss functions (which expect soft one-hot
            # rotations from Gumbel-Softmax) causes massively inflated rotated
            # bounds and boundary loss values (observed: 250M vs actual ~0).
            rotations = __import__("jax").nn.softmax(
                result.final_state.rotation_logits, axis=-1
            )
            loss_result = composite(
                result.final_state.positions,
                rotations,
                context,
            )
            breakdown = loss_result.breakdown if loss_result.breakdown else {}

            overlap_val = float(breakdown.get("overlap", 0.0))
            wirelength_val = float(breakdown.get("wirelength", 0.0))
            boundary_val = float(breakdown.get("boundary", 0.0))
            final_loss_val = float(result.final_loss)

            hpwl_val = 0.0
            try:
                from temper_placer.losses.wirelength import compute_hpwl
                hpwl_val = float(compute_hpwl(result.final_state, netlist))
            except Exception:
                pass

            collected = {
                "overlap_loss_final": overlap_val,
                "wirelength_final": wirelength_val,
                "boundary_loss_final": boundary_val,
                "final_loss": final_loss_val,
                "hpwl_final": hpwl_val,
            }
        except Exception as e:
            err_msg = str(e)
            # NaN at epoch 0 often means the initial placement is degenerate.
            # Retry once with random positions as a fallback.
            if "Non-finite" in err_msg and "epoch 0" in err_msg:
                import jax
                import jax.numpy as jnp
                k1, k2 = jax.random.split(rng_key)
                margin = min(2.0, board.width * 0.1, board.height * 0.1)
                ox, oy = board.origin
                px = jax.random.uniform(
                    k1, (netlist.n_components,),
                    minval=ox + margin, maxval=ox + board.width - margin)
                py = jax.random.uniform(
                    k2, (netlist.n_components,),
                    minval=oy + margin, maxval=oy + board.height - margin)
                rng_key = jax.random.split(k2)[0]
                initial_state = initial_state._replace(
                    positions=jnp.stack([px, py], axis=-1),
                    rotation_logits=jnp.zeros_like(initial_state.rotation_logits),
                )
                try:
                    result = train_multiphase(
                        netlist, board, make_loss, context, cfg,
                        initial_state=initial_state,
                    )
                except Exception as e2:
                    return CorpusBoardResult(
                        board_id=board_id,
                        passed=False,
                        errors=[f"Optimization failed (retry): {e2}"],
                    )
            else:
                return CorpusBoardResult(
                    board_id=board_id,
                    passed=False,
                    errors=[f"Optimization failed: {e}"],
                )

        # Compare metrics
        metric_checks = []
        all_passed = True
        for name, actual in collected.items():
            spec = baseline.metrics.get(name)
            if spec is None:
                continue
            check = check_metric(name, actual, spec)
            metric_checks.append(check)
            if not check["passed"]:
                all_passed = False

        return CorpusBoardResult(
            board_id=board_id,
            passed=all_passed,
            metric_checks=metric_checks,
            elapsed_seconds=elapsed,
            metrics=collected,
        )

    def _print_summary(self, results: list[CorpusBoardResult]) -> None:
        passed = sum(1 for r in results if r.passed)
        failed = sum(1 for r in results if r.failed)
        skipped = sum(1 for r in results if r.skipped)

        print(f"\n=== Corpus Regression Results ===")
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
        report = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "boards": [],
        }
        for result in results:
            report["boards"].append({
                "board_id": result.board_id,
                "passed": result.passed,
                "skipped": result.skipped,
                "skip_reason": result.skip_reason if result.skipped else None,
                "elapsed_seconds": result.elapsed_seconds,
                "metrics": result.metrics,
                "metric_checks": result.metric_checks,
                "errors": result.errors,
                "warnings": result.warnings,
            })
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2)
        print(f"Regression report written to {report_path}", file=sys.stderr)
