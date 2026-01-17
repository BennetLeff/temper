"""Severity levels for check issues."""

from enum import Enum, auto


class Severity(Enum):
    """
    Check result severity levels.

    Severity determines how issues are weighted in metrics and whether
    they cause the overall check to fail.

    Levels:
        INFO: Informational message, no issue (weight: 0.0)
        WARNING: Potential issue that may affect quality (weight: 1.0)
        ERROR: Violation that should be fixed (weight: 10.0)
        CRITICAL: Safety-critical violation that blocks manufacturing (weight: 100.0)
    """

    INFO = auto()
    WARNING = auto()
    ERROR = auto()
    CRITICAL = auto()

    @property
    def weight(self) -> float:
        """
        Penalty weight for this severity level.

        Used to compute aggregate penalty scores for optimization integration.
        """
        weights = {
            Severity.INFO: 0.0,
            Severity.WARNING: 1.0,
            Severity.ERROR: 10.0,
            Severity.CRITICAL: 100.0,
        }
        return weights[self]

    @property
    def is_failure(self) -> bool:
        """Returns True if this severity indicates a check failure."""
        return self in (Severity.ERROR, Severity.CRITICAL)

    def __lt__(self, other: "Severity") -> bool:
        """Compare severity levels (INFO < WARNING < ERROR < CRITICAL)."""
        if not isinstance(other, Severity):
            return NotImplemented
        return self.value < other.value

    def __le__(self, other: "Severity") -> bool:
        if not isinstance(other, Severity):
            return NotImplemented
        return self.value <= other.value
