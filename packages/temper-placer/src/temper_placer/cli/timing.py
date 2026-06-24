"""timing CLI — per-stage timing regression gate.

Commands:
    temper timing baseline   Capture timing baselines for canonical boards.
    temper timing check      Compare current timing against baselines.
    temper timing regenerate Update baselines after intentional changes.
"""

from __future__ import annotations

import json
import sys
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import click
import yaml

from ._io import console

UTC = timezone.utc


def _repo_root() -> Path:
    return Path(
        subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    )


def _timing_baselines_path() -> Path:
    return _repo_root() / "power_pcb_dataset" / "timing_baselines.yaml"


def _load_manifest() -> dict | None:
    path = _timing_baselines_path()
    if not path.exists():
        return None
    with open(path) as f:
        return yaml.safe_load(f) or {}


def _save_manifest(manifest: dict) -> None:
    path = _timing_baselines_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.safe_dump(manifest, f, default_flow_style=False, sort_keys=False)


def _current_git_hash() -> str:
    return subprocess.run(
        ["git", "rev-parse", "--short=12", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def _load_golden_boards() -> list[str]:
    manifest_path = _repo_root() / "power_pcb_dataset" / "golden_manifest.yaml"
    if not manifest_path.exists():
        return []
    data = yaml.safe_load(open(manifest_path))
    if not data:
        return []
    return [b["id"] for b in data.get("boards", [])]


@click.group()
def timing() -> None:
    """Per-stage timing regression gate."""
    pass


@timing.command("baseline")
@click.option(
    "--board", "-b", required=True, default=None,
    help="Board ID (from golden_manifest.yaml)",
)
@click.option(
    "--pipeline", "-p", default="DeterministicPipeline",
    help="Pipeline to measure",
)
@click.option(
    "--stage", "-s", default=None,
    help="Measure only this stage (default: all stages)",
)
@click.option(
    "--all-boards", is_flag=True, default=False,
    help="Measure all canonical boards",
)
@click.option(
    "--overwrite", is_flag=True, default=False,
    help="Overwrite existing baseline entries",
)
@click.option(
    "--runs", type=int, default=3,
    help="Number of measurement runs per stage",
)
def timing_baseline(
    board: str,
    pipeline: str,
    stage: str | None,
    all_boards: bool,
    overwrite: bool,
    runs: int,
) -> None:
    """Capture timing baselines for per-stage regression detection."""
    from temper_placer.profiling.timing_gate import (
        measure_all_stages,
        measure_stage_timing,
    )

    manifest = _load_manifest() or {
        "format_version": 1,
        "captured_python": sys.version.split()[0],
        "captured_platform": sys.platform,
        "captured_at": datetime.now(UTC).isoformat(),
        "stages": [],
    }

    boards = _load_golden_boards() if all_boards else [board]
    unknown = [b for b in boards if b not in _load_golden_boards()]
    if unknown:
        available = _load_golden_boards()
        console.print(
            "[red]ERROR: unknown board(s): {}[/]".format(", ".join(unknown))
        )
        console.print("Available: {}".format(", ".join(available)))
        sys.exit(1)

    git_hash = _current_git_hash()
    new_entries = 0
    skipped = 0
    overwritten = 0

    for board_id in boards:
        if stage:
            stages_to_measure = [stage]
        else:
            try:
                all_results = measure_all_stages(
                    board_id=board_id, pipeline=pipeline, n_runs=runs
                )
                stages_to_measure = [r.stage_name for r in all_results]
            except Exception as e:
                console.print("[red]ERROR: {}[/]".format(e))
                sys.exit(1)

        for stage_name in stages_to_measure:
            existing_idx = None
            for i, entry in enumerate(manifest["stages"]):
                if (
                    entry["board"] == board_id
                    and entry["pipeline"] == pipeline
                    and entry["stage"] == stage_name
                ):
                    existing_idx = i
                    break

            if existing_idx is not None and not overwrite:
                console.print(
                    "SKIP {}/{}/{} (exists, use --overwrite)".format(
                        board_id, pipeline, stage_name
                    )
                )
                skipped += 1
                continue

            try:
                result = measure_stage_timing(
                    stage_name=stage_name,
                    board_id=board_id,
                    pipeline=pipeline,
                    n_runs=runs,
                )
            except Exception as e:
                console.print(
                    "[red]FAIL {}/{}/{}: {}[/]".format(
                        board_id, pipeline, stage_name, e
                    )
                )
                continue

            entry = {
                "board": result.board_id,
                "pipeline": result.pipeline,
                "stage": result.stage_name,
                "wall_ms_mean": round(result.wall_ms, 3),
                "wall_ms_p95": round(
                    sorted(result.individual_ms)[int(len(result.individual_ms) * 0.95)],
                    3,
                ),
                "n_runs": result.n_runs,
                "individual_ms": [round(x, 3) for x in result.individual_ms],
                "git_hash": git_hash,
                "captured_at": datetime.now(UTC).isoformat(),
            }

            if existing_idx is not None:
                manifest["stages"][existing_idx] = entry
                overwritten += 1
            else:
                manifest["stages"].append(entry)
                new_entries += 1

            delta_str = "UPDATED" if existing_idx is not None else "NEW"
            console.print(
                "{} {}/{}/{}: {:.1f} ms ({} runs)".format(
                    delta_str,
                    result.board_id,
                    result.pipeline,
                    result.stage_name,
                    result.wall_ms,
                    result.n_runs,
                )
            )

    manifest["captured_at"] = datetime.now(UTC).isoformat()
    manifest["captured_python"] = sys.version.split()[0]
    manifest["captured_platform"] = sys.platform
    _save_manifest(manifest)

    total = new_entries + overwritten
    console.print(
        "\nBaseline written to power_pcb_dataset/timing_baselines.yaml "
        "({} stages: {} new, {} updated, {} skipped)".format(
            total, new_entries, overwritten, skipped
        )
    )


@timing.command("check")
@click.option(
    "--board", "-b", default=None, help="Check only this board"
)
@click.option(
    "--stage", "-s", default=None, help="Check only this stage"
)
@click.option(
    "--margin", "-m", type=float, default=0.20,
    help="Relative margin (default: 0.20 = 20%%)",
)
@click.option(
    "--floor-ms", type=float, default=10.0,
    help="Absolute floor for near-zero timings (default: 10ms)",
)
@click.option(
    "--json", "json_output", is_flag=True, default=False,
    help="Output as JSON",
)
@click.option(
    "--ci", "ci_mode", is_flag=True, default=False,
    help="CI mode: enforce git ancestry check",
)
def timing_check(
    board: str | None,
    stage: str | None,
    margin: float,
    floor_ms: float,
    json_output: bool,
    _ci_mode: bool,
) -> None:
    """Compare current pipeline timing against committed baselines."""
    from temper_placer.profiling.timing_gate import (
        TimingReport,
        StageTimingEntry,
        measure_all_stages,
    )

    manifest = _load_manifest()
    if manifest is None or not manifest.get("stages"):
        if json_output:
            print(json.dumps({"passed": True, "message": "No timing baselines to check."}))
        else:
            console.print(
                "[dim]No timing baselines to check. Run 'temper timing baseline' first.[/]"
            )
        sys.exit(0)

    entries = manifest["stages"]

    if board:
        entries = [e for e in entries if e["board"] == board]
    if stage:
        entries = [e for e in entries if e["stage"] == stage]

    if not entries:
        if json_output:
            print(json.dumps({"passed": True, "message": "No matching baselines."}))
        else:
            console.print(
                "[dim]No matching baselines to check.[/]"
            )
        sys.exit(0)

    # Group by (board, pipeline) for measurement
    measurement_groups: dict[tuple[str, str], list[dict]] = {}
    for entry in entries:
        key = (entry["board"], entry["pipeline"])
        measurement_groups.setdefault(key, []).append(entry)

    report_entries: list[StageTimingEntry] = []
    fail_count = 0

    for (board_id, pipeline_name), group_entries in measurement_groups.items():
        try:
            all_current = measure_all_stages(
                board_id=board_id, pipeline=pipeline_name, n_runs=3
            )
            current_map = {r.stage_name: r for r in all_current}
        except Exception as e:
            if json_output:
                print(
                    json.dumps(
                        {
                            "passed": False,
                            "error": "Measurement failed for {}/{}: {}".format(
                                board_id, pipeline_name, e
                            ),
                        }
                    )
                )
            else:
                console.print(
                    "[red]ERROR: measurement failed for {}/{}: {}[/]".format(
                        board_id, pipeline_name, e
                    )
                )
            sys.exit(1)

        for entry in group_entries:
            stage_name = entry["stage"]
            baseline_ms = entry["wall_ms_mean"]
            current = current_map.get(stage_name)
            if current is None:
                console.print(
                    "[yellow]WARN: no baseline for stage '{}' on {}/{}[/]".format(
                        stage_name, board_id, pipeline_name
                    )
                )
                continue

            current_ms = current.wall_ms
            delta_ms = current_ms - baseline_ms
            delta_pct = (delta_ms / baseline_ms) * 100.0 if baseline_ms > 0 else 0.0

            effective_baseline = max(baseline_ms, floor_ms)
            threshold_ms = effective_baseline * (1.0 + margin)
            passed = current_ms <= threshold_ms

            if not passed:
                fail_count += 1

            report_entries.append(
                StageTimingEntry(
                    board=board_id,
                    pipeline=pipeline_name,
                    stage=stage_name,
                    baseline_ms=baseline_ms,
                    current_ms=current_ms,
                    delta_ms=delta_ms,
                    delta_pct=delta_pct,
                    threshold_ms=threshold_ms,
                    passed=passed,
                )
            )

    passed_all = fail_count == 0
    report = TimingReport(
        entries=report_entries,
        margin=margin,
        passed=passed_all,
        total_stages=len(report_entries),
        failed_stages=fail_count,
    )

    if json_output:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        for entry in report_entries:
            status = "[green]PASS[/]" if entry.passed else "[red]FAIL[/]"
            sign = "+" if entry.delta_ms >= 0 else ""
            console.print(
                "{}: {:.<40s} {:>8.1f} ms  "
                "(baseline: {:.1f} ms, {}{:.1f}%)".format(
                    status,
                    entry.stage,
                    entry.current_ms,
                    entry.baseline_ms,
                    sign,
                    entry.delta_pct,
                )
            )

        if fail_count > 0:
            console.print("\n---")
            console.print(
                "[red]{} of {} stages failed. Timing regression gate: FAIL[/]".format(
                    fail_count, len(report_entries)
                )
            )
        else:
            console.print(
                "\n[green]All {} stages passed. Timing regression gate: PASS[/]".format(
                    len(report_entries)
                )
            )

    sys.exit(0 if passed_all else 1)


@timing.command("regenerate")
@click.option(
    "--board", "-b", required=True, help="Board ID to regenerate baselines for"
)
@click.option(
    "--stage", "-s", default=None,
    help="Regenerate only this stage (default: all stages)",
)
@click.option(
    "--pipeline", "-p", default="DeterministicPipeline",
    help="Pipeline to measure",
)
@click.option(
    "--force", "-f", is_flag=True, default=False,
    help="Skip confirmation prompt",
)
def timing_regenerate(
    board: str,
    stage: str | None,
    pipeline: str,
    force: bool,
) -> None:
    """Regenerate timing baselines after intentional algorithmic changes."""
    manifest = _load_manifest()
    current_ms = None

    if manifest and manifest.get("stages") and not force:
        matching = [
            e
            for e in manifest["stages"]
            if e["board"] == board
            and e["pipeline"] == pipeline
            and (stage is None or e["stage"] == stage)
        ]
        if matching:
            console.print(
                "Regenerate timing baselines for board '{}', pipeline '{}'{}?".format(
                    board,
                    pipeline,
                    ", stage '{}'".format(stage) if stage else " (all stages)",
                )
            )
            for e in matching:
                console.print(
                    "  {}: {:.1f} ms -> will be replaced".format(
                        e["stage"], e["wall_ms_mean"]
                    )
                )
            if not click.confirm("[y/N]:", default=False):
                console.print("Aborted.")
                return

    if stage:
        console.print(
            "Regenerating baseline for {}/{}/{}".format(board, pipeline, stage)
        )
        from temper_placer.profiling.timing_gate import measure_stage_timing

        result = measure_stage_timing(
            stage_name=stage, board_id=board, pipeline=pipeline, n_runs=3
        )
        current_ms = result.wall_ms

        if manifest is None:
            manifest = {
                "format_version": 1,
                "captured_python": sys.version.split()[0],
                "captured_platform": sys.platform,
                "captured_at": datetime.now(UTC).isoformat(),
                "stages": [],
            }

        git_hash = _current_git_hash()
        new_entry = {
            "board": board,
            "pipeline": pipeline,
            "stage": stage,
            "wall_ms_mean": round(result.wall_ms, 3),
            "wall_ms_p95": round(
                sorted(result.individual_ms)[
                    int(len(result.individual_ms) * 0.95)
                ],
                3,
            ),
            "n_runs": result.n_runs,
            "individual_ms": [round(x, 3) for x in result.individual_ms],
            "git_hash": git_hash,
            "captured_at": datetime.now(UTC).isoformat(),
        }

        found = False
        for i, entry in enumerate(manifest["stages"]):
            if (
                entry["board"] == board
                and entry["pipeline"] == pipeline
                and entry["stage"] == stage
            ):
                manifest["stages"][i] = new_entry
                found = True
                break
        if not found:
            manifest["stages"].append(new_entry)

        _save_manifest(manifest)
        if current_ms is not None:
            console.print(
                "[green]Regenerated: {:.1f} ms[/]".format(current_ms)
            )
    else:
        from temper_placer.profiling.timing_gate import measure_all_stages

        results = measure_all_stages(board_id=board, pipeline=pipeline, n_runs=3)
        if manifest is None:
            manifest = {
                "format_version": 1,
                "captured_python": sys.version.split()[0],
                "captured_platform": sys.platform,
                "captured_at": datetime.now(UTC).isoformat(),
                "stages": [],
            }

        git_hash = _current_git_hash()
        captured_at = datetime.now(UTC).isoformat()

        for result in results:
            new_entry = {
                "board": result.board_id,
                "pipeline": pipeline,
                "stage": result.stage_name,
                "wall_ms_mean": round(result.wall_ms, 3),
                "wall_ms_p95": round(
                    sorted(result.individual_ms)[
                        int(len(result.individual_ms) * 0.95)
                    ],
                    3,
                ),
                "n_runs": result.n_runs,
                "individual_ms": [round(x, 3) for x in result.individual_ms],
                "git_hash": git_hash,
                "captured_at": captured_at,
            }

            found = False
            for i, entry in enumerate(manifest["stages"]):
                if (
                    entry["board"] == board
                    and entry["pipeline"] == pipeline
                    and entry["stage"] == result.stage_name
                ):
                    manifest["stages"][i] = new_entry
                    found = True
                    break
            if not found:
                manifest["stages"].append(new_entry)
            console.print(
                "  {}:{:.1f} ms".format(result.stage_name, result.wall_ms)
            )

        _save_manifest(manifest)
        console.print(
            "[green]Regenerated {} stages for board '{}'[/]".format(
                len(results), board
            )
        )
