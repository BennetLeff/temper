"""
Documentation validation functions for REQ-DFM-03: Assembly Documentation Package.

This module provides validation functions for BOM, CPL, Gerber files, and DNP consistency.
"""

from dataclasses import dataclass
from enum import Enum


class GerberLayerType(Enum):
    """Gerber layer types as defined in REQ-DFM-03."""

    TOP_COPPER = "GTL"  # L1 artwork
    GROUND_PLANE = "G2L"  # L2 artwork
    POWER_PLANE = "G3L"  # L3 artwork
    BOTTOM_COPPER = "GBL"  # L4 artwork
    TOP_SOLDER_MASK = "GTS"
    BOTTOM_SOLDER_MASK = "GBS"
    TOP_SILKSCREEN = "GTO"
    BOTTOM_SILKSCREEN = "GBO"
    BOARD_OUTLINE = "GKO"
    DRILL_FILE = "TXT"  # or .DRL


@dataclass
class BOMEntry:
    """Single line item in a Bill of Materials."""

    item: int
    qty: int
    reference: str  # e.g., "R1,R2,R3" or "U1"
    value: str
    package: str
    description: str
    manufacturer: str
    mpn: str  # Manufacturer Part Number
    supplier: str
    supplier_pn: str
    dnp: bool = False  # Do Not Populate
    notes: str = ""


@dataclass
class CPLEntry:
    """Single line item in a Pick-and-Place file."""

    designator: str
    mid_x: float
    mid_y: float
    layer: str  # "Top" or "Bottom"
    rotation: float


@dataclass
class GerberLayer:
    """Gerber layer specification."""

    layer_type: GerberLayerType
    filename: str
    exists: bool = True


@dataclass
class DocumentationValidationResult:
    """Result of documentation validation."""

    valid: bool
    errors: list[str]
    warnings: list[str]
    missing_components: set[str]
    extra_components: set[str]
    coordinate_mismatches: list[tuple[str, str]]  # (designator, reason)
    missing_layers: list[GerberLayerType]
    dnp_inconsistencies: list[tuple[str, str]]  # (designator, reason)


def validate_bom_completeness(
    bom: list[BOMEntry], netlist_refs: set[str]
) -> DocumentationValidationResult:
    """
    Validate that all components in netlist are in BOM and vice versa.

    Args:
        bom: List of BOM entries
        netlist_refs: Set of component references from netlist

    Returns:
        DocumentationValidationResult with validation results
    """
    errors = []
    warnings = []
    missing_components = set()
    extra_components = set()

    # Extract all component references from BOM
    bom_refs = set()
    for entry in bom:
        # Handle multiple refs separated by commas
        refs = [ref.strip() for ref in entry.reference.split(",")]
        bom_refs.update(refs)

    # Check for missing components (in netlist but not in BOM)
    missing_components = netlist_refs - bom_refs
    if missing_components:
        errors.append(f"Components in netlist but missing from BOM: {sorted(missing_components)}")

    # Check for extra components (in BOM but not in netlist)
    extra_components = bom_refs - netlist_refs
    if extra_components:
        warnings.append(f"Components in BOM but not in netlist: {sorted(extra_components)}")

    # Validate required BOM columns
    required_fields = [
        "item",
        "qty",
        "reference",
        "value",
        "package",
        "description",
        "manufacturer",
        "mpn",
        "supplier",
        "supplier_pn",
    ]

    for i, entry in enumerate(bom, 1):
        for field in required_fields:
            if not getattr(entry, field, None):
                errors.append(f"BOM row {i}: Missing required field '{field}'")

    valid = len(errors) == 0
    return DocumentationValidationResult(
        valid=valid,
        errors=errors,
        warnings=warnings,
        missing_components=missing_components,
        extra_components=extra_components,
        coordinate_mismatches=[],
        missing_layers=[],
        dnp_inconsistencies=[],
    )


def validate_cpl_coordinates(
    cpl: list[CPLEntry], placement_positions: dict[str, tuple[float, float]]
) -> DocumentationValidationResult:
    """
    Validate CPL coordinates match actual component placement.

    Args:
        cpl: List of CPL entries
        placement_positions: Dict mapping designator to (x, y) position

    Returns:
        DocumentationValidationResult with validation results
    """
    errors = []
    warnings = []
    coordinate_mismatches = []

    # Check for missing CPL entries
    cpl_refs = {entry.designator for entry in cpl}
    placement_refs = set(placement_positions.keys())

    missing_cpl = placement_refs - cpl_refs
    if missing_cpl:
        errors.append(f"Components in placement but missing from CPL: {sorted(missing_cpl)}")

    extra_cpl = cpl_refs - placement_refs
    if extra_cpl:
        warnings.append(f"Components in CPL but not in placement: {sorted(extra_cpl)}")

    # Validate coordinate accuracy (within 0.1mm tolerance)
    tolerance = 0.1
    for entry in cpl:
        if entry.designator in placement_positions:
            expected_x, expected_y = placement_positions[entry.designator]
            if (
                abs(entry.mid_x - expected_x) > tolerance
                or abs(entry.mid_y - expected_y) > tolerance
            ):
                coordinate_mismatches.append(
                    (
                        entry.designator,
                        f"CPL ({entry.mid_x}, {entry.mid_y}) vs placement ({expected_x}, {expected_y})",
                    )
                )

    # Validate required CPL columns
    for i, entry in enumerate(cpl, 1):
        if not entry.designator:
            errors.append(f"CPL row {i}: Missing designator")
        if entry.mid_x is None or entry.mid_y is None:
            errors.append(f"CPL row {i}: Missing coordinates")
        if entry.layer not in ["Top", "Bottom"]:
            errors.append(f"CPL row {i}: Invalid layer '{entry.layer}' (must be 'Top' or 'Bottom')")
        if entry.rotation is None:
            errors.append(f"CPL row {i}: Missing rotation")

    valid = len(errors) == 0 and len(coordinate_mismatches) == 0
    return DocumentationValidationResult(
        valid=valid,
        errors=errors,
        warnings=warnings,
        missing_components=set(),
        extra_components=set(),
        coordinate_mismatches=coordinate_mismatches,
        missing_layers=[],
        dnp_inconsistencies=[],
    )


def validate_gerber_layers(gerbers: list[GerberLayer]) -> DocumentationValidationResult:
    """
    Validate that all required Gerber layers are present.

    Args:
        gerbers: List of Gerber layer specifications

    Returns:
        DocumentationValidationResult with validation results
    """
    errors = []
    warnings = []
    missing_layers = []

    # Required layers per REQ-DFM-03
    required_layers = {
        GerberLayerType.TOP_COPPER,
        GerberLayerType.GROUND_PLANE,
        GerberLayerType.POWER_PLANE,
        GerberLayerType.BOTTOM_COPPER,
        GerberLayerType.TOP_SOLDER_MASK,
        GerberLayerType.BOTTOM_SOLDER_MASK,
        GerberLayerType.TOP_SILKSCREEN,
        GerberLayerType.BOTTOM_SILKSCREEN,
        GerberLayerType.BOARD_OUTLINE,
        GerberLayerType.DRILL_FILE,
    }

    # Check which layers are present
    present_layers = {layer.layer_type for layer in gerbers if layer.exists}
    missing_layers = list(required_layers - present_layers)

    if missing_layers:
        errors.append(
            f"Missing required Gerber layers: {[layer.value for layer in missing_layers]}"
        )

    # Validate layer file extensions
    for layer in gerbers:
        expected_ext = f".{layer.layer_type.value}"
        if not layer.filename.lower().endswith(expected_ext.lower()):
            warnings.append(
                f"Layer {layer.layer_type.value}: Unexpected file extension '{layer.filename}'"
            )

    # Check for duplicate layer types
    layer_types = [layer.layer_type for layer in gerbers]
    duplicates = [
        layer_type for layer_type in set(layer_types) if layer_types.count(layer_type) > 1
    ]
    if duplicates:
        errors.append(f"Duplicate layer types found: {[d.value for d in duplicates]}")

    valid = len(errors) == 0
    return DocumentationValidationResult(
        valid=valid,
        errors=errors,
        warnings=warnings,
        missing_components=set(),
        extra_components=set(),
        coordinate_mismatches=[],
        missing_layers=missing_layers,
        dnp_inconsistencies=[],
    )


def check_dnp_consistency(
    bom: list[BOMEntry], cpl: list[CPLEntry]
) -> DocumentationValidationResult:
    """
    Check that DNP (Do Not Populate) flags are consistent between BOM and CPL.

    Args:
        bom: List of BOM entries
        cpl: List of CPL entries

    Returns:
        DocumentationValidationResult with validation results
    """
    errors = []
    warnings = []
    dnp_inconsistencies = []

    # Create lookup dictionaries
    bom_dnp = {}
    for entry in bom:
        refs = [ref.strip() for ref in entry.reference.split(",")]
        for ref in refs:
            bom_dnp[ref] = entry.dnp

    cpl_dnp = {}
    for entry in cpl:
        cpl_dnp[entry.designator] = getattr(
            entry, "dnp", False
        )  # Default to False if not specified

    # Check consistency
    all_refs = set(bom_dnp.keys()) | set(cpl_dnp.keys())

    for ref in all_refs:
        bom_flag = bom_dnp.get(ref, False)
        cpl_flag = cpl_dnp.get(ref, False)

        if bom_flag != cpl_flag:
            dnp_inconsistencies.append((ref, f"BOM DNP={bom_flag} vs CPL DNP={cpl_flag}"))

    if dnp_inconsistencies:
        errors.append(f"DNP inconsistencies found: {len(dnp_inconsistencies)} components")

    # Check for DNP components that still have placement coordinates
    for entry in cpl:
        if entry.designator in bom_dnp and bom_dnp[entry.designator] and (abs(entry.mid_x) > 0.001 or abs(entry.mid_y) > 0.001):
            warnings.append(
                f"DNP component {entry.designator} has non-zero placement coordinates"
            )

    valid = len(errors) == 0
    return DocumentationValidationResult(
        valid=valid,
        errors=errors,
        warnings=warnings,
        missing_components=set(),
        extra_components=set(),
        coordinate_mismatches=[],
        missing_layers=[],
        dnp_inconsistencies=dnp_inconsistencies,
    )
