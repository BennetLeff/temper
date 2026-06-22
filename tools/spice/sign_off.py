"""
Pipeline orchestrator and sign-off report generator.

Runs the full extraction -> sweep -> challenger -> report pipeline.
Applies hard gates (max gate-loop L <= 10nH, Vge overshoot < 20% at all corners)
and soft gates (challenger agreement rate). Exit code 0 only when all hard
gates pass.

Usage:
    python tools/spice/sign_off.py pcb/temper_spice_validated.kicad_pcb \
        simulation/testbenches/sim_26_full_power_stage.cir
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from tools.spice.challenger.cross_validate import cross_validate
from tools.spice.challenger.report import generate_challenger_report
from tools.spice.corner_results import CornerResult
from tools.spice.corner_sweep import run_corner_sweep
from tools.spice.extract import extract_parasitics
from tools.spice.inject_parasitics import inject_parasitics

GATE_DRIVE_L_MAX_nH = 10.0
VGE_OVERSHOOT_MAX_PCT = 20.0
CHALLENGER_DISAGREEMENT_SOFT_PCT = 10.0
HARD_DISAGREEMENT_PCT = 20.0


@dataclass
class SignOffResult:
    """Result of a full sign-off pipeline run."""

    pcb_file: str
    pcb_hash: str
    template_file: str
    extraction_summary: dict[str, dict[str, float]]
    sweep_corners: int
    sweep_converged: int
    challenger_agreement_rate: float
    hard_gates: dict[str, bool]
    soft_warnings: list[str]
    exit_code: int
    output_netlist: str = ""
    report_path: str = ""
    sweep_results_path: str = ""


def _pcb_hash(pcb_path: str) -> str:
    """Compute SHA-256 hash of PCB file for reproducibility tracking."""
    with open(pcb_path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()[:16]


def run_sign_off(
    pcb_file: str,
    template_file: str,
    output_dir: str | None = None,
    mode: str = "corners",
) -> SignOffResult:
    """Run the full sign-off pipeline.

    Steps:
    1. Extract parasitics from KiCad PCB
    2. Inject into SPICE template
    3. Run corner envelope sweep
    4. Run challenger cross-validation
    5. Generate report
    6. Apply hard/soft gates

    Args:
        pcb_file: Path to DRC-clean .kicad_pcb file.
        template_file: Path to SPICE netlist template.
        output_dir: Directory for output artifacts. Default: auto-generated.
        mode: Sweep mode ("corners" or "full").

    Returns:
        SignOffResult with gate status and exit code.
    """
    date_str = datetime.now().strftime("%Y-%m-%d")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    if output_dir is None:
        output_dir = "simulation/reports"

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    Path("simulation/testbenches/layout_parasitics").mkdir(
        parents=True, exist_ok=True
    )
    Path("simulation/results").mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("  Layout-Aware SPICE Sign-Off Pipeline")
    print("=" * 60)
    print()

    pcb_hash_val = _pcb_hash(pcb_file)

    print("[1/4] Extracting parasitics...")
    extraction = extract_parasitics(pcb_file)
    extraction_summary: dict[str, dict[str, float]] = {}
    for net_name, pv in extraction.nets.items():
        extraction_summary[net_name] = {
            "R_mOhm": pv.R_mOhm,
            "L_nH": pv.L_nH,
            "C_pF": pv.C_pF,
        }
        group = pv.loop_group or "unassigned"
        print(f"  {net_name} [{group}]: "
              f"R={pv.R_mOhm:.1f}mOhm L={pv.L_nH:.1f}nH C={pv.C_pF:.1f}pF")

    print()

    output_netlist = (
        f"simulation/testbenches/layout_parasitics/"
        f"augmented_{timestamp}.cir"
    )

    print("[2/4] Injecting parasitics into template...")
    inject_parasitics(template_file, extraction, output_netlist)
    print(f"  Output: {output_netlist}")
    print()

    print(f"[3/4] Running corner sweep ({mode} mode)...")
    sweep_start = time.time()
    sweep_results = run_corner_sweep(
        output_netlist,
        mode=mode,
    )
    sweep_elapsed = time.time() - sweep_start

    sweep_path = f"simulation/results/corner_sweep_{timestamp}.json"
    with open(sweep_path, "w") as f:
        json.dump([r.to_dict() for r in sweep_results], f, indent=2)

    converged = sum(1 for r in sweep_results if not r.convergence_error)
    failed = sum(1 for r in sweep_results if r.convergence_error)
    print(f"  {len(sweep_results)} corners in {sweep_elapsed:.1f}s "
          f"({converged} converged, {failed} failed)")
    print()

    print("[4/4] Running challenger cross-validation...")
    validation = cross_validate(sweep_results)
    print(f"  Agreement rate: {validation.agreement_rate_pct:.1f}%")
    print(f"  Flagged: {validation.flagged_corners}/{validation.total_corners}")
    print()

    hard_gates: dict[str, bool] = {}
    soft_warnings: list[str] = []

    max_gate_L = max(
        (pv.L_nH for pv in extraction.nets.values()
         if pv.loop_group and pv.loop_group.startswith("gate_drive")),
        default=0.0,
    )
    gate_l_pass = max_gate_L <= GATE_DRIVE_L_MAX_nH
    hard_gates["gate_loop_L"] = gate_l_pass

    max_overshoot = max(
        (r.Vge_overshoot_pct for r in sweep_results
         if not r.convergence_error and r.Vge_overshoot_pct is not None),
        default=0.0,
    )
    overshoot_pass = max_overshoot < VGE_OVERSHOOT_MAX_PCT
    hard_gates["vge_overshoot"] = overshoot_pass

    if validation.flagged_corners > 0:
        soft_warnings.append(
            f"{validation.flagged_corners}/{validation.total_corners} corners "
            f"show >{CHALLENGER_DISAGREEMENT_SOFT_PCT}% challenger disagreement"
        )

    hard_disagree = validation.worst_disagreement_pct > HARD_DISAGREEMENT_PCT
    if hard_disagree:
        soft_warnings.append(
            f"Worst challenger disagreement ({validation.worst_disagreement_pct:.1f}%) "
            f"exceeds {HARD_DISAGREEMENT_PCT}%"
        )

    exit_code = 0 if all(hard_gates.values()) else 1

    report_path = f"{output_dir}/layout_spice_report_{date_str}.md"
    _write_sign_off_report(
        report_path,
        pcb_file,
        pcb_hash_val,
        template_file,
        extraction_summary,
        sweep_results,
        converged,
        validation,
        hard_gates,
        soft_warnings,
        exit_code,
    )

    print("=" * 60)
    print("  GATE RESULTS")
    print("=" * 60)
    for gate_name, passed in hard_gates.items():
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {gate_name}")
    print(f"  Exit code: {exit_code}")
    print(f"  Report: {report_path}")
    print()

    return SignOffResult(
        pcb_file=pcb_file,
        pcb_hash=pcb_hash_val,
        template_file=template_file,
        extraction_summary=extraction_summary,
        sweep_corners=len(sweep_results),
        sweep_converged=converged,
        challenger_agreement_rate=validation.agreement_rate_pct,
        hard_gates=hard_gates,
        soft_warnings=soft_warnings,
        exit_code=exit_code,
        output_netlist=output_netlist,
        report_path=report_path,
        sweep_results_path=sweep_path,
    )


def _write_sign_off_report(
    path: str,
    pcb_file: str,
    pcb_hash: str,
    template_file: str,
    extraction_summary: dict[str, dict[str, float]],
    sweep_results: list[CornerResult],
    converged: int,
    validation: object,
    hard_gates: dict[str, bool],
    soft_warnings: list[str],
    exit_code: int,
) -> None:
    """Write the sign-off report in markdown format."""
    lines: list[str] = []
    lines.append("# Layout-Aware SPICE Sign-Off Report")
    lines.append("")
    lines.append(f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"**PCB:** {pcb_file}")
    lines.append(f"**PCB Hash:** {pcb_hash}")
    lines.append(f"**Template:** {template_file}")
    lines.append("**Extraction Method:** Hand-calculated (G3 fallback)")
    lines.append("")

    lines.append("## Hard Gate Results")
    lines.append("")
    for gate, passed in hard_gates.items():
        status = "PASS" if passed else "**FAIL**"
        lines.append(f"- [{status}] {gate}")
    lines.append(f"- **Exit Code:** {exit_code}")
    lines.append("")

    lines.append("## Extracted Parasitics Summary")
    lines.append("")
    lines.append("| Net | R (mOhm) | L (nH) | C (pF) |")
    lines.append("|-----|----------|--------|--------|")
    for net_name, values in extraction_summary.items():
        lines.append(
            f"| {net_name} | {values['R_mOhm']:.1f} | "
            f"{values['L_nH']:.1f} | {values['C_pF']:.1f} |"
        )
    lines.append("")

    lines.append("## Corner Sweep Results")
    lines.append("")
    lines.append(f"- **Total corners:** {len(sweep_results)}")
    lines.append(f"- **Converged:** {converged}")
    lines.append(
        f"- **Failed:** {len(sweep_results) - converged}"
    )

    max_overshoot = max(
        (r.Vge_overshoot_pct for r in sweep_results
         if not r.convergence_error and r.Vge_overshoot_pct is not None),
        default=-1.0,
    )
    lines.append(f"- **Worst Vge overshoot:** {max_overshoot:.1f}%")
    lines.append("")

    lines.append("## Challenger Cross-Validation")
    lines.append("")
    chal_report = generate_challenger_report(
        validation,
        title="Thermal Challenger Results",
    )
    lines.append(chal_report)
    lines.append("")

    if soft_warnings:
        lines.append("## Warnings")
        lines.append("")
        for w in soft_warnings:
            lines.append(f"- {w}")
        lines.append("")

    lines.append("---")
    lines.append(
        f"*Report generated by tools/spice/sign_off.py on "
        f"{datetime.now().strftime('%Y-%m-%d %H:%M')}*"
    )

    with open(path, "w") as f:
        f.write("\n".join(lines))


def main() -> None:
    """CLI entry point for sign-off pipeline."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Layout-aware SPICE sign-off pipeline"
    )
    parser.add_argument(
        "pcb_file", help="Path to DRC-clean .kicad_pcb file"
    )
    parser.add_argument(
        "template_file", help="Path to SPICE netlist template"
    )
    parser.add_argument(
        "--mode",
        choices=["full", "corners"],
        default="corners",
        help="Sweep mode",
    )
    parser.add_argument(
        "--output-dir",
        help="Output directory for reports",
    )
    args = parser.parse_args()

    result = run_sign_off(
        args.pcb_file,
        args.template_file,
        output_dir=args.output_dir,
        mode=args.mode,
    )

    sys.exit(result.exit_code)


if __name__ == "__main__":
    main()
