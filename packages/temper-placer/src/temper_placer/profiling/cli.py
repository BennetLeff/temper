"""temper profile CLI — per-module performance profiling.

Commands:
    temper profile run   Profile one or all modules (pipeline, loss-fn, router-bench).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click  # type: ignore[import-untyped]

from temper_placer.profiling import (
    profile_loss_functions,
    profile_pipeline,
    profile_router_benchmark,
)
from temper_placer.regression.metrics_recorder import record_metrics


@click.group()
def profile():
    """Performance profiling harness — run per-module profiling and emit PipelineMetricsRecord output."""
    pass


@profile.command("run")
@click.option(
    "--module", "-m",
    required=True,
    type=click.Choice(["pipeline", "loss-fn", "router-bench", "all"]),
    help="Profiling module to run",
)
@click.option(
    "--board", "-b",
    default="temper",
    help="Board ID for pipeline and loss-fn profiling",
)
@click.option(
    "--commit",
    default="",
    help="Git commit hash for the record",
)
@click.option(
    "--output-jsonl",
    default=None,
    type=click.Path(path_type=Path),
    help="Append records to a JSONL file",
)
@click.option(
    "--json", "json_output",
    is_flag=True,
    default=False,
    help="Output NDJSON records to stdout",
)
def profile_run(
    module: str,
    board: str,
    commit: str,
    output_jsonl: Path | None,
    json_output: bool,
):
    """Run per-module profiling and emit PipelineMetricsRecord output.

    Outputs NDJSON (one JSON object per line) to stdout when --json is set,
    or appends to a JSONL file when --output-jsonl is set.
    """
    all_records: list[dict] = []

    if module in ("pipeline", "all"):
        all_records.extend(profile_pipeline(board, commit))

    if module in ("loss-fn", "all"):
        all_records.extend(profile_loss_functions(board, commit))

    if module in ("router-bench", "all"):
        all_records.extend(profile_router_benchmark(commit))

    if output_jsonl:
        from temper_placer.regression.metrics_recorder import (
            PipelineMetricsRecord,
            find_metrics_file,
        )
        for rec_dict in all_records:
            rec = PipelineMetricsRecord(**rec_dict)
            record_metrics(rec, output_jsonl)
        print(f"Appended {len(all_records)} records to {output_jsonl}", file=sys.stderr)

    if json_output:
        for rec_dict in all_records:
            print(json.dumps(rec_dict))

    if not json_output and not output_jsonl:
        # No output mode selected — print summary to stderr
        print(f"Profiled {len(all_records)} records (pass --json or --output-jsonl)", file=sys.stderr)
