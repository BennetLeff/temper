"""temper dsn --- DSN/SES universal seam operations CLI."""

from __future__ import annotations

from pathlib import Path

import click

from temper_placer.io.boundary_registry import BoundaryRegistry
from temper_placer.io.dsn_normalizer import DSNNormalizer
from temper_placer.io.dsn_validator import DSNVersionValidator


@click.group()
def dsn() -> None:
    """DSN/SES universal seam operations."""
    pass


@dsn.command()
@click.option("--boundary", "-b", required=True, help="Stage boundary name")
@click.option("--input", "-i", "input_pcb", required=True, type=click.Path(exists=True, path_type=Path), help="Input KiCad PCB")
@click.option("--config", "-c", type=click.Path(exists=True, path_type=Path), help="Constraints YAML")
@click.option("--output", "-o", type=click.Path(path_type=Path), help="Output DSN file (default: stdout)")
@click.option("--no-deterministic", is_flag=True, help="Disable deterministic mode")
def export(
    boundary: str,
    input_pcb: Path,
    config: Path | None,
    output: Path | None,
    no_deterministic: bool,
) -> None:
    """Export DSN at a stage boundary."""
    from temper_placer.io.dsn_boundary import DSNBoundaryExporter

    dsn_text = DSNBoundaryExporter.export_at_boundary(boundary, input_pcb, config)

    if not no_deterministic:
        dsn_text = DSNNormalizer.normalize(dsn_text)

    if output:
        output.write_text(dsn_text)
    else:
        click.echo(dsn_text, nl=False)


@dsn.command()
@click.option("--boundary", "-b", required=True, help="Stage boundary name")
@click.option("--input", "-i", "input_pcb", required=True, type=click.Path(exists=True, path_type=Path), help="Input KiCad PCB")
@click.option("--config", "-c", type=click.Path(exists=True, path_type=Path), help="Constraints YAML")
@click.option("--golden-dir", type=click.Path(exists=True, path_type=Path), default=Path("power_pcb_dataset/goldens/temper"))
def check(
    boundary: str,
    input_pcb: Path,
    config: Path | None,
    golden_dir: Path,
) -> None:
    """Compare current DSN output against committed golden."""
    from temper_placer.io.dsn_boundary import DSNBoundaryExporter
    from temper_placer.io.dsn_schema import DSNSchemaHasher

    golden_path = golden_dir / f"{boundary}.dsn"

    if not golden_path.exists():
        click.echo(f"PASS (no golden for {boundary})", err=True)
        raise click.Abort()

    golden_text = DSNNormalizer.normalize(golden_path.read_text())
    current = DSNNormalizer.normalize(DSNBoundaryExporter.export_at_boundary(boundary, input_pcb, config))

    # Check schema hash first
    golden_hash = DSNSchemaHasher.extract_hash(golden_text)
    current_hash = DSNSchemaHasher.extract_hash(current)
    if golden_hash and current_hash and golden_hash != current_hash:
        click.echo(f"FAIL: schema version mismatch\n  golden: sha256:{golden_hash}\n  current: sha256:{current_hash}")
        raise click.Abort()

    if golden_text == current:
        click.echo(f"PASS: {boundary} matches golden")
    else:
        # Check if differences are geometry-only (within tolerance)
        import difflib
        diff = list(difflib.unified_diff(golden_text.splitlines(True), current.splitlines(True), fromfile="golden", tofile="current"))
        if diff:
            for line in diff:
                click.echo(line, nl=False)

        # Simple check: if only coordinate values differ, it's WITHIN_TOLERANCE
        import re
        golden_no_coords = re.sub(r"\b\d+(\.\d+)?\b", "X", golden_text)
        current_no_coords = re.sub(r"\b\d+(\.\d+)?\b", "X", current)
        if golden_no_coords == current_no_coords:
            click.echo(f"WITHIN_TOLERANCE: {boundary} (geometry-only differences)")
        else:
            click.echo(f"FAIL: {boundary} diverged from golden")
            raise click.Abort()


@dsn.command("boundaries")
def list_boundaries_cmd() -> None:
    """List registered stage boundaries."""
    for name in BoundaryRegistry.list_boundaries():
        b = BoundaryRegistry.get_boundary(name)
        click.echo(f"{name:20s} {b.pipeline_class}.{b.phase_name:15s} format={b.output_format}")


@dsn.command()
@click.option("--dsn", "dsn_file", required=True, type=click.Path(exists=True, path_type=Path), help="DSN file to validate")
@click.option("--expected-hash", required=True, help="Expected schema hash (sha256:<hex>)")
def validate(dsn_file: Path, expected_hash: str) -> None:
    """Validate a DSN file's schema version against an expected hash."""
    dsn_text = dsn_file.read_text()
    DSNVersionValidator.validate(dsn_text, expected_hash)
    click.echo(f"PASS: schema version matches sha256:{expected_hash}")


@dsn.command()
@click.option("--boundary", "-b", help="Stage boundary name (omit for all)")
@click.option("--input", "-i", "input_pcb", required=True, type=click.Path(exists=True, path_type=Path), help="Input KiCad PCB")
@click.option("--config", "-c", type=click.Path(exists=True, path_type=Path), help="Constraints YAML")
@click.option("--golden-dir", type=click.Path(path_type=Path), default=Path("power_pcb_dataset/goldens/temper"))
def generate(
    boundary: str | None,
    input_pcb: Path,
    config: Path | None,
    golden_dir: Path,
) -> None:
    """Generate/update golden DSN fixtures."""
    from temper_placer.io.dsn_boundary import DSNBoundaryExporter
    import yaml, subprocess

    boundaries = [boundary] if boundary else BoundaryRegistry.list_boundaries()
    golden_dir.mkdir(parents=True, exist_ok=True)

    try:
        commit_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        commit_sha = "unknown"

    for name in boundaries:
        dsn_text = DSNNormalizer.normalize(DSNBoundaryExporter.export_at_boundary(name, input_pcb, config))
        out_path = golden_dir / f"{name}.dsn"
        out_path.write_text(dsn_text)
        click.echo(f"Wrote {out_path}")

    manifest_path = golden_dir / "manifest.yaml"
    manifest = {
        "format_version": 1,
        "board": input_pcb.stem,
        "fixtures": [
            {
                "stage": name,
                "pipeline": BoundaryRegistry.get_boundary(name).pipeline_class,
                "format": BoundaryRegistry.get_boundary(name).output_format,
                "generated_at_commit": commit_sha,
            }
            for name in boundaries
        ],
    }
    manifest_path.write_text(yaml.dump(manifest, default_flow_style=False))
    click.echo(f"Updated {manifest_path}")
