"""pcl command for temper-placer CLI."""

from __future__ import annotations

import click
import json
import sys
from pathlib import Path
from ._io import console
from ._io import Table

@click.group()
def pcl() -> None:
    """Placement Constraint Language (PCL) tools."""
    pass


@pcl.command("validate")
@click.argument("pcl_file", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--pcb",
    type=click.Path(exists=True, path_type=Path),
    help="Optional PCB file to validate component references against.",
)
@click.option(
    "--schema/--no-schema",
    default=True,
    help="Validate against JSON Schema (default: enabled).",
)
@click.option(
    "--strict",
    is_flag=True,
    default=False,
    help="Treat warnings as errors.",
)
@click.option(
    "--json-output",
    is_flag=True,
    default=False,
    help="Output results as JSON.",
)
def pcl_validate(
    pcl_file: Path,
    pcb: Path | None,
    schema: bool,
    strict: bool,
    json_output: bool,
) -> None:
    """
    Validate a PCL constraint file.

    Checks:
    - YAML syntax
    - JSON Schema compliance (structure, required fields, value ranges)
    - Constraint parsing (type dispatch, unit conversion)
    - Component reference validity (if --pcb provided)

    Examples:
        temper-placer pcl validate constraints.yaml
        temper-placer pcl validate constraints.yaml --pcb temper.kicad_pcb
        temper-placer pcl validate constraints.yaml --strict --json-output
    """
    import json as json_module

    from temper_placer.pcl import PCLParseError, PCLValidationError, parse_pcl_file

    results = {
        "file": str(pcl_file),
        "passed": True,
        "errors": [],
        "warnings": [],
        "info": [],
        "constraints_count": 0,
    }

    if not json_output:
        console.print(f"[bold blue]Validating PCL:[/] {pcl_file}")

    # Step 1: JSON Schema validation (if enabled)
    if schema:
        if not json_output:
            console.print("\n[bold cyan]JSON Schema Validation:[/]")

        try:
            import jsonschema
            import yaml

            # Load schema
            schema_path = Path(__file__).parent / "../../configs/schemas/pcl.schema.json"
            if not schema_path.exists():
                # Try alternate location
                schema_path = (
                    Path(__file__).parent.parent.parent / "configs/schemas/pcl.schema.json"
                )

            if schema_path.exists():
                with open(schema_path) as f:
                    pcl_schema = json_module.load(f)

                # Load YAML as dict
                with open(pcl_file) as f:
                    pcl_data = yaml.safe_load(f)

                # Validate
                jsonschema.validate(pcl_data, pcl_schema)

                if not json_output:
                    console.print("  [green]✓[/] Schema validation passed")
                results["info"].append("Schema validation passed")
            else:
                if not json_output:
                    console.print(
                        "  [yellow]⚠[/] Schema file not found - skipping schema validation"
                    )
                results["warnings"].append("Schema file not found - skipping schema validation")

        except ImportError:
            if not json_output:
                console.print(
                    "  [yellow]⚠[/] jsonschema not installed - skipping schema validation"
                )
                console.print("    Install with: pip install jsonschema")
            results["warnings"].append("jsonschema not installed - skipping schema validation")

        except jsonschema.ValidationError as e:
            error_msg = f"Schema validation failed: {e.message}"
            if e.path:
                error_msg += f" at {'/'.join(str(p) for p in e.path)}"
            results["errors"].append(error_msg)
            results["passed"] = False

            if not json_output:
                console.print(f"  [red]✗[/] {error_msg}")

        except Exception as e:
            error_msg = f"Schema validation error: {e}"
            results["errors"].append(error_msg)
            results["passed"] = False

            if not json_output:
                console.print(f"  [red]✗[/] {error_msg}")

    # Step 2: PCL Parsing
    if not json_output:
        console.print("\n[bold cyan]PCL Parsing:[/]")

    try:
        collection = parse_pcl_file(pcl_file)
        results["constraints_count"] = len(collection)

        if not json_output:
            console.print(f"  [green]✓[/] Parsed {len(collection)} constraints")

        # Show breakdown by tier
        tier_counts = {}
        for c in collection.constraints:
            tier_name = c.tier.name
            tier_counts[tier_name] = tier_counts.get(tier_name, 0) + 1

        if not json_output:
            for tier, count in sorted(tier_counts.items()):
                console.print(f"    - {tier}: {count}")

        results["info"].append(f"Parsed {len(collection)} constraints")
        results["tier_breakdown"] = tier_counts

    except PCLParseError as e:
        error_msg = f"Parse error: {e}"
        results["errors"].append(error_msg)
        results["passed"] = False

        if not json_output:
            console.print(f"  [red]✗[/] {error_msg}")

        # Can't continue without parsed collection
        if json_output:
            print(json_module.dumps(results, indent=2))
        sys.exit(1)

    # Step 3: Component Reference Validation (if PCB provided)
    if pcb:
        if not json_output:
            console.print("\n[bold cyan]Component Reference Validation:[/]")

        try:
            from temper_placer.io.kicad_parser import parse_kicad_pcb

            parse_result = parse_kicad_pcb(pcb)
            component_refs = [c.ref for c in parse_result.netlist.components]

            if not json_output:
                console.print(f"  [dim]Loaded {len(component_refs)} components from PCB[/]")

            # Validate references
            ref_errors = collection.validate_component_refs(component_refs)

            if ref_errors:
                for err in ref_errors:
                    results["warnings"].append(err)
                    if not json_output:
                        console.print(f"  [yellow]⚠[/] {err}")

                if strict:
                    results["passed"] = False
            else:
                if not json_output:
                    console.print("  [green]✓[/] All component references valid")
                results["info"].append("All component references valid")

        except Exception as e:
            error_msg = f"PCB validation error: {e}"
            results["errors"].append(error_msg)
            results["passed"] = False

            if not json_output:
                console.print(f"  [red]✗[/] {error_msg}")

    # Step 4: Check 'because' field quality
    if not json_output:
        console.print("\n[bold cyan]Rationale Quality:[/]")

    short_because = []
    for c in collection.constraints:
        if len(c.because) < 10:
            short_because.append(
                f"Constraint '{c.id or c.constraint_type.value}': because too short ({len(c.because)} chars)"
            )

    if short_because:
        for msg in short_because:
            results["warnings"].append(msg)
            if not json_output:
                console.print(f"  [yellow]⚠[/] {msg}")

        if strict:
            results["passed"] = False
    else:
        if not json_output:
            console.print("  [green]✓[/] All constraints have meaningful rationale")
        results["info"].append("All constraints have meaningful rationale (>=10 chars)")

    # Output results
    if json_output:
        print(json_module.dumps(results, indent=2))
    else:
        console.print("\n" + "─" * 50)
        if results["passed"] and (not strict or not results["warnings"]):
            console.print("[bold green]✓ Validation passed[/]")
        else:
            console.print("[bold red]✗ Validation failed[/]")
        console.print(
            f"  {len(results['errors'])} errors, "
            f"{len(results['warnings'])} warnings, "
            f"{len(results['info'])} info"
        )

    # Exit code
    if strict:
        sys.exit(0 if results["passed"] and not results["warnings"] else 1)
    else:
        sys.exit(0 if results["passed"] else 1)


@pcl.command("show")
@click.argument("pcl_file", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--tier",
    type=click.Choice(["hard", "strong", "soft", "all"]),
    default="all",
    help="Filter by constraint tier.",
)
@click.option(
    "--type",
    "constraint_type",
    type=str,
    default=None,
    help="Filter by constraint type (e.g., adjacent, separated).",
)
@click.option(
    "--json-output",
    is_flag=True,
    default=False,
    help="Output as JSON.",
)
def pcl_show(
    pcl_file: Path,
    tier: str,
    constraint_type: str | None,
    json_output: bool,
) -> None:
    """
    Display constraints from a PCL file.

    Shows a formatted table or JSON of all constraints with their
    parameters, tiers, and rationale.

    Examples:
        temper-placer pcl show constraints.yaml
        temper-placer pcl show constraints.yaml --tier hard
        temper-placer pcl show constraints.yaml --type adjacent --json-output
    """
    import json as json_module

    from temper_placer.pcl import ConstraintTier, ConstraintType, parse_pcl_file

    try:
        collection = parse_pcl_file(pcl_file)
    except Exception as e:
        console.print(f"[red]Failed to parse: {e}[/]")
        sys.exit(1)

    # Filter by tier
    constraints = collection.constraints
    if tier != "all":
        tier_enum = ConstraintTier[tier.upper()]
        constraints = [c for c in constraints if c.tier == tier_enum]

    # Filter by type
    if constraint_type:
        type_enum = ConstraintType(constraint_type.lower())
        constraints = [c for c in constraints if c.constraint_type == type_enum]

    if json_output:
        output = {
            "file": str(pcl_file),
            "total": len(collection),
            "filtered": len(constraints),
            "constraints": [
                {
                    "id": c.id or f"{c.constraint_type.value}_{i}",
                    "type": c.constraint_type.value,
                    "tier": c.tier.name,
                    "because": c.because,
                    **c.to_dict(),
                }
                for i, c in enumerate(constraints)
            ],
        }
        print(json_module.dumps(output, indent=2))
    else:
        console.print(f"[bold blue]PCL Constraints:[/] {pcl_file}")
        console.print(f"Showing {len(constraints)} of {len(collection)} constraints\n")

        table = Table(title="Constraints")
        table.add_column("ID", style="cyan", width=12)
        table.add_column("Type", style="green", width=10)
        table.add_column("Tier", style="yellow", width=8)
        table.add_column("Details", width=30)
        table.add_column("Because", style="dim", width=30)

        for i, c in enumerate(constraints):
            cid = c.id or f"{c.constraint_type.value[:3]}_{i}"
            ctype = c.constraint_type.value
            ctier = c.tier.name

            # Build details string based on type
            if hasattr(c, "a") and hasattr(c, "b"):
                details = f"{c.a} ↔ {c.b}"
                if hasattr(c, "max_distance_mm"):
                    details += f" ≤{c.max_distance_mm}mm"
                elif hasattr(c, "min_distance_mm"):
                    details += f" ≥{c.min_distance_mm}mm"
            elif hasattr(c, "components"):
                details = ", ".join(c.components[:3])
                if len(c.components) > 3:
                    details += f" +{len(c.components) - 3}"
            elif hasattr(c, "loop_name"):
                details = f"loop:{c.loop_name} ≤{c.max_area_mm2}mm²"
            elif hasattr(c, "component"):
                details = c.component
            else:
                details = str(c)[:30]

            # Truncate because
            because = c.because[:27] + "..." if len(c.because) > 30 else c.because

            table.add_row(cid, ctype, ctier, details, because)

        console.print(table)
