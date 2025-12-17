"""
Base classes and types for validation.

This module defines the common interfaces and types used by all validators.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional

from temper_placer.core.board import Board
from temper_placer.core.netlist import Netlist
from temper_placer.core.state import PlacementState


class ValidationSeverity(Enum):
    """Severity levels for validation issues."""

    INFO = auto()  # Informational, not a problem
    WARNING = auto()  # Potential issue, may affect quality
    ERROR = auto()  # Violation that should be fixed
    CRITICAL = auto()  # Severe violation (safety, DRC failure)


@dataclass
class ValidationIssue:
    """A single validation issue found during checking."""

    severity: ValidationSeverity
    code: str  # Machine-readable code (e.g., "OVERLAP_001")
    message: str  # Human-readable description
    component_refs: List[str] = field(default_factory=list)  # Affected components
    location: Optional[tuple] = None  # (x, y) location if applicable
    details: Dict[str, Any] = field(default_factory=dict)  # Additional data


@dataclass
class ValidationResult:
    """Result of running validation checks."""

    valid: bool  # True if no errors/critical issues
    issues: List[ValidationIssue] = field(default_factory=list)
    metrics: Dict[str, float] = field(default_factory=dict)  # Quality metrics
    elapsed_ms: float = 0.0  # Time taken for validation
    validator_name: str = ""  # Name of validator that ran

    @property
    def error_count(self) -> int:
        """Count of ERROR and CRITICAL severity issues."""
        return sum(
            1
            for i in self.issues
            if i.severity in (ValidationSeverity.ERROR, ValidationSeverity.CRITICAL)
        )

    @property
    def warning_count(self) -> int:
        """Count of WARNING severity issues."""
        return sum(1 for i in self.issues if i.severity == ValidationSeverity.WARNING)

    @property
    def critical_count(self) -> int:
        """Count of CRITICAL severity issues."""
        return sum(1 for i in self.issues if i.severity == ValidationSeverity.CRITICAL)

    def merge(self, other: ValidationResult) -> ValidationResult:
        """Merge another validation result into this one."""
        return ValidationResult(
            valid=self.valid and other.valid,
            issues=self.issues + other.issues,
            metrics={**self.metrics, **other.metrics},
            elapsed_ms=self.elapsed_ms + other.elapsed_ms,
            validator_name=f"{self.validator_name}+{other.validator_name}",
        )

    def summary(self) -> str:
        """Get a human-readable summary."""
        status = "PASS" if self.valid else "FAIL"
        return (
            f"Validation {status}: "
            f"{self.critical_count} critical, "
            f"{self.error_count - self.critical_count} errors, "
            f"{self.warning_count} warnings"
        )


class Validator(ABC):
    """Abstract base class for validators."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Validator name for identification."""
        pass

    @abstractmethod
    def validate(
        self,
        state: PlacementState,
        netlist: Netlist,
        board: Board,
    ) -> ValidationResult:
        """
        Run validation on a placement.

        Args:
            state: Current placement state.
            netlist: Component netlist.
            board: Board definition.

        Returns:
            ValidationResult with any issues found.
        """
        pass

    def is_available(self) -> bool:
        """
        Check if this validator can run in the current environment.

        Override this for validators that depend on external tools.
        """
        return True


class CompositeValidator(Validator):
    """Runs multiple validators and combines results."""

    def __init__(self, validators: List[Validator]):
        self.validators = validators

    @property
    def name(self) -> str:
        return "CompositeValidator"

    def validate(
        self,
        state: PlacementState,
        netlist: Netlist,
        board: Board,
    ) -> ValidationResult:
        """Run all validators and merge results."""
        result = ValidationResult(valid=True, validator_name=self.name)

        for validator in self.validators:
            if validator.is_available():
                sub_result = validator.validate(state, netlist, board)
                result = result.merge(sub_result)

        return result

    def is_available(self) -> bool:
        """At least one validator must be available."""
        return any(v.is_available() for v in self.validators)
