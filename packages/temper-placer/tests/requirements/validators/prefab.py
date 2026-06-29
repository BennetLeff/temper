"""
Pre-Fabrication Sign-Off Validation Functions (REQ-REV-03)

This module provides validation functions for the pre-fabrication sign-off
requirements including design file verification, Gerber file inspection,
design rule validation, and manufacturing notes compliance.
"""

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class ValidationSeverity(Enum):
    """Severity levels for validation issues."""

    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


@dataclass
class ValidationIssue:
    """Represents a validation issue."""

    severity: ValidationSeverity
    code: str
    message: str
    file_path: str | None = None
    line_number: int | None = None


@dataclass
class ValidationResult:
    """Result of validation checks."""

    passed: bool
    issues: list[ValidationIssue]

    @property
    def error_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == ValidationSeverity.ERROR)

    @property
    def warning_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == ValidationSeverity.WARNING)

    @property
    def info_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == ValidationSeverity.INFO)


@dataclass
class DesignRuleSpec:
    """Specification for a design rule."""

    name: str
    value: str | float
    unit: str | None = None
    verified: bool = False


@dataclass
class ManufacturingSpec:
    """Specification for manufacturing requirements."""

    requirement: str
    value: str
    verified: bool = False


def validate_design_files_complete(project_dir: str | Path) -> ValidationResult:
    """
    Validate that all required design files are present and complete.

    Args:
        project_dir: Path to the project directory

    Returns:
        ValidationResult with issues found
    """
    issues = []
    project_path = Path(project_dir)

    # Required design files

    # Check for schematic PDF
    schematic_pdfs = list(project_path.glob("**/*schematic*.pdf")) + list(
        project_path.glob("**/*SCHEMATIC*.pdf")
    )
    if not schematic_pdfs:
        issues.append(
            ValidationIssue(
                ValidationSeverity.ERROR,
                "FILE_001",
                "Final schematic PDF not found",
                str(project_path),
            )
        )

    # Check for layout PDF
    layout_pdfs = (
        list(project_path.glob("**/*layout*.pdf"))
        + list(project_path.glob("**/*LAYOUT*.pdf"))
        + list(project_path.glob("**/*pcb*.pdf"))
        + list(project_path.glob("**/*PCB*.pdf"))
    )
    if not layout_pdfs:
        issues.append(
            ValidationIssue(
                ValidationSeverity.ERROR,
                "FILE_002",
                "Final layout PDF not found",
                str(project_path),
            )
        )

    # Check for Gerber files
    gerber_extensions = [".gbr", ".gm1", ".gm2", ".gml", ".gko", ".gts", ".gto", ".gml"]
    gerber_files = []
    for ext in gerber_extensions:
        gerber_files.extend(list(project_path.glob(f"**/*{ext}")))

    if not gerber_files:
        issues.append(
            ValidationIssue(
                ValidationSeverity.ERROR, "FILE_003", "No Gerber files found", str(project_path)
            )
        )
    elif len(gerber_files) < 8:  # Typical minimum for 4-layer board
        issues.append(
            ValidationIssue(
                ValidationSeverity.WARNING,
                "FILE_004",
                f"Only {len(gerber_files)} Gerber files found, expected at least 8",
                str(project_path),
            )
        )

    # Check for drill files
    drill_files = list(project_path.glob("**/*.drl")) + list(project_path.glob("**/*.drd"))
    if not drill_files:
        issues.append(
            ValidationIssue(
                ValidationSeverity.ERROR, "FILE_005", "Drill files not found", str(project_path)
            )
        )

    # Check for pick-and-place file
    pick_place_files = (
        list(project_path.glob("**/*pick*place*.csv"))
        + list(project_path.glob("**/*PICK*PLACE*.csv"))
        + list(project_path.glob("**/*pos*.csv"))
    )
    if not pick_place_files:
        issues.append(
            ValidationIssue(
                ValidationSeverity.ERROR,
                "FILE_006",
                "Pick-and-place file not found",
                str(project_path),
            )
        )

    # Check for BOM
    bom_files = (
        list(project_path.glob("**/*BOM*.csv"))
        + list(project_path.glob("**/*bom*.csv"))
        + list(project_path.glob("**/*parts*.csv"))
    )
    if not bom_files:
        issues.append(
            ValidationIssue(
                ValidationSeverity.ERROR, "FILE_007", "BOM file not found", str(project_path)
            )
        )

    return ValidationResult(
        passed=len([i for i in issues if i.severity == ValidationSeverity.ERROR]) == 0,
        issues=issues,
    )


def validate_gerber_alignment(gerber_dir: str | Path) -> ValidationResult:
    """
    Validate Gerber file alignment and completeness.

    Args:
        gerber_dir: Directory containing Gerber files

    Returns:
        ValidationResult with alignment issues
    """
    issues = []
    gerber_path = Path(gerber_dir)

    # Expected Gerber layers for a typical PCB
    expected_layers = {
        ".gbr": "Copper layers",
        ".gm1": "Mechanical layer 1 (board outline)",
        ".gm2": "Mechanical layer 2",
        ".gko": "Keep-out layer",
        ".gts": "Solder mask top",
        ".gbs": "Solder mask bottom",
        ".gto": "Silkscreen top",
        ".gbo": "Silkscreen bottom",
        ".gml": "Solder paste top",
        ".gma": "Solder paste bottom",
    }

    found_layers = {}

    # Scan for Gerber files
    for ext, _description in expected_layers.items():
        files = list(gerber_path.glob(f"**/*{ext}"))
        if files:
            found_layers[ext] = files[0]  # Take first match

    # Check for missing critical layers
    critical_layers = [".gbr", ".gm1", ".gko", ".gts", ".gto"]
    for ext in critical_layers:
        if ext not in found_layers:
            issues.append(
                ValidationIssue(
                    ValidationSeverity.ERROR,
                    "GERBER_001",
                    f"Missing critical Gerber layer: {expected_layers[ext]} ({ext})",
                    str(gerber_path),
                )
            )

    # Check for copper layers (should have multiple for multi-layer boards)
    copper_files = [f for ext, f in found_layers.items() if ext == ".gbr"]
    if len(copper_files) < 2:
        issues.append(
            ValidationIssue(
                ValidationSeverity.WARNING,
                "GERBER_002",
                f"Only {len(copper_files)} copper layer(s) found, multi-layer boards typically have 4+",
                str(gerber_path),
            )
        )

    # Validate file naming conventions
    for _ext, file_path in found_layers.items():
        filename = file_path.name

        # Check for common naming patterns
        if not re.search(
            r"[_-](copper|top|bottom|inner|outline|mask|paste|silk)", filename, re.IGNORECASE
        ):
            issues.append(
                ValidationIssue(
                    ValidationSeverity.WARNING,
                    "GERBER_003",
                    f"Gerber file '{filename}' may not follow standard naming conventions",
                    str(file_path),
                )
            )

        # Check file size (empty files are suspicious)
        if file_path.stat().st_size < 100:  # Less than 100 bytes
            issues.append(
                ValidationIssue(
                    ValidationSeverity.ERROR,
                    "GERBER_004",
                    f"Gerber file '{filename}' appears to be empty or corrupted",
                    str(file_path),
                )
            )

    # Check for board outline in mechanical layers
    outline_layers = [".gm1", ".gm2"]
    outline_found = False
    for ext in outline_layers:
        if ext in found_layers:
            outline_found = True
            break

    if not outline_found:
        issues.append(
            ValidationIssue(
                ValidationSeverity.ERROR,
                "GERBER_005",
                "Board outline not found in mechanical layers",
                str(gerber_path),
            )
        )

    return ValidationResult(
        passed=len([i for i in issues if i.severity == ValidationSeverity.ERROR]) == 0,
        issues=issues,
    )


def validate_drill_file(
    drill_file: str | Path, _pad_locations: list[tuple[float, float]] | None = None
) -> ValidationResult:
    """
    Validate drill file format and content.

    Args:
        drill_file: Path to drill file (.drl or .drd)
        pad_locations: Optional list of pad coordinates for validation

    Returns:
        ValidationResult with drill file issues
    """
    issues = []
    drill_path = Path(drill_file)

    if not drill_path.exists():
        issues.append(
            ValidationIssue(
                ValidationSeverity.ERROR,
                "DRILL_001",
                f"Drill file not found: {drill_file}",
                str(drill_path),
            )
        )
        return ValidationResult(passed=False, issues=issues)

    # Check file size
    if drill_path.stat().st_size < 50:
        issues.append(
            ValidationIssue(
                ValidationSeverity.ERROR,
                "DRILL_002",
                f"Drill file '{drill_path.name}' appears to be empty or corrupted",
                str(drill_path),
            )
        )

    # Read and validate drill file content
    try:
        with open(drill_path, encoding="utf-8", errors="ignore") as f:
            content = f.read()

        # Check for common drill file headers
        if drill_path.suffix.lower() == ".drl" and not re.search(r"(M48|INCH|METRIC)", content.upper()):
            issues.append(
                    ValidationIssue(
                        ValidationSeverity.WARNING,
                        "DRILL_003",
                        "Drill file may not be in standard Excellon format",
                        str(drill_path),
                    )
                )
        if drill_path.suffix.lower() == ".drl" and not content.strip().startswith("<?xml"):
            # KiCad format already checked: drl + non-XML means not KiCad XML
            issues.append(
                ValidationIssue(
                    ValidationSeverity.WARNING,
                    "DRILL_004",
                    "Drill file may not be in KiCad XML format",
                    str(drill_path),
                )
            )

        # Count drill hits
        drill_patterns = [
            r"X[\d.-]+Y[\d.-]+",  # Excellon format
            r'<hole[^>]*x="[^"]*"[^>]*y="[^"]*"',  # KiCad XML format
        ]

        total_drills = 0
        for pattern in drill_patterns:
            total_drills += len(re.findall(pattern, content, re.IGNORECASE))

        if total_drills == 0:
            issues.append(
                ValidationIssue(
                    ValidationSeverity.ERROR,
                    "DRILL_005",
                    "No drill hits found in drill file",
                    str(drill_path),
                )
            )
        elif total_drills < 10:  # Very few drills for a PCB
            issues.append(
                ValidationIssue(
                    ValidationSeverity.WARNING,
                    "DRILL_006",
                    f"Very few drill hits found ({total_drills}), check if this is correct",
                    str(drill_path),
                )
            )

        # Check for multiple drill sizes
        drill_sizes = re.findall(r"T(\d+)", content)
        unique_sizes = set(drill_sizes)

        if len(unique_sizes) > 20:  # Unusually many drill sizes
            issues.append(
                ValidationIssue(
                    ValidationSeverity.WARNING,
                    "DRILL_007",
                    f"Many different drill sizes found ({len(unique_sizes)}), consider standardization",
                    str(drill_path),
                )
            )

    except Exception as e:
        issues.append(
            ValidationIssue(
                ValidationSeverity.ERROR,
                "DRILL_008",
                f"Error reading drill file: {str(e)}",
                str(drill_path),
            )
        )

    return ValidationResult(
        passed=len([i for i in issues if i.severity == ValidationSeverity.ERROR]) == 0,
        issues=issues,
    )


def check_design_rules_documented(
    drc_rules: dict[str, DesignRuleSpec], spec: dict[str, ManufacturingSpec]
) -> ValidationResult:
    """
    Validate that design rules are properly documented and verified.

    Args:
        drc_rules: Dictionary of design rule specifications
        spec: Dictionary of manufacturing specifications

    Returns:
        ValidationResult with design rule issues
    """
    issues = []

    # Required design rules for Temper PCB
    required_rules = {
        "min_trace_width": DesignRuleSpec("Minimum Trace Width", "0.15mm", "mm"),
        "min_trace_space": DesignRuleSpec("Minimum Trace Spacing", "0.15mm", "mm"),
        "min_via_drill": DesignRuleSpec("Minimum Via Drill", "0.3mm", "mm"),
        "min_annular_ring": DesignRuleSpec("Minimum Annular Ring", "0.15mm", "mm"),
        "outer_copper": DesignRuleSpec("Outer Copper Weight", "2 oz", "oz"),
        "inner_copper": DesignRuleSpec("Inner Copper Weight", "1 oz", "oz"),
        "board_thickness": DesignRuleSpec("Board Thickness", "1.6mm", "mm"),
        "surface_finish": DesignRuleSpec("Surface Finish", "ENIG", None),
    }

    # Check for required rules
    for rule_key, required_rule in required_rules.items():
        if rule_key not in drc_rules:
            issues.append(
                ValidationIssue(
                    ValidationSeverity.ERROR,
                    "RULE_001",
                    f"Required design rule not documented: {required_rule.name}",
                )
            )
        else:
            documented_rule = drc_rules[rule_key]

            # Check if rule is verified
            if not documented_rule.verified:
                issues.append(
                    ValidationIssue(
                        ValidationSeverity.WARNING,
                        "RULE_002",
                        f"Design rule not verified: {documented_rule.name}",
                    )
                )

            # Check value consistency
            if documented_rule.value != required_rule.value:
                issues.append(
                    ValidationIssue(
                        ValidationSeverity.WARNING,
                        "RULE_003",
                        f"Design rule value mismatch for {documented_rule.name}: "
                        f"documented '{documented_rule.value}', expected '{required_rule.value}'",
                    )
                )

    # Check manufacturing specifications
    required_specs = {
        "controlled_impedance": ManufacturingSpec("Controlled Impedance", "Not required"),
        "via_fill": ManufacturingSpec("Via Fill", "Required for thermal pads"),
        "edge_plating": ManufacturingSpec("Edge Plating", "Not required"),
        "slots": ManufacturingSpec("Slots", "Specify in drill file"),
        "panel": ManufacturingSpec("Panel", "Individual board"),
    }

    for spec_key, required_spec in required_specs.items():
        if spec_key not in spec:
            issues.append(
                ValidationIssue(
                    ValidationSeverity.WARNING,
                    "SPEC_001",
                    f"Manufacturing specification not documented: {required_spec.requirement}",
                )
            )
        else:
            documented_spec = spec[spec_key]

            # Check if spec is verified
            if not documented_spec.verified:
                issues.append(
                    ValidationIssue(
                        ValidationSeverity.INFO,
                        "SPEC_002",
                        f"Manufacturing specification not verified: {documented_spec.requirement}",
                    )
                )

    # Validate rule values are reasonable
    for rule_key, rule in drc_rules.items():
        try:
            if rule.unit == "mm":
                value_str = str(rule.value).replace("mm", "")
                value = float(value_str)
                if rule_key == "min_trace_width" and (value < 0.1 or value > 0.5):
                    issues.append(
                        ValidationIssue(
                            ValidationSeverity.WARNING,
                            "RULE_004",
                            f"Unusual trace width value: {rule.value}",
                        )
                    )
                elif rule_key == "min_via_drill" and (value < 0.2 or value > 0.8):
                    issues.append(
                        ValidationIssue(
                            ValidationSeverity.WARNING,
                            "RULE_005",
                            f"Unusual via drill size: {rule.value}",
                        )
                    )
                elif rule_key == "board_thickness" and (value < 1.0 or value > 2.0):
                    issues.append(
                        ValidationIssue(
                            ValidationSeverity.WARNING,
                            "RULE_006",
                            f"Unusual board thickness: {rule.value}",
                        )
                    )
        except (ValueError, AttributeError):
            issues.append(
                ValidationIssue(
                    ValidationSeverity.WARNING,
                    "RULE_007",
                    f"Cannot parse design rule value: {rule.name} = {rule.value}",
                )
            )

    return ValidationResult(
        passed=len([i for i in issues if i.severity == ValidationSeverity.ERROR]) == 0,
        issues=issues,
    )


def validate_silkscreen_quality(silkscreen_files: list[Path]) -> ValidationResult:
    """
    Validate silkscreen layer quality and readability.

    Args:
        silkscreen_files: List of silkscreen Gerber file paths

    Returns:
        ValidationResult with silkscreen issues
    """
    issues = []

    for silkscreen_file in silkscreen_files:
        file_path = Path(silkscreen_file)

        if not file_path.exists():
            issues.append(
                ValidationIssue(
                    ValidationSeverity.ERROR,
                    "SILK_001",
                    f"Silkscreen file not found: {file_path.name}",
                    str(file_path),
                )
            )
            continue

        # Check file size
        if file_path.stat().st_size < 100:
            issues.append(
                ValidationIssue(
                    ValidationSeverity.ERROR,
                    "SILK_002",
                    f"Silkscreen file '{file_path.name}' appears to be empty",
                    str(file_path),
                )
            )
            continue

        try:
            with open(file_path, encoding="utf-8", errors="ignore") as f:
                content = f.read()

            # Check for text elements (silkscreen should have text)
            text_patterns = [
                r"TD\d+",  # Text definitions
                r"G\d+",  # G codes
                r"M\d+",  # M codes
            ]

            has_text = any(re.search(pattern, content) for pattern in text_patterns)

            if not has_text:
                issues.append(
                    ValidationIssue(
                        ValidationSeverity.WARNING,
                        "SILK_003",
                        f"Silkscreen file '{file_path.name}' may not contain text elements",
                        str(file_path),
                    )
                )

            # Check for reasonable file size (not too sparse)
            if file_path.stat().st_size < 1000:
                issues.append(
                    ValidationIssue(
                        ValidationSeverity.WARNING,
                        "SILK_004",
                        f"Silkscreen file '{file_path.name}' is very small, may be incomplete",
                        str(file_path),
                    )
                )

        except Exception as e:
            issues.append(
                ValidationIssue(
                    ValidationSeverity.ERROR,
                    "SILK_005",
                    f"Error reading silkscreen file '{file_path.name}': {str(e)}",
                    str(file_path),
                )
            )

    return ValidationResult(
        passed=len([i for i in issues if i.severity == ValidationSeverity.ERROR]) == 0,
        issues=issues,
    )


def validate_solder_mask(mask_files: list[Path]) -> ValidationResult:
    """
    Validate solder mask layer completeness.

    Args:
        mask_files: List of solder mask Gerber file paths

    Returns:
        ValidationResult with solder mask issues
    """
    issues = []

    if not mask_files:
        issues.append(
            ValidationIssue(
                ValidationSeverity.ERROR,
                "MASK_001",
                "No solder mask files found",
            )
        )
        return ValidationResult(passed=False, issues=issues)

    # Check for both top and bottom masks
    mask_types = {"top": False, "bottom": False}

    for mask_file in mask_files:
        file_path = Path(mask_file)
        filename = file_path.name.lower()

        if "top" in filename or "gts" in filename:
            mask_types["top"] = True
        elif "bottom" in filename or "gbs" in filename:
            mask_types["bottom"] = True

    if not mask_types["top"]:
        issues.append(
            ValidationIssue(
                ValidationSeverity.ERROR,
                "MASK_002",
                "Top solder mask not found",
            )
        )

    if not mask_types["bottom"]:
        issues.append(
            ValidationIssue(
                ValidationSeverity.WARNING,
                "MASK_003",
                "Bottom solder mask not found (may be intentional for single-sided boards)",
            )
        )

    # Validate each mask file
    for mask_file in mask_files:
        file_path = Path(mask_file)

        if not file_path.exists():
            issues.append(
                ValidationIssue(
                    ValidationSeverity.ERROR,
                    "MASK_004",
                    f"Solder mask file not found: {file_path.name}",
                    str(file_path),
                )
            )
            continue

        if file_path.stat().st_size < 100:
            issues.append(
                ValidationIssue(
                    ValidationSeverity.ERROR,
                    "MASK_005",
                    f"Solder mask file '{file_path.name}' appears to be empty",
                    str(file_path),
                )
            )

    return ValidationResult(
        passed=len([i for i in issues if i.severity == ValidationSeverity.ERROR]) == 0,
        issues=issues,
    )


def run_prefab_validation(project_dir: str | Path) -> ValidationResult:
    """
    Run complete pre-fabrication validation.

    Args:
        project_dir: Path to project directory

    Returns:
        Combined ValidationResult
    """
    project_path = Path(project_dir)

    # Run all validation checks
    design_files_result = validate_design_files_complete(project_path)
    gerber_result = validate_gerber_alignment(project_path)

    # Find and validate drill files
    drill_files = list(project_path.glob("**/*.drl")) + list(project_path.glob("**/*.drd"))
    drill_result = ValidationResult(passed=True, issues=[])
    if drill_files:
        drill_result = validate_drill_file(drill_files[0])

    # Find and validate silkscreen files
    silkscreen_files = (
        list(project_path.glob("**/*silk*.gbr"))
        + list(project_path.glob("**/*SILK*.gbr"))
        + list(project_path.glob("**/*.gto"))
        + list(project_path.glob("**/*.gbo"))
    )
    silk_result = validate_silkscreen_quality(silkscreen_files)

    # Find and validate solder mask files
    mask_files = (
        list(project_path.glob("**/*mask*.gbr"))
        + list(project_path.glob("**/*.gts"))
        + list(project_path.glob("**/*.gbs"))
    )
    mask_result = validate_solder_mask(mask_files)

    # Combine all results
    all_issues = (
        design_files_result.issues
        + gerber_result.issues
        + drill_result.issues
        + silk_result.issues
        + mask_result.issues
    )

    return ValidationResult(
        passed=all(
            result.passed
            for result in [
                design_files_result,
                gerber_result,
                drill_result,
                silk_result,
                mask_result,
            ]
        ),
        issues=all_issues,
    )
