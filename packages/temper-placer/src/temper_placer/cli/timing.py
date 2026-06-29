"""timing CLI — per-stage timing regression gate.

Commands:
    temper timing baseline   Capture timing baselines for canonical boards.
    temper timing check      Compare current timing against baselines.
    temper timing regenerate Update baselines after intentional changes.
    temper timing tighten    Auto-lower stale baselines from JSONL trends.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import click
import yaml

from ._io import console

UTC = UTC


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
    data = yaml.safe_load(manifest_path.read_text())
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
@click.option(
    "--sub-steps", is_flag=True, default=False,
    help="Capture sub-step timings for stages that support them (e.g., RouterV6Pipeline stage2)",
)
def timing_baseline(
    board: str,
    pipeline: str,
    stage: str | None,
    all_boards: bool,
    overwrite: bool,
    runs: int,
    sub_steps: bool,
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
                    board_id=board_id, pipeline=pipeline, n_runs=runs,
                    sub_steps=sub_steps,
                )
                stages_to_measure = [r.stage_name for r in all_results]
            except Exception as e:
                console.print(f"[red]ERROR: {e}[/]")
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
                    f"SKIP {board_id}/{pipeline}/{stage_name} (exists, use --overwrite)"
                )
                skipped += 1
                continue

            try:
                result = measure_stage_timing(
                    stage_name=stage_name,
                    board_id=board_id,
                    pipeline=pipeline,
                    n_runs=runs,
                    sub_steps=sub_steps,
                )
            except Exception as e:
                console.print(
                    f"[red]FAIL {board_id}/{pipeline}/{stage_name}: {e}[/]"
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
                f"{delta_str} {result.board_id}/{result.pipeline}/{result.stage_name}: {result.wall_ms:.1f} ms ({result.n_runs} runs)"
            )

    manifest["captured_at"] = datetime.now(UTC).isoformat()
    manifest["captured_python"] = sys.version.split()[0]
    manifest["captured_platform"] = sys.platform
    _save_manifest(manifest)

    total = new_entries + overwritten
    console.print(
        "\nBaseline written to power_pcb_dataset/timing_baselines.yaml "
        f"({total} stages: {new_entries} new, {overwritten} updated, {skipped} skipped)"
    )


def _record_metrics(report_entries: list) -> None:
    """Record per-stage timing check results to pipeline_metrics.jsonl."""
    from temper_placer.regression.metrics_recorder import (
        find_metrics_file,
        record_metrics,
    )

    if not report_entries:
        return

    import contextlib

    metrics_path = find_metrics_file(_repo_root())
    for entry in report_entries:
        record = entry.to_pipeline_metrics_record()
        with contextlib.suppress(OSError):
            record_metrics(record, metrics_path)


def _check_git_ancestry(baseline_git_hash: str) -> bool:
    """Return True if baseline_git_hash is an ancestor of HEAD."""
    try:
        result = subprocess.run(
            ["git", "merge-base", "--is-ancestor", baseline_git_hash, "HEAD"],
            capture_output=True,
            text=True,
        )
        return result.returncode == 0
    except Exception:
        return False


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
    ci_mode: bool,
) -> None:
    """Compare current pipeline timing against committed baselines."""
    from temper_placer.profiling.timing_gate import (
        StageTimingEntry,
        TimingReport,
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

    # Platform/Python version mismatch check
    baseline_python = manifest.get("captured_python", "unknown")
    baseline_platform = manifest.get("captured_platform", "unknown")
    current_python = sys.version.split()[0]
    current_platform = sys.platform

    platform_mismatch = baseline_platform != current_platform
    python_mismatch = baseline_python != current_python

    if platform_mismatch or python_mismatch:
        msg = f"Platform/Python version mismatch: baseline={baseline_python}/{baseline_platform} current={current_python}/{current_platform}"
        if ci_mode:
            if json_output:
                print(
                    json.dumps(
                        {"passed": False, "error": f"Platform/Python mismatch: {msg}"}
                    )
                )
            else:
                console.print(f"[red]ERROR: {msg}[/]")
            sys.exit(1)
        else:
            if json_output:
                print(json.dumps({"warning": msg}), file=sys.stderr)
            else:
                console.print(f"[yellow]WARN: {msg}[/]")

    # Git ancestry check (R11) — always check, fail only in --ci mode
    orphan_entries: list[str] = []
    for entry in entries:
        baseline_hash = entry.get("git_hash", "")
        if baseline_hash and not _check_git_ancestry(baseline_hash):
            orphan_entries.append(
                "{}/{}/{} (baseline at {})".format(
                    entry["board"], entry["pipeline"], entry["stage"], baseline_hash
                )
            )

    if orphan_entries:
        msg = "ORPHAN_BASELINE: timing baseline(s) captured at commit(s) not ancestors of HEAD:\n"
        msg += "\n".join(f"  - {e}" for e in orphan_entries)
        msg += "\nRegenerate baselines in this branch."
        if ci_mode:
            if json_output:
                print(json.dumps({"passed": False, "error": msg}))
            else:
                console.print(f"[red]{msg}[/]")
            sys.exit(1)
        else:
            if json_output:
                print(json.dumps({"warning": msg}), file=sys.stderr)
            else:
                console.print(f"[yellow]WARN: {msg}[/]")

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
                            "error": f"Measurement failed for {board_id}/{pipeline_name}: {e}",
                        }
                    )
                )
            else:
                console.print(
                    f"[red]ERROR: measurement failed for {board_id}/{pipeline_name}: {e}[/]"
                )
            sys.exit(1)

        for entry in group_entries:
            stage_name = entry["stage"]
            baseline_ms = entry["wall_ms_mean"]
            current = current_map.get(stage_name)
            if current is None:
                console.print(
                    f"[yellow]WARN: no baseline for stage '{stage_name}' on {board_id}/{pipeline_name}[/]"
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

    # Record per-stage timing results to pipeline_metrics.jsonl for trend
    # detection and dashboard (Plan 010 integration)
    _record_metrics(report_entries)

    if json_output:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        for entry in report_entries:
            status = "[green]PASS[/]" if entry.passed else "[red]FAIL[/]"
            sign = "+" if entry.delta_ms >= 0 else ""
            console.print(
                f"{status}: {entry.stage:.<40s} {entry.current_ms:>8.1f} ms  "
                f"(baseline: {entry.baseline_ms:.1f} ms, {sign}{entry.delta_pct:.1f}%)"
            )

        if fail_count > 0:
            console.print("\n---")
            console.print(
                f"[red]{fail_count} of {len(report_entries)} stages failed. Timing regression gate: FAIL[/]"
            )
        else:
            console.print(
                f"\n[green]All {len(report_entries)} stages passed. Timing regression gate: PASS[/]"
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
                    f", stage '{stage}'" if stage else " (all stages)",
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
            f"Regenerating baseline for {board}/{pipeline}/{stage}"
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
                f"[green]Regenerated: {current_ms:.1f} ms[/]"
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
                f"  {result.stage_name}:{result.wall_ms:.1f} ms"
            )

        _save_manifest(manifest)
        console.print(
            f"[green]Regenerated {len(results)} stages for board '{board}'[/]"
        )


@timing.command("tighten")
@click.option("--board", "-b", default=None, help="Tighten only this board")
@click.option("--stage", "-s", default=None, help="Tighten only this stage")
@click.option(
    "--pipeline", "-p", default="DeterministicPipeline", help="Pipeline to check"
)
@click.option(
    "--n-runs", type=int, default=7, help="Consecutive runs required (default: 7)"
)
@click.option(
    "--threshold",
    "-t",
    type=float,
    default=0.50,
    help="Below-baseline ratio (default: 0.50 = 50%%)",
)
@click.option(
    "--noise-floor",
    type=float,
    default=10.0,
    help="Min baseline ms to consider (default: 10ms)",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Print proposed changes without writing",
)
@click.option(
    "--ci",
    "ci_mode",
    is_flag=True,
    default=False,
    help="CI mode: no prompts, exit 0 on success",
)
def timing_tighten(
    board: str | None,
    stage: str | None,
    pipeline: str,
    n_runs: int,
    threshold: float,
    noise_floor: float,
    dry_run: bool,
    ci_mode: bool,
) -> None:
    """Auto-lower stale timing baselines from pipeline_metrics.jsonl trends.  # R4,R5,R6

    Queries the committed JSONL time-series store for consecutive main-push
    runs where per-stage wall-clock has dropped consistently below the current
    baseline, then lowers the baseline to the median of those runs.
    """
    from rich.table import Table as RT

    from temper_placer.profiling.timing_gate import detect_tightenable_stages
    from temper_placer.regression.metrics_recorder import find_metrics_file

    # 1. Load manifest --------------------------------------------------------
    manifest = _load_manifest()
    if manifest is None or not manifest.get("stages"):
        if dry_run or ci_mode:
            console.print("[dim]No timing baselines to tighten.[/]")
            return
        console.print("[dim]No timing baselines to tighten.[/]")
        return

    # 2. Resolve JSONL path ---------------------------------------------------
    metrics_path = find_metrics_file(_repo_root())
    if not metrics_path.exists():
        if dry_run or ci_mode:
            console.print("[dim]No metrics data to analyze.[/]")
            return
        console.print("[dim]No metrics data to analyze.[/]")
        return

    # 3. Detect eligible stages -----------------------------------------------
    results = detect_tightenable_stages(
        jsonl_path=metrics_path,
        manifest=manifest,
        n_runs=n_runs,
        threshold=threshold,
        noise_floor=noise_floor,
        board_filter=board,
        stage_filter=stage,
        pipeline_filter=pipeline,
    )

    if not results:
        console.print("No stages eligible for tightening.")
        return

    # 4. Pretty-print results --------------------------------------------------
    pct_str = f"{threshold * 100:.0f}%"
    console.print(
        f"\nEligible stages for auto-tightening (threshold: {pct_str}, N={n_runs}):"
    )
    table = RT(show_header=True, header_style="bold")
    table.add_column("Board")
    table.add_column("Stage")
    table.add_column("Baseline", justify="right")
    table.add_column("Proposed", justify="right")
    table.add_column("Drop %", justify="right")
    table.add_column("Streak", justify="right")
    for r in results:
        table.add_row(
            r.board,
            r.stage,
            f"{r.baseline_ms:.1f} ms",
            f"{r.proposed_ms:.1f} ms",
            f"{r.drop_pct:.1f}%",
            str(r.streak_count),
        )
    console.print(table)

    # 5. Dry-run mode ---------------------------------------------------------
    if dry_run:
        console.print("[dim]Dry run — no changes written. Remove --dry-run to apply.[/]")
        return

    # 6. Confirmation (skip in CI mode) ---------------------------------------
    if not ci_mode and not click.confirm(
        "\nApply these baseline changes?",
        default=False,
    ):
        console.print("Aborted.")
        return

    # 7. Apply changes --------------------------------------------------------
    now_ts = datetime.now(UTC).isoformat()
    git_hash = _current_git_hash()
    tightened_count = 0

    for result in results:
        for i, entry in enumerate(manifest["stages"]):
            if (
                entry["board"] == result.board
                and entry.get("pipeline", pipeline) == result.pipeline
                and entry["stage"] == result.stage
            ):
                # Compute p95 of qualifying runs  # R5
                p95_ms = round(
                    sorted(result.qualifying_runs)[
                        int(len(result.qualifying_runs) * 0.95)
                    ],
                    3,
                ) if result.qualifying_runs else 0.0

                manifest["stages"][i] = {
                    "board": result.board,
                    "pipeline": result.pipeline,
                    "stage": result.stage,
                    "wall_ms_mean": round(result.proposed_ms, 3),
                    "wall_ms_p95": p95_ms,
                    "n_runs": n_runs,
                    "individual_ms": [round(x, 3) for x in result.qualifying_runs],
                    "git_hash": git_hash,
                    "captured_at": now_ts,
                    "tightened_from_ms": round(result.baseline_ms, 3),
                    "tightened_at": now_ts,
                    "tightened_n_runs": len(result.qualifying_runs),
                    "tightened_trigger_pct": round(threshold, 3),
                }
                tightened_count += 1
                break

    if tightened_count == 0:
        console.print("[dim]No manifest entries were updated.[/]")
        return

    manifest["captured_at"] = now_ts
    manifest["captured_python"] = sys.version.split()[0]
    manifest["captured_platform"] = sys.platform
    _save_manifest(manifest)

    console.print(f"\nTightening {tightened_count} stage(s):")
    for result in results:
        result.baseline_ms - result.proposed_ms
        console.print(
            "  {stage:.<40s} {old:.1f} ms {arrow} {new:.1f} ms   "
            "(-{pct:.1f}%, {streak}-run streak)".format(
                stage=result.stage,
                old=result.baseline_ms,
                arrow="→",
                new=result.proposed_ms,
                pct=result.drop_pct,
                streak=result.streak_count,
            )
        )
    console.print(
        "Baselines written to power_pcb_dataset/timing_baselines.yaml"
    )
