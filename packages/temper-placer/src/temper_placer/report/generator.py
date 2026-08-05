"""
Benchmark report generator for temper-placer.

This module provides functions to generate human-readable and machine-readable
reports comparing optimizer results against human baselines.

Wave 4, Phase 5: the numeric scoring kernel (``calculate_benchmark_result``)
and the JSON data shape (``generate_json_report``'s dict) now live in the
``temper-io-types`` Rust crate (``report.rs``); this module is a delegation
shim. The pre-migration implementation is pinned verbatim as
``tests/report/_generator_py_oracle.py`` and driven bit-identical by
``test_generator_rust_differential.py``. ``json.dump`` stays Python stdlib.
``generate_text_report`` stays Python: Rich console rendering is a library
semantic, not reimplementable (see ``temper-io-types/VERIFICATION.md``).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

import temper_io_types as _rust


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
    violations: list[str] = field(default_factory=list)


@dataclass
class BenchmarkSummary:
    """Aggregate summary of a benchmark run."""

    total_pcbs: int
    passed: int
    failed: int
    better_than_human: int
    results: list[BenchmarkResult] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


def calculate_benchmark_result(
    name: str,
    opt_result: Any,  # TrainingResult
    baseline: dict[str, Any],
    _context: Any,  # LossContext
) -> BenchmarkResult:
    """Compute quantitative scores comparing optimizer to baseline."""
    payload = _rust.report_calculate_benchmark_result(name, opt_result, baseline)
    return BenchmarkResult(**payload)


def generate_text_report(summary: BenchmarkSummary) -> str:
    """Generate a formatted text report using Rich."""
    console = Console(record=True, width=100)

    console.print(
        Panel.fit(
            f"[bold blue]TEMPER-PLACER BENCHMARK REPORT[/]\nGenerated: {summary.timestamp}",
            border_style="blue",
        )
    )

    # Summary Section
    table_sum = Table(title="Summary", show_header=False, padding=(0, 2))
    table_sum.add_row("Total PCBs tested", str(summary.total_pcbs))
    table_sum.add_row(
        "Passed", f"[green]{summary.passed}[/] ({summary.passed / summary.total_pcbs * 100:.0f}%)"
    )
    table_sum.add_row(
        "Failed", f"[red]{summary.failed}[/] ({summary.failed / summary.total_pcbs * 100:.0f}%)"
    )
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

        status_style = {"BETTER": "bold cyan", "PASS": "green", "FAIL": "red"}.get(
            res.status, "white"
        )

        table_res.add_row(
            res.name,
            drc_text,
            f"{res.wirelength_ratio:.2f}x",
            f"{res.thermal_score * 100:.0f}%",
            f"{res.compactness_score * 100:.0f}%",
            f"{res.overall_score * 100:.0f}%",
            f"[{status_style}]{res.status}[/]",
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
    data = _rust.report_benchmark_json_data(summary)
    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)
