"""
PCL (Placement Constraint Language) parser for loading constraints from YAML — re-export hub.

Implementation extracted to ``pcl._parse_utils``, ``pcl._tag_parser``,
``pcl._tag_expanders``, ``pcl._constraint_parser``, and ``pcl._schema``.
``ConstraintCollection``, ``parse_pcl_file``, and ``load_pcl_collection``
remain here; all helpers are imported from the internal modules.

Example usage:
    >>> from temper_placer.pcl.parser import parse_pcl_file, ConstraintCollection
    >>>
    >>> # Load constraints from YAML file
    >>> collection = parse_pcl_file("configs/half_bridge_constraints.yaml")
    >>> print(len(collection.constraints))
    12
"""

from __future__ import annotations

import copy
import logging
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml  # type: ignore[import-untyped]

from temper_placer.pcl._constraint_parser import _is_resolved, parse_constraint_dict
from temper_placer.pcl._parse_utils import PCLParseError
from temper_placer.pcl._schema import PCLValidationError, validate_pcl_dict
from temper_placer.pcl._tag_expanders import _TAGGED_EXPANDERS
from temper_placer.pcl.constraints import (
    AdjacentConstraint,
    AlignedConstraint,
    AnchoredConstraint,
    BaseConstraint,
    CompilationContext,
    CompilationTarget,
    ConstraintTier,
    ConstraintType,
    EnclosingConstraint,
    KeepoutConstraint,
    OnSideConstraint,
    SeparatedConstraint,
)

if TYPE_CHECKING:
    from temper_placer.core.board import Board
    from temper_placer.core.netlist import Netlist


@dataclass
class ConstraintCollection:
    """Collection of PCL constraints with validation methods.

    Attributes:
        constraints: List of parsed constraints
        version: PCL schema version
        metadata: Optional metadata from YAML file
    """

    constraints: list[BaseConstraint]
    version: str = "1.0"
    metadata: dict[str, Any] | None = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}

    def __len__(self) -> int:
        return len(self.constraints)

    def copy(self) -> ConstraintCollection:
        return ConstraintCollection(
            constraints=copy.deepcopy(self.constraints),
            version=self.version,
            metadata=copy.deepcopy(self.metadata),
        )

    def add(self, constraint: BaseConstraint) -> None:
        self.constraints.append(constraint)

    def compile(self, target: CompilationTarget, context: CompilationContext) -> list:
        """Dispatch all constraints to the target backend.

        Args:
            target: Compilation target (JAX, SAT, or DRC).
            context: CompilationContext with netlist, board, etc.

        Returns:
            List of backend-specific outputs.

        Raises:
            ValueError: If no backend is registered for the target.
        """
        backend_fn = BaseConstraint.backends.get(target.value)  # type: ignore[attr-defined]
        if backend_fn is None:
            raise ValueError(
                f"No backend registered for target '{target.value}'. "
                f"Available: {sorted(BaseConstraint.backends.keys())}"  # type: ignore[attr-defined]
            )
        results = []
        for constraint in self.constraints:
            if target.value not in constraint.targets:
                continue
            if not _is_resolved(constraint, context):
                warnings.warn(
                    f"Constraint '{constraint.id}' references unresolved components, skipping",
                    stacklevel=2,
                )
                continue
            try:
                results.append(backend_fn(constraint, context))
            except Exception as e:
                warnings.warn(
                    f"Constraint '{constraint.id}' failed to compile to "
                    f"'{target.value}': {e}, skipping",
                    stacklevel=2,
                )
        return results

    def by_type(self, constraint_type: ConstraintType) -> list[BaseConstraint]:
        return [c for c in self.constraints if c.constraint_type == constraint_type]

    def by_tier(self, tier: ConstraintTier) -> list[BaseConstraint]:
        return [c for c in self.constraints if c.tier == tier]

    def lint(self, netlist: Netlist, board: Board) -> Any:
        from .linter import lint_constraints

        return lint_constraints(self.constraints, netlist, board)

    def involving_component(self, component: str) -> list[BaseConstraint]:
        return [c for c in self.constraints if c.involves_component(component)]

    def validate_component_refs(self, component_refs: list[str]) -> list[str]:
        """Validate that all component references exist in the netlist.

        Args:
            component_refs: List of valid component reference designators

        Returns:
            List of error messages for invalid references
        """
        errors = []
        component_set = set(component_refs)

        for constraint in self.constraints:
            if isinstance(constraint, (AdjacentConstraint, SeparatedConstraint)):
                refs = [constraint.a, constraint.b]
            elif isinstance(constraint, EnclosingConstraint):
                refs = [constraint.outer] + constraint.inner
            elif isinstance(constraint, (AlignedConstraint, OnSideConstraint)):
                refs = constraint.components
            elif isinstance(constraint, AnchoredConstraint):
                refs = [constraint.component]
            else:
                continue

            for ref in refs:
                if ref.isupper() and "_ZONE" in ref:
                    continue

                if ref not in component_set:
                    errors.append(
                        f"Constraint '{constraint.id}' references unknown component '{ref}'"
                    )

        return errors

    def auto_enrich(self, netlist: Netlist, board: Board | None = None) -> None:
        """Auto-generate constraints from design data.

        Three automatic enrichments:
        1. Decoupling detection: scan netlist for capacitor-IC pairs
        2. Keepout emission: emit KeepoutConstraint for zones with type='keepout'
        3. Tag expansion: expand tagged constraints into concrete constraints

        Args:
            netlist: The netlist to analyze
            board: Optional board for zone-based enrichments
        """
        logger = logging.getLogger(__name__)

        # 1. Decoupling detection
        def auto_detect_decoupling(*a, **kw):
            raise NotImplementedError("auto_detect_decoupling removed (JAX retirement)")

        rules = auto_detect_decoupling(netlist)
        if rules:
            count = len(rules)
            for rule in rules:
                classification = getattr(rule, "_classification", None)
                if classification is not None:
                    tier = (
                        ConstraintTier.HARD
                        if getattr(classification, "name", "") == "BYPASS"
                        else ConstraintTier.STRONG
                    )
                else:
                    tier = ConstraintTier.STRONG
                self.constraints.append(
                    AdjacentConstraint(
                        a=rule.cap_ref,
                        b=rule.ic_ref,
                        max_distance_mm=rule.max_distance_mm,
                        tier=tier,
                        because=(
                            f"Decoupling capacitor {rule.cap_ref} for {rule.ic_ref}"
                            f"{' on net ' + rule.power_pin if rule.power_pin else ''}"
                        ),
                        pin_b=rule.power_pin if rule.power_pin else None,
                    )
                )
            logger.info("Auto-detected %d decoupling constraints", count)

        # 2. Keepout emission from board zones
        if board is not None:
            keepout_count = 0
            for zone in board.zones:
                zone_type = getattr(zone, "zone_type", "placement")
                if zone_type == "keepout":
                    self.constraints.append(
                        KeepoutConstraint(
                            zone_name=zone.name,
                            tier=ConstraintTier.HARD,
                            because=f"Auto-generated from zone '{zone.name}' (type: keepout)",
                            margin_mm=0.0,
                        )
                    )
                    keepout_count += 1
            if keepout_count > 0:
                logger.info("Emitted %d keepout constraint(s) from board zones", keepout_count)

        # 3. Tag expansion
        expanded_count = 0
        new_constraints: list[BaseConstraint] = []

        for constraint in list(self.constraints):
            expander = _TAGGED_EXPANDERS.get(type(constraint))
            if expander is None:
                continue

            new = expander(constraint, netlist)
            new_constraints.extend(new)
            self.constraints.remove(constraint)
            expanded_count += 1

        if new_constraints:
            self.constraints.extend(new_constraints)
        if expanded_count > 0:
            logger.info(
                "Expanded %d tagged constraint(s) into %d concrete constraint(s)",
                expanded_count,
                len(new_constraints),
            )


def parse_pcl_file(path: Path | str) -> ConstraintCollection:
    """Load constraint collection from YAML file.

    Expected YAML format:
        version: "1.0"
        metadata:
          description: "Half-bridge constraints"
          author: "Designer"
        constraints:
          - type: adjacent
            a: Q1
            b: Q2
            max_distance_mm: 10
            tier: 1
            because: "Minimize commutation loop"

    Args:
        path: Path to YAML file

    Returns:
        ConstraintCollection with parsed constraints

    Raises:
        PCLParseError: If file cannot be parsed or has invalid structure
    """
    path = Path(path)

    if not path.exists():
        raise PCLParseError(f"File not found: {path}")

    try:
        with open(path) as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise PCLParseError(f"YAML parse error in {path}: {e}") from e

    if not isinstance(data, dict):
        raise PCLParseError(f"Expected YAML dict at top level, got {type(data)}")

    try:
        validate_pcl_dict(data)
    except PCLValidationError as e:
        raise PCLParseError(str(e)) from e

    version = data.get("version", "1.0")
    metadata = data.get("metadata", {})

    if "constraints" not in data:
        raise PCLParseError("Missing 'constraints' key in YAML")

    constraints_data = data["constraints"]
    if not isinstance(constraints_data, list):
        raise PCLParseError("'constraints' must be a list")

    constraints = []
    for i, constraint_data in enumerate(constraints_data):
        try:
            constraint = parse_constraint_dict(constraint_data)
            constraints.append(constraint)
        except PCLParseError as e:
            raise PCLParseError(f"Error parsing constraint {i}: {e}") from e

    return ConstraintCollection(
        constraints=constraints,
        version=version,
        metadata=metadata,
    )


def load_pcl_collection(directory: Path | str) -> ConstraintCollection:
    """Load all PCL files from a directory and merge into one collection.

    Args:
        directory: Path to directory containing .yaml/.yml files

    Returns:
        ConstraintCollection with all constraints from all files

    Raises:
        PCLParseError: If directory doesn't exist or files can't be parsed
    """
    directory = Path(directory)

    if not directory.exists():
        raise PCLParseError(f"Directory not found: {directory}")

    if not directory.is_dir():
        raise PCLParseError(f"Not a directory: {directory}")

    all_constraints = []
    all_metadata = {}

    yaml_files = sorted(directory.glob("*.yaml")) + sorted(directory.glob("*.yml"))

    if not yaml_files:
        raise PCLParseError(f"No YAML files found in {directory}")

    for yaml_file in yaml_files:
        try:
            collection = parse_pcl_file(yaml_file)
            all_constraints.extend(collection.constraints)
            all_metadata[yaml_file.stem] = collection.metadata
        except PCLParseError as e:
            raise PCLParseError(f"Error loading {yaml_file}: {e}") from e

    return ConstraintCollection(
        constraints=all_constraints,
        version="1.0",
        metadata={"sources": all_metadata},
    )
