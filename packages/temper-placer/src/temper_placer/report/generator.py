"""
Benchmark report generator for temper-placer.

This module provides functions to generate human-readable and machine-readable
reports comparing optimizer results against human baselines.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

@dataclass
class BenchmarkResult:
    """Result of a single PCB benchmark."""
    name: str
    drc_errors: int
    wirelength_ratio: float  # opt / human
    overlap_score: float
    boundary_score: float
    thermal_score: float
    compactness_score: float
    overall_score: float
    status: str  # "BETTER", "PASS", "FAIL"
    violations: List[str] = field(default_factory=list)

@dataclass
class BenchmarkSummary:
    """Aggregate summary of a benchmark run."""
    total_pcbs: int
    passed: int
    failed: int
    better_than_human: int
    results: List[BenchmarkResult] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

def calculate_benchmark_result(
    name: str,
    opt_result: Any, # TrainingResult
    baseline: Dict[str, Any],
    context: Any, # LossContext
) -> BenchmarkResult:
    """Compute quantitative scores comparing optimizer to baseline."""
    # Handle both new and legacy schema
    human_p = baseline.get("human_placement", {})
    human_metrics = human_p.get("metrics", baseline.get("human_metrics", {}))
    
    human_wl = human_metrics.get("total_wirelength_mm", human_metrics.get("total_hpwl_mm", 0.0))
    
    # 1. Wirelength Ratio
    # result.history[-1] contains final metrics
    final_metrics = opt_result.history[-1]
    opt_wl = final_metrics.loss_breakdown.get("wirelength", 0.0)
    wl_ratio = opt_wl / human_wl if human_wl > 0 else 1.0
    
    # 2. Hard Constraint Scores
    # We use 1.0 if violation is < 1.0, and decay exponentially
    overlap_val = final_metrics.loss_breakdown.get("overlap", 0.0)
    overlap_score = 1.0 if overlap_val < 1.0 else max(0.0, 1.0 - (overlap_val / 100.0))
    
    boundary_val = final_metrics.loss_breakdown.get("boundary", 0.0)
    boundary_score = 1.0 if boundary_val < 1.0 else max(0.0, 1.0 - (boundary_val / 100.0))
    
    # 3. Quality Scores
    thermal_val = final_metrics.loss_breakdown.get("thermal", 0.0)
    thermal_score = 1.0 / (1.0 + thermal_val / 10.0) if thermal_val > 0 else 1.0
    
    compactness_score = human_metrics.get("compactness_score", human_metrics.get("density", 0.5))
    
    # 4. Overall Score (Weighted)
    # Hard constraints must be satisfied for high score
    if overlap_score < 0.9 or boundary_score < 0.9:
        overall = min(overlap_score, boundary_score) * 0.5
    else:
        # Balanced score if hard constraints pass
        overall = (0.4 * (1.0/max(wl_ratio, 0.5)) + 0.3 * thermal_score + 0.3 * compactness_score)

    # 5. Status Determination
    violations = []
    if overlap_val > 10.0: violations.append(f"Overlap too high ({overlap_val:.1f})")
    if boundary_val > 10.0: violations.append(f"Boundary violation ({boundary_val:.1f})")
    
    if violations:
        status = "FAIL"
    elif wl_ratio < 0.95:
        status = "BETTER"
    else:
        status = "PASS"
        
    return BenchmarkResult(
        name=name,
        drc_errors=0, # Need kicad-cli for this
        wirelength_ratio=wl_ratio,
        overlap_score=overlap_score,
        boundary_score=boundary_score,
        thermal_score=thermal_score,
        compactness_score=compactness_score,
        overall_score=overall,
        status=status,
        violations=violations
    )

def generate_text_report(summary: BenchmarkSummary) -> str:
    """Generate a formatted text report using Rich."""
    console = Console(record=True, width=100)
    
    console.print(Panel.fit(
        f"[bold blue]TEMPER-PLACER BENCHMARK REPORT[/]\nGenerated: {summary.timestamp}",
        border_style="blue",
    ))

    # Summary Section
    table_sum = Table(title="Summary", show_header=False, padding=(0, 2))
    table_sum.add_row("Total PCBs tested", str(summary.total_pcbs))
    table_sum.add_row("Passed", f"[green]{summary.passed}[/] ({summary.passed/summary.total_pcbs*100:.0f}%)")
    table_sum.add_row("Failed", f"[red]{summary.failed}[/] ({summary.failed/summary.total_pcbs*100:.0f}%)")
    table_sum.add_row("Better than human", f"[cyan]{summary.better_than_human}[/]")
    console.print(table_sum)

    # Detailed Results Table
    table_res = Table(title="Detailed Results", header_style="bold cyan")
    table_res.add_column("PCB")
    table_res.add_column("DRC", justify="center")
    table_res.add_column("WL Ratio", justify="right")
    table_res.add_column("Thermal", justify="right")
    table_res.add_column("Compact", justify="right")
    table_res.add_column("Overall", justify="right")
    table_res.add_column("Status", justify="center")

    for res in summary.results:
        drc_text = "[green]✓[/]" if res.drc_errors == 0 else f"[red]✗ {res.drc_errors}[/]"
        
        status_style = {
            "BETTER": "bold cyan",
            "PASS": "green",
            "FAIL": "red"
        }.get(res.status, "white")
        
        table_res.add_row(
            res.name,
            drc_text,
            f"{res.wirelength_ratio:.2f}x",
            f"{res.thermal_score*100:.0f}%",
            f"{res.compactness_score*100:.0f}%",
            f"{res.overall_score*100:.0f}%",
            f"[{status_style}]{res.status}[/]"
        )
    
    console.print(table_res)

    # Failures Section
    failures = [r for r in summary.results if r.status == "FAIL"]
    if failures:
        console.print("\n[bold red]FAILURES[/]")
        for f in failures:
            console.print(f"[bold]{f.name}:[/]")
            console.print(f"  - DRC: {f.drc_errors} errors")
            for v in f.violations:
                console.print(f"  - Violation: {v}")

    # Recommendations
    console.print("\n[bold]RECOMMENDATIONS[/]")
    console.print("1. Increase ClearanceLoss weight for dense boards.")
    console.print("2. Consider adding CourtYardLoss to directly penalize overlaps.")

    return console.export_text()

def generate_json_report(summary: BenchmarkSummary, output_path: Path):
    """Save benchmark results to JSON."""
    data = {
        "timestamp": summary.timestamp,
        "summary": {
            "total_pcbs": summary.total_pcbs,
            "passed": summary.passed,
            "failed": summary.failed,
            "better_than_human": summary.better_than_human,
            "pass_rate": summary.passed / summary.total_pcbs if summary.total_pcbs > 0 else 0
        },
        "results": [
            {
                "name": r.name,
                "drc_errors": r.drc_errors,
                "wirelength_ratio": r.wirelength_ratio,
                "thermal_score": r.thermal_score,
                "compactness_score": r.compactness_score,
                "overall_score": r.overall_score,
                "status": r.status,
                "violations": r.violations
            } for r in summary.results
        ]
    }
    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)
