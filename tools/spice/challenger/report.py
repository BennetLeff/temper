"""
Challenger cross-validation report generator.

Produces a markdown report summarizing the cross-validation results
between the ngspice primary thermal model and the independent 2D
finite-difference challenger.
"""

from __future__ import annotations

from tools.spice.challenger.cross_validate import CrossValidationResult


def generate_challenger_report(
    validation: CrossValidationResult,
    title: str = "Thermal Challenger Cross-Validation Report",
) -> str:
    """Generate a markdown cross-validation report.

    Args:
        validation: CrossValidationResult from cross_validate().
        title: Report title.

    Returns:
        Markdown report string.
    """
    lines: list[str] = []
    lines.append(f"# {title}")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- **Total corners:** {validation.total_corners}")
    lines.append(f"- **Agreed (<10%):** {validation.agreed_corners}")
    lines.append(f"- **Flagged (>10%):** {validation.flagged_corners}")
    lines.append(
        f"- **Agreement rate:** {validation.agreement_rate_pct:.1f}%"
    )
    lines.append(
        f"- **Worst disagreement:** {validation.worst_disagreement_pct:.1f}% "
        f"(corner: {validation.worst_corner})"
    )
    lines.append("")

    if validation.flagged_corners > 0:
        lines.append("## Flagged Corners")
        lines.append("")

        threshold = validation.flagged_corners / max(validation.total_corners, 1)
        if threshold > 0.1:
            lines.append(
                "**WARNING:** More than 10% of corners show >10% disagreement. "
                "This suggests a systematic modeling error. Review stack-up "
                "parameters, boundary conditions, or the hand-calculation "
                "derating factors."
            )
            lines.append("")

        lines.append(
            "| Corner | Tj Primary (°C) | Tj Challenger (°C) | Disagreement |"
        )
        lines.append(
            "|--------|-----------------|--------------------|-------------|"
        )
        for fd in validation.flagged_details:
            lines.append(
                f"| {fd['corner']} | {fd['Tj_primary']:.1f} | "
                f"{fd['Tj_challenger']:.1f} | {fd['disagreement_pct']:.1f}% |"
            )
        lines.append("")

    if validation.agreement_rate_pct >= 90.0:
        lines.append("## Assessment")
        lines.append("")
        lines.append("Challenger model agrees with primary thermal model on "
                     ">=90% of corners. Cross-validation passes.")
    else:
        lines.append("## Assessment")
        lines.append("")
        lines.append("Challenger model disagrees with primary thermal model on "
                     ">10% of corners. This is a soft gate only — the pipeline "
                     "still exits 0 if hard gates pass. However, systematic "
                     "disagreement warrants a modeling review before sign-off.")

    return "\n".join(lines)
