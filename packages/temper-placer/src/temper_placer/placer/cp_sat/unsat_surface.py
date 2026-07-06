"""
UNSAT report surfacing layer — Rich panel (stderr) and JSON output.

Translates ``UnsatReport`` dataclass into human-readable Rich-formatted
panel output and machine-readable JSON files.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from temper_placer.placer.cp_sat.unsat import UnsatReport


def format_unsat_panel(report: UnsatReport) -> str:
    """Format an ``UnsatReport`` as a Rich-markup panel string for stderr.

    Produces a human-readable panel that:
    - Lists the minimal core constraints with their ``because`` text
    - Groups conflicting constraints
    - Surfaces missing ``because`` fields as PCL data-quality gaps
    - Provides actionable advice for resolution

    Args:
        report: The unpacked ``UnsatReport``.

    Returns:
        A Rich-markup formatted string suitable for ``console.print()``.
    """
    lines: list[str] = []
    core_count = len(report.minimal_core)
    total_count = len(report.sufficient_core)

    lines.append(
        f"[bold red]Infeasibility detected.[/] Minimum conflicting constraints "
        f"([yellow]{core_count}[/] of [yellow]{total_count}[/]):"
    )
    lines.append("")

    for i, constraint in enumerate(report.minimal_core):
        # Constraint name with type.
        type_str = constraint.constraint_type.value if constraint.constraint_type else "unknown"
        name_display = f"{type_str} '[cyan]{constraint.name}[/]'"

        if constraint.because:
            lines.append(f"  [bold]\\[{i + 1}][/] {name_display}")
            lines.append(f"     [dim]because:[/] {constraint.because}")
        else:
            lines.append(f"  [bold]\\[{i + 1}][/] {name_display}")
            lines.append(
                "     [yellow]because field is unannotated; "
                "rationale not available from PCL spec[/] "
                "[dim](PCL data-quality gap)[/]"
            )

        lines.append("")

    # Suggested resolution guidance.
    lines.append("[bold]Suggested resolutions:[/]")
    lines.append(
        "  • Relax non-physics-grounded constraints (separation, enclosure, keepout)."
    )
    lines.append(
        "  • Increase board dimensions if zone constraints over-constrain."
    )
    lines.append(
        "  • Reduce component count in the constrained zone."
    )
    lines.append("")

    # Data quality summary.
    gaps = report.data_quality_gaps
    if gaps:
        lines.append(
            f"[bold yellow]PCL data-quality gaps:[/] {len(gaps)} constraint(s) "
            f"without rationale."
        )
        for gap in gaps:
            lines.append(
                f"  [dim]• {gap['constraint_name']}: {gap['gap']}[/]"
            )
        lines.append("")

    if not report.is_minimal:
        lines.append(
            "[dim]Note: The core may not be fully minimal (MUS refinement "
            "did not converge).[/]"
        )
        lines.append("")

    return "\n".join(lines)


def _build_unsat_json(report: UnsatReport) -> dict:
    """Build the JSON-serializable dict for an ``UnsatReport``.

    Args:
        report: The ``UnsatReport``.

    Returns:
        A JSON-serializable dict.
    """
    def _constraint_to_dict(c):
        return {
            "constraint_name": c.name,
            "constraint_type": c.constraint_type.value if c.constraint_type else "unknown",
            "because": c.because,
        }

    minimal_core = [_constraint_to_dict(c) for c in report.minimal_core]
    sufficient_core = [_constraint_to_dict(c) for c in report.sufficient_core]

    return {
        "report_type": "unsat",
        "solver": "cp-sat",
        "minimal_core": minimal_core,
        "sufficient_core": sufficient_core,
        "is_minimal": report.is_minimal,
        "data_quality_gaps": [
            {
                "constraint_name": g["constraint_name"],
                "gap": g["gap"],
            }
            for g in report.data_quality_gaps
        ],
    }


def write_unsat_json(report: UnsatReport, path: Path) -> None:
    """Write a structured JSON report of the UNSAT core to ``path``.

    Args:
        report: The ``UnsatReport``.
        path: Output file path.
    """
    data = _build_unsat_json(report)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
