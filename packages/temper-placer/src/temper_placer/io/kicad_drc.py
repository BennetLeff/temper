"""
KiCad DRC Integration.

This module provides integration with KiCad's Design Rules Check (DRC)
via the kicad-cli command-line interface.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class DRCViolation:
    """A single DRC violation."""
    
    type: str
    description: str
    severity: str  # "error", "warning", "exclusion"
    items: list[dict]  # Affected items
    
    @property
    def is_error(self) -> bool:
        return self.severity == "error"
    
    @property
    def is_warning(self) -> bool:
        return self.severity == "warning"


@dataclass
class DRCResult:
    """Result of a DRC check."""
    
    violations: list[DRCViolation]
    source_file: Path
    date: str
    kicad_version: str
    
    @property
    def error_count(self) -> int:
        return sum(1 for v in self.violations if v.is_error)
    
    @property
    def warning_count(self) -> int:
        return sum(1 for v in self.violations if v.is_warning)
    
    @property
    def total_count(self) -> int:
        return len(self.violations)
    
    @property
    def is_clean(self) -> bool:
        return self.error_count == 0
    
    def violations_by_type(self) -> dict[str, int]:
        """Count violations by type."""
        counts = {}
        for v in self.violations:
            counts[v.type] = counts.get(v.type, 0) + 1
        return counts


def run_drc(
    pcb_file: Path | str,
    output_file: Path | str | None = None,
    severity_all: bool = True,
    exit_code_violations: bool = False,
    kicad_cli: str = "kicad-cli",
) -> DRCResult:
    """
    Run KiCad DRC on a PCB file.
    
    Args:
        pcb_file: Path to .kicad_pcb file
        output_file: Optional output file for DRC report (JSON)
        severity_all: Report all severities (errors, warnings, exclusions)
        exit_code_violations: Return nonzero exit code if violations exist
        kicad_cli: Path to kicad-cli executable
        
    Returns:
        DRCResult with violations
        
    Raises:
        FileNotFoundError: If kicad-cli not found
        subprocess.CalledProcessError: If DRC fails
    """
    pcb_file = Path(pcb_file)
    
    if not pcb_file.exists():
        raise FileNotFoundError(f"PCB file not found: {pcb_file}")
    
    # Create output file if not specified
    if output_file is None:
        output_file = pcb_file.parent / f"{pcb_file.stem}-drc.json"
    else:
        output_file = Path(output_file)
    
    # Build command
    cmd = [
        kicad_cli,
        "pcb",
        "drc",
        "--format", "json",
        "--output", str(output_file),
    ]
    
    if severity_all:
        cmd.append("--severity-all")
    
    if exit_code_violations:
        cmd.append("--exit-code-violations")
    
    cmd.append(str(pcb_file))
    
    # Run DRC
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,  # Don't raise on nonzero exit (violations may cause this)
        )
        
        # Check for actual errors (not violations)
        if result.returncode != 0 and not exit_code_violations:
            raise subprocess.CalledProcessError(
                result.returncode,
                cmd,
                result.stdout,
                result.stderr,
            )
        
    except FileNotFoundError:
        raise FileNotFoundError(
            f"kicad-cli not found: {kicad_cli}\n"
            f"Install KiCad or specify path with kicad_cli parameter"
        )
    
    # Parse output
    return parse_drc_report(output_file)


def parse_drc_report(report_file: Path | str) -> DRCResult:
    """
    Parse a KiCad DRC report (JSON format).
    
    Args:
        report_file: Path to DRC report JSON file
        
    Returns:
        DRCResult
    """
    report_file = Path(report_file)
    
    with open(report_file) as f:
        data = json.load(f)
    
    # Parse violations
    violations = []
    
    for v in data.get("violations", []):
        violations.append(DRCViolation(
            type=v.get("type", "unknown"),
            description=v.get("description", ""),
            severity=v.get("severity", "error"),
            items=v.get("items", []),
        ))
    
    return DRCResult(
        violations=violations,
        source_file=Path(data.get("source", report_file.stem)),
        date=data.get("date", ""),
        kicad_version=data.get("kicad_version", ""),
    )


def check_pcb_clean(pcb_file: Path | str, verbose: bool = False) -> bool:
    """
    Quick check if PCB has no DRC errors.
    
    Args:
        pcb_file: Path to .kicad_pcb file
        verbose: Print violations if found
        
    Returns:
        True if no errors, False otherwise
    """
    result = run_drc(pcb_file)
    
    if verbose and not result.is_clean:
        print(f"DRC Violations: {result.error_count} errors, {result.warning_count} warnings")
        
        by_type = result.violations_by_type()
        for vtype, count in sorted(by_type.items(), key=lambda x: -x[1]):
            print(f"  {vtype}: {count}")
    
    return result.is_clean


def run_drc_and_report(
    pcb_file: Path | str,
    verbose: bool = True,
) -> DRCResult:
    """
    Run DRC and print a formatted report.
    
    Args:
        pcb_file: Path to .kicad_pcb file
        verbose: Print detailed report
        
    Returns:
        DRCResult
    """
    if verbose:
        print(f"Running DRC on {Path(pcb_file).name}...")
    
    result = run_drc(pcb_file)
    
    if verbose:
        print(f"\n{'='*70}")
        print("DRC REPORT")
        print(f"{'='*70}")
        print(f"Source: {result.source_file.name}")
        print(f"Date: {result.date}")
        print(f"KiCad: {result.kicad_version}")
        print(f"\nTotal violations: {result.total_count}")
        print(f"  Errors:   {result.error_count}")
        print(f"  Warnings: {result.warning_count}")
        
        if result.total_count > 0:
            print(f"\nViolations by type:")
            by_type = result.violations_by_type()
            for vtype, count in sorted(by_type.items(), key=lambda x: -x[1]):
                print(f"  {vtype:30s}: {count:3d}")
            
            # Show first few violations
            print(f"\nFirst 5 violations:")
            for i, v in enumerate(result.violations[:5], 1):
                print(f"\n{i}. [{v.severity.upper()}] {v.type}")
                print(f"   {v.description}")
                if v.items:
                    for item in v.items[:2]:  # Show first 2 items
                        print(f"   - {item.get('description', 'N/A')}")
        else:
            print(f"\n✅ No violations found!")
    
    return result
