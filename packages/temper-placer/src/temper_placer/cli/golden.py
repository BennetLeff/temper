"""temper golden --- Golden fixture generation and verification CLI."""

from __future__ import annotations

import datetime
import json
import subprocess
import sys
import yaml
from pathlib import Path
from typing import Optional

import click

from temper_placer.io.boundary_registry import STAGE2_BOUNDARY_NAMES, BoundaryRegistry
from temper_placer.io.golden_serializers import SERIALIZER_REGISTRY
from temper_placer.testing.golden_diff import DiffReport, diff_golden


CANONICAL_BOARDS = {
    "temper_placed": Path("pcb/temper_placed.kicad_pcb"),
    "temper_routable": Path("pcb/temper_routable.kicad_pcb"),
    "temper_ready_for_route": Path("pcb/temper_ready_for_route.kicad_pcb"),
    "temper_optimized_hq": Path("pcb/temper_optimized_hq.kicad_pcb"),
}

GOLDENS_ROOT = Path("power_pcb_dataset/goldens")
MANIFEST_PATH = GOLDENS_ROOT / "manifest.yaml"
MANIFEST_FORMAT_VERSION = 1
TOLERANCE_MM = 1e-3


def _git_head_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True
        ).strip()
    except Exception:
        return "unknown"


def _build_pipeline_up_to(boundary_name: str, board, netlist):
    from temper_placer.deterministic import DeterministicPipeline
    from temper_placer.deterministic.stages import (
        ZoneGeometryStage,
        ZoneAssignmentStage,
        SlotGenerationStage,
        ComponentAssignmentStage,
        ApplyPlacementsStage,
        CourtyardCheckStage,
        PlacementValidationStage,
    )

    boundaries_order = [
        "zone_geometry", "zone_assignment", "slot_generation",
        "component_assignment", "apply_placements", "courtyard_check",
        "apply_placements_reapply", "placement_validation",
    ]

    if boundary_name not in boundaries_order:
        raise ValueError(f"Unknown boundary: {boundary_name}")

    target_idx = boundaries_order.index(boundary_name)
    board_w = board.width if board else 100.0
    board_h = board.height if board else 150.0

    stage_factories = {
        "zone_geometry": lambda: ZoneGeometryStage(),
        "zone_assignment": lambda: ZoneAssignmentStage(),
        "slot_generation": lambda: SlotGenerationStage(slot_spacing_mm=7.5),
        "component_assignment": lambda: ComponentAssignmentStage(),
        "apply_placements": lambda: ApplyPlacementsStage(),
        "courtyard_check": lambda: CourtyardCheckStage(
            courtyards={}, board_width=board_w, board_height=board_h, margin=5.0,
        ),
        "apply_placements_reapply": lambda: ApplyPlacementsStage(),
        "placement_validation": lambda: PlacementValidationStage(
            constraints=[], fail_on_hard_violations=False,
        ),
    }

    stages = []
    for i in range(target_idx + 1):
        name = boundaries_order[i]
        stages.append(stage_factories[name]())

    return DeterministicPipeline(stages=stages)


def _generate_fixture(board_id: str, stage: str, pcb_path: Path) -> str:
    from temper_placer.io.kicad_parser import parse_kicad_pcb
    from temper_placer.deterministic.state import BoardState

    bd = BoundaryRegistry.get_boundary(stage)
    serializer = SERIALIZER_REGISTRY[bd.serialization_fn]

    parse_result = parse_kicad_pcb(pcb_path)
    netlist = parse_result.netlist
    board = parse_result.board

    initial_state = BoardState(board=board, netlist=netlist)
    pipeline = _build_pipeline_up_to(stage, board, netlist)
    final_state = pipeline.run(initial_state)

    return serializer(final_state)


def _write_manifest(fixtures: list[dict]) -> None:
    manifest = {
        "format_version": MANIFEST_FORMAT_VERSION,
        "fixtures": fixtures,
    }
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(yaml.dump(manifest, default_flow_style=False, sort_keys=False))


def _load_manifest() -> dict:
    if not MANIFEST_PATH.exists():
        return {"format_version": 1, "fixtures": []}
    return yaml.safe_load(MANIFEST_PATH.read_text()) or {"format_version": 1, "fixtures": []}


@click.group()
def golden() -> None:
    """Golden fixture generation and verification."""
    pass


@golden.command()
@click.option("--stage", "-s", help="Generate for a specific stage boundary")
@click.option("--board", "-b", help="Generate for a specific canonical board")
@click.option("--all-boards", is_flag=True, default=False, help="Generate for all 4 canonical boards")
@click.option("--all-stages", is_flag=True, default=False, help="Generate for all 8 Stage 2 boundaries")
@click.option("--verbose", "-v", is_flag=True, default=False, help="Verbose output")
def generate(
    stage: Optional[str],
    board: Optional[str],
    all_boards: bool,
    all_stages: bool,
    verbose: bool,
) -> None:
    """Generate golden fixtures for canonical boards at stage boundaries."""
    if all_boards:
        boards = list(CANONICAL_BOARDS.keys())
    elif board:
        if board not in CANONICAL_BOARDS:
            click.echo(f"Unknown board '{board}'. Known: {', '.join(CANONICAL_BOARDS.keys())}", err=True)
            raise click.Abort()
        boards = [board]
    else:
        click.echo("Specify --board, --all-boards, or --all-stages", err=True)
        raise click.Abort()

    if all_stages:
        stages = list(STAGE2_BOUNDARY_NAMES)
    elif stage:
        if stage not in STAGE2_BOUNDARY_NAMES:
            click.echo(f"Unknown stage '{stage}'. Known: {', '.join(STAGE2_BOUNDARY_NAMES)}", err=True)
            raise click.Abort()
        stages = [stage]
    else:
        click.echo("Specify --stage or --all-stages", err=True)
        raise click.Abort()

    git_sha = _git_head_sha()
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    existing_manifest = _load_manifest()
    existing_map = {
        (f["board"], f["stage"]): f for f in existing_manifest.get("fixtures", [])
    }

    new_fixtures = []
    for b in boards:
        pcb_path = CANONICAL_BOARDS[b]
        if not pcb_path.exists():
            click.echo(f"PCB not found: {pcb_path}", err=True)
            continue
        for s in stages:
            bd = BoundaryRegistry.get_boundary(s)
            ext = bd.output_format
            out_dir = GOLDENS_ROOT / b
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / f"{s}.{ext}"

            if verbose:
                click.echo(f"Generating {b}/{s} ...")

            content = _generate_fixture(b, s, pcb_path)
            out_path.write_text(content)

            key = (b, s)
            existing = existing_map.get(key, {})
            fixture_entry = {
                "board": b,
                "stage": s,
                "pipeline": bd.pipeline_class,
                "output_format": ext,
                "file": str(out_path.relative_to(GOLDENS_ROOT.parent)),
                "git_hash": git_sha,
                "format_version": MANIFEST_FORMAT_VERSION,
                "first_added_at": existing.get("first_added_at", now_iso),
                "first_added_hash": existing.get("first_added_hash", git_sha),
            }
            new_fixtures.append(fixture_entry)

            if verbose:
                click.echo(f"  -> {out_path}")

    _write_manifest(new_fixtures)
    click.echo(f"Generated {len(new_fixtures)} fixtures across {len(boards)} board(s)")


@golden.command()
@click.option("--json", "json_output", is_flag=True, default=False, help="Output structured JSON")
@click.option("--verbose", "-v", is_flag=True, default=False, help="Verbose output")
def check(json_output: bool, verbose: bool) -> None:
    """Verify golden fixtures against current pipeline output."""
    manifest = _load_manifest()
    fixtures = manifest.get("fixtures", [])

    if not fixtures:
        click.echo("No fixtures in manifest", err=True)
        sys.exit(0)

    all_reports: list[DiffReport] = []
    exit_code = 0

    for fixture in fixtures:
        board_id = fixture["board"]
        stage = fixture["stage"]
        output_format = fixture["output_format"]
        file_rel = fixture["file"]
        golden_path = GOLDENS_ROOT.parent / file_rel

        if not golden_path.exists():
            report = DiffReport(
                board=board_id, stage=stage, passed=False,
                summary=f"Golden file not found: {golden_path}",
            )
            all_reports.append(report)
            exit_code = 1
            if verbose or not json_output:
                click.echo(f"FAIL: {board_id}/{stage} - golden file missing")
            continue

        pcb_path = CANONICAL_BOARDS[board_id]
        if not pcb_path.exists():
            report = DiffReport(
                board=board_id, stage=stage, passed=False,
                summary=f"PCB not found: {pcb_path}",
            )
            all_reports.append(report)
            exit_code = 1
            if verbose or not json_output:
                click.echo(f"FAIL: {board_id}/{stage} - PCB missing")
            continue

        golden_content = golden_path.read_text()
        try:
            candidate_content = _generate_fixture(board_id, stage, pcb_path)
        except Exception as e:
            report = DiffReport(
                board=board_id, stage=stage, passed=False,
                summary=f"Generation failed: {e}",
            )
            all_reports.append(report)
            exit_code = 1
            click.echo(f"FAIL: {board_id}/{stage} - {e}", err=True)
            continue

        report = diff_golden(
            board=board_id, stage=stage,
            golden_content=golden_content,
            candidate_content=candidate_content,
            output_format=output_format,
            tolerance_mm=TOLERANCE_MM,
        )
        all_reports.append(report)

        if report.passed:
            if verbose:
                click.echo(f"PASS: {board_id}/{stage}")
        else:
            exit_code = 1
            if verbose or not json_output:
                click.echo(f"FAIL: {board_id}/{stage}")
                for entry in report.entries:
                    if entry.category in ("BINARY", "BEYOND_TOLERANCE"):
                        click.echo(f"  {entry.category}: {entry.entity} {entry.field}: golden={entry.golden_value} candidate={entry.candidate_value}")

    if json_output:
        flattened = []
        for r in all_reports:
            flattened.extend(r.to_json())
        click.echo(json.dumps(flattened, indent=2))
    else:
        total = len(all_reports)
        passed = sum(1 for r in all_reports if r.passed)
        failed = total - passed
        click.echo(f"\n{passed}/{total} passed, {failed} failed")
        if failed > 0:
            click.echo(f"Run 'temper golden generate --all-boards --all-stages' to regenerate")

    sys.exit(exit_code)
