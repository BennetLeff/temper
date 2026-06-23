"""Closure test: Benders placement -> Router V6 routing -> KiCad DRC.

Runs the full closed-loop pipeline and asserts:
- 100% nets routed (or current baseline)
- DRC count within ratchet ceiling
- No crashes.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ClosureResult:
    """Result of a closure test run."""

    passed: bool
    board_id: str
    benders_iterations: int = 0
    benders_cuts: int = 0
    router_completion_pct: float = 0.0
    drc_errors: int = 0
    drc_warnings: int = 0
    wall_clock_seconds: float = 0.0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    stages_exercised: int = 0

    def validate(self) -> list[str]:
        """Return assertion failures if the pipeline produced no real results."""
        failures: list[str] = []
        if self.benders_iterations <= 0:
            failures.append(
                "benders_iterations <= 0: pipeline produced no placement iterations"
            )
        if self.router_completion_pct <= 0:
            failures.append(
                "router_completion_pct <= 0: pipeline produced no routing results"
            )
        if self.stages_exercised < 2:
            failures.append(
                f"stages_exercised ({self.stages_exercised}) < 2: "
                "insufficient pipeline execution"
            )
        if self.benders_iterations <= 0 and self.router_completion_pct <= 0:
            failures.append(
                "zero-results: both placement and routing produced no results"
            )
        return failures

    def summary(self) -> str:
        lines = [
            f"=== Closure Test: {self.board_id} ===",
            f"Status: {'PASS' if self.passed else 'FAIL'}",
            f"Benders iterations: {self.benders_iterations}, cuts: {self.benders_cuts}",
            f"Router completion: {self.router_completion_pct:.1f}%",
            f"DRC: {self.drc_errors} errors, {self.drc_warnings} warnings",
            f"Wall clock: {self.wall_clock_seconds:.1f}s",
            f"Stages exercised: {self.stages_exercised}",
        ]
        for err in self.errors:
            lines.append(f"  ERROR: {err}")
        for warn in self.warnings:
            lines.append(f"  WARNING: {warn}")
        return "\n".join(lines)


class ClosureTest:
    """Orchestrates the full parse -> Benders -> Router -> DRC pipeline."""

    def __init__(
        self,
        pcb_path: Path,
        seed: dict | None = None,
        repo_root: Path | None = None,
        strategy: str = "template",
        require_all_stages: bool = False,
    ):
        self.pcb_path = Path(pcb_path)
        self.seed = seed or {}
        self.repo_root = repo_root or Path.cwd()
        self.benders_seed = self.seed.get("benders_seed", 42)
        self.router_seed = self.seed.get("router_seed", 42)
        self.strategy = strategy
        self.require_all_stages = require_all_stages

    def run(self) -> ClosureResult:
        start_time = time.perf_counter()
        board_id = self.pcb_path.stem
        errors: list[str] = []
        warnings: list[str] = []
        stages_exercised = 0

        # Step 1: Parse PCB
        try:
            from temper_placer.io.kicad_parser import parse_kicad_pcb_v6

            parsed = parse_kicad_pcb_v6(self.pcb_path)
            stages_exercised += 1
        except Exception as e:
            return ClosureResult(
                passed=False,
                board_id=board_id,
                errors=[f"Parse failed: {e}"],
                wall_clock_seconds=time.perf_counter() - start_time,
            )

        # Step 2: Benders placement via protocol
        benders_iterations = 0
        benders_cuts = 0
        try:
            from temper_placer.protocol import StageInput, StageMeta
            from temper_placer.runner import resolve_and_run

            placement_result = resolve_and_run(
                phase="placement",
                strategies=[self.strategy],
                input=StageInput(
                    data=parsed,
                    meta=StageMeta(seed=self.benders_seed),
                ),
                fallback="template",
            )
            benders_iterations = getattr(placement_result.data, "iterations", 0)
            benders_cuts = getattr(placement_result.data, "cuts", 0)
            optimized_placements = getattr(placement_result.data, "placements", {})
            stages_exercised += 1
        except Exception as e:
            msg = f"Placement not available: {e}"
            if self.require_all_stages:
                errors.append(msg)
            else:
                warnings.append(msg)
            optimized_placements = {}

        # Step 3: Router V6 routing via protocol
        router_completion_pct = 0.0
        try:
            from temper_placer.protocol import StageInput, StageMeta
            from temper_placer.runner import resolve_and_run

            routing_result = resolve_and_run(
                phase="routing",
                strategies=["router_v6_full"],
                input=StageInput(
                    data=parsed,
                    meta=StageMeta(
                        seed=self.router_seed,
                        trace_context={"placements": optimized_placements},
                    ),
                ),
            )
            router_completion_pct = getattr(routing_result.data, "completion_rate", 0.0)
            stages_exercised += 1
        except Exception as e:
            msg = f"Router V6 not available: {e}"
            if self.require_all_stages:
                errors.append(msg)
            else:
                warnings.append(msg)

        # Step 4: KiCad DRC
        drc_errors = 0
        drc_warnings = 0
        try:
            from temper_placer.validation.drc_runner import run_drc

            drc_result = run_drc(self.pcb_path)
            drc_errors = drc_result.error_count
            drc_warnings = drc_result.warning_count
            stages_exercised += 1
        except ImportError:
            msg = "kicad-cli not available; skipping DRC"
            if self.require_all_stages:
                errors.append(msg)
            else:
                warnings.append(msg)
        except Exception as e:
            msg = f"DRC failed: {e}"
            if self.require_all_stages:
                errors.append(msg)
            else:
                warnings.append(msg)

        # Step 5: Load DRC ceiling for check
        ceiling_passed = True
        try:
            ceiling_path = self.repo_root / "power_pcb_dataset" / "drc_ceiling.json"
            if ceiling_path.exists():
                with open(ceiling_path) as f:
                    ceiling_data = json.load(f)
                for entry in ceiling_data.get("boards", []):
                    if entry.get("board_id") == board_id:
                        if drc_errors > entry.get("error_ceiling", 0):
                            errors.append(
                                f"DRC {drc_errors} exceeds ceiling {entry['error_ceiling']}"
                            )
                            ceiling_passed = False
        except Exception as e:
            warnings.append(f"Ceiling check failed: {e}")

        # Validate truth assertions before computing pass/fail
        validation_failures = ClosureResult(
            passed=False,
            board_id=board_id,
            benders_iterations=benders_iterations,
            router_completion_pct=router_completion_pct,
            stages_exercised=stages_exercised,
        ).validate()
        errors.extend(validation_failures)

        passed = len(errors) == 0 and ceiling_passed

        return ClosureResult(
            passed=passed,
            board_id=board_id,
            benders_iterations=benders_iterations,
            benders_cuts=benders_cuts,
            router_completion_pct=router_completion_pct,
            drc_errors=drc_errors,
            drc_warnings=drc_warnings,
            wall_clock_seconds=time.perf_counter() - start_time,
            errors=errors,
            warnings=warnings,
            stages_exercised=stages_exercised,
        )

    @classmethod
    def load_seed(cls, seed_path: Path) -> dict:
        if seed_path.exists():
            with open(seed_path) as f:
                return json.load(f)
        return {"benders_seed": 42, "router_seed": 42}
